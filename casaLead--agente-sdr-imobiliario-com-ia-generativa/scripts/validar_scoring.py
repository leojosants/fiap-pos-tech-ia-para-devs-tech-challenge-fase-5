"""Validação manual da integração do scoring no orquestrador (Etapa 5).

Não é um teste automatizado — é um script de inspeção pontual, para
rodar uma vez e conferir visualmente que o score e a temperatura são
calculados e persistidos corretamente dentro do fluxo real do
Orchestrator. Usa um banco separado, para não tocar em
data/runtime/casalead.db.

Uso:
    uv run python -m scripts.validar_scoring
"""

from pathlib import Path

from src.agents.orchestrator import Orchestrator
from src.core.enums import EventType, Intent, Urgency, Zone
from src.persistence.database import bootstrap

DB_TEMP = Path("data/runtime/validacao_scoring.db")


def main() -> None:
    if DB_TEMP.exists():
        DB_TEMP.unlink()

    bootstrap(DB_TEMP)  

    orquestrador = Orchestrator(db_path=DB_TEMP)

    lead, conversa, saudacao = orquestrador.iniciar_atendimento(nome="Teste Scoring")
    print(f"Lead criado: id={lead.id} | score inicial={lead.score} | temperatura={lead.temperature}")

    # Preenchendo os slots diretamente, para isolar este teste do
    # comportamento do agente de qualificação (já coberto por seus
    # próprios testes).
    lead.intent = Intent.COMPRA
    lead.zona_interesse = Zone.SUL
    lead.preco_max = 800_000
    lead.quartos_desejados = 2
    lead.urgencia = Urgency.IMEDIATA
    lead.disponibilidade_reuniao = "sábado de manhã"

    # Mesma sequência usada dentro de processar_mensagem a cada turno real.
    orquestrador._atualizar_score(lead, lead.id, conversa.id)
    orquestrador._leads.atualizar(lead)

    print("\nApós qualificação completa:")
    print(f"  score       = {lead.score}")
    print(f"  temperature = {lead.temperature}")

    eventos = orquestrador._conversas.listar_eventos(lead_id=lead.id)
    classificacoes = [e for e in eventos if e.tipo == EventType.LEAD_CLASSIFICADO]
    print(f"\nEventos LEAD_CLASSIFICADO registrados: {len(classificacoes)}")
    for e in classificacoes:
        print(f"  {e.detalhes}")


if __name__ == "__main__":
    main()