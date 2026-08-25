"""Testes do ranqueador de imóveis (src/recommendation/ranker.py).

Este é o módulo de regra de negócio mais denso do projeto — combina
filtro estruturado, tradução de preferências textuais em filtros,
relaxamento progressivo e ordenação semântica. A suíte é dividida em
duas categorias:

1. **Testes puros** (métodos estáticos, sem banco): `pode_recomendar`,
   `_preferencias_estruturais`, `_consulta_semantica`,
   `_motivos_estruturais`, `_motivos_investimento` e
   `formatar_para_prompt`. Usam imóveis e leads sintéticos, construídos
   à mão, para isolar cada ramo de decisão sem depender da base real.

2. **Testes de integração** (`TestRecomendarMoradiaIntegracao`,
   `TestRecomendarInvestimentoIntegracao`, `TestRelaxarFiltros`): rodam
   contra a base real de 60 imóveis (`data/seed/properties.json`, o
   mesmo seed versionado usado em produção), carregada uma única vez
   num banco temporário (fixture de escopo de módulo, mesmo padrão de
   `test_property_repository.py`). Cobrem o filtro + relaxamento +
   ordenação de ponta a ponta, incluindo dois cenários calibrados
   manualmente contra o conteúdo real do seed (documentados nos
   próprios testes): o relaxamento de preferência estrutural e a
   ausência total de candidatos.

Nenhum teste desta suíte grava no banco — `recomendar()` e seus
auxiliares são somente leitura.
"""

import pytest

from src.core.enums import (
    Intent,
    InvestmentGoal,
    InvestorProfile,
    Operation,
    PropertyType,
    Zone,
)
from src.core.models import Lead, Property
from src.persistence.database import bootstrap
from src.persistence.property_repository import PropertyRepository
from src.recommendation.ranker import PropertyRanker, Recomendacao, ResultadoRecomendacao
from src.recommendation.retriever import PropertyRetriever


def _imovel(**overrides) -> Property:
    """Fábrica de Property sintético, para os testes puros."""
    base = dict(
        codigo="AP-001",
        titulo="Apartamento teste",
        tipo=PropertyType.APARTAMENTO,
        operacao=Operation.VENDA,
        zona=Zone.SUL,
        bairro="Moema",
        endereco_aproximado="Rua das Flores",
    )
    base.update(overrides)
    return Property(**base)


# ============================================================
# TESTES PUROS — sem banco
# ============================================================


class TestPodeRecomendar:

    def test_moradia_sem_nenhum_criterio_e_insuficiente(self):
        pode, motivo = PropertyRanker.pode_recomendar(Lead(intent=Intent.COMPRA))
        assert pode is False
        assert motivo != ""

    def test_moradia_com_apenas_zona_e_insuficiente(self):
        pode, _ = PropertyRanker.pode_recomendar(
            Lead(intent=Intent.COMPRA, zona_interesse=Zone.SUL)
        )
        assert pode is False

    def test_moradia_com_apenas_preco_e_insuficiente(self):
        pode, _ = PropertyRanker.pode_recomendar(
            Lead(intent=Intent.COMPRA, preco_max=500_000)
        )
        assert pode is False

    def test_moradia_com_zona_e_preco_e_suficiente(self):
        pode, motivo = PropertyRanker.pode_recomendar(
            Lead(intent=Intent.COMPRA, zona_interesse=Zone.SUL, preco_max=500_000)
        )
        assert pode is True
        assert motivo == ""

    def test_bairros_interesse_conta_como_criterio_de_localizacao(self):
        pode, _ = PropertyRanker.pode_recomendar(
            Lead(intent=Intent.COMPRA, bairros_interesse=["Moema"], preco_max=500_000)
        )
        assert pode is True

    def test_aluguel_usa_a_mesma_regra_de_compra(self):
        pode, _ = PropertyRanker.pode_recomendar(
            Lead(intent=Intent.ALUGUEL, zona_interesse=Zone.SUL, preco_max=3_000)
        )
        assert pode is True

    def test_investimento_sem_ticket_e_insuficiente(self):
        pode, motivo = PropertyRanker.pode_recomendar(Lead(intent=Intent.INVESTIMENTO))
        assert pode is False
        assert "valor" in motivo.lower()

    def test_investimento_com_ticket_e_suficiente(self):
        pode, motivo = PropertyRanker.pode_recomendar(
            Lead(intent=Intent.INVESTIMENTO, ticket_disponivel=500_000)
        )
        assert pode is True
        assert motivo == ""


