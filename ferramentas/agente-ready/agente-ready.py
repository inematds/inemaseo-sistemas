#!/usr/bin/env python3
"""agente-ready — nota de prontidão do site para IA e agentes, com pesos públicos (pesos.json).

Evolução do webmcp-readiness (sem alterar aquele repo). Lê a home e algumas páginas do sitemap,
como um robô que não roda JavaScript. Só GET em páginas públicas; respeita robots.txt; nenhuma API.
Reaproveita o núcleo de coleta do auditor (ferramentas/auditor/inemaweb.py).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "auditor"))
sys.path.insert(0, str(AQUI.parent))
import inemaweb as W  # noqa: E402
from _comum import relatorio as R  # noqa: E402

PESOS = AQUI / "pesos.json"
UA = W.UA_PROPRIO.replace("inemaseo-auditor", "inemaseo-agente-ready")

# WebMCP — especificação do W3C WebML CG, Draft Community Group Report de 16/10/2026:
# document.modelContext.registerTool({name, description, inputSchema, execute, annotations}, {signal, exposedTo})
RX_DOC = re.compile(r"document\s*\.\s*modelContext\b")
RX_NAV = re.compile(r"navigator\s*\.\s*modelContext\b")
# registerTool chamado direto ou por alias minificado (let e=document.modelContext; e.registerTool(...))
RX_REG = re.compile(r"\??\.\s*registerTool\s*\??\.?\s*\(")
RX_NOME = re.compile(r"registerTool\s*\(\s*\{[^{}]{0,400}?\bname\s*:\s*['\"`]([\w.\-]{1,64})['\"`]", re.S)
RX_AUTOCOMPLETE = re.compile(r"e-?mail|nome|name|tel|phone|fone|celular", re.I)
RX_SOBRE = re.compile(r"/(sobre|about|quem-somos|contato|contact|acerca|contacto)(/|$|\.html)", re.I)


def carregar_pesos(caminho=PESOS):
    d = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return d


def detectar_webmcp(fontes: list[str]):
    """fontes: textos JS (inline + arquivos). → dict com doc, nav, registros, nomes."""
    todo = "\n".join(fontes)
    return {"document": bool(RX_DOC.search(todo)), "navigator": bool(RX_NAV.search(todo)),
            "registros": len(RX_REG.findall(todo)), "nomes": sorted(set(RX_NOME.findall(todo)))}


def _fracao(n, total):
    return None if not total else n / total


def _status_fracao(fr, ok=0.8, parcial=0.5):
    if fr is None:
        return "na"
    return "ok" if fr >= ok else "parcial" if fr >= parcial else "falha"


def _jsonld_tem(objs, chaves):
    for o in objs:
        if any(k in o for k in chaves):
            return True
    return False


def avaliar(inicio: str, coletor: W.Coletor, paginas: int = 4, max_scripts: int = 8, testar_cdn=True):
    base, _ = W.resolver_inicio(coletor, inicio)  # segue sem-www → www etc.
    u0 = urllib.parse.urlsplit(base)
    raiz = f"{u0.scheme}://{u0.netloc}"
    ev = {"inicio": base, "host": u0.netloc}
    res = {}

    # Robots e acesso.
    rr = coletor.get(raiz + "/robots.txt")
    robots = W.Robots(rr.texto if rr.status == 200 else "", rr.status or 0)
    ev["robots_status"] = rr.status or rr.erro
    perm = {rb["token"]: robots.pode(rb["token"], base) for rb in W.ROBOS}
    ev["robots"] = perm
    por_fim = lambda f: [rb["token"] for rb in W.ROBOS if rb["finalidade"] == f]
    busca_bloq = [t for t in por_fim("busca") if not perm[t]]
    usu_bloq = [t for t in por_fim("usuario") if not perm[t]]
    trein_bloq = [t for t in por_fim("treino") if not perm[t]]
    res["robots_busca"] = ("falha" if "Googlebot" in busca_bloq or len(busca_bloq) == len(por_fim("busca"))
                           else "parcial" if busca_bloq else "ok",
                           f"bloqueados: {', '.join(busca_bloq)}" if busca_bloq else "todos liberados na home")
    res["robots_usuario"] = ("falha" if len(usu_bloq) == len(por_fim("usuario")) else "parcial" if usu_bloq else "ok",
                             f"bloqueados: {', '.join(usu_bloq)}" if usu_bloq else "todos liberados na home")
    res["robots_treino"] = ("info", f"bloqueados: {', '.join(trein_bloq)}" if trein_bloq else "nenhum bloqueado")
    res["content_signal"] = ("info", "; ".join(robots.sinais) or "não declarado")

    # Home + páginas do sitemap.
    home = coletor.get(base)
    ev["home_status"] = home.status or home.erro
    ev["https"] = (home.final_url or base).startswith("https://")
    sm = {"urls": {}}
    for s in ([x for x in robots.sitemaps if urllib.parse.urlsplit(x).netloc == u0.netloc][:2]
              or [urllib.parse.urljoin(base, "sitemap.xml")]):
        sm["urls"].update(W.ler_sitemap(coletor, s, limite_filhos=2)["urls"])
    urls_sm = [W.normalizar(u) for u in sm["urls"] if W.no_escopo(u, base)]
    ev["sitemap_urls"] = len(urls_sm)
    lastmod = sum(1 for u, v in sm["urls"].items() if v["lastmod"] and W.no_escopo(u, base))
    res["sitemap"] = ("ok" if urls_sm else "falha", f"{len(urls_sm)} URL(s) no escopo")
    res["lastmod"] = (_status_fracao(_fracao(lastmod, len(urls_sm)), 0.8, 0.3) if urls_sm else "falha",
                      f"{lastmod} de {len(urls_sm)} com lastmod")

    lidas = []
    if home.status == 200 and home.html:
        lidas.append((W.normalizar(home.final_url or base), home))
    alvo = [u for u in urls_sm if u.rstrip("/") != W.normalizar(base).rstrip("/")]
    passo = max(1, len(alvo) // max(1, paginas))  # espalha a amostra pelo sitemap
    for u in alvo[::passo][:paginas]:
        if robots.pode(W.TOKEN_PROPRIO, u):
            r = coletor.get(u)
            if r.status == 200 and r.html:
                lidas.append((u, r))
    pags = [(u, W.Pagina(r.final_url or u, r.texto), r) for u, r in lidas]
    ev["paginas"] = [u for u, _, _ in pags]

    # CDN/WAF.
    if testar_cdn and home.status == 200:
        bloq, testados = [], 0
        for rb in [x for x in W.ROBOS if x["ua"] and x["finalidade"] in ("busca", "usuario")]:
            if not perm[rb["token"]]:
                continue
            testados += 1
            sinal = W.parece_bloqueio(coletor.get(base, ua=rb["ua"]))
            if sinal:
                bloq.append(f"{rb['token']} ({sinal})")
        res["cdn_robos"] = ("na" if not testados else "falha" if len(bloq) == testados else "parcial" if bloq else "ok",
                            f"barrados: {'; '.join(bloq)}" if bloq else f"{testados} UA(s) de robô testados, nenhum barrado")
    else:
        res["cdn_robos"] = ("na", "não testado")

    # Entidade (home).
    hp = pags[0][1] if pags else W.Pagina(base, "")
    objs_home = [o for o, e in hp.jsonld() if o]
    ent = [o for o in objs_home if W.eh_entidade(o)]
    res["entidade_id"] = ("ok" if any("@id" in o for o in ent) else "parcial" if ent else "falha",
                          f"{len(ent)} entidade(s); com @id: {sum(1 for o in ent if '@id' in o)}")
    res["sameas"] = ("ok" if any(o.get("sameAs") for o in ent) else "falha", "sameAs presente" if any(
        o.get("sameAs") for o in ent) else "sem sameAs na entidade")
    sobre = any(RX_SOBRE.search(urllib.parse.urlsplit(l).path) for l in hp.links)
    res["sobre_contato"] = ("ok" if sobre else "falha", "link encontrado" if sobre else "sem link /sobre, /about ou /contato")

    # Conteúdo extraível (média das páginas lidas).
    n = len(pags)
    com_texto = sum(1 for _, p, _ in pags if p.palavras >= 150)
    res["html_sem_js"] = (_status_fracao(_fracao(com_texto, n)),
                          f"{com_texto} de {n} página(s) com 150+ palavras no HTML entregue "
                          f"(média {round(sum(p.palavras for _, p, _ in pags) / n) if n else 0})")
    resp = sum(1 for _, p, _ in pags if p.h1 and any(len(t.split()) >= 20 for t in p.paragrafos_txt))
    res["resposta_visivel"] = (_status_fracao(_fracao(resp, n)), f"{resp} de {n} com H1 + parágrafo de 20+ palavras")
    aut = sum(1 for _, p, _ in pags if p.metas.get("author") or p.rel_author or
              _jsonld_tem([o for o, e in p.jsonld() if o], ("author", "creator")))
    res["autoria"] = (_status_fracao(_fracao(aut, n)), f"{aut} de {n} com autor (meta, rel=author ou JSON-LD)")
    dat = sum(1 for _, p, _ in pags if p.tem_time or p.metas.get("article:published_time") or
              p.metas.get("article:modified_time") or
              _jsonld_tem([o for o, e in p.jsonld() if o], ("datePublished", "dateModified")))
    res["datas"] = (_status_fracao(_fracao(dat, n)), f"{dat} de {n} com data (JSON-LD, meta article ou <time>)")

    # Descoberta.
    can = sum(1 for _, p, _ in pags if len(set(p.canonicos)) == 1 and p.canonicos[0].startswith("http"))
    res["canonico"] = (_status_fracao(_fracao(can, n)), f"{can} de {n} com um canônico absoluto")
    com_h = [(u, p) for u, p, _ in pags if p.hreflang]
    if com_h:
        selfr = sum(1 for u, p in com_h if u.rstrip("/") in {W.normalizar(h).rstrip("/") for _, h in p.hreflang}
                    or W.normalizar(p.canonicos[0] if p.canonicos else "").rstrip("/") in
                    {W.normalizar(h).rstrip("/") for _, h in p.hreflang})
        res["hreflang"] = (_status_fracao(_fracao(selfr, len(com_h))),
                           f"{len(com_h)} página(s) com hreflang; {selfr} com autorreferência")
    else:
        res["hreflang"] = ("na", "site sem hreflang nas páginas lidas")
    rl = coletor.get(urllib.parse.urljoin(base, "llms.txt"))
    tem_llms = rl.status == 200 and not rl.html and len(rl.texto.strip()) > 20
    res["llms_txt"] = ("ok" if tem_llms else "falha", f"HTTP {rl.status or rl.erro}" + (" (é HTML, não conta)" if rl.html else ""))

    # WebMCP: varredura estática dos scripts inline e de mesma origem (teto de arquivos e bytes).
    fontes = [s for _, p, _ in pags for s in p.scripts_inline]
    srcs = list(dict.fromkeys(s for _, p, _ in pags for s in p.scripts_src
                              if urllib.parse.urlsplit(s).netloc == u0.netloc))[:max_scripts]
    for s in srcs:
        r = coletor.get(s)
        if r.status == 200:
            fontes.append(r.texto)
    wm = detectar_webmcp(fontes)
    toolname = sum(1 for _, p, _ in pags for f in p.forms if f["toolname"])
    wm.update({"scripts_lidos": len(srcs), "forms_toolname": toolname})
    ev["webmcp"] = wm
    if wm["document"] and wm["registros"]:
        res["webmcp_api"] = ("ok", f"{wm['registros']} registerTool(); nomes: {', '.join(wm['nomes']) or '?'}")
    elif wm["navigator"]:
        res["webmcp_api"] = ("parcial", "só navigator.modelContext (nome antigo; a especificação de 16/10/2026 usa document.modelContext)")
    else:
        res["webmcp_api"] = ("falha", f"nenhum registerTool() em {len(srcs)} script(s) de mesma origem + inline")
    pp = home.headers.get("permissions-policy", "")
    desliga = bool(re.search(r"(^|,)\s*tools\s*=\s*\(\s*\)", pp))
    if wm["registros"] or wm["navigator"]:
        res["webmcp_politica"] = ("falha" if desliga else "ok", f"Permissions-Policy: {pp or '(ausente)'}")
    else:
        res["webmcp_politica"] = ("na", f"site sem WebMCP; Permissions-Policy: {pp or '(ausente)'}")
    res["https"] = ("ok" if ev["https"] else "falha", "HTTPS" if ev["https"] else "sem HTTPS")
    if toolname:
        res["webmcp_api"] = (res["webmcp_api"][0], res["webmcp_api"][1] +
                             f"; {toolname} form[toolname] (forma declarativa antiga, fora do texto da spec de 16/10/2026 [a confirmar])")

    # Formulários.
    campos = [c for _, p, _ in pags for f in p.forms for c in f["campos"]]
    if campos:
        rot = sum(1 for c in campos if c["rotulado"])
        res["form_label"] = (_status_fracao(rot / len(campos), 0.95, 0.6), f"{rot} de {len(campos)} campo(s) com rótulo")
        alvo_ac = [c for c in campos if c["tipo"] in ("email", "tel") or RX_AUTOCOMPLETE.search(c["name"] + c["id"])]
        if alvo_ac:
            ac = sum(1 for c in alvo_ac if c["autocomplete"])
            res["form_autocomplete"] = (_status_fracao(ac / len(alvo_ac)), f"{ac} de {len(alvo_ac)} com autocomplete")
        else:
            res["form_autocomplete"] = ("na", "sem campo de e-mail/nome/telefone")
    else:
        res["form_label"] = ("na", "sem formulário nas páginas lidas")
        res["form_autocomplete"] = ("na", "sem formulário nas páginas lidas")

    # Markdown (informativo).
    md = coletor.get(base, extra={"Accept": "text/markdown"})
    res["markdown"] = ("info", f"Content-Type devolvido: {md.tipo or md.erro or '?'}")
    ev["requisicoes"] = coletor.requisicoes
    return ev, res


def pontuar(res: dict, pesos: dict):
    fator = pesos["fator"]
    linhas, ganho, total = [], 0.0, 0.0
    cats = {}
    for c in pesos["criterios"]:
        st, det = res.get(c["id"], ("na", "não avaliado"))
        pts = None
        if c["peso"] and st in fator:
            pts = c["peso"] * fator[st]
            ganho += pts
            total += c["peso"]
            k = cats.setdefault(c["categoria"], [0.0, 0.0])
            k[0] += pts
            k[1] += c["peso"]
        linhas.append({**c, "status": st, "detalhe": det, "pontos": pts})
    nota = round(100 * ganho / total) if total else 0
    por_cat = {k: round(100 * v[0] / v[1]) for k, v in cats.items() if v[1]}
    return nota, por_cat, linhas


ROTULO = {"ok": ("OK", "ok"), "parcial": ("PARCIAL", "importante"), "falha": ("FALHA", "critico"),
          "na": ("N/A", "info"), "info": ("INFO", "info")}


def relatorio_html(ev, nota, por_cat, linhas, pesos):
    cat = pesos["categorias"]
    corpo = R.numeros([(f"{nota}/100", "nota de prontidão"), (len(ev["paginas"]), "páginas lidas"),
                       (ev["sitemap_urls"], "URLs no sitemap"), (ev["requisicoes"], "requisições")])
    corpo += R.bloco("Nota por categoria", "".join(
        f'<p><b>{R.esc(cat.get(k, k))}</b> — {v}/100</p>{R.barra(v)}' for k, v in por_cat.items()))
    falhas = [l for l in linhas if l["status"] in ("falha", "parcial") and l["peso"]]
    falhas.sort(key=lambda l: -(l["peso"] * (1 if l["status"] == "falha" else 0.5)))
    corpo += R.bloco("O que mais pesa na nota (corrigir primeiro)", R.achados_html([
        {"prioridade": "critico" if l["status"] == "falha" else "importante",
         "titulo": f"{l['titulo']} — {ROTULO[l['status']][0]} (peso {l['peso']})",
         "detalhe": f"{l['detalhe']}. Por quê: {l['por_que']}", "url": " ".join(l["fonte"])} for l in falhas]))
    corpo += R.bloco("Todos os critérios (pesos públicos em pesos.json)", R.tabela(
        ["Categoria", "Critério", "Peso", "Resultado", "Pontos", "Evidência", "Fonte"],
        [(cat.get(l["categoria"], l["categoria"]), l["titulo"], l["peso"], ROTULO.get(l["status"], (l["status"],))[0],
          "-" if l["pontos"] is None else round(l["pontos"], 1), l["detalhe"], " ".join(l["fonte"])) for l in linhas]))
    sub = (f"{R.esc(ev['inicio'])} · pesos v{R.esc(pesos['versao'])} ({R.esc(pesos['data'])}) · lido como robô que "
           "não roda JavaScript · WebMCP pela especificação do W3C WebML CG de 16/10/2026 (rascunho, não é padrão)")
    return R.pagina(f"Prontidão para agentes — <span>{R.esc(ev['host'])}</span>", corpo, sub)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="agente-ready.py",
        description="Nota de prontidão do site para IA e agentes (0–100) com pesos públicos em pesos.json: acesso "
                    "dos robôs (robots por finalidade, CDN), entidade, conteúdo extraível, descoberta, WebMCP "
                    "(document.modelContext) e formulários. Só leitura, sem API.",
        epilog="Exemplo: python3 agente-ready.py https://inema.club --saida ../../exemplos/agente-ready/inema.club")
    ap.add_argument("url", help="URL inicial (home ou pasta de um guia no github.io)")
    ap.add_argument("--paginas", type=int, default=4, help="páginas do sitemap além da home (padrão 4, teto 50)")
    ap.add_argument("--max-scripts", type=int, default=8, help="scripts de mesma origem lidos na busca por WebMCP (padrão 8)")
    ap.add_argument("--pausa", type=float, default=1.0, help="segundos entre requisições (padrão 1.0; mínimo 0.5)")
    ap.add_argument("--timeout", type=int, default=15, help="timeout por requisição (padrão 15 s)")
    ap.add_argument("--pesos", default=str(PESOS), help="arquivo de pesos (padrão: pesos.json ao lado)")
    ap.add_argument("--sem-cdn", action="store_true", help="não testa a home com User-Agent de robô de IA")
    ap.add_argument("--saida", default="saida-agente-ready", help="pasta do relatório (HTML, JSON e CSV)")
    a = ap.parse_args(argv)
    pesos = carregar_pesos(a.pesos)
    col = W.Coletor(ua=UA, pausa=max(0.5, a.pausa), timeout=a.timeout)
    ev, res = avaliar(a.url, col, paginas=min(50, max(0, a.paginas)), max_scripts=a.max_scripts, testar_cdn=not a.sem_cdn)
    nota, por_cat, linhas = pontuar(res, pesos)
    saida = Path(a.saida)
    R.salvar_texto(saida / "relatorio.html", relatorio_html(ev, nota, por_cat, linhas, pesos))
    R.salvar_json(saida / "agente-ready.json", {"nota": nota, "por_categoria": por_cat, "evidencias": ev, "criterios": linhas})
    R.salvar_csv(saida / "criterios.csv", ["id", "categoria", "peso", "status", "pontos", "detalhe"],
                 [(l["id"], l["categoria"], l["peso"], l["status"], l["pontos"], l["detalhe"]) for l in linhas])
    print(f"{ev['host']}: nota {nota}/100 ({len(ev['paginas'])} páginas, {ev['requisicoes']} requisições). "
          f"Relatório: {saida / 'relatorio.html'}")
    for l in sorted([l for l in linhas if l["status"] == "falha" and l["peso"]], key=lambda l: -l["peso"])[:4]:
        print(f"  [falha, peso {l['peso']}] {l['titulo']}: {l['detalhe']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
