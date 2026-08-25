"""Testes do cliente Groq (src/llm/groq_client.py).

Nenhum teste aqui faz chamada de rede nem depende de uma
GROQ_API_KEY real — decisão já validada com você na etapa de
planejamento (ver docs/decisoes_tecnicas.md, Etapa 8).

Estratégia de mock: `GroqClient` é instanciado com uma chave de API
fake e `demo_mode_forcado=False`, o que faz `__init__` construir um
cliente `groq.Groq` real — mas construir o objeto do SDK não faz
nenhuma chamada HTTP, só monta a configuração local. Em seguida,
`self._client` é substituído por um `unittest.mock.Mock()`, com
`chat.completions.create` programado para devolver uma resposta falsa
controlada por cada teste. Esse padrão foi validado manualmente antes
de escrever o arquivo (rodando `client._client.chat.completions.create`
mockado ponta a ponta) para confirmar que não há nenhum ponto de
contato real com a rede.

Escopo:

1. `UsageStats` e `LLMResponse`: os acumuladores e o objeto de
   resultado, puros.
2. `GroqClient.disponivel`: a leitura de `modo_demo` que decide se
   existe cliente utilizável.
3. `conversar()`, `extrair_json()`, `resumir()`, `testar_conexao()`:
   os quatro métodos públicos, cada um verificando também os
   parâmetros exatos enviados ao SDK (modelo, temperatura,
   `response_format`, `tool_choice`) — não só o resultado.
4. `_chamar()` — a lógica de retry: erro transitório
   (`tool_use_failed`) retenta, erro 400/BadRequest não retenta, e
   erro genérico retenta até o limite configurado antes de desistir.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from src.core.config import Settings
from src.llm.groq_client import GroqClient, LLMResponse, UsageStats


def _settings(**overrides) -> Settings:
    base = dict(
        groq_api_key="chave-fake-de-teste",
        model_fast="modelo-rapido-fake",
        model_smart="modelo-inteligente-fake",
        demo_mode_forcado=False,
        database_path=Path("data/runtime/teste.db"),
        log_level="INFO",
        max_tentativas=2,
    )
    base.update(overrides)
    return Settings(**base)


def _cliente_com_mock(**settings_overrides) -> tuple[GroqClient, Mock]:
    """GroqClient fora do modo demo, com self._client substituído por
    um Mock — a construção do cliente real (groq.Groq) não faz
    chamada HTTP, só é descartada logo em seguida."""
    cliente = GroqClient(_settings(**settings_overrides))
    mock = Mock()
    cliente._client = mock
    return cliente, mock


def _resposta_ok(conteudo="ok", prompt_tokens=10, completion_tokens=5):
    resposta = MagicMock()
    resposta.choices = [MagicMock(message=MagicMock(content=conteudo))]
    resposta.usage = MagicMock(
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
    )
    return resposta


# ============================================================
# UsageStats e LLMResponse — puros
# ============================================================


class TestUsageStats:

    def test_registrar_sucesso_atualiza_tokens_e_latencia(self):
        stats = UsageStats()
        stats.registrar(LLMResponse(
            conteudo="ok", sucesso=True, latencia_ms=120,
            tokens_entrada=10, tokens_saida=5,
        ))

        assert stats.chamadas == 1
        assert stats.falhas == 0
        assert stats.tokens_entrada == 10
        assert stats.tokens_saida == 5
        assert stats.latencias == [120]

    def test_registrar_falha_nao_atualiza_tokens_nem_latencia(self):
        stats = UsageStats()
        stats.registrar(LLMResponse(conteudo="", sucesso=False, erro="timeout"))

        assert stats.chamadas == 1
        assert stats.falhas == 1
        assert stats.tokens_entrada == 0
        assert stats.latencias == []

    def test_resumo_sem_chamadas_nao_gera_divisao_por_zero(self):
        assert UsageStats().resumo() == {
            "chamadas": 0, "falhas": 0, "taxa_sucesso": 0.0,
            "tokens_entrada": 0, "tokens_saida": 0, "latencia_media_ms": 0,
        }

    def test_resumo_calcula_taxa_de_sucesso_e_latencia_media(self):
        stats = UsageStats()
        stats.registrar(LLMResponse(conteudo="a", sucesso=True, latencia_ms=100))
        stats.registrar(LLMResponse(conteudo="b", sucesso=True, latencia_ms=200))
        stats.registrar(LLMResponse(conteudo="", sucesso=False, erro="falha"))

        resumo = stats.resumo()

        assert resumo["chamadas"] == 3
        assert resumo["falhas"] == 1
        assert resumo["taxa_sucesso"] == round(2 / 3 * 100, 1)
        assert resumo["latencia_media_ms"] == 150


class TestLLMResponseTotalTokens:

    def test_soma_entrada_e_saida(self):
        resposta = LLMResponse(
            conteudo="x", sucesso=True, tokens_entrada=10, tokens_saida=7
        )
        assert resposta.total_tokens == 17


# ============================================================
# Disponibilidade
# ============================================================


class TestDisponivel:

    def test_modo_demo_forcado_deixa_cliente_indisponivel(self):
        cliente = GroqClient(_settings(demo_mode_forcado=True))
        assert cliente.disponivel is False

    def test_sem_chave_de_api_deixa_cliente_indisponivel(self):
        cliente = GroqClient(_settings(groq_api_key=""))
        assert cliente.disponivel is False

    def test_com_chave_e_sem_forcar_fica_disponivel(self):
        cliente = GroqClient(_settings())
        assert cliente.disponivel is True


# ============================================================
# conversar()
# ============================================================


class TestConversar:

    def test_indisponivel_retorna_erro_sem_chamar_o_sdk(self):
        cliente = GroqClient(_settings(demo_mode_forcado=True))
        resultado = cliente.conversar("prompt", [{"role": "user", "content": "oi"}])

        assert resultado.sucesso is False
        assert "modo demonstrativo" in resultado.erro.lower()

    def test_sucesso_retorna_conteudo_modelo_e_tokens(self):
        cliente, mock = _cliente_com_mock()
        mock.chat.completions.create.return_value = _resposta_ok("Olá! Como posso ajudar?")

        resultado = cliente.conversar("prompt do sistema", [{"role": "user", "content": "oi"}])

        assert resultado.sucesso is True
        assert resultado.conteudo == "Olá! Como posso ajudar?"
        assert resultado.modelo == "modelo-rapido-fake"
        assert resultado.tokens_entrada == 10
        assert resultado.tokens_saida == 5

    def test_usa_o_modelo_rapido(self):
        cliente, mock = _cliente_com_mock()
        mock.chat.completions.create.return_value = _resposta_ok()

        cliente.conversar("prompt", [])

        kwargs = mock.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == "modelo-rapido-fake"

    def test_nao_ativa_json_mode(self):
        cliente, mock = _cliente_com_mock()
        mock.chat.completions.create.return_value = _resposta_ok()

        cliente.conversar("prompt", [])

        kwargs = mock.chat.completions.create.call_args.kwargs
        assert "response_format" not in kwargs

    def test_registra_estatisticas_de_uso(self):
        cliente, mock = _cliente_com_mock()
        mock.chat.completions.create.return_value = _resposta_ok()

        cliente.conversar("prompt", [])

        assert cliente.stats.chamadas == 1
        assert cliente.stats.falhas == 0


# ============================================================
# extrair_json()
# ============================================================


class TestExtrairJson:

    def test_json_valido_e_parseado(self):
        cliente, mock = _cliente_com_mock()
        mock.chat.completions.create.return_value = _resposta_ok(
            json.dumps({"zona": "sul", "quartos": 2})
        )

        dados, resposta = cliente.extrair_json("prompt", "quero algo na zona sul")

        assert dados == {"zona": "sul", "quartos": 2}
        assert resposta.sucesso is True

    def test_json_invalido_retorna_none_e_marca_erro(self):
        cliente, mock = _cliente_com_mock()
        mock.chat.completions.create.return_value = _resposta_ok("isto não é JSON")

        dados, resposta = cliente.extrair_json("prompt", "texto qualquer")

        assert dados is None
        assert resposta.sucesso is False
        assert "JSON inválido" in resposta.erro

    def test_chamada_com_falha_retorna_none(self):
        cliente = GroqClient(_settings(demo_mode_forcado=True))
        dados, resposta = cliente.extrair_json("prompt", "texto")

        assert dados is None
        assert resposta.sucesso is False

    def test_ativa_json_mode(self):
        cliente, mock = _cliente_com_mock()
        mock.chat.completions.create.return_value = _resposta_ok("{}")

        cliente.extrair_json("prompt", "texto")

        kwargs = mock.chat.completions.create.call_args.kwargs
        assert kwargs["response_format"] == {"type": "json_object"}

    def test_usa_modelo_smart_por_padrao(self):
        cliente, mock = _cliente_com_mock()
        mock.chat.completions.create.return_value = _resposta_ok("{}")

        cliente.extrair_json("prompt", "texto")

        kwargs = mock.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == "modelo-inteligente-fake"

    def test_usa_modelo_fast_quando_solicitado(self):
        cliente, mock = _cliente_com_mock()
        mock.chat.completions.create.return_value = _resposta_ok("{}")

        cliente.extrair_json("prompt", "texto", usar_modelo_smart=False)

        kwargs = mock.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == "modelo-rapido-fake"


# ============================================================
# resumir()
# ============================================================


class TestResumir:

    def test_sucesso_retorna_conteudo(self):
        cliente, mock = _cliente_com_mock()
        mock.chat.completions.create.return_value = _resposta_ok("Lead qualificado, quer 2 quartos.")

        resultado = cliente.resumir("prompt", "dados do lead")

        assert resultado.sucesso is True
        assert resultado.conteudo == "Lead qualificado, quer 2 quartos."

    def test_usa_modelo_smart_com_temperatura_baixa(self):
        cliente, mock = _cliente_com_mock()
        mock.chat.completions.create.return_value = _resposta_ok()

        cliente.resumir("prompt", "dados")

        kwargs = mock.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == "modelo-inteligente-fake"
        assert kwargs["temperature"] == 0.4
        assert kwargs["max_tokens"] == 700


# ============================================================
# testar_conexao()
# ============================================================


class TestTestarConexao:

    def test_indisponivel_nao_chama_o_sdk(self):
        cliente = GroqClient(_settings(demo_mode_forcado=True))
        ok, mensagem = cliente.testar_conexao()

        assert ok is False
        assert mensagem != ""

    def test_sucesso_informa_modelo_e_latencia(self):
        cliente, mock = _cliente_com_mock()
        mock.chat.completions.create.return_value = _resposta_ok("ok")

        ok, mensagem = cliente.testar_conexao()

        assert ok is True
        assert "modelo-rapido-fake" in mensagem
        assert "Conectado" in mensagem

    def test_falha_retorna_o_erro(self):
        cliente, mock = _cliente_com_mock(max_tentativas=1)
        mock.chat.completions.create.side_effect = TimeoutError("tempo esgotado")

        ok, mensagem = cliente.testar_conexao()

        assert ok is False
        assert "tempo esgotado" in mensagem


# ============================================================
# Retry — a lógica mais sensível do módulo
# ============================================================


class TestRetry:

    @pytest.fixture(autouse=True)
    def _sem_espera_real(self, monkeypatch):
        # A cada retentativa o código chama time.sleep(0.8 * tentativa)
        # — sem isso, os testes desta classe levariam segundos reais.
        monkeypatch.setattr("src.llm.groq_client.time.sleep", lambda s: None)

    def test_erro_generico_retenta_ate_o_limite_e_desiste(self):
        cliente, mock = _cliente_com_mock(max_tentativas=3)
        mock.chat.completions.create.side_effect = ConnectionError("falha de rede")

        resultado = cliente.conversar("prompt", [])

        assert resultado.sucesso is False
        assert mock.chat.completions.create.call_count == 3
        assert "falha de rede" in resultado.erro

    def test_erro_400_nao_retenta(self):
        cliente, mock = _cliente_com_mock(max_tentativas=3)
        mock.chat.completions.create.side_effect = Exception("Error code: 400 - BadRequest")

        cliente.conversar("prompt", [])

        assert mock.chat.completions.create.call_count == 1

    def test_erro_tool_use_failed_e_retentado_mesmo_sendo_400(self):
        # Documentado no código como exceção deliberada: mesmo contendo
        # "400", tool_use_failed é tratado como transitório.
        cliente, mock = _cliente_com_mock(max_tentativas=3)
        mock.chat.completions.create.side_effect = Exception(
            "Error code: 400 - tool_use_failed"
        )

        cliente.conversar("prompt", [])

        assert mock.chat.completions.create.call_count == 3

    def test_falha_seguida_de_sucesso_retorna_o_resultado_bem_sucedido(self):
        cliente, mock = _cliente_com_mock(max_tentativas=3)
        mock.chat.completions.create.side_effect = [
            ConnectionError("instabilidade momentânea"),
            _resposta_ok("recuperou na segunda tentativa"),
        ]

        resultado = cliente.conversar("prompt", [])

        assert resultado.sucesso is True
        assert resultado.conteudo == "recuperou na segunda tentativa"
        assert mock.chat.completions.create.call_count == 2

    def test_falha_final_e_registrada_nas_estatisticas(self):
        cliente, mock = _cliente_com_mock(max_tentativas=1)
        mock.chat.completions.create.side_effect = ConnectionError("erro")

        cliente.conversar("prompt", [])

        assert cliente.stats.chamadas == 1
        assert cliente.stats.falhas == 1


# ============================================================
# Parâmetros comuns a toda chamada
# ============================================================


class TestKwargsComuns:

    def test_tool_choice_none_sempre_presente(self):
        cliente, mock = _cliente_com_mock()
        mock.chat.completions.create.return_value = _resposta_ok()

        cliente.conversar("prompt", [])

        kwargs = mock.chat.completions.create.call_args.kwargs
        assert kwargs["tool_choice"] == "none"

    def test_prompt_sistema_vira_primeira_mensagem_em_conversar(self):
        cliente, mock = _cliente_com_mock()
        mock.chat.completions.create.return_value = _resposta_ok()

        cliente.conversar("você é um assistente", [{"role": "user", "content": "oi"}])

        kwargs = mock.chat.completions.create.call_args.kwargs
        assert kwargs["messages"][0] == {"role": "system", "content": "você é um assistente"}
        assert kwargs["messages"][1] == {"role": "user", "content": "oi"}