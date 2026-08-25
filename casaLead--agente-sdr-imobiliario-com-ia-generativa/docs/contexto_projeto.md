# Documento de Contexto — CasaLead

> **Uso:** cole este documento no início de uma nova conversa, junto com as
> Instruções do Projeto, para retomar o desenvolvimento sem perda de contexto.
> Atualize ao final de cada etapa concluída.

**Última atualização:** fim da Etapa 7
**Repositório:** `git@github.com:leojosants/fiap-pos-tech-ia-para-devs-tech-challenge-fase-5.git`
**Branch de trabalho:** `development` (merge para `main` apenas na entrega final)

> **Reorganização de pastas (Etapa 7):** todo o código-fonte do projeto
> foi movido para dentro de `casaLead--agente-sdr-imobiliario-com-ia-generativa/`,
> na raiz do repositório — só `README.md` permanece fora, na raiz, porque é
> o único arquivo que o GitHub renderiza automaticamente como página
> inicial do repositório. Motivo da mudança: dar ao código um nome de
> produto, mantendo o nome técnico do repositório (herdado do Tech
> Challenge Fase 4) intacto. Movido com `git mv` para preservar o
> histórico de cada arquivo. Detalhe completo em `docs/decisoes_tecnicas.md`,
> seção 6f.

---

## 1. Identificação

| Item | Valor |
| --- | --- |
| Projeto | CasaLead — Agente SDR Imobiliário com IA Generativa |
| Aluno | Leonardo José de Oliveira Santos — RM369985 |
| Curso | FIAP — Pós Tech em IA para Devs (Hackathon) |
| Padrão de entrega | Mesmo do Tech Challenge Fase 4 (MedWatch): README robusto, relatório técnico em PDF, app publicada no Streamlit Cloud, sem vídeo |

## 2. Ambiente confirmado

```md
Python 3.12.9
uv 0.11.3
git 2.45.2.windows.1
Windows · PowerShell e Git Bash
Diretório: D:\REPOS-GITHUB-PUBLICO\fiap-pos-tech-ia-para-devs-tech-challenge-fase-5\casaLead--agente-sdr-imobiliario-com-ia-generativa
```

**Regras operacionais:**

- Sempre `uv add` / `uv run`; nunca `pip` puro nem venv manual
- Scripts executados como módulo: `uv run python -m scripts.x`
- Após alterar arquivo `.py`, **reiniciar o servidor Streamlit por completo** (`Ctrl+C`, aguardar o processo encerrar, subir de novo) — confirmado na prática na Etapa 7: um simples refresh do navegador, com o processo antigo ainda rodando, não é suficiente; o hot-reload do Streamlit pode não pegar a mudança
- Testes de linha de comando rodam em processo separado; não exigem parar o servidor
- Variáveis de ambiente no PowerShell: `$env:DEMO_MODE="true"`
- `pyproject.toml`, `.venv` e `pytest.ini` agora vivem dentro da subpasta do código (ver nota de reorganização acima) — todo comando `uv run ...` precisa ser executado de dentro dela

## 3. Stack e modelos

| Camada | Tecnologia |
| --- | --- |
| Interface | Streamlit 1.61.1 |
| Persistência | SQLite (`sqlite3` puro, sem ORM) |
| LLM conversa | Groq · `openai/gpt-oss-20b` |
| LLM raciocínio | Groq · `openai/gpt-oss-120b` |
| Busca semântica | `scikit-learn` (TF-IDF) |
| Testes | `pytest` |

**Dependências instaladas:** `streamlit`, `python-dotenv`, `groq`, `scikit-learn`, `pytest` (dev)

**Decisões firmadas:** sem LangChain (avaliado e descartado); sem OpenAI API; sem `sentence-transformers` (incompatível com o deploy); scoring de leads por regras explícitas, não por `scikit-learn` treinado (sem dados reais de conversão — ver seção 9).

---

## 4. Estado das etapas

| # | Etapa | Status |
| --- | --- | --- |
| 0 | Fundação do repositório | ✅ |
| 1 | Base de imóveis e persistência | ✅ |
| 2 | Motor conversacional (Groq + modo demo) | ✅ |
| 3 | Orquestração e qualificação | ✅ |
| 3.6 | Interface de chat (antecipada) | ✅ |
| 4 | Recomendação de imóveis (RAG) | ✅ |
| 5 | Classificação e priorização de leads | ✅ |
| 6 | Agendamento, follow-up e resumo | ✅ |
| 7 | Dashboard e observabilidade | ✅ |
| 8 | Testes, documentação e deploy | ⬜ **próxima** |

### Requisitos do enunciado

| Requisito | Status |
| --- | --- |
| Atendimento conversacional | ✅ |
| Conversa natural e humanizada | ✅ |
| Continuidade e memória do contexto | ✅ |
| Identificação de intenção | ✅ |
| Qualificação de leads | ✅ |
| Consulta à base simulada de imóveis (RAG) | ✅ |
| Classificação/priorização de leads | ✅ |
| Agendamento de reuniões ou visitas | ✅ |
| Follow-up automático | ✅ |
| Resumo inteligente para o corretor | ✅ |
| Dashboard mínimo | ✅ |

