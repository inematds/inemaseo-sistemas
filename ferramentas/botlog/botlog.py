#!/usr/bin/env python3
"""botlog — quem lê o seu site: robôs de IA e buscadores no log de acesso, por finalidade, com verificação de IP.

Lê log nginx/Apache no formato "combined" (também .gz) ou JSON por linha do Cloudflare Logpush (HTTP requests).
Classifica cada acesso pelo User-Agent oficial do robô e pela FINALIDADE:
  busca     → OAI-SearchBot, Claude-SearchBot, PerplexityBot (aparecer nas respostas de busca da IA)
  usuario   → ChatGPT-User, Claude-User, Perplexity-User (alguém pediu à IA para abrir a página)
  treino    → GPTBot, ClaudeBot (coleta para treinar modelos)
  buscador  → Googlebot, Bingbot (busca clássica)
Google-Extended NÃO aparece em log: é só um token de robots.txt (usa o Googlebot para buscar).
Confere se o IP está na lista oficial publicada pela empresa (pasta listas/, com data). Fora da lista = falso robô.

Comandos:
  analisar LOG... [--sitemap ARQ_OU_URL] [--saida saida/botlog] [--rdns]
  filtrar  LOG... --saida robos.log   (LGPD: guarda só linhas de robô com IP oficial; tira IP de pessoa)

Exemplos:
  python3 botlog.py analisar ../../exemplos/botlog/entrada/MONTADO_access.log --sitemap ../../exemplos/botlog/entrada/MONTADO_sitemap.xml --saida /tmp/botlog
  python3 botlog.py filtrar /var/log/nginx/access.log --saida /tmp/so-robos.log
"""
from __future__ import annotations

import argparse
import collections
import gzip
import ipaddress
import json
import re
import socket
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _comum import relatorio as R  # noqa: E402

LISTAS = Path(__file__).resolve().parent / 'listas'
F_OPENAI = 'https://platform.openai.com/docs/bots'
F_ANTHROPIC = ('https://support.anthropic.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-'
               'how-can-site-owners-block-the-crawler')
F_PERPLEXITY = 'https://docs.perplexity.ai/guides/bots'
F_GOOGLE = 'https://developers.google.com/search/docs/crawling-indexing/verifying-googlebot'
F_BING = 'https://www.bing.com/webmasters/help/how-to-verify-bingbot-3905dc26'

# Ordem importa: o mais específico primeiro (Claude-SearchBot antes de ClaudeBot etc.).
ROBOS = [
    dict(nome='ChatGPT-User', empresa='OpenAI', finalidade='usuario', listas=['openai.com_chatgpt-user.json'],
         fonte=F_OPENAI),
    dict(nome='OAI-SearchBot', empresa='OpenAI', finalidade='busca', listas=['openai.com_searchbot.json'],
         fonte=F_OPENAI),
    dict(nome='OAI-AdsBot', empresa='OpenAI', finalidade='outro', listas=[], fonte=F_OPENAI),
    dict(nome='GPTBot', empresa='OpenAI', finalidade='treino', listas=['openai.com_gptbot.json'], fonte=F_OPENAI),
    dict(nome='Claude-SearchBot', empresa='Anthropic', finalidade='busca', listas=['claude.com_bots.json'],
         fonte=F_ANTHROPIC),
    dict(nome='Claude-User', empresa='Anthropic', finalidade='usuario', listas=['claude.com_bots.json'],
         fonte=F_ANTHROPIC),
    dict(nome='ClaudeBot', empresa='Anthropic', finalidade='treino', listas=['claude.com_bots.json'],
         fonte=F_ANTHROPIC),
    dict(nome='Perplexity-User', empresa='Perplexity', finalidade='usuario',
         listas=['www.perplexity.com_perplexity-user.json'], fonte=F_PERPLEXITY),
    dict(nome='PerplexityBot', empresa='Perplexity', finalidade='busca',
         listas=['www.perplexity.com_perplexitybot.json'], fonte=F_PERPLEXITY),
    dict(nome='Googlebot', empresa='Google', finalidade='buscador', listas=['developers.google.com_googlebot.json'],
         rdns=['googlebot.com', 'google.com', 'googleusercontent.com'], fonte=F_GOOGLE),
    # Sufixo search.msn.com: conhecido, mas a página do Bing só abre com JavaScript; não reconferido [a confirmar].
    dict(nome='bingbot', empresa='Microsoft', finalidade='buscador', listas=['www.bing.com_bingbot.json'],
         rdns=['search.msn.com'], fonte=F_BING),
]
for _r in ROBOS:
    _r['rx'] = re.compile(r'(?<![\w-])' + re.escape(_r['nome']) + r'(?![\w-])', re.I)
