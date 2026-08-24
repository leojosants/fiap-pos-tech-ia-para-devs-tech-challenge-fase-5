"""Agregação de métricas para observabilidade (Etapa 7).

Reúne, num único ponto, as estatísticas que já existem espalhadas pelos
repositórios (LeadRepository, ConversationRepository,
AppointmentRepository, FollowupRepository) e pelo GroqClient — sem
reimplementar nenhuma delas.

Este módulo não acessa o banco diretamente: cada função recebe o
repositório já instanciado, seguindo o mesmo princípio de
scoring/builder.py (que injeta os repositórios em vez de acessá-los
por conta própria). Isso mantém as funções testáveis com SQLite real
via tmp_path, sem precisar de rede nem de um Orchestrator completo.
"""

from src.core.enums import Intent
from src.core.models import Lead
from src.llm.groq_client import GroqClient
from src.persistence.appointment_repository import AppointmentRepository
from src.persistence.conversation_repository import ConversationRepository
from src.persistence.followup_repository import FollowupRepository
from src.persistence.lead_repository import LeadRepository

# Cobre a escala de uma POC de demonstração (dezenas de leads); um
# volume real de produção pediria paginação, fora do escopo aqui.
LIMITE_LEADS_DASHBOARD = 500


def leads_com_interacao(leads: list[Lead]) -> list[Lead]:
    """Filtra leads que tiveram alguma interação real.

    Um lead é criado assim que a conversa é aberta (ver
    Orchestrator.iniciar_atendimento) — se o usuário fecha a aba sem
    digitar nada, o registro fica vazio no banco (limitação 17 de
    docs/decisoes_tecnicas.md). Esses registros poluem o funil do
    dashboard sem representar um lead de verdade.

    Reaproveita Lead.completude() e Lead.intent em vez de reimplementar
    o critério em SQL — mesma decisão já firmada para o scoring
    (seção 6c de docs/decisoes_tecnicas.md): a regra de completude vive
    em um só lugar, no domínio.
    """
    return [
        lead
        for lead in leads
        if lead.completude() > 0 or lead.intent != Intent.INDEFINIDA
    ]


def funil_de_leads(
    leads_repo: LeadRepository, *, apenas_com_interacao: bool = True
) -> dict:
    """Funil de leads (contagem por status, temperatura e intenção).

    Devolve tanto o total considerado quanto o total bruto, para que a
    interface possa exibir "N leads ocultos (sem interação)" em vez de
    filtrar silenciosamente.
    """
    todos = leads_repo.listar(ordenar_por="score", limite=LIMITE_LEADS_DASHBOARD)
    total_bruto = len(todos)
    considerados = leads_com_interacao(todos) if apenas_com_interacao else todos

    por_status: dict[str, int] = {}
    por_temperatura: dict[str, int] = {}
    por_intencao: dict[str, int] = {}
    soma_score = 0

    for lead in considerados:
        por_status[str(lead.status)] = por_status.get(str(lead.status), 0) + 1
        por_temperatura[str(lead.temperature)] = (
            por_temperatura.get(str(lead.temperature), 0) + 1
        )
        por_intencao[str(lead.intent)] = por_intencao.get(str(lead.intent), 0) + 1
        soma_score += lead.score

    total = len(considerados)

    return {
        "total": total,
        "total_bruto": total_bruto,
        "leads_vazios_ocultos": total_bruto - total,
        "por_status": por_status,
        "por_temperatura": por_temperatura,
        "por_intencao": por_intencao,
        "score_medio": round(soma_score / total, 1) if total else 0.0,
    }


def coletar(
    *,
    leads_repo: LeadRepository,
    conversas_repo: ConversationRepository,
    agendamentos_repo: AppointmentRepository,
    followups_repo: FollowupRepository,
    cliente: GroqClient,
    apenas_com_interacao: bool = True,
) -> dict:
    """Painel completo de observabilidade: funil, eventos, agenda, uso de LLM.

    Ponto único que o dashboard consulta — a interface não sabe de onde
    vem cada número, só que ele está aqui.
    """
    return {
        "funil": funil_de_leads(
            leads_repo, apenas_com_interacao=apenas_com_interacao
        ),
        "eventos": conversas_repo.metricas_de_eventos(),
        "agendamentos": agendamentos_repo.estatisticas(),
        "followups": followups_repo.estatisticas(),
        "uso_llm": cliente.stats.resumo(),
    }