---

## 5. Estrutura atual do repositório

```md
├── README.md                       # única exceção — fica FORA da subpasta (ver nota no topo)
└── casaLead--agente-sdr-imobiliario-com-ia-generativa/
    ├── data/
    │   ├── seed/properties.json        # 60 imóveis sintéticos (versionado)
    │   └── runtime/casalead.db         # banco gerado (gitignored)
    ├── docs/
    │   ├── decisoes_tecnicas.md        # decisões, bugs, limitações, métricas
    │   └── contexto_projeto.md         # este documento
    ├── scripts/
    │   ├── generate_properties.py      # gerador determinístico (seed=369985)
    │   ├── validar_scoring.py          # inspeção manual do scoring (Etapa 5)
    │   ├── validar_agendamento_followup_resumo.py  # inspeção manual, banco isolado (Etapa 6)
    │   └── validar_followup_producao.py            # idem, contra banco de produção real (Etapa 6)
    ├── src/
    │   ├── core/
    │   │   ├── enums.py                # Intent, LeadStatus, Zone, EventType...
    │   │   ├── models.py               # Lead, Property, Conversation, Message, Appointment, Followup, Event
    │   │   └── config.py               # Settings + detecção de modo demo
    │   ├── persistence/
    │   │   ├── database.py             # schema (7 tabelas) + bootstrap idempotente
    │   │   ├── property_repository.py  # busca estruturada + investimento
    │   │   ├── lead_repository.py      # CRUD + estatísticas de funil + buscar_inativos()
    │   │   ├── conversation_repository.py  # conversas, mensagens, eventos
    │   │   ├── appointment_repository.py   # agendamentos + listar_proximos()
    │   │   └── followup_repository.py      # tentativas de follow-up
    │   ├── llm/
    │   │   ├── groq_client.py          # cliente + retry + UsageStats (inclui resumir())
    │   │   ├── prompts.py              # persona Sofia, roteiros, PROMPT_EXTRACAO, PROMPT_RESUMO_CORRETOR
    │   │   └── demo_engine.py          # motor determinístico + detectores regex
    │   ├── agents/
    │   │   ├── qualification_agent.py  # extração híbrida regex + LLM
    │   │   ├── conversation_agent.py   # geração de fala + fallback
    │   │   ├── scheduling_agent.py     # interpretação de disponibilidade
    │   │   └── orchestrator.py         # coordenação do turno + propriedades públicas — ALTERADO (Etapa 7)
    │   ├── followup/
    │   │   └── followup_manager.py     # reengajamento de leads inativos
    │   ├── reporting/
    │   │   └── summarizer.py           # resumo para o corretor
    │   ├── recommendation/
    │   │   ├── retriever.py            # índice TF-IDF + expansão de sinônimos
    │   │   └── ranker.py               # filtro SQL + score semântico
    │   ├── scoring/
    │   │   ├── context.py              # dataclass ContextoScoring (dado externo)
    │   │   ├── rules.py                # regras explícitas puras + ResultadoScoring
    │   │   └── builder.py              # constrói ContextoScoring (única parte impura)
    │   ├── observability/
    │   │   └── metrics.py              # agregação de estatísticas p/ dashboard — NOVO (Etapa 7)
    │   └── ui/
    │       ├── state.py                # gestão de session_state
    │       ├── page_chat.py            # página de atendimento
    │       ├── page_dashboard.py       # funil, eventos, uso de LLM — NOVO (Etapa 7)
    │       ├── page_broker.py          # resumos, agenda, gatilho de follow-up — NOVO (Etapa 7)
    │       └── components/
    │           ├── qualification_panel.py  # + score/temperatura — ALTERADO (Etapa 7)
    │           └── property_card.py
    ├── tests/
    │   ├── test_property_repository.py         # 21 testes
    │   ├── test_scoring_rules.py                # 6 testes — motor puro, sem banco
    │   ├── test_scoring_builder.py              # 2 testes — integração com SQLite real
    │   ├── test_appointment_repository.py       # 25 testes
    │   ├── test_scheduling_agent.py             # 42 testes
    │   ├── test_followup_repository.py          # 17 testes
    │   ├── test_followup_manager.py             # 25 testes
    │   ├── test_prompts.py                      # 9 testes
    │   ├── test_prompts_resumo.py               # 13 testes
    │   ├── test_conversation_agent.py           # 5 testes
    │   ├── test_summarizer.py                   # 16 testes
    │   ├── test_orchestrator_scheduling.py      # 8 testes
    │   ├── test_orchestrator_summary_followup.py  # 11 testes
    │   ├── test_qualification_agent_contexto.py   # 4 testes
    │   ├── test_orchestrator_contexto_extracao.py # 5 testes
    │   ├── test_page_chat_escape.py                # 6 testes
    │   ├── test_prompts_contato.py                 # 6 testes
    │   ├── test_metrics.py                         # 7 testes — NOVO (Etapa 7)
    │   ├── test_orchestrator_properties.py         # 8 testes — NOVO (Etapa 7)
    │   ├── test_page_dashboard.py                  # 5 testes — NOVO (Etapa 7)
    │   ├── test_page_broker.py                     # 4 testes — NOVO (Etapa 7)
    │   └── test_qualification_panel.py             # 5 testes — NOVO (Etapa 7)
    ├── .env.example
    ├── .gitattributes
    ├── main.py                         # + navegação multipágina (st.navigation) — ALTERADO (Etapa 7)
    └── pyproject.toml
```

