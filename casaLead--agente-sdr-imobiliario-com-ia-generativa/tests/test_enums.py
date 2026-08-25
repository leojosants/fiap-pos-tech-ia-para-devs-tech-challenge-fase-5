"""Testes das enumerações do domínio (src/core/enums.py).

Módulo 100% puro — sem banco, sem I/O, sem chave de API. Escopo destes
testes:

1. Comportamento de StrEnum: cada membro também é uma string comum,
   comparável e serializável sem conversão explícita — propriedade da
   qual o resto do sistema depende (persistência em SQLite, JSON de
   eventos, montagem de prompts por interpolação de string).
2. Valores exatos dos membros de cada enum — funciona como teste de
   regressão: uma renomeação acidental de um valor (ex.: "compra" →
   "COMPRA") quebraria dados já persistidos no banco sem que nenhum
   outro teste do projeto detectasse, já que a maioria dos outros
   testes constrói os enums a partir do próprio código-fonte, não a
   partir do valor de string esperado.
3. Ausência de membros duplicados ou colisão de valor dentro do mesmo
   enum.
"""

from enum import StrEnum

from src.core.enums import (
    AppointmentStatus,
    AppointmentType,
    ConversationStatus,
    EventType,
    FollowupStatus,
    Intent,
    InvestmentGoal,
    InvestorProfile,
    LeadStatus,
    LeadTemperature,
    MessageRole,
    Operation,
    PropertyType,
    Urgency,
    Zone,
)

TODOS_OS_ENUMS = [
    Intent,
    LeadStatus,
    LeadTemperature,
    Urgency,
    InvestorProfile,
    InvestmentGoal,
    PropertyType,
    Operation,
    Zone,
    MessageRole,
    ConversationStatus,
    AppointmentType,
    AppointmentStatus,
    FollowupStatus,
    EventType,
]


class TestComportamentoStrEnum:
    """Cada membro de cada enum precisa se comportar como string comum."""

    def test_todos_os_enums_herdam_de_strenum(self):
        for enum_cls in TODOS_OS_ENUMS:
            assert issubclass(enum_cls, StrEnum), (
                f"{enum_cls.__name__} não herda de StrEnum"
            )

    def test_membro_e_comparavel_diretamente_com_string_literal(self):
        assert Intent.COMPRA == "compra"
        assert LeadStatus.QUALIFICADO == "qualificado"
        assert EventType.LEAD_CRIADO == "lead_criado"

    def test_membro_e_serializavel_como_string_sem_conversao(self):
        # Simula o caso real de uso: gravação em SQLite / montagem de
        # prompt por f-string, sem chamar .value explicitamente.
        assert f"{Zone.SUL}" == "sul"
        assert str(Urgency.IMEDIATA) == "imediata"

    def test_membro_funciona_como_chave_de_dict_por_valor_de_string(self):
        # Padrão usado em vários módulos do projeto (ex.: _CORES_TEMPERATURA
        # em qualification_panel.py, _TIPOS_LEGIVEIS em scheduling_agent.py)
        mapa = {"quente": "🔥", "morno": "🌤️", "frio": "❄️"}
        assert mapa[LeadTemperature.QUENTE] == "🔥"


class TestIntegridadeDosMembros:
    """Nenhum enum deve ter membros duplicados ou colisão de valor."""

    def test_nenhum_enum_tem_valores_de_string_duplicados(self):
        for enum_cls in TODOS_OS_ENUMS:
            valores = [membro.value for membro in enum_cls]
            assert len(valores) == len(set(valores)), (
                f"{enum_cls.__name__} tem valores duplicados: {valores}"
            )

    def test_nenhum_enum_esta_vazio(self):
        for enum_cls in TODOS_OS_ENUMS:
            assert len(list(enum_cls)) > 0, f"{enum_cls.__name__} está vazio"


class TestValoresExatosPorEnum:
    """Regressão: valor de string exato de cada membro.

    Uma renomeação acidental aqui quebraria dados já persistidos
    (linhas gravadas no SQLite de produção) sem sinalização em nenhum
    outro teste do projeto.
    """

    def test_intent(self):
        assert {m.value for m in Intent} == {
            "compra", "aluguel", "investimento", "indefinida",
        }

    def test_lead_status(self):
        assert {m.value for m in LeadStatus} == {
            "novo", "em_qualificacao", "qualificado", "agendado",
            "encaminhado", "inativo", "perdido",
        }

    def test_lead_temperature(self):
        assert {m.value for m in LeadTemperature} == {
            "quente", "morno", "frio",
        }

    def test_urgency(self):
        assert {m.value for m in Urgency} == {
            "imediata", "curto_prazo", "medio_prazo", "sem_pressa",
            "nao_informada",
        }

    def test_investor_profile(self):
        assert {m.value for m in InvestorProfile} == {
            "conservador", "moderado", "arrojado", "nao_informado",
        }

    def test_investment_goal(self):
        assert {m.value for m in InvestmentGoal} == {
            "renda", "valorizacao", "diversificacao", "nao_informado",
        }

    def test_property_type(self):
        assert {m.value for m in PropertyType} == {
            "apartamento", "casa", "studio", "sala_comercial",
        }

    def test_operation(self):
        assert {m.value for m in Operation} == {"venda", "aluguel", "ambos"}

    def test_zone(self):
        assert {m.value for m in Zone} == {"sul", "oeste", "centro", "norte"}

    def test_message_role(self):
        assert {m.value for m in MessageRole} == {"lead", "agent", "system"}

    def test_conversation_status(self):
        assert {m.value for m in ConversationStatus} == {
            "ativa", "aguardando_lead", "encerrada", "escalada",
        }

    def test_appointment_type(self):
        assert {m.value for m in AppointmentType} == {
            "visita_imovel", "reuniao_online", "reuniao_presencial",
        }

    def test_appointment_status(self):
        assert {m.value for m in AppointmentStatus} == {
            "agendado", "confirmado", "realizado", "cancelado",
        }

    def test_followup_status(self):
        assert {m.value for m in FollowupStatus} == {
            "pendente", "enviado", "respondido", "sem_resposta",
        }

    def test_event_type(self):
        assert {m.value for m in EventType} == {
            "lead_criado", "conversa_iniciada", "mensagem_recebida",
            "mensagem_enviada", "intencao_identificada", "slot_preenchido",
            "imoveis_recomendados", "lead_classificado",
            "agendamento_criado", "followup_enviado", "resumo_gerado",
            "lead_escalado", "erro_llm",
        }