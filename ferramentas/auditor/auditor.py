#!/usr/bin/env python3
"""auditor — raio-x de SEO técnico do HTML que o servidor entrega (evolução do auditoria.sh do inemaSEO).

Crawler local educado: respeita robots.txt, limite de páginas (--max) e pausa entre requisições,
User-Agent próprio. Só GET em páginas públicas. Nenhuma API.
"""
from __future__ import annotations

import argparse
import sys
import urllib.parse
from collections import Counter, defaultdict, deque
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(AQUI.parent))
import inemaweb as W  # noqa: E402
from _comum import relatorio as R  # noqa: E402

F_CANONICO = "https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls"
F_HREFLANG = "https://developers.google.com/search/docs/specialty/international/localized-versions"
F_NOINDEX = "https://developers.google.com/search/docs/crawling-indexing/block-indexing"
F_SITEMAP = "https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap"
F_ROBOTS = "https://developers.google.com/search/docs/crawling-indexing/robots/robots_txt"
F_TITULO = "https://developers.google.com/search/docs/appearance/title-link"
F_SNIPPET = "https://developers.google.com/search/docs/appearance/snippet"
F_ALT = "https://developers.google.com/search/docs/appearance/google-images"
F_JSONLD = "https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data"
F_FAQ = "https://developers.google.com/search/updates"
F_IA = "https://developers.google.com/search/docs/appearance/ai-features"
F_LLMS = "https://ahrefs.com/blog/llmstxt-study/"
ORDEM = {"critico": 0, "importante": 1, "melhoria": 2, "info": 3}


def _achado(lista, id_, prioridade, titulo, detalhe, como, urls=(), fonte=""):
    urls = list(dict.fromkeys(urls))
    ex = "; ".join(urls[:5]) + (f" (+{len(urls) - 5})" if len(urls) > 5 else "")
    lista.append({"id": id_, "prioridade": prioridade, "titulo": titulo,
                  "detalhe": detalhe + (f" Fonte: {fonte}" if fonte else ""),
                  "como_corrigir": como, "url": ex, "urls": urls, "fonte": fonte})


