import asyncio
from telethon import TelegramClient
from config import load_config
import typer

config = load_config()

async def verificar_link(client: TelegramClient, link: str):
    try:
        canal_id = int(link.split("/c/")[1].split("/")[0])
        canal = int(f"-100{canal_id}")

        entidade = await client.get_entity(canal)
        print(f"Canal encontrado: {entidade.title}") # type: ignore

    except ValueError as e:
        print("Link inválido ou canal privado.\nErro:", e)


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


if __name__ == "__main__":
    asyncio.run(main())