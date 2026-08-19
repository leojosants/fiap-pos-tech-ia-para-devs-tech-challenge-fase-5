# Documento de Contexto — CasaLead

> **Uso:** cole este documento no início de uma nova conversa, junto com as
> Instruções do Projeto, para retomar o desenvolvimento sem perda de contexto.
> Atualize ao final de cada etapa concluída.

**Última atualização:** fim da Etapa 5
**Repositório:** `git@github.com:leojosants/fiap-pos-tech-ia-para-devs-tech-challenge-fase-5.git`
**Branch de trabalho:** `development` (merge para `main` apenas na entrega final)

---

## 1. Identificação

| Item | Valor |
| --- | --- |
| Projeto | CasaLead — Agente SDR Imobiliário com IA Generativa |
| Aluno | Leonardo José de Oliveira Santos — RM369985 |
| Curso | FIAP — Pós Tech em IA para Devs (Hackathon) |
| Padrão de entrega | Mesmo do Tech Challenge Fase 4 (MedWatch): README robusto, relatório técnico em PDF, app publicada no Streamlit Cloud, sem vídeo |

## 2. Ambiente confirmado

```
Python 3.12.9
uv 0.11.3
git 2.45.2.windows.1
Windows · PowerShell e Git Bash
Diretório: D:\REPOS-GITHUB-PUBLICO\fiap-pos-tech-ia-para-devs-tech-challenge-fase-5
```

**Regras operacionais:**

- Sempre `uv add` / `uv run`; nunca `pip` puro nem venv manual
- Scripts executados como módulo: `uv run python -m scripts.x`
- Após alterar arquivo `.py`, **reiniciar o servidor Streamlit** (Ctrl+C e subir de novo) — módulos importados ficam em cache
- Testes de linha de comando rodam em processo separado; não exigem parar o servidor
- Variáveis de ambiente no PowerShell: `$env:DEMO_MODE="true"`

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
| 6 | Agendamento, follow-up e resumo | ⬜ **próxima** |
| 7 | Dashboard e observabilidade | ⬜ |
| 8 | Testes, documentação e deploy | ⬜ |

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
| Agendamento de reuniões ou visitas | ⬜ Etapa 6 |
| Follow-up automático | ⬜ Etapa 6 |
| Resumo inteligente para o corretor | ⬜ Etapa 6 |
| Dashboard mínimo | ⬜ Etapa 7 |

---

## 5. Estrutura atual do repositório

```
├── data/
│   ├── seed/properties.json        # 60 imóveis sintéticos (versionado)
│   └── runtime/casalead.db         # banco gerado (gitignored)
├── docs/
│   ├── decisoes_tecnicas.md        # decisões, 23 bugs, 30 limitações, métricas
│   └── contexto_projeto.md         # este documento
├── scripts/
│   └── generate_properties.py      # gerador determinístico (seed=369985)
├── src/
│   ├── core/
│   │   ├── enums.py                # Intent, LeadStatus, Zone, EventType...
│   │   ├── models.py               # Lead, Property, Conversation, Message, Event
│   │   └── config.py               # Settings + detecção de modo demo
│   ├── persistence/
│   │   ├── database.py             # schema (7 tabelas) + bootstrap idempotente
│   │   ├── property_repository.py  # busca estruturada + investimento
│   │   ├── lead_repository.py      # CRUD + estatísticas de funil
│   │   └── conversation_repository.py  # conversas, mensagens, eventos
│   ├── llm/
│   │   ├── groq_client.py          # cliente + retry + UsageStats
│   │   ├── prompts.py              # persona Sofia, roteiros, PROMPT_EXTRACAO
│   │   └── demo_engine.py          # motor determinístico + detectores regex
│   ├── agents/
│   │   ├── qualification_agent.py  # extração híbrida regex + LLM
│   │   ├── conversation_agent.py   # geração de fala + fallback
│   │   └── orchestrator.py         # coordenação do turno
│   ├── recommendation/
│   │   ├── retriever.py            # índice TF-IDF + expansão de sinônimos
│   │   └── ranker.py               # filtro SQL + score semântico
│   ├── scoring/
│   │   ├── context.py              # dataclass ContextoScoring (dado externo)
│   │   ├── rules.py                # regras explícitas puras + ResultadoScoring
│   │   └── builder.py              # constrói ContextoScoring (única parte impura)
│   └── ui/
│       ├── state.py                # gestão de session_state
│       ├── page_chat.py            # página de atendimento
│       └── components/
│           ├── qualification_panel.py
│           └── property_card.py
├── tests/
│   ├── test_property_repository.py # 21 testes
│   ├── test_scoring_rules.py       # 6 testes — motor puro, sem banco
│   └── test_scoring_builder.py     # 2 testes — integração com SQLite real
├── .env.example
├── .gitattributes
├── main.py
└── pyproject.toml
```

