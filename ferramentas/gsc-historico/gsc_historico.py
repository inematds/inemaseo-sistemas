#!/usr/bin/env python3
"""gsc-historico — guarda o Google Search Console para sempre num SQLite local.

A interface e a API do Search Console só mostram ~16 meses. Esta ferramenta importa os CSV semanais do
gsc_semanal.py (inemaseo-metodo) — `<fim>_<site>_sem-marca.csv` e `resumo.csv` — e guarda tudo num banco
SQLite que nunca apaga nada. Depois gera o relatório: série semanal marca × sem marca × anônimas,
consultas que subiram e caíram, consultas novas sem página dona (pauta) e páginas com impressão e 0 clique.

Comandos:
  importar  PASTA_OU_CSV...  [--db dados/gsc.sqlite]
  relatorio --site SITE [--db ...] [--saida saida/] [--atual AAAA-MM-DD] [--anterior AAAA-MM-DD]
  puxar     (modo API, opcional: mesma autenticação do gsc_semanal.py; NÃO testado ao vivo)

Exemplos:
  python3 gsc_historico.py importar ../../exemplos/gsc-historico/entrada --db /tmp/gsc.sqlite
  python3 gsc_historico.py relatorio --db /tmp/gsc.sqlite --site inema.club --saida /tmp/gsc-rel
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import re
import sqlite3
import sys
import unicodedata
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _comum import relatorio as R  # noqa: E402

NOME_SEMANA = re.compile(r'^(\d{4}-\d{2}-\d{2})_(.+)_sem-marca\.csv$')
CAMPOS_RESUMO = ['total_cliques', 'total_impr', 'marca_cliques', 'marca_impr', 'sem_marca_cliques',
                 'sem_marca_impr', 'anonimas_cliques', 'anonimas_impr', 'consultas_sem_marca']
ESQUEMA = f"""
CREATE TABLE IF NOT EXISTS semanas (site TEXT, inicio TEXT, fim TEXT,
  {', '.join(c + ' INTEGER' for c in CAMPOS_RESUMO)}, importado_em TEXT, PRIMARY KEY (site, fim));
CREATE TABLE IF NOT EXISTS linhas (site TEXT, fim TEXT, query TEXT, page TEXT, clicks INTEGER,
  impressions INTEGER, ctr REAL, position REAL, PRIMARY KEY (site, fim, query, page));
