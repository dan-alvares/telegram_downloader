from pathlib import Path
import asyncio
from telethon import TelegramClient
from telethon.tl.types import InputMessagesFilterVideo
import typer
from config import load_config
# from tqdm.asyncio import tqdm

config = load_config()

async def baixar_limitado(target: str, quantidade: int | None = None):
    async with TelegramClient(config['session_name'], config['api_id'], config['api_hash']) as client:
        try:
            canal_id = int(target.split('/c/')[1].split('/')[0])
            canal = int(f'-100{canal_id}')  # pyright: ignore[reportAssignmentType]

            await client.get_dialogs()

            try:
                entity = await client.get_entity(canal)
            except ValueError:
                canal_id = int(target.split('/c/')[1].split('/')[0])
                canal = int(f'-100{canal_id}')
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
        limite = quantidade if quantidade is not None else total_videos

        print(f"Total de vídeos no canal: {total_videos}. Baixando: {limite}.")

        messages = client.iter_messages(entity, filter=InputMessagesFilterVideo, limit=limite)

        semaphore = asyncio.Semaphore(4)
        contador = total_videos
        tasks = []

        async def baixar_video(message, numero):
            async with semaphore:
                filename = pasta_dos_videos / f"{numero}.mp4"

                if filename.exists():
                    print(f"Já existe: {filename.name}")
                    return

                print(f"Baixando: {filename.name}")
                await client.download_media(message.video, file=filename)
                print(f"Concluído: {filename.name}")
                await asyncio.sleep(0.5)

        async for message in messages:
            tasks.append(asyncio.create_task(baixar_video(message, contador)))
            contador -= 1

        await asyncio.gather(*tasks)
        print("Downloads concluídos.")


async def baixar_paralelo(target: str):
    async with TelegramClient(config['session_name'], config['api_id'], config['api_hash']) as client:
        try:
            canal_id = int(target.split('/c/')[1].split('/')[0])
            canal = int(f'-100{canal_id}')  # pyright: ignore[reportAssignmentType]

            await client.get_dialogs()

            try:
                entity = await client.get_entity(canal)
            except ValueError:
                canal_id = int(target.split('/c/')[1].split('/')[0])
                canal = int(f'-100{canal_id}')
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

        messages = client.iter_messages(entity, filter=InputMessagesFilterVideo)

        semaphore = asyncio.Semaphore(4)
        contador = total_videos
        tasks = []

        async def baixar_video(message, numero):
            async with semaphore:
                filename = pasta_dos_videos / f"{numero}.mp4"

                if filename.exists():
                    print(f"Já existe: {filename.name}")
                    return

                print(f"Baixando: {filename.name}")
                await client.download_media(message.video, file=filename)
                print(f"Concluído: {filename.name}")
                await asyncio.sleep(0.5)

        async for message in messages:
            tasks.append(asyncio.create_task(baixar_video(message, contador)))
            contador -= 1

        await asyncio.gather(*tasks)
        print("Downloads concluídos.")

app = typer.Typer(help="Download de vídeos do Telegram")

@app.command()
def apenas():
    link = typer.prompt('Informe o link do canal ou grupo para vaixar todos os vídeos.')
    quantidade = int(typer.prompt('Quantos vídeos deseja baixar?'))
    asyncio.run(baixar_limitado(link, quantidade))

@app.command()
def tudo():
    link = typer.prompt('Informe o link do canal ou grupo para baixar vídeos em paralelo.')
    asyncio.run(baixar_paralelo(link))

if __name__ == "__main__":
    app()