**Pastas que deixaram de estar vazias:** `src/observability/` — agora contém `metrics.py`.

---

## 6. Arquitetura em uma página

```md
INTERFACE (Streamlit, navegação multipágina st.navigation — Etapa 7)
  💬 Atendimento          📊 Dashboard           🧑‍💼 Corretor
  page_chat                page_dashboard         page_broker
  qualification_panel      (funil, eventos,       (resumos, agenda,
  property_card · state     uso de LLM)            botão de follow-up)
         ↓ ResultadoTurno        ↓                       ↓
         │              leitura via propriedades públicas do Orchestrator
         │              (leads, conversas, agendamentos, followups,
         │              imoveis, cliente — Etapa 7) → src.observability.metrics
         ↓                                              ↓
ORQUESTRADOR  ← única porta de entrada do domínio (escrita E leitura pública)
  persiste entrada → qualifica → recomenda → agenda → pontua
    → resume (se necessário) → gera resposta → persiste saída
         ↓                              ↓
AGENTES                          PERSISTÊNCIA
  qualification_agent              lead_repository
  conversation_agent               property_repository
  scheduling_agent                 conversation_repository
  followup_manager (sem            appointment_repository
   background real — chamado       followup_repository
   por botão na UI, Etapa 7,
   ou script; ver limitação 33)
         ↓                              ↓
CAMADA DE IA                     SQLite (9 tabelas)
  groq_client · prompts             + seed versionado
  demo_engine
         ↓
RECOMENDAÇÃO         SCORING              RESUMO
  retriever (TF-IDF)   rules.py (puro)      summarizer.py
  ranker (filtro)       builder.py (impuro)   (LLM → template)
```

**Degradação em dois níveis, em três agentes:**

1. Sem chave de API → opera integralmente no motor determinístico
   (`conversation_agent`) ou por template (`summarizer`)
2. Chave presente e chamada falha → degrada no turno afetado, volta ao
   LLM no seguinte

**Agendamento não usa LLM em nenhum nível** — interpretação de
disponibilidade é 100% determinística (regras, não modelo), decisão
firmada na seção 10.

---

## 7. Decisões estruturais já firmadas

