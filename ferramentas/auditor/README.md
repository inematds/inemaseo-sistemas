# auditor

Raio-x de SEO técnico do **HTML que o servidor entrega** (o que um robô vê sem rodar JavaScript). Evolução do `inemaseo-metodo/tools/auditoria.sh`: em vez de olhar 1 página por vez com `curl`, rastreia o site com educação e confere cada página. Só Python padrão, só leitura, nenhuma API.

## O que confere

| Grupo | Checagem | Prioridade quando falha |
|---|---|---|
| Domínio | http → https com 301/308; site respondendo com e sem www | importante |
| robots.txt | erro 5xx (RFC 9309: vira "tudo bloqueado"); `Disallow: /` geral | crítico |
| robots.txt por finalidade | robô de **busca** bloqueado (Googlebot, Bingbot, OAI-SearchBot, Claude-SearchBot, PerplexityBot) | crítico |
| | agente **a pedido do usuário** bloqueado (ChatGPT-User, Claude-User, Perplexity-User) | importante |
| | robô de **treino** bloqueado (GPTBot, ClaudeBot, Google-Extended) | info: escolha do dono |
| CDN/WAF | home pedida com o User-Agent publicado de OAI-SearchBot, PerplexityBot, Perplexity-User e GPTBot: 403/429/503, `cf-mitigated` ou página de desafio | crítico (busca) / importante (usuário) / info (treino) |
| Sitemap | ausente; < 50% com `lastmod`; não declarado no robots; URL que não responde 200 direto | importante / melhoria |
| Página | link interno quebrado (4xx/5xx); `noindex` em URL do sitemap; canônico ausente, múltiplo, relativo ou apontando para outra URL que está no sitemap | crítico / importante / melhoria |
| hreflang | alternate sem link de volta (só entre páginas rastreadas); sem autorreferência | importante / melhoria |
| Conteúdo | sem `<title>`; título fora de 15–65 caracteres; títulos e descrições repetidos; sem H1; mais de um H1; menos de 80 palavras no HTML | importante / melhoria |
| JSON-LD | bloco que não é JSON; Organization/Person/WebSite sem `@id`; página sem JSON-LD; FAQPage (info: rich result acabou) | importante / melhoria / info |
| Links | página do sitemap sem link de entrada nas páginas rastreadas (órfã); imagem sem atributo `alt` | melhoria |
| llms.txt | só informa o status | info |

Cada achado sai com **uma linha de "como corrigir"** e a fonte.

## Uso

```bash
python3 auditor.py https://inema.club --max 50 --saida ../../exemplos/auditor/inema.club
python3 auditor.py https://eventos.inema.pro --max 50 -q
python3 auditor.py https://inematds.github.io/rea-engenharia-reversa/guia/ --max 20   # só a pasta do guia
python3 auditor.py --help
```

Saída em `--saida`: `relatorio.html` (padrão INEMA dark), `auditoria.json` (tudo, para outra ferramenta), `achados.csv` (uma linha por achado × URL) e `paginas.csv`. No terminal: o resumo e os 5 primeiros achados críticos/importantes.

Exemplos reais gerados em 19/10/2026: [`exemplos/auditor/`](../../exemplos/auditor/).

## Como ele se comporta (crawler educado)

- User-Agent próprio: `inemaseo-auditor/1.0.0 (+https://github.com/inematds/inemaseo-sistemas)`; respeita o robots.txt para esse nome (cai no grupo `*`).
- `--max` páginas (padrão 50), `--pausa` entre requisições (padrão 1 s, mínimo 0,5 s), `--timeout` 15 s, no máximo 2 MB por resposta, só GET.
- Começa pela URL dada (se ela redireciona para outro host, ex.: `inema.club` → `www.inema.club`, segue o destino), depois as URLs do sitemap, depois os links internos e alternates hreflang. Escopo = mesmo host e mesma pasta da URL inicial (num `github.io` não sai do repositório).
- Teste de CDN: **uma** requisição por robô, só na home, e **só se o robots.txt permitir aquele robô**.

## Limites honestos

