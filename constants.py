from pathlib import Path
import sys


def get_base_dir() -> Path:
    if "__compiled__" in dir():
        return Path(sys.executable).parent
    return Path(__file__).parent


HISTORICO_FILE = get_base_dir() / "historico_downloads.json"

COLECAO_GENERICA = "Sem Coleção"

OPCAO_NOVA = "•  Criar nova coleção"
OPCAO_NENHUMA = "•  Sem coleção"

COMPRESSED_EXTENSIONS = (".rar", ".zip", ".7z", ".tar", ".gz")
DOCUMENT_EXTENSIONS = (".pdf", ".txt", ".docx", ".doc", ".html", ".htm")
IMAGE_EXTENSIONS = (".jpg", ".jpeg")
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".m4v")

ANEXO_EXTENSIONS = COMPRESSED_EXTENSIONS + DOCUMENT_EXTENSIONS + IMAGE_EXTENSIONS

COMPRESSED_MIMETYPES = (
    "application/zip",
    "application/x-rar-compressed",
    "application/x-rar",
    "application/x-7z-compressed",
    "application/gzip",
    "application/x-tar",
)

DOCUMENT_MIMETYPES = (
    "application/pdf",
    "text/plain",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/html",
)

IMAGE_MIMETYPES = ("image/jpeg",)

TARGET_MIMETYPES = COMPRESSED_MIMETYPES + DOCUMENT_MIMETYPES + IMAGE_MIMETYPES
