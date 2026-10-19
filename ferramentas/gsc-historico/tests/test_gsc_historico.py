import csv
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

AQUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AQUI))
import gsc_historico as G  # noqa: E402

EXEMPLO = AQUI.parents[1] / 'exemplos' / 'gsc-historico' / 'entrada'
CAB = ['query', 'page', 'clicks', 'impressions', 'ctr', 'position']


def escreve(pasta, nome, cab, linhas):
    with open(Path(pasta) / nome, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(cab)
        w.writerows(linhas)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        escreve(d, 'resumo.csv', ['inicio', 'fim', 'site', *G.CAMPOS_RESUMO], [
            ['2026-01-01', '2026-01-07', 'ex.com', 10, 100, 8, 60, 1, 20, 1, 20, 2],
            ['2026-01-08', '2026-01-14', 'ex.com', 12, 130, 8, 60, 3, 50, 1, 20, 4]])
        escreve(d, '2026-01-07_ex.com_sem-marca.csv', CAB, [
            ['curso python', 'https://ex.com/python/', 1, 10, 0.1, 5.0],
            ['caiu muito', 'https://ex.com/a/', 0, 10, 0, 8.0]])
        escreve(d, '2026-01-14_ex.com_sem-marca.csv', CAB, [
            ['curso python', 'https://ex.com/python/', 3, 30, 0.1, 4.0],
            ['caiu muito', 'https://ex.com/a/', 0, 2, 0, 9.0],
            ['receita bolo', 'https://ex.com/', 0, 8, 0, 40.0],          # nova, sem dona → pauta
            ['python avançado', 'https://ex.com/python/', 0, 6, 0, 25.0],  # nova, página tem "python" → melhorar
            ['nova top', 'https://ex.com/top/', 0, 4, 0, 3.0]])            # nova mas já na 1ª página
        escreve(d, 'outro.csv', ['x'], [[1]])
        self.dir = d
        self.con = G.conectar(d / 'g.sqlite')


class TestImportar(Base):
    def test_importa_e_e_idempotente(self):
        c1 = G.importar(self.con, [self.dir])
        c2 = G.importar(self.con, [self.dir])
        self.assertEqual(c1['semanas'], 2)
        self.assertEqual(c1['linhas'], 7)
        self.assertEqual(c1['ignorados'], ['outro.csv'])
        self.assertEqual(c2['linhas'], 7)
        n = self.con.execute('SELECT COUNT(*) FROM linhas').fetchone()[0]
        self.assertEqual(n, 7)  # reimportar não duplica

    def test_nome_do_arquivo(self):
        m = G.NOME_SEMANA.match('2026-10-11_inema.club_sem-marca.csv')
        self.assertEqual(m.groups(), ('2026-10-11', 'inema.club'))


class TestAnalise(Base):
    def setUp(self):
        super().setUp()
        G.importar(self.con, [self.dir])
        self.res = G.analisar(self.con, 'ex.com')

    def test_semana_atual_e_anterior(self):
        self.assertEqual(self.res['atual'], '2026-01-14')
        self.assertEqual(self.res['anterior'], '2026-01-07')

    def test_subiu_caiu(self):
        self.assertEqual(self.res['subiram'][0]['consulta'], 'curso python')
        self.assertEqual(self.res['subiram'][0]['delta_cliques'], 2)
        self.assertEqual(self.res['cairam'][0]['consulta'], 'caiu muito')
        self.assertEqual(self.res['cairam'][0]['delta_impr'], -8)

    def test_pauta_e_melhorar(self):
        self.assertEqual([p['consulta'] for p in self.res['pauta']], ['receita bolo'])
        self.assertEqual([p['consulta'] for p in self.res['melhorar']], ['python avançado'])

    def test_paginas_sem_clique(self):
        pags = [p['pagina'] for p in self.res['paginas_sem_clique']]
        self.assertIn('https://ex.com/', pags)
        self.assertNotIn('https://ex.com/python/', pags)  # teve clique

    def test_saida(self):
        out = G.salvar(self.res, self.dir / 'saida')
        h = (out / 'relatorio.html').read_text()
        self.assertIn('#0c0c10', h)
        self.assertIn('receita bolo', h)
        self.assertEqual(json.loads((out / 'relatorio.json').read_text())['site'], 'ex.com')
        self.assertTrue((out / 'pauta.csv').exists())

    def test_sobreposicao(self):
        s = [{'inicio': '2026-09-27', 'fim': '2026-10-03'}, {'inicio': '2026-09-28', 'fim': '2026-10-04'}]
        self.assertEqual(len(G._sobreposicao(s)), 1)


class TestCLI(unittest.TestCase):
    def test_help(self):
        r = subprocess.run([sys.executable, str(AQUI / 'gsc_historico.py'), '--help'], capture_output=True,
                           text=True, timeout=30)
        self.assertEqual(r.returncode, 0)
        self.assertIn('importar', r.stdout)

    @unittest.skipUnless(EXEMPLO.exists(), 'exemplo ausente')
    def test_exemplo_real(self):
        with tempfile.TemporaryDirectory() as t:
            db = Path(t) / 'g.sqlite'
            with redirect_stdout(io.StringIO()):
                G.main(['importar', str(EXEMPLO), '--db', str(db)])
                G.main(['relatorio', '--db', str(db), '--site', 'inema.club', '--saida', str(Path(t) / 's')])
            self.assertTrue((Path(t) / 's' / 'relatorio.html').exists())
            n = sqlite3.connect(db).execute('SELECT COUNT(DISTINCT fim) FROM semanas').fetchone()[0]
            self.assertGreaterEqual(n, 5)


if __name__ == '__main__':
    unittest.main()
