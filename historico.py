import json
from pathlib import Path
from constants import HISTORICO_FILE


class HistoricoManager:
    """Responsável por ler, persistir e consultar o histórico de downloads."""

    # Estrutura do JSON:
    # {
    #   "<coleção>": {
    #     "<nome_arquivo>": {
    #       "status": "incompleto",
    #       "canal": "<link>",
    #       "total_videos": N,
    #       "total_anexos": N,
    #       "videos": {
    #         "<message_id>": { "status": bool, "arquivo": "<filename>" }
    #       },
    #       "anexos": {
    #         "<message_id>": { "status": bool, "arquivo": "<filename>" }
    #       }
    #     }
    #   }
    # }

    def __init__(self, caminho: Path = HISTORICO_FILE):
        self._caminho = caminho

    def carregar(self) -> dict:
        if not self._caminho.exists():
            return {}
        with open(self._caminho, "r", encoding="utf-8") as f:
            return json.load(f)

    def salvar(self, historico: dict) -> None:
        with open(self._caminho, "w", encoding="utf-8") as f:
            json.dump(historico, f, ensure_ascii=False, indent=2)

    def listar_colecoes(self) -> list[str]:
        """Retorna os nomes de todas as coleções já existentes no histórico."""
        return list(self.carregar().keys())

    def pendentes(self) -> list[tuple[str, str, dict]]:
        """Retorna lista de (colecao, nome, info) para downloads incompletos."""
        historico = self.carregar()
        return [
            (colecao, nome, info)
            for colecao, arquivos in historico.items()
            for nome, info in arquivos.items()
            if info["status"] == "incompleto"
        ]

    def registrar(
        self,
        colecao: str,
        nome: str,
        canal: str,
        total_videos: int,
        total_anexos: int,
    ) -> dict:
        historico = self.carregar()
        historico.setdefault(colecao, {})
        if nome not in historico[colecao]:
            historico[colecao][nome] = {
                "status": "incompleto",
                "canal": canal,
                "total_videos": total_videos,
                "total_anexos": total_anexos,
                "videos": {},
                "anexos": {},
            }
            self.salvar(historico)
        return historico

    def registrar_arquivo(
        self,
        colecao: str,
        nome: str,
        file_id: int,
        filename: str,
        eh_anexo: bool,
    ) -> None:
        """Registra um arquivo (vídeo ou anexo) no histórico com status False."""
        historico = self.carregar()
        chave = "anexos" if eh_anexo else "videos"
        if str(file_id) not in historico[colecao][nome][chave]:
            historico[colecao][nome][chave][str(file_id)] = {
                "status": False,
                "arquivo": filename,
            }
            self.salvar(historico)

    def marcar_baixado(
        self,
        colecao: str,
        nome: str,
        file_id: int,
        filename: str,
        eh_anexo: bool,
    ) -> None:
        """Marca um arquivo como baixado. Remove a entrada do curso ao concluir tudo."""
        historico = self.carregar()
        chave = "anexos" if eh_anexo else "videos"
        historico[colecao][nome][chave][str(file_id)] = {
            "status": True,
            "arquivo": filename,
        }

        total_videos = historico[colecao][nome]["total_videos"]
        total_anexos = historico[colecao][nome]["total_anexos"]
        baixados_videos = sum(
            1 for v in historico[colecao][nome]["videos"].values() if v["status"]
        )
        baixados_anexos = sum(
            1 for a in historico[colecao][nome]["anexos"].values() if a["status"]
        )

        if (
            len(historico[colecao][nome]["videos"]) == total_videos
            and len(historico[colecao][nome]["anexos"]) == total_anexos
            and baixados_videos == total_videos
            and baixados_anexos == total_anexos
        ):
            del historico[colecao][nome]
            if not historico[colecao]:
                del historico[colecao]

        self.salvar(historico)

    def obter_entrada_arquivo(
        self,
        colecao: str,
        nome: str,
        file_id: int,
        eh_anexo: bool,
    ) -> dict | None:
        """Retorna a entrada do arquivo no histórico, ou None se não existir."""
        chave = "anexos" if eh_anexo else "videos"
        historico = self.carregar()
        return historico.get(colecao, {}).get(nome, {}).get(chave, {}).get(str(file_id))
