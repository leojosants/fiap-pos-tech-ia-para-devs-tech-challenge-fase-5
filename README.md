# 🏠 CasaLead — Agente SDR Imobiliário com IA Generativa

### FIAP | Pós Tech em IA para Devs — Hackathon

Agente conversacional de **pré-vendas (SDR)** para o mercado imobiliário.
Atende leads automaticamente, identifica a intenção do cliente
(compra, aluguel ou investimento), qualifica o interesse, recomenda
imóveis de uma base simulada, agenda visitas, realiza follow-up e gera
um resumo estruturado para o corretor humano.

> ✅ **Projeto concluído.** As 8 etapas foram fechadas, com 657 testes
> automatizados passando e a aplicação publicada e validada em
> produção: **[casalead-sdr-imobiliario-fase-5.streamlit.app](https://casalead-sdr-imobiliario-fase-5.streamlit.app/)**

---

## 📋 Índice

- [🏠 CasaLead — Agente SDR Imobiliário com IA Generativa](#-casalead--agente-sdr-imobiliário-com-ia-generativa)
  - [FIAP | Pós Tech em IA para Devs — Hackathon](#fiap--pós-tech-em-ia-para-devs--hackathon)
  - [📋 Índice](#-índice)
  - [🎯 O Problema](#-o-problema)
  - [💡 A Solução](#-a-solução)
  - [📸 Demonstração](#-demonstração)
  - [✨ Funcionalidades](#-funcionalidades)
  - [🏗️ Arquitetura](#️-arquitetura)
    - [Responsabilidade de cada componente](#responsabilidade-de-cada-componente)
    - [Degradação em dois níveis](#degradação-em-dois-níveis)
  - [💬 Fluxo da Conversa](#-fluxo-da-conversa)
    - [Critérios de qualificação](#critérios-de-qualificação)
  - [🎬 Exemplos de Uso](#-exemplos-de-uso)
    - [Compra — linguagem direta](#compra--linguagem-direta)
    - [Linguagem natural aberta](#linguagem-natural-aberta)
    - [Investimento](#investimento)
  - [🛠️ Tecnologias](#️-tecnologias)
  - [📁 Estrutura de Diretórios](#-estrutura-de-diretórios)
  - [⚙️ Como Executar Localmente](#️-como-executar-localmente)
    - [Pré-requisitos](#pré-requisitos)
    - [Passo 1 — Clonar o repositório](#passo-1--clonar-o-repositório)
    - [Passo 2 — Configurar variáveis de ambiente](#passo-2--configurar-variáveis-de-ambiente)
    - [Passo 3 — Instalar dependências](#passo-3--instalar-dependências)
    - [Passo 4 — Gerar a base de imóveis](#passo-4--gerar-a-base-de-imóveis)
    - [Passo 5 — Executar](#passo-5--executar)
    - [Executar sem chave de API](#executar-sem-chave-de-api)
  - [🔐 Variáveis de Ambiente](#-variáveis-de-ambiente)
  - [🧪 Testes](#-testes)
  - [☁️ Deploy](#️-deploy)
  - [📐 Decisões Técnicas](#-decisões-técnicas)
  - [📄 Relatório Técnico](#-relatório-técnico)
  - [⚠️ Limitações Conhecidas](#️-limitações-conhecidas)
  - [🚀 Melhorias Futuras](#-melhorias-futuras)
  - [🎓 Autor](#-autor)

---

## 🎯 O Problema

Imobiliárias perdem uma parcela relevante dos leads recebidos por razões
que não têm relação com a qualidade do imóvel ofertado:

- **Tempo de resposta elevado** — o lead procura o concorrente antes do retorno.
- **Falta de acompanhamento** — conversas iniciadas e nunca retomadas.
- **Atendimento manual** — corretor consumido por triagem repetitiva.
- **Dificuldade em priorizar** — leads quentes e frios recebem o mesmo tratamento.
- **Sobrecarga operacional** — volume de contatos acima da capacidade da equipe.

## 💡 A Solução

O CasaLead atua na camada de **pré-venda**, antes do corretor humano
entrar em cena. O agente conduz a conversa inicial, extrai as
informações necessárias para qualificar o lead, sugere imóveis
compatíveis e entrega ao corretor um lead já classificado e resumido —
invertendo a lógica atual, em que o corretor gasta o tempo mais caro na
etapa menos qualificada do funil.

---

## 📸 Demonstração

Capturas de tela reais da aplicação publicada — não do ambiente local.
Mais 10 imagens, cobrindo os três cenários do enunciado, o painel do
corretor e o dashboard, estão em
[docs/relatorio_tecnico.md](casaLead--agente-sdr-imobiliario-com-ia-generativa/docs/relatorio_tecnico.md).

**Tela inicial** — painel de qualificação zerado, três sugestões de
início mapeadas aos três cenários do enunciado (compra, investimento,
aluguel):

![Tela inicial do CasaLead](casaLead--agente-sdr-imobiliario-com-ia-generativa/docs/imagens/chat_tela_inicial.png)

<table>
<tr>
<td width="50%">

**Qualificação completa (compra)**

![Conversa de compra qualificada](casaLead--agente-sdr-imobiliario-com-ia-generativa/docs/imagens/chat_qualificacao_compra.png)

</td>
<td width="50%">

**Dashboard — funil de leads**

![Dashboard do CasaLead](casaLead--agente-sdr-imobiliario-com-ia-generativa/docs/imagens/dashboard_funil_status_temperatura.png)

</td>
</tr>
</table>

**Experimente ao vivo:** [casalead-sdr-imobiliario-fase-5.streamlit.app](https://casalead-sdr-imobiliario-fase-5.streamlit.app/)

---

## ✨ Funcionalidades

| # | Funcionalidade | Status |
| --- | --- | --- |
| 1 | Atendimento conversacional humanizado | ✅ |
| 2 | Identificação de intenção (compra / aluguel / investimento) | ✅ |
| 3 | Qualificação e coleta estruturada de informações | ✅ |
| 4 | Memória e persistência do contexto conversacional | ✅ |
| 5 | Modo demonstrativo sem dependência de API | ✅ |
| 6 | Observabilidade (eventos, tokens, latência) | ✅ |
| 7 | Consulta à base simulada de imóveis (RAG) | ✅ |
| 8 | Classificação e priorização de leads | ✅ |
| 9 | Agendamento de reuniões e visitas | ✅ |
| 10 | Follow-up automático de leads inativos | ✅ |
| 11 | Resumo inteligente para o corretor | ✅ |
| 12 | Dashboard de acompanhamento | ✅ |

---

## 🏗️ Arquitetura

A solução é organizada em camadas com responsabilidades estritas. Nenhuma
camada superior conhece os detalhes da inferior.

```
INTERFACE (Streamlit, 3 páginas: 💬 Atendimento · 📊 Dashboard · 🧑‍💼 Corretor)
        │ ResultadoTurno / leitura via propriedades públicas do Orchestrator
        ▼
ORQUESTRADOR — única porta de entrada do domínio (escrita E leitura)
  persiste entrada → qualifica → recomenda → agenda → pontua
    → resume (se necessário) → gera resposta → persiste saída
        │
        ├── AGENTES: qualification_agent · conversation_agent ·
        │            scheduling_agent · followup_manager
        │
        ├── PERSISTÊNCIA: lead · property · conversation · appointment ·
        │                  followup — repositório por entidade, SQLite (7 tabelas)
        │
        ├── CAMADA DE IA: groq_client (retry + métricas) · prompts ·
        │                  demo_engine (fallback determinístico)
        │
        └── RECOMENDAÇÃO (RAG: retriever TF-IDF + ranker) ·
            SCORING (regras explícitas, puro) ·
            RESUMO (LLM → template)
```

### Responsabilidade de cada componente

| Componente | Responsabilidade |
| --- | --- |
| `ui/` | Renderização e estado de sessão. Não contém regra de negócio |
| `agents/orchestrator` | Coordena o turno: persiste entrada, qualifica, recomenda, agenda, pontua, resume, gera resposta, persiste saída |
| `agents/qualification_agent` | Extrai intenção e slots — regex + LLM com verificação cruzada |
| `agents/conversation_agent` | Produz a fala do agente, com degradação automática para o modo determinístico |
| `agents/scheduling_agent` | Interpreta disponibilidade e agenda — 100% determinístico, nunca usa LLM |
| `followup/followup_manager` | Identifica leads inativos, reengaja (mensagem template) ou escala para atendimento humano |
| `recommendation/` | Busca semântica (RAG via TF-IDF) e filtro estruturado — `retriever.py` + `ranker.py` |
| `scoring/` | Score (0–100) e temperatura por regras explícitas — `rules.py` puro, `builder.py` acessa dado externo |
| `reporting/summarizer` | Resumo para o corretor via LLM, com degradação para template estruturado |
| `observability/metrics` | Agrega estatísticas já existentes nos repositórios para o dashboard, sem reimplementar |
| `llm/groq_client` | Comunicação com a API, retry, timeout e coleta de métricas |
| `llm/prompts` | Persona, roteiros por intenção e prompt de extração |
| `llm/demo_engine` | Motor determinístico e detectores por padrão |
| `persistence/` | Acesso a dados (5 repositórios). Nenhum módulo acima conhece SQL |
| `core/` | Modelos de domínio, enums e configuração |

### Degradação em dois níveis

O sistema mantém-se operante mesmo sem acesso ao provedor de LLM:

1. **Sem chave de API** → opera integralmente no motor determinístico
2. **Chave presente, chamada falha** → degrada para o motor no turno afetado e volta ao LLM no seguinte

---

## 💬 Fluxo da Conversa

```md
Entrada do lead
↓
Persistência da mensagem ──────────────→ tabela messages
↓
Qualificação (regex + LLM, verificação cruzada em campos numéricos)
↓
Atualização do lead ───────────────────→ tabela leads + events
↓
Recomendação de imóveis (filtro estruturado + busca semântica TF-IDF)
↓
Agendamento (interpretação determinística de disponibilidade, se houver)
↓
Scoring — score (0–100) e temperatura recalculados a cada turno
↓
Resumo para o corretor — só na transição de estado (lead fica quente,
agendamento confirmado, ou follow-up escala), via LLM com degradação
↓
Confirmação de intenção ambígua?
├ sim → pergunta determinística
└ não → geração da fala pelo LLM (ou motor determinístico, se indisponível)
↓
Persistência da resposta ──────────────→ tabela messages
↓
ResultadoTurno ─────────────────────────→ interface
```

### Critérios de qualificação

O agente considera o lead qualificado quando reúne todos os slots da
intenção identificada:

| Compra e aluguel | Investimento |
| --- | --- |
| Região de interesse | Perfil de investidor |
| Faixa de preço | Ticket disponível |
| Quantidade de quartos | Objetivo do investimento |
| Prazo | Expectativa de retorno |
| Disponibilidade para reunião | Prazo do investimento |

Um lead com todos os slots preenchidos **mas sem intenção definida** não
é considerado qualificado — sem saber se ele quer comprar, alugar ou
investir, o corretor não sabe como abordá-lo.

---

## 🎬 Exemplos de Uso

### Compra — linguagem direta

LEAD: Oi, procuro apartamento na zona sul
SOFIA: Entendi, você busca um apartamento na zona sul.
Você está pensando em comprar ou alugar?

LEAD: Meu nome é Marcos, até 850 mil
SOFIA: Entendi, Marcos. Só para eu te ajudar direito:
você está pensando em comprar, alugar ou investir?

LEAD: 2 quartos e uma vaga
SOFIA: Entendi, 2 quartos e uma vaga. Qual é o prazo que você
tem em mente para se mudar ou fechar a compra?

LEAD: Posso sábado de manhã
SOFIA: Obrigada, Marcos! Você procura apartamento na zona sul,
até R$ 850.000, com 2 quartos, 1 vaga, e quer se mudar
o quanto antes. Um corretor vai entrar em contato em breve.

### Linguagem natural aberta

De um relato de 340 palavras contendo distratores numéricos ("sete anos",
"nove anos", "uma hora no trânsito") e menções geográficas irrelevantes
("região central", "Paulista"), o agente extraiu corretamente:

| Slot | Valor extraído |
| --- | --- |
| Intenção | Compra *(o texto continha três menções contextuais a "aluguel")* |
| Região | Oeste |
| Orçamento | R$ 1.200.000 *(informado por extenso: "um milhão e duzentos mil")* |
| Quartos | 3 |
| Prazo | Imediata *(inferido de "contrato vence em dois meses")* |
| Preferências | Aceita pet, espaço para escritório |

### Investimento

LEAD: Quero investir em imóveis para renda
SOFIA: Entendi, foco em renda mensal. Já investe em imóveis
ou é a primeira vez?

LEAD: Já invisto, sou conservador
SOFIA: Ótimo! Já tem experiência no mercado. Quanto você
pretende investir nesse próximo imóvel?

LEAD: Penso em investir nos próximos meses
SOFIA: Perfeito! Você já investe em imóveis, tem R$ 600.000
disponíveis, busca renda mensal com retorno de 7% ao ano
e pretende investir nos próximos meses. Vou encaminhar
seu perfil ao nosso especialista em investimentos.

---

## 🛠️ Tecnologias

| Camada | Tecnologia | Justificativa |
| --- | --- | --- |
| Linguagem | Python 3.12+ | Ecossistema de IA e requisito do curso |
| Dependências | [`uv`](https://docs.astral.sh/uv/) | Resolução determinística via lockfile |
| Interface | Streamlit | Chat e dashboard com baixo custo de implementação |
| Persistência | SQLite (`sqlite3` puro) | Zero configuração; camada de repositório abstraída |
| LLM — conversa | Groq · `openai/gpt-oss-20b` | Latência baixa para o turno a turno |
| LLM — raciocínio | Groq · `openai/gpt-oss-120b` | Maior capacidade para extração e sumarização |
| Testes | `pytest` | Cobertura da lógica determinística |

O uso de LangChain foi avaliado e descartado: a orquestração de três
agentes com fluxo determinístico não justifica o overhead de abstração.
Ver [decisões técnicas](casaLead--agente-sdr-imobiliario-com-ia-generativa/docs/decisoes_tecnicas.md).

---

## 📁 Estrutura de Diretórios

```md
├── README.md                       # este arquivo — único item fora da subpasta
└── casaLead--agente-sdr-imobiliario-com-ia-generativa/
    ├── data/
    │   ├── seed/properties.json    # base de 60 imóveis (versionada)
    │   └── runtime/                # banco SQLite (gerado, não versionado)
    ├── docs/
    │   ├── decisoes_tecnicas.md    # decisões, bugs e limitações
    │   ├── contexto_projeto.md     # estado do projeto por etapa
    │   ├── relatorio_tecnico.md    # relatório técnico final, com evidências visuais
    │   └── imagens/                # capturas de tela do app publicado
    ├── scripts/
    │   └── generate_properties.py  # gerador determinístico da base
    ├── src/
    │   ├── core/                   # modelos, enums, configuração
    │   ├── persistence/            # repositórios e schema
    │   ├── llm/                    # cliente Groq, prompts, motor demo
    │   ├── agents/                 # qualificação, conversação, agendamento, orquestrador
    │   ├── followup/                # reengajamento de leads inativos
    │   ├── reporting/               # resumo para o corretor
    │   ├── recommendation/          # busca e recomendação de imóveis (RAG)
    │   ├── scoring/                 # classificação e priorização de leads
    │   ├── observability/           # agregação de métricas para o dashboard
    │   └── ui/                      # páginas (atendimento, dashboard, corretor) e componentes
    ├── tests/                       # 657 testes, sem dependência de rede
    ├── requirements.txt             # gerado via `uv export`, para o Streamlit Cloud
    └── main.py                      # ponto de entrada — navegação multipágina
```

---

## ⚙️ Como Executar Localmente

### Pré-requisitos

- Python 3.12 ou superior
- [`uv`](https://docs.astral.sh/uv/) instalado
- Chave gratuita da [Groq API](https://console.groq.com) *(opcional — há modo demonstrativo)*

### Passo 1 — Clonar o repositório

```bash
git clone git@github.com:leojosants/fiap-pos-tech-ia-para-devs-tech-challenge-fase-5.git
cd fiap-pos-tech-ia-para-devs-tech-challenge-fase-5/casaLead--agente-sdr-imobiliario-com-ia-generativa
```

> O código-fonte fica dentro da subpasta `casaLead--agente-sdr-imobiliario-com-ia-generativa/`
> — só o `README.md` permanece na raiz do repositório, porque é o
> único arquivo que o GitHub renderiza automaticamente como página
> inicial. Todos os comandos a seguir (`uv sync`, `uv run ...`) devem
> ser executados de dentro dessa subpasta.

### Passo 2 — Configurar variáveis de ambiente

```bash
cp .env.example .env
# Edite o .env e preencha GROQ_API_KEY (opcional)
```

### Passo 3 — Instalar dependências

```bash
uv sync
```

### Passo 4 — Gerar a base de imóveis

```bash
uv run python -m scripts.generate_properties
```

### Passo 5 — Executar

```bash
uv run streamlit run main.py
```

A aplicação abre em `http://localhost:8501`.

### Executar sem chave de API

```bash
# Linux/macOS/Git Bash
DEMO_MODE=true uv run streamlit run main.py

# PowerShell
$env:DEMO_MODE="true"; uv run streamlit run main.py
```

---

## 🔐 Variáveis de Ambiente

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `GROQ_API_KEY` | Não | Ausente, o sistema opera em modo demonstrativo |
| `GROQ_MODEL_FAST` | Não | Modelo da conversa (padrão: `openai/gpt-oss-20b`) |
| `GROQ_MODEL_SMART` | Não | Modelo de raciocínio (padrão: `openai/gpt-oss-120b`) |
| `DEMO_MODE` | Não | `true` força o motor determinístico |
| `DATABASE_PATH` | Não | Caminho do banco SQLite |
| `LOG_LEVEL` | Não | Nível de log da aplicação |

A chave de API nunca é exposta em log ou interface — o sistema informa
apenas se ela está configurada.

---

## 🧪 Testes

```bash
uv run pytest
```

**657 testes automatizados**, nenhum dependente de rede ou de chave de
API real — o cliente Groq é mockado em todos os testes que o
exercitam (construído fora do modo demonstrativo, com `self._client`
substituído por um `Mock()`, sem nenhuma chamada HTTP real).

---

## ☁️ Deploy

Aplicação publicada no **Streamlit Community Cloud**, a partir da
branch `main`:
**[casalead-sdr-imobiliario-fase-5.streamlit.app](https://casalead-sdr-imobiliario-fase-5.streamlit.app/)**

Para publicar uma instância própria:

1. Em [share.streamlit.io](https://share.streamlit.io), "Create app" → "Deploy a public app from GitHub".
2. Branch `main`; **main file path**: `casaLead--agente-sdr-imobiliario-com-ia-generativa/main.py` — o caminho completo é obrigatório, já que a aplicação não está na raiz do repositório.
3. Em "Advanced settings" → Secrets:

   ```toml
   GROQ_API_KEY = "sua-chave-aqui"
   DEMO_MODE = "false"
   ```

   Sem chave, ou com `DEMO_MODE = "true"`, o sistema opera integralmente no modo demonstrativo — uma demonstração igualmente válida, sem custo de API.

Detalhe completo do processo, incluindo três bugs reais encontrados só
no deploy (nenhum detectável localmente), em
[docs/relatorio_tecnico.md](casaLead--agente-sdr-imobiliario-com-ia-generativa/docs/relatorio_tecnico.md#134-deploy-no-streamlit-community-cloud).

---

## 📐 Decisões Técnicas

Todas as decisões de arquitetura e implementação, com as alternativas
consideradas e suas justificativas, estão registradas em
**[docs/decisoes_tecnicas.md](casaLead--agente-sdr-imobiliario-com-ia-generativa/docs/decisoes_tecnicas.md)** — incluindo os
bugs encontrados durante o desenvolvimento e os testes de segurança
realizados.

---

## 📄 Relatório Técnico

Documento único, com 17 seções e 13 imagens da aplicação em produção —
arquitetura completa, decisões etapa a etapa, os 35 bugs reais
encontrados e corrigidos (com causa raiz e correção de cada um),
resultados consolidados, segurança e privacidade, e limitações
conhecidas:
**[docs/relatorio_tecnico.md](casaLead--agente-sdr-imobiliario-com-ia-generativa/docs/relatorio_tecnico.md)**

---

## ⚠️ Limitações Conhecidas

Principais limitações desta prova de conceito:

- **Persistência em ambiente efêmero** — no Streamlit Cloud, o banco é
  recriado a partir do seed a cada reciclagem do container.
- **Compreensão limitada no modo demonstrativo** — o motor determinístico
  reconhece padrões conhecidos, mas não compreende linguagem natural.
- **Sem validação da saída do modelo** — não há verificação automática de
  que o agente respeitou as regras do prompt.
- **Slots imutáveis** — apenas a intenção admite correção pelo lead; os
  demais campos, uma vez preenchidos, não são sobrescritos.

A lista completa, com 49 itens e o módulo correspondente, está em
[docs/decisoes_tecnicas.md](casaLead--agente-sdr-imobiliario-com-ia-generativa/docs/decisoes_tecnicas.md).

---

## 🚀 Melhorias Futuras

- Integração com WhatsApp Business API
- Integração com CRM (HubSpot, Pipedrive)
- Circuit breaker no cliente de LLM
- Streaming de resposta token a token
- Migração para Postgres/Supabase — a camada de repositório já abstrai o backend
- Política de retenção de dados conforme LGPD
- Correção de slots já preenchidos por declaração do lead
- Modelo local via Ollama como alternativa de fallback

---

## 🎓 Autor

**Leonardo José de Oliveira Santos** — RM369985
[github.com/leojosants](https://github.com/leojosants)

**FIAP — Pós Tech em IA para Devs** · Hackathon

---

> Prova de conceito acadêmica. Os dados de imóveis e leads são
> sintéticos e não representam ofertas reais.
