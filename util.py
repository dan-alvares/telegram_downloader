import json
import sys
from pathlib import Path
import asyncio
from telethon import TelegramClient
from telethon.errors.rpcerrorlist import FloodWaitError
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import DocumentAttributeFilename
from rich.progress import Progress
from config import load_config
import typer
from loguru import logger
import qrcode

config = load_config()


def get_base_dir() -> Path:
    if "__compiled__" in dir():
        return Path(sys.executable).parent
    return Path(__file__).parent


HISTORICO_FILE = get_base_dir() / "historico_downloads.json"

COLECAO_GENERICA = "Sem Coleção"

_OPCAO_NOVA = "•  Criar nova coleção"
_OPCAO_NENHUMA = "•  Sem coleção"

COMPRESSED_EXTENSIONS = (".rar", ".zip", ".7z", ".tar", ".gz")
DOCUMENT_EXTENSIONS = (".pdf", ".txt", ".docx", ".doc", ".html", ".htm")
IMAGE_EXTENSIONS = (".jpg", ".jpeg")

ANEXO_EXTENSIONS = COMPRESSED_EXTENSIONS + DOCUMENT_EXTENSIONS + IMAGE_EXTENSIONS

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


def parse_numeros(valor: str) -> int | list[int] | range | None:
    if not valor:
        return None
    if "-" in valor and valor.count("-") == 1:
        inicio, fim = valor.split("-")
        return range(int(inicio), int(fim) + 1)
    if "," in valor:
        return [int(n) for n in valor.split(",")]
    return int(valor)


def parse_links(valor: str) -> str | list[str]:
    if not valor:
        return None
    if "," in valor:
        return [link.strip() for link in valor.split(",")]
    return valor.strip()


async def verificar_link(client: TelegramClient, link: str) -> str:
    """Verifica o link e retorna o título do canal/grupo, ou string vazia em caso de erro."""
    try:
        canal_id = int(link.split("/c/")[1].split("/")[0])
        canal = int(f"-100{canal_id}")
        entidade = await client.get_entity(canal)
        print(f"Canal encontrado: {entidade.title}")  # type: ignore
        return entidade.title  # type: ignore
    except ValueError as e:
        print("Link inválido ou canal privado.\nErro:", e)
        return ""


async def autenticar(client: TelegramClient):
    if not await client.is_user_authorized():
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


async def main():
    async with TelegramClient(
        config["session_name"], config["api_id"], config["api_hash"]
    ) as client:
        while True:
            link = typer.prompt("Digite o link do canal ou grupo do Telegram")
            await verificar_link(client, link)
            verificar_novamente = typer.confirm("Deseja verificar outro link?")
            if not verificar_novamente:
                print("Encerrando o programa.")
                break


