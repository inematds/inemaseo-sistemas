import gzip
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AQUI))
import botlog as B  # noqa: E402

EX = AQUI.parents[1] / 'exemplos' / 'botlog' / 'entrada'
UA_GPT = 'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.4; +https://openai.com/gptbot)'
UA_OAI = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 '
          'Safari/537.36; compatible; OAI-SearchBot/1.4; +https://openai.com/searchbot')


def linha(ip, caminho, ua, status=200):
    return f'{ip} - - [13/Oct/2026:11:00:00 +0000] "GET {caminho} HTTP/1.1" {status} 10 "-" "{ua}"'


class TestIdentificar(unittest.TestCase):
    def casos(self):
        return {
            UA_OAI: ('OAI-SearchBot', 'busca'),
            UA_GPT: ('GPTBot', 'treino'),
            'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot':
                ('ChatGPT-User', 'usuario'),
            'compatible; ClaudeBot/1.0; +claudebot@anthropic.com': ('ClaudeBot', 'treino'),
            'compatible; Claude-SearchBot/1.0': ('Claude-SearchBot', 'busca'),
            'compatible; Claude-User/1.0': ('Claude-User', 'usuario'),
            'compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot': ('PerplexityBot', 'busca'),
            'compatible; Perplexity-User/1.0': ('Perplexity-User', 'usuario'),
            'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)': ('Googlebot', 'buscador'),
            'Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)': ('bingbot', 'buscador'),
        }

    def test_ua_oficiais(self):
        for ua, (nome, fin) in self.casos().items():
            r = B.identificar(ua)
            self.assertIsNotNone(r, ua)
            self.assertEqual((r['nome'], r['finalidade']), (nome, fin), ua)

    def test_navegador_nao_e_robo(self):
        self.assertIsNone(B.identificar('Mozilla/5.0 (X11; Linux x86_64) Chrome/141.0 Safari/537.36'))

    def test_google_extended_nao_e_ua(self):
        self.assertNotIn('Google-Extended', [r['nome'] for r in B.ROBOS])


class TestListas(unittest.TestCase):
    def test_listas_versionadas_existem_e_parseiam(self):
        for r in B.ROBOS:
            for arq in r['listas']:
                self.assertTrue(B.rede_da_lista(arq), arq)

    def test_google_tem_ipv4_e_ipv6(self):
        versoes = {n.version for n in B.rede_da_lista('developers.google.com_googlebot.json')}
        self.assertEqual(versoes, {4, 6})

    def test_ip_real_do_log_e_oficial(self):
        # IPs vistos no log real de desenho.inema.pro (VPS6, 06–19/10/2026)
        self.assertTrue(B.ip_na_lista('74.7.227.62', ['openai.com_gptbot.json']))
        self.assertTrue(B.ip_na_lista('216.73.217.101', ['claude.com_bots.json']))
        self.assertFalse(B.ip_na_lista('192.0.2.10', ['openai.com_gptbot.json']))
        self.assertFalse(B.ip_na_lista('lixo', ['openai.com_gptbot.json']))

    def test_verificar(self):
        gpt = B.identificar(UA_GPT)
        self.assertEqual(B.verificar(gpt, '74.7.227.62'), 'autentico')
        self.assertEqual(B.verificar(gpt, '192.0.2.10'), 'falso')
        ads = next(r for r in B.ROBOS if r['nome'] == 'OAI-AdsBot')
        self.assertEqual(B.verificar(ads, '192.0.2.10'), 'sem_lista')


