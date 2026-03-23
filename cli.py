import asyncio
import typer
import download
import questionary
from questionary import Style

estilo = Style(
    [
        ("selected", "fg:cyan bold"),  # opção destacada no menu
        ("pointer", "fg:cyan bold"),  # seta ❯
        ("highlighted", "fg:cyan bold"),  # texto da opção em foco
    ]
)


app = typer.Typer(help="Download de vídeos do Telegram")

app.add_typer(
    download.app, name="baixar", help="Baixar todos os vídeos de um canal ou grupo"
)

_OPCOES = {
    " • Baixar tudo  —  um ou mais canais, todos os vídeos": "tudo",
    " •  Baixar apenas  —  quantidade ou intervalo específico de um canal": "apenas",
    " •  Continuar  —  retomar downloads pendentes no histórico": "continuar",
    " •  Sair": "sair",
}


async def _menu():
    escolha = await questionary.select(
        "O que deseja fazer?",
        choices=list(_OPCOES.keys()),
        instruction="(use as setas para navegar)",
        style=estilo,
    ).ask_async()

    if escolha is None or _OPCOES[escolha] == "sair":
        raise typer.Exit()

    acao = _OPCOES[escolha]

    if acao == "tudo":
        links = await questionary.text(
            "Informe o(s) link(s) do canal ou grupo (separe por vírgula para múltiplos):"
        ).ask_async()
        if not links:
            raise typer.Exit()
        await download.baixar_paralelo(download.parse_links(links))

    elif acao == "apenas":
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
        await download.baixar_limitado(link, numeros=download.parse_numeros(quantidade))

    elif acao == "continuar":
        await download.continuar_download()


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """Download de vídeos do Telegram."""
    if ctx.invoked_subcommand is None:
        asyncio.run(_menu())


if __name__ == "__main__":
    app()
