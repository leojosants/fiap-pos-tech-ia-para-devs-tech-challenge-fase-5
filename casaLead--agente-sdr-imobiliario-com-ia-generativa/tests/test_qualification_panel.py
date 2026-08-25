"""Testes de _formatar() (qualification_panel.py).

Única função pura do módulo (sem chamada a st.*) — mesmo padrão já
aplicado em page_dashboard.py, page_broker.py e page_chat.py. Não
existia teste para ela antes desta etapa; adicionado por consistência
ao tocar no arquivo para exibir score/temperatura.
"""

from src.ui.components.qualification_panel import _formatar


class TestFormatar:

    def test_valor_monetario_float_formata_como_reais(self):
        assert _formatar(850_000.0) == "R$ 850.000"

    def test_expectativa_retorno_formata_como_percentual(self):
        assert _formatar(7.5, slot="expectativa_retorno") == "7.5% ao ano"

    def test_lista_junta_valores_com_virgula(self):
        assert _formatar(["piscina", "varanda"]) == "piscina, varanda"

    def test_string_com_underscore_vira_texto_capitalizado(self):
        assert _formatar("curto_prazo") == "Curto prazo"

    def test_inteiro_nao_monetario_vira_string_simples(self):
        assert _formatar(3) == "3"