# botlog

Mostra quem lê o seu site de verdade: robôs de IA e buscadores no log de acesso, separados por **finalidade**, com o IP conferido nas listas oficiais que as próprias empresas publicam.

## Por que separar por finalidade

| Finalidade | Robôs | Se você bloquear |
|---|---|---|
| Busca de IA (citação) | OAI-SearchBot, Claude-SearchBot, PerplexityBot | some das respostas de busca da IA |
| Ação do usuário | ChatGPT-User, Claude-User, Perplexity-User | a IA não abre a página quando alguém pede |
| Treinamento | GPTBot, ClaudeBot | sai do treino de modelos futuros, sem sumir da busca |
| Buscador clássico | Googlebot, bingbot | some do Google / do Bing (e do Copilot) |

Fontes: [OpenAI](https://platform.openai.com/docs/bots), [Anthropic](https://support.anthropic.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler), [Perplexity](https://docs.perplexity.ai/guides/bots), [Google](https://developers.google.com/search/docs/crawling-indexing/verifying-googlebot). OAI-AdsBot (validação de anúncios da OpenAI) também é reconhecido, como "outro". UA com `bot`, `crawler` ou `spider` fora do catálogo entra como "robô fora do catálogo", sem verificação.

**Google-Extended não aparece em log.** É só um token de robots.txt que controla o uso do conteúdo para treinar o Gemini; quem busca é o Googlebot ([Google](https://developers.google.com/search/docs/crawling-indexing/google-common-crawlers)). O botlog não tenta achá-lo no User-Agent.

## Falso robô

Qualquer um escreve "GPTBot" no User-Agent. O botlog confere o IP de cada acesso na lista oficial do robô (pasta [`listas/`](listas/FONTES.md), com URL e data). Robô com lista e IP fora dela = **falso**. Falsos não contam nas finalidades nem como página lida. Com `--rdns`, Googlebot e bingbot fora da lista ainda são conferidos por DNS reverso + DNS direto, como o Google manda (usa a rede; desligado por padrão).

## O que o relatório mostra

- acessos por finalidade (barras), sem os falsos;
- por robô: acessos, com IP oficial, falsos, sem lista, páginas distintas, leituras do robots.txt, respostas 4xx/5xx (403 para robô de IA costuma ser bloqueio de CDN/WAF) e último acesso;
- quem leu o quê (robô × caminho);
- falsos robôs (IP, quem diz ser, caminhos);
- páginas que nenhum robô conseguiu ler: do `--sitemap` (arquivo ou URL) ou, sem ele, das páginas com resposta 200 no próprio log. "Ler" = robô do catálogo, não falso, resposta abaixo de 400;
- listas usadas com a data de cada uma.

Saída em `--saida`: `relatorio.html` (padrão INEMA dark), `relatorio.json`, `robos.csv`, `acessos.csv` (só acessos de robô; pessoa não entra).

## Formatos de log

- nginx/Apache **combined** (o padrão do nginx), também `.gz` (`access.log.2.gz`);
- **Cloudflare Logpush**, dataset HTTP requests, JSON por linha: `ClientIP`, `ClientRequestURI`, `ClientRequestUserAgent`, `EdgeResponseStatus`, `EdgeStartTimestamp` ([campos](https://developers.cloudflare.com/logs/logpush/logpush-job/datasets/zone/http_requests/));
- Vercel (log drain): não implementado **[a confirmar]** os nomes dos campos.

## Uso

```bash
# analisar (vários arquivos de uma vez, .gz incluso)
python3 botlog.py analisar ../../exemplos/botlog/entrada/MONTADO_access.log ../../exemplos/botlog/entrada/MONTADO_cloudflare.jsonl \
  --sitemap ../../exemplos/botlog/entrada/MONTADO_sitemap.xml --saida saida/montado
# 26 linhas, 22 de robô (treino 6, busca 5, buscador 4, usuario 3); falsos 4; nunca visitadas 1/6 → saida/montado/relatorio.html

# no servidor, só leitura (nginx): copie o log e rode aqui
ssh root@SEU_SERVIDOR 'cd /var/log/nginx; zcat -f access.log.*.gz; cat access.log.1 access.log' > /tmp/site.log
python3 botlog.py analisar /tmp/site.log --sitemap https://seusite.com/sitemap.xml --saida saida/site

# LGPD: antes de mostrar ou publicar um log, guarde só as linhas de robô com IP oficial
python3 botlog.py filtrar /tmp/site.log --saida /tmp/so-robos.log
# 8 de 3082 linha(s) mantidas (só robôs com IP oficial) → /tmp/so-robos.log
```

## Limite honesto

- Log mostra quem **pediu** a página, não se a IA usou o conteúdo numa resposta. Para citação, veja o [bing-ia](../bing-ia/).
- Site atrás de CDN: o log do servidor só vê o que passou pela CDN (e o IP pode ser o da CDN). Use o log da CDN.
- Listas mudam. Uma lista velha (a do Bing é de jan/2024) gera falso "falso"; atualize a pasta `listas/`.
- O IP de quem não é robô é dado pessoal (LGPD). O relatório o mostra só para falsos robôs; use `filtrar` antes de compartilhar.

## Teste

```bash
python3 -m unittest discover -s tests   # 14 testes, sem rede (rDNS fica fora)
```

Exemplos em [`exemplos/botlog/`](../../exemplos/botlog/): um log **real** de desenho.inema.pro já filtrado (só robôs com IP oficial) e uma amostra **montada** com os User-Agents oficiais.
