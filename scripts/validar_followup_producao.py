"""Validação manual de follow-up contra o banco de produção local.

Diferente de scripts/validar_agendamento_followup_resumo.py (banco
isolado, temporário), este roda contra data/runtime/casalead.db — o
mesmo banco que a interface Streamlit usa. Localiza um lead real
(criado através de uma conversa na tela), simula inatividade
retroagindo seu updated_at, e executa a verificação de follow-up de
verdade — Orchestrator real, GroqClient real.

Rodar mais de uma vez para o mesmo lead avança as tentativas (1ª envio,
2º envio, 3ª escala) — mesmo comportamento do turno real.

Uso:
    uv run python -m scripts.validar_followup_producao "Nome do Lead"
    uv run python -m scripts.validar_followup_producao --id 7
"""

import sys
from datetime import datetime, timedelta

from src.agents.orchestrator import Orchestrator
from src.persistence.database import get_connection, get_db_path
from src.persistence.lead_repository import LeadRepository


def _separador(titulo: str) -> None:
    print(f"\n{'=' * 60}\n{titulo}\n{'=' * 60}")


def _localizar_lead(leads: LeadRepository, argumento: str):
    if argumento == "--id":
        raise ValueError("Uso: --id <numero>, ex.: --id 7")

    if argumento.isdigit():
        return leads.buscar_por_id(int(argumento))

    candidatos = [
        l for l in leads.listar(limite=200) if argumento.lower() in (l.nome or "").lower()
    ]
    if not candidatos:
        return None
    return max(candidatos, key=lambda l: l.id)  # o mais recente com esse nome


def main() -> None:
    if len(sys.argv) < 2:
        print('Uso: uv run python -m scripts.validar_followup_producao "Nome" (ou --id N)')
        sys.exit(1)

    args = sys.argv[1:]
    if args[0] == "--id":
        busca = args[1]
    else:
        busca = args[0]

    db_path = get_db_path()
    print(f"Banco: {db_path}")

    leads = LeadRepository(db_path)
    lead = _localizar_lead(leads, busca)

    if lead is None:
        print(f"Nenhum lead encontrado para {busca!r}. Confira o nome/id e tente de novo.")
        sys.exit(1)

    print(f"Lead: id={lead.id} | nome={lead.nome!r} | status={lead.status} | "
          f"intent={lead.intent}")

    _separador("Simulando inatividade (updated_at retrocedido 48h)")
    antigo = (datetime.now() - timedelta(hours=48)).isoformat()
    with get_connection(db_path) as conn:
        conn.execute("UPDATE leads SET updated_at = ? WHERE id = ?", (antigo, lead.id))
    print("OK.")

    _separador("Executando verificação de follow-up (Orchestrator real)")
    orquestrador = Orchestrator(db_path=db_path)
    resultados = orquestrador.executar_verificacao_followup(horas=24)

    alvo = next((r for r in resultados if r.lead_id == lead.id), None)

    if alvo is None:
        print(
            "Este lead NÃO apareceu no resultado. Causas prováveis:\n"
            "  - a conversa foi encerrada/escalada (sem conversa ativa)\n"
            "  - a última tentativa de follow-up já foi respondida\n"
            f"Total de leads processados nesta rodada: {len(resultados)}"
        )
    else:
        print(f"Ação tomada para este lead: {alvo.acao}")
        if alvo.followup:
            print(f"Tentativa número: {alvo.tentativa}")
            print(f"Mensagem gerada:\n  {alvo.followup.mensagem}")

    _separador("Conferindo no banco")
    eventos = orquestrador._conversas.listar_eventos(lead_id=lead.id, limite=10)
    for e in eventos:
        print(f"  [{e.created_at}] {e.tipo} — {e.detalhes}")

    lead_atualizado = leads.buscar_por_id(lead.id)
    print(f"\nStatus final do lead: {lead_atualizado.status}")
    resumo = lead_atualizado.resumo_corretor
    print(f"Resumo do corretor: {resumo[:200] + '...' if resumo else '(vazio)'}")


if __name__ == "__main__":
    main()