import asyncio
from collections import deque
from pathlib import Path

import typer
from loguru import logger
from rich.progress import (
    BarColumn,
    FileSizeColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TotalFileSizeColumn,
    TransferSpeedColumn,
)
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.errors.rpcerrorlist import FloodWaitError
from telethon.tl.types import DocumentAttributeFilename, DocumentAttributeVideo

import qrcode

from constants import (
    ANEXO_EXTENSIONS,
    COLECAO_GENERICA,
    TARGET_MIMETYPES,
    VIDEO_EXTENSIONS,
    get_base_dir,
)
from historico import HistoricoManager


logger.configure(
    handlers=[
        {
            "sink": get_base_dir() / "logs" / "app.log",
            "rotation": "10 MB",
            "retention": "7 days",
            "format": "[{time:DD-MM-YYYY HH:mm:ss}] [{level}] {message}",
        },
    ]
)

_PROGRESS_COLUMNS = (
    TextColumn("[bold blue]{task.fields[filename]}"),
    BarColumn(bar_width=20),
    "[progress.percentage]{task.percentage:>3.1f}%",
    " [",
    FileSizeColumn(),
    ":",
    TotalFileSizeColumn(),
    "] ",
    TransferSpeedColumn(),
    TimeRemainingColumn(),
)


class MessageFilter:
    """Classifica mensagens do Telegram em vídeos, anexos ou irrelevantes."""

    @staticmethod
    def _get_filename(message) -> str | None:
        if not message.document:
            return None
        for attr in message.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                return attr.file_name.lower()
        return None

    @staticmethod
    def _has_video_attr(message) -> bool:
        if not message.document:
            return False
        return any(
            isinstance(attr, DocumentAttributeVideo)
            for attr in message.document.attributes
        )

    @classmethod
    def is_target(cls, message) -> bool:
        """True se a mensagem contém vídeo, compactado, documento ou imagem."""
        if not message.document:
            return False

        mime = getattr(message.document, "mime_type", "") or ""
        if mime in TARGET_MIMETYPES:
            return True

        filename = cls._get_filename(message)
        is_video = cls._has_video_attr(message) or (
            filename and filename.endswith(VIDEO_EXTENSIONS)
        )
        is_non_video = filename and filename.endswith(ANEXO_EXTENSIONS)
        return bool(is_video or is_non_video)

    @classmethod
    def is_anexo(cls, message) -> bool:
        """True se a mensagem é um anexo (compactado, documento ou imagem)."""
        if not message.document:
            return False

        mime = getattr(message.document, "mime_type", "") or ""
        if mime in TARGET_MIMETYPES:
            # Vídeos podem ter mime video/* — só é anexo se não tiver atributo de vídeo
            return not cls._has_video_attr(message)

        filename = cls._get_filename(message)
        return bool(filename and filename.endswith(ANEXO_EXTENSIONS))

    @staticmethod
    def get_extension(message) -> str:
        """Retorna a extensão real do arquivo; fallback para '.mp4' em vídeos nativos."""
        if message.document:
            for attr in message.document.attributes:
                if isinstance(attr, DocumentAttributeFilename):
                    return Path(attr.file_name).suffix
        return ".mp4"

    @classmethod
    def separar_e_enumerar(cls, messages: list) -> list[tuple[object, int]]:
        """
        Enumera mensagens separadamente por tipo: vídeos (1..N) e anexos (1..M).
        A ordem original é preservada.
        """
        contador_videos = 0
        contador_anexos = 0
        resultado = []

        for message in messages:
            if cls.is_anexo(message):
                contador_anexos += 1
                resultado.append((message, contador_anexos))
            else:
                contador_videos += 1
                resultado.append((message, contador_videos))

        return resultado


