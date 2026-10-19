# bing-ia

Mostra onde o seu site é citado em respostas de IA do Bing e cruza com o Google. O Bing Webmaster Tools tem o relatório **AI Performance** (prévia pública desde fevereiro de 2026): total de citações, páginas citadas e as *grounding queries*, as frases que a IA usou para buscar o conteúdo citado. Cobre o Microsoft Copilot, os resumos de IA do Bing e integrações de parceiros ([Bing, 02/2026](https://blogs.bing.com/webmaster/2026/02/Introducing-AI-Performance-in-Bing-Webmaster-Tools-Public-Preview)). Hoje é o único painel oficial e gratuito de "fui citado por IA".

Não existe API para esses dados: o caminho é exportar o CSV no painel ([Search Influence](https://www.searchinfluence.com/blog/bing-ai-performance-report-copilot-citations/) relata que a API está "no backlog, sem prazo"). Esta ferramenta importa os CSV num SQLite e cruza com o banco do [gsc-historico](../gsc-historico/).

## O que o relatório mostra

| Seção | Para que serve |
|---|---|
| As 10 páginas mais citadas | o que a IA já usa como fonte |
| Citadas pela IA **e** com clique no Google | funcionam nos dois; manter atualizadas |
| Citadas pela IA, **sem** clique no Google | a IA confia, o Google não manda gente: revisar título e consulta-alvo |
| Com clique no Google, **nunca** citadas | candidatas a GEO (resposta direta, autoria, data, dados estruturados) |
| Ideias de conteúdo | grounding queries que não aparecem em nenhuma semana do gsc-historico |
| Grounding queries que já aparecem no Google | com impressões, cliques e melhor posição |

Saída em `--saida`: `relatorio.html` (padrão INEMA dark), `relatorio.json`, `ideias.csv`, `paginas.csv`.

## Colunas do CSV: leia isto

A Microsoft **não documenta as colunas do export** (procurado em 19/10/2026 no anúncio oficial; a página de ajuda do Bing Webmaster só abre com JavaScript). Por isso:

- a ferramenta tenta reconhecer sozinha nomes comuns — `Page`/`URL`, `Citations`, `Grounding Query`/`Query`, `Date` (e versões em português). Esses apelidos são palpite **[a confirmar]** com um export real;
- se não reconhecer, ela para e pede o mapa: `--colunas "url=<coluna>,citacoes=<coluna>,data=<coluna>"` (páginas) ou `--colunas "consulta=<coluna>,citacoes=<coluna>"` (grounding queries), com `--tipo paginas|consultas`;
- aceita vírgula, ponto e vírgula ou tabulação; datas `AAAA-MM-DD`, `MM/DD/AAAA` ou `DD/MM/AAAA` (nessa ordem: uma data ambígua como 01/12 é lida como 12 de janeiro).

## Uso

```bash
# 1. importar os CSV exportados (um de páginas, um de grounding queries; reimportar substitui)
python3 bing_ia.py importar ../../exemplos/bing-ia/entrada/*.csv --db dados/bing.sqlite
# FICTICIO_ai-performance-paginas.csv: 6 linha(s) de paginas (colunas {'url': 'Page', 'citacoes': 'Citations', 'data': 'Date'}) → dados/bing.sqlite

# 2. cruzar com o gsc-historico
python3 bing_ia.py relatorio --db dados/bing.sqlite --gsc-db ../gsc-historico/dados/gsc.sqlite --site inema.pro --saida saida/inema.pro
# 38 citações em 5 página(s), 6 grounding queries, 4 ideia(s), citadas sem clique no Google 5, clique sem citação 1 → saida/inema.pro/relatorio.html
```

Sem `--gsc-db` válido, o relatório sai só com os dados do Bing e avisa.

## Como cruza

- URL: sem esquema, sem `www.`, sem barra final, sem `?query` e `#fragmento` dos dois lados (`https://www.ex.com/a/` = `ex.com/a`).
- `--site inema.pro` filtra o Bing pelo domínio e subdomínios, e o Google pela propriedade `inema.pro` do gsc-historico.
- Consulta: minúsculas, sem acento, sem pontuação. Só igualdade exata conta como "já está no Google".

## Limite honesto

- Os números do Bing são amostra e não têm clique ([Bing, 02/2026](https://blogs.bing.com/webmaster/2026/02/Introducing-AI-Performance-in-Bing-Webmaster-Tools-Public-Preview)). Citação não é ranking nem autoridade.
- O cruzamento com o Google usa só as consultas **sem marca** que o gsc-historico guarda; uma página com clique só de marca aparece como "sem clique no Google".
- "Ideia de conteúdo" compara texto exato; variações da mesma pergunta contam como ideias diferentes.
- O Topics Portfolio (beta, 13/10/2026) não é lido aqui **[a confirmar]** se exporta CSV.

## Teste

```bash
python3 -m unittest discover -s tests   # 11 testes, sem rede
```

O exemplo em [`exemplos/bing-ia/`](../../exemplos/bing-ia/) usa CSV **fictícios** (números inventados com URLs reais do inema.pro), cruzados com o banco real do gsc-historico.