class TestPreferenciasEstruturais:

    def test_reconhece_pedido_de_home_office(self):
        lead = Lead(preferencias=["preciso de espaço para home office"])
        assert "quarto_extra" in PropertyRanker._preferencias_estruturais(lead)

    def test_reconhece_pedido_de_pet(self):
        lead = Lead(preferencias=["tenho um cachorro"])
        assert "pet" in PropertyRanker._preferencias_estruturais(lead)

    def test_reconhece_pedido_de_vaga(self):
        lead = Lead(preferencias=["preciso de garagem"])
        assert "vaga" in PropertyRanker._preferencias_estruturais(lead)

    def test_reconhece_pedido_de_mobiliado(self):
        lead = Lead(preferencias=["quero algo mobiliado"])
        assert "mobiliado" in PropertyRanker._preferencias_estruturais(lead)

    def test_preferencia_nao_mapeada_nao_adiciona_nada(self):
        lead = Lead(preferencias=["gosto de vista para o pôr do sol"])
        assert PropertyRanker._preferencias_estruturais(lead) == set()

    def test_sem_preferencias_devolve_conjunto_vazio(self):
        assert PropertyRanker._preferencias_estruturais(Lead()) == set()


class TestConsultaSemantica:

    def test_junta_preferencias_e_bairros(self):
        lead = Lead(preferencias=["arejado"], bairros_interesse=["Pinheiros"])
        consulta = PropertyRanker._consulta_semantica(lead)
        assert "arejado" in consulta
        assert "Pinheiros" in consulta

    def test_lead_sem_nada_produz_consulta_vazia(self):
        assert PropertyRanker._consulta_semantica(Lead()) == ""


class TestMotivosEstruturais:

    def test_motivo_de_zona_quando_bate(self):
        lead = Lead(zona_interesse=Zone.SUL)
        imovel = _imovel(zona=Zone.SUL, bairro="Moema")
        motivos = PropertyRanker._motivos_estruturais(imovel, lead, set())
        assert any("região que você procura" in m for m in motivos)

    def test_sem_motivo_de_zona_quando_nao_bate(self):
        lead = Lead(zona_interesse=Zone.NORTE)
        imovel = _imovel(zona=Zone.SUL)
        motivos = PropertyRanker._motivos_estruturais(imovel, lead, set())
        assert not any("região que você procura" in m for m in motivos)

    def test_preco_confortavelmente_dentro_do_orcamento(self):
        lead = Lead(preco_max=500_000)
        imovel = _imovel(preco_venda=400_000)  # folga de 100k > 10% de 500k
        motivos = PropertyRanker._motivos_estruturais(imovel, lead, set())
        assert any("confortavelmente" in m for m in motivos)

    def test_preco_cabe_mas_sem_folga_confortavel(self):
        lead = Lead(preco_max=500_000)
        imovel = _imovel(preco_venda=480_000)  # folga de 20k < 10% de 500k
        motivos = PropertyRanker._motivos_estruturais(imovel, lead, set())
        assert any(m == "Cabe no seu orçamento" for m in motivos)

    def test_sem_motivo_de_preco_quando_estoura_orcamento(self):
        lead = Lead(preco_max=500_000)
        imovel = _imovel(preco_venda=600_000)
        motivos = PropertyRanker._motivos_estruturais(imovel, lead, set())
        assert not any("orçamento" in m for m in motivos)

    def test_motivo_de_quartos_a_mais(self):
        lead = Lead(quartos_desejados=2)
        imovel = _imovel(quartos=4)
        motivos = PropertyRanker._motivos_estruturais(imovel, lead, set())
        assert any("2 a mais" in m for m in motivos)

    def test_motivo_de_quartos_a_menos_plural(self):
        lead = Lead(quartos_desejados=3)
        imovel = _imovel(quartos=2)
        motivos = PropertyRanker._motivos_estruturais(imovel, lead, set())
        assert any("2 quartos" in m and "menos do que você pediu" in m for m in motivos)

    def test_motivo_de_quartos_a_menos_singular(self):
        lead = Lead(quartos_desejados=3)
        imovel = _imovel(quartos=1)
        motivos = PropertyRanker._motivos_estruturais(imovel, lead, set())
        assert any("1 quarto " in m for m in motivos)  # singular, sem "s"

    def test_motivo_de_studio_quando_lead_pediu_quartos(self):
        lead = Lead(quartos_desejados=2)
        imovel = _imovel(quartos=0)
        motivos = PropertyRanker._motivos_estruturais(imovel, lead, set())
        assert any("studio" in m for m in motivos)

    def test_motivo_pet_aceita(self):
        imovel = _imovel(aceita_pet=True)
        motivos = PropertyRanker._motivos_estruturais(imovel, Lead(), {"pet"})
        assert any("Aceita animais" in m for m in motivos)

    def test_motivo_pet_nao_aceita(self):
        imovel = _imovel(aceita_pet=False)
        motivos = PropertyRanker._motivos_estruturais(imovel, Lead(), {"pet"})
        assert any("Não aceita animais" in m for m in motivos)

    def test_sem_estrutural_pet_nao_menciona_animais(self):
        imovel = _imovel(aceita_pet=False)
        motivos = PropertyRanker._motivos_estruturais(imovel, Lead(), set())
        assert not any("animais" in m.lower() for m in motivos)

    def test_motivo_de_vaga_quando_imovel_tem_vaga(self):
        imovel = _imovel(vagas=2)
        motivos = PropertyRanker._motivos_estruturais(imovel, Lead(), {"vaga"})
        assert any("2 vaga(s)" in m for m in motivos)

    def test_sem_motivo_de_vaga_quando_imovel_nao_tem_vaga(self):
        imovel = _imovel(vagas=0)
        motivos = PropertyRanker._motivos_estruturais(imovel, Lead(), {"vaga"})
        assert not any("vaga" in m.lower() for m in motivos)


