from pathlib import Path
from collections import deque
from rich.progress import (
    Progress,
    BarColumn,
    TransferSpeedColumn,
    TextColumn,
    FileSizeColumn,
    TotalFileSizeColumn,
    TimeRemainingColumn,
)
import asyncio
from telethon import TelegramClient
from telethon.tl.types import (
    DocumentAttributeFilename,
    DocumentAttributeVideo,
)
import typer
from config import load_config
from util import (
    parse_numeros,
    parse_links,
    autenticar,
    baixar_video,
    historico_completo,
    resetar_historico,
    registrar_historico,
    selecionar_ou_criar_colecao,
    carregar,
    COMPRESSED_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
    IMAGE_EXTENSIONS,
    ANEXO_EXTENSIONS,
)

config = load_config()

VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".m4v")

COMPRESSED_MIMETYPES = (
    "application/zip",
    "application/x-rar-compressed",
    "application/x-rar",
    "application/x-7z-compressed",
    "application/gzip",
    "application/x-tar",
)

DOCUMENT_MIMETYPES = (
    "application/pdf",
    "text/plain",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/html",
)

IMAGE_MIMETYPES = ("image/jpeg",)

TARGET_MIMETYPES = COMPRESSED_MIMETYPES + DOCUMENT_MIMETYPES + IMAGE_MIMETYPES


def is_target_file(message) -> bool:
    """Retorna True se a mensagem contém vídeo, compactado, documento ou imagem."""
    if not message.document:
        return False

    mime = getattr(message.document, "mime_type", "") or ""
    if mime in TARGET_MIMETYPES:
        return True

    filename = None
    is_video_attr = False

    for attr in message.document.attributes:
        if isinstance(attr, DocumentAttributeFilename):
            filename = attr.file_name.lower()
        if isinstance(attr, DocumentAttributeVideo):
            is_video_attr = True

    is_video = is_video_attr or (filename and filename.endswith(VIDEO_EXTENSIONS))
    is_compressed = filename and filename.endswith(COMPRESSED_EXTENSIONS)
    is_document = filename and filename.endswith(DOCUMENT_EXTENSIONS)
    is_image = filename and filename.endswith(IMAGE_EXTENSIONS)

    return bool(is_video or is_compressed or is_document or is_image)


def _eh_anexo_message(message) -> bool:
    """Verifica se a mensagem é um anexo (compactado, documento ou imagem)."""
    if not message.document:
        return False

    mime = getattr(message.document, "mime_type", "") or ""
    if mime in TARGET_MIMETYPES:
        # Vídeos podem ter mime video/* — só é anexo se NÃO for vídeo por atributo
        for attr in message.document.attributes:
            if isinstance(attr, DocumentAttributeVideo):
                return False
        return True

    for attr in message.document.attributes:
        if isinstance(attr, DocumentAttributeFilename):
            return attr.file_name.lower().endswith(ANEXO_EXTENSIONS)

    return False


async def coletar_mensagens_filtradas(client, canal) -> list:
    """Itera todas as mensagens do canal do mais antigo ao mais recente."""
    filtered = []
    async for message in client.iter_messages(canal, reverse=True):
        if is_target_file(message):
            filtered.append(message)
    return filtered


def _separar_e_enumerar(messages: list) -> list[tuple[object, int]]:
    """
    Recebe uma lista de mensagens filtradas e retorna uma lista de tuplas
    (message, numero), onde 'numero' é o índice dentro do próprio tipo:
    vídeos são numerados 1..N independente dos anexos e vice-versa.
    A ordem original (por message.id) é preservada.
    """
    contador_videos = 0
    contador_anexos = 0
    resultado = []

    for message in messages:
        if _eh_anexo_message(message):
            contador_anexos += 1
            resultado.append((message, contador_anexos))
        else:
            contador_videos += 1
            resultado.append((message, contador_videos))

    return resultado