| Tema | Decisão |
| --- | --- |
| Persistência | SQLite; repositório por entidade; nenhum módulo de negócio conhece SQL |
| Modelos | `dataclass` + `StrEnum`; modelo plano de `Lead` |
| Base de imóveis | 60 imóveis, 4 zonas de SP × 15, preço derivado de área × R$/m² do bairro |
| Extração | Híbrida: regex primeiro, LLM complementa, regex vence em campos numéricos |
| Modo demo | Motor determinístico por regras (não Ollama) |
| Recomendação | Filtro SQL → busca TF-IDF sobre candidatos; relaxamento progressivo em 6 níveis |
| Quando recomendar | A partir de 2 critérios estruturados (moradia) ou ticket informado (investimento) |
| Apresentação | Texto da Sofia + cards visuais; cabeçalho dos cards é determinístico |
| Princípio geral | O que pode ser determinístico não vai ao LLM (saudação, confirmação de intenção, cabeçalho dos cards, correção de gênero) |
| Scoring de leads | Regras de negócio explícitas (0–100, 6 sinais ponderados), não `scikit-learn` — sem dados reais de conversão para treinar um modelo que agregasse valor real |
| Scoring: pureza | `rules.py` puro (sem banco, sem LLM) recebe `ContextoScoring` já pronto; só `builder.py` acessa banco — permite testar as regras isoladamente |
| Scoring: frequência | Recalculado a cada turno (custo desprezível); evento `LEAD_CLASSIFICADO` registrado só quando a temperatura muda, não a cada turno |
| Interpretação de disponibilidade | Regras determinísticas (dia da semana, "amanhã"/"hoje", período do dia) — não LLM. Sem dependência nova, testável sem banco nem API, mesmo espírito do scoring. Cobertura de vocabulário é limitada por desenho (ver `docs/decisoes_tecnicas.md`) |
| Fallback de interpretação | Quando `disponibilidade_reuniao` (já persistida) não é interpretável, tenta a mensagem do turno atual (`texto_turno`) — o `QualificationAgent` só grava esse slot uma vez, então uma resposta a uma sugestão de horário não reabriria o campo sem esse segundo caminho |
| Contexto de agendamento no prompt | Só injetado no turno em que algo muda (acabou de confirmar, ou acabou de sugerir horários) — evita a Sofia repetir a confirmação a cada mensagem |
| Exceção à regra de não prometer horário | Condicionada à presença literal do bloco `COMPROMISSO CONFIRMADO NESTE TURNO` no prompt — o LLM só confirma data porque o sistema entregou pronta, nunca por inferência própria |
| Mensagem de follow-up | Determinística (template), não LLM — é mensagem proativa de background, não resposta a um turno de conversa; gastar uma chamada de API seria desproporcional |
| Limite de tentativas de follow-up | `MAX_TENTATIVAS = 2`; na 3ª verificação sem resposta, escala para atendimento humano |
| Escalada por follow-up | Altera só `ConversationStatus.ESCALADA`, não `LeadStatus` — `LeadStatus.ENCAMINHADO` já tem outro sentido (encaminhamento a especialista de investimento); misturar os dois confundiria o funil |
| Resumo do corretor | LLM (`model_smart`, via `GroqClient.resumir()`, já existente) quando disponível; degrada para template estruturado (reaproveita `montar_conteudo_resumo()`) no modo demo ou em falha de API — mesmo padrão de degradação do `conversation_agent` |
| Gatilho do resumo | Lead fica quente, agendamento é confirmado, ou follow-up escala — não a cada turno; e não quando a condição já valia antes (só na transição) |
| Repositório de agendamento compartilhado | `AppointmentRepository` instanciado uma vez no orquestrador, usado tanto por `SchedulingAgent` quanto por `Summarizer` — stateless por chamada, sem motivo para duas instâncias |
| Propriedades públicas de leitura no `Orchestrator` (Etapa 7) | `orquestrador.leads`, `.conversas`, `.imoveis`, `.agendamentos`, `.followups`, `.cliente` — somente leitura (`@property`, sem setter). Resolve o acesso direto a atributo privado que já existia (`page_chat` chamava `orquestrador._leads`) e dá às páginas novas um jeito limpo de consultar sem duplicar instância de repositório |
| Filtro de leads vazios no dashboard | Reaproveita `Lead.completude()`/`Lead.intent` em Python (não reimplementado em SQL) para excluir, por padrão, leads sem nenhuma interação — mesma decisão já tomada para o scoring (seção 6c): a regra de completude vive num só lugar, no domínio |
| Navegação multipágina via `st.navigation`/`st.Page` | Escolhida sobre `st.sidebar.radio` por gerar URL própria por página (`/_pagina_dashboard`, `/_pagina_corretor`) — ajuda na demonstração para a banca e é o mecanismo nativo do Streamlit desde a 1.36 |
| Threshold de follow-up com atalho de demonstração | Campo numérico de horas (padrão 24, comportamento real) + atalho de 1 minuto, visível só em modo demonstrativo — permite mostrar o ciclo completo de follow-up ao vivo sem esperar 24h de verdade |
| `pandas` usado sem declarar em `pyproject.toml` | Dependência obrigatória do próprio `streamlit` (não opcional — usada internamente por todo componente de dado/gráfico); `page_dashboard.py` importa o que o `streamlit` já garante, sem adicionar peso novo ao ambiente |

---

## 8. Comportamento validado na interface

Sete blocos de teste executados na UI, com ~23 bugs encontrados e corrigidos:

- **Compra (cenário 3.1):** progressão 0 → 100% em cinco turnos, sem repetir perguntas
- **Investimento (cenário 3.2):** quatro slots extraídos, cards financeiros, encaminhamento ao especialista
- **Intenção ambígua:** confirmação disparada quando o LLM infere sem termo explícito
- **Linguagem aberta:** relato de 340 palavras com ruído → sete atributos extraídos corretamente
- **Modo demonstrativo:** conversa completa sem nenhuma chamada de API
- **Robustez:** recusa de dados de terceiros, resistência a prompt injection, entradas mínimas e emojis
- **Persistência:** leads, conversas, mensagens e eventos recuperáveis

---

## 9. Etapa 5 — concluída

**Objetivo alcançado:** score (0–100) e temperatura (quente/morno/frio) calculados por regras de negócio explícitas, integrados ao fluxo real de conversa.

**Decisão firmada:** regras explícitas, não ML. Sem dados reais de conversão disponíveis, um classificador `scikit-learn` treinado em rótulos sintéticos gerados pelas próprias regras não agregaria poder preditivo real — e ainda adicionaria dependência de artefato serializado no deploy do Streamlit Cloud. Justificativa completa em `docs/decisoes_tecnicas.md`, seção 6c.

**Sinais e pesos (soma 100):**

| Sinal | Peso | Fonte |
| --- | --- | --- |
| Completude da qualificação | 30 | `Lead.completude()`, reaproveitado do domínio |
| Urgência declarada | 20 | Escala graduada sobre `Urgency` (imediata=20 → não informada=0) |
| Disponibilidade para reunião/visita | 20 | Binário — `disponibilidade_reuniao` preenchido ou vazio |
| Orçamento coerente com o mercado | 15 | Binário — consulta real a `PropertyRepository` (via `builder.py`) |
| Engajamento (turnos substantivos) | 10 | Proporcional, satura em 5 turnos |
| Intenção identificada | 5 | Binário — `Intent != INDEFINIDA` |

**Cortes de temperatura:** quente ≥ 70 · morno 40–69 · frio < 40.

**Arquivos implementados:**

