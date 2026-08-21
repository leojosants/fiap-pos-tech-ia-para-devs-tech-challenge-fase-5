"""Testes de _escapar_cifrao (page_chat.py).

Bug real encontrado em teste manual na interface: a fala da Sofia
mencionando "R$" mais de uma vez na mesma mensagem acionava a
renderização de fórmula LaTeX do Streamlit, escondendo parte do texto
— mesma causa raiz do bug #21 já documentado, que só havia sido
corrigido em property_card.py, não na bolha de chat.
"""

from src.ui.page_chat import _escapar_cifrao


class TestEscaparCifrao:

    def test_string_sem_cifrao_nao_muda(self):
        texto = "Entendi, você quer comprar na zona sul."
        assert _escapar_cifrao(texto) == texto

    def test_um_cifrao_e_escapado(self):
        texto = "Até R$ 500.000"
        assert _escapar_cifrao(texto) == "Até R\\$ 500.000"

    def test_dois_cifroes_ambos_escapados(self):
        """O caso real que causava o bug: duas ocorrências de R$ na
        mesma mensagem acionavam o modo LaTeX do Streamlit."""
        texto = "Orçamento até R$ 320.000, ou R$ 1.500/mês de aluguel"
        resultado = _escapar_cifrao(texto)

        assert resultado.count("\\$") == 2
        assert "$" not in resultado.replace("\\$", "")

    def test_preserva_o_resto_do_texto_integralmente(self):
        texto = "Seu horário confirmado é sexta-feira, 21/08, às 10h00."
        assert _escapar_cifrao(texto) == texto  # sem $, nada muda

    def test_string_vazia_nao_quebra(self):
        assert _escapar_cifrao("") == ""

    def test_e_a_funcao_realmente_usada_no_modulo(self):
        """Confirma que a função testada é a mesma referenciada nos
        pontos de renderização — não uma cópia isolada."""
        import inspect
        from src.ui import page_chat

        codigo_processar = inspect.getsource(page_chat._processar_entrada)
        codigo_renderizar = inspect.getsource(page_chat.renderizar)

        assert "_escapar_cifrao(resultado.resposta)" in codigo_processar
        assert '_escapar_cifrao(mensagem["content"])' in codigo_renderizar