async def continuar_download():
    historico = carregar()

    pendentes = [
        (colecao, nome, info)
        for colecao, cursos in historico.items()
        for nome, info in cursos.items()
        if info["status"] == "incompleto"
    ]

    if not pendentes:
        print("Nenhum download pendente encontrado no seu histórico.\n")
        return

    for colecao, nome, info in pendentes:
        print(f'Continuando download de "{nome}" ({colecao})...')
        await baixar_paralelo(info["canal"], colecao_forcada=colecao)


async def baixar_limitado(
    target: str,
    numeros: int | list[int] | range | None = None,
    colecao: str | None = None,
):
    client = TelegramClient(
        config["session_name"], config["api_id"], config["api_hash"]
    )
    await client.connect()
    await autenticar(client)

    try:
        canal_id = int(target.split("/c/")[1].split("/")[0])
        canal = int(f"-100{canal_id}")  # pyright: ignore[reportAssignmentType]
        await client.get_dialogs()
        try:
            entity = await client.get_entity(canal)
        except ValueError:
            entity = await client.get_entity(canal)

        nome_curso = entity.title

        if colecao is None:
            colecao = await selecionar_ou_criar_colecao()

        base_dir = Path(config["download_dir"])
        pasta_dos_videos = base_dir / colecao / nome_curso

    except Exception as e:
        print(f"Erro ao obter entidade: {e}")
        return

    pasta_dos_videos.mkdir(parents=True, exist_ok=True)

    print("Coletando arquivos do canal...")
    all_messages = await coletar_mensagens_filtradas(client, canal)

    total_videos = sum(1 for m in all_messages if not _eh_anexo_message(m))
    total_anexos = sum(1 for m in all_messages if _eh_anexo_message(m))

    if historico_completo(colecao, nome_curso):
        resposta = typer.confirm(
            f'"{nome_curso}" já foi baixado por completo. Deseja baixar novamente?',
            default=False,
        )
        if not resposta:
            print("Download pulado.")
            await client.disconnect()
            return
        resetar_historico(colecao, nome_curso, target, total_videos, total_anexos)
    else:
        registrar_historico(colecao, nome_curso, target, total_videos, total_anexos)

    enumerados = _separar_e_enumerar(all_messages)

    if isinstance(numeros, (list, range)):
        pendentes = set(numeros)
        messages_enum = enumerados
    elif isinstance(numeros, int):
        pendentes = None
        messages_enum = enumerados[:numeros]
    else:
        pendentes = None
        messages_enum = enumerados

    total_baixar = len(pendentes) if pendentes is not None else len(messages_enum)
    print(
        f"Vídeos: {total_videos} | Anexos: {total_anexos} | Baixando: {total_baixar}."
    )

    semaphore = asyncio.Semaphore(config["concurrent_downloads"])
    tasks = []

    with Progress(
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
    ) as progress:
        for message, numero in messages_enum:
            tasks.append(
                asyncio.create_task(
                    baixar_video(
                        message,
                        numero,
                        client,
                        progress,
                        semaphore,
                        colecao,
                        nome_curso,
                        pasta_dos_videos,
                        nome_canal=nome_curso,
                        pendentes=pendentes,
                    )
                )
            )

        await asyncio.gather(*tasks)

    await client.disconnect()
    print("Downloads concluídos.")


