#!/usr/bin/env python3
"""bing-ia — citações do seu site no Copilot/Bing (AI Performance) cruzadas com o Search Console.

O Bing Webmaster Tools tem o relatório AI Performance (prévia pública desde fev/2026): quantas vezes
páginas do seu site aparecem como fonte em respostas de IA do Copilot, dos resumos de IA do Bing e de
parceiros, e as "grounding queries" (frases que a IA usou para buscar). Não há API: só exportação CSV.
Esta ferramenta importa esses CSV num SQLite e cruza com o banco do gsc-historico:
  - páginas citadas pela IA × páginas com clique no Google;
  - grounding queries que o Google ainda não te mostra → ideias de conteúdo.

Comandos:
  importar CSV... [--tipo auto|paginas|consultas] [--colunas url=Page,citacoes=Citations,...] [--db ...]
  relatorio [--db dados/bing.sqlite] [--gsc-db dados/gsc.sqlite] [--site inema.club] [--saida ...]

Exemplos:
  python3 bing_ia.py importar ../../exemplos/bing-ia/entrada/*.csv --db /tmp/bing.sqlite
  python3 bing_ia.py relatorio --db /tmp/bing.sqlite --gsc-db /tmp/gsc.sqlite --site inema.club --saida /tmp/bing-rel
"""
from __future__ import annotations

import argparse
import csv
import datetime
import io
import re
import sqlite3
import sys
import unicodedata
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _comum import relatorio as R  # noqa: E402

# Nomes de coluna aceitos sem --colunas. A Microsoft NÃO documenta as colunas do export (busca em 19/10/2026
# no anúncio oficial do AI Performance); estes apelidos são palpite [a confirmar] com um export real.
APELIDOS = {
    'url': ['url', 'page', 'pages', 'page url', 'cited page', 'cited url', 'pagina', 'página', 'endereço'],
    'citacoes': ['citations', 'citation', 'total citations', 'citation count', 'citations count', 'citacoes',
                 'citações', 'count'],
    'consulta': ['grounding query', 'grounding queries', 'query', 'queries', 'keyword', 'phrase', 'consulta'],
    'data': ['date', 'day', 'data', 'dia'],
}
ESQUEMA = """
CREATE TABLE IF NOT EXISTS paginas (arquivo TEXT, data TEXT, url TEXT, url_norm TEXT, citacoes INTEGER,
  PRIMARY KEY (arquivo, data, url));
CREATE TABLE IF NOT EXISTS consultas (arquivo TEXT, data TEXT, consulta TEXT, consulta_norm TEXT,
  citacoes INTEGER, PRIMARY KEY (arquivo, data, consulta));
"""


def conectar(db) -> sqlite3.Connection:
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.executescript(ESQUEMA)
    return con


def norm_url(u: str) -> str:
    """https://www.Site.com/a/?x#y → site.com/a  (sem esquema, sem www, sem / final, sem query/fragmento)."""
    u = (u or '').strip()
    if not re.match(r'^[a-z][a-z0-9+.-]*://', u, re.I):
        u = 'https://' + u
    p = urllib.parse.urlsplit(u)
    host = (p.hostname or '').lower()
    host = host[4:] if host.startswith('www.') else host
    path = p.path.rstrip('/')
    return host + path


def norm_txt(t: str) -> str:
    t = unicodedata.normalize('NFKD', (t or '').lower())
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', t)).strip()


def _chave(c):
    return norm_txt(c).replace('_', ' ')


def mapear_colunas(cabecalho, colunas_arg=None) -> dict:
    """Devolve {campo: nome real da coluna}. --colunas tem prioridade; senão, tenta os apelidos."""
    reais = {_chave(c): c for c in cabecalho}
    out = {}
    if colunas_arg:
        for par in colunas_arg.split(','):
            k, _, v = par.partition('=')
            k, v = k.strip(), v.strip()
            if k not in APELIDOS:
                raise SystemExit(f'--colunas: campo desconhecido {k!r} (use {", ".join(APELIDOS)})')
            if _chave(v) not in reais:
                raise SystemExit(f'--colunas: coluna {v!r} não está no CSV ({", ".join(cabecalho)})')
            out[k] = reais[_chave(v)]
    for campo, nomes in APELIDOS.items():
        if campo in out:
            continue
        for n in nomes:
            if _chave(n) in reais:
                out[campo] = reais[_chave(n)]
                break
    return out


def ler_csv(caminho):
    texto = Path(caminho).read_text(encoding='utf-8-sig', errors='replace')
    try:
        dialeto = csv.Sniffer().sniff(texto[:4096], delimiters=',;\t')
    except csv.Error:
        dialeto = csv.excel
    rd = csv.DictReader(io.StringIO(texto), dialect=dialeto)
    return rd.fieldnames or [], list(rd)


