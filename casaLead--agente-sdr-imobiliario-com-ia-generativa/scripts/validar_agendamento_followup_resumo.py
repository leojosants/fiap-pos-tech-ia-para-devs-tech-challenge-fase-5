"""Validação manual da integração de agendamento, follow-up e resumo
no orquestrador (Etapa 6).

Não é um teste automatizado — é um script de inspeção pontual, mesmo
espírito do scripts/validar_scoring.py (Etapa 5): roda uma vez e
confere visualmente que os três módulos funcionam dentro do fluxo real
do Orchestrator, com GroqClient e demais colaboradores reais (respeita
o DEMO_MODE e a chave de API já configurados no seu .env). Usa um banco
separado, para não tocar em data/runtime/casalead.db.

Uso:
    uv run python -m scripts.validar_agendamento_followup_resumo
"""

from datetime import datetime, timedelta
from pathlib import Path

from src.agents.orchestrator import Orchestrator
from src.core.enums import EventType, Intent, LeadTemperature, Urgency, Zone
from src.persistence.database import bootstrap, get_connection

DB_TEMP = Path("data/runtime/validacao_agendamento_followup_resumo.db")


def _separador(titulo: str) -> None:
    print(f"\n{'=' * 60}\n{titulo}\n{'=' * 60}")


def _backdatar_lead(db_path: Path, lead_id: int, horas: int) -> None:
    """Simula inatividade — sem isso, buscar_inativos() nunca encontraria
    um lead criado agora mesmo. Mesma técnica usada nos testes
    automatizados (tests/test_orchestrator_summary_followup.py)."""
    antigo = (datetime.now() - timedelta(hours=horas)).isoformat()
    with get_connection(db_path) as conn:
        conn.execute("UPDATE leads SET updated_at = ? WHERE id = ?", (antigo, lead_id))


def validar_agendamento_interpretavel(orquestrador: Orchestrator) -> None:
    _separador("1. AGENDAMENTO — disponibilidade interpretável")

    lead, conversa, _ = orquestrador.iniciar_atendimento(nome="Teste Agendamento")
    lead.intent = Intent.COMPRA
    lead.zona_interesse = Zone.SUL
    lead.disponibilidade_reuniao = "sexta de manhã"

    resultado = orquestrador._agendar_se_possivel(
        lead, lead.id, conversa.id, "sexta de manhã"
    )

    print(f"Lead: id={lead.id}")
    print(f"houve_agendamento = {resultado.houve_agendamento}")
    if resultado.appointment:
        print(f"data_hora = {resultado.appointment.data_hora}")
        print(f"tipo      = {resultado.appointment.tipo}")
    print(f"lead.status = {lead.status}")

    assert resultado.houve_agendamento, "esperava um agendamento criado"
    assert lead.status.value == "agendado", "esperava lead.status == AGENDADO"
    print("OK — agendamento criado e status atualizado")


def validar_agendamento_vago_gera_sugestoes(orquestrador: Orchestrator) -> None:
    _separador("2. AGENDAMENTO — disponibilidade vaga (sugestões)")

    lead, conversa, _ = orquestrador.iniciar_atendimento(nome="Teste Sugestoes")
    lead.intent = Intent.COMPRA
    lead.disponibilidade_reuniao = "qualquer hora tá bom pra mim"

    resultado = orquestrador._agendar_se_possivel(
        lead, lead.id, conversa.id, "qualquer hora tá bom pra mim"
    )

    print(f"Lead: id={lead.id}")
    print(f"appointment criado? {resultado.appointment is not None}")
    print(f"sugestões geradas ({len(resultado.sugestoes)}):")
    for s in resultado.sugestoes:
        print(f"  - {s}")

    assert resultado.appointment is None, "não deveria ter criado agendamento"
    assert len(resultado.sugestoes) > 0, "esperava sugestões"
    print("OK — sugestões geradas, sem agendamento prematuro")


