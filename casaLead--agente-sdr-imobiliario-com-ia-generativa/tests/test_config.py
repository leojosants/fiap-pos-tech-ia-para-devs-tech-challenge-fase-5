"""Testes da configuração central (src/core/config.py).

Escopo: a ordem de precedência de três fontes de configuração —
variável de ambiente do processo → st.secrets (Streamlit Cloud) →
.env (desenvolvimento local) — documentada no próprio módulo como a
razão de existir do arquivo, e nunca testada isoladamente até agora.
Também cobre `_get_bool()` (parsing textual de booleano) e a decisão
`modo_demo` — usada pelo sistema inteiro para decidir entre LLM real e
motor determinístico.

Usa `monkeypatch` para variáveis de ambiente e `reset_settings_cache()`
(já existente em config.py, criada exatamente para isso) — nenhum
teste aqui toca rede nem exige chave de API real.
"""

from pathlib import Path
import streamlit as st

from src.core.config import (
    DEFAULT_DB_PATH,
    DEFAULT_MODEL_FAST,
    DEFAULT_MODEL_SMART,
    Settings,
    get_settings,
    reset_settings_cache,
)


def _limpar_env_relevante(monkeypatch):
    """Remove do processo as variáveis que Settings lê, e neutraliza
    st.secrets (voltando ao estado real de 'sem secrets.toml') — ponto
    de partida limpo para cada teste desta ordem de precedência."""
    for chave in (
        "GROQ_API_KEY",
        "GROQ_MODEL_FAST",
        "GROQ_MODEL_SMART",
        "DEMO_MODE",
        "DATABASE_PATH",
        "LOG_LEVEL",
    ):
        monkeypatch.delenv(chave, raising=False)
    monkeypatch.setattr(st, "secrets", {}, raising=False)
    reset_settings_cache()


class TestOrdemDePrecedencia:
    """Variável de ambiente > st.secrets > padrão embutido no código.

    O .env local não entra neste teste porque `load_dotenv()` roda uma
    única vez, na importação do módulo — não é possível simular sua
    ausência sem reimportar o módulo. A precedência entre ambiente do
    processo e st.secrets, que é a parte que muda entre ambiente local
    e Streamlit Cloud, é o que este teste garante.
    """

    def test_variavel_de_ambiente_vence_st_secrets(self, monkeypatch):
        _limpar_env_relevante(monkeypatch)
        monkeypatch.setenv("GROQ_API_KEY", "chave-do-ambiente")
        monkeypatch.setattr(
            st, "secrets", {"GROQ_API_KEY": "chave-do-secrets"}, raising=False
        )

        settings = get_settings()

        assert settings.groq_api_key == "chave-do-ambiente"
        reset_settings_cache()

    def test_st_secrets_usado_quando_ambiente_esta_ausente(self, monkeypatch):
        _limpar_env_relevante(monkeypatch)
        monkeypatch.setattr(
            st, "secrets", {"GROQ_API_KEY": "chave-do-secrets"}, raising=False
        )

        settings = get_settings()

        assert settings.groq_api_key == "chave-do-secrets"
        reset_settings_cache()

    def test_padrao_do_codigo_usado_quando_nada_esta_configurado(self, monkeypatch):
        _limpar_env_relevante(monkeypatch)

        settings = get_settings()

        assert settings.groq_api_key == ""
        assert settings.model_fast == DEFAULT_MODEL_FAST
        assert settings.model_smart == DEFAULT_MODEL_SMART
        # Path com Path, não str com barra fixa — str(Path(...)) usa
        # "\" no Windows e "/" no Linux/macOS (achado real na validação
        # manual desta etapa, ver docs/decisoes_tecnicas.md).
        assert settings.database_path == Path(DEFAULT_DB_PATH)
        reset_settings_cache()

    def test_secrets_sem_secrets_toml_nao_derruba_a_aplicacao(self, monkeypatch):
        # Reproduz o ambiente real de desenvolvimento local: nenhum
        # .streamlit/secrets.toml existe. _from_streamlit_secrets deve
        # engolir a exceção do Streamlit e devolver None, não propagar.
        _limpar_env_relevante(monkeypatch)
        monkeypatch.delattr(st, "secrets", raising=False)  # volta ao objeto real

        settings = get_settings()  # não deve levantar exceção

        assert settings.groq_api_key == ""
        reset_settings_cache()


class TestGetBool:
    """Parsing de DEMO_MODE (e qualquer outra flag textual futura)."""

    def _demo_mode_forcado(self, monkeypatch, valor_bruto: str | None) -> bool:
        _limpar_env_relevante(monkeypatch)
        if valor_bruto is not None:
            monkeypatch.setenv("DEMO_MODE", valor_bruto)
        settings = get_settings()
        resultado = settings.demo_mode_forcado
        reset_settings_cache()
        return resultado

    def test_valores_verdadeiros_reconhecidos(self, monkeypatch):
        for valor in ("true", "1", "yes", "sim", "on", "TRUE", "Sim"):
            assert self._demo_mode_forcado(monkeypatch, valor) is True, valor

    def test_valores_falsos_reconhecidos(self, monkeypatch):
        for valor in ("false", "0", "no", "nao", "off", ""):
            assert self._demo_mode_forcado(monkeypatch, valor) is False, valor

    def test_ausencia_da_variavel_usa_padrao_false(self, monkeypatch):
        assert self._demo_mode_forcado(monkeypatch, None) is False