def carregar() -> dict:
    if not HISTORICO_FILE.exists():
        return {}
    with open(HISTORICO_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def salvar(historico: dict):
    with open(HISTORICO_FILE, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)


def listar_colecoes() -> list[str]:
    """Retorna os nomes de todas as coleções já existentes no histórico."""
    historico = carregar()
    return list(historico.keys())


async def selecionar_ou_criar_colecao() -> str:
    """
    Interativamente pergunta ao usuário a qual coleção o download pertence.
    Permite escolher uma existente com setas direcionais, criar uma nova, ou
    não vincular a nenhuma (agrupa em COLECAO_GENERICA).
    Retorna o nome da coleção escolhida/criada.
    """
    import questionary
    from questionary import Style

    estilo = Style(
        [
            ("selected", "fg:cyan bold"),  # opção destacada no menu
            ("pointer", "fg:cyan bold"),  # seta ❯
            ("highlighted", "fg:cyan bold"),  # texto da opção em foco
        ]
    )

    colecoes = [c for c in listar_colecoes() if c != COLECAO_GENERICA]
    opcoes = colecoes + [_OPCAO_NOVA, _OPCAO_NENHUMA]

    escolha = await questionary.select(
        "A qual coleção este download pertence?",
        choices=opcoes,
        style=estilo,
        instruction="(use as setas para navegar)",
    ).ask_async()

    if escolha is None:
        raise typer.Abort()

    if escolha == _OPCAO_NENHUMA:
        typer.echo(f'Agrupando em "{COLECAO_GENERICA}".')
        return COLECAO_GENERICA

    if escolha == _OPCAO_NOVA:
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


# Estrutura do JSON:
# {
#   "<coleção>": {
#     "<nome_curso>": {
#       "status": "incompleto" | "completo",
#       "canal": "<link>",
#       "total_videos": N,
#       "total_anexos": N,
#       "videos": {
#         "<message_id>": { "status": bool, "arquivo": "<filename>" }
#       },
#       "anexos": {
#         "<message_id>": { "status": bool, "arquivo": "<filename>" }
#       }
#     }
#   }
# }


def is_anexo(extensao: str) -> bool:
    """Retorna True se a extensão corresponde a um anexo (compactado, documento ou imagem)."""
    return extensao.lower() in ANEXO_EXTENSIONS


def registrar_historico(
    colecao: str,
    nome: str,
    canal: str,
    total_videos: int,
    total_anexos: int,
) -> dict:
    historico = carregar()
    historico.setdefault(colecao, {})
    if nome not in historico[colecao]:
        historico[colecao][nome] = {
            "status": "incompleto",
            "canal": canal,
            "total_videos": total_videos,
            "total_anexos": total_anexos,
            "videos": {},
            "anexos": {},
        }
        salvar(historico)
    return historico


def registrar_arquivo(
    colecao: str,
    nome: str,
    file_id: int,
    filename: str,
    eh_anexo: bool,
):
    """Registra um arquivo (vídeo ou anexo) no histórico com status False."""
    historico = carregar()
    chave = "anexos" if eh_anexo else "videos"
    if str(file_id) not in historico[colecao][nome][chave]:
        historico[colecao][nome][chave][str(file_id)] = {
            "status": False,
            "arquivo": filename,
        }
        salvar(historico)


def marcar_baixado(
    colecao: str,
    nome: str,
    file_id: int,
    filename: str,
    eh_anexo: bool,
):
    """Marca um arquivo (vídeo ou anexo) como baixado e atualiza o status geral."""
    historico = carregar()
    chave = "anexos" if eh_anexo else "videos"
    historico[colecao][nome][chave][str(file_id)] = {
        "status": True,
        "arquivo": filename,
    }

    total_videos = historico[colecao][nome]["total_videos"]
    total_anexos = historico[colecao][nome]["total_anexos"]
    baixados_videos = sum(
        1 for v in historico[colecao][nome]["videos"].values() if v["status"]
    )
    baixados_anexos = sum(
        1 for a in historico[colecao][nome]["anexos"].values() if a["status"]
    )

    if baixados_videos >= total_videos and baixados_anexos >= total_anexos:
        historico[colecao][nome]["status"] = "completo"

    salvar(historico)


def historico_completo(colecao: str, nome: str) -> bool:
    historico = carregar()
    return historico.get(colecao, {}).get(nome, {}).get("status") == "completo"


def resetar_historico(
    colecao: str,
    nome: str,
    canal: str,
    total_videos: int,
    total_anexos: int,
):
    historico = carregar()
    historico.setdefault(colecao, {})
    historico[colecao][nome] = {
        "status": "incompleto",
        "canal": canal,
        "total_videos": total_videos,
        "total_anexos": total_anexos,
        "videos": {},
        "anexos": {},
    }
    salvar(historico)


def _log_ctx(colecao: str, canal: str, arquivo: str) -> str:
    """Monta o prefixo de contexto padrão para as entradas de log."""
    return f"[coleção: {colecao}] [canal: {canal}] [arquivo: {arquivo}]"


def _obter_extensao(message) -> str:
    """
    Retorna a extensão real do arquivo da mensagem.
    Fallback para '.mp4' em vídeos nativos sem DocumentAttributeFilename.
    """
    if message.document:
        for attr in message.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                return Path(attr.file_name).suffix
    return ".mp4"


async def baixar_video(
    message,
    numero: int,
    client: TelegramClient,
    progress: Progress,
    semaphore: asyncio.Semaphore,
    colecao: str,
    nome_historico: str,
    pasta_dos_videos: Path,
    nome_canal: str = "",
    pendentes: set[int] | None = None,
):
    async with semaphore:
        if pendentes is not None and numero not in pendentes:
            return

        extensao = _obter_extensao(message)
        eh_anexo = is_anexo(extensao)

        # Nome baseado no índice do tipo: 1.mp4, 2.mp4 ou 1.rar, 2.rar etc.
        nome_arquivo = f"{numero}{extensao}"
        filename = pasta_dos_videos / nome_arquivo
        ctx = _log_ctx(colecao, nome_canal, filename.name)

        historico = carregar()
        chave = "anexos" if eh_anexo else "videos"
        file_entry = (
            historico.get(colecao, {})
            .get(nome_historico, {})
            .get(chave, {})
            .get(str(message.id))
        )

        if file_entry:
            arquivo_no_disco = pasta_dos_videos / file_entry["arquivo"]
            ctx_entry = _log_ctx(colecao, nome_canal, file_entry["arquivo"])

            if file_entry["status"] and arquivo_no_disco.exists():
                logger.info(f"{ctx_entry} | Já baixado (histórico), pulando.")
                return

            elif file_entry["status"] and not arquivo_no_disco.exists():
                logger.warning(
                    f"{ctx_entry} | Arquivo marcado como baixado, mas não encontrado no disco."
                )
                return

            if not file_entry["status"] and arquivo_no_disco.exists():
                logger.warning(
                    f"{ctx_entry} | Arquivo incompleto encontrado no disco, removendo para novo download."
                )
                arquivo_no_disco.unlink()
        else:
            registrar_arquivo(
                colecao, nome_historico, message.id, filename.name, eh_anexo
            )
            if filename.exists():
                logger.info(
                    f"{ctx} | Arquivo já existe no disco, marcando como baixado."
                )
                progress.console.log(f"Já existe no disco: {filename.name}")
                marcar_baixado(
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
            marcar_baixado(colecao, nome_historico, message.id, filename.name, eh_anexo)
            logger.success(f"{ctx} | Download concluído com sucesso.")
            await asyncio.sleep(0.5)

        except FloodWaitError as e:
            logger.warning(
                f"{ctx} | Flood wait detectado: aguardando {e.seconds}s antes de tentar novamente."
            )
            progress.console.log(f"[yellow]Flood wait: aguardando {e.seconds}s...[/]")
            if filename.exists():
                filename.unlink()
            await asyncio.sleep(e.seconds)
            await baixar_video(
                message,
                numero,
                client,
                progress,
                semaphore,
                colecao,
                nome_historico,
                pasta_dos_videos,
                nome_canal,
                pendentes,
            )
            return

        except Exception as e:
            logger.error(f"{ctx} | Erro ao baixar: {e}")
            progress.console.log(f"[red]Erro ao baixar {filename.name}: {e}[/]")
            if filename.exists():
                filename.unlink()
                logger.warning(f"{ctx} | Arquivo incompleto removido do disco.")
                progress.console.log(
                    f"[yellow]Arquivo incompleto removido: {filename.name}[/]"
                )

        finally:
            progress.remove_task(task_id)


if __name__ == "__main__":
    asyncio.run(main())
