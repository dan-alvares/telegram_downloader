from pathlib import Path
import json
from collections import deque
from rich.progress import (
    Progress,
    BarColumn,
    TransferSpeedColumn,
    TextColumn,
    TimeRemainingColumn,
)
import asyncio
from telethon import TelegramClient
from telethon.tl.types import InputMessagesFilterVideo
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
)

config = load_config()


async def continuar_download():
    with open("historico_downloads.json", "r") as arquivo:
        historico = json.load(arquivo)

    for nome, info in historico.items():
        if info["status"] == "incompleto":
            print(f'Continuando download de "{nome}"...')
            await baixar_paralelo(info["canal"])
        else:
            print("Nenhum download pendente encontrado no seu histórico.")


async def baixar_limitado(target: str, numeros: int | list[int] | range | None = None):
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

        base_dir = Path(config["download_dir"])
        pasta_dos_videos = base_dir / entity.title

    except Exception as e:
        print(f"Erro ao obter entidade: {e}")
        return

    pasta_dos_videos.mkdir(parents=True, exist_ok=True)

    result = await client.get_messages(canal, filter=InputMessagesFilterVideo)  # pyright: ignore[reportUnknownMemberType]
    total_videos = result.total
    nome_curso = entity.title

    if historico_completo(nome_curso):
        resposta = typer.confirm(
            f'"{nome_curso}" já foi baixado por completo. Deseja baixar novamente?',
            default=False,
        )
        if not resposta:
            print("Download pulado.")
            await client.disconnect()
            return
        resetar_historico(nome_curso, target, total_videos)
    else:
        registrar_historico(nome_curso, target, total_videos)

    if isinstance(numeros, (list, range)):
        pendentes = set(numeros)
        limite = total_videos
    elif isinstance(numeros, int):
        pendentes = None
        limite = numeros
    else:
        pendentes = None
        limite = total_videos

    print(
        f"Total de vídeos no canal: {total_videos}. Baixando: {len(pendentes) if pendentes is not None else limite}."
    )

    messages = client.iter_messages(
        entity, filter=InputMessagesFilterVideo, limit=limite
    )
    semaphore = asyncio.Semaphore(config["concurrent_downloads"])
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
            tasks.append(
                asyncio.create_task(
                    baixar_video(
                        message,
                        contador,
                        client,
                        progress,
                        semaphore,
                        nome_curso,
                        pasta_dos_videos,
                        pendentes,
                    )
                )
            )
            contador -= 1

        await asyncio.gather(*tasks)

    await client.disconnect()
    print("Downloads concluídos.")


async def baixar_paralelo(target: str | list[str]):
    client = TelegramClient(
        config["session_name"], config["api_id"], config["api_hash"]
    )
    await client.connect()
    await autenticar(client)

    fila = deque([target] if isinstance(target, str) else target)

    while fila:
        link = fila.popleft()
        restantes = len(fila)
        print(
            f"\nProcessando: {link}"
            + (f" ({restantes} restante(s) na fila)" if restantes else "")
        )

        try:
            canal_id = int(link.split("/c/")[1].split("/")[0])
            canal = int(f"-100{canal_id}")  # pyright: ignore[reportAssignmentType]
            await client.get_dialogs()
            try:
                entity = await client.get_entity(canal)
            except ValueError:
                entity = await client.get_entity(canal)

            base_dir = Path(config["download_dir"])
            pasta_dos_videos = base_dir / entity.title

        except Exception as e:
            print(f"Erro ao obter entidade: {e}")
            continue

        pasta_dos_videos.mkdir(parents=True, exist_ok=True)

        result = await client.get_messages(
            canal, filter=InputMessagesFilterVideo, reverse=True
        )  # pyright: ignore[reportUnknownMemberType]
        total_videos = result.total
        nome_curso = entity.title

        if historico_completo(nome_curso):
            resposta = typer.confirm(
                f'"{nome_curso}" já foi baixado por completo. Deseja baixar novamente?',
                default=False,
            )
            if not resposta:
                print("Download pulado.")
                continue
            resetar_historico(nome_curso, link, total_videos)
        else:
            registrar_historico(nome_curso, link, total_videos)
            typer.echo(f'Iniciando download de "{nome_curso}"...\n')

        messages = client.iter_messages(
            entity, filter=InputMessagesFilterVideo, reverse=True
        )  # pyright: ignore[reportUnknownMemberType]
        semaphore = asyncio.Semaphore(config["concurrent_downloads"])
        contador = 1
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
                tasks.append(
                    asyncio.create_task(
                        baixar_video(
                            message,
                            contador,
                            client,
                            progress,
                            semaphore,
                            nome_curso,
                            pasta_dos_videos,
                        )
                    )
                )
                contador += 1

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
