# inemaseo-sistemas

[![inemaseo-sistemas](guia/assets/banner-en.jpg)](https://inematds.github.io/inemaseo-sistemas/guia/en/)

**🇧🇷 [Português](README.md) · 🇺🇸 [English](README.en.md) · 🇪🇸 [Español](README.es.md)**

## What it is

inemaseo-sistemas is a set of five free programs for taking care of the SEO (how your site shows up on Google and in AIs) of **your own** site. It is for anyone who has a website and wants to know what is broken, who finds you, which AI bots read your pages, and whether the site is ready for AI agents. Everything runs on your computer, with Python 3.10 or newer, using only free data: the site itself, the server log, and the files that Search Console and Bing Webmaster let you download.

## 📖 User guide

Full guide (landing page + step by step): **https://inematds.github.io/inemaseo-sistemas/guia/en/**

The "open Semrush" for **your own site**: 5 command-line tools that run on your computer, with just Python 3.10+ (standard library), no paid API and no account on any service other than Search Console and Bing Webmaster, which are free. MIT license.

Part of [inemaSEO](https://eventos.inema.pro/inemaseo/) and the basis of course 7 of the inemaSEO Training.

| tool | what it answers | where the data comes from |
|---|---|---|
| [gsc-historico](ferramentas/gsc-historico/) (in Portuguese) | how many searches **without your brand name** found you, week by week, forever (Search Console only keeps 16 months) | CSV from `gsc_semanal.py` (Search Console) |
| [bing-ia](ferramentas/bing-ia/) | which pages Copilot/Bing cited and whether they also get clicks on Google | Bing Webmaster AI Performance export |
| [botlog](ferramentas/botlog/) | which AI bots actually read the site, by purpose (search, user request, training), and which ones are fake | your server's access log + official IP lists |
| [auditor](ferramentas/auditor/) | what is broken in the HTML the server delivers (canonical, hreflang, sitemap, robots by purpose, CDN blocking, orphan pages) | your site, crawled politely |
| [agente-ready](ferramentas/agente-ready/) | 0–100 readiness score for AI and agents, with public weights | your site |

## Getting started
```bash
git clone https://github.com/inematds/inemaseo-sistemas && cd inemaseo-sistemas
python3 ferramentas/auditor/auditor.py https://seusite.com --max 50
python3 ferramentas/agente-ready/agente-ready.py https://seusite.com
```
Each folder has its own README with all the commands, the tool's honest limits, and the sources. Real examples (INEMA sites, 10/19/2026) in [exemplos/](exemplos/) (in Portuguese).

## What you can and can't do for free
You can: technical audit, Search Console history, official Bing citations, AI bots in the log, readiness score. You **can't**, without paid data: exact search volume, keyword difficulty, competitor SERPs, full backlinks, and automatic monitoring of AI answers. For that there are DataForSEO, Firecrawl, Apify, Semrush, and Ahrefs — optional, outside this repo. Comparison in [docs/ESPEC.md](docs/ESPEC.md) (in Portuguese).

## Tests
```bash
for t in ferramentas/*/; do [ -d $t/tests ] && python3 -m unittest discover -s $t/tests; done
```
