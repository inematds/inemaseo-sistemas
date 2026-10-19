# inemaseo-sistemas

O "Semrush aberto" do **seu próprio site**: 5 ferramentas de linha de comando que rodam no seu computador, só com Python 3.10+ (biblioteca padrão), sem API paga e sem conta em serviço nenhum além do Search Console e do Bing Webmaster, que são grátis. Licença MIT.

Faz parte do [inemaSEO](https://eventos.inema.pro/inemaseo/) e é a base do curso 7 da Formação inemaSEO.

| ferramenta | o que responde | de onde vem o dado |
|---|---|---|
| [gsc-historico](ferramentas/gsc-historico/) | quantas buscas **sem a sua marca** te acharam, semana a semana, para sempre (o Search Console só guarda 16 meses) | CSV do `gsc_semanal.py` (Search Console) |
| [bing-ia](ferramentas/bing-ia/) | quais páginas o Copilot/Bing citou e se elas também têm clique no Google | export do Bing Webmaster AI Performance |
| [botlog](ferramentas/botlog/) | quais robôs de IA leram o site de verdade, por finalidade (busca, pedido do usuário, treino), e quais são falsos | log de acesso do seu servidor + listas oficiais de IP |
| [auditor](ferramentas/auditor/) | o que está quebrado no HTML que o servidor entrega (canônico, hreflang, sitemap, robots por finalidade, bloqueio de CDN, órfãs) | o seu site, rastreado com educação |
| [agente-ready](ferramentas/agente-ready/) | nota 0–100 de prontidão para IA e agentes, com pesos públicos | o seu site |

## Começar
```bash
git clone https://github.com/inematds/inemaseo-sistemas && cd inemaseo-sistemas
python3 ferramentas/auditor/auditor.py https://seusite.com --max 50
python3 ferramentas/agente-ready/agente-ready.py https://seusite.com
```
Cada pasta tem o próprio README com todos os comandos, o limite honesto da ferramenta e as fontes. Exemplos reais (sites do INEMA, 19/10/2026) em [exemplos/](exemplos/).

## O que dá e o que não dá para fazer de graça
Dá: auditoria técnica, histórico do Search Console, citações oficiais do Bing, robôs de IA no log, nota de prontidão. **Não dá** sem dado pago: volume exato de busca, dificuldade de palavra-chave, SERP de concorrente, backlinks completos e monitor automático das respostas das IAs. Para isso existem DataForSEO, Firecrawl, Apify, Semrush e Ahrefs — opcionais, fora deste repo. Comparativo em [docs/ESPEC.md](docs/ESPEC.md).

## Testes
```bash
for t in ferramentas/*/; do [ -d $t/tests ] && python3 -m unittest discover -s $t/tests; done
```

---
**English:** a free, local "open Semrush" for your own site — 5 stdlib-only Python CLIs (Search Console history, Bing AI citations, AI bot log analysis, technical auditor, AI/agent readiness score). MIT. Docs are in Portuguese; guide in EN/ES at `guia/`.
**Español:** un "Semrush abierto" gratuito y local para tu propio sitio — 5 herramientas en Python (historial de Search Console, citas de IA en Bing, robots de IA en el log, auditor técnico, nota de preparación para agentes). MIT. Guía en ES en `guia/es/`.
