"""Monitor finito de rede para Windows, sem alterar a configuração do computador.

Não carrega o assistente, .env, dados, histórico ou linhas de comando. Os únicos
contatos externos são conexões TCP curtas a dois IPs públicos e a resolução de
example.com. Falhas nessas sondas não demonstram a causa de uma interrupção.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

INTERVALO = 10
MAX_SAIDA = 65536
PROCESSOS = frozenset(('ollama', 'ollama app', 'ollama_llama_server', 'python',
                      'pythonw', 'node', '9remote', '9router', 'cloudflared',
                      'tailscale', 'tailscaled', 'tailscale-ipn'))
DESTINOS = (('tcp_a', '1.1.1.1'), ('tcp_b', '9.9.9.9'))
_AMBIENTE = frozenset(('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP'))

# Somente consultas. Nenhuma informação identificadora é emitida pelo PowerShell.
_SISTEMA_PS = r"""
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$r=@{adaptadores=@(); gateways=@(); processos=@(); proxy=@{}; recursos=@{}; consultas=@{}}
try {
  $r.adaptadores=@(Get-NetAdapter -ErrorAction Stop | Select-Object -First 32 | ForEach-Object {
    $rx=$null; $tx=$null
    try { $s=$_ | Get-NetAdapterStatistics -ErrorAction Stop; $rx=$s.ReceivedBytes; $tx=$s.SentBytes } catch {}
    @{indice=[int]$_.ifIndex; estado=[string]$_.Status; recebidos=$rx; enviados=$tx}
  })
  $r.consultas.adaptadores='consultado'
} catch {$r.consultas.adaptadores='indisponivel'}
try {
  $cfg=@(Get-NetIPConfiguration -ErrorAction Stop | Where-Object {$_.IPv4DefaultGateway} | Select-Object -First 2)
  $r.gateways=@($cfg | ForEach-Object {
    $ok=$null
    try {
      $p=[Net.NetworkInformation.Ping]::new()
      try {$ok=($p.Send([string]$_.IPv4DefaultGateway.NextHop,600).Status -eq 'Success')} finally {$p.Dispose()}
    } catch {}
    @{indice=[int]$_.InterfaceIndex; responde=$ok}
  })
  $r.consultas.gateways='consultado'
} catch {$r.consultas.gateways='indisponivel'}
try {
  $p=Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction Stop
  $tipo='ausente'
  if ($p.ProxyEnable -eq 1) {
    $tipo='outro'
    $partes=@(([string]$p.ProxyServer) -split ';' | Where-Object {$_})
    if ($partes.Count -gt 0 -and @($partes | Where-Object {$_ -notmatch '^(?:\w+=)?(?:https?://)?(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$'}).Count -eq 0) {$tipo='loopback'}
  }
  $r.proxy=@{manual=($p.ProxyEnable -eq 1); tipo=$tipo; pac_configurado=(![string]::IsNullOrWhiteSpace([string]$p.AutoConfigURL))}
  $r.consultas.proxy='consultado'
} catch {$r.consultas.proxy='indisponivel'}
try {
  $o=Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
  $c=Get-CimInstance Win32_Processor -ErrorAction Stop | Measure-Object -Property LoadPercentage -Average
  $r.recursos=@{ram_total_kib=$o.TotalVisibleMemorySize; ram_livre_kib=$o.FreePhysicalMemory; cpu_percentual=$c.Average}
  $r.consultas.recursos='consultado'
} catch {$r.consultas.recursos='indisponivel'}
try {
  $nomes=@('ollama','ollama app','ollama_llama_server','python','pythonw','node','9remote','9router','cloudflared','tailscale','tailscaled','tailscale-ipn')
  $r.processos=@(Get-Process -ErrorAction Stop | Where-Object {$_.ProcessName -in $nomes} | Select-Object -First 32 | ForEach-Object {
    @{nome=$_.ProcessName; pid=[int]$_.Id; cpu_segundos=$_.CPU; memoria_bytes=$_.WorkingSet64}
  })
  $r.consultas.processos='consultado'
} catch {$r.consultas.processos='indisponivel'}
$r | ConvertTo-Json -Depth 5 -Compress
"""
_DNS_PS = r"""
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
try { $null=Resolve-DnsName -Name 'example.com' -DnsOnly -QuickTimeout -ErrorAction Stop; '{"resolveu":true}' }
catch { '{"resolveu":false}' }
"""


def _numero(valor, limite=2**64):
    return (isinstance(valor, (int, float)) and not isinstance(valor, bool)
            and 0 <= valor <= limite and math.isfinite(valor))


def _filtrar_sistema(dados):
    """Esquema fechado: nunca salva mensagens, endereços ou campos desconhecidos."""
    if not isinstance(dados, dict):
        return {'estado': 'resposta_invalida'}
    saida = {'estado': 'consultado', 'adaptadores': [], 'gateways': [],
             'processos': [], 'proxy': {}, 'recursos': {}, 'consultas': {}}
    consultas = dados.get('consultas')
    if isinstance(consultas, dict):
        saida['consultas'] = {k: consultas[k] for k in ('adaptadores', 'gateways', 'processos', 'proxy', 'recursos')
            if consultas.get(k) in ('consultado', 'indisponivel')}
    for item in dados.get('adaptadores', [])[:32] if isinstance(dados.get('adaptadores'), list) else []:
        if not isinstance(item, dict) or not _numero(item.get('indice'), 2**31):
            continue
        estado = item.get('estado')
        estado = estado if estado in ('Up', 'Down', 'Disconnected', 'Disabled',
                                      'Not Present', 'LowerLayerDown', 'Dormant', 'Unknown') else 'Unknown'
        saida['adaptadores'].append({'indice': int(item['indice']), 'estado': estado,
            **{k: item.get(k) if _numero(item.get(k)) else None for k in ('recebidos', 'enviados')}})
    for item in dados.get('gateways', [])[:2] if isinstance(dados.get('gateways'), list) else []:
        if isinstance(item, dict) and _numero(item.get('indice'), 2**31):
            saida['gateways'].append({'indice': int(item['indice']),
                'responde': item.get('responde') if type(item.get('responde')) is bool else None})
    for item in dados.get('processos', [])[:32] if isinstance(dados.get('processos'), list) else []:
        if (isinstance(item, dict) and isinstance(item.get('nome'), str)
                and item['nome'] in PROCESSOS and _numero(item.get('pid'), 2**31)):
            saida['processos'].append({'nome': item['nome'], 'pid': int(item['pid']),
                **{k: item.get(k) if _numero(item.get(k)) else None for k in ('cpu_segundos', 'memoria_bytes')}})
    proxy = dados.get('proxy')
    if isinstance(proxy, dict):
        saida['proxy'] = {k: proxy[k] for k in ('manual', 'pac_configurado') if type(proxy.get(k)) is bool}
        if proxy.get('tipo') in ('ausente', 'loopback', 'outro'):
            saida['proxy']['tipo'] = proxy['tipo']
    recursos = dados.get('recursos')
    if isinstance(recursos, dict):
        saida['recursos'] = {k: recursos[k] for k, limite in (
            ('ram_total_kib', 2**64), ('ram_livre_kib', 2**64), ('cpu_percentual', 100))
            if _numero(recursos.get(k), limite)}
    return saida


def _powershell(script, timeout):
    if sys.platform != 'win32':
        return None, 'windows_necessario'
    raiz = os.environ.get('SystemRoot', os.environ.get('SYSTEMROOT', r'C:\Windows'))
    executavel = Path(raiz) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
    if not executavel.is_file():
        return None, 'powershell_ausente'
    comando = [str(executavel), '-NoLogo', '-NoProfile', '-NonInteractive',
               '-EncodedCommand', base64.b64encode(script.encode('utf-16le')).decode('ascii')]
    ambiente = {k: v for k, v in os.environ.items() if k.upper() in _AMBIENTE}
    try:
        resultado = subprocess.run(comando, shell=False, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout,
            env=ambiente, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000))
        if resultado.returncode != 0:
            return None, 'consulta_indisponivel'
        if len(resultado.stdout) > MAX_SAIDA:
            return None, 'resposta_invalida'
        dados = json.loads(resultado.stdout.decode('utf-8-sig'))
        return dados, 'consultado'
    except subprocess.TimeoutExpired:
        return None, 'tempo_esgotado'
    except (OSError, UnicodeError, ValueError):
        return None, 'consulta_indisponivel'


def _tcp(ip, timeout):
    inicio = time.monotonic()
    try:
        # IP literal e socket AF_INET: não depende de DNS, proxy ou de HTTP.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as conexao:
            conexao.settimeout(timeout)
            conexao.connect((ip, 443))
        return {'conectou': True, 'milissegundos': round((time.monotonic() - inicio) * 1000)}
    except OSError:
        return {'conectou': False, 'milissegundos': None}


def coletar_amostra(*, restante=90):
    if sys.platform != 'win32':
        raise RuntimeError('Este diagnóstico precisa do Windows; nenhuma consulta foi feita.')
    prazo = time.monotonic() + restante
    def limite(maximo):
        return max(0.1, min(maximo, prazo - time.monotonic()))
    dados, estado = _powershell(_SISTEMA_PS, limite(6))
    sistema = _filtrar_sistema(dados) if estado == 'consultado' else {'estado': estado}
    dns, estado_dns = _powershell(_DNS_PS, limite(4))
    sondas = {nome: _tcp(ip, limite(0.6)) for nome, ip in DESTINOS}
    sondas['dns'] = {'estado': estado_dns, 'resolveu': (
        dns.get('resolveu') if isinstance(dns, dict) and type(dns.get('resolveu')) is bool else None)}
    return {'sistema': sistema, 'sondas': sondas}


def _taxas(anterior, atual, segundos):
    if segundos <= 0:
        return
    anteriores = {a['indice']: a for a in anterior.get('sistema', {}).get('adaptadores', [])}
    for adaptador in atual.get('sistema', {}).get('adaptadores', []):
        antes = anteriores.get(adaptador['indice'], {})
        for origem, destino in (('recebidos', 'recepcao_kib_s'), ('enviados', 'envio_kib_s')):
            a, b = antes.get(origem), adaptador.get(origem)
            if _numero(a) and _numero(b) and b >= a:
                adaptador[destino] = round((b - a) / segundos / 1024, 2)


def monitorar(duracao=90):
    if sys.platform != 'win32':
        raise RuntimeError('Este diagnóstico precisa do Windows; nenhuma consulta foi feita.')
    if type(duracao) is not int or not 30 <= duracao <= 180:
        raise ValueError('Use uma duração inteira entre 30 e 180 segundos.')
    inicio = time.monotonic()
    relatorio = {'formato': 1, 'inicio_utc': datetime.now(timezone.utc).isoformat(),
                 'duracao_solicitada_segundos': duracao, 'amostras': []}
    while time.monotonic() - inicio < duracao and len(relatorio['amostras']) < 19:
        tempo = time.monotonic() - inicio
        amostra = coletar_amostra(restante=duracao - tempo)
        amostra['segundos'] = round(time.monotonic() - inicio, 2)
        if relatorio['amostras']:
            anterior = relatorio['amostras'][-1]
            _taxas(anterior, amostra, amostra['segundos'] - anterior['segundos'])
        relatorio['amostras'].append(amostra)
        print('Amostra', len(relatorio['amostras']), 'registrada.', flush=True)
        restante = duracao - (time.monotonic() - inicio)
        if restante > 0:
            time.sleep(min(max(0, INTERVALO - (time.monotonic() - inicio - tempo)), restante))
    relatorio['duracao_real_segundos'] = round(time.monotonic() - inicio, 2)
    return relatorio


def resumir(relatorio):
    amostras = relatorio.get('amostras', [])
    tcp = [a for a in amostras if any(a['sondas'][k]['conectou'] for k in ('tcp_a', 'tcp_b'))]
    dns = [a for a in amostras if a['sondas']['dns'].get('resolveu') is True]
    linhas = ['Diagnóstico de rede: observações, sem causa confirmada.',
        f'Amostras: {len(amostras)}; com TCP externo: {len(tcp)}; com DNS resolvido: {len(dns)}.',
        'TCP A=1.1.1.1:443, B=9.9.9.9:443 (IPv4); DNS consulta somente example.com.']
    recursos = [a.get('sistema', {}).get('recursos', {}) for a in amostras]
    cpus = [r['cpu_percentual'] for r in recursos if _numero(r.get('cpu_percentual'), 100)]
    livres = [r['ram_livre_kib'] / 1024 for r in recursos if _numero(r.get('ram_livre_kib'))]
    usos = [100 * (1 - r['ram_livre_kib'] / r['ram_total_kib']) for r in recursos
            if _numero(r.get('ram_livre_kib')) and _numero(r.get('ram_total_kib'))
            and r['ram_total_kib'] > 0 and r['ram_livre_kib'] <= r['ram_total_kib']]
    linhas.append('Picos/mínimos observados: CPU máxima ' + (f'{max(cpus):.1f}%' if cpus else '?')
                  + '; RAM livre mínima ' + (f'{min(livres):.0f} MiB' if livres else '?')
                  + '; uso de RAM máximo ' + (f'{max(usos):.1f}%.' if usos else '?.'))
    tipos = sorted({a.get('sistema', {}).get('proxy', {}).get('tipo') for a in amostras
                    if a.get('sistema', {}).get('proxy', {}).get('tipo') in ('ausente', 'loopback', 'outro')})
    pac = any(a.get('sistema', {}).get('proxy', {}).get('pac_configurado') for a in amostras)
    linhas.append('Proxy manual: ' + (', '.join(tipos) if tipos else 'não verificado')
                  + '; PAC observado: ' + ('sim.' if pac else 'não confirmado.'))
    nomes = sorted({p['nome'] for a in amostras for p in a.get('sistema', {}).get('processos', [])})
    linhas.append('Processos da lista observados: ' + (', '.join(nomes) if nomes else 'nenhum ou consulta indisponível.'))
    linhas.extend(['', 'Sondas por amostra: sim/não/?; ? = sem medição disponível.',
                   'segundos | TCP A | TCP B | DNS | gateway ICMP | CPU % | RAM livre MiB'])
    sinal = lambda valor: 'sim' if valor is True else ('não' if valor is False else '?')
    estados = {}; mudancas = []
    for a in amostras:
        sistema, sondas = a.get('sistema', {}), a.get('sondas', {})
        r = sistema.get('recursos', {})
        gateways = [g.get('responde') for g in sistema.get('gateways', [])]
        gateway = True if True in gateways else (False if False in gateways else None)
        linhas.append(' | '.join((str(a.get('segundos', '?')), sinal(sondas.get('tcp_a', {}).get('conectou')),
            sinal(sondas.get('tcp_b', {}).get('conectou')), sinal(sondas.get('dns', {}).get('resolveu')),
            sinal(gateway), f"{r['cpu_percentual']:.1f}" if _numero(r.get('cpu_percentual'), 100) else '?',
            f"{r['ram_livre_kib'] / 1024:.0f}" if _numero(r.get('ram_livre_kib')) else '?')))
        for adaptador in sistema.get('adaptadores', []):
            indice, estado = adaptador['indice'], adaptador['estado']
            if indice in estados and estados[indice] != estado:
                mudancas.append(f"{a.get('segundos', '?')}s: interface {indice}, {estados[indice]} -> {estado}")
            estados[indice] = estado
    linhas.extend(['', 'Mudanças de estado de adaptadores:'] + (mudancas[:20] or ['Nenhuma observada ou consulta indisponível.']))
    linhas.extend(['',
        'Uma sonda pode ser bloqueada pelo provedor/firewall. ICMP pode ser bloqueado no gateway.',
        'TCP disponível com DNS falhando sugere investigar DNS; não comprova defeito no servidor DNS.',
        'TCP e DNS disponíveis com navegador falhando: confira proxy/PAC, VPN e a mensagem do navegador.',
        'Taxas incluem todo o tráfego do adaptador; não atribuem consumo a um aplicativo.',
        'CPU dos processos é cumulativa; compare a diferença entre amostras.'])
    if any(a.get('sistema', {}).get('proxy', {}).get('manual') or
           a.get('sistema', {}).get('proxy', {}).get('pac_configurado') for a in amostras):
        linhas.append('Proxy manual ou PAC observado: confira Configurações > Rede e Internet > Proxy; nenhuma opção foi alterada.')
    if any(a.get('sistema', {}).get('estado') != 'consultado' or
           'indisponivel' in a.get('sistema', {}).get('consultas', {}).values() for a in amostras):
        linhas.append('Há consultas locais indisponíveis ou sem resposta; veja os estados no JSON.')
    linhas.append('Nenhum modelo/programa foi aberto; nenhuma configuração foi alterada. O relatório não é enviado automaticamente.')
    return '\n'.join(linhas) + '\n'


def salvar(relatorio, pasta=None):
    pasta = Path(pasta) if pasta is not None else Path(__file__).resolve().parent / 'diagnosticos_rede'
    pasta.mkdir(parents=True, exist_ok=True)
    nome = 'rede_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    arquivo_json, arquivo_texto = pasta / (nome + '.json'), pasta / (nome + '.txt')
    with arquivo_json.open('x', encoding='utf-8') as arquivo:
        json.dump(relatorio, arquivo, ensure_ascii=False, indent=2, allow_nan=False)
        arquivo.write('\n')
    with arquivo_texto.open('x', encoding='utf-8') as arquivo:
        arquivo.write(resumir(relatorio))
    return arquivo_json, arquivo_texto


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duracao', type=int, default=90, choices=range(30, 181), metavar='30..180')
    args = parser.parse_args(argv)
    if sys.platform != 'win32':
        print('Este diagnóstico precisa do Windows; nenhuma consulta foi feita.')
        return 2
    print('Monitoramento por', args.duracao, 'segundos; não exige administrador e não altera a rede.')
    print('Faz pequenas sondas TCP em 1.1.1.1 e 9.9.9.9 e consulta DNS de example.com.')
    print('Aguarde duas amostras (~20 s); depois abra apenas um dos programas suspeitos.')
    try:
        relatorio = monitorar(args.duracao)
        arquivos = salvar(relatorio)
    except KeyboardInterrupt:
        print('Diagnóstico interrompido. Nenhuma configuração foi alterada.')
        return 1
    except (OSError, ValueError, RuntimeError):
        print('Não foi possível concluir ou salvar o diagnóstico. Confira as permissões da pasta e o Python 3.11+.')
        return 1
    print(resumir(relatorio))
    for arquivo in arquivos:
        print('Relatório local:', arquivo)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