def auditar(inicio: str, coletor: W.Coletor, maximo: int = 50, testar_cdn: bool = True, log=print):
    inicio = inicio if "://" in inicio else "https://" + inicio
    u0 = urllib.parse.urlsplit(inicio)
    raiz = f"{u0.scheme}://{u0.netloc}"
    base = inicio if u0.path else raiz + "/"
    host = u0.netloc
    dados = {"inicio": base, "host": host, "redirecionamentos": [], "robots": {}, "sitemap": {},
             "paginas": {}, "cdn": [], "llms_txt": None}
    achados = []

    # 1. Redirecionamentos (http→https e www↔sem www), sem seguir.
    sem_www = host[4:] if host.startswith("www.") else host
    variantes = [f"http://{host}{u0.path or '/'}"]  # caminho da URL inicial (num github.io a raiz pode não existir)
    if not host.endswith("github.io"):
        variantes += [f"https://{sem_www}/", f"https://www.{sem_www}/"]
    for v in variantes:
        r = coletor.get(v, seguir=False)
        dados["redirecionamentos"].append({"url": v, "status": r.status or r.erro,
                                           "destino": r.headers.get("location", "")})
    http = dados["redirecionamentos"][0]
    if http["status"] not in (301, 308) or not str(http["destino"]).startswith("https://"):
        _achado(achados, "http-https", "importante", "HTTP não redireciona permanente para HTTPS",
                f"http://{host}/ respondeu {http['status']} → {http['destino'] or '(sem destino)'}.",
                "Configure redirecionamento 301/308 de http:// para https:// em todo o site.", [http["url"]])
    if len(variantes) == 3:
        st = [d["status"] for d in dados["redirecionamentos"][1:]]
        if st[0] == 200 and st[1] == 200:
            _achado(achados, "www-duplicado", "importante", "Site responde com e sem www (conteúdo duplicado)",
                    "As duas versões do domínio respondem 200 sem redirecionar.",
                    "Escolha uma versão e redirecione a outra com 301.", variantes[1:], F_CANONICO)

    # Base final: se a home redireciona para outro host (ex.: sem www → www), o crawl usa o destino.
    base_final, _ = W.resolver_inicio(coletor, base)
    if base_final != base:
        dados["redirecionou_para"] = base_final
        base = base_final
        u0 = urllib.parse.urlsplit(base)
        raiz, host = f"{u0.scheme}://{u0.netloc}", u0.netloc
        dados.update({"inicio": base, "host": host})

    # 2. robots.txt e permissões por finalidade.
    rr = coletor.get(raiz + "/robots.txt")
    robots = W.Robots(rr.texto if rr.status == 200 else "", rr.status or 0)
    dados["robots"] = {"status": rr.status or rr.erro, "sitemaps": robots.sitemaps, "content_signal": robots.sinais,
                       "robos": []}
    if rr.status == 404:
        _achado(achados, "robots-ausente", "melhoria", "robots.txt não existe",
                "Sem robots.txt tudo fica liberado, mas também não há onde declarar o sitemap.",
                "Publique /robots.txt com as regras por robô e a linha Sitemap:.", [raiz + "/robots.txt"], F_ROBOTS)
    elif rr.status >= 500 or not rr.status:
        _achado(achados, "robots-erro", "critico", "robots.txt com erro de servidor",
                f"Resposta {rr.status or rr.erro}. Pela RFC 9309, erro 5xx faz o robô tratar o site como bloqueado.",
                "Corrija o servidor para devolver 200 (ou 404) em /robots.txt.", [raiz + "/robots.txt"], F_ROBOTS)
    if robots.bloqueia_tudo("*") and rr.status == 200:
        _achado(achados, "robots-tudo", "critico", "robots.txt bloqueia tudo para qualquer robô",
                "O grupo User-agent: * tem Disallow: / sem Allow que libere a home.",
                "Remova o Disallow: / do grupo * (ou libere explicitamente os robôs de busca).",
                [raiz + "/robots.txt"], F_ROBOTS)
    bloq = defaultdict(list)
    for rb in W.ROBOS:
        pode = robots.pode(rb["token"], base)
        _, grupo = robots.regras_de(rb["token"])
        dados["robots"]["robos"].append({**{k: rb[k] for k in ("token", "finalidade", "empresa", "fonte")},
                                         "pode_home": pode, "grupo": grupo})
        if not pode:
            bloq[rb["finalidade"]].append(rb["token"])
    if bloq["busca"]:
        _achado(achados, "robots-busca", "critico", "robots.txt bloqueia robô de BUSCA",
                f"Bloqueados na home: {', '.join(bloq['busca'])}. Quem bloqueia robô de busca some das respostas "
                "daquele buscador/assistente.", "Libere esses tokens (Allow: /) se quer aparecer nas respostas.",
                [raiz + "/robots.txt"], W.F_OPENAI)
    if bloq["usuario"]:
        _achado(achados, "robots-usuario", "importante", "robots.txt bloqueia agente a pedido do usuário",
                f"Bloqueados: {', '.join(bloq['usuario'])}. O assistente não consegue ler a página quando alguém pede.",
                "Libere os tokens de ação do usuário, a menos que seja uma escolha consciente.",
                [raiz + "/robots.txt"], W.F_ANTHROPIC)
    if bloq["treino"]:
        _achado(achados, "robots-treino", "info", "robots.txt bloqueia robô de treino (escolha do dono)",
                f"Bloqueados: {', '.join(bloq['treino'])}. Isso tira do treino futuro; em geral não tira da busca. "
                "Google-Extended não afeta a Busca do Google.", "Nada a corrigir se foi decisão sua.",
                [raiz + "/robots.txt"], W.F_GOOGLE)

    # 3. llms.txt (informativo).
    rl = coletor.get(urllib.parse.urljoin(base, "llms.txt"))
    dados["llms_txt"] = rl.status or rl.erro
    _achado(achados, "llms", "info", f"llms.txt: HTTP {dados['llms_txt']}",
            "Opcional. Estudo do Ahrefs (jun/2026, 137 mil domínios): 97% dos arquivos não receberam nenhuma "
            "requisição; o guia de IA do Google diz que pode ignorar.", "Não é prioridade; não venda como alavanca.",
            [], F_LLMS)

    # 4. Sitemap(s).
    candidatos = [s for s in robots.sitemaps if W.no_escopo(s, base) or urllib.parse.urlsplit(s).netloc == host]
    if not candidatos:
        candidatos = [urllib.parse.urljoin(base, "sitemap.xml")]
    sm = {"urls": {}, "arquivos": []}
    for s in candidatos[:3]:
        sub = W.ler_sitemap(coletor, s)
        sm["urls"].update(sub["urls"])
        sm["arquivos"].extend(sub["arquivos"])
    urls_sm = {W.normalizar(u): v for u, v in sm["urls"].items() if W.no_escopo(u, base)}
    com_lastmod = sum(1 for v in urls_sm.values() if v["lastmod"])
    dados["sitemap"] = {"arquivos": sm["arquivos"], "urls": len(urls_sm), "com_lastmod": com_lastmod,
                        "com_hreflang": sum(1 for v in urls_sm.values() if v["alternates"])}
    if not urls_sm:
        _achado(achados, "sitemap-ausente", "importante", "Sitemap não encontrado ou vazio",
                f"Tentado: {', '.join(candidatos[:3])}.", "Publique sitemap.xml com as URLs canônicas e declare em robots.txt.",
                candidatos[:3], F_SITEMAP)
    else:
        if com_lastmod < 0.5 * len(urls_sm):
            _achado(achados, "sitemap-lastmod", "melhoria", "Sitemap sem lastmod na maioria das URLs",
                    f"{com_lastmod} de {len(urls_sm)} URLs com <lastmod>.",
                    "Informe a data real da última mudança de conteúdo (não a data do build).", [], F_SITEMAP)
        if not any(urllib.parse.urlsplit(s).netloc == host for s in robots.sitemaps) and rr.status == 200:
            _achado(achados, "sitemap-robots", "melhoria", "Sitemap não declarado no robots.txt",
                    "Robôs que não usam o Search Console descobrem o sitemap pela linha Sitemap:.",
                    "Acrescente 'Sitemap: <url absoluta>' ao robots.txt.", [raiz + "/robots.txt"], F_SITEMAP)

    # 5. Crawl.
    fila = deque([W.normalizar(base)] + list(urls_sm))
    vistos, entrada = set(), defaultdict(set)
    paginas = dados["paginas"]
    nao_rastreadas = []
    while fila and len(paginas) < maximo:
        url = fila.popleft()
        if url in vistos:
            continue
        vistos.add(url)
        if not robots.pode(W.TOKEN_PROPRIO, url):
            nao_rastreadas.append(url)
            continue
        r = coletor.get(url)
        info = {"status": r.status or r.erro, "final": W.normalizar(r.final_url) if r.final_url else "",
                "tipo": r.tipo, "x_robots": r.headers.get("x-robots-tag", "")}
        paginas[url] = info
        if not r.html or r.status != 200:
            continue
        p = W.Pagina(r.final_url or url, r.texto)
        jl = p.jsonld()
        info.update({
            "titulo": p.titulo, "descricao": p.descricao, "h1": p.h1, "lang": p.lang,
            "canonicos": p.canonicos, "hreflang": p.hreflang, "robots_meta": p.robots_meta,
            "jsonld_erros": [e for o, e in jl if e], "jsonld_tipos": p.tipos_jsonld(),
            "entidades_sem_id": [o.get("@type") for o, e in jl if o and W.eh_entidade(o, com_site=True)
                                 and "@id" not in o],
            "imgs": p.imgs, "imgs_sem_alt": p.imgs_sem_alt, "palavras": p.palavras,
        })
        internos = set()
        for l in p.links:
            ln = W.normalizar(l.split("#")[0])
            if W.no_escopo(ln, base) and ln != url:
                internos.add(ln)
        info["links_internos"] = len(internos)
        for _, alt in p.hreflang:  # alternates entram na fila (sem contar como link de entrada)
            an = W.normalizar(alt)
            if W.no_escopo(an, base) and an not in vistos:
                fila.append(an)
        for ln in internos:
            entrada[ln].add(url)
            if ln not in vistos:
                fila.append(ln)
        log(f"  [{len(paginas):>2}/{maximo}] {r.status} {url}")
    dados["nao_rastreadas_robots"] = nao_rastreadas
    dados["fila_restante"] = len([u for u in fila if u not in vistos])

    # 6. Teste de CDN/WAF com User-Agent de robô de IA (só na home, só se robots.txt permitir ao robô).
    home = W.normalizar(base)
    if testar_cdn:
        base_st = paginas.get(home, {}).get("status")
        for rb in [x for x in W.ROBOS if x["ua"]]:
            if not robots.pode(rb["token"], home):
                dados["cdn"].append({"token": rb["token"], "status": "não testado (robots.txt proíbe)", "sinal": ""})
                continue
            r = coletor.get(home, ua=rb["ua"])
            sinal = W.parece_bloqueio(r)
            dados["cdn"].append({"token": rb["token"], "finalidade": rb["finalidade"],
                                 "status": r.status or r.erro, "sinal": sinal})
            if sinal and base_st == 200:
                pri = {"busca": "critico", "usuario": "importante"}.get(rb["finalidade"], "info")
                _achado(achados, f"cdn-{rb['token'].lower()}", pri,
                        f"CDN/WAF bloqueia {rb['token']} ({W.FINALIDADES[rb['finalidade']].split(' (')[0]})",
                        f"Com o User-Agent publicado de {rb['token']} a home respondeu: {sinal}; com o UA do auditor, 200. "
                        "Limite: o teste só vê regra por User-Agent; bloqueio por IP verificado não é testável daqui.",
                        "No painel da CDN (ex.: Cloudflare AI Crawl Control / regras de bot), libere esse robô se quer "
                        "aparecer nas respostas.", [home], "https://developers.cloudflare.com/ai-crawl-control/")

    # 7. Checagens por página.
    ok = {u: i for u, i in paginas.items() if i.get("titulo") is not None}
    quebrados = {u: i["status"] for u, i in paginas.items() if isinstance(i["status"], int) and i["status"] >= 400}
    if quebrados:
        origem = [f"{u} ({s}) ← {', '.join(sorted(entrada.get(u, []))[:2]) or 'sitemap'}" for u, s in quebrados.items()]
        _achado(achados, "quebrados", "critico" if any(s >= 500 for s in quebrados.values()) else "importante",
                f"{len(quebrados)} link(s) interno(s) quebrado(s)", "URL → status ← página que aponta. " + "; ".join(origem[:5]),
                "Corrija o link na página de origem ou redirecione (301) a URL antiga.", list(quebrados))
    sm_ruins = [u for u in urls_sm if u in paginas and (paginas[u]["status"] != 200 or
                (paginas[u]["final"] and paginas[u]["final"] != u))]
    if sm_ruins:
        _achado(achados, "sitemap-status", "importante", "Sitemap lista URL que não responde 200 direto",
                f"{len(sm_ruins)} URL(s) do sitemap com erro ou redirecionamento.",
                "O sitemap deve listar só URLs finais, canônicas e 200.", sm_ruins, F_SITEMAP)

    def lista(pred):
        return [u for u, i in ok.items() if pred(i)]

    noindex = lista(lambda i: "noindex" in (i["robots_meta"] + " " + i["x_robots"]).lower())
    noindex_sm = [u for u in noindex if u in urls_sm]
    if noindex_sm:
        _achado(achados, "noindex-sitemap", "critico", "Página com noindex está no sitemap",
                "Sinais contraditórios: o sitemap pede indexação, a página pede para não indexar.",
                "Tire a página do sitemap ou remova o noindex.", noindex_sm, F_NOINDEX)
    if set(noindex) - set(noindex_sm):
        _achado(achados, "noindex", "info", "Páginas com noindex", "Confira se é intencional.",
                "Remova o noindex das páginas que devem aparecer na busca.", sorted(set(noindex) - set(noindex_sm)), F_NOINDEX)

    sem_can = lista(lambda i: not i["canonicos"])
    if sem_can:
        _achado(achados, "canonico-ausente", "importante", "Página sem link canônico",
                f"{len(sem_can)} página(s) sem <link rel=canonical> no HTML entregue.",
                "Declare um canônico absoluto apontando para a própria URL preferida.", sem_can, F_CANONICO)
    multi = lista(lambda i: len(set(i["canonicos"])) > 1)
    if multi:
        _achado(achados, "canonico-multiplo", "critico", "Mais de um canônico na mesma página",
                "Com vários rel=canonical diferentes o Google ignora todos.", "Deixe um só canônico por página.",
                multi, F_CANONICO)
    relativo = lista(lambda i: any(c and not c.startswith(("http://", "https://")) for c in i["canonicos"]))
    if relativo:
        _achado(achados, "canonico-relativo", "melhoria", "Canônico relativo",
                "Funciona, mas o Google recomenda URL absoluta.", "Use https://dominio/caminho completo.", relativo, F_CANONICO)
    outro = []
    for u, i in ok.items():
        if len(set(i["canonicos"])) == 1 and i["canonicos"][0]:
            c = W.normalizar(urllib.parse.urljoin(u, i["canonicos"][0]))
            if c.rstrip("/") != u.rstrip("/"):
                outro.append(f"{u} → {c}")
                i["canonico_aponta"] = c
    sm_nao_can = [x for x in outro if x.split(" → ")[0] in urls_sm]
    if sm_nao_can:
        _achado(achados, "canonico-sitemap", "importante", "Sitemap lista URL cujo canônico aponta para outra",
                "O sitemap deve ter só a versão canônica.", "Troque a URL no sitemap pela canônica (ou corrija o canônico).",
                sm_nao_can, F_CANONICO)
    elif outro:
        _achado(achados, "canonico-outro", "info", "Páginas que apontam canônico para outra URL",
                "Normal em duplicadas; confira se é intencional.", "Nada a fazer se for intencional.", outro, F_CANONICO)

    # hreflang recíproco (só entre páginas rastreadas).
    sem_volta, nao_verif = [], 0
    for u, i in ok.items():
        for lang, alvo in i["hreflang"]:
            a = W.normalizar(alvo)
            if a.rstrip("/") == u.rstrip("/"):
                continue
            if a not in ok:
                nao_verif += 1
                continue
            voltas = {W.normalizar(h).rstrip("/") for _, h in ok[a]["hreflang"]}
            if u.rstrip("/") not in voltas and i.get("canonico_aponta") is None:
                sem_volta.append(f"{u} → {a} ({lang})")
    sem_self = [u for u, i in ok.items() if i["hreflang"] and i.get("canonico_aponta") is None
                and u.rstrip("/") not in {W.normalizar(h).rstrip("/") for _, h in i["hreflang"]}]
    if sem_self:
        _achado(achados, "hreflang-self", "melhoria", "hreflang sem autorreferência",
                "A lista de idiomas da página não inclui a própria página.",
                "Inclua um <link rel=alternate hreflang> para o próprio idioma.", sem_self, F_HREFLANG)
    dados["hreflang_nao_verificados"] = nao_verif
    if sem_volta:
        _achado(achados, "hreflang-reciproco", "importante", "hreflang sem link de volta",
                f"A página aponta para a versão em outro idioma, mas essa versão não aponta de volta. "
                f"({nao_verif} alternate(s) fora das páginas rastreadas: não verificados.)",
                "Cada versão precisa listar todas as outras E a si mesma.", sem_volta, F_HREFLANG)

    sem_tit = lista(lambda i: not i["titulo"])
    if sem_tit:
        _achado(achados, "titulo-ausente", "importante", "Página sem <title>", "", "Escreva um título único e descritivo.",
                sem_tit, F_TITULO)
    fora = lista(lambda i: i["titulo"] and not 15 <= len(i["titulo"]) <= 65)
    if fora:
        _achado(achados, "titulo-tamanho", "melhoria", "Título muito curto ou longo (fora de 15–65 caracteres)",
                "Faixa prática herdada do webmcp-readiness, não regra do Google (o Google corta pela largura).",
                "Deixe o assunto principal nas primeiras palavras.", [f"{u} ({len(ok[u]['titulo'])})" for u in fora], F_TITULO)
    dup_t = [t for t, n in Counter(i["titulo"] for i in ok.values() if i["titulo"]).items() if n > 1]
    if dup_t:
        _achado(achados, "titulo-duplicado", "melhoria", f"{len(dup_t)} título(s) repetido(s) em páginas diferentes",
                "Exemplos: " + " | ".join(dup_t[:3]), "Cada página com título próprio.",
                [u for u, i in ok.items() if i["titulo"] in dup_t], F_TITULO)
    sem_d = lista(lambda i: not i["descricao"])
    if sem_d:
        _achado(achados, "descricao-ausente", "melhoria", "Página sem meta description",
                "O Google pode montar o trecho sozinho, mas a descrição ajuda no clique.", "Resuma a página em 1–2 frases.",
                sem_d, F_SNIPPET)
    dup_d = [d for d, n in Counter(i["descricao"] for i in ok.values() if i["descricao"]).items() if n > 1]
    if dup_d:
        _achado(achados, "descricao-duplicada", "melhoria", f"{len(dup_d)} descrição(ões) repetida(s)",
                "Exemplo: " + dup_d[0][:120], "Escreva uma descrição específica por página.",
                [u for u, i in ok.items() if i["descricao"] in dup_d], F_SNIPPET)
    sem_h1 = lista(lambda i: not i["h1"])
    if sem_h1:
        _achado(achados, "h1-ausente", "importante", "Página sem H1 no HTML entregue",
                "Se o H1 só aparece depois do JavaScript, o robô que não roda JS não vê.",
                "Coloque um H1 com o assunto da página no HTML do servidor.", sem_h1)
    multi_h1 = lista(lambda i: len(i["h1"]) > 1)
    if multi_h1:
        _achado(achados, "h1-multiplo", "melhoria", "Mais de um H1", "Não é erro para o Google, mas confunde a hierarquia.",
                "Deixe um H1 e passe os outros para H2.", multi_h1)
    jl_err = lista(lambda i: i["jsonld_erros"])
    if jl_err:
        _achado(achados, "jsonld-invalido", "importante", "JSON-LD que não é JSON válido",
                "Bloco <script type=application/ld+json> que não abre como JSON: o robô descarta.",
                "Valide no Rich Results Test / validator.schema.org.", jl_err, F_JSONLD)
    sem_id = lista(lambda i: i["entidades_sem_id"])
    if sem_id:
        _achado(achados, "jsonld-sem-id", "melhoria", "Organization/Person/WebSite sem @id",
                "Sem @id fica difícil ligar a mesma entidade entre páginas.",
                "Dê um @id fixo (ex.: https://site/#organizacao) e repita nas páginas.", sem_id, F_JSONLD)
    sem_jl = lista(lambda i: not i["jsonld_tipos"] and not i["jsonld_erros"])
    if sem_jl:
        _achado(achados, "jsonld-ausente", "melhoria", "Página sem dados estruturados (JSON-LD)",
                "Não existe schema especial para IA; mas Organization/Person/Article/Course ajudam a entender a entidade.",
                "Acrescente JSON-LD que bata com o texto visível.", sem_jl, F_IA)
    faq = lista(lambda i: "FAQPage" in i["jsonld_tipos"])
    if faq:
        _achado(achados, "faq", "info", "FAQPage no JSON-LD",
                "O rich result de FAQ deixou de aparecer no Google em 07/05/2026. A marcação não estraga; o valor está "
                "na resposta visível.", "Mantenha as perguntas e respostas visíveis; não prometa vitrine.", faq, F_FAQ)
    alt = lista(lambda i: i["imgs_sem_alt"])
    if alt:
        _achado(achados, "alt", "melhoria", "Imagens sem atributo alt",
                f"{sum(ok[u]['imgs_sem_alt'] for u in alt)} imagem(ns) sem alt (alt=\"\" em imagem decorativa é ok).",
                "Descreva as imagens informativas; use alt=\"\" nas decorativas.", alt, F_ALT)
    # Órfãs: URL do sitemap rastreada que nenhuma das páginas rastreadas linka.
    orfas = [u for u in urls_sm if u in ok and not entrada.get(u) and u != home]
    if orfas:
        _achado(achados, "orfa", "melhoria", "Página sem link de entrada (órfã nas páginas rastreadas)",
                f"Está no sitemap, mas nenhuma das {len(ok)} páginas rastreadas aponta para ela. "
                "Crawl parcial: aumente --max para confirmar.", "Linke a página a partir de uma página relacionada ou do menu.",
                orfas)
    poucas = lista(lambda i: i["palavras"] < 80)
    if poucas:
        _achado(achados, "html-vazio", "importante", "Pouco texto no HTML entregue (< 80 palavras)",
                "Pode ser conteúdo que só aparece com JavaScript; robôs de IA em geral não rodam JS.",
                "Renderize o conteúdo principal no servidor (SSR/SSG).", [f"{u} ({ok[u]['palavras']})" for u in poucas], F_IA)

    achados.sort(key=lambda a: ORDEM.get(a["prioridade"], 9))
    dados["requisicoes"] = coletor.requisicoes
    return dados, achados