class TestModoDemo:
    """A decisão única que todo o sistema consulta para saber se opera
    com LLM real ou com o motor determinístico."""

    def test_sem_chave_de_api_forca_modo_demo(self, monkeypatch):
        _limpar_env_relevante(monkeypatch)

        settings = get_settings()

        assert settings.tem_api_key is False
        assert settings.modo_demo is True
        reset_settings_cache()

    def test_com_chave_de_api_e_sem_forcar_opera_com_llm(self, monkeypatch):
        _limpar_env_relevante(monkeypatch)
        monkeypatch.setenv("GROQ_API_KEY", "chave-valida-fake")

        settings = get_settings()

        assert settings.tem_api_key is True
        assert settings.modo_demo is False
        reset_settings_cache()

    def test_demo_mode_true_forca_modo_demo_mesmo_com_chave_valida(self, monkeypatch):
        # DEMO_MODE=true precisa vencer mesmo com chave de API presente
        # — é o mecanismo que permite demonstrar o sistema sem gastar
        # quota mesmo tendo chave configurada.
        _limpar_env_relevante(monkeypatch)
        monkeypatch.setenv("GROQ_API_KEY", "chave-valida-fake")
        monkeypatch.setenv("DEMO_MODE", "true")

        settings = get_settings()

        assert settings.tem_api_key is True
        assert settings.modo_demo is True
        reset_settings_cache()

    def test_chave_so_com_espacos_conta_como_ausente(self, monkeypatch):
        _limpar_env_relevante(monkeypatch)
        monkeypatch.setenv("GROQ_API_KEY", "   ")

        settings = get_settings()

        assert settings.tem_api_key is False
        assert settings.modo_demo is True
        reset_settings_cache()


class TestMotivoModoDemo:

    def test_motivo_quando_forcado_por_configuracao(self, monkeypatch):
        _limpar_env_relevante(monkeypatch)
        monkeypatch.setenv("DEMO_MODE", "true")

        settings = get_settings()

        assert "DEMO_MODE=true" in settings.motivo_modo_demo
        reset_settings_cache()

    def test_motivo_quando_falta_chave_de_api(self, monkeypatch):
        _limpar_env_relevante(monkeypatch)

        settings = get_settings()

        assert "chave" in settings.motivo_modo_demo.lower()
        reset_settings_cache()

    def test_motivo_vazio_quando_nao_esta_em_modo_demo(self, monkeypatch):
        _limpar_env_relevante(monkeypatch)
        monkeypatch.setenv("GROQ_API_KEY", "chave-valida-fake")

        settings = get_settings()

        assert settings.motivo_modo_demo == ""
        reset_settings_cache()


class TestResumoPublico:
    """resumo_publico() alimenta o painel de diagnóstico da interface —
    nunca pode conter o valor bruto da chave de API."""

    def test_nunca_expoe_o_valor_da_chave_de_api(self, monkeypatch):
        _limpar_env_relevante(monkeypatch)
        monkeypatch.setenv("GROQ_API_KEY", "segredo-super-secreto-12345")

        settings = get_settings()
        resumo = settings.resumo_publico()

        assert "segredo-super-secreto-12345" not in str(resumo)
        assert resumo["api_key_configurada"] is True
        reset_settings_cache()

    def test_modo_demo_oculta_nomes_de_modelo(self, monkeypatch):
        _limpar_env_relevante(monkeypatch)  # sem chave → modo demo

        settings = get_settings()
        resumo = settings.resumo_publico()

        assert resumo["modo"] == "demonstrativo"
        assert resumo["modelo_conversa"] == "—"
        assert resumo["modelo_raciocinio"] == "—"
        reset_settings_cache()

    def test_modo_llm_exibe_nomes_de_modelo_configurados(self, monkeypatch):
        _limpar_env_relevante(monkeypatch)
        monkeypatch.setenv("GROQ_API_KEY", "chave-valida-fake")
        monkeypatch.setenv("GROQ_MODEL_FAST", "modelo-rapido-customizado")

        settings = get_settings()
        resumo = settings.resumo_publico()

        assert resumo["modo"] == "llm"
        assert resumo["modelo_conversa"] == "modelo-rapido-customizado"
        reset_settings_cache()


class TestGetSettingsCache:
    """get_settings() é cacheado (lru_cache) — reset_settings_cache()
    precisa de fato invalidar esse cache, ou testes (e trocas de
    ambiente em runtime) ficariam presos ao primeiro valor lido."""

    def test_reset_settings_cache_reflete_nova_variavel_de_ambiente(self, monkeypatch):
        _limpar_env_relevante(monkeypatch)
        monkeypatch.setenv("GROQ_API_KEY", "primeira-chave")
        primeira = get_settings()
        assert primeira.groq_api_key == "primeira-chave"

        monkeypatch.setenv("GROQ_API_KEY", "segunda-chave")
        ainda_a_primeira = get_settings()
        assert ainda_a_primeira.groq_api_key == "primeira-chave", (
            "sem reset, o cache deveria manter o valor antigo"
        )

        reset_settings_cache()
        segunda = get_settings()
        assert segunda.groq_api_key == "segunda-chave"
        reset_settings_cache()

    def test_settings_e_imutavel(self, monkeypatch):
        _limpar_env_relevante(monkeypatch)
        settings = get_settings()

        assert isinstance(settings, Settings)
        try:
            settings.groq_api_key = "outra-coisa"
            assert False, "Settings deveria ser frozen (imutável)"
        except (AttributeError, TypeError, Exception) as exc:
            assert type(exc).__name__ in ("FrozenInstanceError", "AttributeError")
        reset_settings_cache()