- `src/scoring/context.py` — `ContextoScoring` (dataclass puro)
- `src/scoring/rules.py` — `calcular_score()`, 100% puro e testável sem banco
- `src/scoring/builder.py` — `construir_contexto()`, único ponto do módulo que acessa banco (`PropertyRepository`, `ConversationRepository`)
- `src/agents/orchestrator.py` — `_atualizar_score()` chamado uma vez por turno, ao final do processamento

**Testes:** `tests/test_scoring_rules.py` (6 testes, motor puro) e `tests/test_scoring_builder.py` (2 testes, integração com SQLite real via `tmp_path`). Todos passando.

**Validação end-to-end:** conferida via `scripts/validar_scoring.py` e, em seguida, numa conversa real na interface Streamlit — lead evoluiu `frio (0) → morno (42) → quente (96)` ao longo de 3 turnos, com 2 eventos `LEAD_CLASSIFICADO` registrados, cada um com o detalhamento por sinal.

**Integração já existente, confirmada:** o campo `score` e `temperature` já existiam no modelo `Lead` e na tabela desde etapas anteriores; `LeadRepository.listar()` já ordena por score decrescente — nenhuma mudança de schema foi necessária.

**Simplificações conscientes, registradas como limitações (`docs/decisoes_tecnicas.md`, itens 27–30):** disponibilidade e orçamento pontuam de forma binária, não graduada; intenção não distingue se houve confirmação explícita; cortes de temperatura são constantes fixas, não calibradas por dados reais.

**Pendente para uma etapa futura (não bloqueia o fechamento desta):** exibição visual de `score`/`temperature` na interface — fica para a Etapa 7 (dashboard), que já é o lugar planejado para isso.

---

## 10. Etapa 6 — concluída

**Objetivo alcançado:** os três requisitos que faltavam do enunciado — agendamento de reuniões/visitas, follow-up automático e resumo inteligente para o corretor — implementados, testados isoladamente e integrados de ponta a ponta no fluxo real de conversa.

**Ordem de implementação:** `appointment_repository.py` → `scheduling_agent.py` (interpretação + `formatar_para_prompt`) → ajuste em `prompts.py` (exceção à regra de horário) → `conversation_agent.py` (novo parâmetro) → integração no `orchestrator.py` (passo `[4.5]`) → `followup_repository.py` → `followup_manager.py` → `PROMPT_RESUMO_CORRETOR` + `montar_conteudo_resumo()` → `summarizer.py` → integração final no `orchestrator.py` (gatilhos de resumo + `executar_verificacao_followup`).

**Arquivos novos:**

- `src/persistence/appointment_repository.py` — CRUD de agendamentos; `proximo_agendamento_do_lead()` evita duplicar compromisso ativo
- `src/agents/scheduling_agent.py` — interpretação determinística de disponibilidade (dia da semana, período, horário explícito), geração de sugestões quando o texto é vago, `formatar_para_prompt()`
- `src/persistence/followup_repository.py` — CRUD de tentativas de follow-up; `marcar_enviado()` separado de `atualizar_status()` para não perder o carimbo de envio original
- `src/followup/followup_manager.py` — identifica leads inativos (`LeadRepository.buscar_inativos()`, já existente), decide reengajar ou escalar, mensagem por template
- `src/reporting/summarizer.py` — resumo via LLM (`GroqClient.resumir()`, que já existia, feito sob medida para isso) com degradação para template

**Arquivos modificados:**

- `src/llm/prompts.py` — exceção estreita à regra de não prometer horário; `PROMPT_RESUMO_CORRETOR` e `montar_conteudo_resumo()`
- `src/agents/conversation_agent.py` — novo parâmetro `agendamento_contexto`, repassado só ao caminho LLM
- `src/agents/orchestrator.py` — novo passo `[4.5]` (agendar); `_atualizar_score()` agora devolve `bool`; `_resumir_se_necessario()`; `executar_verificacao_followup()` (público, sem gatilho de UI ainda)

**Testes:** 16 arquivos novos, 103 testes (221 no total do projeto, contra 118 ao fim da Etapa 5) — ver contagem completa na estrutura do repositório (seção 5). Todos com banco SQLite real via `tmp_path`, sem mocks de banco.

**Dois bugs reais encontrados pelos próprios testes automatizados** (detalhe completo em `docs/decisoes_tecnicas.md`):

1. `"amanhã"` sendo interpretado como contendo `"manhã"` (substring) — corrigido com normalização de acentos + casamento por palavra inteira (`\b`)
2. Colisão de chave `"tipo"` entre o parâmetro posicional de `registrar_evento()` (tipo do evento) e uma chave do dicionário de detalhes do `scheduling_agent` (tipo do compromisso) — só apareceu no primeiro teste que exercitou a cadeia completa contra o banco real; corrigido renomeando para `"tipo_compromisso"`

**Decisão que atravessa os três módulos:** nenhum usa LLM para a lógica central — agendamento e follow-up são 100% determinísticos; o resumo usa LLM mas com degradação honesta (template, não uma tentativa de imitar prosa de IA). Mantém o princípio já firmado desde a Etapa 2: o que pode ser determinístico não vai ao modelo.

**Validação manual na interface: concluída.** Conversa real cobrindo:

- Cenário 3.1 compra — Blocos A/B/C do agendamento (horário interpretável com confirmação exata, disponibilidade vaga com sugestões sem confirmar, não duplicação de agendamento já confirmado)
- Cenário 3.1 aluguel — ciclo completo até 100% qualificado
- Cenário 3.2 investimento — ciclo completo até 100% qualificado, incluindo a pergunta de perfil de investidor (uma preocupação levantada durante a validação — que o roteiro nunca perguntasse sobre isso — não se confirmou)
- Correção do texto de encerramento (ver abaixo) validada nos dois caminhos: LLM genuíno e fallback determinístico
- Follow-up e resumo — sem nenhuma representação visual na interface ainda (pendência já conhecida) — validados por `scripts/validar_followup_producao.py` contra o **banco de produção real** (`data/runtime/casalead.db`), não um banco isolado: ciclo completo 1ª tentativa → 2ª tentativa → escalada → resumo automático, com `GroqClient` real

**Cinco bugs adicionais encontrados só na validação manual** (nenhum detectável por teste automatizado, por natureza — envolvem renderização visual, relógio real, ou encadeamento de duas falhas de LLM no mesmo turno; detalhe completo em `docs/decisoes_tecnicas.md`, itens 26–30):

1. `quartos_desejados` não capturado quando a resposta é um número isolado ("2") sem a palavra "quartos" junto — a extração por LLM não recebia contexto de qual pergunta estava sendo respondida. Corrigido com `ultima_pergunta_agente`, repassado só ao caminho LLM
2. Mensagens da Sofia cortando no meio quando mencionavam "R$" mais de uma vez — Streamlit interpreta `$` duplicado como delimitador LaTeX. Mesma causa do bug já corrigido no card de imóvel (Etapa 4), nunca corrigida na bolha de chat até agora
3. Três testes começaram a falhar sozinhos, sem mudança de código — usavam uma data absoluta fixa "no futuro" que o relógio real acabou alcançando durante a sessão. Trocado por `datetime.now() + timedelta(...)`
4. `PropertyRanker` ignorava o `db_path` customizado do `Orchestrator` (bug pré-existente da Etapa 4, só visível ao isolar banco em scripts de validação)
5. O encerramento da conversa prometia "um corretor entra em contato em breve" — mas nenhum ponto do sistema jamais coleta telefone ou e-mail do lead. Ajustado o texto (determinístico e instrução do LLM) para não prometer contato ativo — decisão registrada em `docs/decisoes_tecnicas.md`, seção 6e, junto com a alternativa descartada (adicionar coleta de contato ao roteiro)

**Observação quantificada, não uma medição precisa:** taxa de fallback do `model_fast` (`openai/gpt-oss-20b`) pareceu alta durante a sessão de teste manual (múltiplas ocorrências ao longo de ~30 turnos). Causa raiz não isolada — pode ser característica do modelo ou do provedor. Investigação de baixo custo proposta (trocar `model_fast` por outro modelo já disponível no Groq, antes de considerar migração de provedor) registrada como item futuro, não decidida nesta sessão.

**Pendente para uma etapa futura (não bloqueia o fechamento desta):**

- Threshold de inatividade do follow-up (`horas`) não é lido de variável de ambiente — precisa ser passado explicitamente por quem chama `executar_verificacao_followup()`. Sem atalho de `DEMO_MODE` para acelerar a demonstração ainda
- `executar_verificacao_followup()` não tem gatilho de UI — método pronto, sem botão/rotina que o acione. Fica para a Etapa 7
- Diferencial de calendário (link "Adicionar ao Google Calendar") discutido e adiado deliberadamente para depois do agendamento básico estar validado — ainda não implementado
- Entrada por voz (Voice AI) avaliada tecnicamente como viável (Groq Whisper + `st.audio_input` nativo do Streamlit, sem TTS — só entrada, saída continua em texto), adiada deliberadamente para não expandir escopo em cima do fechamento da Etapa 6
- Colisão entre `disponibilidade_reuniao` e `urgencia` quando a resposta de prazo tem "cara" de agendamento (dia da semana + período) — o regex vence sem saber a que pergunta o texto respondia. Efeito prático: repetição de pergunta, não perda de dado
- Motor determinístico pode repetir a mesma pergunta (só 2 opções por slot, sem memória da última escolhida) em quedas consecutivas — avaliado e conscientemente não corrigido (baixo impacto, evento raro e composto)
- Taxa de fallback do `model_fast` alta em teste manual, causa raiz não isolada — ver observação acima

---

## 11. Etapa 7 — concluída

**Objetivo alcançado:** dashboard mínimo (funil de leads, eventos, agenda, uso de LLM) e painel do corretor (resumos, agenda, gatilho manual de follow-up), navegação multipágina entre as três telas, e as duas pendências abertas desde as Etapas 5 e 6 — exibição visual de score/temperatura e gatilho de UI para follow-up — ambas resolvidas.

**Ordem de implementação:** `src/observability/metrics.py` (agregação pura) → propriedades públicas no `orchestrator.py` (pré-requisito de leitura para as páginas novas) → `page_dashboard.py` → `page_broker.py` → navegação em `main.py` → `qualification_panel.py` (score/temperatura).