GENERICO = re.compile(r'bot\b|crawler|spider|crawl', re.I)
FINALIDADES = {'busca': 'Busca de IA (citação)', 'usuario': 'Ação do usuário na IA', 'treino': 'Treinamento',
               'buscador': 'Buscador clássico', 'outro': 'Outro (anúncios etc.)',
               'desconhecido': 'Robô fora do catálogo'}
ASSET = re.compile(r'\.(css|js|mjs|map|png|jpe?g|gif|webp|avif|svg|ico|woff2?|ttf|eot|mp4|webm|mp3|pdf|zip|json|xml|txt)$',
                   re.I)

COMBINED = re.compile(r'^(?P<ip>\S+) \S+ \S+ \[(?P<ts>[^\]]+)\] "(?P<req>[^"]*)" (?P<status>\d{3}) \S+'
                      r'(?: "(?P<ref>[^"]*)" "(?P<ua>[^"]*)")?')


# ---------------------------------------------------------------- leitura do log
def abrir(caminho):
    p = Path(caminho)
    if p.suffix == '.gz':
        return gzip.open(p, 'rt', encoding='utf-8', errors='replace')
    return open(p, encoding='utf-8', errors='replace')


def ler_linha(linha: str):
    """Devolve dict(ip, ts, metodo, caminho, status, ua) ou None. Aceita combined e JSON do Cloudflare."""
    linha = linha.strip()
    if not linha:
        return None
    if linha.startswith('{'):
        try:
            j = json.loads(linha)
        except ValueError:
            return None
        # Campos do dataset HTTP requests do Cloudflare Logpush:
        # https://developers.cloudflare.com/logs/logpush/logpush-job/datasets/zone/http_requests/
        if 'ClientIP' not in j:
            return None
        uri = j.get('ClientRequestURI') or j.get('ClientRequestPath') or '/'
        return {'ip': j['ClientIP'], 'ts': str(j.get('EdgeStartTimestamp', '')), 'metodo': j.get('ClientRequestMethod', ''),
                'caminho': urllib.parse.urlsplit(uri).path or '/', 'status': int(j.get('EdgeResponseStatus') or 0),
                'ua': j.get('ClientRequestUserAgent') or ''}
    m = COMBINED.match(linha)
    if not m:
        return None
    partes = m['req'].split()
    alvo = partes[1] if len(partes) >= 2 else '/'
    return {'ip': m['ip'], 'ts': m['ts'], 'metodo': partes[0] if partes else '',
            'caminho': urllib.parse.urlsplit(alvo).path or '/', 'status': int(m['status']), 'ua': m['ua'] or ''}


# ---------------------------------------------------------------- listas oficiais e verificação
@lru_cache(maxsize=None)
def rede_da_lista(arquivo):
    d = json.loads((LISTAS / arquivo).read_text())
    redes = []
    for p in d.get('prefixes', []):
        v = p.get('ipv4Prefix') or p.get('ipv6Prefix')
        if v:
            redes.append(ipaddress.ip_network(v, strict=False))
    return tuple(redes)


def ip_na_lista(ip, arquivos) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(a in n for arq in arquivos for n in rede_da_lista(arq) if a.version == n.version)


@lru_cache(maxsize=4096)
def rdns_confirma(ip, sufixos):  # pragma: no cover - usa a rede (DNS)
    """rDNS + DNS direto, como manda o Google: o nome termina no sufixo e resolve de volta para o mesmo IP."""
    try:
        nome = socket.gethostbyaddr(ip)[0].rstrip('.').lower()
        if not any(nome == s or nome.endswith('.' + s) for s in sufixos):
            return False
        return ip in socket.gethostbyname_ex(nome)[2]
    except OSError:
        return False


def identificar(ua: str):
    for r in ROBOS:
        if r['rx'].search(ua):
            return r
    return None


def verificar(robo, ip, usar_rdns=False) -> str:
    """'autentico' (IP na lista oficial ou rDNS confirmado), 'falso' (há lista e o IP não está) ou 'sem_lista'."""
    if not robo['listas'] and not robo.get('rdns'):
        return 'sem_lista'
    if robo['listas'] and ip_na_lista(ip, robo['listas']):
        return 'autentico'
    if usar_rdns and robo.get('rdns') and rdns_confirma(ip, tuple(robo['rdns'])):
        return 'autentico'
    return 'falso'


