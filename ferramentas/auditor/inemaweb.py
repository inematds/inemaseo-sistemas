"""inemaweb.py — núcleo de coleta do auditor (também usado pelo agente-ready).

Só biblioteca padrão:
- Coletor: GET educado (User-Agent próprio, pausa entre requisições, timeout, teto de bytes, só leitura).
- Robots: leitor de robots.txt no formato RFC 9309 / Google (grupos por produto, '*' de reserva,
  curingas '*' e '$', regra mais longa vence, empate = allow).
- Pagina: extrator do HTML entregue pelo servidor (o que o robô vê sem rodar JS).
- ROBOS: robôs de busca, de ação do usuário e de treino, com a fonte oficial de cada um.
- ler_sitemap: sitemap.xml e sitemapindex (com .gz), <lastmod> e alternates hreflang.
"""
from __future__ import annotations

import gzip
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html.parser import HTMLParser

VERSAO = "1.0.0"
UA_PROPRIO = f"inemaseo-auditor/{VERSAO} (+https://github.com/inematds/inemaseo-sistemas)"
TOKEN_PROPRIO = "inemaseo-auditor"

# ---------------------------------------------------------------------------
# Robôs por finalidade. "ua" só nos que têm string publicada (usada no teste de CDN/WAF).
# ---------------------------------------------------------------------------
F_OPENAI = "https://platform.openai.com/docs/bots"
F_ANTHROPIC = "https://support.anthropic.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how"
F_PERPLEXITY = "https://docs.perplexity.ai/guides/bots"
F_GOOGLE = "https://developers.google.com/search/docs/crawling-indexing/google-common-crawlers"
F_BING = "https://www.bing.com/webmasters/help/which-crawlers-does-bing-use-8c184ec0"

