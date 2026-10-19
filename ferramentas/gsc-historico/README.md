# gsc-historico

Guarda o Google Search Console para sempre. A interface e a API do Search Console guardam 16 meses de dados de desempenho ([Google, 2018](https://developers.google.com/search/blog/2018/01/introducing-new-search-console)). Esta ferramenta importa os CSV semanais do `gsc_semanal.py` (repositório `inemaseo-metodo`) num banco SQLite local que nunca apaga nada, e gera um relatório.

## O que o relatório mostra

| Seção | De onde vem |
|---|---|
| Série semanal: marca × sem marca × anônimas (cliques e impressões) | `resumo.csv` |
| Consultas que subiram e que caíram (semana atual × anterior) | `<fim>_<site>_sem-marca.csv`, somando as páginas de cada consulta |
| Pauta: consultas novas sem página dona | idem (regra abaixo) |
| Consultas novas que já têm página, mas fora da 1ª página | idem |
| Páginas com impressão e 0 clique (reescrever título e descrição) | idem |

Saída em `--saida`: `relatorio.html` (padrão INEMA dark), `relatorio.json`, `serie.csv`, `pauta.csv`, `melhorar.csv`, `paginas_sem_clique.csv`.

## De onde vem o dado

O formato é o do `gsc_semanal.py`:

- `resumo.csv`: `inicio,fim,site,total_cliques,total_impr,marca_cliques,marca_impr,sem_marca_cliques,sem_marca_impr,anonimas_cliques,anonimas_impr,consultas_sem_marca` (uma linha por semana e site);
- `<fim>_<site>_sem-marca.csv`: `query,page,clicks,impressions,ctr,position`, só consultas que não batem com a regex da marca.

"Anônimas" é o que o Google esconde quando a consulta é rara: total menos marca menos sem marca ([Google: consultas anonimizadas entram no total, não na tabela](https://developers.google.com/search/blog/2022/10/performance-data-deep-dive)).

## Regras desta ferramenta (não são regras do Google)

- **Página dona.** Uma consulta tem página dona quando (a) alguma página do site aparece na 1ª página (melhor posição ≤ 10, mude com `--posicao-dona`) ou (b) o endereço de alguma página que aparece tem palavra da consulta (4+ letras, sem acento). Sem dona = **pauta**: escreva uma página feita para ela. Com dona por (b) e fora da 1ª página = **melhorar** a página que existe.
- **Consulta nova** = nunca apareceu no banco antes da semana atual. Quanto mais semanas no banco, mais confiável.
- **Página sem clique** usa só consultas sem marca, com mínimo de 5 impressões na semana (`--min-impr`). A página pode ter clique de marca.
- **Semanas sobrepostas.** Se o `gsc_semanal.py` rodou em dias seguidos, duas "semanas" dividem dias (ex.: 27/09–03/10 e 28/09–04/10). O banco guarda as duas (chave `site + fim`), o relatório avisa e não soma.

## Uso

```bash
# 1. importar (pasta ou arquivos; reimportar não duplica)
python3 gsc_historico.py importar ../../exemplos/gsc-historico/entrada --db dados/gsc.sqlite
# importado: 10 linha(s) de resumo, 244 linha(s) de consulta → dados/gsc.sqlite

# 2. relatório de um site (semana mais recente × anterior; ou --atual / --anterior AAAA-MM-DD)
python3 gsc_historico.py relatorio --db dados/gsc.sqlite --site inema.club --saida saida/inema.club
# inema.club semana 2026-10-11 (comparada com 2026-10-04): sem marca 0 cliques / 157 impr.; subiram 15, caíram 15, pauta 18, páginas sem clique 5 → saida/inema.club/relatorio.html
```

Toda semana, depois do `gsc_semanal.py`, rode o `importar` apontando para a pasta dele (ex.: `~/projetos/inemaseo/data/gsc/`). Pode ir no mesmo cron.

### Modo API (opcional)

`python3 gsc_historico.py puxar --script ~/projetos/inemaseo-metodo/tools/gsc_semanal.py --pasta dados/gsc-csv` roda o `gsc_semanal.py` (Search Console API, Application Default Credentials do `gcloud`, variáveis `GSC_SITES`, `GSC_MARCA`, `GSC_QUOTA_PROJ`) e importa a pasta. **Não foi testado ao vivo** e os testes não o usam. Nenhuma credencial fica neste repositório.

## Limite honesto

- Só sabe o que o `gsc_semanal.py` exportou: consultas sem marca com dimensão `query + page`, até 25.000 linhas por chamada. Consultas de marca entram só como soma no `resumo.csv`.
- "Subiu/caiu" compara impressões e cliques somados por consulta; a posição mostrada é a melhor entre as páginas.
- A regra da página dona é heurística: compara palavras da consulta com o endereço, não com o conteúdo da página.

## Teste

```bash
python3 -m unittest discover -s tests   # 10 testes, sem rede
```

O exemplo em [`exemplos/gsc-historico/`](../../exemplos/gsc-historico/) usa os CSV reais de inema.club e inema.pro (16/09 a 11/10/2026), os mesmos números que já aparecem nos relatórios públicos do inemaSEO; uma consulta que parecia nome de pessoa foi retirada.
