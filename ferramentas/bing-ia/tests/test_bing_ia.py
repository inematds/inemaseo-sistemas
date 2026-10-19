import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AQUI))
import bing_ia as B  # noqa: E402

EXEMPLO = AQUI.parents[1] / 'exemplos' / 'bing-ia' / 'entrada'


def gsc_fake(caminho):
    con = sqlite3.connect(caminho)
    con.execute('CREATE TABLE linhas (site TEXT, fim TEXT, query TEXT, page TEXT, clicks INTEGER, '
                'impressions INTEGER, ctr REAL, position REAL)')
    con.executemany('INSERT INTO linhas VALUES (?,?,?,?,?,?,?,?)', [
        ('ex.com', '2026-01-07', 'curso python', 'https://www.ex.com/python/', 3, 30, .1, 4.0),
        ('ex.com', '2026-01-14', 'curso python', 'https://www.ex.com/python/', 2, 20, .1, 5.0),
        ('ex.com', '2026-01-14', 'receita bolo', 'https://ex.com/bolo', 0, 9, 0, 30.0),
        ('ex.com', '2026-01-14', 'só google', 'https://ex.com/so-google/', 4, 40, .1, 2.0),
        ('outro.com', '2026-01-14', 'x', 'https://outro.com/', 9, 9, 1, 1.0)])
    con.commit()
    con.close()


class TestNormaliza(unittest.TestCase):
    def test_url(self):
        self.assertEqual(B.norm_url('https://www.Ex.com/a/?x=1#y'), 'ex.com/a')
        self.assertEqual(B.norm_url('http://ex.com/'), 'ex.com')
        self.assertEqual(B.norm_url('ex.com/a'), 'ex.com/a')

    def test_texto(self):
        self.assertEqual(B.norm_txt('  Ação, IA!  '), 'acao ia')

    def test_colunas_auto_e_manual(self):
        self.assertEqual(B.mapear_colunas(['Date', 'Page', 'Citations']),
                         {'url': 'Page', 'citacoes': 'Citations', 'data': 'Date'})
        m = B.mapear_colunas(['Endereço X', 'Vezes'], 'url=Endereço X,citacoes=Vezes')
        self.assertEqual(m, {'url': 'Endereço X', 'citacoes': 'Vezes'})
        with self.assertRaises(SystemExit):
            B.mapear_colunas(['a'], 'url=b')

    def test_numero(self):
        self.assertEqual(B._int('1,234'), 1234)
        self.assertEqual(B._int('7'), 7)
        self.assertEqual(B._int(''), 0)


class TestFluxo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        (d / 'pag.csv').write_text('Date,Page,Citations\n2026-01-10,https://ex.com/python,5\n'
                                   '2026-01-11,https://ex.com/bolo/,2\n2026-01-11,https://outro.com/z,1\n')
        (d / 'q.csv').write_text('Date;Grounding Query;Citations\n01/12/2026;Curso Python;4\n'
                                 '01/12/2026;tema novo;3\n')
        (d / 'ruim.csv').write_text('a,b\n1,2\n')
        gsc_fake(d / 'gsc.sqlite')
        self.d = d
        self.con = B.conectar(d / 'b.sqlite')
        B.importar(self.con, [d / 'pag.csv', d / 'q.csv'])

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_reimportar_nao_duplica(self):
        B.importar(self.con, [self.d / 'pag.csv'])
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM paginas').fetchone()[0], 3)

    def test_colunas_desconhecidas(self):
        with self.assertRaises(SystemExit):
            B.importar(self.con, [self.d / 'ruim.csv'])

    def test_cruzamento(self):
        r = B.analisar(self.con, self.d / 'gsc.sqlite', 'ex.com')
        self.assertTrue(r['tem_gsc'])
        self.assertEqual(r['total_citacoes'], 7)  # outro.com fica de fora
        self.assertEqual([p['url'] for p in r['citadas_com_clique']], ['https://ex.com/python'])
        self.assertEqual(r['citadas_com_clique'][0]['cliques_google'], 5)  # www e / final normalizados
        self.assertEqual([p['url'] for p in r['citadas_sem_clique']], ['https://ex.com/bolo/'])
        self.assertEqual([p['url'] for p in r['clique_sem_citacao']], ['https://ex.com/so-google/'])
        self.assertEqual([c['consulta'] for c in r['ideias']], ['tema novo'])
        self.assertEqual([c['consulta'] for c in r['ja_no_google']], ['Curso Python'])
        self.assertEqual(r['periodo'], ['2026-01-10', '2026-01-12'])

    def test_sem_gsc(self):
        r = B.analisar(self.con, self.d / 'nao-existe.sqlite')
        self.assertFalse(r['tem_gsc'])
        self.assertEqual(len(r['ideias']), 2)
        out = B.salvar(r, self.d / 's')
        self.assertIn('SEM GOOGLE', (out / 'relatorio.html').read_text())

    def test_saida(self):
        out = B.salvar(B.analisar(self.con, self.d / 'gsc.sqlite', 'ex.com'), self.d / 's2')
        h = (out / 'relatorio.html').read_text()
        self.assertIn('#FACC15', h)
        self.assertIn('tema novo', h)
        self.assertTrue((out / 'paginas.csv').exists())


class TestCLI(unittest.TestCase):
    def test_help(self):
        r = subprocess.run([sys.executable, str(AQUI / 'bing_ia.py'), '--help'], capture_output=True, text=True,
                           timeout=30)
        self.assertEqual(r.returncode, 0)
        self.assertIn('AI Performance', r.stdout)

    @unittest.skipUnless(EXEMPLO.exists(), 'exemplo ausente')
    def test_exemplo_ficticio(self):
        with tempfile.TemporaryDirectory() as t:
            con = B.conectar(Path(t) / 'b.sqlite')
            rel = B.importar(con, sorted(EXEMPLO.glob('*.csv')))
            self.assertEqual({x['tipo'] for x in rel}, {'paginas', 'consultas'})


if __name__ == '__main__':
    unittest.main()