def _int(v):
    v = str(v or '0').strip().replace(' ', '').replace(' ', '')
    v = v.replace('.', '').replace(',', '') if re.fullmatch(r'\d{1,3}([.,]\d{3})+', v) else v
    try:
        return int(float(v))
    except ValueError:
        return 0


def _data(v):
    v = (v or '').strip()
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%Y/%m/%d'):
        try:
            return datetime.datetime.strptime(v[:10], fmt).date().isoformat()
        except ValueError:
            pass
    return v or '-'


def importar(con, arquivos, tipo='auto', colunas=None) -> list[dict]:
    """Importa um ou mais CSV. Reimportar o mesmo arquivo substitui as linhas dele (chave = nome do arquivo)."""
    relato = []
    for arq in arquivos:
        cab, linhas = ler_csv(arq)
        m = mapear_colunas(cab, colunas)
        t = tipo
        if t == 'auto':
            t = 'paginas' if 'url' in m else 'consultas' if 'consulta' in m else None
        if t is None or 'citacoes' not in m or (t == 'paginas' and 'url' not in m) or (
                t == 'consultas' and 'consulta' not in m):
            raise SystemExit(f'{arq}: não reconheci as colunas {cab}. Diga quais são com '
                             '--colunas url=<coluna>,citacoes=<coluna> (ou consulta=<coluna>), e --tipo.')
        nome = Path(arq).name
        tabela = 'paginas' if t == 'paginas' else 'consultas'
        con.execute(f'DELETE FROM {tabela} WHERE arquivo=?', [nome])
        n = 0
        for r in linhas:
            d = _data(r.get(m['data'])) if 'data' in m else '-'
            cit = _int(r.get(m['citacoes']))
            if t == 'paginas':
                u = (r.get(m['url']) or '').strip()
                if not u:
                    continue
                con.execute('INSERT OR REPLACE INTO paginas VALUES (?,?,?,?,?)', [nome, d, u, norm_url(u), cit])
            else:
                q = (r.get(m['consulta']) or '').strip()
                if not q:
                    continue
                con.execute('INSERT OR REPLACE INTO consultas VALUES (?,?,?,?,?)', [nome, d, q, norm_txt(q), cit])
            n += 1
        relato.append({'arquivo': nome, 'tipo': t, 'linhas': n, 'colunas': m})
    con.commit()
    return relato


# ---------------------------------------------------------------- cruzamento com o gsc-historico
def gsc_paginas(gsc_db, site=None):
    """{url_norm: {cliques, impressoes}} somando todas as semanas do banco do gsc-historico."""
    if not gsc_db or not Path(gsc_db).exists():
        return None
    con = sqlite3.connect(gsc_db)
    sql, par = 'SELECT page, SUM(clicks), SUM(impressions) FROM linhas', []
    if site:
        sql, par = sql + ' WHERE site=?', [site]
    out = {}
    for page, c, i in con.execute(sql + ' GROUP BY page', par):
        k = norm_url(page)
        o = out.setdefault(k, {'url': page, 'cliques': 0, 'impressoes': 0})
        o['cliques'] += c
        o['impressoes'] += i
    return out


def gsc_consultas(gsc_db, site=None):
    if not gsc_db or not Path(gsc_db).exists():
        return None
    con = sqlite3.connect(gsc_db)
    sql, par = 'SELECT query, SUM(clicks), SUM(impressions), MIN(position) FROM linhas', []
    if site:
        sql, par = sql + ' WHERE site=?', [site]
    out = {}
    for q, c, i, p in con.execute(sql + ' GROUP BY query', par):
        k = norm_txt(q)
        o = out.setdefault(k, {'consulta': q, 'cliques': 0, 'impressoes': 0, 'melhor_posicao': p})
        o['cliques'] += c
        o['impressoes'] += i
        o['melhor_posicao'] = min(o['melhor_posicao'], p)
    return out


