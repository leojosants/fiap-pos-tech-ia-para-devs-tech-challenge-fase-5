"""Testes do gerenciador de follow-up.

Dividido em dois blocos, mesmo espírito de separação já usado no
scheduling_agent: _montar_mensagem e _detalhe_contexto são funções
puras, testadas sem banco; FollowupManager é testado com SQLite real
via tmp_path (banco isolado por teste, mesma justificativa dos demais
repositórios: a entidade é escrita e alterada pelos próprios testes).
"""

from datetime import datetime, timedelta

import pytest

from src.core.enums import (
    ConversationStatus,
    FollowupStatus,
    Intent,
    InvestmentGoal,
    Zone,
)
from src.core.models import Conversation, Followup, Lead
from src.followup.followup_manager import (
    MAX_TENTATIVAS,
    FollowupManager,
    ResultadoFollowup,
    _detalhe_contexto,
    _montar_mensagem,
)
from src.persistence.conversation_repository import ConversationRepository
from src.persistence.database import create_schema, get_connection
from src.persistence.followup_repository import FollowupRepository
from src.persistence.lead_repository import LeadRepository


# ============================================================
# _detalhe_contexto / _montar_mensagem — funções puras
# ============================================================

class TestDetalheContexto:

    def test_sem_nada_conhecido_retorna_vazio(self):
        lead = Lead(intent=Intent.COMPRA)
        assert _detalhe_contexto(lead) == ""

    def test_compra_com_zona_menciona_a_zona(self):
        lead = Lead(intent=Intent.COMPRA, zona_interesse=Zone.SUL)
        assert "zona sul" in _detalhe_contexto(lead)

    def test_aluguel_com_zona_menciona_a_zona(self):
        lead = Lead(intent=Intent.ALUGUEL, zona_interesse=Zone.OESTE)
        assert "zona oeste" in _detalhe_contexto(lead)

    def test_investimento_com_objetivo_menciona_o_objetivo(self):
        lead = Lead(
            intent=Intent.INVESTIMENTO,
            objetivo_investimento=InvestmentGoal.RENDA,
        )
        assert "renda mensal" in _detalhe_contexto(lead)

    def test_investimento_sem_objetivo_retorna_vazio(self):
        lead = Lead(intent=Intent.INVESTIMENTO)
        assert _detalhe_contexto(lead) == ""

    def test_investimento_ignora_zona_mesmo_se_presente(self):
        """zona_interesse não é relevante para investimento — o detalhe
        certo nesse caso é o objetivo, não a região."""
        lead = Lead(
            intent=Intent.INVESTIMENTO,
            zona_interesse=Zone.NORTE,
            objetivo_investimento=InvestmentGoal.VALORIZACAO,
        )
        detalhe = _detalhe_contexto(lead)
        assert "valorização" in detalhe
        assert "zona norte" not in detalhe


class TestMontarMensagem:

    def test_com_nome_inclui_saudacao_personalizada(self):
        lead = Lead(nome="Ana", intent=Intent.COMPRA)
        msg = _montar_mensagem(lead, tentativa=1)
        assert "Ana" in msg

    def test_sem_nome_nao_quebra_e_ainda_cumprimenta(self):
        lead = Lead(intent=Intent.COMPRA)
        msg = _montar_mensagem(lead, tentativa=1)
        assert msg.startswith("Oi!")

    def test_tentativa_1_e_tentativa_2_tem_textos_diferentes(self):
        lead = Lead(nome="Ana", intent=Intent.COMPRA)
        msg1 = _montar_mensagem(lead, tentativa=1)
        msg2 = _montar_mensagem(lead, tentativa=2)
        assert msg1 != msg2

    def test_tentativa_alem_do_mapeamento_nao_falha(self):
        lead = Lead(nome="Ana", intent=Intent.COMPRA)
        msg = _montar_mensagem(lead, tentativa=5)
        assert isinstance(msg, str) and len(msg) > 0

    def test_mensagem_incorpora_detalhe_de_contexto(self):
        lead = Lead(nome="Ana", intent=Intent.COMPRA, zona_interesse=Zone.SUL)
        msg = _montar_mensagem(lead, tentativa=1)
        assert "zona sul" in msg