class TelegramDownloader:
    """
    Gerencia a conexão com o Telegram e orquestra os downloads.

    Responsabilidades:
      - Autenticação (QR code / senha 2FA)
      - Coleta e filtragem de mensagens
      - Download individual com retry, flood-wait e histórico
      - Orquestração paralela (baixar_limitado, baixar_paralelo, continuar)
    """

    def __init__(self, config: dict):
        self._config = config
        self._historico = HistoricoManager()
        self._filter = MessageFilter()
        self._client: TelegramClient | None = None

    async def _conectar(self) -> TelegramClient:
        client = TelegramClient(
            self._config["session_name"],
            self._config["api_id"],
            self._config["api_hash"],
        )
        await client.connect()
        await self._autenticar(client)
        self._client = client
        return client

    @staticmethod
    async def _autenticar(client: TelegramClient) -> None:
        if await client.is_user_authorized():
            return

        print("Autenticando via QR Code...")
        qr_login = await client.qr_login()
        qr = qrcode.QRCode()
        qr.add_data(qr_login.url)
        qr.make()
        qr.print_ascii()
        print(
            "Abra o Telegram no celular → Configurações → Dispositivos → Conectar dispositivo"
        )
        print("Escaneie o QR Code acima.")
        try:
            await qr_login.wait(timeout=120)
            print("Autenticado com sucesso!")
        except SessionPasswordNeededError:
            senha = typer.prompt("Digite sua senha de dois fatores", hide_input=True)
            await client.sign_in(password=senha)

    async def _resolver_canal(self, client: TelegramClient, link: str):
        canal_id = int(link.split("/c/")[1].split("/")[0])
        canal = int(f"-100{canal_id}")
        try:
            return canal, await client.get_entity(canal)
        except ValueError:
            return canal, await client.get_entity(canal)

    async def verificar_link(self, link: str) -> str:
        """Verifica o link e retorna o título do canal/grupo, ou '' em caso de erro."""
        client = await self._conectar()
        try:
            _, entidade = await self._resolver_canal(client, link)
            print(f"Canal encontrado: {entidade.title}")
            return entidade.title
        except (ValueError, Exception) as e:
            print("Link inválido ou canal privado.\nErro:", e)
            return ""
        finally:
            await client.disconnect()

    async def _coletar_mensagens(self, client: TelegramClient, canal) -> list:
        filtered = []
        async for message in client.iter_messages(canal, reverse=True):
            if self._filter.is_target(message):
                filtered.append(message)
        return filtered

    async def _baixar_arquivo(
        self,
        message,
        numero: int,
        client: TelegramClient,
        progress: Progress,
        semaphore: asyncio.Semaphore,
        colecao: str,
        nome_historico: str,
        pasta: Path,
        nome_canal: str = "",
        pendentes: set[int] | None = None,
    ) -> None:
        async with semaphore:
            if pendentes is not None and numero not in pendentes:
                return

            extensao = self._filter.get_extension(message)
            eh_anexo = extensao.lower() in ANEXO_EXTENSIONS
            nome_arquivo = f"{numero}{extensao}"
            filename = pasta / nome_arquivo
            ctx = f"[{colecao}] - {nome_canal}] [arquivo: {filename.name}]"

            file_entry = self._historico.obter_entrada_arquivo(
                colecao, nome_historico, message.id, eh_anexo
            )

            if file_entry:
                arquivo_no_disco = pasta / file_entry["arquivo"]
                ctx_entry = (
                    f"[{colecao}] - {nome_canal}] [arquivo: {file_entry['arquivo']}]"
                )

                if file_entry["status"] and arquivo_no_disco.exists():
                    logger.info(f"{ctx_entry} | Já baixado (histórico), pulando.")
                    return

                if file_entry["status"] and not arquivo_no_disco.exists():
                    logger.warning(
                        f"{ctx_entry} | Marcado como baixado, mas não encontrado no disco."
                    )
                    return

                if not file_entry["status"] and arquivo_no_disco.exists():
                    logger.warning(
                        f"{ctx_entry} | Arquivo incompleto encontrado no disco, removendo."
                    )
                    arquivo_no_disco.unlink()
            else:
                self._historico.registrar_arquivo(
                    colecao, nome_historico, message.id, filename.name, eh_anexo
                )
                if filename.exists():
                    logger.info(
                        f"{ctx} | Arquivo já existe no disco, marcando como baixado."
                    )
                    progress.console.log(f"Já existe no disco: {filename.name}")
                    self._historico.marcar_baixado(
                        colecao, nome_historico, message.id, filename.name, eh_anexo
                    )
                    return

            task_id = progress.add_task("download", filename=filename.name, total=None)

            def progresso(bytes_baixados, total_bytes):
                progress.update(task_id, completed=bytes_baixados, total=total_bytes)

            try:
                logger.info(f"{ctx} | Iniciando download.")
                media = message.document or message
                await client.download_media(
                    media, file=filename, progress_callback=progresso
                )
                self._historico.marcar_baixado(
                    colecao, nome_historico, message.id, filename.name, eh_anexo
                )
                logger.success(f"{ctx} | Download concluído com sucesso.")
                await asyncio.sleep(0.5)

            except FloodWaitError as e:
                logger.warning(f"{ctx} | Flood wait: aguardando {e.seconds}s.")
                progress.console.log(
                    f"[yellow]Flood wait: aguardando {e.seconds}s...[/]"
                )
                if filename.exists():
                    filename.unlink()
                await asyncio.sleep(e.seconds)
                await self._baixar_arquivo(
                    message,
                    numero,
                    client,
                    progress,
                    semaphore,
                    colecao,
                    nome_historico,
                    pasta,
                    nome_canal,
                    pendentes,
                )

            except Exception as e:
                if filename.exists():
                    filename.unlink()
                    logger.warning(f"{ctx} | Arquivo incompleto removido do disco.")
                    progress.console.log(
                        f"[yellow]Arquivo incompleto removido: {filename.name}[/]"
                    )

                if "file reference" in str(e).lower() or "expired" in str(e).lower():
                    logger.warning(
                        f"{ctx} | Referência expirada, recarregando mensagem..."
                    )
                    progress.console.log(
                        f"[yellow]Referência expirada, recarregando: {filename.name}[/]"
                    )
                    try:
                        message = await client.get_messages(
                            message.peer_id, ids=message.id
                        )
                        if message:
                            await self._baixar_arquivo(
                                message,
                                numero,
                                client,
                                progress,
                                semaphore,
                                colecao,
                                nome_historico,
                                pasta,
                                nome_canal,
                                pendentes,
                            )
                    except Exception as retry_err:
                        logger.error(
                            f"{ctx} | Falha ao recarregar mensagem: {retry_err}"
                        )
                        progress.console.log(
                            f"[red]Falha ao recarregar {filename.name}: {retry_err}[/]"
                        )
                    return

                logger.error(f"{ctx} | Erro ao baixar: {e}")
                progress.console.log(f"[red]Erro ao baixar {filename.name}: {e}[/]")

            finally:
                progress.remove_task(task_id)

    def _criar_tasks(
        self,
        messages_enum: list[tuple],
        client: TelegramClient,
        progress: Progress,
        semaphore: asyncio.Semaphore,
        colecao: str,
        nome_arquivo: str,
        pasta: Path,
        pendentes: set[int] | None = None,
    ) -> list:
        return [
            asyncio.create_task(
                self._baixar_arquivo(
                    message,
                    numero,
                    client,
                    progress,
                    semaphore,
                    colecao,
                    nome_arquivo,
                    pasta,
                    nome_canal=nome_arquivo,
                    pendentes=pendentes,
                )
            )
            for message, numero in messages_enum
        ]

    async def baixar_limitado(
        self,
        target: str,
        numeros: int | list[int] | range | None = None,
        colecao: str | None = None,
    ) -> None:
        """Baixa um subconjunto de vídeos de um único canal."""
        client = await self._conectar()
        try:
            await client.get_dialogs()
            canal, entity = await self._resolver_canal(client, target)
            nome_arquivo = entity.title

            if colecao is None:
                colecao = await ColecaoSelector(self._historico).selecionar()

            pasta = Path(self._config["download_dir"]) / colecao / nome_arquivo
            pasta.mkdir(parents=True, exist_ok=True)

            all_messages = await self._coletar_mensagens(client, canal)

            total_videos = sum(1 for m in all_messages if not self._filter.is_anexo(m))
            total_anexos = sum(1 for m in all_messages if self._filter.is_anexo(m))

            self._historico.registrar(
                colecao, nome_arquivo, target, total_videos, total_anexos
            )

            enumerados = self._filter.separar_e_enumerar(all_messages)

            if isinstance(numeros, (list, range)):
                pendentes = set(numeros)
                messages_enum = enumerados
            elif isinstance(numeros, int):
                pendentes = None
                messages_enum = enumerados[:numeros]
            else:
                pendentes = None
                messages_enum = enumerados

            total_baixar = (
                len(pendentes) if pendentes is not None else len(messages_enum)
            )
            print(
                f"Vídeos: {total_videos} | Anexos: {total_anexos} | Baixando: {total_baixar}."
            )

            semaphore = asyncio.Semaphore(self._config["concurrent_downloads"])
            with Progress(*_PROGRESS_COLUMNS) as progress:
                tasks = self._criar_tasks(
                    messages_enum,
                    client,
                    progress,
                    semaphore,
                    colecao,
                    nome_arquivo,
                    pasta,
                    pendentes,
                )
                await asyncio.gather(*tasks)

            print("Downloads concluídos.")

        except Exception as e:
            print(f"Erro: {e}")
        finally:
            await client.disconnect()

    async def baixar_paralelo(
        self,
        target: str | list[str],
        colecao_forcada: str | None = None,
    ) -> None:
        """Baixa todos os vídeos de um ou mais canais, sequencialmente por canal."""
        client = await self._conectar()
        try:
            links = [target] if isinstance(target, str) else list(target)
            await client.get_dialogs()

            entradas: list[dict] = []
            for link in links:
                try:
                    canal, entity = await self._resolver_canal(client, link)
                    entradas.append({"link": link, "canal": canal, "entity": entity})
                except Exception as e:
                    print(f"Erro ao obter entidade para {link}: {e}")

            if not entradas:
                return

            colecao = colecao_forcada
            if colecao is None:
                selector = ColecaoSelector(self._historico)
                if len(entradas) > 1:
                    typer.echo(
                        f"\n{len(entradas)} links na fila. Escolha a coleção para este lote:"
                    )
                else:
                    typer.echo(
                        f'\nEscolha a coleção para "{entradas[0]["entity"].title}":'
                    )
                colecao = await selector.selecionar()

            for entrada in entradas:
                nome_arquivo = entrada["entity"].title
                typer.echo(f'Coletando arquivos de "{nome_arquivo}"...')
                filtered = await self._coletar_mensagens(client, entrada["canal"])

                total_videos = sum(1 for m in filtered if not self._filter.is_anexo(m))
                total_anexos = sum(1 for m in filtered if self._filter.is_anexo(m))

                entrada["messages_enum"] = self._filter.separar_e_enumerar(filtered)
                entrada["total_videos"] = total_videos
                entrada["total_anexos"] = total_anexos

                self._historico.registrar(
                    colecao, nome_arquivo, entrada["link"], total_videos, total_anexos
                )

            typer.echo(
                f'\nTodos os links registrados em "{colecao}". Iniciando downloads...'
            )

            fila = deque(entradas)
            while fila:
                entrada = fila.popleft()
                restantes = len(fila)
                nome_arquivo = entrada["entity"].title

                typer.echo(
                    f"\nProcessando: {entrada['link']}"
                    + (f" ({restantes} restante(s) na fila)" if restantes else "")
                )

                pasta = Path(self._config["download_dir"]) / colecao / nome_arquivo
                pasta.mkdir(parents=True, exist_ok=True)

                typer.echo(
                    f'Baixando "{nome_arquivo}" em "{colecao}"...'
                    f" ({entrada['total_videos']} vídeo(s), {entrada['total_anexos']} anexo(s))\n"
                )

                semaphore = asyncio.Semaphore(self._config["concurrent_downloads"])
                with Progress(*_PROGRESS_COLUMNS) as progress:
                    tasks = self._criar_tasks(
                        entrada["messages_enum"],
                        client,
                        progress,
                        semaphore,
                        colecao,
                        nome_arquivo,
                        pasta,
                    )
                    await asyncio.gather(*tasks)

        finally:
            await client.disconnect()

    async def continuar_downloads(self) -> None:
        """Retoma todos os downloads marcados como incompletos no histórico."""
        pendentes = self._historico.pendentes()
        if not pendentes:
            typer.echo("Nenhum download pendente encontrado no seu histórico.\n")
            return
        for colecao, nome, info in pendentes:
            typer.echo(f'Continuando download de "{nome}" ({colecao})...')
            await self.baixar_paralelo(info["canal"], colecao_forcada=colecao)


