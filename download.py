from pathlib import Path
import asyncio
from telethon import TelegramClient
from telethon.tl.types import InputMessagesFilterVideo
from telethon.errors import SessionPasswordNeededError
import typer
from config import load_config
import webbrowser

config = load_config()

async def autenticar(client: TelegramClient):
    if not await client.is_user_authorized():
        print("Autenticando via QR Code...")
        qr_login = await client.qr_login()
        
        # Abre o link no navegador
        webbrowser.open(qr_login.url)
        print("Uma página foi aberta no navegador.")
        print("Abra o Telegram no celular → Configurações → Dispositivos → Conectar dispositivo")
        print("Escaneie o QR Code exibido no navegador.")
        
        try:
            await qr_login.wait(timeout=120)
            print("Autenticado com sucesso!")
        except SessionPasswordNeededError:
            senha = typer.prompt("Digite sua senha de dois fatores", hide_input=True)
            await client.sign_in(password=senha)

async def baixar_limitado(target: str, quantidade: int | None = None):
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