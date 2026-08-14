# 🏠 CasaLead — Agente SDR Imobiliário com IA Generativa

### FIAP | Pós Tech em IA para Devs — Hackathon

Agente conversacional de **pré-vendas (SDR)** para o mercado imobiliário.
Atende leads automaticamente, identifica a intenção do cliente
(compra, aluguel ou investimento), qualifica o interesse, recomenda
imóveis de uma base simulada, agenda visitas, realiza follow-up e gera
um resumo estruturado para o corretor humano.

> 🚧 **Projeto em desenvolvimento.** Este README é um documento vivo e
> será atualizado a cada etapa concluída.

---

## 📋 Índice

- [🏠 CasaLead — Agente SDR Imobiliário com IA Generativa](#-casalead--agente-sdr-imobiliário-com-ia-generativa)
    - [FIAP | Pós Tech em IA para Devs — Hackathon](#fiap--pós-tech-em-ia-para-devs--hackathon)
  - [📋 Índice](#-índice)
  - [🎯 O Problema](#-o-problema)
  - [💡 A Solução](#-a-solução)
  - [✨ Funcionalidades](#-funcionalidades)
  - [🎬 Demonstração](#-demonstração)
  - [🏗️ Arquitetura](#️-arquitetura)
  - [💬 Fluxo da Conversa](#-fluxo-da-conversa)
  - [🛠️ Tecnologias](#️-tecnologias)
  - [📁 Estrutura de Diretórios](#-estrutura-de-diretórios)
  - [⚙️ Como Executar Localmente](#️-como-executar-localmente)
    - [Pré-requisitos](#pré-requisitos)
    - [Passo 1 — Clonar o repositório](#passo-1--clonar-o-repositório)
    - [Passo 2 — Configurar variáveis de ambiente](#passo-2--configurar-variáveis-de-ambiente)
    - [Passo 3 — Instalar dependências](#passo-3--instalar-dependências)
    - [Passo 4 — Executar](#passo-4--executar)
  - [🔐 Variáveis de Ambiente](#-variáveis-de-ambiente)
  - [🧪 Testes](#-testes)
  - [☁️ Deploy](#️-deploy)
  - [📊 Critérios de Qualificação](#-critérios-de-qualificação)
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

## ✨ Funcionalidades

| # | Funcionalidade | Status |
| --- | --- | --- |
| 1 | Atendimento conversacional humanizado | 🔜 |
| 2 | Identificação de intenção (compra / aluguel / investimento) | 🔜 |
| 3 | Qualificação e coleta estruturada de informações | 🔜 |
| 4 | Memória e persistência do contexto conversacional | 🔜 |
| 5 | Consulta à base simulada de imóveis (RAG) | 🔜 |
| 6 | Classificação e priorização de leads | 🔜 |
| 7 | Agendamento de reuniões e visitas | 🔜 |
| 8 | Follow-up automático de leads inativos | 🔜 |
| 9 | Resumo inteligente para o corretor | 🔜 |
| 10 | Dashboard de acompanhamento | 🔜 |
| 11 | Observabilidade e métricas de conversão | 🔜 |

---

## 🎬 Demonstração

_A ser preenchido — aplicação publicada e exemplos de conversa._

---

## 🏗️ Arquitetura

_A ser preenchido — diagrama e descrição dos componentes._

---

## 💬 Fluxo da Conversa

_A ser preenchido._

---

## 🛠️ Tecnologias

| Camada | Tecnologia | Justificativa |
| --- | --- | --- |
| Linguagem | Python 3.12.9 | Ecossistema de IA e requisito do curso |
| Dependências | [`uv`](https://docs.astral.sh/uv/) | Resolução determinística via lockfile |
| Interface | Streamlit | Chat e dashboard com baixo custo de implementação |
| Persistência | SQLite | Zero configuração; camada de repositório abstraída |
| LLM | Groq API | Inferência rápida, free tier, sem custo operacional |

---

## 📁 Estrutura de Diretórios

_A ser preenchido ao final da implementação._

---

## ⚙️ Como Executar Localmente

### Pré-requisitos

- Python 3.12.9
- [`uv`](https://docs.astral.sh/uv/) instalado
- Chave gratuita da [Groq API](https://console.groq.com) _(opcional — há modo demonstrativo)_

### Passo 1 — Clonar o repositório

```bash
git clone git@github.com:leojosants/fiap-pos-tech-ia-para-devs-tech-challenge-fase-5.git
cd fiap-pos-tech-ia-para-devs-tech-challenge-fase-5
```

### Passo 2 — Configurar variáveis de ambiente

```bash
cp .env.example .env
```

### Passo 3 — Instalar dependências

```bash
uv sync
```

### Passo 4 — Executar

```bash
uv run streamlit run main.py
```

A aplicação abre em `http://localhost:8501`.

---

## 🔐 Variáveis de Ambiente

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `GROQ_API_KEY` | Não | Chave da Groq API. Ausente, o sistema opera em modo demonstrativo |
| `GROQ_MODEL_FAST` | Não | Modelo para tarefas de baixa latência |
| `GROQ_MODEL_SMART` | Não | Modelo para raciocínio e sumarização |
| `DEMO_MODE` | Não | `true` força o motor determinístico |
| `DATABASE_PATH` | Não | Caminho do banco SQLite |
| `LOG_LEVEL` | Não | Nível de log da aplicação |

---

## 🧪 Testes

```bash
uv run pytest
```

---

## ☁️ Deploy

_A ser preenchido._

---

## 📊 Critérios de Qualificação

_A ser preenchido._

---

## ⚠️ Limitações Conhecidas

_A ser preenchido._

---

## 🚀 Melhorias Futuras

_A ser preenchido._

---

## 🎓 Autor

**Leonardo José de Oliveira Santos** — RM369985
[github.com/leojosants](https://github.com/leojosants)

**FIAP — Pós Tech em IA para Devs** · Hackathon

---

> Prova de conceito acadêmica. Os dados de imóveis e leads são
> sintéticos e não representam ofertas reais.
