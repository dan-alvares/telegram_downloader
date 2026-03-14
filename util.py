import asyncio
from pathlib import Path
from config import load_config
import typer

config = load_config()

FFMPEG = Path(__file__).resolve().parent / "ffmpeg" / "ffmpeg"

base_dir = Path(config['download_dir'])
pasta_dos_videos = base_dir

async def converter_videos(pasta: Path | str):
    if isinstance(pasta, str):
        pasta = Path(pasta_dos_videos) / pasta

    cq: str = "28"
    maxrate: str = "1M"
    bufsize: str = "2M"
    fps: str = "24"

    arquivos_mp4 = sorted(pasta.glob("*.mp4"))

    for arquivo_original in arquivos_mp4:

        arquivo_convertido = arquivo_original.with_stem(
            f"{arquivo_original.stem}_encoded"
        )

        if arquivo_convertido.exists():
            continue

        comando = [
            str(FFMPEG),
            "-i", str(arquivo_original),
            "-c:v", "hevc_nvenc",
            "-preset", "p5",
            "-rc", "vbr_hq",
            "-cq", cq,
            "-b:v", "0",
            "-maxrate", maxrate,
            "-bufsize", bufsize,
            "-profile:v", "main",
            "-pix_fmt", "yuv420p",
            "-r", fps,
            "-movflags", "+faststart",
            "-c:a", "aac",
            "-b:a", "92k",
            str(arquivo_convertido),
        ]

        proc = await asyncio.create_subprocess_exec(
            *comando,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        await proc.wait()

app = typer.Typer(help="Download de vídeos do Telegram")

@app.command()
def converter():
    pasta = typer.prompt('Digite o nome da pasta dos vídeos.')
    asyncio.run(converter_videos(pasta))

if __name__ == "__main__":
    app()