**Arquivos novos:**

- `src/observability/metrics.py` — `funil_de_leads()`, `leads_com_interacao()`, `coletar()`; agrega as estatísticas já existentes nos repositórios (`LeadRepository`, `ConversationRepository`, `AppointmentRepository`, `FollowupRepository`, `GroqClient.stats`) sem reimplementar nenhuma
- `src/ui/page_dashboard.py` — funil por status/temperatura/intenção, eventos do sistema, agenda e follow-ups, uso de LLM; gráficos via `st.bar_chart` (usa `pandas`, dependência transitiva do `streamlit`)
- `src/ui/page_broker.py` — verificação manual de follow-up (com atalho de demonstração), agenda dos próximos 7 dias (`AppointmentRepository.listar_proximos()`, já deixado pronto na Etapa 6 exatamente para este uso), resumos gerados para o corretor

**Arquivos modificados:**

- `src/agents/orchestrator.py` — seis propriedades públicas de leitura (`leads`, `conversas`, `imoveis`, `agendamentos`, `followups`, `cliente`); `FollowupRepository` passou a ser guardado como atributo próprio (`self._followups_repo`), compartilhado com o `FollowupManager`, em vez de criado inline e inacessível de fora
- `src/ui/page_chat.py` — uma linha: `orquestrador._leads` → `orquestrador.leads`
- `main.py` — `st.navigation`/`st.Page` com três páginas (Atendimento, Dashboard, Corretor); funções wrapper para as duas páginas que recebem o orquestrador por injeção, já que `st.Page` exige uma função sem argumentos
- `src/ui/components/qualification_panel.py` — nova linha exibindo temperatura (emoji + texto) e score, usando `_CORES_TEMPERATURA` (já existia no arquivo, sem uso até então)

**Testes:** 5 arquivos novos, 29 testes (250 no total do projeto, contra 221 ao fim da Etapa 6). Todos os testes de UI desta etapa seguem o mesmo princípio já estabelecido em `test_page_chat_escape.py`: só a lógica pura de cada módulo (sem chamada a `st.*`) é testável automaticamente — `_serie()` (`page_dashboard`), `_resumir_resultados()` (`page_broker`), `_formatar()` (`qualification_panel`, que já existia sem teste e passou a ter um, por consistência com os demais módulos de UI).

**Um incidente de processo, não de código, ocorrido e resolvido durante a etapa:** ao colar o conteúdo completo de `orchestrator.py` numa entrega, ele acabou salvo por engano em `conversation_agent.py` no ambiente local do aluno — os dois arquivos ficaram com conteúdo trocado, quebrando toda a suíte com `ImportError` de importação circular (`conversation_agent.py` importando de si mesmo). Diagnosticado comparando byte a byte os arquivos que o aluno reenviou; resolvido reentregando os dois arquivos completos como download, com o caminho exato de cada um, em vez de blocos de código colados — reduz o risco de erro de cópia entre arquivos abertos simultaneamente no editor.

**Decisão que atravessa a etapa:** nenhuma tela nova processa lógica de negócio — `page_dashboard.py` e `page_broker.py` só leem, através das propriedades públicas do orquestrador, o que os agentes e repositórios já calculam e persistem. Mesmo princípio já firmado desde a arquitetura original (`ResultadoTurno` como contrato com a UI): a interface não sabe como o dado foi produzido, só como exibi-lo.

**Validação manual na interface: concluída.** Conversa real (cenário 3.1, compra) do zero até 100% qualificado, com agendamento confirmado no último turno, cobrindo:

- Navegação entre as três páginas sem conflito visual com o painel de qualificação já existente na barra lateral
- Dashboard refletindo o lead recém-criado sem reload do navegador — mesma instância de `Orchestrator` da sessão, confirmada pelo número de chamadas ao LLM batendo entre as duas telas
- Painel do corretor: agenda mostrando o compromisso confirmado, resumo automático gerado (gatilho "agendamento confirmado") aparecendo na lista, botão de verificação de follow-up testado contra o banco de produção real (31 leads processados, 10 reengajados, 0 escalados)
- Exibição de score/temperatura na barra lateral do chat — só confirmada depois de identificar que o servidor Streamlit precisava de restart completo (não bastava recarregar o navegador) para pegar a mudança de código; achado que reforça, na prática, a regra operacional já registrada na seção 2

**Reorganização de pastas, decidida e executada pelo aluno durante a etapa (fora do escopo técnico original):** todo o código movido para dentro de `casaLead--agente-sdr-imobiliario-com-ia-generativa/`, com `README.md` permanecendo na raiz do repositório. Feito em três passos — desfazer uma movimentação manual inicial → mover com `git mv`, preservando histórico → descartar e recriar o `.venv` (guarda caminho absoluto, não sobrevive à mudança de local). Detalhe completo, incluindo os comandos exatos usados, em `docs/decisoes_tecnicas.md`, seção 6f.

**Pendente para uma etapa futura (não bloqueia o fechamento desta):**

