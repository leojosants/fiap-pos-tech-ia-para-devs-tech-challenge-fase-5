"""Testes do conteúdo estruturado enviado ao modelo para o resumo do
corretor (src/llm/prompts.py — montar_conteudo_resumo).

Não testa o texto integral do PROMPT_RESUMO_CORRETOR (frágil e pouco
útil); testa o contrato que o summarizer vai depender: quais dados
aparecem no conteúdo montado a partir de um Lead.
"""

from src.core.enums import (
    Intent,
    InvestmentGoal,
    InvestorProfile,
    LeadStatus,
    LeadTemperature,
    Urgency,
    Zone,
)
from src.core.models import Lead
from src.llm.prompts import montar_conteudo_resumo


class TestMontarConteudoResumo:

    def test_inclui_nome_quando_presente(self):
        lead = Lead(nome="Ana", intent=Intent.COMPRA)
        conteudo = montar_conteudo_resumo(lead)
        assert "Ana" in conteudo

    def test_omite_nome_quando_ausente(self):
        lead = Lead(intent=Intent.COMPRA)
        conteudo = montar_conteudo_resumo(lead)
        assert "Nome:" not in conteudo

    def test_inclui_intencao_legivel(self):
        lead = Lead(intent=Intent.COMPRA)
        assert "compra de imóvel" in montar_conteudo_resumo(lead)

    def test_intencao_investimento_legivel(self):
        lead = Lead(intent=Intent.INVESTIMENTO)
        assert "investimento imobiliário" in montar_conteudo_resumo(lead)

    def test_inclui_score_e_temperatura(self):
        lead = Lead(intent=Intent.COMPRA, score=85, temperature=LeadTemperature.QUENTE)
        conteudo = montar_conteudo_resumo(lead)
        assert "85" in conteudo
        assert "quente" in conteudo

    def test_inclui_status_do_funil(self):
        lead = Lead(intent=Intent.COMPRA, status=LeadStatus.QUALIFICADO)
        assert "qualificado" in montar_conteudo_resumo(lead)

    def test_inclui_apenas_slots_preenchidos_do_cenario_compra(self):
        lead = Lead(
            intent=Intent.COMPRA,
            zona_interesse=Zone.SUL,
            preco_max=800_000,
            quartos_desejados=None,  # ainda não informado
            urgencia=Urgency.NAO_INFORMADA,  # ainda não informado
            disponibilidade_reuniao="",  # ainda não informado
        )
        conteudo = montar_conteudo_resumo(lead)

        assert "zona sul" in conteudo
        assert "800" in conteudo  # valor monetário formatado
        # slots não preenchidos não devem aparecer como linha vazia/None
        assert "None" not in conteudo

    def test_inclui_slots_do_cenario_investimento(self):
        lead = Lead(
            intent=Intent.INVESTIMENTO,
            perfil_investidor=InvestorProfile.CONSERVADOR,
            ticket_disponivel=500_000,
            objetivo_investimento=InvestmentGoal.RENDA,
        )
        conteudo = montar_conteudo_resumo(lead)

        assert "conservador" in conteudo
        assert "renda mensal" in conteudo

    def test_inclui_preferencias_quando_declaradas(self):
        lead = Lead(
            intent=Intent.COMPRA, preferencias=["aceita pet", "vaga de garagem"]
        )
        conteudo = montar_conteudo_resumo(lead)
        assert "aceita pet" in conteudo
        assert "vaga de garagem" in conteudo

    def test_omite_preferencias_quando_vazias(self):
        lead = Lead(intent=Intent.COMPRA)
        assert "Preferências" not in montar_conteudo_resumo(lead)

    def test_agendamento_texto_e_incluido_quando_fornecido(self):
        lead = Lead(intent=Intent.COMPRA)
        conteudo = montar_conteudo_resumo(
            lead, agendamento_texto="Reunião confirmada: sexta-feira, 21/08 às 15h00."
        )
        assert "Reunião confirmada" in conteudo

    def test_sem_agendamento_texto_nao_aparece_nada_sobre_isso(self):
        lead = Lead(intent=Intent.COMPRA)
        conteudo = montar_conteudo_resumo(lead)
        assert "Reunião" not in conteudo
        assert "agendad" not in conteudo.lower()

    def test_lead_totalmente_vazio_nao_quebra(self):
        lead = Lead()
        conteudo = montar_conteudo_resumo(lead)
        assert isinstance(conteudo, str)
        assert "não identificada" in conteudo  # intent INDEFINIDA