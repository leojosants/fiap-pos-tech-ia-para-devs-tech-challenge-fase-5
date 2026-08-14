"""Repositório de imóveis.

Encapsula todo o acesso SQL à tabela properties, expondo aos demais
módulos apenas objetos de domínio (Property) e uma interface de busca
por critérios de negócio.

Nenhuma camada acima desta conhece SQL ou a estrutura das tabelas.
"""

import json
import sqlite3
from pathlib import Path

from src.core.enums import InvestorProfile, Operation, PropertyType, Zone
from src.core.models import Property
from src.persistence.database import get_connection


class PropertyRepository:
    """Acesso à base simulada de imóveis."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path

    # --------------------------------------------------------
    # Mapeamento
    # --------------------------------------------------------

    @staticmethod
    def _to_domain(row: sqlite3.Row) -> Property:
        """Converte uma linha do banco em objeto de domínio."""
        return Property(
            id=row["id"],
            codigo=row["codigo"],
            titulo=row["titulo"],
            tipo=PropertyType(row["tipo"]),
            operacao=Operation(row["operacao"]),
            zona=Zone(row["zona"]),
            bairro=row["bairro"],
            endereco_aproximado=row["endereco_aproximado"],
            preco_venda=row["preco_venda"],
            preco_aluguel=row["preco_aluguel"],
            condominio=row["condominio"],
            iptu=row["iptu"],
            quartos=row["quartos"],
            suites=row["suites"],
            banheiros=row["banheiros"],
            vagas=row["vagas"],
            area_util=row["area_util"],
            andar=row["andar"],
            ano_construcao=row["ano_construcao"],
            mobiliado=bool(row["mobiliado"]),
            aceita_pet=bool(row["aceita_pet"]),
            caracteristicas=json.loads(row["caracteristicas"]),
            descricao=row["descricao"],
            rentabilidade_estimada=row["rentabilidade_estimada"],
            potencial_valorizacao=row["potencial_valorizacao"],
            perfil_investimento=InvestorProfile(row["perfil_investimento"]),
        )

    # --------------------------------------------------------
    # Consultas pontuais
    # --------------------------------------------------------

    def listar_todos(self) -> list[Property]:
        """Retorna a base completa. Usado pelo indexador do RAG."""
        with get_connection(self._db_path) as conn:
            rows = conn.execute("SELECT * FROM properties ORDER BY id").fetchall()
        return [self._to_domain(r) for r in rows]

    def buscar_por_id(self, property_id: int) -> Property | None:
        """Retorna um imóvel pelo identificador interno."""
        with get_connection(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM properties WHERE id = ?", (property_id,)
            ).fetchone()
        return self._to_domain(row) if row else None

    def buscar_por_codigo(self, codigo: str) -> Property | None:
        """Retorna um imóvel pelo código público (ex.: CL0001)."""
        with get_connection(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM properties WHERE codigo = ?", (codigo,)
            ).fetchone()
        return self._to_domain(row) if row else None

    def contar(self) -> int:
        """Total de imóveis na base."""
        with get_connection(self._db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM properties").fetchone()[0]

    # --------------------------------------------------------
    # Busca por critérios
    # --------------------------------------------------------

    def buscar(
        self,
        *,
        zona: Zone | None = None,
        bairros: list[str] | None = None,
        tipo: PropertyType | None = None,
        operacao: Operation | None = None,
        preco_min: float | None = None,
        preco_max: float | None = None,
        quartos_min: int | None = None,
        vagas_min: int | None = None,
        aceita_pet: bool | None = None,
        mobiliado: bool | None = None,
        limite: int = 20,
    ) -> list[Property]:
        """Busca imóveis por critérios estruturados.

        Todos os filtros são opcionais e combinam-se por AND. Ausentes,
        não restringem o resultado.

        A coluna de preço considerada depende da operação: aluguel filtra
        por preco_aluguel; os demais casos, por preco_venda.
        """
        clausulas: list[str] = []
        params: list[object] = []

        if zona is not None:
            clausulas.append("zona = ?")
            params.append(str(zona))

        if bairros:
            marcadores = ",".join("?" for _ in bairros)
            clausulas.append(f"bairro IN ({marcadores})")
            params.extend(bairros)

        if tipo is not None:
            clausulas.append("tipo = ?")
            params.append(str(tipo))

        if operacao is not None:
            # 'ambos' atende tanto quem busca venda quanto aluguel
            clausulas.append("operacao IN (?, ?)")
            params.extend([str(operacao), str(Operation.AMBOS)])

        coluna_preco = (
            "preco_aluguel" if operacao == Operation.ALUGUEL else "preco_venda"
        )

        if preco_min is not None:
            clausulas.append(f"{coluna_preco} >= ?")
            params.append(preco_min)

        if preco_max is not None:
            clausulas.append(f"{coluna_preco} IS NOT NULL AND {coluna_preco} <= ?")
            params.append(preco_max)

        if quartos_min is not None:
            clausulas.append("quartos >= ?")
            params.append(quartos_min)

        if vagas_min is not None:
            clausulas.append("vagas >= ?")
            params.append(vagas_min)

        if aceita_pet is not None:
            clausulas.append("aceita_pet = ?")
            params.append(int(aceita_pet))

        if mobiliado is not None:
            clausulas.append("mobiliado = ?")
            params.append(int(mobiliado))

        where = f"WHERE {' AND '.join(clausulas)}" if clausulas else ""
        sql = f"SELECT * FROM properties {where} ORDER BY id LIMIT ?"
        params.append(limite)

        with get_connection(self._db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._to_domain(r) for r in rows]

    # --------------------------------------------------------
    # Busca voltada a investimento (cenário 3.2 do enunciado)
    # --------------------------------------------------------

    def buscar_para_investimento(
        self,
        *,
        ticket_max: float | None = None,
        perfil: InvestorProfile | None = None,
        rentabilidade_min: float | None = None,
        ordenar_por: str = "rentabilidade",
        limite: int = 10,
    ) -> list[Property]:
        """Busca imóveis sob a ótica do investidor.

        ordenar_por aceita 'rentabilidade' (renda) ou 'valorizacao'
        (ganho de capital), refletindo o objetivo declarado pelo lead.
        """
        clausulas = ["preco_venda IS NOT NULL"]
        params: list[object] = []

        if ticket_max is not None:
            clausulas.append("preco_venda <= ?")
            params.append(ticket_max)

        if perfil is not None and perfil != InvestorProfile.NAO_INFORMADO:
            clausulas.append("perfil_investimento = ?")
            params.append(str(perfil))

        if rentabilidade_min is not None:
            clausulas.append("rentabilidade_estimada >= ?")
            params.append(rentabilidade_min)

        coluna_ordem = (
            "potencial_valorizacao"
            if ordenar_por == "valorizacao"
            else "rentabilidade_estimada"
        )

        sql = (
            f"SELECT * FROM properties WHERE {' AND '.join(clausulas)} "
            f"ORDER BY {coluna_ordem} DESC LIMIT ?"
        )
        params.append(limite)

        with get_connection(self._db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._to_domain(r) for r in rows]

    # --------------------------------------------------------
    # Agregações — insumo do dashboard
    # --------------------------------------------------------

    def estatisticas(self) -> dict:
        """Resumo quantitativo da base, exibido no dashboard."""
        with get_connection(self._db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM properties").fetchone()[0]

            por_zona = {
                r["zona"]: r["c"]
                for r in conn.execute(
                    "SELECT zona, COUNT(*) c FROM properties GROUP BY zona"
                ).fetchall()
            }
            por_tipo = {
                r["tipo"]: r["c"]
                for r in conn.execute(
                    "SELECT tipo, COUNT(*) c FROM properties GROUP BY tipo"
                ).fetchall()
            }
            faixa = conn.execute(
                "SELECT MIN(preco_venda) mn, MAX(preco_venda) mx, "
                "AVG(preco_venda) avg FROM properties WHERE preco_venda IS NOT NULL"
            ).fetchone()

        return {
            "total": total,
            "por_zona": por_zona,
            "por_tipo": por_tipo,
            "preco_min": faixa["mn"],
            "preco_max": faixa["mx"],
            "preco_medio": round(faixa["avg"], 2) if faixa["avg"] else 0,
        }