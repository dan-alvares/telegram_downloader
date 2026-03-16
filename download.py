from pathlib import Path
from rich.progress import Progress, BarColumn, TransferSpeedColumn, TextColumn, TimeRemainingColumn
import asyncio
from telethon import TelegramClient
from telethon.tl.types import InputMessagesFilterVideo
import typer
from config import load_config
from util import (
    parse_numeros, autenticar, baixar_video,
    curso_completo, resetar_curso, registrar_curso
)

config = load_config()

async def baixar_limitado(target: str, numeros: int | list[int] | range | None = None):
    client = TelegramClient(config['session_name'], config['api_id'], config['api_hash'])
    await client.connect()
    await autenticar(client)

    try:
        canal_id = int(target.split('/c/')[1].split('/')[0])
        canal = int(f'-100{canal_id}')  # pyright: ignore[reportAssignmentType]
        await client.get_dialogs()
        try:
            entity = await client.get_entity(canal)
        except ValueError:
            entity = await client.get_entity(canal)

        base_dir = Path(config['download_dir'])
        pasta_dos_videos = base_dir / entity.title

    except Exception as e:
        print(f"Erro ao obter entidade: {e}")
        return

    pasta_dos_videos.mkdir(parents=True, exist_ok=True)

    result = await client.get_messages(canal, filter=InputMessagesFilterVideo)  # pyright: ignore[reportUnknownMemberType]
    total_videos = result.total
    nome_curso = entity.title

    if curso_completo(nome_curso):
        resposta = typer.confirm(f'"{nome_curso}" já foi baixado por completo. Deseja baixar novamente?', default=False)
        if not resposta:
            print("Download pulado.")
            await client.disconnect()
            return
        resetar_curso(nome_curso, target, total_videos)
    else:
        registrar_curso(nome_curso, target, total_videos)

    if isinstance(numeros, (list, range)):
        pendentes = set(numeros)
        limite = total_videos
    elif isinstance(numeros, int):
        pendentes = None
        limite = numeros
    else:
        pendentes = None
        limite = total_videos

    print(f"Total de vídeos no canal: {total_videos}. Baixando: {len(pendentes) if pendentes is not None else limite}.")

    messages = client.iter_messages(entity, filter=InputMessagesFilterVideo, limit=limite)
    semaphore = asyncio.Semaphore(config['concurrent_downloads'])
    contador = total_videos
    tasks = []

    with Progress(
        TextColumn("[bold blue]{task.fields[filename]}"),
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.1f}%",
        "—",
        TransferSpeedColumn(),
        "—",
        TimeRemainingColumn(),
    ) as progress:
        async for message in messages:
            tasks.append(asyncio.create_task(baixar_video(
                message, contador, client, progress, semaphore,
                nome_curso, pasta_dos_videos, pendentes
            )))
            contador -= 1

        await asyncio.gather(*tasks)

    await client.disconnect()
    print("Downloads concluídos.")

async def baixar_paralelo(target: str):
    client = TelegramClient(config['session_name'], config['api_id'], config['api_hash'])
    await client.connect()
    await autenticar(client)

    try:
        canal_id = int(target.split('/c/')[1].split('/')[0])
        canal = int(f'-100{canal_id}')  # pyright: ignore[reportAssignmentType]
        await client.get_dialogs()
        try:
            entity = await client.get_entity(canal)
        except ValueError:
            entity = await client.get_entity(canal)

        base_dir = Path(config['download_dir'])
        pasta_dos_videos = base_dir / entity.title

    except Exception as e:
        print(f"Erro ao obter entidade: {e}")
        return

    pasta_dos_videos.mkdir(parents=True, exist_ok=True)

    result = await client.get_messages(canal, filter=InputMessagesFilterVideo)  # pyright: ignore[reportUnknownMemberType]
    total_videos = result.total
    nome_curso = entity.title

    if curso_completo(nome_curso):
        resposta = typer.confirm(f'"{nome_curso}" já foi baixado por completo. Deseja baixar novamente?', default=False)
        if not resposta:
            print("Download pulado.")
            await client.disconnect()
            return
        resetar_curso(nome_curso, target, total_videos)
    else:
        registrar_curso(nome_curso, target, total_videos)

    messages = client.iter_messages(entity, filter=InputMessagesFilterVideo)
    semaphore = asyncio.Semaphore(config['concurrent_downloads'])
    contador = total_videos
    tasks = []

    with Progress(
        TextColumn("[bold blue]{task.fields[filename]}"),
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.1f}%",
        "—",
        TransferSpeedColumn(),
        "—",
        TimeRemainingColumn(),
    ) as progress:
        async for message in messages:
            tasks.append(asyncio.create_task(baixar_video(
                message, contador, client, progress, semaphore,
                nome_curso, pasta_dos_videos
            )))
            contador -= 1

        await asyncio.gather(*tasks)

    await client.disconnect()
    print("Downloads concluídos.")

app = typer.Typer(help="Download de vídeos do Telegram")

@app.command()
def apenas():
    link = typer.prompt('Informe o link do canal ou grupo para baixar todos os vídeos')
    quantidade = typer.prompt('Quantos vídeos deseja baixar?\nSe deseja baixar X últimos números de um canal informe apenas o número (ex: 10)\nSe deseja baixar um intervalo de vídeos informe no formato "início-fim" (ex: 1-44)\nSe deseja baixar vídeos específicos informe os números separados por vírgula (ex: 10,7,4,1)')
    asyncio.run(baixar_limitado(link, numeros=parse_numeros(quantidade)))

@app.command()
def tudo():
    link = typer.prompt('Informe o link do canal ou grupo para baixar vídeos em paralelo')
    asyncio.run(baixar_paralelo(link))

if __name__ == "__main__":
    app()