import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parent
FERR = AQUI.parent
sys.path.insert(0, str(FERR.parent / "auditor" / "tests"))
import sitefalso  # noqa: E402

_spec = importlib.util.spec_from_file_location("agente_ready", FERR / "agente-ready.py")
AR = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(AR)
HTML = {"content-type": "text/html; charset=utf-8"}


class TestPesos(unittest.TestCase):
    def test_soma_100_e_fonte(self):
        p = AR.carregar_pesos()
        self.assertEqual(sum(c["peso"] for c in p["criterios"]), 100)
        for c in p["criterios"]:
            self.assertTrue(c["por_que"] and c["fonte"], c["id"])
            self.assertIn(c["categoria"], p["categorias"])
        llms = [c for c in p["criterios"] if c["id"] == "llms_txt"][0]
        self.assertLessEqual(llms["peso"], 2)
        self.assertIn("97%", llms["por_que"])

    def test_na_sai_do_denominador(self):
        p = {"fator": {"ok": 1, "parcial": 0.5, "falha": 0}, "criterios": [
            {"id": "a", "categoria": "x", "peso": 50, "titulo": "", "por_que": "", "fonte": []},
            {"id": "b", "categoria": "x", "peso": 50, "titulo": "", "por_que": "", "fonte": []}]}
        nota, _, _ = AR.pontuar({"a": ("ok", ""), "b": ("na", "")}, p)
        self.assertEqual(nota, 100)
        nota, _, _ = AR.pontuar({"a": ("ok", ""), "b": ("parcial", "")}, p)
        self.assertEqual(nota, 75)


class TestWebMCP(unittest.TestCase):
    def test_document_atual(self):
        w = AR.detectar_webmcp(['document.modelContext.registerTool({ name: "x_y", description: "d" })'])
        self.assertTrue(w["document"])
        self.assertEqual(w["registros"], 1)
        self.assertEqual(w["nomes"], ["x_y"])

    def test_alias_minificado(self):
        w = AR.detectar_webmcp(['let e=document.modelContext;if(!e?.registerTool)return;e.registerTool({name:"buscar_cursos",description:"d"})'])
        self.assertTrue(w["document"])
        self.assertEqual(w["registros"], 1)
        self.assertEqual(w["nomes"], ["buscar_cursos"])

    def test_navigator_legado(self):
        w = AR.detectar_webmcp(["navigator.modelContext.registerTool({name:'velho'})"])
        self.assertTrue(w["navigator"])
        self.assertFalse(w["document"])

    def test_nada(self):
        w = AR.detectar_webmcp(["console.log('modelo de contexto')"])
        self.assertEqual((w["document"], w["navigator"], w["registros"]), (False, False, 0))


class TestAvaliar(unittest.TestCase):
    def test_site_sem_webmcp(self):
        ev, res = AR.avaliar("https://ex.test/", sitefalso.coletor(), paginas=4)
        self.assertEqual(res["robots_busca"][0], "ok")
        self.assertIn("GPTBot", res["robots_treino"][1])
        self.assertEqual(res["cdn_robos"][0], "parcial")  # OAI-SearchBot barrado, Perplexity não
        self.assertEqual(res["entidade_id"][0], "ok")
        self.assertEqual(res["sameas"][0], "ok")
        self.assertEqual(res["webmcp_api"][0], "falha")
        self.assertEqual(res["webmcp_politica"][0], "na")
        self.assertEqual(res["llms_txt"][0], "falha")
        self.assertIn(res["form_label"][0], ("parcial", "falha"))
        self.assertEqual(res["form_autocomplete"][0], "parcial")  # email sim, nome não
        nota, _, _ = AR.pontuar(res, AR.carregar_pesos())
        self.assertTrue(0 < nota < 100)

    def test_site_com_webmcp_e_politica_desligada(self):
        hd = dict(HTML, **{"permissions-policy": "tools=(), camera=()"})
        extra = {"https://ex.test/": (AQUI / "fixtures" / "webmcp.html", hd),
                 "https://ex.test/app.js": (AQUI / "fixtures" / "webmcp.html", {"content-type": "text/javascript"})}
        ev, res = AR.avaliar("https://ex.test/", sitefalso.coletor(extra_rotas=extra, bloquear_ua=()), paginas=1)
        self.assertEqual(res["webmcp_api"][0], "ok")
        self.assertIn("buscar_cursos", res["webmcp_api"][1])
        self.assertEqual(res["webmcp_politica"][0], "falha")
        self.assertEqual(res["cdn_robos"][0], "ok")
        self.assertEqual(res["entidade_id"][0], "ok")
        self.assertEqual(res["sobre_contato"][0], "falha")

    def test_main_gera_saida(self):
        import inemaweb as W
        orig = W.Coletor.__init__

        def falso(self, *a, **k):
            orig(self, pausa=0, buscar=lambda u, h, s, t, m: sitefalso.buscar(u, h, s, t, m))
        with tempfile.TemporaryDirectory() as t, contextlib.redirect_stdout(io.StringIO()):
            W.Coletor.__init__ = falso
            try:
                AR.main(["https://ex.test/", "--saida", t])
            finally:
                W.Coletor.__init__ = orig
            html = (Path(t) / "relatorio.html").read_text(encoding="utf-8")
            self.assertIn("pesos.json", html)
            self.assertIn("#FACC15", html)
            self.assertTrue((Path(t) / "criterios.csv").exists())

    def test_help(self):
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stdout(io.StringIO()):
            AR.main(["--help"])
        self.assertEqual(cm.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
