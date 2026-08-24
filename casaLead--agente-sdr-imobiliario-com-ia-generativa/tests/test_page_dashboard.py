"""Testes de _serie() (page_dashboard.py).

Única parte de page_dashboard.py que não chama nenhum st.* — por isso
é a única testável automaticamente, mesmo padrão já usado em
test_page_chat_escape.py para _escapar_cifrao.
"""

from src.core.enums import Intent, LeadStatus
from src.ui.page_dashboard import (
    _ROTULO_INTENCAO,
    _ROTULO_STATUS,
    _serie,
)


class TestSerie:

    def test_converte_chave_para_rotulo_legivel(self):
        contagens = {str(LeadStatus.QUALIFICADO): 3, str(LeadStatus.NOVO): 1}

        resultado = _serie(contagens, _ROTULO_STATUS)

        assert dict(resultado) == {"Qualificado": 3, "Novo": 1}

    def test_chave_sem_rotulo_mapeado_usa_valor_bruto(self):
        """Dado inesperado no banco não derruba a página — cai no
        valor bruto em vez de lançar KeyError."""
        contagens = {"algo_nao_mapeado": 2}

        resultado = _serie(contagens, _ROTULO_STATUS)

        assert dict(resultado) == {"algo_nao_mapeado": 2}

    def test_dicionario_vazio_produz_serie_vazia(self):
        resultado = _serie({}, _ROTULO_INTENCAO)

        assert len(resultado) == 0

    def test_funciona_com_qualquer_dos_dicionarios_de_rotulo(self):
        """Confirma que a função é genérica — não amarrada a um enum
        específico. Testa com _ROTULO_INTENCAO, diferente do teste
        principal (que usa _ROTULO_STATUS)."""
        contagens = {str(Intent.COMPRA): 5}

        resultado = _serie(contagens, _ROTULO_INTENCAO)

        assert dict(resultado) == {"Compra": 5}

    def test_e_a_funcao_realmente_usada_no_modulo(self):
        """Confirma que a função testada é a mesma referenciada nos
        pontos de renderização — não uma cópia isolada."""
        import inspect
        from src.ui import page_dashboard

        codigo_funil = inspect.getsource(page_dashboard._renderizar_funil)
        codigo_eventos = inspect.getsource(page_dashboard._renderizar_eventos)

        assert "_serie(funil[" in codigo_funil
        assert "_serie(eventos, _ROTULO_EVENTOS)" in codigo_eventos