- **Crawl parcial.** Com `--max 50` num site de 1.000 URLs, "órfã" quer dizer "sem link de entrada nas 50 páginas lidas"; hreflang e links quebrados só são checados entre páginas que foram lidas. O relatório diz quantas URLs ficaram na fila e quantos hreflang não foram verificados.
- **O teste de CDN só vê regra por User-Agent.** CDN que verifica o IP do robô (Cloudflare Verified Bots, faixas publicadas pela OpenAI/Perplexity) pode tratar o robô real diferente. Os marcadores de página de desafio (`Just a moment`, `challenge-platform`, `cf-chl`) vêm do comportamento conhecido da Cloudflare, não de lista oficial: **[a confirmar]**.
- O User-Agent de GPTBot usa a versão `1.3` no formato do exemplo publicado do OAI-SearchBot: versão **[a confirmar]**. Os de OAI-SearchBot, PerplexityBot e Perplexity-User são os publicados.
- A faixa de título 15–65 caracteres vem do `webmcp-readiness`; **não é regra do Google** (o Google corta pela largura).
- Não roda JavaScript de propósito: é o ponto de vista do robô que não renderiza. Para ver o que o Google renderiza, use a Inspeção de URL do Search Console.
- Não mede velocidade (Core Web Vitals) nem backlinks.
- Em site de projeto do GitHub Pages (`usuario.github.io/repo/`), o robots.txt que vale é o da raiz do host, que pertence ao repositório `usuario.github.io`. O achado "robots.txt não existe" ali só se corrige nesse outro repositório; o sitemap é procurado na pasta da URL inicial (ou nas linhas `Sitemap:` do robots).

## robots.txt (como é lido)

Leitor próprio no formato da [RFC 9309 / Google](https://developers.google.com/search/docs/crawling-indexing/robots/robots_txt): grupo do robô pelo nome (sem diferença de maiúsculas), `*` como reserva, várias linhas `User-agent` no mesmo grupo, curingas `*` e `$`, a regra mais longa vence e empate fica com `Allow`; 4xx = sem restrição, 5xx = tudo bloqueado. Linhas `Content-Signal` (proposta da Cloudflare) são só registradas. O `urllib.robotparser` do Python não trata `*`/`$` nem a regra mais longa, por isso não é usado.

## Fontes dos robôs e das regras

- OpenAI (OAI-SearchBot, ChatGPT-User, GPTBot, User-Agents): https://platform.openai.com/docs/bots
- Anthropic (ClaudeBot, Claude-User, Claude-SearchBot): https://support.anthropic.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how
- Perplexity (PerplexityBot, Perplexity-User, User-Agents): https://docs.perplexity.ai/guides/bots
- Google (Googlebot, Google-Extended é só token e não afeta a Busca): https://developers.google.com/search/docs/crawling-indexing/google-common-crawlers
- Bing (Bingbot): https://www.bing.com/webmasters/help/which-crawlers-does-bing-use-8c184ec0
- Canônico (vários canônicos = ignorados): https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls
- hreflang: https://developers.google.com/search/docs/specialty/international/localized-versions
- noindex: https://developers.google.com/search/docs/crawling-indexing/block-indexing
- Sitemap e lastmod: https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap
- Rich result de FAQ encerrado em 07/05/2026: https://developers.google.com/search/updates
- Recursos de IA do Google (rastreio liberado em robots e CDN; sem schema especial para IA): https://developers.google.com/search/docs/appearance/ai-features
- llms.txt, estudo do Ahrefs (97% sem requisição): https://ahrefs.com/blog/llmstxt-study/
- Cloudflare AI Crawl Control: https://developers.cloudflare.com/ai-crawl-control/

## Testes

```bash
python3 -m unittest discover -s ferramentas/auditor/tests
```

Sem rede: um site falso em `tests/fixtures/site/` (robots com grupos e curingas, sitemap, páginas com canônico duplo, noindex no sitemap, hreflang sem volta, JSON-LD inválido, link quebrado, órfã, CDN que barra OAI-SearchBot). O `tests/sitefalso.py` também serve aos testes do `agente-ready`.

## Código

- `auditor.py`: CLI, checagens e relatório.
- `inemaweb.py`: núcleo de coleta (Coletor educado, leitor de robots.txt, extrator de HTML, sitemap, lista de robôs por finalidade). O `agente-ready` importa este arquivo.
- Relatório HTML/CSV/JSON: `ferramentas/_comum/relatorio.py`.