# ============================================================
# FollowupManager — integração com SQLite real
# ============================================================

@pytest.fixture
def db_path(tmp_path):
    caminho = tmp_path / "test_casalead.db"
    create_schema(caminho)
    return caminho


@pytest.fixture
def lead_repo(db_path) -> LeadRepository:
    return LeadRepository(db_path)


@pytest.fixture
def conversas_repo(db_path) -> ConversationRepository:
    return ConversationRepository(db_path)


@pytest.fixture
def followups_repo(db_path) -> FollowupRepository:
    return FollowupRepository(db_path)


@pytest.fixture
def manager(followups_repo, conversas_repo, lead_repo) -> FollowupManager:
    return FollowupManager(followups_repo, conversas_repo, lead_repo)


@pytest.fixture
def lead_com_conversa_ativa(lead_repo, conversas_repo):
    lead = lead_repo.criar(Lead(nome="Ana", intent=Intent.COMPRA))
    conversa = conversas_repo.criar_conversa(Conversation(lead_id=lead.id))
    return lead, conversa


class TestProcessarLeadSemConversa:

    def test_lead_sem_conversa_nenhuma_nao_faz_nada(self, manager, lead_repo):
        lead = lead_repo.criar(Lead(nome="Sem Conversa"))
        resultado = manager.processar_lead(lead)

        assert resultado.acao == "nenhuma"
        assert not resultado.houve_envio
        assert not resultado.houve_escalada

    def test_lead_com_conversa_encerrada_nenhuma_acao(
        self, manager, lead_repo, conversas_repo
    ):
        lead = lead_repo.criar(Lead(nome="Ana"))
        conversa = conversas_repo.criar_conversa(Conversation(lead_id=lead.id))
        conversas_repo.atualizar_status_conversa(
            conversa.id, ConversationStatus.ENCERRADA
        )

        resultado = manager.processar_lead(lead)
        assert resultado.acao == "nenhuma"

    def test_lead_sem_id_levanta_erro(self, manager):
        with pytest.raises(ValueError):
            manager.processar_lead(Lead(nome="Fantasma"))


class TestPrimeiraTentativa:

    def test_cria_e_envia_a_primeira_tentativa(
        self, manager, lead_com_conversa_ativa, followups_repo
    ):
        lead, conversa = lead_com_conversa_ativa

        resultado = manager.processar_lead(lead)

        assert resultado.houve_envio
        assert resultado.tentativa == 1
        assert resultado.followup is not None

        salvo = followups_repo.buscar_por_id(resultado.followup.id)
        assert salvo.status == FollowupStatus.ENVIADO
        assert salvo.enviado_em is not None

    def test_marca_conversa_como_aguardando_lead(
        self, manager, lead_com_conversa_ativa, conversas_repo
    ):
        lead, conversa = lead_com_conversa_ativa
        manager.processar_lead(lead)

        atualizada = conversas_repo.buscar_conversa(conversa.id)
        assert atualizada.status == ConversationStatus.AGUARDANDO_LEAD