class TestMotivosInvestimento:

    def test_sempre_inclui_rentabilidade_e_valorizacao(self):
        imovel = _imovel(rentabilidade_estimada=6.5, potencial_valorizacao=8.0)
        motivos = PropertyRanker._motivos_investimento(imovel, Lead())
        assert any("Rentabilidade estimada" in m for m in motivos)
        assert any("valorização" in m for m in motivos)

    def test_atende_expectativa_de_retorno_quando_rentabilidade_e_maior(self):
        lead = Lead(expectativa_retorno=5.0)
        imovel = _imovel(rentabilidade_estimada=6.0)
        motivos = PropertyRanker._motivos_investimento(imovel, lead)
        assert any("Atende à sua expectativa" in m for m in motivos)

    def test_nao_menciona_expectativa_quando_rentabilidade_e_menor(self):
        lead = Lead(expectativa_retorno=8.0)
        imovel = _imovel(rentabilidade_estimada=6.0)
        motivos = PropertyRanker._motivos_investimento(imovel, lead)
        assert not any("expectativa" in m.lower() for m in motivos)

    def test_perfil_compativel_e_mencionado(self):
        lead = Lead(perfil_investidor=InvestorProfile.MODERADO)
        imovel = _imovel(perfil_investimento=InvestorProfile.MODERADO)
        motivos = PropertyRanker._motivos_investimento(imovel, lead)
        assert any("Compatível com o perfil" in m for m in motivos)

    def test_perfil_incompativel_nao_e_mencionado(self):
        lead = Lead(perfil_investidor=InvestorProfile.CONSERVADOR)
        imovel = _imovel(perfil_investimento=InvestorProfile.ARROJADO)
        motivos = PropertyRanker._motivos_investimento(imovel, lead)
        assert not any("Compatível com o perfil" in m for m in motivos)


