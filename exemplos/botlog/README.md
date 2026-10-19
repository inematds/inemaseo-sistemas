# Exemplo — botlog

## Real: desenho.inema.pro (VPS6)

- `entrada/REAL_desenho-inema-pro_robos.log`: **8 linhas reais** do access log do nginx da VPS6 (Hostinger, desenho.inema.pro e n8n.inema.cloud no mesmo nginx), período 05/10 a 19/10/2026, lidas só em leitura por SSH em 19/10/2026.
- O log original tinha 3.082 linhas. Passou pelo `botlog.py filtrar`: ficaram só linhas de robô do catálogo com IP dentro da lista oficial (GPTBot, OAI-SearchBot, ClaudeBot). Todo IP de pessoa, scanner, `curl` ou `python-httpx` saiu (LGPD). O log original não foi copiado.
- `saida-real/`: relatório. A seção "páginas que nenhum robô conseguiu ler" fica vazia porque, sem o tráfego de pessoas e sem sitemap, o universo de páginas é só o que os próprios robôs pediram.

## Montado

- `entrada/MONTADO_access.log`, `MONTADO_cloudflare.jsonl`, `MONTADO_sitemap.xml`: **amostra montada**. User-Agents copiados das páginas oficiais (Claude-User e Claude-SearchBot com string completa montada: a Anthropic dá o nome, não a string inteira [a confirmar]). IPs de robô tirados das listas oficiais. IPs de pessoa e de falsos robôs são de faixas reservadas para documentação (198.51.100.0/24 e 192.0.2.0/24, RFC 5737): não são de ninguém.
- `saida-montado/`: relatório com 3 falsos robôs (GPTBot, Googlebot e PerplexityBot de IP fora da lista), um 403 para ClaudeBot (simula bloqueio de CDN) e uma página do sitemap que nenhum robô leu.

```bash
cd ferramentas/botlog
python3 botlog.py analisar ../../exemplos/botlog/entrada/MONTADO_access.log ../../exemplos/botlog/entrada/MONTADO_cloudflare.jsonl --sitemap ../../exemplos/botlog/entrada/MONTADO_sitemap.xml --saida ../../exemplos/botlog/saida-montado
python3 botlog.py analisar ../../exemplos/botlog/entrada/REAL_desenho-inema-pro_robos.log --saida ../../exemplos/botlog/saida-real
```
