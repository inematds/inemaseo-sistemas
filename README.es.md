# inemaseo-sistemas

[![inemaseo-sistemas](guia/assets/banner-es.jpg)](https://inematds.github.io/inemaseo-sistemas/guia/es/)

**🇧🇷 [Português](README.md) · 🇺🇸 [English](README.en.md) · 🇪🇸 [Español](README.es.md)**

## Qué es

inemaseo-sistemas es un conjunto de cinco programas gratuitos para cuidar el SEO (cómo aparece el sitio en Google y en las IA) de **tu propio** sitio. Sirve para quien tiene un sitio y quiere saber qué está roto, quién lo encuentra, qué robots de IA leen las páginas y si el sitio está listo para agentes de IA. Todo corre en tu computadora, con Python 3.10 o más nuevo, usando solo datos gratuitos: el sitio, el log del servidor y los archivos que Search Console y Bing Webmaster permiten descargar.

## 📖 Guía de uso

Guía completa (landing + paso a paso): **https://inematds.github.io/inemaseo-sistemas/guia/es/**

El "Semrush abierto" de **tu propio sitio**: 5 herramientas de línea de comandos que corren en tu computadora, solo con Python 3.10+ (biblioteca estándar), sin API de pago y sin cuenta en ningún servicio además de Search Console y Bing Webmaster, que son gratuitos. Licencia MIT.

Forma parte de [inemaSEO](https://eventos.inema.pro/inemaseo/) y es la base del curso 7 de la Formación inemaSEO.

| herramienta | qué responde | de dónde viene el dato |
|---|---|---|
| [gsc-historico](ferramentas/gsc-historico/) (en portugués) | cuántas búsquedas **sin tu marca** te encontraron, semana a semana, para siempre (Search Console solo guarda 16 meses) | CSV de `gsc_semanal.py` (Search Console) |
| [bing-ia](ferramentas/bing-ia/) | qué páginas citó Copilot/Bing y si también tienen clics en Google | export de Bing Webmaster AI Performance |
| [botlog](ferramentas/botlog/) | qué robots de IA leyeron el sitio de verdad, por finalidad (búsqueda, pedido del usuario, entrenamiento), y cuáles son falsos | log de acceso de tu servidor + listas oficiales de IP |
| [auditor](ferramentas/auditor/) | qué está roto en el HTML que entrega el servidor (canónico, hreflang, sitemap, robots por finalidad, bloqueo de CDN, huérfanas) | tu sitio, rastreado con cortesía |
| [agente-ready](ferramentas/agente-ready/) | nota 0–100 de preparación para IA y agentes, con pesos públicos | tu sitio |

## Empezar
```bash
git clone https://github.com/inematds/inemaseo-sistemas && cd inemaseo-sistemas
python3 ferramentas/auditor/auditor.py https://seusite.com --max 50
python3 ferramentas/agente-ready/agente-ready.py https://seusite.com
```
Cada carpeta tiene su propio README con todos los comandos, el límite honesto de la herramienta y las fuentes. Ejemplos reales (sitios de INEMA, 19/10/2026) en [exemplos/](exemplos/) (en portugués).

## Qué se puede y qué no se puede hacer gratis
Se puede: auditoría técnica, historial de Search Console, citas oficiales de Bing, robots de IA en el log, nota de preparación. **No se puede** sin datos de pago: volumen exacto de búsqueda, dificultad de palabra clave, SERP de la competencia, backlinks completos y monitor automático de las respuestas de las IA. Para eso existen DataForSEO, Firecrawl, Apify, Semrush y Ahrefs — opcionales, fuera de este repo. Comparativo en [docs/ESPEC.md](docs/ESPEC.md) (en portugués).

## Pruebas
```bash
for t in ferramentas/*/; do [ -d $t/tests ] && python3 -m unittest discover -s $t/tests; done
```