class TestFormatarParaPrompt:

    def test_sem_resultados_produz_string_vazia(self):
        assert PropertyRanker.formatar_para_prompt(ResultadoRecomendacao()) == ""

    def test_formata_preco_de_venda_com_separador_de_milhar(self):
        imovel = _imovel(preco_venda=750_000, area_util=80, quartos=2, vagas=1)
        resultado = ResultadoRecomendacao(
            recomendacoes=[Recomendacao(imovel=imovel, score_final=1.0)]
        )
        texto = PropertyRanker.formatar_para_prompt(resultado)
        assert "R$ 750.000" in texto

    def test_formata_preco_de_aluguel_com_sufixo_mes(self):
        imovel = _imovel(
            preco_venda=None, preco_aluguel=2_500, operacao=Operation.ALUGUEL,
            area_util=50, quartos=1, vagas=0,
        )
        resultado = ResultadoRecomendacao(
            recomendacoes=[Recomendacao(imovel=imovel, score_final=1.0)]
        )
        texto = PropertyRanker.formatar_para_prompt(resultado)
        assert "R$ 2.500/mês" in texto

    def test_trunca_caracteristicas_as_tres_primeiras(self):
        imovel = _imovel(
            preco_venda=500_000,
            caracteristicas=["varanda", "piscina", "academia", "playground", "salão"],
        )
        resultado = ResultadoRecomendacao(
            recomendacoes=[Recomendacao(imovel=imovel, score_final=1.0)]
        )
        texto = PropertyRanker.formatar_para_prompt(resultado)
        assert "playground" not in texto
        assert "salão" not in texto
        assert "varanda" in texto


# ============================================================
# TESTES DE INTEGRAÇÃO — base real (seed versionado, 60 imóveis)
# ============================================================


@pytest.fixture(scope="module")
def ranker(tmp_path_factory) -> PropertyRanker:
    """Ranker sobre a base real, carregada uma única vez no módulo.

    Somente leitura — recomendar() e seus auxiliares não gravam nada,
    então compartilhar a instância entre os testes deste módulo é
    seguro (mesmo padrão de test_property_repository.py).
    """
    db_path = tmp_path_factory.mktemp("db") / "ranker.db"
    bootstrap(db_path)
    repo = PropertyRepository(db_path)
    retriever = PropertyRetriever(repo.listar_todos())
    return PropertyRanker(repo, retriever)


class TestRecomendarMoradiaIntegracao:

    def test_sem_criterios_suficientes_nao_busca_nada(self, ranker):
        resultado = ranker.recomendar(Lead(intent=Intent.COMPRA))
        assert resultado.tem_resultados is False
        assert resultado.motivo_ausencia != ""

    def test_filtra_pela_zona_pedida(self, ranker):
        lead = Lead(intent=Intent.COMPRA, zona_interesse=Zone.SUL, preco_max=3_500_000)
        resultado = ranker.recomendar(lead)

        assert resultado.tem_resultados is True
        assert all(r.imovel.zona == Zone.SUL for r in resultado.recomendacoes)

    def test_respeita_quartos_minimos_declarados(self, ranker):
        lead = Lead(
            intent=Intent.COMPRA, zona_interesse=Zone.SUL,
            preco_max=3_500_000, quartos_desejados=3,
        )
        resultado = ranker.recomendar(lead)

        assert all(r.imovel.quartos >= 3 for r in resultado.recomendacoes)

    def test_preferencia_de_home_office_soma_um_quarto_ao_minimo(self, ranker):
        # quartos_desejados=2 + preferência de home office → filtro real
        # aplicado é quartos >= 3, não >= 2.
        lead = Lead(
            intent=Intent.COMPRA, zona_interesse=Zone.SUL, preco_max=3_500_000,
            quartos_desejados=2, preferencias=["preciso de espaço para home office"],
        )
        resultado = ranker.recomendar(lead)

        assert resultado.tem_resultados is True
        assert all(r.imovel.quartos >= 3 for r in resultado.recomendacoes)

    def test_sem_tipo_studio_pedido_studios_sao_excluidos(self, ranker):
        lead = Lead(intent=Intent.COMPRA, zona_interesse=Zone.SUL, preco_max=3_500_000)
        resultado = ranker.recomendar(lead)

        assert all(r.imovel.quartos >= 1 for r in resultado.recomendacoes)

    def test_tipo_studio_pedido_explicitamente_e_incluido(self, ranker):
        lead = Lead(
            intent=Intent.COMPRA, zona_interesse=Zone.SUL, preco_max=3_500_000,
            tipo_imovel=PropertyType.STUDIO,
        )
        resultado = ranker.recomendar(lead)

        assert resultado.tem_resultados is True
        assert all(r.imovel.tipo is PropertyType.STUDIO for r in resultado.recomendacoes)

    def test_aluguel_filtra_pela_operacao_correta(self, ranker):
        lead = Lead(intent=Intent.ALUGUEL, zona_interesse=Zone.NORTE, preco_max=20_000)
        resultado = ranker.recomendar(lead)

        assert all(
            r.imovel.operacao in (Operation.ALUGUEL, Operation.AMBOS)
            for r in resultado.recomendacoes
        )

    def test_preferencia_estrutural_muito_restritiva_e_relaxada(self, ranker):
        # Calibrado manualmente contra o seed real: zona sul, teto de
        # R$ 1.200.000, só 1 imóvel é mobiliado entre os 5 candidatos
        # sem essa preferência — dispara o relaxamento (ver
        # docstring de _recomendar_moradia).
        lead = Lead(
            intent=Intent.COMPRA, zona_interesse=Zone.SUL, preco_max=1_200_000,
            preferencias=["apartamento mobiliado"],
        )
        resultado = ranker.recomendar(lead)

        assert resultado.criterios_usados["preferencias_relaxadas"] is True
        assert resultado.total_candidatos == 5

    def test_sem_nenhum_candidato_mesmo_apos_relaxamento_total(self, ranker):
        # Teto de R$ 1 é inatingível mesmo com o fator de relaxamento
        # máximo (1,60×) — nenhum imóvel do seed chega perto disso.
        lead = Lead(intent=Intent.COMPRA, zona_interesse=Zone.SUL, preco_max=1.0)
        resultado = ranker.recomendar(lead)

        assert resultado.tem_resultados is False
        assert "Nenhum imóvel disponível" in resultado.motivo_ausencia


