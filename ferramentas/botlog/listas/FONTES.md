# Listas oficiais de IP dos robôs

Baixadas com `curl` (HTTP GET, arquivo público) em **19/10/2026**. `creationTime` é a data que a própria empresa grava no arquivo. Atualize de tempos em tempos com o mesmo comando e faça commit: o histórico do git guarda as versões.

| Arquivo | URL | creationTime | Faixas | Robô(s) | Página que aponta a lista |
|---|---|---|---|---|---|
| `openai.com_gptbot.json` | https://openai.com/gptbot.json | 2026-09-22 | 18 | GPTBot | https://platform.openai.com/docs/bots |
| `openai.com_searchbot.json` | https://openai.com/searchbot.json | 2026-01-02 | 39 | OAI-SearchBot | idem |
| `openai.com_chatgpt-user.json` | https://openai.com/chatgpt-user.json | 2026-10-07 | 234 | ChatGPT-User | idem |
| `claude.com_bots.json` | https://claude.com/crawling/bots.json | 2026-10-07 | 38 | ClaudeBot, Claude-User, Claude-SearchBot (uma lista para os três) | https://support.anthropic.com/en/articles/8896518 |
| `www.perplexity.com_perplexitybot.json` | https://www.perplexity.com/perplexitybot.json | 2025-02-07 | 8 | PerplexityBot | https://docs.perplexity.ai/guides/bots |
| `www.perplexity.com_perplexity-user.json` | https://www.perplexity.com/perplexity-user.json | 2025-10-17 | 4 | Perplexity-User | idem |
| `developers.google.com_googlebot.json` | https://developers.google.com/static/search/apis/ipranges/googlebot.json | 2026-10-16 | 317 | Googlebot | https://developers.google.com/search/docs/crawling-indexing/verifying-googlebot |
| `developers.google.com_special-crawlers.json` | …/ipranges/special-crawlers.json | 2026-10-16 | 272 | AdsBot e outros especiais (não usado na classificação) | idem |
| `developers.google.com_user-triggered-fetchers.json` | …/ipranges/user-triggered-fetchers.json | 2026-10-16 | 1068 | buscas disparadas por usuário (não usado) | idem |
| `developers.google.com_user-triggered-fetchers-google.json` | …/ipranges/user-triggered-fetchers-google.json | 2026-10-16 | 504 | idem (não usado) | idem |
| `developers.google.com_user-triggered-agents.json` | …/ipranges/user-triggered-agents.json | 2026-03-03 | 4 | agentes disparados por usuário (não usado) | idem |
| `www.bing.com_bingbot.json` | https://www.bing.com/toolbox/bingbot.json | **2024-01-03** | 28 | bingbot | https://www.bing.com/webmasters/help/how-to-verify-bingbot-3905dc26 |

Observações:

- A lista do Bing é de janeiro de 2024. Pode estar desatualizada: um bingbot de verdade fora dela aparece como "falso". Use `--rdns` para conferir por DNS reverso (sufixo `search.msn.com` **[a confirmar]**: a página de ajuda do Bing só abre com JavaScript e não foi relida).
- Para o Google, o DNS reverso tem de terminar em `googlebot.com`, `google.com` ou `googleusercontent.com` e o nome tem de resolver de volta para o mesmo IP (página de verificação do Google acima, lida em 19/10/2026).
- A OpenAI publica a lista do OAI-AdsBot? Não achei na página dos robôs **[a confirmar]**; o botlog marca esse robô como "sem lista".
- Os IPs do OAI-SearchBot aparecem também na lista do GPTBot (conferido no log real de 19/10/2026). O botlog confere cada robô contra a lista dele.