def classificar(reg, usar_rdns=False):
    r = identificar(reg['ua'])
    if r:
        return {**reg, 'robo': r['nome'], 'empresa': r['empresa'], 'finalidade': r['finalidade'],
                'verificacao': verificar(r, reg['ip'], usar_rdns)}
    if GENERICO.search(reg['ua']):
        m = re.search(r'([\w.-]*(?:bot|crawler|spider)[\w.-]*)', reg['ua'], re.I)
        return {**reg, 'robo': m.group(1) if m else 'desconhecido', 'empresa': '?', 'finalidade': 'desconhecido',
                'verificacao': 'sem_lista'}
    return None


# ---------------------------------------------------------------- páginas do site
def paginas_do_sitemap(origem, limite=20):
    """Caminhos das URLs de um sitemap (arquivo local ou URL). Segue sitemapindex até `limite` filhos."""
    def ler(o):
        o = str(o)
        if re.match(r'^https?://', o):
            req = urllib.request.Request(o, headers={'User-Agent': 'inemaseo-botlog/1.0'})
            with urllib.request.urlopen(req, timeout=30) as f:
                return f.read()
        return Path(o).read_bytes()
    raiz = ET.fromstring(ler(origem))
    ns = lambda t: t.split('}')[-1]
    locs = [e.text.strip() for e in raiz.iter() if ns(e.tag) == 'loc' and e.text]
    if ns(raiz.tag) == 'sitemapindex':
        out = set()
        for filho in locs[:limite]:
            out |= paginas_do_sitemap(filho, 0)
        return out
    return {urllib.parse.urlsplit(u).path or '/' for u in locs}


def eh_pagina(caminho):
    return not ASSET.search(caminho)


# ---------------------------------------------------------------- análise
def analisar(arquivos, sitemap=None, usar_rdns=False) -> dict:
    total, invalidas = 0, 0
    regs = []
    paginas_log = set()
    for arq in arquivos:
        with abrir(arq) as f:
            for linha in f:
                reg = ler_linha(linha)
                if not reg:
                    invalidas += bool(linha.strip())
                    continue
                total += 1
                if reg['status'] == 200 and eh_pagina(reg['caminho']):
                    paginas_log.add(reg['caminho'])
                c = classificar(reg, usar_rdns)
                if c:
                    regs.append(c)
    por_robo = collections.OrderedDict()
    for c in regs:
        p = por_robo.setdefault(c['robo'], {'robo': c['robo'], 'empresa': c['empresa'], 'finalidade': c['finalidade'],
                                            'acessos': 0, 'autenticos': 0, 'falsos': 0, 'sem_lista': 0,
                                            'paginas': set(), 'robots_txt': 0, 'erros_4xx_5xx': 0, 'ultimo': ''})
        p['acessos'] += 1
        p[{'autentico': 'autenticos', 'falso': 'falsos', 'sem_lista': 'sem_lista'}[c['verificacao']]] += 1
        if c['verificacao'] != 'falso':
            p['paginas'].add(c['caminho'])
        p['robots_txt'] += c['caminho'] == '/robots.txt'
        p['erros_4xx_5xx'] += c['status'] >= 400
        p['ultimo'] = c['ts']
    finalidade = collections.Counter(c['finalidade'] for c in regs if c['verificacao'] != 'falso')
    leitura = collections.Counter((c['robo'], c['caminho']) for c in regs if c['verificacao'] != 'falso')
    falsos = collections.OrderedDict()
    for c in regs:
        if c['verificacao'] == 'falso':
            f = falsos.setdefault((c['ip'], c['robo']), {'ip': c['ip'], 'diz_ser': c['robo'], 'acessos': 0,
                                                          'caminhos': collections.Counter(), 'ua': c['ua']})
            f['acessos'] += 1
            f['caminhos'][c['caminho']] += 1
    # "Leu" = robô do catálogo, não falso, e o servidor entregou (status < 400). 403 de CDN/WAF não conta.
    visitadas = {c['caminho'] for c in regs
                 if c['verificacao'] != 'falso' and c['finalidade'] != 'desconhecido' and c['status'] < 400}
    if sitemap:
        universo, origem = paginas_do_sitemap(sitemap), f'sitemap {sitemap}'
    else:
        universo, origem = paginas_log, 'páginas com resposta 200 no próprio log (passe --sitemap para usar o sitemap)'
    nunca = sorted(universo - visitadas)
    robos = []
    for p in por_robo.values():
        robos.append({**p, 'paginas': len(p['paginas'])})
    robos.sort(key=lambda r: (-r['acessos'], r['robo']))
    return {
        'linhas_lidas': total, 'linhas_invalidas': invalidas, 'acessos_de_robo': len(regs),
        'robos': robos, 'por_finalidade': dict(finalidade),
        'quem_leu_o_que': [{'robo': r, 'caminho': c, 'acessos': n} for (r, c), n in
                           sorted(leitura.items(), key=lambda kv: (-kv[1], kv[0]))],
        'falsos': [{**f, 'caminhos': dict(f['caminhos'].most_common(5))} for f in falsos.values()],
        'nunca_visitadas': nunca, 'origem_paginas': origem, 'total_paginas': len(universo),
        'rdns': usar_rdns, 'listas': listas_info(), 'acessos': regs,
    }


