import typer
import download

app = typer.Typer(help="Download de vídeos do Telegram")

app.add_typer(
    download.app, name="baixar", help="Baixar todos os vídeos de um canal ou grupo"
)

if __name__ == "__main__":
    app()