class TestRecomendarInvestimentoIntegracao:

    def test_ticket_disponivel_e_suficiente_para_recomendar(self, ranker):
        lead = Lead(intent=Intent.INVESTIMENTO, ticket_disponivel=1_000_000)
        resultado = ranker.recomendar(lead)

        assert resultado.tem_resultados is True
        assert all(
            im.imovel.preco_venda <= 1_000_000 for im in resultado.recomendacoes
        )

    def test_motivos_de_investimento_sao_preenchidos(self, ranker):
        lead = Lead(intent=Intent.INVESTIMENTO, ticket_disponivel=1_000_000)
        resultado = ranker.recomendar(lead)

        assert all(r.motivos for r in resultado.recomendacoes)

    def test_ordena_por_valorizacao_quando_esse_e_o_objetivo(self, ranker):
        lead = Lead(
            intent=Intent.INVESTIMENTO, ticket_disponivel=2_000_000,
            objetivo_investimento=InvestmentGoal.VALORIZACAO,
        )
        resultado = ranker.recomendar(lead)

        assert resultado.criterios_usados["ordenado_por"] == "valorizacao"
        valorizacoes = [r.imovel.potencial_valorizacao for r in resultado.recomendacoes]
        assert valorizacoes == sorted(valorizacoes, reverse=True)

    def test_ordena_por_rentabilidade_quando_objetivo_e_renda(self, ranker):
        lead = Lead(
            intent=Intent.INVESTIMENTO, ticket_disponivel=2_000_000,
            objetivo_investimento=InvestmentGoal.RENDA,
        )
        resultado = ranker.recomendar(lead)

        assert resultado.criterios_usados["ordenado_por"] == "rentabilidade"
        rentabilidades = [r.imovel.rentabilidade_estimada for r in resultado.recomendacoes]
        assert rentabilidades == sorted(rentabilidades, reverse=True)


class TestRelaxarFiltros:

    def test_encontra_candidatos_relaxando_progressivamente(self, ranker):
        # Teto abaixo do menor preço da zona sul (R$ 455 mil) — o filtro
        # direto não encontraria nada, mas os níveis de relaxamento
        # (até 1,60× de preço e zona ampliada) alcançam o restante da
        # base, que tem imóveis a partir de R$ 196 mil (zona norte).
        lead = Lead(zona_interesse=Zone.SUL, preco_max=400_000)
        candidatos = ranker._relaxar_filtros(lead, Operation.VENDA, quartos_min=2)
        assert len(candidatos) > 0

    def test_retorna_vazio_quando_nenhum_nivel_encontra_nada(self, ranker):
        lead = Lead(zona_interesse=Zone.SUL, preco_max=1.0)
        candidatos = ranker._relaxar_filtros(lead, Operation.VENDA, quartos_min=1)
        assert candidatos == []