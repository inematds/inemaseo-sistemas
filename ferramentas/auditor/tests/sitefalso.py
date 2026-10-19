"""Site falso para os testes: responde a partir de tests/fixtures/site, sem rede.

Também usado pelos testes do agente-ready.
"""
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
import inemaweb as W  # noqa: E402

FIX = AQUI / "fixtures" / "site"
HTML = {"content-type": "text/html; charset=utf-8"}
ROTAS = {
    "https://ex.test/": ("index.html", HTML),
    "https://ex.test/a": ("a.html", HTML),
    "https://ex.test/orfa": ("orfa.html", HTML),
    "https://ex.test/noidx": ("noidx.html", HTML),
    "https://ex.test/en/": ("en.html", HTML),
    "https://ex.test/robots.txt": ("robots.txt", {"content-type": "text/plain"}),
    "https://ex.test/sitemap.xml": ("sitemap.xml", {"content-type": "application/xml"}),
}


def buscar(url, headers, seguir, timeout, max_bytes, extra_rotas=None, bloquear_ua=("OAI-SearchBot",)):
    ua = headers.get("User-Agent", "")
    if url == "http://ex.test/":
        return W.Resposta(url=url, status=301, final_url=url, headers={"location": "https://ex.test/"})
    if url in ("https://www.ex.test/",):
        return W.Resposta(url=url, status=200, final_url=url, headers=dict(HTML), texto="<html></html>")
    if any(b in ua for b in bloquear_ua) and url == "https://ex.test/":
        return W.Resposta(url=url, status=403, final_url=url, headers=dict(HTML),
                          texto="<title>Just a moment...</title>")
    rotas = dict(ROTAS, **(extra_rotas or {}))
    if url in rotas:
        arq, hd = rotas[url]
        texto = (FIX / arq).read_text(encoding="utf-8") if arq else ""
        return W.Resposta(url=url, status=200, final_url=url, headers=dict(hd), texto=texto)
    return W.Resposta(url=url, status=404, final_url=url, headers={"content-type": "text/html"}, texto="não achei")


def coletor(**kw):
    return W.Coletor(pausa=0, buscar=lambda u, h, s, t, m: buscar(u, h, s, t, m, **kw))
