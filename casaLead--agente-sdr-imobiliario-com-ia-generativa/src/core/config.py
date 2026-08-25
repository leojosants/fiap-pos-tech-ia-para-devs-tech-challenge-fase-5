"""Configuração central do CasaLead.

Resolve as variáveis de ambiente a partir de três fontes, nesta ordem
de precedência:

    1. Variáveis de ambiente do processo (usado em testes e CI)
    2. st.secrets           (Streamlit Cloud)
    3. arquivo .env         (desenvolvimento local)

A ordem existe para que um teste possa sobrescrever a configuração sem
depender de arquivos, e para que o deploy funcione sem .env — que não
é versionado.
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Identificadores confirmados via GET /v1/models da Groq
DEFAULT_MODEL_FAST = "openai/gpt-oss-20b"
DEFAULT_MODEL_SMART = "openai/gpt-oss-120b"

# Ancorado na localização deste arquivo, não no diretório de trabalho
# do processo — mesma razão documentada em src/persistence/database.py:
# o Streamlit Community Cloud roda o app a partir da raiz do
# repositório Git, não desta subpasta.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = str(_PROJECT_ROOT / "data" / "runtime" / "casalead.db")


def _from_streamlit_secrets(chave: str) -> str | None:
    """Lê uma chave de st.secrets, se a aplicação estiver sob Streamlit.

    O import é local e protegido porque o Streamlit pode não estar em
    execução (scripts de linha de comando, pytest), caso em que o acesso
    a st.secrets levanta exceção.
    """
    try:
        import streamlit as st

        return st.secrets.get(chave)
    except Exception:
        return None


def _get(chave: str, padrao: str = "") -> str:
    """Resolve uma variável seguindo a ordem de precedência definida."""
    valor = os.getenv(chave)
    if valor:
        return valor

    valor = _from_streamlit_secrets(chave)
    if valor:
        return str(valor)

    return padrao


def _get_bool(chave: str, padrao: bool = False) -> bool:
    """Interpreta uma variável textual como booleano."""
    valor = _get(chave, str(padrao)).strip().lower()
    return valor in ("true", "1", "yes", "sim", "on")


@dataclass(frozen=True)
class Settings:
    """Configuração imutável da aplicação."""

    groq_api_key: str
    model_fast: str
    model_smart: str
    demo_mode_forcado: bool
    database_path: Path
    log_level: str

    # Parâmetros de inferência
    temperatura_conversa: float = 0.7
    temperatura_extracao: float = 0.1
    max_tokens_resposta: int = 500
    timeout_segundos: int = 30
    max_tentativas: int = 2

    @property
    def tem_api_key(self) -> bool:
        """Indica se há chave de API configurada."""
        return bool(self.groq_api_key.strip())

    @property
    def modo_demo(self) -> bool:
        """Decide se o sistema opera sem LLM.

        Ativo quando forçado explicitamente por DEMO_MODE=true ou quando
        não há chave de API disponível. Essa é a decisão única que todo
        o sistema consulta — nenhum módulo reimplementa esse critério.
        """
        return self.demo_mode_forcado or not self.tem_api_key

    @property
    def motivo_modo_demo(self) -> str:
        """Explica ao usuário por que o modo demonstrativo está ativo."""
        if self.demo_mode_forcado:
            return "Modo demonstrativo ativado por configuração (DEMO_MODE=true)."
        if not self.tem_api_key:
            return (
                "Nenhuma chave da Groq API configurada. "
                "O agente opera com o motor determinístico."
            )
        return ""

    def resumo_publico(self) -> dict:
        """Configuração sem segredos, exibível na interface e nos logs.

        A chave de API nunca é exposta — apenas a informação de que
        existe ou não.
        """
        return {
            "modo": "demonstrativo" if self.modo_demo else "llm",
            "api_key_configurada": self.tem_api_key,
            "modelo_conversa": self.model_fast if not self.modo_demo else "—",
            "modelo_raciocinio": self.model_smart if not self.modo_demo else "—",
            "banco_de_dados": str(self.database_path),
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna a configuração da aplicação (instância única em cache)."""
    return Settings(
        groq_api_key=_get("GROQ_API_KEY"),
        model_fast=_get("GROQ_MODEL_FAST", DEFAULT_MODEL_FAST),
        model_smart=_get("GROQ_MODEL_SMART", DEFAULT_MODEL_SMART),
        demo_mode_forcado=_get_bool("DEMO_MODE", False),
        database_path=Path(_get("DATABASE_PATH", DEFAULT_DB_PATH)),
        log_level=_get("LOG_LEVEL", "INFO").upper(),
    )


def reset_settings_cache() -> None:
    """Limpa o cache de configuração. Necessário em testes que alteram
    variáveis de ambiente entre casos."""
    get_settings.cache_clear()