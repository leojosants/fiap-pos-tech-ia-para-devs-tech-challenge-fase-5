"""Enumerações do domínio CasaLead.

Centraliza todos os valores categóricos do sistema. O uso de StrEnum
(Python 3.11+) garante que cada membro seja também uma string comum,
permitindo gravação direta no SQLite e serialização em JSON sem
conversão explícita.
"""

from enum import StrEnum


# ============================================================
# LEAD — intenção, ciclo de vida e priorização
# ============================================================

class Intent(StrEnum):
    """Intenção principal identificada na conversa com o lead."""

    COMPRA = "compra"
    ALUGUEL = "aluguel"
    INVESTIMENTO = "investimento"
    INDEFINIDA = "indefinida"


class LeadStatus(StrEnum):
    """Estágio do lead no funil de atendimento."""

    NOVO = "novo"
    EM_QUALIFICACAO = "em_qualificacao"
    QUALIFICADO = "qualificado"
    AGENDADO = "agendado"
    ENCAMINHADO = "encaminhado"
    INATIVO = "inativo"
    PERDIDO = "perdido"


class LeadTemperature(StrEnum):
    """Classificação de prioridade do lead para o corretor."""

    QUENTE = "quente"
    MORNO = "morno"
    FRIO = "frio"


class Urgency(StrEnum):
    """Prazo declarado pelo lead para concretizar a operação."""

    IMEDIATA = "imediata"
    CURTO_PRAZO = "curto_prazo"
    MEDIO_PRAZO = "medio_prazo"
    SEM_PRESSA = "sem_pressa"
    NAO_INFORMADA = "nao_informada"


# ============================================================
# INVESTIMENTO — cenário obrigatório 3.2 do enunciado
# ============================================================

class InvestorProfile(StrEnum):
    """Perfil de risco declarado pelo investidor."""

    CONSERVADOR = "conservador"
    MODERADO = "moderado"
    ARROJADO = "arrojado"
    NAO_INFORMADO = "nao_informado"


class InvestmentGoal(StrEnum):
    """Objetivo principal do investimento imobiliário."""

    RENDA = "renda"
    VALORIZACAO = "valorizacao"
    DIVERSIFICACAO = "diversificacao"
    NAO_INFORMADO = "nao_informado"


# ============================================================
# IMÓVEL
# ============================================================

class PropertyType(StrEnum):
    """Tipo do imóvel."""

    APARTAMENTO = "apartamento"
    CASA = "casa"
    STUDIO = "studio"
    SALA_COMERCIAL = "sala_comercial"


class Operation(StrEnum):
    """Operação disponível para o imóvel."""

    VENDA = "venda"
    ALUGUEL = "aluguel"
    AMBOS = "ambos"


class Zone(StrEnum):
    """Zona da cidade de São Paulo."""

    SUL = "sul"
    OESTE = "oeste"
    CENTRO = "centro"
    NORTE = "norte"


# ============================================================
# CONVERSA
# ============================================================

class MessageRole(StrEnum):
    """Autor de uma mensagem no histórico da conversa."""

    LEAD = "lead"
    AGENT = "agent"
    SYSTEM = "system"


class ConversationStatus(StrEnum):
    """Situação da sessão de atendimento."""

    ATIVA = "ativa"
    AGUARDANDO_LEAD = "aguardando_lead"
    ENCERRADA = "encerrada"
    ESCALADA = "escalada"


# ============================================================
# AGENDAMENTO E FOLLOW-UP
# ============================================================

class AppointmentType(StrEnum):
    """Modalidade do compromisso agendado."""

    VISITA_IMOVEL = "visita_imovel"
    REUNIAO_ONLINE = "reuniao_online"
    REUNIAO_PRESENCIAL = "reuniao_presencial"


class AppointmentStatus(StrEnum):
    """Situação do compromisso."""

    AGENDADO = "agendado"
    CONFIRMADO = "confirmado"
    REALIZADO = "realizado"
    CANCELADO = "cancelado"


class FollowupStatus(StrEnum):
    """Resultado de uma tentativa de reengajamento."""

    PENDENTE = "pendente"
    ENVIADO = "enviado"
    RESPONDIDO = "respondido"
    SEM_RESPOSTA = "sem_resposta"


# ============================================================
# OBSERVABILIDADE
# ============================================================

class EventType(StrEnum):
    """Eventos rastreados para métricas e auditoria."""

    LEAD_CRIADO = "lead_criado"
    CONVERSA_INICIADA = "conversa_iniciada"
    MENSAGEM_RECEBIDA = "mensagem_recebida"
    MENSAGEM_ENVIADA = "mensagem_enviada"
    INTENCAO_IDENTIFICADA = "intencao_identificada"
    SLOT_PREENCHIDO = "slot_preenchido"
    IMOVEIS_RECOMENDADOS = "imoveis_recomendados"
    LEAD_CLASSIFICADO = "lead_classificado"
    AGENDAMENTO_CRIADO = "agendamento_criado"
    FOLLOWUP_ENVIADO = "followup_enviado"
    RESUMO_GERADO = "resumo_gerado"
    LEAD_ESCALADO = "lead_escalado"
    ERRO_LLM = "erro_llm"