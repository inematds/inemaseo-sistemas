# inemaseo-sistemas — especificação (19/10/2026)

O "Semrush aberto" do próprio site: 5 ferramentas de linha de comando, MIT, que rodam local, sem API paga, só com dado grátis do seu site. Nasce do `inemaseo-metodo` (scripts das etapas 1, 3 e 10) e alimenta o curso 7 da Formação inemaSEO. Base da pesquisa: `~/projetos/wifi/longrun/2026-10-19-formacao-inemaseo-v72/SISTEMAS-SEO-FERRAMENTAS.md` e `TENDENCIAS-SEO-GEO-2026-10.md`.

## Regras comuns
- **Python 3.10+ só com biblioteca padrão** (sqlite3, csv, urllib, html.parser, argparse, gzip, ipaddress, socket). Dependência externa só se indispensável e opcional.
- Cada ferramenta: `ferramentas/<nome>/<nome>.py` (CLI com `--help` em PT), `README.md` próprio (o que faz, de onde vem o dado, limite honesto, exemplos de comando reais), `tests/` com `python3 -m unittest` passando, e `exemplos/<nome>/` com dado de exemplo e a saída gerada.
- Saída: terminal curto + relatório HTML self-contained (padrão INEMA dark: preto `#0c0c10`, amarelo `#FACC15`, títulos Sora; ler `~/projetos/inema-design/DESIGN.md`) e JSON/CSV para outra ferramenta ler.
- Nenhuma chamada de API sem autorização do Nei. Nos testes, nada de rede além de `curl`/HTTP GET em sites públicos do INEMA (inema.club, news.inema.pro, eventos.inema.pro, inematds.github.io). GSC e Bing: o modo API pode existir no código, mas os testes usam arquivos locais.
- Nada inventado: nome de robô, IP oficial, coluna de CSV, regra do Google — só com fonte (link no README). Onde não houver fonte, dizer "[a confirmar]".
- Segredo nunca no repo. `.gitignore` para `dados/`, `*.sqlite`, `.env`.
- Commits: autor `inematds <inematds@gmail.com>`, **só dos seus caminhos** (`git commit -- ferramentas/<nome> exemplos/<nome>`), sem push (o agente principal empurra).

## As 5 ferramentas

### 1. gsc-historico
Guarda o Search Console para sempre (a UI e a API só têm ~16 meses). Importa os CSV do `gsc_semanal.py` (formato: `<fim>_<site>_sem-marca.csv` e `resumo.csv`) e, opcionalmente, puxa direto pela API (mesma autenticação do `gsc_semanal.py`, não testada ao vivo). Banco SQLite. Relatórios: série semanal marca × sem marca × anônimas, consultas que subiram/caíram, consultas novas com impressão e sem página dona (pauta), páginas com impressão e 0 clique (reescrever título). Teste com os CSV reais de `~/projetos/inemaseo/data/gsc/` (copiar uma amostra anonimizável para `exemplos/`; os números já são públicos nos relatórios do inemaSEO).

### 2. bing-ia
Importa o CSV exportado do Bing Webmaster **AI Performance** (citações em Copilot/Bing) e cruza com o gsc-historico: páginas citadas pela IA × páginas com clique no Google; consultas de "grounding" viram ideias de conteúdo. Pesquisar na documentação oficial do Bing as colunas do export; se não houver doc das colunas, aceitar mapeamento por `--colunas` e dizer isso no README. Exemplo com CSV de amostra rotulado "fictício".

### 3. botlog
Lê log de acesso (nginx/Apache combined, JSON do Cloudflare/Vercel se documentado) e classifica robôs de IA **por finalidade**: busca (OAI-SearchBot, PerplexityBot, Claude-SearchBot), ação do usuário (ChatGPT-User, Claude-User, Perplexity-User), treino (GPTBot, ClaudeBot, Google-Extended é token de robots, não UA — tratar), buscadores clássicos (Googlebot, Bingbot). Verifica autenticidade por rDNS/faixa de IP oficial quando a fonte existir (listas JSON publicadas pela OpenAI, Google, Bing etc. — baixar e versionar em `ferramentas/botlog/listas/` com data). Relatório: quem leu o quê, quantas vezes, falsos robôs, páginas nunca visitadas por nenhum robô. Dado real: ver `~/projetos/wifi/VPS.md` e ler (só leitura, `ssh ... 'sudo -n tail' ou zcat`) um log nginx de uma VPS que sirva site; copiar para `exemplos/` só depois de remover IPs de pessoas (manter só os de robôs) — LGPD. Sem log real acessível, usar amostra montada com UAs oficiais, rotulada.

### 4. auditor
Evolução do `inemaseo-metodo/tools/auditoria.sh`: crawler local educado (respeita robots.txt, limite de páginas e de taxa, User-Agent próprio) que confere em cada página o HTML entregue pelo servidor: status, canônico (um só, absoluto, coerente com sitemap), hreflang recíproco, `noindex`, título/descrição (tamanho, duplicados), H1, JSON-LD válido (tipos, `@id`), links internos (página órfã = sem link de entrada), links quebrados, imagens sem alt, sitemap (`lastmod`), robots.txt **por finalidade de robô de IA** (o que cada robô pode), sinal de bloqueio por CDN/WAF (resposta 403/desafio para UA de robô de IA). Saída: relatório HTML com prioridade (crítico/importante/melhoria) e uma linha de "como corrigir" por achado. Teste em inema.club e eventos.inema.pro com `--max 50`.

### 5. agente-ready
Evolução do `webmcp-readiness` (ler `~/projetos/webmcp-readiness/lib/audit-rules.mjs`, sem alterar aquele repo): nota de prontidão para IA e agentes com **pesos públicos** num arquivo `pesos.json` versionado. Critérios: acesso dos robôs (robots por finalidade, CDN), entidade (Person/Organization com `@id`, `sameAs`), conteúdo extraível (HTML sem depender de JS, resposta visível, autoria, datas), descoberta (sitemap, hreflang, llms.txt como **opcional de peso baixo**, com a evidência do Ahrefs no README), WebMCP (`document.modelContext` conforme a especificação de 16/10/2026 do W3C Community Group — confirmar lendo a spec; aceitar `navigator.modelContext` como legado com aviso), formulários acessíveis (label, autocomplete). Cada critério com "por que" e fonte. Teste em 3 sites públicos do INEMA.

## Pronto quando
- `for t in ferramentas/*/; do python3 -m unittest discover -s $t/tests; done` → OK nas 5
- cada `ferramentas/<nome>/<nome>.py --help` funciona
- `exemplos/<nome>/` tem entrada + relatório HTML gerado de verdade
- `grep -rn "api_key\|token=" ferramentas | grep -v "os.environ"` → vazio
- README raiz lista as 5 com um comando de exemplo cada
