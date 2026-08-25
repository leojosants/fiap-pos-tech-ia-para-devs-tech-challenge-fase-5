"""Testes dos helpers puros de src/ui/components/property_card.py.

Escopo deliberadamente restrito: `_moeda()` e `_moeda_md()` são as
únicas funções do módulo sem chamada a `st.*` — todo o resto
(`_renderizar_card`, `_renderizar_card_investimento`, `renderizar`)
desenha diretamente na interface do Streamlit e não é testável em
unidade, mesmo padrão já aceito para `page_chat.py`, `page_dashboard.py`
e `page_broker.py` nas etapas anteriores.

`_moeda_md()` escapa o cifrão (`R\\$` em vez de `R$`) pela mesma razão
documentada em `test_page_chat_escape.py`: duas ocorrências de `$` na
mesma string acionam a renderização de fórmula LaTeX do Streamlit —
bug #21, corrigido aqui primeiro e depois replicado em `page_chat.py`.
Os testes de escape aqui são a cobertura original desse comportamento.
"""

import inspect

from src.ui.components import property_card
from src.ui.components.property_card import _moeda, _moeda_md


class TestMoeda:
    """Formato para st.metric — não interpreta markdown, cifrão puro."""

    def test_none_vira_travessao(self):
        assert _moeda(None) == "—"

    def test_formata_com_separador_de_milhar(self):
        assert _moeda(850_000) == "R$ 850.000"

    def test_arredonda_centavos(self):
        assert _moeda(850_000.7) == "R$ 850.001"

    def test_zero_nao_e_tratado_como_ausente(self):
        # A checagem é `valor is None`, não uma checagem de "falsy" —
        # 0 é um valor monetário legítimo (ex.: vagas sem custo extra),
        # diferente de "sem informação".
        assert _moeda(0) == "R$ 0"


class TestMoedaMd:
    """Formato para st.markdown/st.caption — cifrão escapado."""

    def test_none_vira_travessao(self):
        assert _moeda_md(None) == "—"

    def test_escapa_o_cifrao(self):
        # Regressão do bug #21: sem o escape, duas ocorrências de "$"
        # na mesma tela acionam o modo LaTeX do Streamlit.
        assert _moeda_md(850_000) == "R\\$ 850.000"

    def test_formata_com_separador_de_milhar(self):
        resultado = _moeda_md(850_000)
        assert "850.000" in resultado

    def test_zero_nao_e_tratado_como_ausente(self):
        assert _moeda_md(0) == "R\\$ 0"


class TestFuncoesRealmenteUsadasNoModulo:
    """Confirma que os helpers testados são os mesmos referenciados nos
    pontos de renderização — não cópias isoladas sem uso real."""

    def test_moeda_md_e_usada_no_card_de_moradia(self):
        codigo = inspect.getsource(property_card._renderizar_card)
        assert "_moeda_md(" in codigo

    def test_moeda_md_e_usada_no_card_de_investimento(self):
        codigo = inspect.getsource(property_card._renderizar_card_investimento)
        assert "_moeda_md(" in codigo

    def test_moeda_e_usada_no_card_de_investimento(self):
        # _moeda() (sem escape) é usada especificamente para os valores
        # dentro de st.metric, que não interpreta markdown.
        codigo = inspect.getsource(property_card._renderizar_card_investimento)
        assert "_moeda(" in codigo