class TestTentativasSubsequentes:

    def test_segunda_chamada_marca_primeira_como_sem_resposta_e_cria_segunda(
        self, manager, lead_com_conversa_ativa, followups_repo
    ):
        lead, conversa = lead_com_conversa_ativa

        primeiro = manager.processar_lead(lead)
        segundo = manager.processar_lead(lead)

        assert segundo.houve_envio
        assert segundo.tentativa == 2

        primeira_tentativa = followups_repo.buscar_por_id(primeiro.followup.id)
        assert primeira_tentativa.status == FollowupStatus.SEM_RESPOSTA

    def test_terceira_chamada_escala_em_vez_de_enviar(
        self, manager, lead_com_conversa_ativa, followups_repo, conversas_repo
    ):
        lead, conversa = lead_com_conversa_ativa

        manager.processar_lead(lead)  # tentativa 1
        segundo = manager.processar_lead(lead)  # tentativa 2 (== MAX_TENTATIVAS)
        terceiro = manager.processar_lead(lead)  # deveria escalar

        assert terceiro.houve_escalada
        assert terceiro.followup is None

        segunda_tentativa = followups_repo.buscar_por_id(segundo.followup.id)
        assert segunda_tentativa.status == FollowupStatus.SEM_RESPOSTA

        atualizada = conversas_repo.buscar_conversa(conversa.id)
        assert atualizada.status == ConversationStatus.ESCALADA

    def test_nao_cria_terceiro_followup_ao_escalar(
        self, manager, lead_com_conversa_ativa, followups_repo
    ):
        lead, conversa = lead_com_conversa_ativa

        manager.processar_lead(lead)
        manager.processar_lead(lead)
        manager.processar_lead(lead)

        assert followups_repo.contar_tentativas(lead.id) == MAX_TENTATIVAS

    def test_ultima_tentativa_respondida_nao_faz_nada(
        self, manager, lead_com_conversa_ativa, followups_repo
    ):
        lead, conversa = lead_com_conversa_ativa
        primeiro = manager.processar_lead(lead)
        followups_repo.atualizar_status(
            primeiro.followup.id, FollowupStatus.RESPONDIDO
        )

        resultado = manager.processar_lead(lead)
        assert resultado.acao == "nenhuma"


class TestProcessarInativos:

    def test_processa_todos_os_leads_inativos(
        self, manager, lead_repo, conversas_repo, db_path
    ):
        lead1 = lead_repo.criar(Lead(nome="Lead 1"))
        conversas_repo.criar_conversa(Conversation(lead_id=lead1.id))
        lead2 = lead_repo.criar(Lead(nome="Lead 2"))
        conversas_repo.criar_conversa(Conversation(lead_id=lead2.id))

        # backdatar updated_at diretamente via SQL — LeadRepository não
        # expõe um jeito de forjar isso, e é exatamente o que
        # buscar_inativos() consulta
        antigo = (datetime.now() - timedelta(hours=48)).isoformat()
        with get_connection(db_path) as conn:
            conn.execute(
                "UPDATE leads SET updated_at = ? WHERE id IN (?, ?)",
                (antigo, lead1.id, lead2.id),
            )

        resultados = manager.processar_inativos(horas=24)

        assert len(resultados) == 2
        assert all(r.houve_envio for r in resultados)

    def test_lead_recente_nao_e_processado(
        self, manager, lead_repo, conversas_repo
    ):
        lead = lead_repo.criar(Lead(nome="Recente"))
        conversas_repo.criar_conversa(Conversation(lead_id=lead.id))

        resultados = manager.processar_inativos(horas=24)
        assert resultados == []


# ============================================================
# eventos_do_resultado
# ============================================================

class TestEventosDoResultado:

    def test_envio_gera_evento_followup_enviado(self):
        from src.core.enums import EventType

        followup = Followup(
            id=1, lead_id=1, conversation_id=1, tentativa=1, mensagem="oi"
        )
        resultado = ResultadoFollowup(
            lead_id=1, acao="enviado", followup=followup, tentativa=1
        )

        eventos = FollowupManager.eventos_do_resultado(resultado)

        assert len(eventos) == 1
        tipo, detalhes = eventos[0]
        assert tipo == EventType.FOLLOWUP_ENVIADO
        assert detalhes["followup_id"] == 1
        assert detalhes["tentativa"] == 1

    def test_escalada_gera_evento_lead_escalado(self):
        from src.core.enums import EventType

        resultado = ResultadoFollowup(lead_id=1, acao="escalado")
        eventos = FollowupManager.eventos_do_resultado(resultado)

        assert len(eventos) == 1
        tipo, _ = eventos[0]
        assert tipo == EventType.LEAD_ESCALADO

    def test_nenhuma_acao_nao_gera_evento(self):
        resultado = ResultadoFollowup(lead_id=1, acao="nenhuma")
        assert FollowupManager.eventos_do_resultado(resultado) == []