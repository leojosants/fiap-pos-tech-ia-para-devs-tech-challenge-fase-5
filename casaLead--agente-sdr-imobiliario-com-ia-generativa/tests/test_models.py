"""Testes dos modelos de domínio (src/core/models.py).

Módulo 100% puro — sem banco, sem I/O. Escopo destes testes:

1. `Property`: as duas propriedades calculadas (`preco_m2`,
   `custo_mensal_total`) e `texto_para_busca()`, a base textual
   consumida pelo retriever TF-IDF (Etapa 4/RAG) — se essa junção de
   campos quebrar, a busca semântica degrada silenciosamente, sem
   nenhum teste hoje detectando.
2. `Lead`: a lógica de completude de qualificação
   (`slots_relevantes`, `_slot_preenchido`, `slots_status`,
   `completude`) — usada tanto pelo painel lateral do chat quanto
   pelo motor de scoring (peso "completude", 30 pontos, Etapa 5).
   Já validada indiretamente por `test_scoring_rules.py`, mas nunca
   isolada e testada como unidade própria de `models.py`.
3. Uma classe de regressão para o erro clássico de dataclass —
   campos com `default_factory=list`/`dict` compartilhados
   acidentalmente entre instâncias quando declarados como `= []`/`{}`
   em vez de `field(default_factory=...)`. Os modelos já usam
   `field(default_factory=...)` corretamente; este teste garante que
   uma edição futura não reintroduza o bug.

Não testa geração de `id` nem persistência — isso é responsabilidade
de `src/persistence/`, com seus próprios testes.
"""

from src.core.enums import (
    AppointmentStatus,
    ConversationStatus,
    FollowupStatus,
    Intent,
    InvestmentGoal,
    InvestorProfile,
    Operation,
    PropertyType,
    Urgency,
    Zone,
)
from src.core.models import (
    Appointment,
    AppointmentType,
    Conversation,
    Event,
    EventType,
    Followup,
    Lead,
    Message,
    MessageRole,
    Property,
)


def _imovel(**overrides) -> Property:
    """Fábrica de Property com valores mínimos válidos para os testes."""
    base = dict(
        codigo="AP-001",
        titulo="Apartamento 2 quartos",
        tipo=PropertyType.APARTAMENTO,
        operacao=Operation.VENDA,
        zona=Zone.SUL,
        bairro="Moema",
        endereco_aproximado="Rua das Flores",
    )
    base.update(overrides)
    return Property(**base)


class TestPropertyPrecoM2:

    def test_calcula_preco_por_metro_quadrado_quando_ha_venda_e_area(self):
        imovel = _imovel(preco_venda=500_000.0, area_util=100.0)
        assert imovel.preco_m2 == 5_000.0

    def test_arredonda_para_duas_casas_decimais(self):
        imovel = _imovel(preco_venda=333_333.0, area_util=70.0)
        assert imovel.preco_m2 == round(333_333.0 / 70.0, 2)

    def test_none_quando_falta_preco_de_venda(self):
        imovel = _imovel(preco_venda=None, area_util=100.0)
        assert imovel.preco_m2 is None

    def test_none_quando_falta_area_util(self):
        imovel = _imovel(preco_venda=500_000.0, area_util=0.0)
        assert imovel.preco_m2 is None


class TestPropertyCustoMensalTotal:

    def test_soma_aluguel_condominio_e_iptu_rateado(self):
        imovel = _imovel(preco_aluguel=2_000.0, condominio=500.0, iptu=1_200.0)
        assert imovel.custo_mensal_total == round(2_000.0 + 500.0 + (1_200.0 / 12), 2)

    def test_none_quando_nao_ha_operacao_de_aluguel(self):
        imovel = _imovel(preco_aluguel=None)
        assert imovel.custo_mensal_total is None

    def test_funciona_mesmo_sem_condominio_ou_iptu_informados(self):
        imovel = _imovel(preco_aluguel=1_500.0)
        assert imovel.custo_mensal_total == 1_500.0


