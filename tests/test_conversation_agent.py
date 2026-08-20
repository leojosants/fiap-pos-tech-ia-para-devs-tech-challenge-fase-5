"""Testes do conversation_agent — foco no que mudou no Passo 3.

Não depende de GroqClient nem DemoEngine reais (nem de chave de API):
usa dublês (fakes) que implementam só a interface que o ConversationAgent
efetivamente chama. Isso mantém os testes rápidos, sem rede e sem
depender de configuração de ambiente.
"""

from dataclasses import dataclass

import pytest

from src.agents.conversation_agent import ConversationAgent
from src.core.enums import Intent
from src.core.models import Lead


@dataclass
class _RespostaLLMFalsa:
    sucesso: bool = True
    conteudo: str = "Perfeito, já anotei aqui."
    modelo: str = "modelo-falso"
    latencia_ms: int = 10
    total_tokens: int = 5


class _ClienteFalso:
    """Substitui o GroqClient: registra o prompt recebido, sem chamar API."""

    def __init__(self, *, disponivel: bool = True, resposta: _RespostaLLMFalsa | None = None):
        self.disponivel = disponivel
        self._resposta = resposta or _RespostaLLMFalsa()
        self.prompts_recebidos: list[str] = []

    def conversar(self, prompt: str, historico: list[dict]):
        self.prompts_recebidos.append(prompt)
        return self._resposta


class _MotorDemoFalso:
    """Substitui o DemoEngine: devolve um texto fixo, sem lógica real."""

    def responder(self, lead: Lead, texto_do_lead: str) -> str:
        return "Resposta determinística de teste."


def _lead() -> Lead:
    return Lead(nome="Ana", intent=Intent.COMPRA)


class TestAgendamentoContextoChegaAoPrompt:

    def test_agendamento_contexto_e_incluido_no_prompt_enviado_ao_llm(self):
        cliente = _ClienteFalso()
        agente = ConversationAgent(cliente=cliente, motor_demo=_MotorDemoFalso())

        bloco = "COMPROMISSO CONFIRMADO NESTE TURNO\nQuando: sexta-feira, 21/08 às 15h00"
        agente.responder(
            _lead(), "pode ser sexta", historico=[], agendamento_contexto=bloco
        )

        assert len(cliente.prompts_recebidos) == 1
        assert bloco in cliente.prompts_recebidos[0]

    def test_sem_agendamento_contexto_bloco_nao_aparece_no_prompt(self):
        cliente = _ClienteFalso()
        agente = ConversationAgent(cliente=cliente, motor_demo=_MotorDemoFalso())

        agente.responder(_lead(), "oi", historico=[])

        prompt = cliente.prompts_recebidos[0]
        # a persona sempre CITA o nome do bloco (é parte fixa da regra de
        # exceção); o que não deve aparecer é a INSTRUÇÃO de uso, que só
        # é adicionada quando agendamento_contexto é de fato passado
        assert "ÚNICO horário que você pode confirmar" not in prompt
        assert "HORÁRIOS SUGERIDOS" not in prompt

    def test_imoveis_e_agendamento_contexto_coexistem_no_prompt(self):
        cliente = _ClienteFalso()
        agente = ConversationAgent(cliente=cliente, motor_demo=_MotorDemoFalso())

        agente.responder(
            _lead(),
            "ok",
            historico=[],
            imoveis_contexto="CL0001 | Apartamento em Moema",
            agendamento_contexto="HORÁRIOS SUGERIDOS NESTE TURNO\n- terça, 10h",
        )

        prompt = cliente.prompts_recebidos[0]
        assert "IMÓVEIS ENCONTRADOS" in prompt
        assert "HORÁRIOS SUGERIDOS NESTE TURNO" in prompt


class TestModoDeterministicoIgnoraAgendamentoContexto:
    """O motor determinístico não recebe agendamento_contexto — mesma
    decisão já válida para imoveis_contexto: ele não tem capacidade de
    incorporar dados variáveis em linguagem natural."""

    def test_llm_indisponivel_usa_motor_deterministico_sem_erro(self):
        cliente = _ClienteFalso(disponivel=False)
        agente = ConversationAgent(cliente=cliente, motor_demo=_MotorDemoFalso())

        resposta = agente.responder(
            _lead(),
            "pode ser sexta",
            historico=[],
            agendamento_contexto="COMPROMISSO CONFIRMADO NESTE TURNO\n...",
        )

        assert resposta.origem == "deterministico"
        assert resposta.texto == "Resposta determinística de teste."
        # o cliente (LLM) nunca deveria ter sido chamado
        assert cliente.prompts_recebidos == []


class TestCompatibilidadeRetroativa:

    def test_chamada_sem_agendamento_contexto_continua_funcionando(self):
        cliente = _ClienteFalso()
        agente = ConversationAgent(cliente=cliente, motor_demo=_MotorDemoFalso())

        resposta = agente.responder(_lead(), "oi", historico=[])

        assert resposta.origem == "llm"
        assert resposta.texto == "Perfeito, já anotei aqui."