class TestLeitura(unittest.TestCase):
    def test_combined(self):
        r = B.ler_linha(linha('1.2.3.4', '/a/?x=1', UA_GPT, 403))
        self.assertEqual((r['ip'], r['caminho'], r['status'], r['metodo']), ('1.2.3.4', '/a/', 403, 'GET'))

    def test_cloudflare(self):
        j = json.dumps({'ClientIP': '1.2.3.4', 'ClientRequestURI': '/b?y', 'ClientRequestUserAgent': UA_GPT,
                        'EdgeResponseStatus': 200, 'EdgeStartTimestamp': '2026-10-14T09:00:00Z'})
        r = B.ler_linha(j)
        self.assertEqual((r['ip'], r['caminho'], r['status']), ('1.2.3.4', '/b', 200))

    def test_lixo(self):
        self.assertIsNone(B.ler_linha('isto não é log'))
        self.assertIsNone(B.ler_linha('{"x": 1}'))


class TestAnalise(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        linhas = [
            linha('74.7.227.62', '/', UA_GPT),
            linha('74.7.227.62', '/robots.txt', UA_GPT),
            linha('192.0.2.10', '/wp-login.php', UA_GPT, 404),       # falso GPTBot
            linha('74.7.228.62', '/so-403/', UA_OAI, 403),           # bloqueado: não conta como lida
            linha('198.51.100.7', '/pessoa/', 'Mozilla/5.0 Chrome/141'),
            linha('198.51.100.8', '/x', 'AlgumCrawler/1.0 (+https://x)'),
        ]
        self.log = d / 'access.log.gz'
        with gzip.open(self.log, 'wt') as f:
            f.write('\n'.join(linhas) + '\nlinha quebrada\n')
        (d / 'sitemap.xml').write_text(
            '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            '<url><loc>https://ex.com/</loc></url><url><loc>https://ex.com/so-403/</loc></url>'
            '<url><loc>https://ex.com/nunca/</loc></url></urlset>')
        self.d = d

    def tearDown(self):
        self.tmp.cleanup()

    def test_relatorio(self):
        r = B.analisar([self.log], self.d / 'sitemap.xml')
        self.assertEqual(r['linhas_lidas'], 6)
        self.assertEqual(r['linhas_invalidas'], 1)
        gpt = next(x for x in r['robos'] if x['robo'] == 'GPTBot')
        self.assertEqual((gpt['acessos'], gpt['autenticos'], gpt['falsos'], gpt['robots_txt']), (3, 2, 1, 1))
        self.assertEqual([f['ip'] for f in r['falsos']], ['192.0.2.10'])
        self.assertEqual(r['por_finalidade'], {'treino': 2, 'busca': 1, 'desconhecido': 1})
        self.assertEqual(r['nunca_visitadas'], ['/nunca/', '/so-403/'])
        out = B.salvar(r, self.d / 's')
        h = (out / 'relatorio.html').read_text()
        self.assertIn('#0c0c10', h)
        self.assertIn('192.0.2.10', h)
        self.assertNotIn('198.51.100.7', (out / 'acessos.csv').read_text())  # pessoa não entra no CSV

    def test_filtrar_lgpd(self):
        dest = self.d / 'robos.log'
        n, m = B.filtrar([self.log], dest)
        self.assertEqual((n, m), (6, 3))
        txt = dest.read_text()
        self.assertNotIn('198.51.100', txt)
        self.assertNotIn('192.0.2.10', txt)


class TestCLI(unittest.TestCase):
    def test_help(self):
        r = subprocess.run([sys.executable, str(AQUI / 'botlog.py'), '--help'], capture_output=True, text=True,
                           timeout=30)
        self.assertEqual(r.returncode, 0)
        self.assertIn('finalidade', r.stdout)

    @unittest.skipUnless(EX.exists(), 'exemplo ausente')
    def test_exemplos(self):
        r = B.analisar([EX / 'MONTADO_access.log', EX / 'MONTADO_cloudflare.jsonl'], EX / 'MONTADO_sitemap.xml')
        self.assertEqual(len(r['falsos']), 3)
        self.assertEqual(r['nunca_visitadas'], ['/blog/post-b/'])
        real = B.analisar([EX / 'REAL_desenho-inema-pro_robos.log'])
        self.assertTrue(all(x['falsos'] == 0 for x in real['robos']))


if __name__ == '__main__':
    unittest.main()
