"""Modelos de domínio do CasaLead.

Estruturas de dados puras, sem lógica de negócio e sem dependência
de banco. O mapeamento para SQLite é responsabilidade exclusiva da
camada src/persistence/.
"""

from dataclasses import dataclass, field
from datetime import datetime

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


def _now() -> datetime:
    """Timestamp padrão para criação de registros."""
    return datetime.now()


# ============================================================
# IMÓVEL
# ============================================================

@dataclass
class Property:
    """Imóvel da base simulada."""

    codigo: str
    titulo: str
    tipo: PropertyType
    operacao: Operation
    zona: Zone
    bairro: str
    endereco_aproximado: str

    # Valores (em reais); None quando a operação não se aplica
    preco_venda: float | None = None
    preco_aluguel: float | None = None
    condominio: float = 0.0
    iptu: float = 0.0

    # Atributos físicos
    quartos: int = 0
    suites: int = 0
    banheiros: int = 1
    vagas: int = 0
    area_util: float = 0.0
    andar: int | None = None
    ano_construcao: int = 2010

    # Atributos booleanos
    mobiliado: bool = False
    aceita_pet: bool = True

    # Conteúdo textual — base da busca semântica (RAG, Etapa 4)
    caracteristicas: list[str] = field(default_factory=list)
    descricao: str = ""

    # Indicadores para o cenário de investimento (enunciado 3.2)
    rentabilidade_estimada: float = 0.0      # % ao ano sobre o valor de venda
    potencial_valorizacao: float = 0.0       # % ao ano projetado
    perfil_investimento: InvestorProfile = InvestorProfile.MODERADO

    id: int | None = None

    @property
    def preco_m2(self) -> float | None:
        """Preço por metro quadrado, quando há valor de venda."""
        if self.preco_venda and self.area_util:
            return round(self.preco_venda / self.area_util, 2)
        return None

    @property
    def custo_mensal_total(self) -> float | None:
        """Aluguel somado a condomínio e IPTU rateado."""
        if self.preco_aluguel is None:
            return None
        return round(self.preco_aluguel + self.condominio + (self.iptu / 12), 2)

    def texto_para_busca(self) -> str:
        """Representação textual consolidada, usada pelo retriever."""
        partes = [
            self.titulo,
            f"{self.tipo} em {self.bairro}, zona {self.zona}",
            f"{self.quartos} quartos, {self.vagas} vagas, {self.area_util}m²",
            " ".join(self.caracteristicas),
            self.descricao,
        ]
        return " | ".join(p for p in partes if p)


# ============================================================
# LEAD
# ============================================================

@dataclass
class Lead:
    """Lead atendido pelo agente, com os dados coletados na qualificação."""

    nome: str = ""
    telefone: str = ""
    email: str = ""
    canal_origem: str = "site"

    # Estado no funil
    intent: Intent = Intent.INDEFINIDA
    status: LeadStatus = LeadStatus.NOVO
    temperature: LeadTemperature = LeadTemperature.FRIO
    score: int = 0

    # --- Slots de compra e aluguel (enunciado 3.1) ---
    zona_interesse: Zone | None = None
    bairros_interesse: list[str] = field(default_factory=list)
    tipo_imovel: PropertyType | None = None
    preco_min: float | None = None
    preco_max: float | None = None
    quartos_desejados: int | None = None
    vagas_desejadas: int | None = None
    preferencias: list[str] = field(default_factory=list)
    urgencia: Urgency = Urgency.NAO_INFORMADA
    disponibilidade_reuniao: str = ""

    # --- Slots de investimento (enunciado 3.2) ---
    perfil_investidor: InvestorProfile = InvestorProfile.NAO_INFORMADO
    ticket_disponivel: float | None = None
    objetivo_investimento: InvestmentGoal = InvestmentGoal.NAO_INFORMADO
    expectativa_retorno: float | None = None
    prazo_investimento: str = ""

    # Saída para o corretor
    resumo_corretor: str = ""

    id: int | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    # --- Controle de completude da qualificação ---

    SLOTS_COMPRA = (
        "zona_interesse",
        "preco_max",
        "quartos_desejados",
        "urgencia",
        "disponibilidade_reuniao",
    )

    SLOTS_INVESTIMENTO = (
        "perfil_investidor",
        "ticket_disponivel",
        "objetivo_investimento",
        "expectativa_retorno",
        "prazo_investimento",
    )

    def slots_relevantes(self) -> tuple[str, ...]:
        """Slots que importam de acordo com a intenção identificada."""
        if self.intent == Intent.INVESTIMENTO:
            return self.SLOTS_INVESTIMENTO
        return self.SLOTS_COMPRA

    def _slot_preenchido(self, nome_slot: str) -> bool:
        """Indica se um slot possui valor efetivamente informado."""
        valor = getattr(self, nome_slot, None)
        if valor is None or valor == "" or valor == []:
            return False
        if valor in (
            Urgency.NAO_INFORMADA,
            InvestorProfile.NAO_INFORMADO,
            InvestmentGoal.NAO_INFORMADO,
        ):
            return False
        return True

    def slots_status(self) -> dict[str, bool]:
        """Mapa slot → preenchido. Alimenta o painel lateral do chat."""
        return {s: self._slot_preenchido(s) for s in self.slots_relevantes()}

    def completude(self) -> float:
        """Percentual de qualificação concluída (0.0 a 1.0)."""
        status = self.slots_status()
        if not status:
            return 0.0
        return sum(status.values()) / len(status)


# ============================================================
# CONVERSA
# ============================================================

@dataclass
class Conversation:
    """Sessão de atendimento entre o agente e um lead."""

    lead_id: int
    status: ConversationStatus = ConversationStatus.ATIVA
    canal: str = "web"

    id: int | None = None
    started_at: datetime = field(default_factory=_now)
    last_activity_at: datetime = field(default_factory=_now)
    ended_at: datetime | None = None


@dataclass
class Message:
    """Turno individual do histórico conversacional."""

    conversation_id: int
    role: MessageRole
    content: str

    # Rastreabilidade da inferência (observabilidade)
    modelo_usado: str = ""
    latencia_ms: int = 0

    id: int | None = None
    created_at: datetime = field(default_factory=_now)


# ============================================================
# AGENDAMENTO E FOLLOW-UP
# ============================================================

@dataclass
class Appointment:
    """Visita ou reunião agendada pelo agente."""

    lead_id: int
    tipo: AppointmentType
    data_hora: datetime
    property_id: int | None = None
    corretor: str = ""
    observacoes: str = ""
    status: AppointmentStatus = AppointmentStatus.AGENDADO

    id: int | None = None
    created_at: datetime = field(default_factory=_now)


@dataclass
class Followup:
    """Tentativa de reengajamento de um lead inativo (enunciado 3.3)."""

    lead_id: int
    conversation_id: int
    tentativa: int
    mensagem: str
    status: FollowupStatus = FollowupStatus.PENDENTE
    motivo: str = ""

    id: int | None = None
    agendado_para: datetime = field(default_factory=_now)
    enviado_em: datetime | None = None


# ============================================================
# OBSERVABILIDADE
# ============================================================

@dataclass
class Event:
    """Registro estruturado de um acontecimento no sistema."""

    tipo: EventType
    lead_id: int | None = None
    conversation_id: int | None = None
    detalhes: dict = field(default_factory=dict)

    id: int | None = None
    created_at: datetime = field(default_factory=_now)