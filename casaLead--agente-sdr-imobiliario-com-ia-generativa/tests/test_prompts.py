"""Testes do prompt de sistema — foco no que mudou no Passo 3.

Não testa o conteúdo integral do prompt (isso seria frágil e acoplado
demais ao texto exato da persona). Testa apenas os pontos de contrato
que o resto do sistema depende: presença/ausência dos blocos e da
exceção de agendamento na regra de horário.
"""

from src.core.enums import Intent, Zone
from src.core.models import Lead
from src.llm.prompts import montar_prompt_sistema


def _lead_com_intencao_definida() -> Lead:
    """Evita o roteiro de intenção indefinida, que suprime o contexto
    de slots e deixa o teste mais difícil de ler."""
    return Lead(nome="Ana", intent=Intent.COMPRA, zona_interesse=Zone.SUL)


class TestExcecaoDeHorarioNaPersona:
    """A regra geral (não prometer horário) deve seguir presente sempre;
    a exceção só deve aparecer condicionada ao bloco de confirmação."""

    def test_regra_geral_de_nao_prometer_horario_permanece(self):
        prompt = montar_prompt_sistema(_lead_com_intencao_definida())
        assert "Não afirme, por conta própria" in prompt
        # a exceção cita o bloco pelo nome — mesmo sem agendamento_contexto
        # neste turno, a regra da persona precisa estar sempre presente
        assert "COMPROMISSO CONFIRMADO NESTE TURNO" in prompt

    def test_excecao_referencia_o_nome_exato_do_bloco(self):
        """A exceção da persona precisa citar o mesmo texto de prefixo
        que o scheduling_agent usa — senão o LLM não teria como associar
        os dois. Este teste amarra as duas pontas."""
        from src.agents.scheduling_agent import ResultadoAgendamento
        from src.core.enums import AppointmentType
        from src.core.models import Appointment
        from datetime import datetime

        ap = Appointment(
            id=1, lead_id=1, tipo=AppointmentType.REUNIAO_ONLINE,
            data_hora=datetime(2026, 8, 21, 15, 0),
        )
        from src.agents.scheduling_agent import SchedulingAgent

        resultado = ResultadoAgendamento(appointment=ap, ja_existia=False)
        bloco = SchedulingAgent.formatar_para_prompt(resultado)

        # a persona menciona esse prefixo exato como a única condição
        # que autoriza confirmar um horário
        prompt = montar_prompt_sistema(_lead_com_intencao_definida())
        prefixo = bloco.splitlines()[0]
        assert prefixo in prompt


class TestBlocoDeAgendamentoNoPrompt:

    def test_sem_agendamento_contexto_bloco_nao_aparece(self):
        prompt = montar_prompt_sistema(_lead_com_intencao_definida())
        assert "HORÁRIOS SUGERIDOS" not in prompt

    def test_compromisso_confirmado_gera_instrucao_de_afirmar(self):
        bloco = (
            "COMPROMISSO CONFIRMADO NESTE TURNO\n"
            "Tipo: reunião online\n"
            "Quando: sexta-feira, 21/08 às 15h00"
        )
        prompt = montar_prompt_sistema(
            _lead_com_intencao_definida(), agendamento_contexto=bloco
        )

        assert bloco in prompt
        assert "ÚNICO horário que você pode confirmar" in prompt
        assert "não invente" in prompt.lower()

    def test_sugestoes_geram_instrucao_de_oferecer_sem_confirmar(self):
        bloco = (
            "HORÁRIOS SUGERIDOS NESTE TURNO\n"
            "- terça-feira, 25/08 às 10h00\n"
            "- terça-feira, 25/08 às 15h00"
        )
        prompt = montar_prompt_sistema(
            _lead_com_intencao_definida(), agendamento_contexto=bloco
        )

        assert bloco in prompt
        assert "PROIBIDO sugerir qualquer horário" in prompt
        assert "não copie a lista literalmente" in prompt.lower()

    def test_sugestoes_nao_usam_instrucao_de_compromisso_confirmado(self):
        bloco = "HORÁRIOS SUGERIDOS NESTE TURNO\n- terça-feira, 25/08 às 10h00"
        prompt = montar_prompt_sistema(
            _lead_com_intencao_definida(), agendamento_contexto=bloco
        )
        assert "ÚNICO horário que você pode confirmar" not in prompt

    def test_agendamento_e_imoveis_contexto_coexistem(self):
        """Os dois blocos podem aparecer no mesmo turno (ex.: recomendação
        de imóvel e sugestão de horário no mesmo prompt) sem um sobrescrever
        o outro."""
        bloco_agendamento = "HORÁRIOS SUGERIDOS NESTE TURNO\n- terça, 10h"
        prompt = montar_prompt_sistema(
            _lead_com_intencao_definida(),
            imoveis_contexto="CL0001 | Apartamento em Moema",
            agendamento_contexto=bloco_agendamento,
        )

        assert "IMÓVEIS ENCONTRADOS" in prompt
        assert bloco_agendamento in prompt


class TestCompatibilidadeRetroativa:
    """Garante que quem já chama montar_prompt_sistema sem o novo
    parâmetro (código existente, ainda não migrado) continua funcionando."""

    def test_chamada_sem_agendamento_contexto_nao_quebra(self):
        prompt = montar_prompt_sistema(_lead_com_intencao_definida())
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_chamada_so_com_imoveis_contexto_continua_igual(self):
        prompt = montar_prompt_sistema(
            _lead_com_intencao_definida(),
            imoveis_contexto="CL0001 | Apartamento em Moema",
        )
        assert "IMÓVEIS ENCONTRADOS" in prompt