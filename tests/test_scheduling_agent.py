"""Testes do agente de agendamento.

Dividido em dois blocos, espelhando a separação de pureza do próprio
agente (mesmo padrão de tests/test_scoring_rules.py vs
tests/test_scoring_builder.py):

    TestInterpretacao e TestSugestoes — funções puras, sem banco,
    com uma data de referência fixa para eliminar qualquer dependência
    do dia real em que os testes rodam.

    TestAgendarSePossivel — integração real com SQLite via tmp_path,
    validando o único ponto impuro do agente.
"""

from datetime import datetime

import pytest

from src.agents.scheduling_agent import SchedulingAgent, ResultadoAgendamento
from src.core.enums import AppointmentStatus, AppointmentType
from src.core.models import Appointment, Lead
from src.persistence.appointment_repository import AppointmentRepository
from src.persistence.database import create_schema
from src.persistence.lead_repository import LeadRepository

# Referência fixa: quarta-feira, 19/08/2026, 09h00 — escolhida para que
# "amanhã" caia numa quinta e o teste nunca dependa da data real de
# execução (essencial para CI e para rodar em qualquer fuso/dia).
REFERENCIA = datetime(2026, 8, 19, 9, 0, 0)
assert REFERENCIA.weekday() == 2  # confirma a premissa: quarta-feira


# ============================================================
# _interpretar — função pura
# ============================================================

class TestInterpretacao:

    def test_amanha_usa_periodo_padrao_tarde(self):
        momento = SchedulingAgent._interpretar("posso amanhã", REFERENCIA)
        assert momento == datetime(2026, 8, 20, 15, 0)

    def test_hoje_mantem_a_data_de_referencia(self):
        momento = SchedulingAgent._interpretar("hoje mesmo", REFERENCIA)
        assert momento.date() == REFERENCIA.date()

    def test_dia_da_semana_futuro_na_mesma_semana(self):
        # referência é quarta; "sexta" deve cair na sexta desta semana
        momento = SchedulingAgent._interpretar("pode ser sexta", REFERENCIA)
        assert momento.date() == datetime(2026, 8, 21).date()

    def test_dia_da_semana_igual_ao_de_hoje_pula_para_proxima_semana(self):
        # referência é quarta; "quarta" não pode ser hoje mesmo
        momento = SchedulingAgent._interpretar("prefiro quarta", REFERENCIA)
        assert momento.date() == datetime(2026, 8, 26).date()
        assert momento.date() != REFERENCIA.date()

    def test_dia_da_semana_ja_passado_na_semana_pula_para_proxima(self):
        # referência é quarta; "segunda" já passou nesta semana
        momento = SchedulingAgent._interpretar("segunda de manhã", REFERENCIA)
        assert momento.date() == datetime(2026, 8, 24).date()

    def test_periodo_manha_define_horario_padrao(self):
        momento = SchedulingAgent._interpretar("quinta de manhã", REFERENCIA)
        assert momento.time() == datetime(2026, 1, 1, 10, 0).time()

    def test_periodo_noite_define_horario_padrao(self):
        momento = SchedulingAgent._interpretar("sexta à noite", REFERENCIA)
        assert momento.time() == datetime(2026, 1, 1, 18, 30).time()

    def test_horario_explicito_prevalece_sobre_periodo(self):
        momento = SchedulingAgent._interpretar(
            "sexta de manhã, tipo 11h30", REFERENCIA
        )
        assert momento.time() == datetime(2026, 1, 1, 11, 30).time()

    def test_horario_explicito_sem_minutos(self):
        momento = SchedulingAgent._interpretar("quinta às 14h", REFERENCIA)
        assert momento.time() == datetime(2026, 1, 1, 14, 0).time()

    def test_dia_sem_periodo_nem_horario_usa_padrao_tarde(self):
        momento = SchedulingAgent._interpretar("quinta", REFERENCIA)
        assert momento.time() == datetime(2026, 1, 1, 15, 0).time()

    def test_texto_sem_nenhum_padrao_reconhecido_retorna_none(self):
        assert SchedulingAgent._interpretar("qualquer hora tá bom", REFERENCIA) is None
        assert SchedulingAgent._interpretar("depois te aviso", REFERENCIA) is None
        assert SchedulingAgent._interpretar("", REFERENCIA) is None

    def test_reconhece_variacao_sem_acento(self):
        momento = SchedulingAgent._interpretar("terca de tarde", REFERENCIA)
        assert momento.date() == datetime(2026, 8, 25).date()

    def test_case_insensitive(self):
        momento = SchedulingAgent._interpretar("AMANHÃ DE MANHÃ", REFERENCIA)
        assert momento is not None