def analisar(con, gsc_db=None, site=None) -> dict:
    pags = {}
    for url, un, cit in con.execute('SELECT MIN(url), url_norm, SUM(citacoes) FROM paginas GROUP BY url_norm'):
        host = un.split('/')[0]
        if site and not (host == site or host.endswith('.' + site)):
            continue
        pags[un] = {'url': url, 'citacoes': cit}
    cons = [{'consulta': q, 'citacoes': c, 'norm': n} for q, n, c in con.execute(
        'SELECT MIN(consulta), consulta_norm, SUM(citacoes) FROM consultas GROUP BY consulta_norm '
        'ORDER BY SUM(citacoes) DESC, consulta_norm')]
    dias = [r[0] for r in con.execute(
        "SELECT DISTINCT data FROM paginas WHERE data<>'-' UNION SELECT DISTINCT data FROM consultas "
        "WHERE data<>'-' ORDER BY 1")]
    gp, gq = gsc_paginas(gsc_db, site), gsc_consultas(gsc_db, site)
    res = {'site': site, 'periodo': [dias[0], dias[-1]] if dias else None, 'tem_gsc': gp is not None,
           'total_citacoes': sum(p['citacoes'] for p in pags.values()),
           'paginas_citadas': len(pags), 'consultas_grounding': len(cons)}
    citadas = sorted(pags.items(), key=lambda kv: (-kv[1]['citacoes'], kv[0]))
    if gp is None:
        res['citadas'] = [{'url': p['url'], 'citacoes': p['citacoes']} for _, p in citadas]
        res['ideias'] = [{'consulta': c['consulta'], 'citacoes': c['citacoes']} for c in cons]
        return res
    res['citadas_com_clique'], res['citadas_sem_clique'] = [], []
    for k, p in citadas:
        g = gp.get(k, {'cliques': 0, 'impressoes': 0})
        item = {'url': p['url'], 'citacoes': p['citacoes'], 'cliques_google': g['cliques'],
                'impressoes_google': g['impressoes']}
        (res['citadas_com_clique'] if g['cliques'] > 0 else res['citadas_sem_clique']).append(item)
    res['clique_sem_citacao'] = sorted(
        [{'url': g['url'], 'cliques_google': g['cliques'], 'impressoes_google': g['impressoes']}
         for k, g in gp.items() if g['cliques'] > 0 and k not in pags],
        key=lambda r: (-r['cliques_google'], r['url']))
    res['ideias'], res['ja_no_google'] = [], []
    for c in cons:
        g = gq.get(c['norm'])
        if g:
            res['ja_no_google'].append({'consulta': c['consulta'], 'citacoes': c['citacoes'],
                                        'impressoes_google': g['impressoes'], 'cliques_google': g['cliques'],
                                        'melhor_posicao': g['melhor_posicao']})
        else:
            res['ideias'].append({'consulta': c['consulta'], 'citacoes': c['citacoes']})
    return res


# ---------------------------------------------------------------- saída
def html(res) -> str:
    per = f"{res['periodo'][0]} a {res['periodo'][1]}" if res['periodo'] else 'período não informado no CSV'
    corpo = R.numeros([(res['total_citacoes'], 'citações em respostas de IA'),
                       (res['paginas_citadas'], 'páginas citadas'),
                       (res['consultas_grounding'], 'grounding queries'),
                       (len(res['ideias']), 'ideias de conteúdo')])
    corpo += ('<p class="mut">Fonte: Bing Webmaster Tools → AI Performance (Copilot, resumos de IA do Bing e '
              'parceiros). O próprio Bing avisa que as grounding queries são amostra e que não há clique. '
              'Citação não é ranking nem autoridade.</p>')
    if not res['tem_gsc']:
        corpo += ('<div class="card achado warn"><span class="tag warn">SEM GOOGLE</span><p>Sem banco do '
                  'gsc-historico (--gsc-db): o cruzamento com cliques do Google ficou de fora.</p></div>')
        corpo += R.bloco('Páginas citadas pela IA', R.tabela(['página', 'citações'],
                                                             [[p['url'], p['citacoes']] for p in res['citadas']]))
        corpo += R.bloco('Grounding queries (ideias de conteúdo)',
                         R.tabela(['consulta', 'citações'], [[c['consulta'], c['citacoes']] for c in res['ideias']]))
    else:
        cab = ['página', 'citações IA', 'cliques Google', 'impressões Google']
        lin = lambda ls: [[p['url'], p['citacoes'], p['cliques_google'], p['impressoes_google']] for p in ls]
        mx = max([p['citacoes'] for p in res['citadas_com_clique'] + res['citadas_sem_clique']] or [1])
        barras = ''.join(f'<p style="margin:6px 0 2px"><code>{R.esc(p["url"])}</code> — {p["citacoes"]}</p>'
                         f'{R.barra(p["citacoes"], mx)}'
                         for p in (res['citadas_com_clique'] + res['citadas_sem_clique'])[:10])
        corpo += R.bloco('As 10 páginas mais citadas', barras or '<p class="mut">Nenhuma.</p>')
        corpo += R.bloco('Citadas pela IA e com clique no Google', '<p class="mut">Funcionam nos dois. Mantenha '
                         'atualizadas.</p>' + R.tabela(cab, lin(res['citadas_com_clique'])))
        corpo += R.bloco('Citadas pela IA, sem clique no Google', '<p class="mut">A IA confia nelas, o Google '
                         'não manda gente. Olhe título, descrição e consulta-alvo no gsc-historico.</p>'
                         + R.tabela(cab, lin(res['citadas_sem_clique'])))
        corpo += R.bloco('Com clique no Google, nunca citadas pela IA', '<p class="mut">Candidatas a GEO: '
                         'resposta direta no topo, autoria, data, dados estruturados coerentes com o texto.</p>'
                         + R.tabela(['página', 'cliques Google', 'impressões Google'],
                                    [[p['url'], p['cliques_google'], p['impressoes_google']]
                                     for p in res['clique_sem_citacao']]))
        corpo += R.bloco('Ideias de conteúdo: a IA busca, o Google ainda não te mostra', (
            '<p class="mut">Grounding queries que não aparecem (texto igual, sem acento e sem pontuação) em '
            'nenhuma semana do gsc-historico.</p>') + R.tabela(['grounding query', 'citações'],
                                                             [[c['consulta'], c['citacoes']] for c in res['ideias']]))
        corpo += R.bloco('Grounding queries que já aparecem no Google', R.tabela(
            ['consulta', 'citações IA', 'impressões Google', 'cliques Google', 'melhor posição'],
            [[c['consulta'], c['citacoes'], c['impressoes_google'], c['cliques_google'], c['melhor_posicao']]
             for c in res['ja_no_google']]))
    alvo = R.esc(res['site'] or 'todos os sites')
    return R.pagina(f'IA do Bing × Google — <span>{alvo}</span>', corpo,
                    subtitulo=f'Citações em respostas de IA ({R.esc(per)}) cruzadas com o Search Console')


