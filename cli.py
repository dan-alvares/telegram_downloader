import asyncio

import typer
import questionary
from questionary import Style

from config import load_config
from download import TelegramDownloader


def _parse_numeros(valor: str) -> int | list[int] | range | None:
    if not valor:
        return None
    if "-" in valor and valor.count("-") == 1:
        inicio, fim = valor.split("-")
        return range(int(inicio), int(fim) + 1)
    if "," in valor:
        return [int(n) for n in valor.split(",")]
    return int(valor)


def _parse_links(valor: str) -> str | list[str]:
    if not valor:
        return None
    if "," in valor:
        return [link.strip() for link in valor.split(",")]
    return valor.strip()


_ESTILO = Style(
    [
        ("selected", "fg:cyan bold"),
        ("pointer", "fg:cyan bold"),
        ("highlighted", "fg:cyan bold"),
    ]
)

_OPCOES = {
    " • Baixar tudo  —  um ou mais canais, todos os vídeos": "tudo",
    " •  Baixar apenas  —  quantidade ou intervalo específico de um canal": "apenas",
    " •  Continuar  —  retomar downloads pendentes no histórico": "continuar",
    " •  Sair": "sair",
}


class Menu:
    """Menu interativo TUI que despacha para o TelegramDownloader."""

    def __init__(self, downloader: TelegramDownloader):
        self._dl = downloader

    async def executar(self) -> None:
        escolha = await questionary.select(
            "O que deseja fazer?",
            choices=list(_OPCOES.keys()),
            instruction="(use as setas para navegar)",
            style=_ESTILO,
        ).ask_async()

        if escolha is None or _OPCOES[escolha] == "sair":
            raise typer.Exit()

        acao = _OPCOES[escolha]

        if acao == "tudo":
            await self._cmd_tudo()
        elif acao == "apenas":
            await self._cmd_apenas()
        elif acao == "continuar":
            await self._dl.continuar_downloads()

    async def _cmd_tudo(self) -> None:
        links = await questionary.text(
            "Informe o(s) link(s) do canal ou grupo (separe por vírgula para múltiplos):"
        ).ask_async()
        if not links:
            raise typer.Exit()
        await self._dl.baixar_paralelo(_parse_links(links))

    async def _cmd_apenas(self) -> None:
        link = await questionary.text("Informe o link do canal ou grupo:").ask_async()
        if not link:
            raise typer.Exit()

        quantidade = await questionary.text(
            "Quantos vídeos deseja baixar?\n"
            "  • Últimos X vídeos          →  ex: 10\n"
            "  • Intervalo                 →  ex: 1-44\n"
            "  • Vídeos específicos        →  ex: 10,7,4,1\n"
            "Resposta"
        ).ask_async()
        if not quantidade:
            raise typer.Exit()

        await self._dl.baixar_limitado(link, numeros=_parse_numeros(quantidade))


config = load_config()
_downloader = TelegramDownloader(config)

app = typer.Typer(help="Download de vídeos do Telegram")


@app.command("tudo")
def cmd_tudo():
    """Baixa todos os vídeos de um ou mais canais."""
    links = typer.prompt(
        "Informe o(s) link(s) do canal ou grupo (separe por vírgula para múltiplos)"
    )
    asyncio.run(_downloader.baixar_paralelo(_parse_links(links)))


@app.command("apenas")
def cmd_apenas():
    """Baixa uma quantidade ou intervalo específico de vídeos de um canal."""
    link = typer.prompt("Informe o link do canal ou grupo para baixar os vídeos")
    quantidade = typer.prompt(
        "Quantos vídeos deseja baixar?\n"
        "  • Últimos X           →  ex: 10\n"
        "  • Intervalo           →  ex: 1-44\n"
        "  • Específicos         →  ex: 10,7,4,1"
    )
    asyncio.run(_downloader.baixar_limitado(link, numeros=_parse_numeros(quantidade)))


@app.command("continuar")
def cmd_continuar():
    """Retoma downloads pendentes no histórico."""
    typer.echo("Continuando downloads pendentes...")
    asyncio.run(_downloader.continuar_downloads())


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """Download de vídeos do Telegram."""
    if ctx.invoked_subcommand is None:
        asyncio.run(Menu(_downloader).executar())


if __name__ == "__main__":
    app()
