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
from loguru import logger
import qrcode

config = load_config()


def get_base_dir() -> Path:
    if "__compiled__" in dir():
        return Path(sys.executable).parent
    return Path(__file__).parent


HISTORICO_FILE = get_base_dir() / "historico_downloads.json"

COLECAO_GENERICA = "Sem Coleção"

_OPCAO_NOVA = "•  Criar nova coleção"
_OPCAO_NENHUMA = "•  Sem coleção"

logger.configure(
    handlers=[
        {
            "sink": get_base_dir() / "logs" / "app.log",
            "rotation": "10 MB",
            "retention": "7 days",
            "format": "[{time:DD-MM-YYYY HH:mm:ss}] [{level}] {message}",
        },
    ]
)


def parse_numeros(valor: str) -> int | list[int] | range | None:
    if not valor:
        return None
    if "-" in valor and valor.count("-") == 1:
        inicio, fim = valor.split("-")
        return range(int(inicio), int(fim) + 1)
    if "," in valor:
        return [int(n) for n in valor.split(",")]
    return int(valor)


def parse_links(valor: str) -> str | list[str]:
    if not valor:
        return None
    if "," in valor:
        return [link.strip() for link in valor.split(",")]
    return valor.strip()


async def verificar_link(client: TelegramClient, link: str) -> str:
    """Verifica o link e retorna o título do canal/grupo, ou string vazia em caso de erro."""
    try:
        canal_id = int(link.split("/c/")[1].split("/")[0])
        canal = int(f"-100{canal_id}")
        entidade = await client.get_entity(canal)
        print(f"Canal encontrado: {entidade.title}")  # type: ignore
        return entidade.title  # type: ignore
    except ValueError as e:
        print("Link inválido ou canal privado.\nErro:", e)
        return ""


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


