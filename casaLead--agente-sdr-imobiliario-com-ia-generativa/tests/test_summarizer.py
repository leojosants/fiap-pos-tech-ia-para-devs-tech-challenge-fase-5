"""Testes do summarizer.

Usa um GroqClient falso (mesmo padrão de test_conversation_agent.py),
mas devolvendo instâncias reais de LLMResponse — garante fidelidade ao
contrato real sem depender de rede ou de chave de API. O
AppointmentRepository é real, com SQLite via tmp_path.
"""

from datetime import datetime, timedelta

import pytest

from src.core.enums import AppointmentStatus, AppointmentType, EventType, Intent
from src.core.models import Appointment, Lead
from src.llm.groq_client import LLMResponse
from src.persistence.appointment_repository import AppointmentRepository
from src.persistence.database import create_schema
from src.persistence.lead_repository import LeadRepository
from src.reporting.summarizer import ResumoGerado, Summarizer


class _ClienteFalso:
    """Substitui o GroqClient: registra as chamadas, sem tocar rede."""

    def __init__(
        self, *, disponivel: bool = True, resposta: LLMResponse | None = None
    ):
        self.disponivel = disponivel
        self._resposta = resposta or LLMResponse(
            conteudo="Ana busca um apartamento na zona sul, já qualificada.",
            sucesso=True,
            modelo="modelo-falso",
            latencia_ms=42,
            tokens_entrada=100,
            tokens_saida=30,
        )
        self.chamadas: list[tuple[str, str]] = []

    def resumir(self, prompt_sistema: str, conteudo: str) -> LLMResponse:
        self.chamadas.append((prompt_sistema, conteudo))
        return self._resposta


@pytest.fixture
def db_path(tmp_path):
    caminho = tmp_path / "test_casalead.db"
    create_schema(caminho)
    return caminho


@pytest.fixture
def appointment_repo(db_path) -> AppointmentRepository:
    return AppointmentRepository(db_path)


@pytest.fixture
def lead_repo(db_path) -> LeadRepository:
    return LeadRepository(db_path)


@pytest.fixture
def lead_persistido(lead_repo) -> Lead:
    return lead_repo.criar(Lead(nome="Ana", intent=Intent.COMPRA))


# ============================================================
# Caminho via LLM
# ============================================================

class TestGerarComLLM:

    def test_llm_disponivel_e_sucesso_usa_origem_llm(
        self, appointment_repo, lead_persistido
    ):
        cliente = _ClienteFalso()
        summarizer = Summarizer(cliente=cliente, agendamentos=appointment_repo)

        resumo = summarizer.gerar(lead_persistido)

        assert resumo.origem == "llm"
        assert resumo.usou_llm
        assert not resumo.houve_degradacao
        assert resumo.texto == "Ana busca um apartamento na zona sul, já qualificada."

    def test_grava_o_resumo_no_lead(self, appointment_repo, lead_persistido):
        cliente = _ClienteFalso()
        summarizer = Summarizer(cliente=cliente, agendamentos=appointment_repo)

        resumo = summarizer.gerar(lead_persistido)

        assert lead_persistido.resumo_corretor == resumo.texto

    def test_conteudo_enviado_ao_cliente_inclui_dados_do_lead(
        self, appointment_repo, lead_persistido
    ):
        cliente = _ClienteFalso()
        summarizer = Summarizer(cliente=cliente, agendamentos=appointment_repo)

        summarizer.gerar(lead_persistido)

        assert len(cliente.chamadas) == 1
        _, conteudo = cliente.chamadas[0]
        assert "Ana" in conteudo
        assert "compra de imóvel" in conteudo

    def test_metadados_de_rastreabilidade_sao_preservados(
        self, appointment_repo, lead_persistido
    ):
        cliente = _ClienteFalso()
        summarizer = Summarizer(cliente=cliente, agendamentos=appointment_repo)

        resumo = summarizer.gerar(lead_persistido)

        assert resumo.modelo == "modelo-falso"
        assert resumo.latencia_ms == 42
        assert resumo.tokens == 130  # 100 entrada + 30 saída