ROBOS = [
    {"token": "Googlebot", "finalidade": "busca", "empresa": "Google", "fonte": F_GOOGLE, "ua": None},
    {"token": "Bingbot", "finalidade": "busca", "empresa": "Microsoft", "fonte": F_BING, "ua": None},
    {"token": "OAI-SearchBot", "finalidade": "busca", "empresa": "OpenAI", "fonte": F_OPENAI,
     "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/131.0.0.0 Safari/537.36; compatible; OAI-SearchBot/1.4; +https://openai.com/searchbot"},
    {"token": "Claude-SearchBot", "finalidade": "busca", "empresa": "Anthropic", "fonte": F_ANTHROPIC, "ua": None},
    {"token": "PerplexityBot", "finalidade": "busca", "empresa": "Perplexity", "fonte": F_PERPLEXITY,
     "ua": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; "
           "+https://perplexity.ai/perplexitybot)"},
    {"token": "ChatGPT-User", "finalidade": "usuario", "empresa": "OpenAI", "fonte": F_OPENAI, "ua": None},
    {"token": "Claude-User", "finalidade": "usuario", "empresa": "Anthropic", "fonte": F_ANTHROPIC, "ua": None},
    {"token": "Perplexity-User", "finalidade": "usuario", "empresa": "Perplexity", "fonte": F_PERPLEXITY,
     "ua": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Perplexity-User/1.0; "
           "+https://perplexity.ai/perplexity-user)"},
    # Versão "1.3" do GPTBot: [a confirmar] — o formato segue o exemplo do OAI-SearchBot na mesma página.
    {"token": "GPTBot", "finalidade": "treino", "empresa": "OpenAI", "fonte": F_OPENAI,
     "ua": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.3; +https://openai.com/gptbot"},
    {"token": "ClaudeBot", "finalidade": "treino", "empresa": "Anthropic", "fonte": F_ANTHROPIC, "ua": None},
    # Google-Extended é só token de robots.txt (não há robô com esse User-Agent); não afeta a Busca.
    {"token": "Google-Extended", "finalidade": "treino", "empresa": "Google", "fonte": F_GOOGLE, "ua": None},
]
FINALIDADES = {
    "busca": "Busca e citação (bloquear = some das respostas)",
    "usuario": "Ação a pedido do usuário (bloquear = o agente não lê a página quando alguém pede)",
    "treino": "Treino de modelo (bloquear = fora do treino futuro; em geral não tira da busca)",
}


# ---------------------------------------------------------------------------
# Coletor HTTP
# ---------------------------------------------------------------------------
@dataclass
class Resposta:
    url: str
    status: int = 0
    final_url: str = ""
    headers: dict = field(default_factory=dict)
    texto: str = ""
    erro: str = ""
    redirecionou: bool = False

    @property
    def tipo(self) -> str:
        return self.headers.get("content-type", "").split(";")[0].strip().lower()

    @property
    def html(self) -> bool:
        return self.tipo in ("text/html", "application/xhtml+xml")


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _baixar(url, headers, seguir, timeout, max_bytes) -> Resposta:
    req = urllib.request.Request(url, headers=headers, method="GET")
    abridor = urllib.request.build_opener() if seguir else urllib.request.build_opener(_SemRedirecionar)
    try:
        with abridor.open(req, timeout=timeout) as r:
            corpo = r.read(max_bytes)
            st, fin, hd = r.status, r.geturl(), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as ex:
        corpo = ex.read(max_bytes) if ex.fp else b""
        st, fin, hd = ex.code, ex.geturl() or url, {k.lower(): v for k, v in (ex.headers or {}).items()}
    except Exception as ex:  # rede, DNS, timeout, TLS
        return Resposta(url=url, erro=f"{type(ex).__name__}: {ex}"[:200])
    if hd.get("content-encoding") == "gzip" or url.endswith(".gz") or corpo[:2] == b"\x1f\x8b":
        try:
            corpo = gzip.decompress(corpo)
        except Exception:
            pass
    m = re.search(r"charset=([\w-]+)", hd.get("content-type", ""), re.I)
    try:
        texto = corpo.decode(m.group(1) if m else "utf-8", errors="replace")
    except LookupError:
        texto = corpo.decode("utf-8", errors="replace")
    return Resposta(url=url, status=st, final_url=fin, headers=hd, texto=texto,
                    redirecionou=(fin.rstrip("/") != url.rstrip("/")))


class Coletor:
    """GET educado. `buscar` pode ser trocado nos testes (fixtures locais, sem rede)."""

    def __init__(self, ua=UA_PROPRIO, pausa=1.0, timeout=15, max_bytes=2_000_000, buscar=None):
        self.ua, self.pausa, self.timeout, self.max_bytes = ua, pausa, timeout, max_bytes
        self._buscar = buscar or _baixar
        self._ultimo = 0.0
        self.requisicoes = 0

    def get(self, url, ua=None, seguir=True, extra=None) -> Resposta:
        espera = self.pausa - (time.monotonic() - self._ultimo)
        if espera > 0 and self.requisicoes:
            time.sleep(espera)
        h = {"User-Agent": ua or self.ua, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5",
             "Accept-Encoding": "gzip"}
        h.update(extra or {})
        self.requisicoes += 1
        try:
            return self._buscar(url, h, seguir, self.timeout, self.max_bytes)
        finally:
            self._ultimo = time.monotonic()


# ---------------------------------------------------------------------------
# robots.txt (RFC 9309; https://developers.google.com/search/docs/crawling-indexing/robots/robots_txt)
# ---------------------------------------------------------------------------
class Robots:
    def __init__(self, texto: str = "", status: int = 200):
        self.status = status
        self.grupos: list[tuple[list[str], list[tuple[str, str]]]] = []
        self.sitemaps: list[str] = []
        self.sinais: list[str] = []  # linhas Content-Signal (proposta da Cloudflare) — só registro
        if 200 <= status < 300:
            self._ler(texto or "")

    def _ler(self, texto):
        agentes, regras, em_regras = [], [], False
        for bruta in texto.splitlines():
            linha = bruta.split("#", 1)[0].strip()
            if ":" not in linha:
                continue
            k, v = (p.strip() for p in linha.split(":", 1))
            k = k.lower()
            if k == "user-agent":
                if em_regras:
                    self.grupos.append((agentes, regras))
                    agentes, regras, em_regras = [], [], False
                agentes.append(v.lower())
            elif k in ("allow", "disallow"):
                if agentes:
                    em_regras = True
                    if v:
                        regras.append((k, v))
            elif k == "sitemap":
                self.sitemaps.append(v)
            elif k == "content-signal":
                self.sinais.append(v)
        if agentes:
            self.grupos.append((agentes, regras))

    def regras_de(self, token: str):
        t = token.lower()
        especificas = [r for ags, r in self.grupos if t in ags]
        if especificas:
            return [x for r in especificas for x in r], "específico"
        geral = [r for ags, r in self.grupos if "*" in ags]
        if geral:
            return [x for r in geral for x in r], "*"
        return [], "nenhum"

    @staticmethod
    def _casa(padrao: str, caminho: str) -> bool:
        ancora = padrao.endswith("$")
        p = padrao[:-1] if ancora else padrao
        rx = "".join(".*" if c == "*" else re.escape(c) for c in p)
        return re.match(rx + ("$" if ancora else ""), caminho) is not None

    def pode(self, token: str, url: str) -> bool:
        # RFC 9309 §2.3.1.3: 4xx = sem restrição; 5xx/sem resposta = tudo bloqueado.
        if 400 <= self.status < 500:
            return True
        if self.status >= 500 or self.status == 0:
            return False
        u = urllib.parse.urlsplit(url)
        caminho = (u.path or "/") + (f"?{u.query}" if u.query else "")
        if caminho == "/robots.txt":
            return True
        regras, _ = self.regras_de(token)
        melhor = None  # (comprimento, é_allow)
        for tipo, padrao in regras:
            if self._casa(padrao, caminho):
                cand = (len(padrao), tipo == "allow")
                if melhor is None or cand > melhor:
                    melhor = cand
        return True if melhor is None else melhor[1]

    def bloqueia_tudo(self, robo="*") -> bool:
        return not self.pode(robo, "https://x/") and not self.pode(robo, "https://x/qualquer-pagina")


# ---------------------------------------------------------------------------
# Extrator de HTML
# ---------------------------------------------------------------------------
_INVISIVEL = {"script", "style", "noscript", "template", "svg", "head"}
_VAZIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Pagina(HTMLParser):
    def __init__(self, url: str, html: str = ""):
        super().__init__(convert_charrefs=True)
        self.url = url
        self.lang = ""
        self.titulo = ""
        self.metas: dict[str, str] = {}
        self.canonicos: list[str] = []
        self.hreflang: list[tuple[str, str]] = []
        self.h1: list[str] = []
        self.headings: list[tuple[int, str]] = []
        self.links: list[str] = []
        self.imgs_sem_alt = 0
        self.imgs = 0
        self.jsonld_bruto: list[str] = []
        self.scripts_src: list[str] = []
        self.scripts_inline: list[str] = []
        self.forms: list[dict] = []
        self.paragrafos = 0
        self.paragrafos_txt: list[str] = []
        self.rel_author = False
        self.tem_main = False
        self.tem_time = False
        self.palavras = 0
        self._pilha: list[str] = []
        self._buf_tit = None
        self._buf_h = None
        self._buf_script = None
        self._buf_p = None
        self._script_tipo = ""
        self._labels_for: set[str] = set()
        self._label_aberto = 0
        self._form = None
        self._texto: list[str] = []
        if html:
            try:
                self.feed(html)
                self.close()
            except Exception:
                pass
        self.palavras = len(re.findall(r"\w{2,}", " ".join(self._texto)))
        self._fechar_forms()

    # -- helpers
    def _abs(self, href):
        return urllib.parse.urljoin(self.url, (href or "").strip())

    def _invisivel(self):
        return any(t in _INVISIVEL for t in self._pilha)

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "body":  # HTML5 permite omitir </head>: <body> fecha o head e o que ficou aberto nele
            self._pilha = [t for t in self._pilha if t == "html"]
        if tag not in _VAZIOS:
            self._pilha.append(tag)
        if tag == "html":
            self.lang = a.get("lang", "")
        elif tag == "title" and not self.titulo:
            self._buf_tit = []
        elif tag == "meta":
            nome = (a.get("name") or a.get("property") or a.get("http-equiv") or "").lower()
            if nome:
                self.metas.setdefault(nome, a.get("content", ""))
        elif tag == "link":
            rel = a.get("rel", "").lower().split()
            if "author" in rel:
                self.rel_author = True
            if "canonical" in rel:
                self.canonicos.append(a.get("href", ""))
            if "alternate" in rel and a.get("hreflang"):
                self.hreflang.append((a["hreflang"].lower(), self._abs(a.get("href"))))
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._buf_h = (int(tag[1]), [])
        elif tag == "a" and a.get("href"):
            self.links.append(self._abs(a["href"]))
            if "author" in a.get("rel", "").lower().split():
                self.rel_author = True
        elif tag == "img":
            self.imgs += 1
            if "alt" not in a:
                self.imgs_sem_alt += 1
        elif tag == "script":
            self._script_tipo = a.get("type", "").lower()
            if a.get("src"):
                self.scripts_src.append(self._abs(a["src"]))
            self._buf_script = []
        elif tag == "p":
            self.paragrafos += 1
            self._buf_p = []
        elif tag == "main" or a.get("role") == "main":
            self.tem_main = True
        elif tag == "time":
            self.tem_time = True
        elif tag == "form":
            self._fechar_forms()
            self._form = {"toolname": a.get("toolname", ""), "campos": [], "action": a.get("action", "")}
        elif tag == "label":
            self._label_aberto += 1
            if a.get("for"):
                self._labels_for.add(a["for"])
        if tag in ("input", "select", "textarea") and self._form is not None:
            tipo = a.get("type", "text").lower() if tag == "input" else tag
            if tipo not in ("hidden", "submit", "button", "reset", "image"):
                self._form["campos"].append({
                    "tipo": tipo, "id": a.get("id", ""), "name": a.get("name", ""),
                    "autocomplete": a.get("autocomplete", ""),
                    "rotulo_attr": bool(a.get("aria-label") or a.get("aria-labelledby") or a.get("title")),
                    "dentro_label": self._label_aberto > 0,
                })

    def handle_endtag(self, tag):
        if tag == "title" and self._buf_tit is not None:
            self.titulo = " ".join("".join(self._buf_tit).split())
            self._buf_tit = None
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6") and self._buf_h:
            nivel, buf = self._buf_h
            txt = " ".join("".join(buf).split())
            self.headings.append((nivel, txt))
            if nivel == 1:
                self.h1.append(txt)
            self._buf_h = None
        elif tag == "script" and self._buf_script is not None:
            corpo = "".join(self._buf_script)
            if self._script_tipo == "application/ld+json":
                self.jsonld_bruto.append(corpo)
            elif corpo.strip():
                self.scripts_inline.append(corpo)
            self._buf_script = None
        elif tag == "p" and self._buf_p is not None:
            self.paragrafos_txt.append(" ".join("".join(self._buf_p).split()))
            self._buf_p = None
        elif tag == "label" and self._label_aberto:
            self._label_aberto -= 1
        elif tag == "form":
            self._fechar_forms()
        if tag in self._pilha:
            while self._pilha:
                if self._pilha.pop() == tag:
                    break

    def handle_data(self, data):
        if self._buf_tit is not None:
            self._buf_tit.append(data)
        if self._buf_script is not None:
            self._buf_script.append(data)
            return
        if self._buf_h is not None:
            self._buf_h[1].append(data)
        if self._buf_p is not None:
            self._buf_p.append(data)
        if not self._invisivel():
            self._texto.append(data)

    def _fechar_forms(self):
        if self._form is not None:
            for c in self._form["campos"]:
                c["rotulado"] = c["dentro_label"] or c["rotulo_attr"] or (c["id"] and c["id"] in self._labels_for)
            self.forms.append(self._form)
            self._form = None

    # -- derivados
    @property
    def descricao(self):
        return self.metas.get("description", "").strip()

    @property
    def robots_meta(self):
        return " ".join(v for k, v in self.metas.items() if k in ("robots", "googlebot")).lower()

    def jsonld(self):
        """[(objeto_ou_None, erro)] — cada bloco; @graph é aberto."""
        out = []
        for bruto in self.jsonld_bruto:
            try:
                dado = json.loads(bruto)
            except Exception as ex:
                out.append((None, str(ex)[:120]))
                continue
            itens = dado if isinstance(dado, list) else [dado]
            for it in itens:
                if isinstance(it, dict) and "@graph" in it and isinstance(it["@graph"], list):
                    out.extend((g, "") for g in it["@graph"] if isinstance(g, dict))
                elif isinstance(it, dict):
                    out.append((it, ""))
        return out

    def tipos_jsonld(self):
        tipos = []
        for obj, _ in self.jsonld():
            if obj:
                t = obj.get("@type")
                tipos.extend(t if isinstance(t, list) else [t] if t else [])
        return [str(t) for t in tipos]


# ---------------------------------------------------------------------------
# URLs e sitemap
# ---------------------------------------------------------------------------
def eh_entidade(obj: dict, com_site=False) -> bool:
    """Organization (e subtipos: EducationalOrganization, NewsMediaOrganization…), Person, LocalBusiness."""
    t = obj.get("@type")
    tipos = [str(x) for x in (t if isinstance(t, list) else [t]) if x]
    return any(x.endswith("Organization") or x in ("Person", "LocalBusiness") or (com_site and x == "WebSite")
               for x in tipos)


def normalizar(url: str) -> str:
    u = urllib.parse.urlsplit(url)
    caminho = u.path or "/"
    return urllib.parse.urlunsplit((u.scheme.lower(), u.netloc.lower(), caminho, u.query, ""))


def resolver_inicio(coletor: "Coletor", url: str):
    """Segue o redirecionamento da URL inicial (ex.: inema.club → www.inema.club) e devolve a base final."""
    url = url if "://" in url else "https://" + url
    u = urllib.parse.urlsplit(url)
    url = url if u.path else url + "/"
    r = coletor.get(url)
    if r.final_url and r.status and r.status < 400:
        f = urllib.parse.urlsplit(r.final_url)
        if f.netloc and (f.netloc != u.netloc or f.scheme != u.scheme):
            return urllib.parse.urlunsplit((f.scheme, f.netloc, f.path or "/", "", "")), r
    return url, r


def no_escopo(url: str, base: str) -> bool:
    u, b = urllib.parse.urlsplit(url), urllib.parse.urlsplit(base)
    if u.scheme not in ("http", "https") or u.netloc.lower() != b.netloc.lower():
        return False
    prefixo = b.path if b.path.endswith("/") else b.path.rsplit("/", 1)[0] + "/"
    return (u.path or "/").startswith(prefixo) or (u.path or "/") + "/" == prefixo


def ler_sitemap(coletor: Coletor, url: str, limite_filhos=5, _prof=0):
    """→ {'urls': {loc: {'lastmod': str, 'alternates': [(lang, href)]}}, 'arquivos': [(url, status, n)]}"""
    res = {"urls": {}, "arquivos": []}
    r = coletor.get(url)
    if r.status != 200 or not r.texto.strip():
        res["arquivos"].append((url, r.status or r.erro, 0))
        return res
    try:
        raiz = ET.fromstring(r.texto.encode("utf-8"))
    except ET.ParseError:
        res["arquivos"].append((url, "XML inválido", 0))
        return res
    tag = lambda el: el.tag.rsplit("}", 1)[-1]
    if tag(raiz) == "sitemapindex":
        filhos = [el.text.strip() for el in raiz.iter() if tag(el) == "loc" and el.text]
        res["arquivos"].append((url, 200, len(filhos)))
        if _prof == 0:
            for f in filhos[:limite_filhos]:
                sub = ler_sitemap(coletor, f, limite_filhos, _prof + 1)
                res["urls"].update(sub["urls"])
                res["arquivos"].extend(sub["arquivos"])
        return res
    for el in raiz:
        if tag(el) != "url":
            continue
        loc, lastmod, alts = "", "", []
        for c in el:
            t = tag(c)
            if t == "loc" and c.text:
                loc = c.text.strip()
            elif t == "lastmod" and c.text:
                lastmod = c.text.strip()
            elif t == "link" and c.get("hreflang"):
                alts.append((c.get("hreflang").lower(), c.get("href", "")))
        if loc:
            res["urls"][loc] = {"lastmod": lastmod, "alternates": alts}
    res["arquivos"].append((url, 200, len(res["urls"])))
    return res


# Sinais de desafio/bloqueio de CDN/WAF. Marcadores [a confirmar]: vêm do comportamento conhecido das
# páginas de desafio da Cloudflare, não de uma lista oficial publicada.
_MARCAS_DESAFIO = ("just a moment", "attention required", "challenge-platform", "cf-chl", "captcha")


def parece_bloqueio(r: Resposta) -> str:
    if r.erro:
        return f"sem resposta ({r.erro[:60]})"
    if r.headers.get("cf-mitigated"):
        return f"cf-mitigated: {r.headers['cf-mitigated']}"
    corpo = r.texto[:5000].lower()
    if r.status in (403, 429, 503):
        marca = next((m for m in _MARCAS_DESAFIO if m in corpo), "")
        return f"HTTP {r.status}" + (f" + página de desafio ('{marca}')" if marca else "")
    if r.status == 200 and any(m in corpo for m in _MARCAS_DESAFIO[:3]):
        return "HTTP 200 com página de desafio"
    return ""