def listas_info():
    out = []
    for arq in sorted({a for r in ROBOS for a in r['listas']}):
        try:
            d = json.loads((LISTAS / arq).read_text())
            out.append({'arquivo': arq, 'creationTime': d.get('creationTime'), 'faixas': len(d.get('prefixes', []))})
        except FileNotFoundError:
            out.append({'arquivo': arq, 'creationTime': None, 'faixas': 0})
    return out


# ---------------------------------------------------------------- filtro LGPD
def filtrar(arquivos, destino) -> tuple[int, int]:
    """Copia só as linhas de robô do catálogo com IP oficial (autêntico). Linha de pessoa ou robô falso sai."""
    n, mantidas = 0, 0
    Path(destino).parent.mkdir(parents=True, exist_ok=True)
    with open(destino, 'w', encoding='utf-8') as out:
        for arq in arquivos:
            with abrir(arq) as f:
                for linha in f:
                    reg = ler_linha(linha)
                    if not reg:
                        continue
                    n += 1
                    r = identificar(reg['ua'])
                    if r and r['listas'] and ip_na_lista(reg['ip'], r['listas']):
                        out.write(linha.rstrip('\n') + '\n')
                        mantidas += 1
    return n, mantidas


# ---------------------------------------------------------------- saída
VERIF = {'autentico': ('IP OFICIAL', 'good'), 'falso': ('FALSO', 'bad'), 'sem_lista': ('SEM LISTA', 'mut')}


def html(res) -> str:
    corpo = R.numeros([(res['acessos_de_robo'], f"acessos de robô em {res['linhas_lidas']} linhas"),
                       (len(res['robos']), 'robôs diferentes'),
                       (sum(f['acessos'] for f in res['falsos']), 'acessos de falso robô'),
                       (len(res['nunca_visitadas']), f"páginas nunca visitadas (de {res['total_paginas']})")])
    fin = res['por_finalidade']
    mx = max(fin.values() or [1])
    barras = ''.join(f'<p style="margin:8px 0 2px">{R.esc(FINALIDADES[k])} — <b>{fin.get(k, 0)}</b></p>'
                     f'{R.barra(fin.get(k, 0), mx)}' for k in FINALIDADES if k in fin)
    corpo += R.bloco('Acessos por finalidade (sem os falsos)', barras or '<p class="mut">Nenhum robô no log.</p>')
    corpo += ('<p class="mut">Bloquear robô de <b>treinamento</b> não tira você da <b>busca</b> da IA; bloquear '
              'robô de busca ou de ação do usuário tira. Google-Extended não aparece em log: é só um token de '
              'robots.txt e quem busca é o próprio Googlebot.</p>')
    linhas = [[r['robo'], r['empresa'], FINALIDADES[r['finalidade']], r['acessos'], r['autenticos'], r['falsos'],
               r['sem_lista'], r['paginas'], r['robots_txt'], r['erros_4xx_5xx'], r['ultimo']] for r in res['robos']]
    corpo += R.bloco('Por robô', R.tabela(['robô', 'empresa', 'finalidade', 'acessos', 'IP oficial', 'falsos',
                                           'sem lista', 'páginas', 'robots.txt', '4xx/5xx', 'último'], linhas)
                     + '<p class="mut">4xx/5xx para robô de IA pode ser bloqueio de CDN/WAF: confira no '
                       'auditor.</p>')
    corpo += R.bloco('Quem leu o quê', R.tabela(['robô', 'caminho', 'acessos'],
                                                [[q['robo'], q['caminho'], q['acessos']] for q in res['quem_leu_o_que']],
                                                max_linhas=200))
    corpo += R.bloco('Falsos robôs (diz ser, mas o IP não é da lista oficial)', R.tabela(
        ['IP', 'diz ser', 'acessos', 'caminhos'],
        [[f['ip'], f['diz_ser'], f['acessos'], ', '.join(f['caminhos'])] for f in res['falsos']])
        if res['falsos'] else '<p class="mut">Nenhum.</p>')
    corpo += R.bloco('Páginas que nenhum robô conseguiu ler', f'<p class="mut">Universo: {R.esc(res["origem_paginas"])}. '
                     'Conta como lida só a resposta abaixo de 400 para robô do catálogo com IP não falso.</p>' + (
                         R.tabela(['caminho'], [[p] for p in res['nunca_visitadas']]) if res['nunca_visitadas']
                         else '<p class="mut">Todas foram visitadas.</p>'))
    corpo += R.bloco('Listas oficiais usadas', R.tabela(
        ['arquivo', 'publicada em', 'faixas'], [[l['arquivo'], l['creationTime'], l['faixas']] for l in res['listas']])
        + f'<p class="mut">rDNS {"ligado" if res["rdns"] else "desligado (use --rdns para Googlebot e bingbot)"}. '
          'Fontes e datas de download em listas/FONTES.md.</p>')
    return R.pagina('Quem lê o seu site — <span>robôs de IA e buscadores</span>', corpo,
                    subtitulo='Log de acesso classificado por finalidade, com IP conferido nas listas oficiais')