# ============================================================
# _gerar_sugestoes — função pura
# ============================================================

class TestSugestoes:

    def test_gera_quatro_sugestoes_dois_dias_uteis_dois_horarios(self):
        sugestoes = SchedulingAgent._gerar_sugestoes(REFERENCIA)
        assert len(sugestoes) == 4

    def test_sugestoes_pulam_fim_de_semana(self):
        # referência: sexta-feira 21/08/2026 — os próximos dias úteis
        # devem pular sábado e domingo, indo para segunda e terça
        sexta = datetime(2026, 8, 21, 9, 0)
        assert sexta.weekday() == 4

        sugestoes = SchedulingAgent._gerar_sugestoes(sexta)
        assert all("sábado" not in s and "domingo" not in s for s in sugestoes)
        assert any("segunda-feira" in s for s in sugestoes)

    def test_sugestoes_sao_texto_legivel_em_portugues(self):
        sugestoes = SchedulingAgent._gerar_sugestoes(REFERENCIA)
        for s in sugestoes:
            assert "h" in s  # formato Hh MM
            assert "/" in s  # formato dd/mm


# ============================================================
# agendar_se_possivel — integração real com SQLite
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
def appointment_repo(db_path) -> AppointmentRepository:
    return AppointmentRepository(db_path)


@pytest.fixture
def agent(appointment_repo) -> SchedulingAgent:
    return SchedulingAgent(appointment_repo)


@pytest.fixture
def lead_persistido(lead_repo) -> Lead:
    return lead_repo.criar(Lead(nome="Lead de Teste"))


