from pathlib import Path
import asyncio
from telethon import TelegramClient
from telethon.tl.types import InputMessagesFilterVideo
import typer
# from util import converter_videos
from config import load_config
from tqdm.asyncio import tqdm

config = load_config()

async def baixar_tudo(target: str):
    async with TelegramClient(config['session_name'], config['api_id'], config['api_hash']) as client:
        try:
            canal_id = int(target.split('/c/')[1].split('/')[0])
            canal = int(f'-100{canal_id}')  # pyright: ignore[reportAssignmentType]

            entity = await client.get_entity(canal)

            base_dir = Path(config['download_dir'])
            pasta_dos_videos = base_dir / entity.title

        except Exception as e:
            print(f"Erro ao obter entidade: {e}")
            return

        pasta_dos_videos.mkdir(parents=True, exist_ok=True)

        result = await client.get_messages(
            canal,
            filter=InputMessagesFilterVideo,
        )  # pyright: ignore[reportUnknownMemberType]

        total_videos = result.total

        messages = client.iter_messages(entity)

        contador = total_videos

        async for message in tqdm(
            messages,
            total=total_videos,
            desc="Baixando vídeos",
            unit="video"
        ):
            if not message.video:
                continue

            filename = pasta_dos_videos / f"{contador}.mp4"

            if filename.exists():
                contador -= 1
                continue

            await client.download_media(
                message.video,
                file=filename
            )

            contador -= 1

            await asyncio.sleep(1)  # evita FloodWait

async def baixar_paralelo(target: str):

    async with TelegramClient(config['session_name'], config['api_id'], config['api_hash']) as client:

        try:
            canal_id = int(target.split('/c/')[1].split('/')[0])
            canal = int(f'-100{canal_id}')  # pyright: ignore[reportAssignmentType]

            await client.get_dialogs() 

            entity = await client.get_entity(canal)

            base_dir = Path(config['download_dir'])
            pasta_dos_videos = base_dir / entity.title

        except Exception as e:
            print(f"Erro ao obter entidade: {e}")
            return

        pasta_dos_videos.mkdir(parents=True, exist_ok=True)

        result = await client.get_messages(
            canal,
            filter=InputMessagesFilterVideo,
        )  # pyright: ignore[reportUnknownMemberType]

        total_videos = result.total

        messages = client.iter_messages(entity)

        semaphore = asyncio.Semaphore(4)
        contador = total_videos
        tasks = []

        pbar = tqdm(total=total_videos, desc="Baixando vídeos", unit="video")

        async def baixar_video(message, numero):

            async with semaphore:
                filename = pasta_dos_videos / f"{numero}.mp4"

                if filename.exists():
                    pbar.update(1)
                    return

                await client.download_media(
                    message.video,
                    file=filename
                )

                pbar.update(1)
                await asyncio.sleep(0.5)

        async for message in messages:
            if not message.video:
                continue

            tasks.append(
                asyncio.create_task(
                    baixar_video(message, contador)
                )
            )

            contador -= 1

        await asyncio.gather(*tasks)
        pbar.close()

        print("Downloads concluídos. Iniciando compressão com ffmpeg...")

        # await converter_videos(pasta_dos_videos)

app = typer.Typer(help="Download de vídeos do Telegram")

@app.command()
def tudo():
    link = typer.prompt('Informe o link do canal ou grupo para vaixar todos os vídeos.')
    asyncio.run(baixar_tudo(link))

@app.command()
def paralelo():
    link = typer.prompt('Informe o link do canal ou grupo para baixar vídeos em paralelo.')
    asyncio.run(baixar_paralelo(link))

if __name__ == "__main__":
    app()