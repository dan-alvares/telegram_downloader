from pathlib import Path
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
    selecionar_ou_criar_colecao,
    carregar,
)

config = load_config()


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
        print(f'Continuando download de "{nome}" (coleção: "{colecao}")...')
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

    result = await client.get_messages(canal, filter=InputMessagesFilterVideo)  # pyright: ignore[reportUnknownMemberType]
    total_videos = result.total

    if historico_completo(colecao, nome_curso):
        resposta = typer.confirm(
            f'"{nome_curso}" já foi baixado por completo. Deseja baixar novamente?',
            default=False,
        )
        if not resposta:
            print("Download pulado.")
            await client.disconnect()
            return
        resetar_historico(colecao, nome_curso, target, total_videos)
    else:
        registrar_historico(colecao, nome_curso, target, total_videos)

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
                        colecao,
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


async def baixar_paralelo(
    target: str | list[str],
    colecao_forcada: str | None = None,
):
    client = TelegramClient(
        config["session_name"], config["api_id"], config["api_hash"]
    )
    await client.connect()
    await autenticar(client)

    fila = deque([target] if isinstance(target, str) else target)

    # Quando há múltiplos links, pergunta a coleção uma única vez antes de iniciar
    colecao: str | None = colecao_forcada
    if colecao is None and len(fila) > 1:
        typer.echo(f"\n{len(fila)} links na fila. Escolha a coleção para este lote:")
        colecao = await selecionar_ou_criar_colecao()

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

            nome_curso = entity.title

            # Link único: pergunta a coleção individualmente
            colecao_atual = colecao
            if colecao_atual is None:
                typer.echo(f'\nEscolha a coleção para "{nome_curso}":')
                colecao_atual = await selecionar_ou_criar_colecao()

            base_dir = Path(config["download_dir"])
            pasta_dos_videos = base_dir / colecao_atual / nome_curso

        except Exception as e:
            print(f"Erro ao obter entidade: {e}")
            continue

        pasta_dos_videos.mkdir(parents=True, exist_ok=True)

        result = await client.get_messages(
            canal, filter=InputMessagesFilterVideo, reverse=True
        )  # pyright: ignore[reportUnknownMemberType]
        total_videos = result.total

        if historico_completo(colecao_atual, nome_curso):
            resposta = typer.confirm(
                f'"{nome_curso}" já foi baixado por completo. Deseja baixar novamente?',
                default=False,
            )
            if not resposta:
                print("Download pulado.")
                continue
            resetar_historico(colecao_atual, nome_curso, link, total_videos)
        else:
            registrar_historico(colecao_atual, nome_curso, link, total_videos)
            typer.echo(
                f'Iniciando download de "{nome_curso}" em "{colecao_atual}"...\n'
            )

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
                            colecao_atual,
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
