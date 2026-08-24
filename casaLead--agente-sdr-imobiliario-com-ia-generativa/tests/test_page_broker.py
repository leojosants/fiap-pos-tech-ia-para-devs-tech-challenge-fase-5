"""Testes de _resumir_resultados() (page_broker.py).

Única parte de page_broker.py que não chama nenhum st.* — mesmo padrão
já usado para _serie() (page_dashboard.py) e _escapar_cifrao()
(page_chat.py): só a lógica pura de um módulo de UI é testável de
forma automatizada.
"""

from src.followup.followup_manager import ResultadoFollowup
from src.ui.page_broker import _resumir_resultados


def _resultado(acao: str, lead_id: int = 1) -> ResultadoFollowup:
    return ResultadoFollowup(lead_id=lead_id, acao=acao)


class TestResumirResultados:

    def test_lista_vazia_devolve_zeros(self):
        resultado = _resumir_resultados([])

        assert resultado == {"total": 0, "enviados": 0, "escalados": 0}

    def test_conta_envios_e_escaladas_separadamente(self):
        resultados = [
            _resultado("enviado", lead_id=1),
            _resultado("enviado", lead_id=2),
            _resultado("escalado", lead_id=3),
        ]

        resultado = _resumir_resultados(resultados)

        assert resultado == {"total": 3, "enviados": 2, "escalados": 1}

    def test_acao_nenhuma_conta_no_total_mas_nao_em_envio_ou_escalada(self):
        resultados = [_resultado("nenhuma", lead_id=1)]

        resultado = _resumir_resultados(resultados)

        assert resultado == {"total": 1, "enviados": 0, "escalados": 0}

    def test_e_a_funcao_realmente_usada_no_modulo(self):
        """Confirma que a função testada é a mesma referenciada no
        ponto de exibição do resultado — não uma cópia isolada."""
        import inspect
        from src.ui import page_broker

        codigo = inspect.getsource(page_broker._exibir_resultado_followup)

        assert "_resumir_resultados(resultados)" in codigo