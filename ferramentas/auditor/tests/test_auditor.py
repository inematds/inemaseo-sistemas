import sys
import tempfile
import unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(AQUI.parent))
import auditor  # noqa: E402
import inemaweb as W  # noqa: E402
import sitefalso  # noqa: E402


class TestRobots(unittest.TestCase):
    def test_grupo_especifico_e_reserva(self):
        r = W.Robots("User-agent: *\nDisallow: /adm\n\nUser-agent: GPTBot\nDisallow: /\n")
        self.assertFalse(r.pode("GPTBot", "https://x/"))
        self.assertTrue(r.pode("OAI-SearchBot", "https://x/"))
        self.assertFalse(r.pode("OAI-SearchBot", "https://x/adm/painel"))

    def test_mais_longa_vence_e_empate_allow(self):
        r = W.Robots("User-agent: *\nDisallow: /a\nAllow: /a/livre\nAllow: /b\nDisallow: /b\n")
        self.assertTrue(r.pode("x", "https://x/a/livre/1"))
        self.assertFalse(r.pode("x", "https://x/a/fechado"))
        self.assertTrue(r.pode("x", "https://x/b"))  # empate de tamanho: allow vence

    def test_curingas(self):
        r = W.Robots("User-agent: *\nDisallow: /*.pdf$\nDisallow: /busca*q=\n")
        self.assertFalse(r.pode("x", "https://x/doc/a.pdf"))
        self.assertTrue(r.pode("x", "https://x/doc/a.pdf?v=1"))
        self.assertFalse(r.pode("x", "https://x/busca?q=seo"))

    def test_maiusculas_grupo_multiplo_e_sitemap(self):
        r = W.Robots("User-Agent: ClaudeBot\nuser-agent: GPTBot\nDisallow: /\nSitemap: https://x/s.xml\n"
                     "Content-Signal: search=yes, ai-train=no\n")
        self.assertFalse(r.pode("claudebot", "https://x/p"))
        self.assertFalse(r.pode("GPTBot", "https://x/p"))
        self.assertTrue(r.pode("PerplexityBot", "https://x/p"))
        self.assertEqual(r.sitemaps, ["https://x/s.xml"])
        self.assertEqual(r.sinais, ["search=yes, ai-train=no"])

    def test_status_http(self):
        self.assertTrue(W.Robots("", 404).pode("x", "https://x/"))
        self.assertFalse(W.Robots("", 503).pode("x", "https://x/"))

    def test_disallow_vazio_libera(self):
        self.assertTrue(W.Robots("User-agent: *\nDisallow:\n").pode("x", "https://x/qualquer"))


class TestEntidade(unittest.TestCase):
    def test_subtipos(self):
        self.assertTrue(W.eh_entidade({"@type": "NewsMediaOrganization"}))
        self.assertTrue(W.eh_entidade({"@type": ["Thing", "Person"]}))
        self.assertFalse(W.eh_entidade({"@type": "CollectionPage"}))
        self.assertFalse(W.eh_entidade({"@type": "WebSite"}))
        self.assertTrue(W.eh_entidade({"@type": "WebSite"}, com_site=True))


class TestPagina(unittest.TestCase):
    def test_extrai(self):
        html = (sitefalso.FIX / "index.html").read_text(encoding="utf-8")
        p = W.Pagina("https://ex.test/", html)
        self.assertEqual(p.lang, "pt-BR")
        self.assertEqual(p.h1, ["Site de exemplo"])
        self.assertEqual(p.canonicos, ["https://ex.test/"])
        self.assertIn(("en", "https://ex.test/en/"), p.hreflang)
        self.assertEqual(p.tipos_jsonld(), ["Organization"])
        self.assertIn("https://ex.test/a", p.links)
        self.assertGreater(p.palavras, 80)
        campos = p.forms[0]["campos"]
        self.assertTrue(campos[0]["rotulado"])
        self.assertFalse(campos[1]["rotulado"])

    def test_head_sem_fechamento(self):
        p = W.Pagina("https://x/", "<html><head><title>T</title><body><h1>Oi</h1><p>um dois tres quatro</p></body></html>")
        self.assertEqual(p.palavras, 5)  # Oi + 4 palavras; <title> não conta

    def test_jsonld_graph_e_invalido(self):
        p = W.Pagina("https://ex.test/a", (sitefalso.FIX / "a.html").read_text(encoding="utf-8"))
        self.assertIn("FAQPage", p.tipos_jsonld())
        self.assertEqual(len([e for o, e in p.jsonld() if e]), 1)
        self.assertEqual(p.imgs_sem_alt, 1)


class TestAuditoria(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dados, cls.achados = auditor.auditar("https://ex.test/", sitefalso.coletor(), maximo=20, log=lambda *_: None)
        cls.ids = {a["id"]: a for a in cls.achados}

    def test_achados_esperados(self):
        for id_ in ("www-duplicado", "robots-treino", "cdn-oai-searchbot", "quebrados", "noindex-sitemap",
                    "canonico-multiplo", "canonico-relativo", "hreflang-reciproco", "titulo-tamanho",
                    "h1-ausente", "jsonld-invalido", "jsonld-sem-id", "faq", "alt", "orfa", "sitemap-lastmod",
                    "sitemap-status"):
            self.assertIn(id_, self.ids, id_)

    def test_nao_inventa(self):
        self.assertNotIn("http-https", self.ids)  # http → 301 https está certo
        self.assertNotIn("robots-busca", self.ids)  # PerplexityBot só bloqueado em /privado
        self.assertNotIn("sitemap-ausente", self.ids)
        self.assertNotIn("robots-tudo", self.ids)

    def test_prioridades(self):
        self.assertEqual(self.ids["cdn-oai-searchbot"]["prioridade"], "critico")
        self.assertEqual(self.ids["robots-treino"]["prioridade"], "info")
        self.assertEqual(self.ids["noindex-sitemap"]["prioridade"], "critico")
        ordem = [auditor.ORDEM[a["prioridade"]] for a in self.achados]
        self.assertEqual(ordem, sorted(ordem))

    def test_cdn_respeita_robots(self):
        gpt = [c for c in self.dados["cdn"] if c["token"] == "GPTBot"][0]
        self.assertIn("robots.txt proíbe", gpt["status"])

    def test_limite_max(self):
        d, _ = auditor.auditar("https://ex.test/", sitefalso.coletor(), maximo=2, testar_cdn=False, log=lambda *_: None)
        self.assertEqual(len(d["paginas"]), 2)

    def test_saida(self):
        with tempfile.TemporaryDirectory() as t:
            auditor.salvar(self.dados, self.achados, Path(t))
            html = (Path(t) / "relatorio.html").read_text(encoding="utf-8")
            self.assertIn("#0c0c10", html)
            self.assertIn("CRÍTICO", html)
            for f in ("auditoria.json", "achados.csv", "paginas.csv"):
                self.assertTrue((Path(t) / f).exists())

    def test_help(self):
        import contextlib
        import io
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stdout(io.StringIO()):
            auditor.main(["--help"])
        self.assertEqual(cm.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
