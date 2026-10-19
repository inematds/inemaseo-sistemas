"""relatorio.py — código comum de saída das ferramentas inemaseo-sistemas.

Só biblioteca padrão. Gera:
- relatório HTML self-contained no padrão INEMA dark (DESIGN.md: preto #0c0c10, amarelo #FACC15,
  títulos Sora, corpo Inter, 16px; prioridade sempre com rótulo, nunca só cor);
- JSON e CSV para outra ferramenta ler.

Uso típico:
    import sys; from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from _comum import relatorio as R
    html = R.pagina("Título", R.bloco("Resumo", "<p>…</p>") + R.tabela(["a","b"], [[1,2]]))
    R.salvar_texto("saida/relatorio.html", html)

Funções aditivas: se outra ferramenta precisar de algo novo, acrescente, não altere assinatura.
"""
from __future__ import annotations

import csv
import html as _html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

# Prioridades de achado (rótulo + cor; a cor nunca vem sozinha).
PRIORIDADES = {
    "critico": ("CRÍTICO", "bad"),
    "importante": ("IMPORTANTE", "warn"),
    "melhoria": ("MELHORIA", "info"),
    "ok": ("OK", "good"),
    "info": ("INFO", "mut"),
}

CSS = """
:root{--bg:#0c0c10;--bg2:#14141b;--card:#16161e;--line:#272730;--txt:#e9e9ee;--mut:#9a9aa6;
--amb:#FACC15;--bad:#f87171;--warn:#fb923c;--info:#38bdf8;--good:#4ade80}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){--bg:#f6f7f9;--bg2:#eceef2;
--card:#ffffff;--line:#e1e3ea;--txt:#1a1a22;--mut:#5b5b68;--amb:#a16207;--bad:#b91c1c;--warn:#9a3412;
--info:#0369a1;--good:#15803d}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font:16px/1.6 Inter,system-ui,sans-serif}
main{max-width:1160px;margin:0 auto;padding:32px 16px 64px}
h1,h2,h3{font-family:Sora,Inter,system-ui,sans-serif;line-height:1.25}
h1{font-size:2rem;margin:0 0 4px}h1 span{color:var(--amb)}
h2{font-size:1.3rem;margin:36px 0 12px;border-bottom:1px solid var(--line);padding-bottom:6px}
.sub{color:var(--mut);margin:0 0 24px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:12px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.num{font-family:Sora,Inter,sans-serif;font-size:2rem;font-weight:700;color:var(--amb)}
.lbl{color:var(--mut);font-size:.875rem}
table{width:100%;border-collapse:collapse;font-size:.9rem;display:block;overflow-x:auto}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-family:Sora,Inter,sans-serif;color:var(--mut);font-weight:600}
code{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:.85em;word-break:break-all}
.tag{display:inline-block;font-family:Sora,Inter,sans-serif;font-size:.75rem;letter-spacing:.1em;
font-weight:700;padding:2px 9px;border-radius:999px;border:1px solid currentColor;white-space:nowrap}
.bad{color:var(--bad)}.warn{color:var(--warn)}.info{color:var(--info)}.good{color:var(--good)}.mut{color:var(--mut)}
.achado{border-left:4px solid var(--line)}
.achado.bad{border-left-color:var(--bad)}.achado.warn{border-left-color:var(--warn)}
.achado.info{border-left-color:var(--info)}.achado.good{border-left-color:var(--good)}
.achado h3{font-size:1rem;margin:6px 0;color:var(--txt)}.achado p{margin:4px 0;color:var(--txt)}
.fix{color:var(--mut)}.fix b{color:var(--amb)}
.barra{height:10px;background:var(--bg2);border-radius:999px;overflow:hidden;border:1px solid var(--line)}
.barra i{display:block;height:100%;background:var(--amb)}
footer{margin-top:48px;color:var(--mut);font-size:.875rem}
a{color:var(--amb)}
"""


def esc(v) -> str:
    """Escapa texto para HTML."""
    return _html.escape("" if v is None else str(v), quote=True)


def agora_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def pagina(titulo: str, corpo: str, subtitulo: str = "", rodape: str = "") -> str:
    """Documento HTML completo, self-contained (sem script, sem CDN obrigatório)."""
    fontes = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
              '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Sora:wght@600;700'
              '&display=swap" rel="stylesheet">')
    rod = rodape or f"Gerado em {esc(agora_iso())} por inemaseo-sistemas (MIT). Só leitura do HTML público."
    sub = f'<p class="sub">{subtitulo}</p>' if subtitulo else ""
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(titulo)}</title>{fontes}<style>{CSS}</style></head><body><main>'
            f'<h1>{titulo}</h1>{sub}{corpo}<footer>{rod}</footer></main></body></html>')


def bloco(titulo: str, conteudo_html: str) -> str:
    return f"<h2>{esc(titulo)}</h2>{conteudo_html}"


def numeros(itens: Sequence[tuple]) -> str:
    """Faixa de números grandes: [(valor, rótulo), ...]."""
    cel = "".join(f'<div class="card"><div class="num">{esc(v)}</div><div class="lbl">{esc(l)}</div></div>'
                  for v, l in itens)
    return f'<div class="grid">{cel}</div>'


def tag(prioridade: str) -> str:
    rot, cls = PRIORIDADES.get(prioridade, (prioridade.upper(), "mut"))
    return f'<span class="tag {cls}">{esc(rot)}</span>'


def achados_html(achados: Iterable[dict]) -> str:
    """Cada achado: {prioridade, titulo, detalhe, como_corrigir, url?}."""
    out = []
    for a in achados:
        cls = PRIORIDADES.get(a.get("prioridade", "info"), ("", "mut"))[1]
        url = f'<p><code>{esc(a["url"])}</code></p>' if a.get("url") else ""
        fix = (f'<p class="fix"><b>Como corrigir:</b> {esc(a["como_corrigir"])}</p>'
               if a.get("como_corrigir") else "")
        out.append(f'<div class="card achado {cls}">{tag(a.get("prioridade", "info"))}'
                   f'<h3>{esc(a.get("titulo", ""))}</h3><p>{esc(a.get("detalhe", ""))}</p>{url}{fix}</div>')
    return "".join(out) or '<p class="mut">Nenhum achado.</p>'


def tabela(cabecalho: Sequence[str], linhas: Iterable[Sequence], max_linhas: int = 500) -> str:
    th = "".join(f"<th>{esc(c)}</th>" for c in cabecalho)
    trs, n = [], 0
    for ln in linhas:
        n += 1
        if n > max_linhas:
            continue
        trs.append("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in ln) + "</tr>")
    extra = f'<p class="mut">… mais {n - max_linhas} linha(s) no CSV.</p>' if n > max_linhas else ""
    return f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(trs)}</tbody></table>{extra}"


def barra(valor: float, maximo: float = 100) -> str:
    pct = 0 if not maximo else max(0, min(100, round(100 * valor / maximo)))
    return f'<div class="barra" role="img" aria-label="{pct}%"><i style="width:{pct}%"></i></div>'


def salvar_texto(caminho, texto: str) -> Path:
    p = Path(caminho)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(texto, encoding="utf-8")
    return p


def salvar_json(caminho, dados) -> Path:
    return salvar_texto(caminho, json.dumps(dados, ensure_ascii=False, indent=2))


def salvar_csv(caminho, cabecalho: Sequence[str], linhas: Iterable[Sequence]) -> Path:
    p = Path(caminho)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cabecalho)
        for ln in linhas:
            w.writerow(ln)
    return p
