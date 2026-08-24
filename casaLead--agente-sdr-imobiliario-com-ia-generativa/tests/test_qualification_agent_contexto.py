"""Testes do QualificationAgent — escopo restrito ao parâmetro
`ultima_pergunta_agente`, adicionado para corrigir a extração de
respostas curtas sem contexto (ex.: "2" sozinho não sendo atribuído a
"quartos"). Não é a suíte completa de qualification_agent.py — essa
ainda está pendente (Etapa 8, "ampliar testes").

Usa um GroqClient falso, com _settings.modo_demo controlável e
extrair_json() programável — evita rede e chave de API real.
"""

from types import SimpleNamespace

import pytest

from src.agents.qualification_agent import QualificationAgent
from src.core.enums import Intent
from src.core.models import Lead


class _ClienteFalso:
    """Substitui o GroqClient: registra o conteúdo recebido por
    extrair_json(), sem tocar rede."""

    def __init__(self, *, modo_demo: bool = False, dados_llm: dict | None = None):
        self._settings = SimpleNamespace(modo_demo=modo_demo)
        self._dados_llm = dados_llm if dados_llm is not None else {}
        self.conteudos_recebidos: list[str] = []

    def extrair_json(self, prompt_sistema: str, conteudo: str):
        self.conteudos_recebidos.append(conteudo)
        resposta = SimpleNamespace(
            conteudo=str(self._dados_llm), sucesso=True, erro="",
            latencia_ms=5, modelo="modelo-falso",
        )
        return (dict(self._dados_llm) if self._dados_llm else None), resposta


def _lead_aguardando_quartos() -> Lead:
    """Lead com tudo preenchido exceto quartos — força o caminho por LLM
    (regex sozinho não cobriria tudo, então cobriu_tudo=False)."""
    from src.core.enums import Urgency, Zone

    return Lead(
        intent=Intent.COMPRA,
        zona_interesse=Zone.SUL,
        preco_max=500_000.0,
        urgencia=Urgency.IMEDIATA,
        disponibilidade_reuniao="sexta de manhã",
    )


class TestContextoRepassadoParaExtracao:

    def test_sem_ultima_pergunta_conteudo_e_so_o_texto(self):
        """Retrocompatibilidade: comportamento igual ao de antes desta
        mudança quando ultima_pergunta_agente não é informado."""
        cliente = _ClienteFalso()
        agente = QualificationAgent(cliente=cliente)

        agente.qualificar(_lead_aguardando_quartos(), "2")

        assert cliente.conteudos_recebidos == ["2"]

    def test_com_ultima_pergunta_conteudo_inclui_pergunta_e_resposta(self):
        cliente = _ClienteFalso()
        agente = QualificationAgent(cliente=cliente)

        agente.qualificar(
            _lead_aguardando_quartos(),
            "2",
            ultima_pergunta_agente="Quantos quartos você precisa?",
        )

        assert len(cliente.conteudos_recebidos) == 1
        conteudo = cliente.conteudos_recebidos[0]
        assert "PERGUNTA ANTERIOR" in conteudo
        assert "Quantos quartos você precisa?" in conteudo
        assert "RESPOSTA DA PESSOA: 2" in conteudo

    def test_modo_demo_nunca_chama_extrair_json(self):
        """ultima_pergunta_agente não força o caminho LLM — a decisão de
        usar LLM continua a mesma de antes (modo_demo / cobertura dos
        padrões)."""
        cliente = _ClienteFalso(modo_demo=True)
        agente = QualificationAgent(cliente=cliente)

        agente.qualificar(
            _lead_aguardando_quartos(),
            "2",
            ultima_pergunta_agente="Quantos quartos você precisa?",
        )

        assert cliente.conteudos_recebidos == []


class TestExtracaoComContextoPreencheOSlot:
    """Valida a fiação completa: dado um retorno simulado do modelo
    (como se ele tivesse corretamente interpretado "2" com a pergunta em
    contexto), o slot é de fato aplicado ao lead. Não testa a
    compreensão real do modelo — isso só um teste manual com API real
    confirma — testa que, SE o modelo responder certo, o resultado chega
    ao domínio corretamente."""

    def test_quartos_extraido_com_contexto_e_aplicado_ao_lead(self):
        cliente = _ClienteFalso(dados_llm={"quartos": 2})
        agente = QualificationAgent(cliente=cliente)
        lead = _lead_aguardando_quartos()

        resultado = agente.qualificar(
            lead, "2", ultima_pergunta_agente="Quantos quartos você precisa?"
        )

        assert lead.quartos_desejados == 2
        assert resultado.slots_atualizados.get("quartos_desejados") == 2