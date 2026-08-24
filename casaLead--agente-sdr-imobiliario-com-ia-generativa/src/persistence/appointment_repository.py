"""Repositório de agendamentos.

Encapsula todo o acesso SQL à tabela appointments, expondo aos demais
módulos apenas objetos de domínio (Appointment).

Diferente do lead_repository, não usa mapeamento genérico por lista de
colunas: com poucos campos e nenhum campo JSON, a conversão explícita
é mais simples de ler e de manter.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from src.core.enums import AppointmentStatus, AppointmentType
from src.core.models import Appointment
from src.persistence.database import get_connection


class AppointmentRepository:
    """Acesso à agenda de visitas e reuniões."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path

    # --------------------------------------------------------
    # Mapeamento
    # --------------------------------------------------------

    @staticmethod
    def _to_domain(row: sqlite3.Row) -> Appointment:
        """Converte uma linha do banco em objeto de domínio."""
        return Appointment(
            id=row["id"],
            lead_id=row["lead_id"],
            property_id=row["property_id"],
            tipo=AppointmentType(row["tipo"]),
            data_hora=datetime.fromisoformat(row["data_hora"]),
            corretor=row["corretor"],
            observacoes=row["observacoes"],
            status=AppointmentStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # --------------------------------------------------------
    # Escrita
    # --------------------------------------------------------

    def criar(self, appointment: Appointment) -> Appointment:
        """Insere um novo agendamento e devolve o objeto com o id atribuído."""
        agora = datetime.now()
        appointment.created_at = agora

        with get_connection(self._db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO appointments
                    (lead_id, property_id, tipo, data_hora, corretor,
                     observacoes, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    appointment.lead_id,
                    appointment.property_id,
                    str(appointment.tipo),
                    appointment.data_hora.isoformat(),
                    appointment.corretor,
                    appointment.observacoes,
                    str(appointment.status),
                    agora.isoformat(),
                ),
            )
            appointment.id = cursor.lastrowid

        return appointment

    def atualizar_status(
        self, appointment_id: int, status: AppointmentStatus
    ) -> None:
        """Altera o status de um agendamento (confirmado/realizado/cancelado).

        Único campo que muda depois de criado no fluxo atual da POC —
        por isso um método dedicado, em vez de um atualizar() genérico
        que reescreveria data_hora/observacoes sem necessidade.
        """
        with get_connection(self._db_path) as conn:
            conn.execute(
                "UPDATE appointments SET status = ? WHERE id = ?",
                (str(status), appointment_id),
            )

    # --------------------------------------------------------
    # Leitura
    # --------------------------------------------------------

    def buscar_por_id(self, appointment_id: int) -> Appointment | None:
        with get_connection(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM appointments WHERE id = ?", (appointment_id,)
            ).fetchone()
        return self._to_domain(row) if row else None

    def listar_do_lead(
        self, lead_id: int, *, apenas_futuros: bool = False
    ) -> list[Appointment]:
        """Agendamentos de um lead, do mais antigo para o mais recente."""
        sql = "SELECT * FROM appointments WHERE lead_id = ?"
        params: list[object] = [lead_id]

        if apenas_futuros:
            sql += " AND data_hora >= ?"
            params.append(datetime.now().isoformat())

        sql += " ORDER BY data_hora"

        with get_connection(self._db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._to_domain(r) for r in rows]

    def proximo_agendamento_do_lead(self, lead_id: int) -> Appointment | None:
        """Compromisso futuro mais próximo, ainda ativo (agendado/confirmado).

        Usado pelo scheduling_agent para evitar criar um novo agendamento
        a cada turno em que o lead volta a mencionar "quero visitar" —
        se já existe um ativo, o agente confirma o existente em vez de
        duplicar.
        """
        with get_connection(self._db_path) as conn:
            row = conn.execute(
                """
                SELECT * FROM appointments
                WHERE lead_id = ?
                  AND status IN ('agendado', 'confirmado')
                  AND data_hora >= ?
                ORDER BY data_hora
                LIMIT 1
                """,
                (lead_id, datetime.now().isoformat()),
            ).fetchone()
        return self._to_domain(row) if row else None

    def listar_proximos(
        self,
        *,
        dias: int = 7,
        status: AppointmentStatus | None = None,
        limite: int = 50,
    ) -> list[Appointment]:
        """Agendamentos futuros de todos os leads, para visão do corretor.

        Insumo previsto para a Etapa 7 (page_broker) — consulta que não
        pertence ao lead_repository porque é sobre agenda, não sobre o
        estado do lead.
        """
        clausulas = ["data_hora >= ?", "data_hora <= ?"]
        agora = datetime.now()
        limite_data = agora + timedelta(days=dias)
        params: list[object] = [agora.isoformat(), limite_data.isoformat()]

        if status is not None:
            clausulas.append("status = ?")
            params.append(str(status))

        where = " AND ".join(clausulas)
        params.append(limite)

        with get_connection(self._db_path) as conn:
            rows = conn.execute(
                f"SELECT * FROM appointments WHERE {where} "
                f"ORDER BY data_hora LIMIT ?",
                params,
            ).fetchall()
        return [self._to_domain(r) for r in rows]

    # --------------------------------------------------------
    # Agregações — insumo do dashboard
    # --------------------------------------------------------

    def estatisticas(self) -> dict:
        """Contagem de agendamentos por status."""
        with get_connection(self._db_path) as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) c FROM appointments GROUP BY status"
            ).fetchall()
            total = conn.execute(
                "SELECT COUNT(*) FROM appointments"
            ).fetchone()[0]

        return {
            "total": total,
            "por_status": {r["status"]: r["c"] for r in rows},
        }