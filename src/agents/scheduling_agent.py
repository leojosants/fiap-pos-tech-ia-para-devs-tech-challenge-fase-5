"""Agente de agendamento.

Interpreta a disponibilidade que o lead já informou (texto livre,
capturado durante a qualificação) e, quando possível, formaliza um
compromisso concreto (Appointment). Quando o texto é vago demais para
virar uma data, gera sugestões de horário para o lead escolher.

A interpretação é feita por regras determinísticas (dia da semana,
"amanhã"/"hoje", período do dia), sem chamada a LLM — mesmo princípio
já aplicado no scoring de leads: o que pode ser determinístico não vai
ao modelo de linguagem. A cobertura é limitada por desenho; expressões
fora do vocabulário reconhecido resultam em sugestões, nunca em uma
data inventada. Ver docs/decisoes_tecnicas.md para o registro dessa
limitação.

Separação de pureza, no mesmo espírito de src/scoring/:
    _interpretar()      — puro, testável sem banco e sem relógio real
    _gerar_sugestoes()  — puro, idem
    agendar_se_possivel() — único ponto impuro: consulta o repositório
                            para não duplicar um compromisso já ativo
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from src.core.enums import AppointmentType, EventType
from src.core.models import Appointment, Lead
from src.persistence.appointment_repository import AppointmentRepository

# ============================================================
# Vocabulário reconhecido — puramente declarativo, fácil de auditar
# e de estender sem tocar na lógica de interpretação.
#
# As chaves ficam sem acento porque o texto é normalizado (minúsculo e
# sem diacríticos) antes de qualquer comparação — ver _normalizar().
# Isso evita duplicar cada termo em duas grafias e, mais importante,
# evita falso positivo por substring: comparar por PALAVRA INTEIRA
# (\b...\b) impede que "manha" seja "encontrado" dentro de "amanha".
# ============================================================

_DIAS_SEMANA = {
    "segunda-feira": 0, "segunda": 0,
    "terca-feira": 1, "terca": 1,
    "quarta-feira": 2, "quarta": 2,
    "quinta-feira": 3, "quinta": 3,
    "sexta-feira": 4, "sexta": 4,
    "sabado": 5,
    "domingo": 6,
}

# Nomes em português para exibição — não usa strftime("%A") de propósito,
# pois depende do locale configurado no sistema operacional (variável
# entre Windows local e o container do Streamlit Cloud).
_NOMES_DIAS_SEMANA = (
    "segunda-feira", "terça-feira", "quarta-feira",
    "quinta-feira", "sexta-feira", "sábado", "domingo",
)

_PERIODOS_DIA = {
    "manha": time(10, 0),
    "tarde": time(15, 0),
    "noite": time(18, 30),
}

_HORARIO_EXPLICITO = re.compile(r"\b(\d{1,2})h(\d{2})?\b")

_TIPOS_LEGIVEIS = {
    AppointmentType.VISITA_IMOVEL: "visita ao imóvel",
    AppointmentType.REUNIAO_ONLINE: "reunião online",
    AppointmentType.REUNIAO_PRESENCIAL: "reunião presencial",
}


def _normalizar(texto: str) -> str:
    """Minúsculo e sem acentos, para comparação robusta e sem duplicação
    de vocabulário (uma única grafia por termo nos dicionários acima)."""
    sem_acento = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sem_acento if not unicodedata.combining(c))


def _contem_palavra(texto_normalizado: str, termo: str) -> bool:
    """Casamento por palavra inteira — não por substring.

    Sem isso, "manha" seria "encontrado" dentro de "amanha", já que
    uma é substring literal da outra.
    """
    return re.search(rf"\b{re.escape(termo)}\b", texto_normalizado) is not None

_PERIODO_PADRAO = _PERIODOS_DIA["tarde"]

# Parâmetros da geração de sugestões
DURACAO_PADRAO_MINUTOS = 60
DIAS_UTEIS_SUGERIDOS = 2
HORARIOS_SUGERIDOS = (time(10, 0), time(15, 0))


def _formatar_data_legivel(momento: datetime) -> str:
    """Ex.: 'terça-feira, 26/08 às 15h00'."""
    nome_dia = _NOMES_DIAS_SEMANA[momento.weekday()]
    return f"{nome_dia}, {momento.strftime('%d/%m')} às {momento.strftime('%Hh%M')}"


# ============================================================
# Resultado
# ============================================================

@dataclass
class ResultadoAgendamento:
    """Registro do que o scheduling_agent decidiu neste turno."""

    appointment: Appointment | None = None
    ja_existia: bool = False
    sugestoes: list[str] = field(default_factory=list)

    @property
    def houve_agendamento(self) -> bool:
        """True somente quando um Appointment novo foi criado agora."""
        return self.appointment is not None and not self.ja_existia

    @property
    def tem_compromisso_ativo(self) -> bool:
        """True quando há um Appointment válido, novo ou pré-existente.

        Útil para o orquestrador decidir se deve informar ao LLM que já
        existe um horário confirmado — para a Sofia poder mencioná-lo
        sem violar a regra de não prometer horário por conta própria.
        """
        return self.appointment is not None


class SchedulingAgent:
    """Formaliza a disponibilidade do lead em um compromisso agendado."""

    def __init__(self, repositorio: AppointmentRepository | None = None) -> None:
        self._agendamentos = repositorio or AppointmentRepository()

    # --------------------------------------------------------
    # Interpretação determinística de texto livre (função pura)
    # --------------------------------------------------------

    @staticmethod
    def _proxima_ocorrencia(dia_semana: int, referencia: datetime) -> datetime:
        """Próxima data, a partir de amanhã, que cai nesse dia da semana.

        Nunca retorna o próprio dia de referência: se o lead diz "terça"
        numa terça-feira, o entendimento razoável é a próxima terça, não
        daqui a poucas horas.
        """
        dias_ate = (dia_semana - referencia.weekday()) % 7
        dias_ate = dias_ate if dias_ate > 0 else 7
        return referencia + timedelta(days=dias_ate)

    @classmethod
    def _interpretar(
        cls, texto: str, referencia: datetime
    ) -> datetime | None:
        """Tenta extrair uma data e hora concretas do texto livre.

        Retorna None quando nenhum padrão reconhecido está presente —
        quem chama deve então oferecer sugestões, nunca presumir uma data.
        """
        texto_normalizado = _normalizar(texto)

        data_base: datetime | None = None

        if _contem_palavra(texto_normalizado, "amanha"):
            data_base = referencia + timedelta(days=1)
        elif _contem_palavra(texto_normalizado, "hoje"):
            data_base = referencia
        else:
            for termo, indice in _DIAS_SEMANA.items():
                if _contem_palavra(texto_normalizado, termo):
                    data_base = cls._proxima_ocorrencia(indice, referencia)
                    break

        if data_base is None:
            return None

        horario: time | None = None
        casamento = _HORARIO_EXPLICITO.search(texto_normalizado)
        if casamento:
            hora = int(casamento.group(1))
            minuto = int(casamento.group(2) or 0)
            if 0 <= hora <= 23 and 0 <= minuto <= 59:
                horario = time(hora, minuto)

        if horario is None:
            for termo, hora_padrao in _PERIODOS_DIA.items():
                if _contem_palavra(texto_normalizado, termo):
                    horario = hora_padrao
                    break

        # Dia reconhecido, mas sem período nem horário explícito: ainda é
        # informação demais para descartar. Assume-se a tarde como padrão
        # neutro, mais compatível com agenda comercial.
        horario = horario or _PERIODO_PADRAO

        return datetime.combine(data_base.date(), horario)

    # --------------------------------------------------------
    # Sugestões, quando a interpretação falha (função pura)
    # --------------------------------------------------------

    @staticmethod
    def _proximos_dias_uteis(
        quantidade: int, referencia: datetime
    ) -> list[datetime]:
        dias: list[datetime] = []
        offset = 1
        while len(dias) < quantidade:
            candidato = referencia + timedelta(days=offset)
            if candidato.weekday() < 5:  # segunda a sexta
                dias.append(candidato)
            offset += 1
        return dias

    @classmethod
    def _gerar_sugestoes(cls, referencia: datetime) -> list[str]:
        """Sugestões determinísticas de horário, para o lead escolher.

        Regra fixa (próximos dias úteis, dois horários por dia) — não é
        integração de calendário real, é o mesmo espírito do cabeçalho
        determinístico dos cards de imóveis: previsível e auditável.
        """
        dias = cls._proximos_dias_uteis(DIAS_UTEIS_SUGERIDOS, referencia)
        return [
            _formatar_data_legivel(datetime.combine(dia.date(), horario))
            for dia in dias
            for horario in HORARIOS_SUGERIDOS
        ]

    # --------------------------------------------------------
    # Interface pública (único ponto impuro — acessa o repositório)
    # --------------------------------------------------------

    def agendar_se_possivel(
        self,
        lead: Lead,
        *,
        tipo: AppointmentType = AppointmentType.REUNIAO_ONLINE,
        property_id: int | None = None,
        referencia: datetime | None = None,
        texto_turno: str = "",
    ) -> ResultadoAgendamento:
        """Decide o que fazer com a disponibilidade do lead neste turno.

        Ordem de decisão:
          1. Já existe um compromisso ativo? Não duplica — devolve o
             existente (ja_existia=True).
          2. `lead.disponibilidade_reuniao` é interpretável? Cria o
             Appointment a partir dela.
          3. Não é interpretável (ou está vazia), mas a mensagem deste
             turno (`texto_turno`) é? Cria o Appointment a partir dela.
             Cobre o caso em que o lead respondeu a uma sugestão anterior
             ("terça está bom") — o QualificationAgent só grava
             disponibilidade_reuniao quando o slot ainda está vazio, então
             uma resposta a uma sugestão não reabriria esse campo sem
             este segundo caminho de interpretação.
          4. Nenhuma das duas é interpretável, mas havia algo informado?
             Gera sugestões.
          5. Nada informado em lugar nenhum? Não há o que fazer.

        `referencia` existe para tornar os testes determinísticos —
        sem ela, usa o momento real (datetime.now()).
        """
        if lead.id is None:
            raise ValueError("Lead sem id não pode ter agendamento criado.")

        referencia = referencia or datetime.now()

        existente = self._agendamentos.proximo_agendamento_do_lead(lead.id)
        if existente is not None:
            return ResultadoAgendamento(appointment=existente, ja_existia=True)

        origem_texto = ""
        momento: datetime | None = None

        if lead.disponibilidade_reuniao:
            momento = self._interpretar(lead.disponibilidade_reuniao, referencia)
            origem_texto = lead.disponibilidade_reuniao

        if momento is None and texto_turno:
            momento = self._interpretar(texto_turno, referencia)
            if momento is not None:
                origem_texto = texto_turno

        if momento is not None:
            appointment = Appointment(
                lead_id=lead.id,
                tipo=tipo,
                data_hora=momento,
                property_id=property_id,
                observacoes=(
                    "Disponibilidade original informada pelo lead: "
                    f'"{origem_texto}"'
                ),
            )
            criado = self._agendamentos.criar(appointment)
            return ResultadoAgendamento(appointment=criado)

        if lead.disponibilidade_reuniao or texto_turno:
            return ResultadoAgendamento(sugestoes=self._gerar_sugestoes(referencia))

        return ResultadoAgendamento()

    # --------------------------------------------------------
    # Formatação para o prompt do LLM
    # --------------------------------------------------------

    @staticmethod
    def formatar_para_prompt(resultado: ResultadoAgendamento) -> str:
        """Bloco de dados sobre o agendamento, para o prompt da Sofia.

        Só o dado — a instrução de como usá-lo (estrutura da mensagem,
        proibição de inventar horários além destes) fica em
        montar_prompt_sistema(), a mesma divisão já usada para
        imoveis_contexto.

        Devolve string vazia quando nada mudou NESTE turno: um
        agendamento pré-existente (ja_existia=True) não gera contexto
        novo, para a Sofia não repetir a confirmação a cada mensagem
        — decisão registrada na conversa sobre o Passo 3.
        """
        if resultado.houve_agendamento:
            ap = resultado.appointment
            tipo_legivel = _TIPOS_LEGIVEIS.get(ap.tipo, str(ap.tipo))
            return (
                "COMPROMISSO CONFIRMADO NESTE TURNO\n"
                f"Tipo: {tipo_legivel}\n"
                f"Quando: {_formatar_data_legivel(ap.data_hora)}"
            )

        if resultado.sugestoes:
            linhas = "\n".join(f"- {s}" for s in resultado.sugestoes)
            return f"HORÁRIOS SUGERIDOS NESTE TURNO\n{linhas}"

        return ""

    # --------------------------------------------------------
    # Eventos — mesmo contrato do qualification_agent
    # --------------------------------------------------------

    @staticmethod
    def eventos_do_resultado(
        resultado: ResultadoAgendamento,
    ) -> list[tuple[EventType, dict]]:
        """Traduz o resultado em eventos para o log de observabilidade."""
        if not resultado.houve_agendamento:
            return []

        ap = resultado.appointment
        return [(
            EventType.AGENDAMENTO_CRIADO,
            {
                "appointment_id": ap.id,
                "data_hora": ap.data_hora.isoformat(),
                "tipo": str(ap.tipo),
            },
        )]