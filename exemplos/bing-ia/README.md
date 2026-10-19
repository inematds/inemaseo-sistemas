# Exemplo — bing-ia

- `entrada/FICTICIO_*.csv`: **dados fictícios**. Os números de citação e as grounding queries foram inventados para mostrar a ferramenta; as URLs são páginas reais do inema.pro. O nome das colunas (`Date`, `Page`, `Citations`, `Grounding Query`) é palpite: a Microsoft não documenta o export [a confirmar com um CSV real].
- `saida/`: relatório gerado de verdade, cruzando esses CSV com o banco **real** do gsc-historico (exemplo `exemplos/gsc-historico/entrada`).

```bash
cd ferramentas/gsc-historico
python3 gsc_historico.py importar ../../exemplos/gsc-historico/entrada --db /tmp/gsc.sqlite
cd ../bing-ia
python3 bing_ia.py importar ../../exemplos/bing-ia/entrada/*.csv --db /tmp/bing.sqlite
python3 bing_ia.py relatorio --db /tmp/bing.sqlite --gsc-db /tmp/gsc.sqlite --site inema.pro --saida ../../exemplos/bing-ia/saida
```
