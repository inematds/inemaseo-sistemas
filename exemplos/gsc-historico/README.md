# Exemplo — gsc-historico

- `entrada/`: CSV **reais** do `gsc_semanal.py` para inema.club e inema.pro, semanas de 16/09 a 11/10/2026 (cópia de `~/projetos/inemaseo/data/gsc/`). Retirada uma linha cuja consulta parecia nome de pessoa.
- `saida-inema.club/`, `saida-inema.pro/`: relatório gerado de verdade com os comandos abaixo.

```bash
cd ferramentas/gsc-historico
python3 gsc_historico.py importar ../../exemplos/gsc-historico/entrada --db /tmp/gsc.sqlite
python3 gsc_historico.py relatorio --db /tmp/gsc.sqlite --site inema.club --saida ../../exemplos/gsc-historico/saida-inema.club
python3 gsc_historico.py relatorio --db /tmp/gsc.sqlite --site inema.pro  --saida ../../exemplos/gsc-historico/saida-inema.pro
```

O banco SQLite não vai para o repositório (`.gitignore`); o comando acima recria.
