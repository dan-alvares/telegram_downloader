import json
import sys
from pathlib import Path
import asyncio
from telethon import TelegramClient
from telethon.errors.rpcerrorlist import FloodWaitError
from telethon.errors import SessionPasswordNeededError
from rich.progress import Progress
from config import load_config
import typer
import qrcode

config = load_config()


def parse_numeros(valor: str) -> int | list[int] | range | None:
    if not valor:
        return None
    if "-" in valor and valor.count("-") == 1:
        inicio, fim = valor.split("-")
        return range(int(inicio), int(fim) + 1)
    if "," in valor:
        return [int(n) for n in valor.split(",")]
    return int(valor)


async def verificar_link(client: TelegramClient, link: str):
    try:
        canal_id = int(link.split("/c/")[1].split("/")[0])
        canal = int(f"-100{canal_id}")
        entidade = await client.get_entity(canal)
        print(f"Canal encontrado: {entidade.title}")  # type: ignore
    except ValueError as e:
        print("Link inválido ou canal privado.\nErro:", e)


async def autenticar(client: TelegramClient):
    if not await client.is_user_authorized():
        print("Autenticando via QR Code...")
        qr_login = await client.qr_login()
        qr = qrcode.QRCode()
        qr.add_data(qr_login.url)
        qr.make()
        qr.print_ascii()
        print(
            "Abra o Telegram no celular → Configurações → Dispositivos → Conectar dispositivo"
        )
        print("Escaneie o QR Code acima.")
        try:
            await qr_login.wait(timeout=120)
            print("Autenticado com sucesso!")
        except SessionPasswordNeededError:
            senha = typer.prompt("Digite sua senha de dois fatores", hide_input=True)
            await client.sign_in(password=senha)


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


# ── JSON / histórico ──────────────────────────────────────────────────────────


def get_base_dir() -> Path:
    if "__compiled__" in dir():
        return Path(sys.executable).parent
    return Path(__file__).parent


CURSOS_FILE = get_base_dir() / "cursos.json"


def carregar() -> dict:
    if not CURSOS_FILE.exists():
        return {}
    with open(CURSOS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def salvar(cursos: dict):
    with open(CURSOS_FILE, "w", encoding="utf-8") as f:
        json.dump(cursos, f, ensure_ascii=False, indent=2)


def registrar_curso(nome: str, canal: str, total_videos: int) -> dict:
    cursos = carregar()
    if nome not in cursos:
        cursos[nome] = {
            "status": "incompleto",
            "canal": canal,
            "total_videos": total_videos,
            "videos": {},
        }
        salvar(cursos)
    return cursos


def registrar_video(nome: str, video_id: int, filename: str):
    cursos = carregar()
    if str(video_id) not in cursos[nome]["videos"]:
        cursos[nome]["videos"][str(video_id)] = {"status": False, "arquivo": filename}
        salvar(cursos)


def marcar_baixado(nome: str, video_id: int, filename: str):
    cursos = carregar()
    cursos[nome]["videos"][str(video_id)] = {"status": True, "arquivo": filename}
    total = cursos[nome]["total_videos"]
    baixados = sum(1 for v in cursos[nome]["videos"].values() if v["status"])
    if baixados >= total:
        cursos[nome]["status"] = "completo"
    salvar(cursos)


def videos_pendentes(nome: str) -> set[str]:
    cursos = carregar()
    if nome not in cursos:
        return set()
    return {vid_id for vid_id, v in cursos[nome]["videos"].items() if not v["status"]}


def curso_completo(nome: str) -> bool:
    cursos = carregar()
    return cursos.get(nome, {}).get("status") == "completo"


def resetar_curso(nome: str, canal: str, total_videos: int):
    cursos = carregar()
    cursos[nome] = {
        "status": "incompleto",
        "canal": canal,
        "total_videos": total_videos,
        "videos": {},
    }
    salvar(cursos)


# ── Download ──────────────────────────────────────────────────────────────────


async def baixar_video(
    message,
    numero: int,
    client: TelegramClient,
    progress: Progress,
    semaphore: asyncio.Semaphore,
    nome_curso: str,
    pasta_dos_videos: Path,
    pendentes: set[int] | None = None,
):
    async with semaphore:
        if pendentes is not None and numero not in pendentes:
            return

        filename = pasta_dos_videos / f"{numero}.mp4"
        cursos = carregar()
        video_entry = cursos.get(nome_curso, {}).get("videos", {}).get(str(message.id))

        if video_entry:
            if video_entry["status"]:
                progress.console.print(
                    f"Já baixado (histórico): {video_entry['arquivo']}"
                )
                return
            arquivo_no_disco = pasta_dos_videos / video_entry["arquivo"]
            if arquivo_no_disco.exists():
                progress.console.print(
                    f"Arquivo encontrado no disco: {video_entry['arquivo']}"
                )
                marcar_baixado(nome_curso, message.id, video_entry["arquivo"])
                return
        else:
            registrar_video(nome_curso, message.id, filename.name)
            if filename.exists():
                progress.console.print(f"Já existe no disco: {filename.name}")
                marcar_baixado(nome_curso, message.id, filename.name)
                return

        task_id = progress.add_task("download", filename=filename.name, total=None)

        def progresso(bytes_baixados, total_bytes):
            progress.update(task_id, completed=bytes_baixados, total=total_bytes)

        try:
            await client.download_media(
                message.video, file=filename, progress_callback=progresso
            )
            marcar_baixado(nome_curso, message.id, filename.name)
        except FloodWaitError as e:
            progress.console.print(f"Flood wait: aguardando {e.seconds}s...")
            await asyncio.sleep(e.seconds)
            progress.remove_task(task_id)
            return

        progress.remove_task(task_id)
        progress.console.print(f"Concluído: {filename.name}")
        await asyncio.sleep(0.5)


if __name__ == "__main__":
    asyncio.run(main())