CREATE INDEX IF NOT EXISTS ix_linhas_query ON linhas (site, query);
CREATE INDEX IF NOT EXISTS ix_linhas_page ON linhas (site, page);
"""


def conectar(db) -> sqlite3.Connection:
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.executescript(ESQUEMA)
    return con


# ---------------------------------------------------------------- importar
def _arquivos(entradas):
    for e in entradas:
        p = Path(e)
        if p.is_dir():
            yield from sorted(p.glob('*.csv'))
        elif p.exists():
            yield p
        else:
            raise SystemExit(f'não achei: {e}')


def importar(con, entradas) -> dict:
    """Importa resumo.csv e *_sem-marca.csv. Idempotente: a chave é (site, fim) e (site, fim, query, page)."""
    agora = datetime.datetime.now().isoformat(timespec='seconds')
    cont = {'semanas': 0, 'linhas': 0, 'ignorados': []}
    for arq in _arquivos(entradas):
        m = NOME_SEMANA.match(arq.name)
        with open(arq, newline='', encoding='utf-8-sig') as f:
            rd = csv.DictReader(f)
            if arq.name == 'resumo.csv' or {'inicio', 'fim', 'site'} <= set(rd.fieldnames or []):
                for r in rd:
                    con.execute(f'INSERT OR REPLACE INTO semanas VALUES (?,?,?,{",".join("?" * len(CAMPOS_RESUMO))},?)',
                                [r['site'], r['inicio'], r['fim'], *[int(float(r[c] or 0)) for c in CAMPOS_RESUMO],
                                 agora])
                    cont['semanas'] += 1
            elif m:
                fim, site = m.groups()
                for r in rd:
                    con.execute('INSERT OR REPLACE INTO linhas VALUES (?,?,?,?,?,?,?,?)',
                                [site, fim, r['query'], r['page'], int(float(r['clicks'])),
                                 int(float(r['impressions'])), float(r['ctr']), float(r['position'])])
                    cont['linhas'] += 1
            else:
                cont['ignorados'].append(arq.name)
    con.commit()
    return cont


# ---------------------------------------------------------------- análises
def semanas_com_linhas(con, site):
    return [r[0] for r in con.execute('SELECT DISTINCT fim FROM linhas WHERE site=? ORDER BY fim', [site])]


def serie(con, site):
    cur = con.execute(f'SELECT inicio, fim, {", ".join(CAMPOS_RESUMO)} FROM semanas WHERE site=? ORDER BY fim',
                      [site])
    cols = ['inicio', 'fim', *CAMPOS_RESUMO]
    return [dict(zip(cols, r)) for r in cur]


def _por_consulta(con, site, fim):
    """Soma por consulta (todas as páginas). Posição = melhor posição entre as páginas."""
    q = {}
    for query, clk, imp, pos in con.execute(
            'SELECT query, SUM(clicks), SUM(impressions), MIN(position) FROM linhas WHERE site=? AND fim=? '
            'GROUP BY query', [site, fim]):
        q[query] = {'cliques': clk, 'impressoes': imp, 'melhor_posicao': pos}
    return q


def variacao(con, site, anterior, atual, n=15):
    a, b = _por_consulta(con, site, anterior), _por_consulta(con, site, atual)
    lin = []
    for k in set(a) | set(b):
        ia, ib = a.get(k, {}).get('impressoes', 0), b.get(k, {}).get('impressoes', 0)
        ca, cb = a.get(k, {}).get('cliques', 0), b.get(k, {}).get('cliques', 0)
        lin.append({'consulta': k, 'impr_antes': ia, 'impr_agora': ib, 'delta_impr': ib - ia,
                    'cliques_antes': ca, 'cliques_agora': cb, 'delta_cliques': cb - ca,
                    'posicao_antes': a.get(k, {}).get('melhor_posicao'),
                    'posicao_agora': b.get(k, {}).get('melhor_posicao')})
    subiu = sorted([l for l in lin if l['delta_impr'] > 0 or l['delta_cliques'] > 0],
                   key=lambda l: (-l['delta_cliques'], -l['delta_impr'], l['consulta']))[:n]
    caiu = sorted([l for l in lin if l['delta_impr'] < 0 or l['delta_cliques'] < 0],
                  key=lambda l: (l['delta_cliques'], l['delta_impr'], l['consulta']))[:n]
    return subiu, caiu


def _palavras(texto):
    """Palavras de 4+ letras, sem acento e em minúsculas (para comparar consulta com o endereço da página)."""
    t = unicodedata.normalize('NFKD', texto.lower())
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return {w for w in re.split(r'[^a-z0-9]+', t) if len(w) >= 4}


def pauta(con, site, atual, posicao_dona=10.0):
    """Consultas NOVAS (nunca vistas antes de `atual`) com impressão e 0 clique, separadas em duas listas.

    Regra desta ferramenta (não é regra do Google). Uma consulta TEM página dona quando
    (a) alguma página do site aparece na 1ª página (melhor posição <= posicao_dona), ou
    (b) o endereço de alguma página que aparece tem palavra da consulta (4+ letras, sem acento).
    - sem dona → `pauta`: escreva uma página feita para ela;
    - com dona por (b) mas fora da 1ª página → `melhorar`: a página existe, falta força ou clareza.
    """
    vistas = {r[0] for r in con.execute('SELECT DISTINCT query FROM linhas WHERE site=? AND fim<?', [site, atual])}
    out, melhorar = [], []
    for query, imp, clk, pos, paginas in con.execute(
            'SELECT query, SUM(impressions), SUM(clicks), MIN(position), GROUP_CONCAT(page, " | ") '
            'FROM linhas WHERE site=? AND fim=? GROUP BY query', [site, atual]):
        if query in vistas or imp <= 0 or clk > 0 or pos <= posicao_dona:
            continue
        caminhos = ' '.join(urllib.parse.urlsplit(p.strip()).path for p in paginas.split(' | '))
        item = {'consulta': query, 'impressoes': imp, 'melhor_posicao': pos, 'paginas_hoje': paginas}
        (melhorar if _palavras(query) & _palavras(caminhos) else out).append(item)
    chave = lambda r: (-r['impressoes'], r['consulta'])
    return sorted(out, key=chave), sorted(melhorar, key=chave)


def paginas_sem_clique(con, site, atual, min_impr=5):
    """Páginas com impressões (consultas sem marca) e 0 clique na semana: candidatas a reescrever título."""
    out = []
    for page, imp, clk, pos, nq in con.execute(
            'SELECT page, SUM(impressions), SUM(clicks), ROUND(SUM(position*impressions)*1.0/SUM(impressions),1), '
            'COUNT(DISTINCT query) FROM linhas WHERE site=? AND fim=? GROUP BY page', [site, atual]):
        if clk == 0 and imp >= min_impr:
            out.append({'pagina': page, 'impressoes': imp, 'posicao_media': pos, 'consultas': nq})
    return sorted(out, key=lambda r: (-r['impressoes'], r['pagina']))


def analisar(con, site, atual=None, anterior=None, posicao_dona=10.0, min_impr=5):
    fins = semanas_com_linhas(con, site)
    if not fins:
        raise SystemExit(f'sem dados de consultas para o site {site!r} (rode "importar" antes)')
    atual = atual or fins[-1]
    anteriores = [f for f in fins if f < atual]
    anterior = anterior or (anteriores[-1] if anteriores else None)
    subiu, caiu = variacao(con, site, anterior, atual) if anterior else ([], [])
    sem_dona, melhorar = pauta(con, site, atual, posicao_dona)
    return {'site': site, 'atual': atual, 'anterior': anterior, 'semanas_disponiveis': fins,
            'serie': serie(con, site), 'subiram': subiu, 'cairam': caiu,
            'pauta': sem_dona, 'melhorar': melhorar, 'paginas_sem_clique': paginas_sem_clique(
                con, site, atual, min_impr), 'regras': {'posicao_dona': posicao_dona, 'min_impr': min_impr}}


# ---------------------------------------------------------------- saída
def _sobreposicao(serie_):
    """Semanas cujo intervalo se sobrepõe ao da anterior (o gsc_semanal.py rodado em dias seguidos)."""
    out = []
    for a, b in zip(serie_, serie_[1:]):
        if b['inicio'] <= a['fim']:
            out.append(f"{a['inicio']}..{a['fim']} e {b['inicio']}..{b['fim']}")
    return out


def html(res) -> str:
    s = res['serie']
    ult = s[-1] if s else {}
    corpo = R.numeros([
        (ult.get('sem_marca_impr', '-'), f"impressões sem marca ({ult.get('fim', '-')})"),
        (ult.get('sem_marca_cliques', '-'), 'cliques sem marca'),
        (ult.get('marca_cliques', '-'), 'cliques de marca'),
        (len(res['pauta']), 'consultas novas sem página dona'),
        (len(res['paginas_sem_clique']), 'páginas com impressão e 0 clique'),
    ])
    corpo += ('<p class="mut">Sem marca = gente que não te conhecia e te achou. É o número que mostra se o '
              'SEO está funcionando. "Anônimas" = o que o Google esconde quando a consulta é rara '
              '(total menos marca menos sem marca).</p>')
    # série
    mx = max([max(r['marca_impr'], r['sem_marca_impr'], r['anonimas_impr']) for r in s] or [1])
    lin = []
    for r in s:
        lin.append(f"<tr><td>{R.esc(r['inicio'])}..{R.esc(r['fim'])}</td>"
                   f"<td>{r['marca_cliques']} / {r['marca_impr']}{R.barra(r['marca_impr'], mx)}</td>"
                   f"<td>{r['sem_marca_cliques']} / {r['sem_marca_impr']}{R.barra(r['sem_marca_impr'], mx)}</td>"
                   f"<td>{r['anonimas_cliques']} / {r['anonimas_impr']}{R.barra(r['anonimas_impr'], mx)}</td>"
                   f"<td>{r['consultas_sem_marca']}</td></tr>")
    tab = ('<table><thead><tr><th>semana</th><th>marca (cliques / impr.)</th><th>sem marca</th>'
           f'<th>anônimas</th><th>consultas sem marca</th></tr></thead><tbody>{"".join(lin)}</tbody></table>')
    sob = _sobreposicao(s)
    if sob:
        tab += (f'<p class="mut">Atenção: {len(sob)} par(es) de semanas se sobrepõem ({"; ".join(sob)}). '
                'O script semanal rodou em dias seguidos; não some as linhas.</p>')
    corpo += R.bloco('Série semanal: marca × sem marca × anônimas', tab)
    cmp_ = f"{res['anterior']} → {res['atual']}" if res['anterior'] else 'só existe uma semana'
    cab = ['consulta', 'impr. antes', 'impr. agora', 'Δ impr.', 'cliques antes', 'cliques agora', 'posição agora']
    fl = lambda ls: [[l['consulta'], l['impr_antes'], l['impr_agora'], f"{l['delta_impr']:+d}", l['cliques_antes'],
                      l['cliques_agora'], l['posicao_agora'] if l['posicao_agora'] is not None else '—'] for l in ls]
    corpo += R.bloco(f'Consultas que subiram ({cmp_})', R.tabela(cab, fl(res['subiram'])))
    corpo += R.bloco(f'Consultas que caíram ({cmp_})', R.tabela(cab, fl(res['cairam'])))
    cab_p = ['consulta', 'impressões', 'melhor posição', 'página que aparece hoje']
    lin_p = lambda ls: [[p['consulta'], p['impressoes'], p['melhor_posicao'], p['paginas_hoje']] for p in ls]
    corpo += R.bloco('Pauta: consultas novas sem página dona', (
        f'<p class="mut">Regra desta ferramenta (não do Google): consulta que apareceu pela 1ª vez em '
        f'{R.esc(res["atual"])}, com impressão, 0 clique, nenhuma página na 1ª página (melhor posição &gt; '
        f'{res["regras"]["posicao_dona"]:g}) e nenhuma página cujo endereço tenha palavra da consulta. '
        'Escreva uma página feita para ela.</p>') + R.tabela(cab_p, lin_p(res['pauta'])))
    corpo += R.bloco('Consultas novas que já têm página, mas fora da 1ª página', (
        '<p class="mut">O endereço da página tem palavra da consulta, mas ela está depois da posição '
        f'{res["regras"]["posicao_dona"]:g}. Não precisa de página nova: reforce a que existe.</p>')
        + R.tabela(cab_p, lin_p(res['melhorar'])))
    corpo += R.bloco('Páginas com impressão e 0 clique (reescrever título e descrição)', (
        f'<p class="mut">Só consultas sem marca; mínimo de {res["regras"]["min_impr"]} impressões na semana. '
        'Se a posição média é boa e ninguém clica, o título não convence.</p>') + R.tabela(
        ['página', 'impressões', 'posição média', 'consultas'],
        [[p['pagina'], p['impressoes'], p['posicao_media'], p['consultas']] for p in res['paginas_sem_clique']]))
    return R.pagina(f'Histórico do Search Console — <span>{R.esc(res["site"])}</span>', corpo,
                    subtitulo=f'Semana atual {R.esc(res["atual"])} · {len(res["semanas_disponiveis"])} semana(s) '
                              'com consultas no banco · dado do próprio Search Console (gsc_semanal.py)')


def salvar(res, saida):
    saida = Path(saida)
    R.salvar_texto(saida / 'relatorio.html', html(res))
    R.salvar_json(saida / 'relatorio.json', res)
    R.salvar_csv(saida / 'serie.csv', ['inicio', 'fim', *CAMPOS_RESUMO],
                 [[r['inicio'], r['fim'], *[r[c] for c in CAMPOS_RESUMO]] for r in res['serie']])
    R.salvar_csv(saida / 'pauta.csv', ['consulta', 'impressoes', 'melhor_posicao', 'paginas_hoje'],
                 [[p['consulta'], p['impressoes'], p['melhor_posicao'], p['paginas_hoje']] for p in res['pauta']])
    R.salvar_csv(saida / 'melhorar.csv', ['consulta', 'impressoes', 'melhor_posicao', 'paginas_hoje'],
                 [[p['consulta'], p['impressoes'], p['melhor_posicao'], p['paginas_hoje']] for p in res['melhorar']])
    R.salvar_csv(saida / 'paginas_sem_clique.csv', ['pagina', 'impressoes', 'posicao_media', 'consultas'],
                 [[p['pagina'], p['impressoes'], p['posicao_media'], p['consultas']]
                  for p in res['paginas_sem_clique']])
    return saida


# ---------------------------------------------------------------- modo API (opcional, não testado ao vivo)
def puxar(args):  # pragma: no cover - depende de credencial do Google
    """Roda o mesmo fluxo do gsc_semanal.py e importa a pasta gerada. Exige o script e o gcloud configurados.

    Mantido como chamada ao script original para não duplicar a autenticação (Application Default
    Credentials do gcloud, variáveis GSC_SITES, GSC_MARCA, GSC_QUOTA_PROJ — ver o cabeçalho de lá).
    """
    import subprocess
    script = Path(args.script).expanduser()
    if not script.exists():
        raise SystemExit(f'não achei {script}; passe --script caminho/gsc_semanal.py')
    for v in ('GSC_SITES', 'GSC_MARCA', 'GSC_QUOTA_PROJ'):
        if not os.environ.get(v):
            raise SystemExit(f'defina {v} (ver o cabeçalho do gsc_semanal.py)')
    pasta = Path(args.pasta)
    subprocess.run([sys.executable, str(script), '--dias', str(args.dias), '--saida', str(pasta)], check=True,
                   timeout=600)
    with conectar(args.db) as con:
        print(importar(con, [pasta]))


def main(argv=None):
    ap = argparse.ArgumentParser(prog='gsc_historico.py', description=__doc__.split('\n\n')[0] + (
        ' Importa os CSV do gsc_semanal.py num SQLite e gera relatório HTML/JSON/CSV.'),
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog='Exemplos:' + __doc__.split('Exemplos:')[1])
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('importar', help='importa resumo.csv e <fim>_<site>_sem-marca.csv (pasta ou arquivos)')
    a.add_argument('entradas', nargs='+', help='pasta(s) ou CSV')
    a.add_argument('--db', default='dados/gsc.sqlite', help='banco SQLite (padrão: dados/gsc.sqlite)')
    r = sub.add_parser('relatorio', help='gera relatorio.html, relatorio.json e CSVs')
    r.add_argument('--site', required=True, help='nome do site como no CSV (ex.: inema.club)')
    r.add_argument('--db', default='dados/gsc.sqlite')
    r.add_argument('--saida', default='saida/gsc-historico', help='pasta de saída')
    r.add_argument('--atual', help='semana (data de fim) analisada; padrão: a mais recente')
    r.add_argument('--anterior', help='semana de comparação; padrão: a anterior à atual')
    r.add_argument('--posicao-dona', type=float, default=10.0,
                   help='melhor posição a partir da qual a consulta "não tem página dona" (padrão 10)')
    r.add_argument('--min-impr', type=int, default=5, help='impressões mínimas para listar página sem clique')
    p = sub.add_parser('puxar', help='(opcional) roda o gsc_semanal.py pela API do Google e importa; não testado')
    p.add_argument('--script', default='~/projetos/inemaseo-metodo/tools/gsc_semanal.py')
    p.add_argument('--pasta', default='dados/gsc-csv')
    p.add_argument('--dias', type=int, default=7)
    p.add_argument('--db', default='dados/gsc.sqlite')
    args = ap.parse_args(argv)
    if args.cmd == 'importar':
        con = conectar(args.db)
        c = importar(con, args.entradas)
        print(f"importado: {c['semanas']} linha(s) de resumo, {c['linhas']} linha(s) de consulta"
              + (f"; ignorados: {', '.join(c['ignorados'])}" if c['ignorados'] else '') + f' → {args.db}')
    elif args.cmd == 'relatorio':
        con = conectar(args.db)
        res = analisar(con, args.site, args.atual, args.anterior, args.posicao_dona, args.min_impr)
        out = salvar(res, args.saida)
        ult = res['serie'][-1] if res['serie'] else {}
        print(f"{res['site']} semana {res['atual']} (comparada com {res['anterior']}): "
              f"sem marca {ult.get('sem_marca_cliques', '-')} cliques / {ult.get('sem_marca_impr', '-')} impr.; "
              f"subiram {len(res['subiram'])}, caíram {len(res['cairam'])}, pauta {len(res['pauta'])}, "
              f"páginas sem clique {len(res['paginas_sem_clique'])} → {out}/relatorio.html")
    else:
        puxar(args)


if __name__ == '__main__':
    main()