def salvar(res, saida):
    saida = Path(saida)
    R.salvar_texto(saida / 'relatorio.html', html(res))
    R.salvar_json(saida / 'relatorio.json', res)
    R.salvar_csv(saida / 'ideias.csv', ['consulta', 'citacoes'], [[c['consulta'], c['citacoes']] for c in res['ideias']])
    if res['tem_gsc']:
        todas = [('com_clique', p) for p in res['citadas_com_clique']] + [
            ('sem_clique', p) for p in res['citadas_sem_clique']]
        R.salvar_csv(saida / 'paginas.csv', ['grupo', 'url', 'citacoes', 'cliques_google', 'impressoes_google'],
                     [[g, p['url'], p['citacoes'], p['cliques_google'], p['impressoes_google']] for g, p in todas])
    return saida


def main(argv=None):
    ap = argparse.ArgumentParser(prog='bing_ia.py', description='Importa o CSV do Bing Webmaster AI Performance '
                                 '(citações no Copilot/Bing) e cruza com o banco do gsc-historico.',
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog='Exemplos:' + __doc__.split('Exemplos:')[1])
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('importar', help='importa CSV exportado do AI Performance (páginas ou grounding queries)')
    a.add_argument('arquivos', nargs='+')
    a.add_argument('--tipo', choices=['auto', 'paginas', 'consultas'], default='auto')
    a.add_argument('--colunas', help='mapa campo=coluna, campos: url, citacoes, consulta, data. '
                                     'Ex.: --colunas "url=Page,citacoes=Citations,data=Date"')
    a.add_argument('--db', default='dados/bing.sqlite')
    r = sub.add_parser('relatorio', help='gera relatorio.html, relatorio.json, ideias.csv, paginas.csv')
    r.add_argument('--db', default='dados/bing.sqlite')
    r.add_argument('--gsc-db', default='dados/gsc.sqlite', help='banco do gsc-historico (se não existir, pula o cruzamento)')
    r.add_argument('--site', help='filtra por site (ex.: inema.club; aceita subdomínios)')
    r.add_argument('--saida', default='saida/bing-ia')
    args = ap.parse_args(argv)
    con = conectar(args.db)
    if args.cmd == 'importar':
        for x in importar(con, args.arquivos, args.tipo, args.colunas):
            print(f"{x['arquivo']}: {x['linhas']} linha(s) de {x['tipo']} (colunas {x['colunas']}) → {args.db}")
    else:
        res = analisar(con, args.gsc_db, args.site)
        out = salvar(res, args.saida)
        extra = (f", citadas sem clique no Google {len(res['citadas_sem_clique'])}, clique sem citação "
                 f"{len(res['clique_sem_citacao'])}" if res['tem_gsc'] else ' (sem banco do Google)')
        print(f"{res['total_citacoes']} citações em {res['paginas_citadas']} página(s), "
              f"{res['consultas_grounding']} grounding queries, {len(res['ideias'])} ideia(s){extra} "
              f"→ {out}/relatorio.html")


if __name__ == '__main__':
    main()
