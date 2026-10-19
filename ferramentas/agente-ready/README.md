# agente-ready

Nota de **prontidão do site para IA e agentes** (0 a 100) com **pesos públicos** em [`pesos.json`](pesos.json). Evolução do `webmcp-readiness` (as regras de `lib/audit-rules.mjs` foram a base; aquele repo não foi alterado). Lê a home e algumas páginas do sitemap como um robô que não roda JavaScript. Só Python padrão, só leitura, nenhuma API.

O Cloudflare tem um scanner parecido (isitagentready), mas não publica os pesos. Aqui cada ponto da nota tem peso, motivo e fonte num arquivo versionado: dá para discordar, mudar e comparar.

## Critérios e pesos (v1.0.0, 19/10/2026)

| Categoria | Critério | Peso |
|---|---|---|
| Acesso dos robôs (30) | robots.txt libera robôs de busca (Googlebot, Bingbot, OAI-SearchBot, Claude-SearchBot, PerplexityBot) | 12 |
| | robots.txt libera agentes a pedido do usuário (ChatGPT-User, Claude-User, Perplexity-User) | 6 |
| | CDN/WAF não barra o User-Agent publicado de OAI-SearchBot, PerplexityBot e Perplexity-User | 12 |
| Entidade (14) | Organization/Person com `@id` no JSON-LD da home | 8 |
| | `sameAs` ligando aos perfis oficiais | 4 |
| | link para Sobre/Contato na home | 2 |
| Conteúdo extraível (26) | 150+ palavras no HTML entregue (sem depender de JS) | 10 |
| | resposta visível: H1 + parágrafo de 20+ palavras | 6 |
| | autoria (meta author, `rel=author` ou `author` no JSON-LD) | 5 |
| | data (`datePublished`/`dateModified`, meta article ou `<time>`) | 5 |
| Descoberta (18) | sitemap com URLs | 6 |
| | `lastmod` no sitemap | 3 |
| | um canônico absoluto por página | 4 |
| | hreflang com autorreferência (só se o site tem idiomas) | 3 |
| | **llms.txt — opcional, peso baixo** | 2 |
| WebMCP (8) | ferramenta registrada com `document.modelContext.registerTool()` | 5 |
| | `Permissions-Policy` não desliga (`tools=()`) as ferramentas que o site registra | 1 |
| | HTTPS (a API só existe em contexto seguro) | 2 |
| Formulários (4) | campos com rótulo | 2 |
| | `autocomplete` em e-mail, nome e telefone | 2 |
| Informativo (0) | robôs de treino bloqueados; `Content-Signal` no robots; resposta a `Accept: text/markdown` | 0 |

Fator: ok = 1, parcial = 0,5, falha = 0. Critério que **não se aplica** (site sem formulário, site sem idiomas, WebMCP ausente para a checagem de política) **sai do denominador** — não vira falha. Nota = pontos ganhos ÷ pesos aplicáveis × 100.

### Por que llms.txt pesa só 2

O maior estudo público (Ahrefs, 15/06/2026, 137 mil domínios, tráfego de maio/2026) viu que cerca de 28% dos domínios publicam llms.txt e que **97% dos arquivos válidos não receberam nenhuma requisição**; robôs de recuperação de IA somam 1,1% das requisições ao arquivo. O guia de otimização para IA do Google diz que pode ignorar llms.txt. É barato e útil como índice para agentes de código, mas não é alavanca de citação. Fontes: https://ahrefs.com/blog/llmstxt-study/ e https://developers.google.com/search/docs/fundamentals/ai-optimization-guide

### WebMCP: o que é checado

Pela especificação do W3C Web Machine Learning Community Group, **Draft Community Group Report de 16/10/2026** (https://webmachinelearning.github.io/webmcp/), lida em 19/10/2026:

- A API fica em **`document.modelContext`** (`partial interface Document`, `[SecureContext]`), com `registerTool(tool, options)`, `getTools()` e `executeTool()`.
- A ferramenta é um dicionário `{name, title?, description, inputSchema?, execute, annotations?}`; o registro sai com o `AbortSignal` passado em `options.signal` (não há `unregisterTool`).
- O acesso passa pela política `tools` (padrão `'self'`); `Permissions-Policy: tools=()` desliga a API.
- O documento diz que **não é padrão W3C nem está na trilha de padrões**. Vale como preparação, não como fator de ranking.

O detector lê os scripts inline e até `--max-scripts` (padrão 8) arquivos JS de mesma origem e procura `document.modelContext` + chamadas `.registerTool(` — inclusive por alias minificado (`let e=document.modelContext; e.registerTool({...})`, que é como o inema.club faz). `navigator.modelContext` (nome dos guias antigos e do origin trial) vale **parcial**, com aviso. Formulário com atributo `toolname` (forma declarativa do `webmcp-readiness`) é só citado: ele **não aparece no texto da especificação de 16/10/2026** — **[a confirmar]** se continua no explainer.

## Uso

```bash
python3 agente-ready.py https://inema.club --saida ../../exemplos/agente-ready/inema.club
python3 agente-ready.py https://news.inema.pro --paginas 8
python3 agente-ready.py https://inematds.github.io/rea-engenharia-reversa/guia/
python3 agente-ready.py --help
```

Saída: `relatorio.html` (nota, nota por categoria, o que mais pesa para corrigir primeiro, tabela com todos os critérios, evidência e fonte), `agente-ready.json` e `criterios.csv`. Exemplos reais: [`exemplos/agente-ready/`](../../exemplos/agente-ready/).

Requisições por site: ~10 a 25 (robots, sitemap, home + `--paginas` páginas espalhadas pelo sitemap, até 8 scripts, llms.txt, 3 testes de CDN, 1 teste de Markdown), com pausa de 1 s.

## Limites honestos

- Amostra pequena (padrão: home + 4 páginas). É um termômetro, não um crawl: para o site inteiro use o `auditor`.
- "Sem depender de JS" mede palavras no HTML entregue. O Google renderiza JavaScript; se cada robô de IA renderiza ou não, **[a confirmar por robô]** (não há documentação oficial de todos).
- Teste de CDN só vê regra por User-Agent, não bloqueio por IP verificado (ver README do `auditor`).
- Detecção de WebMCP é estática: ferramenta registrada por script de outra origem, carregado depois ou dentro de iframe não aparece.
- Os pesos são uma decisão editorial do INEMA, com fonte para o **porquê** de cada critério — não para o número. Mude `pesos.json` e rode de novo.

## Código e testes

- `agente-ready.py` importa o núcleo do auditor (`ferramentas/auditor/inemaweb.py`) e o relatório comum (`ferramentas/_comum/relatorio.py`).
- `python3 -m unittest discover -s ferramentas/agente-ready/tests` — sem rede, com o site falso do auditor e `tests/fixtures/webmcp.html` (ferramenta registrada + `Permissions-Policy: tools=()`).