class ColecaoSelector:
    """Interação com o usuário para escolha ou criação de coleções."""

    def __init__(self, historico: HistoricoManager):
        self._historico = historico

    async def selecionar(self) -> str:
        import questionary
        from constants import OPCAO_NOVA, OPCAO_NENHUMA

        colecoes = [
            c for c in self._historico.listar_colecoes() if c != COLECAO_GENERICA
        ]
        opcoes = colecoes + [OPCAO_NOVA, OPCAO_NENHUMA]

        escolha = await questionary.select(
            "A qual coleção este download pertence?",
            choices=opcoes,
            default=OPCAO_NENHUMA,
            instruction="(use as setas para navegar)",
        ).ask_async()

        if escolha is None:
            raise typer.Abort()

        if escolha == OPCAO_NENHUMA:
            typer.echo(f'Agrupando em "{COLECAO_GENERICA}".')
            return COLECAO_GENERICA

        if escolha == OPCAO_NOVA:
            colecao = await questionary.text(
                "Nome da nova coleção:",
                validate=lambda v: "Informe um nome." if not v.strip() else True,
            ).ask_async()
            if colecao is None:
                raise typer.Abort()
            colecao = colecao.strip()
            typer.echo(f'Nova coleção criada: "{colecao}".')
            return colecao

        typer.echo(f'Adicionando à coleção "{escolha}".')
        return escolha
