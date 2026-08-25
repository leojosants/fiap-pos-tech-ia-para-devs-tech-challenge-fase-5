"""Testes do retriever de busca semântica (src/recommendation/retriever.py).

Módulo 100% em memória — sem banco. Escopo:

1. `normalizar()`: remoção de acento, minúsculas, pontuação e espaços
   redundantes — a base de tudo que segue, já que TF-IDF e expansão de
   sinônimos operam sobre o texto normalizado.
2. `expandir()`: a mitigação documentada da limitação conhecida do
   TF-IDF ("não reconhece sinônimos") — garante que o dicionário de
   expansão do domínio realmente produz os termos esperados, nos dois
   sentidos (indexação e consulta), incluindo o caso de a palavra vir
   acentuada na entrada do usuário.
3. `PropertyRetriever`: construção do índice, `disponivel` e
   `tamanho_vocabulario` como sinais de diagnóstico, e o comportamento
   de `buscar()` — limite, `score_minimo`, restrição por `candidatos`
   (o ponto de integração com o filtro estruturado do
   `PropertyRepository`), ordenação por score e a evidência de
   `termos_relevantes`.
4. `ResultadoBusca.percentual` e `explicar()`.

Sem esses testes, uma mudança no dicionário `_EXPANSAO_TERMOS` ou nos
parâmetros do `TfidfVectorizer` só seria percebida manualmente, testando
buscas no chat — como já ocorreu durante o desenvolvimento (ver
docs/decisoes_tecnicas.md, Etapa 4).
"""

from src.core.enums import Operation, PropertyType, Zone
from src.core.models import Property
from src.recommendation.retriever import PropertyRetriever, expandir, normalizar


def _imovel(id: int, **overrides) -> Property:
    """Fábrica de Property com valores mínimos válidos para os testes."""
    base = dict(
        codigo=f"AP-{id:03d}",
        titulo="Apartamento padrão",
        tipo=PropertyType.APARTAMENTO,
        operacao=Operation.VENDA,
        zona=Zone.SUL,
        bairro="Moema",
        endereco_aproximado="Rua das Flores",
        id=id,
    )
    base.update(overrides)
    return Property(**base)


class TestNormalizar:

    def test_remove_acentuacao(self):
        assert normalizar("Saúde") == "saude"
        assert normalizar("Butantã") == "butanta"

    def test_converte_para_minusculas(self):
        assert normalizar("APARTAMENTO") == "apartamento"

    def test_remove_pontuacao(self):
        assert normalizar("Olá, mundo!") == "ola mundo"

    def test_colapsa_espacos_redundantes(self):
        assert normalizar("muitos    espaços   aqui") == "muitos espacos aqui"

    def test_remove_espacos_nas_bordas(self):
        assert normalizar("  texto com espaço nas bordas  ") == "texto com espaco nas bordas"


class TestExpandir:

    def test_palavra_conhecida_traz_seus_sinonimos(self):
        resultado = expandir("apartamento arejado")
        assert "ensolarado" in resultado
        assert "ventilado" in resultado

    def test_palavra_desconhecida_permanece_sozinha(self):
        resultado = expandir("xilofone azul")
        assert resultado == "xilofone azul"

    def test_multiplos_termos_conhecidos_expandem_todos(self):
        resultado = expandir("pet e piscina")
        assert "cachorro" in resultado  # expansão de "pet"
        assert "lazer" in resultado  # expansão de "piscina"

    def test_termo_acentuado_na_entrada_ainda_e_reconhecido(self):
        # "espaçoso" (com cedilha) precisa normalizar para "espacoso"
        # antes de bater com a chave do dicionário de expansão.
        resultado = expandir("apartamento espaçoso")
        assert "amplo" in resultado

    def test_string_vazia_nao_quebra(self):
        assert expandir("") == ""


class TestPropertyRetrieverIndice:

    def test_disponivel_com_base_nao_vazia(self):
        retriever = PropertyRetriever([_imovel(1, descricao="apartamento amplo")])
        assert retriever.disponivel is True

    def test_indisponivel_com_base_vazia(self):
        retriever = PropertyRetriever([])
        assert retriever.disponivel is False

    def test_tamanho_vocabulario_positivo_com_base_indexada(self):
        retriever = PropertyRetriever(
            [_imovel(1, descricao="apartamento amplo e ensolarado")]
        )
        assert retriever.tamanho_vocabulario > 0

    def test_tamanho_vocabulario_zero_com_base_vazia(self):
        retriever = PropertyRetriever([])
        assert retriever.tamanho_vocabulario == 0


