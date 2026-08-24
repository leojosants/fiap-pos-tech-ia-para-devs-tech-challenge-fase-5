"""Testes da camada de persistência de imóveis.

Cada teste roda contra um banco temporário isolado, criado e destruído
pela fixture — sem tocar no banco de desenvolvimento.
"""

import pytest

from src.core.enums import InvestorProfile, Operation, PropertyType, Zone
from src.persistence.database import bootstrap
from src.persistence.property_repository import PropertyRepository

TOTAL_ESPERADO = 60
IMOVEIS_POR_ZONA = 15


@pytest.fixture(scope="module")
def repo(tmp_path_factory) -> PropertyRepository:
    """Repositório apontando para um banco temporário populado."""
    db_path = tmp_path_factory.mktemp("db") / "test_casalead.db"
    bootstrap(db_path)
    return PropertyRepository(db_path)


# ============================================================
# Bootstrap e integridade da base
# ============================================================

def test_base_carregada_completa(repo):
    assert repo.contar() == TOTAL_ESPERADO


def test_distribuicao_equilibrada_por_zona(repo):
    """Garante cobertura mínima em qualquer recorte geográfico."""
    por_zona = repo.estatisticas()["por_zona"]
    assert len(por_zona) == 4
    for zona, total in por_zona.items():
        assert total == IMOVEIS_POR_ZONA, f"zona {zona} com {total} imóveis"


def test_bootstrap_e_idempotente(repo):
    """Rodar o bootstrap novamente não duplica registros."""
    resultado = bootstrap(repo._db_path)
    assert resultado["imoveis_inseridos"] == 0
    assert resultado["imoveis_total"] == TOTAL_ESPERADO


# ============================================================
# Coerência dos dados sintéticos
# ============================================================

def test_todo_imovel_tem_preco_compativel_com_operacao(repo):
    for im in repo.listar_todos():
        if im.operacao in (Operation.VENDA, Operation.AMBOS):
            assert im.preco_venda and im.preco_venda > 0, im.codigo
        if im.operacao in (Operation.ALUGUEL, Operation.AMBOS):
            assert im.preco_aluguel and im.preco_aluguel > 0, im.codigo


def test_preco_por_m2_dentro_de_faixa_plausivel(repo):
    """Nenhum imóvel deve fugir da realidade do mercado paulistano."""
    for im in repo.listar_todos():
        if im.preco_m2 is not None:
            assert 4_000 <= im.preco_m2 <= 25_000, f"{im.codigo}: {im.preco_m2}/m²"


def test_atributos_fisicos_coerentes(repo):
    for im in repo.listar_todos():
        assert im.area_util > 0, im.codigo
        assert im.suites <= im.quartos, im.codigo
        assert im.banheiros >= 1, im.codigo
        if im.tipo == PropertyType.CASA:
            assert im.andar is None, im.codigo


def test_descricao_e_caracteristicas_preenchidas(repo):
    """A busca semântica da Etapa 4 depende desses campos."""
    for im in repo.listar_todos():
        assert len(im.descricao) > 50, im.codigo
        assert len(im.caracteristicas) >= 3, im.codigo


# ============================================================
# Busca estruturada
# ============================================================

def test_busca_sem_filtros_retorna_ate_o_limite(repo):
    assert len(repo.buscar(limite=10)) == 10


def test_busca_por_zona_respeita_filtro(repo):
    resultados = repo.buscar(zona=Zone.SUL, limite=50)
    assert resultados
    assert all(im.zona == Zone.SUL for im in resultados)


def test_busca_por_preco_maximo(repo):
    teto = 600_000
    resultados = repo.buscar(preco_max=teto, limite=50)
    assert resultados
    assert all(im.preco_venda <= teto for im in resultados)


def test_busca_por_quartos_minimo(repo):
    resultados = repo.buscar(quartos_min=3, limite=50)
    assert resultados
    assert all(im.quartos >= 3 for im in resultados)


def test_busca_aluguel_filtra_pela_coluna_correta(repo):
    """Operação aluguel deve filtrar por preco_aluguel, não por venda."""
    resultados = repo.buscar(operacao=Operation.ALUGUEL, preco_max=3_000, limite=50)
    assert resultados
    assert all(im.preco_aluguel <= 3_000 for im in resultados)


def test_busca_aluguel_inclui_operacao_ambos(repo):
    """Imóveis marcados como 'ambos' devem aparecer na busca por aluguel."""
    resultados = repo.buscar(operacao=Operation.ALUGUEL, limite=60)
    assert any(im.operacao == Operation.AMBOS for im in resultados)


def test_filtros_combinados_aplicam_todos_os_criterios(repo):
    resultados = repo.buscar(
        zona=Zone.SUL,
        tipo=PropertyType.APARTAMENTO,
        quartos_min=2,
        preco_max=900_000,
    )
    assert resultados, "cenário 3.1 do enunciado não pode retornar vazio"
    for im in resultados:
        assert im.zona == Zone.SUL
        assert im.tipo == PropertyType.APARTAMENTO
        assert im.quartos >= 2
        assert im.preco_venda <= 900_000


def test_todos_os_cenarios_de_busca_tem_cobertura(repo):
    """Nenhuma combinação plausível pode retornar vazio na demonstração."""
    for zona in Zone:
        assert repo.buscar(zona=zona, quartos_min=2, preco_max=900_000), zona


# ============================================================
# Busca para investimento (cenário 3.2)
# ============================================================

def test_investimento_ordena_por_rentabilidade(repo):
    resultados = repo.buscar_para_investimento(ordenar_por="rentabilidade", limite=10)
    valores = [im.rentabilidade_estimada for im in resultados]
    assert valores == sorted(valores, reverse=True)


def test_investimento_ordena_por_valorizacao(repo):
    resultados = repo.buscar_para_investimento(ordenar_por="valorizacao", limite=10)
    valores = [im.potencial_valorizacao for im in resultados]
    assert valores == sorted(valores, reverse=True)


def test_investimento_respeita_ticket_e_perfil(repo):
    resultados = repo.buscar_para_investimento(
        ticket_max=600_000, perfil=InvestorProfile.CONSERVADOR, limite=10
    )
    assert resultados, "cenário 3.2 do enunciado não pode retornar vazio"
    for im in resultados:
        assert im.preco_venda <= 600_000
        assert im.perfil_investimento == InvestorProfile.CONSERVADOR


# ============================================================
# Consultas pontuais
# ============================================================

def test_busca_por_codigo_existente(repo):
    im = repo.buscar_por_codigo("CL0001")
    assert im is not None
    assert im.id == 1


def test_busca_por_codigo_inexistente_retorna_none(repo):
    assert repo.buscar_por_codigo("CL9999") is None


def test_texto_para_busca_consolida_atributos(repo):
    texto = repo.buscar_por_codigo("CL0001").texto_para_busca()
    assert "Pinheiros" in texto
    assert "quartos" in texto