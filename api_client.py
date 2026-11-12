"""Cliente HTTP do Portal do Aluno; não armazena nem inclui tokens padrão."""
from __future__ import annotations

from urllib.parse import urljoin, urlparse

import requests

API_BASE = "https://smartv5.escolarmanageronline.com.br"
API_HOST = urlparse(API_BASE).hostname
DOMINIO = "grupofractal"

DEFAULT_CATEGORIES = [
    {"id": "conteudos", "label": "Conteúdos e tarefas", "code": "111", "description": "Avisos, atividades e materiais"},
    {"id": "faltas", "label": "Faltas", "code": "22", "description": "Registros e comunicados"},
    {"id": "saida", "label": "Saída antecipada", "code": "108", "description": "Autorizações e avisos"},
    {"id": "listas", "label": "Listas obrigatórias", "code": "124", "description": "Listas e documentos da turma"},
]


class PortalApiError(Exception):
    """Erro seguro para apresentar ao usuário sem expor dados internos da API."""


class AuthenticationError(PortalApiError):
    """Matrícula/token ausente, inválido ou expirado."""


def _items_from_payload(payload):
    if payload is None:
        return []

    if isinstance(payload, list):
        result = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            if str(row.get("des", "")).strip().casefold() == "financeiro":
                continue
            if isinstance(row.get("pub"), list):
                result.extend(item for item in row["pub"] if isinstance(item, dict))
            elif "tit" in row or "url" in row:
                result.append(row)
        return result

    if isinstance(payload, dict):
        if str(payload.get("des", "")).strip().casefold() == "financeiro":
            return []
        for key in ("pub", "items", "data", "publicacoes", "publicações", "result", "resultado"):
            if key in payload:
                value = payload[key]
                if isinstance(value, list):
                    return _items_from_payload(value)
                if isinstance(value, dict):
                    return _items_from_payload(value)
                if value is None:
                    return []
        if "tit" in payload or "url" in payload:
            return [payload]
        if not payload:
            return []

    raise PortalApiError("A API respondeu em um formato inesperado. Tente atualizar; se persistir, contate a escola.")


class PortalApi:
    def __init__(self, session=None):
        self.session = session or requests

    @staticmethod
    def _headers(token: str) -> dict:
        return {
            "dominio": DOMINIO,
            "user-agent": "Versao/2026.01.02",
            "accept-encoding": "gzip",
            "authorization": "Bearer " + token.strip(),
            "content-type": "application/json",
            "accept": "application/json",
        }

    def fetch_folder_items(self, matricula: str, token: str, folder_code: str) -> list[dict]:
        matricula = str(matricula or "").strip()
        folder_code = str(folder_code or "").strip()
        token = str(token or "").strip()

        if not matricula.isdigit():
            raise PortalApiError("A matrícula deve conter apenas números.")
        if not folder_code.isdigit():
            raise PortalApiError("O código desta categoria é inválido. Confira as configurações.")
        if not token:
            raise AuthenticationError("Informe o token de acesso nas configurações do app.")

        try:
            response = self.session.post(
                f"{API_BASE}/publicacoes/ConsultePublicacaoAlunoPasta",
                json={"Matricula": int(matricula), "PastaCodigo": int(folder_code)},
                headers=self._headers(token),
                timeout=(10, 30),
            )
        except requests.Timeout:
            raise PortalApiError("A conexão com a escola demorou demais. Verifique a internet e tente novamente.") from None
        except requests.RequestException:
            raise PortalApiError("Não foi possível conectar à API da escola. Verifique a internet e tente novamente.") from None

        status = getattr(response, "status_code", 0)
        if status in (401, 419):
            raise AuthenticationError("A API recusou o acesso. Confira a matrícula e atualize o token nas configurações.")
        if status == 403:
            raise PortalApiError("A API negou o acesso a esta categoria. Confira as permissões ou fale com a escola.")
        if status == 404:
            raise PortalApiError("A rota da API não foi encontrada. A escola pode ter atualizado o serviço.")
        if status == 429:
            raise PortalApiError("Muitas tentativas em pouco tempo. Aguarde um minuto e tente novamente.")
        if status >= 500:
            raise PortalApiError("A API da escola está indisponível agora. Tente novamente mais tarde.")
        if not 200 <= status < 300:
            raise PortalApiError(f"A API respondeu com erro HTTP {status}. Confira os dados e tente novamente.")

        try:
            payload = response.json()
        except (ValueError, AttributeError):
            raise PortalApiError("A API respondeu sem JSON válido. Tente novamente mais tarde.") from None

        return _items_from_payload(payload)

    def download_item_bytes(self, url: str, token: str) -> tuple[bytes, str]:
        raw_url = str(url or "").strip()
        if not raw_url:
            raise PortalApiError("Este documento não possui um endereço de download.")
        resolved = urljoin(API_BASE.rstrip("/") + "/", raw_url)
        parsed = urlparse(resolved)
        if parsed.scheme != "https" or not parsed.hostname:
            raise PortalApiError("O endereço deste documento não é seguro.")

        headers = {"accept": "*/*", "user-agent": "Versao/2026.01.02"}
        # Nunca encaminha a credencial escolar a um host diferente do servidor da API.
        if parsed.hostname.casefold() == (API_HOST or "").casefold():
            headers.update({"dominio": DOMINIO, "authorization": "Bearer " + str(token or "").strip()})

        try:
            response = self.session.get(resolved, headers=headers, timeout=(10, 45), allow_redirects=True)
        except requests.Timeout:
            raise PortalApiError("O download demorou demais. Verifique a internet e tente novamente.") from None
        except requests.RequestException:
            raise PortalApiError("Não foi possível baixar o documento. Tente novamente.") from None

        if response.status_code in (401, 403):
            raise AuthenticationError("A API recusou o download. Confira se o token ainda está válido.")
        if not 200 <= response.status_code < 300:
            raise PortalApiError(f"Não foi possível baixar o documento (HTTP {response.status_code}).")
        return response.content, response.headers.get("content-type", "")