class TestBuscar:

    def _base_variada(self) -> list[Property]:
        return [
            _imovel(
                1,
                titulo="Studio arejado",
                bairro="Pinheiros",
                caracteristicas=["varanda"],
                descricao="Apartamento ensolarado, perto do metrô",
            ),
            _imovel(
                2,
                titulo="Casa com piscina",
                bairro="Moema",
                caracteristicas=["churrasqueira", "área gourmet"],
                descricao="Casa ampla, ideal para família, aceita pet",
            ),
            _imovel(
                3,
                titulo="Sala comercial",
                tipo=PropertyType.SALA_COMERCIAL,
                bairro="Centro",
                descricao="Espaço comercial simples, sem diferenciais",
            ),
        ]

    def test_consulta_vazia_retorna_lista_vazia(self):
        retriever = PropertyRetriever(self._base_variada())
        assert retriever.buscar("   ") == []

    def test_indice_indisponivel_retorna_lista_vazia(self):
        retriever = PropertyRetriever([])
        assert retriever.buscar("apartamento arejado") == []

    def test_encontra_o_imovel_semanticamente_mais_proximo(self):
        retriever = PropertyRetriever(self._base_variada())

        resultados = retriever.buscar("quero um lugar arejado perto do metrô")

        assert len(resultados) >= 1
        assert resultados[0].imovel.id == 1

    def test_sinonimo_encontra_imovel_que_usa_o_termo_relacionado(self):
        # A base só tem "ensolarado" — a consulta usa "arejado". Sem a
        # expansão de sinônimos, a similaridade seria baixa demais.
        retriever = PropertyRetriever(self._base_variada())

        resultados = retriever.buscar("apartamento arejado")

        ids_encontrados = {r.imovel.id for r in resultados}
        assert 1 in ids_encontrados

    def test_respeita_o_limite(self):
        base = [
            _imovel(i, descricao="apartamento amplo ensolarado arejado")
            for i in range(1, 6)
        ]
        retriever = PropertyRetriever(base)

        resultados = retriever.buscar("apartamento amplo", limite=2)

        assert len(resultados) <= 2

    def test_score_minimo_filtra_correspondencias_fracas(self):
        retriever = PropertyRetriever(self._base_variada())

        # score_minimo=1.01 é inatingível (cosseno máximo é 1.0) —
        # garante que o filtro de fato descarta tudo quando exigido.
        resultados = retriever.buscar("apartamento arejado", score_minimo=1.01)

        assert resultados == []

    def test_restringe_busca_ao_subconjunto_de_candidatos(self):
        base = self._base_variada()
        retriever = PropertyRetriever(base)

        # Sem restrição, o imóvel 1 apareceria; forçando candidatos
        # sem ele, não deve aparecer mesmo sendo o mais relevante.
        candidatos = [im for im in base if im.id != 1]
        resultados = retriever.buscar("apartamento arejado", candidatos=candidatos)

        ids_encontrados = {r.imovel.id for r in resultados}
        assert 1 not in ids_encontrados

    def test_resultados_ordenados_por_score_decrescente(self):
        retriever = PropertyRetriever(self._base_variada())

        resultados = retriever.buscar("apartamento amplo arejado ensolarado família pet")

        scores = [r.score for r in resultados]
        assert scores == sorted(scores, reverse=True)

    def test_termos_relevantes_nao_vazio_quando_ha_correspondencia(self):
        retriever = PropertyRetriever(self._base_variada())

        resultados = retriever.buscar("apartamento ensolarado metrô")

        assert len(resultados) >= 1
        assert len(resultados[0].termos_relevantes) > 0


class TestResultadoBuscaPercentual:

    def test_converte_score_para_percentual_arredondado(self):
        retriever = PropertyRetriever(
            [_imovel(1, descricao="apartamento ensolarado e amplo perto do metrô")]
        )
        resultados = retriever.buscar("apartamento ensolarado amplo metrô")

        assert len(resultados) == 1
        assert resultados[0].percentual == round(resultados[0].score * 100)


class TestExplicar:

    def test_retorna_diagnostico_completo(self):
        retriever = PropertyRetriever(
            [_imovel(1, descricao="apartamento ensolarado")]
        )

        diagnostico = retriever.explicar("apartamento arejado")

        assert diagnostico["consulta_original"] == "apartamento arejado"
        assert "ensolarado" in diagnostico["consulta_expandida"]
        assert diagnostico["vocabulario_indexado"] == retriever.tamanho_vocabulario
        assert diagnostico["imoveis_indexados"] == 1