class TestDegradacaoParaTemplate:

    def test_llm_disponivel_mas_falha_degrada_para_fallback(
        self, appointment_repo, lead_persistido
    ):
        resposta_falha = LLMResponse(conteudo="", sucesso=False, erro="timeout")
        cliente = _ClienteFalso(resposta=resposta_falha)
        summarizer = Summarizer(cliente=cliente, agendamentos=appointment_repo)

        resumo = summarizer.gerar(lead_persistido)

        assert resumo.origem == "fallback"
        assert resumo.houve_degradacao
        assert not resumo.usou_llm

    def test_llm_devolve_conteudo_vazio_tambem_degrada(
        self, appointment_repo, lead_persistido
    ):
        resposta_vazia = LLMResponse(conteudo="   ", sucesso=True)
        cliente = _ClienteFalso(resposta=resposta_vazia)
        summarizer = Summarizer(cliente=cliente, agendamentos=appointment_repo)

        resumo = summarizer.gerar(lead_persistido)
        assert resumo.origem == "fallback"

    def test_llm_indisponivel_usa_template_sem_chamar_resumir(
        self, appointment_repo, lead_persistido
    ):
        cliente = _ClienteFalso(disponivel=False)
        summarizer = Summarizer(cliente=cliente, agendamentos=appointment_repo)

        resumo = summarizer.gerar(lead_persistido)

        assert resumo.origem == "deterministico"
        assert cliente.chamadas == []  # nunca tentou chamar a API

    def test_template_inclui_nome_e_dados_estruturados(
        self, appointment_repo, lead_persistido
    ):
        cliente = _ClienteFalso(disponivel=False)
        summarizer = Summarizer(cliente=cliente, agendamentos=appointment_repo)

        resumo = summarizer.gerar(lead_persistido)

        assert "Ana" in resumo.texto
        assert "compra de imóvel" in resumo.texto

    def test_template_tambem_grava_no_lead(self, appointment_repo, lead_persistido):
        cliente = _ClienteFalso(disponivel=False)
        summarizer = Summarizer(cliente=cliente, agendamentos=appointment_repo)

        resumo = summarizer.gerar(lead_persistido)
        assert lead_persistido.resumo_corretor == resumo.texto


# ============================================================
# Contexto de agendamento
# ============================================================

class TestTextoAgendamento:

    def test_sem_compromisso_ativo_nao_menciona_agendamento(
        self, appointment_repo, lead_persistido
    ):
        cliente = _ClienteFalso()
        summarizer = Summarizer(cliente=cliente, agendamentos=appointment_repo)

        summarizer.gerar(lead_persistido)

        _, conteudo = cliente.chamadas[0]
        assert "Compromisso agendado" not in conteudo

    def test_com_compromisso_ativo_inclui_no_conteudo_enviado(
        self, appointment_repo, lead_persistido
    ):
        appointment_repo.criar(
            Appointment(
                lead_id=lead_persistido.id,
                tipo=AppointmentType.VISITA_IMOVEL,
                data_hora=datetime.now() + timedelta(days=2),
            )
        )
        cliente = _ClienteFalso()
        summarizer = Summarizer(cliente=cliente, agendamentos=appointment_repo)

        summarizer.gerar(lead_persistido)

        _, conteudo = cliente.chamadas[0]
        assert "Compromisso agendado" in conteudo
        assert "visita ao imóvel" in conteudo

    def test_compromisso_cancelado_nao_aparece(
        self, appointment_repo, lead_persistido
    ):
        ap = appointment_repo.criar(
            Appointment(
                lead_id=lead_persistido.id,
                tipo=AppointmentType.VISITA_IMOVEL,
                data_hora=datetime.now() + timedelta(days=2),
            )
        )
        appointment_repo.atualizar_status(ap.id, AppointmentStatus.CANCELADO)

        cliente = _ClienteFalso()
        summarizer = Summarizer(cliente=cliente, agendamentos=appointment_repo)
        summarizer.gerar(lead_persistido)

        _, conteudo = cliente.chamadas[0]
        assert "Compromisso agendado" not in conteudo

    def test_agendamento_tambem_aparece_no_template_deterministico(
        self, appointment_repo, lead_persistido
    ):
        appointment_repo.criar(
            Appointment(
                lead_id=lead_persistido.id,
                tipo=AppointmentType.REUNIAO_ONLINE,
                data_hora=datetime.now() + timedelta(days=1),
            )
        )
        cliente = _ClienteFalso(disponivel=False)
        summarizer = Summarizer(cliente=cliente, agendamentos=appointment_repo)

        resumo = summarizer.gerar(lead_persistido)
        assert "Compromisso agendado" in resumo.texto


# ============================================================
# eventos_do_resultado
# ============================================================

class TestEventosDoResultado:

    def test_origem_llm_registra_usou_llm_true(self):
        resumo = ResumoGerado(texto="x", origem="llm")
        eventos = Summarizer.eventos_do_resultado(resumo)

        assert len(eventos) == 1
        tipo, detalhes = eventos[0]
        assert tipo == EventType.RESUMO_GERADO
        assert detalhes["origem"] == "llm"
        assert detalhes["usou_llm"] is True

    def test_origem_deterministico_registra_usou_llm_false(self):
        resumo = ResumoGerado(texto="x", origem="deterministico")
        eventos = Summarizer.eventos_do_resultado(resumo)

        tipo, detalhes = eventos[0]
        assert detalhes["usou_llm"] is False

    def test_sempre_gera_exatamente_um_evento(self):
        for origem in ("llm", "deterministico", "fallback"):
            resumo = ResumoGerado(texto="x", origem=origem)
            assert len(Summarizer.eventos_do_resultado(resumo)) == 1