def validar_resumo_lead_quente(orquestrador: Orchestrator) -> None:
    _separador("3. RESUMO — lead fica quente")

    lead, conversa, _ = orquestrador.iniciar_atendimento(nome="Teste Resumo")
    lead.intent = Intent.COMPRA
    lead.zona_interesse = Zone.OESTE
    lead.preco_max = 700_000.0
    lead.quartos_desejados = 2
    lead.urgencia = Urgency.IMEDIATA
    lead.disponibilidade_reuniao = "amanhã de tarde"

    print(f"Lead: id={lead.id} | resumo_corretor (antes) = {lead.resumo_corretor!r}")

    resumo = orquestrador._resumir_se_necessario(
        lead, lead.id, conversa.id,
        temperatura_mudou=True,
        agendamento=__import__(
            "src.agents.scheduling_agent", fromlist=["ResultadoAgendamento"]
        ).ResultadoAgendamento(),
    )

    # Forçar quente diretamente, pois o cálculo real do score depende
    # de vários sinais (ver src/scoring/rules.py) — aqui o objetivo é
    # validar o GATILHO do resumo, não recalcular o score do zero.
    if resumo is None:
        lead.temperature = LeadTemperature.QUENTE
        resumo = orquestrador._resumir_se_necessario(
            lead, lead.id, conversa.id,
            temperatura_mudou=True,
            agendamento=__import__(
                "src.agents.scheduling_agent", fromlist=["ResultadoAgendamento"]
            ).ResultadoAgendamento(),
        )

    print(f"\norigem do resumo: {resumo.origem}")
    print(f"usou_llm: {resumo.usou_llm}")
    print(f"\nTexto do resumo:\n{'-' * 40}\n{resumo.texto}\n{'-' * 40}")

    assert resumo is not None, "esperava um resumo gerado"
    assert lead.resumo_corretor == resumo.texto
    print("OK — resumo gerado e persistido em lead.resumo_corretor")


def validar_followup_ate_escalar(orquestrador: Orchestrator, db_path: Path) -> None:
    _separador("4. FOLLOW-UP — ciclo completo até escalar")

    lead, conversa, _ = orquestrador.iniciar_atendimento(nome="Teste Followup")
    lead.intent = Intent.ALUGUEL
    lead.zona_interesse = Zone.NORTE
    orquestrador._leads.atualizar(lead)
    _backdatar_lead(db_path, lead.id, horas=48)

    for tentativa in (1, 2, 3):
        resultados = orquestrador.executar_verificacao_followup(horas=24)
        alvo = next((r for r in resultados if r.lead_id == lead.id), None)

        print(f"\nVerificação #{tentativa}:")
        if alvo is None:
            print("  nenhum resultado para este lead (verifique o filtro de horas)")
            continue
        print(f"  ação = {alvo.acao}")
        if alvo.followup:
            print(f"  mensagem = {alvo.followup.mensagem}")

        # após cada envio, "backdata" de novo — sem isso, o próprio
        # followup não teria alterado updated_at do lead, então ele
        # continuaria aparecendo como inativo naturalmente; mantido
        # aqui só para deixar explícito que a inatividade persiste
        # entre as três verificações.
        _backdatar_lead(db_path, lead.id, horas=48)

    lead_final = orquestrador._leads.buscar_por_id(lead.id)
    eventos = orquestrador._conversas.listar_eventos(lead_id=lead.id)
    escalados = [e for e in eventos if e.tipo == EventType.LEAD_ESCALADO]
    resumos = [e for e in eventos if e.tipo == EventType.RESUMO_GERADO]

    print(f"\nEventos LEAD_ESCALADO: {len(escalados)}")
    print(f"Eventos RESUMO_GERADO: {len(resumos)}")
    print(f"resumo_corretor do lead escalado: {lead_final.resumo_corretor[:80]}...")

    assert len(escalados) == 1, "esperava exatamente 1 escalada após 3 verificações"
    assert lead_final.resumo_corretor != "", "esperava resumo gerado na escalada"
    print("OK — 2 tentativas enviadas, 3ª escalou, resumo gerado automaticamente")


def main() -> None:
    if DB_TEMP.exists():
        DB_TEMP.unlink()

    bootstrap(DB_TEMP)
    orquestrador = Orchestrator(db_path=DB_TEMP)

    validar_agendamento_interpretavel(orquestrador)
    validar_agendamento_vago_gera_sugestoes(orquestrador)
    validar_resumo_lead_quente(orquestrador)
    validar_followup_ate_escalar(orquestrador, DB_TEMP)

    _separador("RESUMO FINAL")
    print("Todos os blocos passaram (assert não disparou). Banco de")
    print(f"inspeção em: {DB_TEMP}")
    print("Abra com um visualizador SQLite para conferir as tabelas")
    print("appointments, followups e o campo resumo_corretor em leads.")


if __name__ == "__main__":
    main()