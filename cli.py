import typer
import download
import util

app = typer.Typer(help="Download de vídeos do Telegram")

app.add_typer(download.app, name='download', help="Baixar todos os vídeos de um canal ou grupo")
# app.add_typer(util.app, name='util', help="Utilitários para processamento de vídeos")

if __name__ == "__main__":
    app()