class TestAgendarSePossivel:

    def test_sem_disponibilidade_nao_faz_nada(self, agent, lead_persistido):
        resultado = agent.agendar_se_possivel(lead_persistido, referencia=REFERENCIA)

        assert resultado.appointment is None
        assert resultado.sugestoes == []
        assert not resultado.houve_agendamento

    def test_disponibilidade_interpretavel_cria_appointment(
        self, agent, lead_persistido, appointment_repo
    ):
        lead_persistido.disponibilidade_reuniao = "sexta de manhã"

        resultado = agent.agendar_se_possivel(lead_persistido, referencia=REFERENCIA)

        assert resultado.houve_agendamento
        assert resultado.appointment.id is not None
        assert resultado.appointment.status == AppointmentStatus.AGENDADO

        # confirma que foi persistido de verdade, não só devolvido em memória
        do_banco = appointment_repo.buscar_por_id(resultado.appointment.id)
        assert do_banco is not None

    def test_appointment_criado_registra_disponibilidade_original(
        self, agent, lead_persistido
    ):
        lead_persistido.disponibilidade_reuniao = "sexta de manhã"
        resultado = agent.agendar_se_possivel(lead_persistido, referencia=REFERENCIA)
        assert "sexta de manhã" in resultado.appointment.observacoes

    def test_disponibilidade_vaga_gera_sugestoes_sem_criar_appointment(
        self, agent, lead_persistido, appointment_repo
    ):
        lead_persistido.disponibilidade_reuniao = "qualquer hora tá bom"

        resultado = agent.agendar_se_possivel(lead_persistido, referencia=REFERENCIA)

        assert resultado.appointment is None
        assert len(resultado.sugestoes) == 4
        assert appointment_repo.listar_do_lead(lead_persistido.id) == []

    def test_nao_duplica_quando_ja_existe_agendamento_ativo(
        self, agent, lead_persistido, appointment_repo
    ):
        primeiro = appointment_repo.criar(
            Appointment(
                lead_id=lead_persistido.id,
                tipo=AppointmentType.REUNIAO_ONLINE,
                data_hora=datetime(2026, 8, 21, 15, 0),
            )
        )
        lead_persistido.disponibilidade_reuniao = "sexta de manhã"

        resultado = agent.agendar_se_possivel(lead_persistido, referencia=REFERENCIA)

        assert resultado.ja_existia
        assert resultado.appointment.id == primeiro.id
        assert not resultado.houve_agendamento
        assert len(appointment_repo.listar_do_lead(lead_persistido.id)) == 1

    def test_reconhece_agendamento_confirmado_como_ativo(
        self, agent, lead_persistido, appointment_repo
    ):
        confirmado = appointment_repo.criar(
            Appointment(
                lead_id=lead_persistido.id,
                tipo=AppointmentType.REUNIAO_ONLINE,
                data_hora=datetime(2026, 8, 21, 15, 0),
            )
        )
        appointment_repo.atualizar_status(confirmado.id, AppointmentStatus.CONFIRMADO)

        resultado = agent.agendar_se_possivel(lead_persistido, referencia=REFERENCIA)
        assert resultado.ja_existia

    def test_agendamento_cancelado_permite_novo_agendamento(
        self, agent, lead_persistido, appointment_repo
    ):
        cancelado = appointment_repo.criar(
            Appointment(
                lead_id=lead_persistido.id,
                tipo=AppointmentType.REUNIAO_ONLINE,
                data_hora=datetime(2026, 8, 21, 15, 0),
            )
        )
        appointment_repo.atualizar_status(cancelado.id, AppointmentStatus.CANCELADO)
        lead_persistido.disponibilidade_reuniao = "sexta de manhã"

        resultado = agent.agendar_se_possivel(lead_persistido, referencia=REFERENCIA)

        assert not resultado.ja_existia
        assert resultado.houve_agendamento

    def test_tipo_padrao_e_reuniao_online(self, agent, lead_persistido):
        lead_persistido.disponibilidade_reuniao = "sexta de manhã"
        resultado = agent.agendar_se_possivel(lead_persistido, referencia=REFERENCIA)
        assert resultado.appointment.tipo == AppointmentType.REUNIAO_ONLINE

    def test_tipo_pode_ser_sobrescrito_para_visita(self, agent, lead_persistido):
        lead_persistido.disponibilidade_reuniao = "sexta de manhã"
        resultado = agent.agendar_se_possivel(
            lead_persistido,
            tipo=AppointmentType.VISITA_IMOVEL,
            referencia=REFERENCIA,
        )
        assert resultado.appointment.tipo == AppointmentType.VISITA_IMOVEL

    def test_property_id_e_repassado_quando_informado(
        self, agent, lead_persistido, db_path
    ):
        # appointments.property_id é FK real para properties — o banco de
        # teste só tem o schema (sem seed), então é preciso um imóvel
        # de verdade para o teste ser válido, não um id arbitrário.
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO properties "
            "(id, codigo, titulo, tipo, operacao, zona, bairro) "
            "VALUES (42, 'CLTESTE', 'Imóvel de teste', 'apartamento', "
            "'venda', 'sul', 'Moema')"
        )
        conn.commit()
        conn.close()

        lead_persistido.disponibilidade_reuniao = "sexta de manhã"
        resultado = agent.agendar_se_possivel(
            lead_persistido, property_id=42, referencia=REFERENCIA
        )
        assert resultado.appointment.property_id == 42

    def test_lead_sem_id_levanta_erro(self, agent):
        lead_sem_id = Lead(nome="Fantasma", disponibilidade_reuniao="sexta")
        with pytest.raises(ValueError):
            agent.agendar_se_possivel(lead_sem_id, referencia=REFERENCIA)