class TestPropertyTextoParaBusca:

    def test_junta_titulo_localizacao_atributos_e_descricao(self):
        imovel = _imovel(
            titulo="Studio moderno",
            bairro="Pinheiros",
            zona=Zone.OESTE,
            quartos=1,
            vagas=1,
            area_util=35.0,
            caracteristicas=["varanda", "pet friendly"],
            descricao="Reformado recentemente",
        )
        texto = imovel.texto_para_busca()

        assert "Studio moderno" in texto
        assert "Pinheiros" in texto
        assert "oeste" in texto
        assert "varanda" in texto
        assert "pet friendly" in texto
        assert "Reformado recentemente" in texto

    def test_ignora_partes_vazias_sem_gerar_separadores_soltos(self):
        # Sem características e sem descrição — as duas partes vazias
        # não devem aparecer como " |  | " no meio do texto.
        imovel = _imovel(caracteristicas=[], descricao="")
        texto = imovel.texto_para_busca()

        assert " |  | " not in texto
        assert not texto.endswith("|")


class TestLeadSlotsRelevantes:

    def test_intent_compra_usa_slots_de_compra(self):
        lead = Lead(intent=Intent.COMPRA)
        assert lead.slots_relevantes() == Lead.SLOTS_COMPRA

    def test_intent_aluguel_tambem_usa_slots_de_compra(self):
        # Compra e aluguel compartilham o mesmo conjunto de slots —
        # comportamento documentado no README (seção de critérios de
        # qualificação), não uma omissão.
        lead = Lead(intent=Intent.ALUGUEL)
        assert lead.slots_relevantes() == Lead.SLOTS_COMPRA

    def test_intent_indefinida_usa_slots_de_compra_como_padrao(self):
        lead = Lead(intent=Intent.INDEFINIDA)
        assert lead.slots_relevantes() == Lead.SLOTS_COMPRA

    def test_intent_investimento_usa_slots_de_investimento(self):
        lead = Lead(intent=Intent.INVESTIMENTO)
        assert lead.slots_relevantes() == Lead.SLOTS_INVESTIMENTO


class TestLeadSlotPreenchido:

    def test_slot_none_nao_conta_como_preenchido(self):
        lead = Lead(intent=Intent.COMPRA, zona_interesse=None)
        assert lead.slots_status()["zona_interesse"] is False

    def test_slot_string_vazia_nao_conta_como_preenchido(self):
        lead = Lead(intent=Intent.COMPRA, disponibilidade_reuniao="")
        assert lead.slots_status()["disponibilidade_reuniao"] is False

    def test_slot_string_preenchida_conta_como_preenchido(self):
        lead = Lead(intent=Intent.COMPRA, disponibilidade_reuniao="sábado de manhã")
        assert lead.slots_status()["disponibilidade_reuniao"] is True

    def test_enum_nao_informado_nao_conta_como_preenchido(self):
        lead = Lead(
            intent=Intent.INVESTIMENTO,
            perfil_investidor=InvestorProfile.NAO_INFORMADO,
        )
        assert lead.slots_status()["perfil_investidor"] is False

    def test_enum_com_valor_declarado_conta_como_preenchido(self):
        lead = Lead(
            intent=Intent.INVESTIMENTO,
            perfil_investidor=InvestorProfile.CONSERVADOR,
        )
        assert lead.slots_status()["perfil_investidor"] is True

    def test_numero_zero_conta_como_preenchido(self):
        # Comportamento atual documentado: 0 não é None, "" nem [],
        # então passa a checagem de _slot_preenchido. Um lead que
        # declara "zero vagas" é uma resposta válida, não uma ausência
        # de resposta — este teste fixa esse comportamento existente.
        lead = Lead(intent=Intent.COMPRA, quartos_desejados=0)
        assert lead.slots_status()["quartos_desejados"] is True

    def test_lista_vazia_nao_conta_como_preenchido(self):
        # bairros_interesse não é slot de completude hoje, mas a regra
        # de lista vazia se aplica a qualquer slot futuro do tipo lista
        # — testado diretamente via _slot_preenchido.
        lead = Lead()
        assert lead._slot_preenchido("bairros_interesse") is False