- `Orchestrator.diagnostico()` ainda acessa `self._cliente._settings` (atributo privado do `GroqClient`) — mesma família de pendência já registrada para `qualification_agent.py`; não corrigida nesta etapa porque exigiria alterar `GroqClient` também, fora do escopo definido para a Etapa 7
- Uso de LLM exibido no dashboard é a contagem da sessão atual do processo Streamlit (`GroqClient.stats`, em memória), não um histórico persistido — já sinalizado na própria tela, mas vale registrar como limitação de dado, não de interface
- Histórico de `git mv` de alguns arquivos `__init__.py` vazios não ficou perfeitamente limpo (o Git emparelhou deleção/criação de forma um pouco aleatória entre arquivos idênticos) — cosmético, não afeta conteúdo nem funcionamento

---

## 12. Etapa 8 — planejada

- Ampliar `tests/` (demo_engine, qualification_agent, ranker, groq_client)
- `requirements.txt` gerado do lock para o Streamlit Cloud
- Relatório técnico em PDF a partir de `docs/decisoes_tecnicas.md`
- Merge `development` → `main` e deploy

---

## 13. Pendências conhecidas

| Item | Observação |
| --- | --- |
| Encapsulamento — leitura | ✅ **Resolvido na Etapa 7.** `page_chat` acessava `orquestrador._leads`; corrigido com propriedades públicas no `Orchestrator` (`leads`, `conversas`, `imoveis`, `agendamentos`, `followups`, `cliente`) |
| Encapsulamento — `_cliente._settings` | Ainda pendente: `qualification_agent.py` e `Orchestrator.diagnostico()` continuam acessando `self._cliente._settings` diretamente. Fora do escopo da Etapa 7 (exigiria alterar `GroqClient`) |
| Leads vazios | ✅ **Endereçado na Etapa 7** para fins de exibição: `page_dashboard.py` oculta por padrão leads sem interação (`metrics.leads_com_interacao()`), com contador de quantos foram ocultados. A causa raiz (criação do lead na abertura da conversa) permanece — é a limitação 17, deliberadamente não alterada, pois viabiliza a continuidade do atendimento |
| Alertas ⚠️ sem cor | `:orange[]` não funciona em `st.caption`; alternativa é `st.warning` |
| Threshold de follow-up fixo | ✅ **Resolvido na Etapa 7.** `page_broker.py` expõe campo numérico de horas (padrão 24) + atalho de 1 minuto em modo demonstrativo |
| Follow-up sem gatilho de UI | ✅ **Resolvido na Etapa 7.** Botão "Verificar leads inativos agora" em `page_broker.py`, chamando `Orchestrator.executar_verificacao_followup()` |
| `_TIPOS_LEGIVEIS` duplicado | Mesmo dicionário de 3 entradas, agora em três módulos (`scheduling_agent.py`, `summarizer.py`, e `page_broker.py`, Etapa 7) — trade-off consciente mantido: não acoplar a um símbolo privado de outro módulo |
| Colisão disponibilidade/prazo | Resposta de prazo com "cara" de agendamento (dia da semana + período) pode ser capturada como disponibilidade em vez de urgência — regex vence sem saber a que pergunta respondia (pós-validação manual) |
| Repetição de pergunta no fallback | Motor determinístico pode sortear a mesma das 2 opções em quedas consecutivas pro mesmo slot — avaliado e conscientemente não corrigido (pós-validação manual) |
| Taxa de fallback do `model_fast` | Pareceu alta em teste manual (~30 turnos); causa raiz (modelo vs. provedor) não isolada — investigação de baixo custo proposta para o futuro (pós-validação manual) |
| Telefone/e-mail nunca coletados | Nenhum ponto do sistema pergunta ou extrai contato do lead — decisão consciente (Opção B: ajuste de texto, não coleta de dado), registrada em `decisoes_tecnicas.md` seção 6e (pós-validação manual) |
| Voice AI (entrada por voz) | Avaliada tecnicamente como viável (Groq Whisper + `st.audio_input`), adiada deliberadamente — sem TTS, só entrada (pós-validação manual) |
| Uso de LLM no dashboard é por sessão | `GroqClient.stats` acumula em memória desde que o processo Streamlit começou — não é histórico persistido; já sinalizado na própria tela (pendência nova da Etapa 7) |
| Histórico de `git mv` de `__init__.py` vazios | Não ficou perfeitamente limpo na reorganização de pastas — Git emparelhou deleção/criação de forma um pouco aleatória entre arquivos idênticos; cosmético, sem efeito em conteúdo (pendência nova da Etapa 7) |
| Data de entrega | Não informada nesta sessão |

---

## 14. Como retomar

1. Colar as **Instruções do Projeto** (o bloco longo com os 16 itens).
2. Colar este documento
3. Informar a etapa desejada — provavelmente **Etapa 8**
4. Se necessário, enviar `docs/decisoes_tecnicas.md` para o histórico completo de decisões e bugs

**Forma de trabalho estabelecida:** passo a passo, com explicação de cada decisão técnica, alternativas descartadas e limitações; validação por execução real de teste (`uv run pytest`) antes de considerar um arquivo fechado; commit sugerido ao final de cada arquivo; confirmação explícita antes de avançar de etapa — nenhuma etapa começa sem ordem direta, mesmo que a anterior tenha fechado.