class TestTextoTurnoComoSegundaTentativa:
    """Cobre o caso em que disponibilidade_reuniao já ficou congelada com
    um texto vago (o QualificationAgent só grava esse slot uma vez), e o
    lead responde a uma sugestão anterior na mensagem atual."""

    def test_disponibilidade_vaga_mas_texto_turno_interpretavel_cria_appointment(
        self, agent, lead_persistido
    ):
        lead_persistido.disponibilidade_reuniao = "qualquer hora tá bom"

        resultado = agent.agendar_se_possivel(
            lead_persistido,
            referencia=REFERENCIA,
            texto_turno="terça de manhã então",
        )

        assert resultado.houve_agendamento
        assert resultado.appointment.data_hora.date() == datetime(2026, 8, 25).date()

    def test_appointment_via_texto_turno_registra_o_texto_correto(
        self, agent, lead_persistido
    ):
        lead_persistido.disponibilidade_reuniao = "qualquer hora tá bom"

        resultado = agent.agendar_se_possivel(
            lead_persistido,
            referencia=REFERENCIA,
            texto_turno="terça de manhã então",
        )

        assert "terça de manhã então" in resultado.appointment.observacoes
        assert "qualquer hora" not in resultado.appointment.observacoes

    def test_disponibilidade_reuniao_interpretavel_nao_precisa_de_texto_turno(
        self, agent, lead_persistido
    ):
        """Quando disponibilidade_reuniao já é suficiente, texto_turno
        nem é consultado — evita reinterpretar a mesma informação duas
        vezes de fontes diferentes."""
        lead_persistido.disponibilidade_reuniao = "sexta de manhã"

        resultado = agent.agendar_se_possivel(
            lead_persistido,
            referencia=REFERENCIA,
            texto_turno="na verdade prefiro quarta",  # deve ser ignorado
        )

        assert resultado.appointment.data_hora.date() == datetime(2026, 8, 21).date()

    def test_ambos_vagos_gera_sugestoes(self, agent, lead_persistido):
        lead_persistido.disponibilidade_reuniao = "qualquer hora"

        resultado = agent.agendar_se_possivel(
            lead_persistido,
            referencia=REFERENCIA,
            texto_turno="tanto faz pra mim",
        )

        assert resultado.appointment is None
        assert len(resultado.sugestoes) == 4

    def test_sem_disponibilidade_nenhuma_mas_texto_turno_interpretavel_cria_appointment(
        self, agent, lead_persistido
    ):
        """Situação hipotética (na prática o QualificationAgent grava
        disponibilidade_reuniao no mesmo turno em que é dita), mas o
        método deve se comportar de forma previsível mesmo assim."""
        resultado = agent.agendar_se_possivel(
            lead_persistido,
            referencia=REFERENCIA,
            texto_turno="pode ser amanhã de tarde",
        )

        assert resultado.houve_agendamento

    def test_texto_turno_vazio_mantem_comportamento_anterior(
        self, agent, lead_persistido
    ):
        """Retrocompatibilidade: chamada sem texto_turno continua
        funcionando exatamente como antes desta mudança."""
        resultado = agent.agendar_se_possivel(lead_persistido, referencia=REFERENCIA)
        assert resultado.appointment is None
        assert resultado.sugestoes == []


# ============================================================
# eventos_do_resultado
# ============================================================

