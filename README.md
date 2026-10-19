# inemaseo-sistemas

[![inemaseo-sistemas](guia/assets/banner.jpg)](https://inematds.github.io/inemaseo-sistemas/guia/)

**🇧🇷 [Português](README.md) · 🇺🇸 [English](README.en.md) · 🇪🇸 [Español](README.es.md)**

## O que é

O inemaseo-sistemas é um conjunto de cinco programas gratuitos para cuidar do SEO (como o site aparece no Google e nas IAs) do **seu próprio** site. Serve para quem tem um site e quer saber o que está quebrado, quem te encontra, quais robôs de IA leem as páginas e se o site está pronto para agentes de IA. Tudo roda no seu computador, com o Python 3.10 ou mais novo, usando só dado grátis: o site, o log do servidor e os arquivos que o Search Console e o Bing Webmaster deixam baixar.

## 📖 Guia de uso

Guia completo (landing + passo a passo): **https://inematds.github.io/inemaseo-sistemas/guia/**

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
**English:** [README.en.md](README.en.md) · guide: https://inematds.github.io/inemaseo-sistemas/guia/en/
**Español:** [README.es.md](README.es.md) · guía: https://inematds.github.io/inemaseo-sistemas/guia/es/