**Pastas previstas e ainda vazias:** `src/followup/`, `src/reporting/`, `src/observability/`

**Script de apoio (fora de `src/`, não versionado como entregável):** `scripts/validar_scoring.py` — inspeção manual do fluxo de scoring via `Orchestrator`, sem depender da interface.

---

## 6. Arquitetura em uma página

```
INTERFACE (Streamlit)
  page_chat · qualification_panel · property_card · state
         ↓ ResultadoTurno
ORQUESTRADOR  ← única porta de entrada do domínio
  persiste entrada → qualifica → recomenda → pontua → gera resposta → persiste saída
         ↓                              ↓
AGENTES                          PERSISTÊNCIA
  qualification_agent              lead_repository
  conversation_agent               property_repository
  (scheduling_agent — Etapa 6)     conversation_repository
         ↓                              ↓
CAMADA DE IA                     SQLite (7 tabelas)
  groq_client · prompts             + seed versionado
  demo_engine
         ↓
RECOMENDAÇÃO                     SCORING (Etapa 5)
  retriever (TF-IDF)                rules.py (puro, testado isolado)
  ranker (filtro + score)           builder.py (impuro — consulta banco)
```

**Degradação em dois níveis:**

1. Sem chave de API → opera integralmente no motor determinístico
2. Chave presente e chamada falha → degrada no turno afetado, volta ao LLM no seguinte

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

## 10. Etapas 6 a 8 — planejadas

**Etapa 6 — Agendamento, follow-up e resumo (próxima)**

- `src/agents/scheduling_agent.py` — criar `Appointment` a partir da disponibilidade
- `src/followup/followup_manager.py` — usar `LeadRepository.buscar_inativos()` e `ConversationStatus.AGUARDANDO_LEAD`
- `src/reporting/summarizer.py` — resumo para o corretor via `model_smart`
- Ao implementar o agendamento, revisar a regra do prompt que proíbe prometer contato em horário específico

**Etapa 7 — Dashboard e observabilidade**

- `src/ui/page_dashboard.py` — funil, leads por temperatura, métricas de conversão
- `src/ui/page_broker.py` — visão do corretor com resumos
- `src/observability/` — consumir `ConversationRepository.metricas_de_eventos()` e `GroqClient.stats`
- Navegação entre páginas em `main.py`

**Etapa 8 — Testes, documentação e deploy**

- Ampliar `tests/` (demo_engine, qualification_agent, ranker)
- `requirements.txt` gerado do lock para o Streamlit Cloud
- Relatório técnico em PDF a partir de `docs/decisoes_tecnicas.md`
- Merge `development` → `main` e deploy

---

## 11. Pendências conhecidas

| Item | Observação |
| --- | --- |
| Encapsulamento | `qualification_agent` e `orchestrator` acessam `_cliente._settings`; `page_chat` acessa `orquestrador._leads`. Corrigir expondo propriedades públicas |
| Leads vazios | Criados na abertura da conversa; poluem o dashboard se o usuário não interagir (limitação 17) |
| Alertas ⚠️ sem cor | `:orange[]` não funciona em `st.caption`; alternativa é `st.warning` |
| Data de entrega | Não informada nesta sessão |

---

## 12. Como retomar

1. Colar as **Instruções do Projeto** (o bloco longo com os 16 itens).
2. Colar este documento
3. Informar a etapa desejada — provavelmente **Etapa 6**
4. Se necessário, enviar `docs/decisoes_tecnicas.md` para o histórico completo de decisões e bugs

**Forma de trabalho estabelecida:** passo a passo, com explicação de cada decisão técnica, alternativas descartadas e limitações; validação por script antes de testar na interface; commit sugerido ao final de cada arquivo; confirmação antes de avançar de etapa.