# ---------------------------------------------------------------------------
def relatorio_html(dados, achados):
    cont = Counter(a["prioridade"] for a in achados)
    ok = [i for i in dados["paginas"].values() if i.get("titulo") is not None]
    corpo = R.numeros([(len(dados["paginas"]), "páginas rastreadas"), (cont["critico"], "críticos"),
                       (cont["importante"], "importantes"), (cont["melhoria"], "melhorias"),
                       (dados["sitemap"].get("urls", 0), "URLs no sitemap"), (dados["requisicoes"], "requisições feitas")])
    corpo += R.bloco("Achados por prioridade", R.achados_html(achados))
    rob = [(r["token"], W.FINALIDADES[r["finalidade"]].split(" (")[0], r["empresa"],
            "PODE" if r["pode_home"] else "BLOQUEADO", r["grupo"]) for r in dados["robots"]["robos"]]
    corpo += R.bloco("robots.txt por finalidade (home)",
                     R.tabela(["Robô", "Finalidade", "Empresa", "Home", "Grupo usado"], rob)
                     + f"<p class='sub'>HTTP do robots.txt: {R.esc(dados['robots']['status'])}. "
                       f"Content-Signal: {R.esc(', '.join(dados['robots']['content_signal']) or 'não declarado')}.</p>")
    if dados["cdn"]:
        corpo += R.bloco("CDN/WAF com User-Agent de robô de IA",
                         R.tabela(["Robô", "Resposta", "Sinal de bloqueio"],
                                  [(c["token"], c["status"], c["sinal"] or "nenhum") for c in dados["cdn"]])
                         + "<p class='sub'>Só detecta regra por User-Agent. Bloqueio por IP verificado não é testável daqui.</p>")
    corpo += R.bloco("Redirecionamentos", R.tabela(["URL", "Status", "Destino"],
                     [(d["url"], d["status"], d["destino"]) for d in dados["redirecionamentos"]]))
    corpo += R.bloco("Páginas", R.tabela(
        ["URL", "Status", "Título (car.)", "H1", "Canônico", "hreflang", "JSON-LD", "Palavras"],
        [(u, i["status"], len(i.get("titulo") or "") if i.get("titulo") is not None else "-", len(i.get("h1", [])),
          len(i.get("canonicos", [])), len(i.get("hreflang", [])), ", ".join(sorted(set(i.get("jsonld_tipos", []))))[:60],
          i.get("palavras", "-")) for u, i in dados["paginas"].items()]))
    sub = (f"{R.esc(dados['inicio'])} · {len(ok)} páginas HTML lidas · limite honesto: crawl parcial, "
           f"{dados['fila_restante']} URL(s) na fila não visitadas, {dados.get('hreflang_nao_verificados', 0)} hreflang não verificados.")
    return R.pagina(f"Auditoria técnica — <span>{R.esc(dados['host'])}</span>", corpo, sub)


