"""Testes da correção: a persona não deve prometer contato ativo
(ligação, mensagem, e-mail) da equipe, porque o sistema nunca coleta
telefone nem e-mail do lead em nenhum ponto da conversa — descoberto em
validação manual na interface (Etapa 6).
"""

from src.core.enums import Intent, Urgency, Zone
from src.core.models import Lead
from src.llm.demo_engine import _ENCERRAMENTO
from src.llm.prompts import PERSONA_BASE, montar_prompt_sistema


def _lead_totalmente_qualificado() -> Lead:
    return Lead(
        nome="Ana",
        intent=Intent.COMPRA,
        zona_interesse=Zone.SUL,
        preco_max=500_000.0,
        quartos_desejados=3,
        urgencia=Urgency.IMEDIATA,
        disponibilidade_reuniao="segunda de tarde",
    )


class TestRegraNaPersona:

    def test_persona_probe_prometer_contato_ativo(self):
        assert "Não prometa que alguém da equipe fará contato ativo" in PERSONA_BASE

    def test_persona_explica_o_motivo(self):
        """Não é só uma proibição — o modelo precisa entender o porquê,
        senão pode reintroduzir a promessa por conta própria em outra
        formulação."""
        assert "não coleta telefone nem e-mail" in PERSONA_BASE


class TestInstrucaoDeEncerramento:

    def test_prompt_de_qualificacao_completa_nao_promete_contato(self):
        lead = _lead_totalmente_qualificado()
        prompt = montar_prompt_sistema(lead)

        assert "QUALIFICAÇÃO COMPLETA" in prompt
        assert "vai entrar em contato" not in prompt
        assert "entra em contato" not in prompt

    def test_prompt_de_qualificacao_completa_orienta_fala_correta(self):
        lead = _lead_totalmente_qualificado()
        prompt = montar_prompt_sistema(lead)
        assert "registradas com a equipe" in prompt


class TestEncerramentoDeterministico:

    def test_nao_promete_contato_ativo(self):
        assert "entra em contato" not in _ENCERRAMENTO
        assert "corretor" not in _ENCERRAMENTO.lower()

    def test_ainda_agradece_e_confirma_registro(self):
        assert "Obrigada" in _ENCERRAMENTO
        assert "registradas" in _ENCERRAMENTO