def carregar() -> dict:
    if not HISTORICO_FILE.exists():
        return {}
    with open(HISTORICO_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def salvar(historico: dict):
    with open(HISTORICO_FILE, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)


def listar_colecoes() -> list[str]:
    """Retorna os nomes de todas as coleções já existentes no histórico."""
    historico = carregar()
    return list(historico.keys())


async def selecionar_ou_criar_colecao() -> str:
    """
    Interativamente pergunta ao usuário a qual coleção o download pertence.
    Permite escolher uma existente com setas direcionais, criar uma nova, ou
    não vincular a nenhuma (agrupa em COLECAO_GENERICA).
    Retorna o nome da coleção escolhida/criada.
    """
    import questionary

    colecoes = listar_colecoes()
    opcoes = colecoes + [_OPCAO_NOVA, _OPCAO_NENHUMA]

    escolha = await questionary.select(
        "A qual coleção este download pertence?",
        choices=opcoes,
        default=_OPCAO_NENHUMA,
        instruction="(use as setas para navegar)",
    ).ask_async()

    if escolha is None:
        raise typer.Abort()

    if escolha == _OPCAO_NENHUMA:
        typer.echo(f'Agrupando em "{COLECAO_GENERICA}".')
        return COLECAO_GENERICA

    if escolha == _OPCAO_NOVA:
        colecao = await questionary.text(
            "Nome da nova coleção:",
            validate=lambda v: "Informe um nome." if not v.strip() else True,
        ).ask_async()
        if colecao is None:
            raise typer.Abort()
        colecao = colecao.strip()
        typer.echo(f'Nova coleção criada: "{colecao}".')
        return colecao

    typer.echo(f'Adicionando à coleção "{escolha}".')
    return escolha


# Estrutura do JSON:
# {
#   "<coleção>": {
#     "<nome_curso>": {
#       "status": "incompleto" | "completo",
#       "canal": "<link>",
#       "total_videos": N,
#       "videos": {
#         "<message_id>": { "status": bool, "arquivo": "<filename>" }
#       }
#     }
#   }
# }


def registrar_historico(colecao: str, nome: str, canal: str, total_videos: int) -> dict:
    historico = carregar()
    historico.setdefault(colecao, {})
    if nome not in historico[colecao]:
        historico[colecao][nome] = {
            "status": "incompleto",
            "canal": canal,
            "total_videos": total_videos,
            "videos": {},
        }
        salvar(historico)
    return historico


def registrar_video(colecao: str, nome: str, video_id: int, filename: str):
    historico = carregar()
    if str(video_id) not in historico[colecao][nome]["videos"]:
        historico[colecao][nome]["videos"][str(video_id)] = {
            "status": False,
            "arquivo": filename,
        }
        salvar(historico)


def marcar_baixado(colecao: str, nome: str, video_id: int, filename: str):
    historico = carregar()
    historico[colecao][nome]["videos"][str(video_id)] = {
        "status": True,
        "arquivo": filename,
    }
    total = historico[colecao][nome]["total_videos"]
    baixados = sum(
        1 for v in historico[colecao][nome]["videos"].values() if v["status"]
    )
    if baixados >= total:
        historico[colecao][nome]["status"] = "completo"
    salvar(historico)


def videos_pendentes(colecao: str, nome: str) -> set[str]:
    historico = carregar()
    curso = historico.get(colecao, {}).get(nome)
    if not curso:
        return set()
    return {vid_id for vid_id, v in curso["videos"].items() if not v["status"]}


def historico_completo(colecao: str, nome: str) -> bool:
    historico = carregar()
    return historico.get(colecao, {}).get(nome, {}).get("status") == "completo"


def resetar_historico(colecao: str, nome: str, canal: str, total_videos: int):
    historico = carregar()
    historico.setdefault(colecao, {})
    historico[colecao][nome] = {
        "status": "incompleto",
        "canal": canal,
        "total_videos": total_videos,
        "videos": {},
    }
    salvar(historico)


def _log_ctx(colecao: str, canal: str, arquivo: str) -> str:
    """Monta o prefixo de contexto padrão para as entradas de log."""
    return f"[coleção: {colecao}] [canal: {canal}] [arquivo: {arquivo}]"


async def baixar_video(
    message,
    numero: int,
    client: TelegramClient,
    progress: Progress,
    semaphore: asyncio.Semaphore,
    colecao: str,
    nome_historico: str,
    pasta_dos_videos: Path,
    nome_canal: str = "",
    pendentes: set[int] | None = None,
):
    async with semaphore:
        if pendentes is not None and numero not in pendentes:
            return

        filename = pasta_dos_videos / f"{numero}.mp4"
        ctx = _log_ctx(colecao, nome_canal, filename.name)

        historico = carregar()
        video_entry = (
            historico.get(colecao, {})
            .get(nome_historico, {})
            .get("videos", {})
            .get(str(message.id))
        )

        if video_entry:
            arquivo_no_disco = pasta_dos_videos / video_entry["arquivo"]
            ctx_entry = _log_ctx(colecao, nome_canal, video_entry["arquivo"])

            if video_entry["status"] and arquivo_no_disco.exists():
                logger.info(f"{ctx_entry} | Já baixado (histórico), pulando.")
                return

            elif video_entry["status"] and not arquivo_no_disco.exists():
                logger.warning(
                    f"{ctx_entry} | Arquivo marcado como baixado, mas não encontrado no disco."
                )
                return

            if not video_entry["status"] and arquivo_no_disco.exists():
                logger.warning(
                    f"{ctx_entry} | Arquivo incompleto encontrado no disco, removendo para novo download."
                )
                arquivo_no_disco.unlink()
        else:
            registrar_video(colecao, nome_historico, message.id, filename.name)
            if filename.exists():
                logger.info(
                    f"{ctx} | Arquivo já existe no disco, marcando como baixado."
                )
                progress.console.log(f"Já existe no disco: {filename.name}")
                marcar_baixado(colecao, nome_historico, message.id, filename.name)
                return

        task_id = progress.add_task("download", filename=filename.name, total=None)

        def progresso(bytes_baixados, total_bytes):
            progress.update(task_id, completed=bytes_baixados, total=total_bytes)

        try:
            logger.info(f"{ctx} | Iniciando download.")
            await client.download_media(
                message.video, file=filename, progress_callback=progresso
            )
            marcar_baixado(colecao, nome_historico, message.id, filename.name)
            logger.success(f"{ctx} | Download concluído com sucesso.")
            await asyncio.sleep(0.5)

        except FloodWaitError as e:
            logger.warning(
                f"{ctx} | Flood wait detectado: aguardando {e.seconds}s antes de tentar novamente."
            )
            progress.console.log(f"[yellow]Flood wait: aguardando {e.seconds}s...[/]")
            if filename.exists():
                filename.unlink()
            await asyncio.sleep(e.seconds)
            await baixar_video(
                message,
                numero,
                client,
                progress,
                semaphore,
                colecao,
                nome_historico,
                pasta_dos_videos,
                nome_canal,
                pendentes,
            )
            return

        except Exception as e:
            logger.error(f"{ctx} | Erro ao baixar: {e}")
            progress.console.log(f"[red]Erro ao baixar {filename.name}: {e}[/]")
            if filename.exists():
                filename.unlink()
                logger.warning(f"{ctx} | Arquivo incompleto removido do disco.")
                progress.console.log(
                    f"[yellow]Arquivo incompleto removido: {filename.name}[/]"
                )

        finally:
            progress.remove_task(task_id)


if __name__ == "__main__":
    asyncio.run(main())