def salvar(dados, achados, saida: Path):
    R.salvar_texto(saida / "relatorio.html", relatorio_html(dados, achados))
    R.salvar_json(saida / "auditoria.json", {"dados": dados, "achados": achados})
    R.salvar_csv(saida / "achados.csv", ["prioridade", "id", "titulo", "como_corrigir", "url"],
                 [(a["prioridade"], a["id"], a["titulo"], a["como_corrigir"], u) for a in achados for u in (a["urls"] or [""])])
    R.salvar_csv(saida / "paginas.csv", ["url", "status", "titulo", "descricao", "h1", "canonicos", "hreflang", "jsonld", "palavras"],
                 [(u, i["status"], i.get("titulo", ""), i.get("descricao", ""), " | ".join(i.get("h1", [])),
                   " ".join(i.get("canonicos", [])), " ".join(f"{l}={h}" for l, h in i.get("hreflang", [])),
                   " ".join(i.get("jsonld_tipos", [])), i.get("palavras", "")) for u, i in dados["paginas"].items()])


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="auditor.py",
        description="Audita o SEO técnico do HTML que o servidor entrega: status, canônico, hreflang, noindex, "
                    "título/descrição, H1, JSON-LD, links internos e quebrados, imagens sem alt, sitemap, "
                    "robots.txt por finalidade de robô de IA e bloqueio de CDN/WAF. Só leitura, sem API.",
        epilog="Exemplo: python3 auditor.py https://inema.club --max 50 --saida ../../exemplos/auditor/inema.club")
    ap.add_argument("url", help="URL inicial (home do site ou pasta de um guia no github.io)")
    ap.add_argument("--max", type=int, default=50, help="máximo de páginas a rastrear (padrão 50)")
    ap.add_argument("--pausa", type=float, default=1.0, help="segundos entre requisições (padrão 1.0; mínimo 0.5)")
    ap.add_argument("--timeout", type=int, default=15, help="timeout por requisição em segundos (padrão 15)")
    ap.add_argument("--saida", default="saida-auditor", help="pasta do relatório (HTML, JSON e CSV)")
    ap.add_argument("--sem-cdn", action="store_true", help="não testa a home com User-Agent de robô de IA")
    ap.add_argument("-q", "--quieto", action="store_true", help="não lista cada página rastreada")
    a = ap.parse_args(argv)
    col = W.Coletor(pausa=max(0.5, a.pausa), timeout=a.timeout)
    dados, achados = auditar(a.url, col, maximo=max(1, a.max), testar_cdn=not a.sem_cdn,
                             log=(lambda *_: None) if a.quieto else print)
    saida = Path(a.saida)
    salvar(dados, achados, saida)
    c = Counter(x["prioridade"] for x in achados)
    print(f"{dados['host']}: {len(dados['paginas'])} páginas, {c['critico']} crítico(s), {c['importante']} importante(s), "
          f"{c['melhoria']} melhoria(s). Relatório: {saida / 'relatorio.html'}")
    for x in [x for x in achados if x["prioridade"] in ("critico", "importante")][:5]:
        print(f"  [{x['prioridade']}] {x['titulo']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