class TestLeadCompletude:

    def test_lead_totalmente_vazio_tem_completude_zero(self):
        lead = Lead()
        assert lead.completude() == 0.0

    def test_lead_compra_com_todos_os_slots_tem_completude_total(self):
        lead = Lead(
            intent=Intent.COMPRA,
            zona_interesse=Zone.SUL,
            preco_max=500_000.0,
            quartos_desejados=2,
            urgencia=Urgency.IMEDIATA,
            disponibilidade_reuniao="sábado de manhã",
        )
        assert lead.completude() == 1.0

    def test_lead_compra_com_metade_dos_slots_tem_completude_parcial(self):
        # SLOTS_COMPRA tem 5 itens; preenchendo zona e preço = 2/5 = 0.4
        lead = Lead(
            intent=Intent.COMPRA,
            zona_interesse=Zone.SUL,
            preco_max=500_000.0,
        )
        assert lead.completude() == 2 / 5

    def test_lead_investimento_calcula_sobre_slots_de_investimento(self):
        lead = Lead(
            intent=Intent.INVESTIMENTO,
            perfil_investidor=InvestorProfile.MODERADO,
            ticket_disponivel=600_000.0,
            objetivo_investimento=InvestmentGoal.RENDA,
            expectativa_retorno=7.0,
            prazo_investimento="próximos meses",
        )
        assert lead.completude() == 1.0


class TestCamposMutaveisPadraoNaoCompartilhados:
    """Regressão contra o erro clássico de dataclass: default mutável
    compartilhado entre instâncias quando declarado como `= []` em vez
    de `field(default_factory=list)`. Os modelos já usam a forma
    correta — este teste protege contra reintrodução futura do bug."""

    def test_bairros_interesse_nao_e_compartilhado_entre_leads(self):
        lead_a = Lead()
        lead_b = Lead()

        lead_a.bairros_interesse.append("Moema")

        assert lead_a.bairros_interesse == ["Moema"]
        assert lead_b.bairros_interesse == []

    def test_preferencias_nao_e_compartilhado_entre_leads(self):
        lead_a = Lead()
        lead_b = Lead()

        lead_a.preferencias.append("aceita pet")

        assert lead_b.preferencias == []

    def test_caracteristicas_nao_e_compartilhado_entre_imoveis(self):
        imovel_a = _imovel()
        imovel_b = _imovel()

        imovel_a.caracteristicas.append("varanda")

        assert imovel_a.caracteristicas == ["varanda"]
        assert imovel_b.caracteristicas == []

    def test_detalhes_do_evento_nao_e_compartilhado_entre_eventos(self):
        evento_a = Event(tipo=EventType.LEAD_CRIADO)
        evento_b = Event(tipo=EventType.LEAD_CRIADO)

        evento_a.detalhes["origem"] = "site"

        assert evento_b.detalhes == {}


class TestValoresPadraoDosDemaisModelos:
    """Um teste de sanidade por dataclass restante — confirma que o
    valor padrão declarado é de fato o que o construtor produz sem
    argumentos opcionais, para os campos com regra de negócio embutida
    no valor padrão (não apenas presença do campo)."""

    def test_conversation_comeca_ativa(self):
        conversa = Conversation(lead_id=1)
        assert conversa.status == ConversationStatus.ATIVA
        assert conversa.ended_at is None

    def test_message_sem_rastreabilidade_de_llm_por_padrao(self):
        mensagem = Message(conversation_id=1, role=MessageRole.LEAD, content="Oi")
        assert mensagem.modelo_usado == ""
        assert mensagem.latencia_ms == 0

    def test_appointment_comeca_agendado(self):
        from datetime import datetime

        compromisso = Appointment(
            lead_id=1, tipo=AppointmentType.VISITA_IMOVEL, data_hora=datetime.now()
        )
        assert compromisso.status == AppointmentStatus.AGENDADO

    def test_followup_comeca_pendente_e_sem_envio(self):
        followup = Followup(
            lead_id=1, conversation_id=1, tentativa=1, mensagem="Oi, tudo bem?"
        )
        assert followup.status == FollowupStatus.PENDENTE
        assert followup.enviado_em is None