def salvar(res, saida):
    saida = Path(saida)
    R.salvar_texto(saida / 'relatorio.html', html(res))
    sem_linhas = {k: v for k, v in res.items() if k != 'acessos'}
    R.salvar_json(saida / 'relatorio.json', sem_linhas)
    R.salvar_csv(saida / 'robos.csv', ['robo', 'empresa', 'finalidade', 'acessos', 'autenticos', 'falsos', 'sem_lista',
                                       'paginas', 'robots_txt', 'erros_4xx_5xx', 'ultimo'],
                 [[r[k] for k in ('robo', 'empresa', 'finalidade', 'acessos', 'autenticos', 'falsos', 'sem_lista',
                                  'paginas', 'robots_txt', 'erros_4xx_5xx', 'ultimo')] for r in res['robos']])
    R.salvar_csv(saida / 'acessos.csv', ['ts', 'ip', 'robo', 'finalidade', 'verificacao', 'metodo', 'caminho', 'status'],
                 [[a['ts'], a['ip'], a['robo'], a['finalidade'], a['verificacao'], a['metodo'], a['caminho'],
                   a['status']] for a in res['acessos']])
    return saida


def main(argv=None):
    ap = argparse.ArgumentParser(prog='botlog.py', description='Classifica robôs de IA e buscadores no log de '
                                 'acesso por finalidade (busca, ação do usuário, treino, buscador) e confere o IP '
                                 'nas listas oficiais.', formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog='Exemplos:' + __doc__.split('Exemplos:')[1])
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('analisar', help='gera relatorio.html, relatorio.json, robos.csv, acessos.csv')
    a.add_argument('logs', nargs='+', help='access.log, access.log.1, *.gz ou JSON por linha do Cloudflare')
    a.add_argument('--sitemap', help='sitemap.xml (arquivo ou URL) com as páginas do site')
    a.add_argument('--saida', default='saida/botlog')
    a.add_argument('--rdns', action='store_true', help='confere Googlebot/bingbot fora da lista por DNS reverso (usa rede)')
    f = sub.add_parser('filtrar', help='LGPD: copia só as linhas de robô com IP oficial')
    f.add_argument('logs', nargs='+')
    f.add_argument('--saida', required=True, help='arquivo de saída')
    args = ap.parse_args(argv)
    if args.cmd == 'filtrar':
        n, m = filtrar(args.logs, args.saida)
        print(f'{m} de {n} linha(s) mantidas (só robôs com IP oficial) → {args.saida}')
        return
    res = analisar(args.logs, args.sitemap, args.rdns)
    out = salvar(res, args.saida)
    fin = ', '.join(f'{k} {v}' for k, v in sorted(res['por_finalidade'].items(), key=lambda kv: -kv[1]))
    print(f"{res['linhas_lidas']} linhas, {res['acessos_de_robo']} de robô ({fin or 'nenhum'}); "
          f"falsos {sum(x['acessos'] for x in res['falsos'])}; nunca visitadas {len(res['nunca_visitadas'])}/"
          f"{res['total_paginas']} → {out}/relatorio.html")


if __name__ == '__main__':
    main()