async def baixar_paralelo(
    target: str | list[str],
    colecao_forcada: str | None = None,
):
    client = TelegramClient(
        config["session_name"], config["api_id"], config["api_hash"]
    )
    await client.connect()
    await autenticar(client)

    links = [target] if isinstance(target, str) else list(target)

    await client.get_dialogs()
    entradas: list[dict] = []
    for link in links:
        try:
            canal_id = int(link.split("/c/")[1].split("/")[0])
            canal = int(f"-100{canal_id}")  # pyright: ignore[reportAssignmentType]
            try:
                entity = await client.get_entity(canal)
            except ValueError:
                entity = await client.get_entity(canal)
            entradas.append({"link": link, "canal": canal, "entity": entity})
        except Exception as e:
            print(f"Erro ao obter entidade para {link}: {e}")

    if not entradas:
        await client.disconnect()
        return

    colecao: str | None = colecao_forcada

    if colecao is None and len(entradas) > 1:
        typer.echo(
            f"\n{len(entradas)} links na fila. Escolha a coleção para este lote:"
        )
        colecao = await selecionar_ou_criar_colecao()
    elif colecao is None:
        nome_curso_unico = entradas[0]["entity"].title
        typer.echo(f'\nEscolha a coleção para "{nome_curso_unico}":')
        colecao = await selecionar_ou_criar_colecao()

    for entrada in entradas:
        nome_curso = entrada["entity"].title

        print(f'Coletando arquivos de "{nome_curso}"...')
        filtered = await coletar_mensagens_filtradas(client, entrada["canal"])

        total_videos = sum(1 for m in filtered if not _eh_anexo_message(m))
        total_anexos = sum(1 for m in filtered if _eh_anexo_message(m))

        entrada["messages_enum"] = _separar_e_enumerar(filtered)
        entrada["total_videos"] = total_videos
        entrada["total_anexos"] = total_anexos

        if historico_completo(colecao, nome_curso):
            resposta = typer.confirm(
                f'"{nome_curso}" já foi baixado por completo. Deseja baixar novamente?',
                default=False,
            )
            if not resposta:
                entrada["pular"] = True
                continue
            resetar_historico(
                colecao, nome_curso, entrada["link"], total_videos, total_anexos
            )
        else:
            registrar_historico(
                colecao, nome_curso, entrada["link"], total_videos, total_anexos
            )

        entrada["pular"] = False

    typer.echo(f'\nTodos os links registrados em "{colecao}". Iniciando downloads...')

    fila = deque(entradas)
    while fila:
        entrada = fila.popleft()
        restantes = len(fila)
        nome_curso = entrada["entity"].title

        if entrada.get("pular"):
            print(f'"{nome_curso}" pulado.')
            continue

        print(
            f"\nProcessando: {entrada['link']}"
            + (f" ({restantes} restante(s) na fila)" if restantes else "")
        )

        base_dir = Path(config["download_dir"])
        pasta_dos_videos = base_dir / colecao / nome_curso
        pasta_dos_videos.mkdir(parents=True, exist_ok=True)

        typer.echo(
            f'Iniciando download de "{nome_curso}" em "{colecao}"...'
            f" ({entrada['total_videos']} vídeo(s), {entrada['total_anexos']} anexo(s))\n"
        )

        # Mensagens já coletadas em ordem crescente (reverse=True no iter_messages)
        messages_enum = entrada["messages_enum"]

        semaphore = asyncio.Semaphore(config["concurrent_downloads"])
        tasks = []

        with Progress(
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
        ) as progress:
            for message, numero in messages_enum:
                tasks.append(
                    asyncio.create_task(
                        baixar_video(
                            message,
                            numero,
                            client,
                            progress,
                            semaphore,
                            colecao,
                            nome_curso,
                            pasta_dos_videos,
                            nome_canal=nome_curso,
                        )
                    )
                )

            await asyncio.gather(*tasks)

        print(
            f'"{nome_curso}" concluído.'
            + (" Próximo na fila..." if fila else " Fila finalizada.")
        )

    await client.disconnect()


app = typer.Typer(help="Download de vídeos do Telegram")


@app.command()
def apenas():
    link = typer.prompt("Informe o link do canal ou grupo para baixar todos os vídeos")
    quantidade = typer.prompt(
        'Quantos vídeos deseja baixar?\nSe deseja baixar X últimos números de um canal informe apenas o número (ex: 10)\nSe deseja baixar um intervalo de vídeos informe no formato "início-fim" (ex: 1-44)\nSe deseja baixar vídeos específicos informe os números separados por vírgula (ex: 10,7,4,1)'
    )
    asyncio.run(baixar_limitado(link, numeros=parse_numeros(quantidade)))


@app.command()
def tudo():
    links = typer.prompt(
        "Informe o(s) link(s) do canal ou grupo (separe por vírgula para múltiplos)"
    )
    asyncio.run(baixar_paralelo(parse_links(links)))


@app.command()
def continuar():
    typer.echo("Continuando downloads pendentes...")
    asyncio.run(continuar_download())


if __name__ == "__main__":
    app()