class TestEventosDoResultado:

    def test_sem_agendamento_nao_gera_evento(self):
        resultado = ResultadoAgendamento()
        assert SchedulingAgent.eventos_do_resultado(resultado) == []

    def test_agendamento_ja_existente_nao_gera_evento(self):
        ap = Appointment(
            id=1, lead_id=1, tipo=AppointmentType.REUNIAO_ONLINE,
            data_hora=REFERENCIA,
        )
        resultado = ResultadoAgendamento(appointment=ap, ja_existia=True)
        assert SchedulingAgent.eventos_do_resultado(resultado) == []

    def test_agendamento_novo_gera_evento_agendamento_criado(self):
        from src.core.enums import EventType

        ap = Appointment(
            id=7, lead_id=1, tipo=AppointmentType.VISITA_IMOVEL,
            data_hora=REFERENCIA,
        )
        resultado = ResultadoAgendamento(appointment=ap, ja_existia=False)

        eventos = SchedulingAgent.eventos_do_resultado(resultado)

        assert len(eventos) == 1
        tipo, detalhes = eventos[0]
        assert tipo == EventType.AGENDAMENTO_CRIADO
        assert detalhes["appointment_id"] == 7
        assert detalhes["tipo"] == "visita_imovel"


# ============================================================
# formatar_para_prompt
# ============================================================

class TestFormatarParaPrompt:

    def test_resultado_vazio_produz_string_vazia(self):
        resultado = ResultadoAgendamento()
        assert SchedulingAgent.formatar_para_prompt(resultado) == ""

    def test_agendamento_ja_existente_produz_string_vazia(self):
        """Não repete a confirmação a cada turno — só quando algo muda."""
        ap = Appointment(
            id=1, lead_id=1, tipo=AppointmentType.REUNIAO_ONLINE,
            data_hora=REFERENCIA,
        )
        resultado = ResultadoAgendamento(appointment=ap, ja_existia=True)
        assert SchedulingAgent.formatar_para_prompt(resultado) == ""

    def test_agendamento_novo_inclui_tipo_e_data(self):
        ap = Appointment(
            id=1, lead_id=1, tipo=AppointmentType.REUNIAO_ONLINE,
            data_hora=datetime(2026, 8, 21, 15, 0),
        )
        resultado = ResultadoAgendamento(appointment=ap, ja_existia=False)

        bloco = SchedulingAgent.formatar_para_prompt(resultado)

        assert "COMPROMISSO CONFIRMADO" in bloco
        assert "reunião online" in bloco
        assert "sexta-feira, 21/08 às 15h00" in bloco

    def test_agendamento_novo_tipo_visita_usa_rotulo_correto(self):
        ap = Appointment(
            id=1, lead_id=1, tipo=AppointmentType.VISITA_IMOVEL,
            data_hora=datetime(2026, 8, 21, 15, 0),
        )
        resultado = ResultadoAgendamento(appointment=ap, ja_existia=False)

        bloco = SchedulingAgent.formatar_para_prompt(resultado)
        assert "visita ao imóvel" in bloco

    def test_sugestoes_aparecem_uma_por_linha(self):
        resultado = ResultadoAgendamento(
            sugestoes=["terça-feira, 25/08 às 10h00", "terça-feira, 25/08 às 15h00"]
        )

        bloco = SchedulingAgent.formatar_para_prompt(resultado)

        assert "HORÁRIOS SUGERIDOS" in bloco
        assert "- terça-feira, 25/08 às 10h00" in bloco
        assert "- terça-feira, 25/08 às 15h00" in bloco

    def test_agendamento_confirmado_tem_prioridade_sobre_sugestoes(self):
        """Situação hipotética (não ocorre na prática, mas o método deve
        ser previsível mesmo assim): se ambos vierem preenchidos, o
        agendamento confirmado é o que importa."""
        ap = Appointment(
            id=1, lead_id=1, tipo=AppointmentType.REUNIAO_ONLINE,
            data_hora=REFERENCIA,
        )
        resultado = ResultadoAgendamento(
            appointment=ap, ja_existia=False, sugestoes=["algo"]
        )

        bloco = SchedulingAgent.formatar_para_prompt(resultado)
        assert "COMPROMISSO CONFIRMADO" in bloco
        assert "HORÁRIOS SUGERIDOS" not in bloco