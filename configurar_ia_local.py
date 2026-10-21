"""Configura Ollama no próprio PC, sem chaves ou créditos de APIs cloud.

Instale e abra o Ollama em https://ollama.com/download. Este assistente não
instala programas nem baixa modelos sem --baixar-modelo explícito.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from urllib.parse import urlsplit

ENV = Path(__file__).resolve().parent / '.env'
URL_PADRAO = 'http://127.0.0.1:11434'
MODELO_PADRAO = 'qwen2.5:3b'
CHAVES = ('OLLAMA_HABILITADO', 'OLLAMA_URL', 'OLLAMA_MODEL')
LIMITE_RESPOSTA = 2_000_000
TIMEOUT_CONSULTA = 4
TIMEOUT_DOWNLOAD = 30 * 60
PADRAO_MODELO = re.compile(
    r'[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*'
    r'(?::[A-Za-z0-9][A-Za-z0-9._-]*)?'
)


class FalhaConfiguracao(RuntimeError):
    """Mensagem local controlada, sem respostas brutas ou credenciais."""


def validar_url(texto):
    """Aceita apenas IP literal de loopback, sem proxy, caminho ou credencial."""
    if not isinstance(texto, str) or any(c.isspace() for c in texto):
        raise ValueError('Use uma URL local como http://127.0.0.1:11434.')
    try:
        partes = urlsplit(texto)
        host = partes.hostname or ''
        ip = ipaddress.ip_address(host)
        porta = partes.port
    except ValueError:
        raise ValueError('OLLAMA_URL exige um IP literal de loopback, como 127.0.0.1 ou [::1].') from None
    if (partes.scheme not in ('http', 'https') or not ip.is_loopback or '%' in host
            or partes.username is not None or partes.password is not None
            or partes.path not in ('', '/') or partes.query or partes.fragment
            or porta is not None and not 1 <= porta <= 65535):
        raise ValueError('OLLAMA_URL deve apontar apenas ao próprio PC, sem caminho ou credenciais.')
    porta = porta if porta is not None else (443 if partes.scheme == 'https' else 80)
    host = f'[{ip.compressed}]' if ip.version == 6 else ip.compressed
    return f'{partes.scheme}://{host}:{porta}'


def validar_modelo(modelo):
    if not isinstance(modelo, str) or len(modelo) > 200 or not PADRAO_MODELO.fullmatch(modelo):
        raise ValueError('Nome de modelo inválido. Exemplo: qwen2.5:3b.')
    return modelo


class SemRedirecionamento(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def listar_modelos(url=URL_PADRAO):
    url = validar_url(url)
    cliente = urllib.request.build_opener(urllib.request.ProxyHandler({}), SemRedirecionamento())
    pedido = urllib.request.Request(url + '/api/tags', headers={'Accept': 'application/json'})
    try:
        with cliente.open(pedido, timeout=TIMEOUT_CONSULTA) as resposta:
            corpo = resposta.read(LIMITE_RESPOSTA + 1)
    except urllib.error.HTTPError as erro:
        with erro:
            codigo = erro.code
        raise FalhaConfiguracao(f'Ollama respondeu HTTP {codigo}; o serviço local não foi validado.') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise FalhaConfiguracao(
            'O serviço Ollama não respondeu no endereço local. Instale e abra o Ollama; '
            'se necessário, execute ollama serve em outro terminal.'
        ) from None
    if len(corpo) > LIMITE_RESPOSTA:
        raise FalhaConfiguracao('A lista de modelos excedeu o tamanho permitido.')
    try:
        dados = json.loads(corpo.decode('utf-8'))
        itens = dados['models']
        if not isinstance(itens, list):
            raise ValueError
        modelos = []
        for item in itens:
            nome = item.get('name') or item.get('model')
            nome = validar_modelo(nome)
            if nome not in modelos:
                modelos.append(nome)
        return modelos
    except (ValueError, UnicodeError, KeyError, TypeError, AttributeError):
        raise FalhaConfiguracao('O serviço local retornou uma lista de modelos inválida.') from None


def modelo_instalado(modelo, modelos):
    validar_modelo(modelo)
    candidatos = (modelo, modelo + ':latest') if ':' not in modelo else (modelo,)
    return next((nome for nome in candidatos if nome in modelos), None)


def valores_env(caminho=ENV):
    """Lê somente as três opções de Ollama; nunca imprime conteúdo do .env."""
    caminho = Path(caminho)
    if not caminho.exists():
        return {}
    valores = {}
    for linha in caminho.read_text(encoding='utf-8-sig').splitlines():
        if linha.lstrip().startswith('#') or '=' not in linha:
            continue
        chave, valor = linha.split('=', 1)
        if chave.strip() in CHAVES:
            valores[chave.strip()] = valor.strip().strip('"\'')
    return valores


def atualizar_env(modelo, url=URL_PADRAO, caminho=ENV):
    """Substitui só as três opções locais, preservando as outras linhas e segredos."""
    modelo = validar_modelo(modelo)
    url = validar_url(url)
    caminho = Path(caminho)
    bruto = caminho.read_bytes() if caminho.exists() else b''
    bom = '\ufeff' if bruto.startswith(b'\xef\xbb\xbf') else ''
    original = bruto.decode('utf-8-sig')
    quebra = '\r\n' if '\r\n' in original else '\n'
    alteracoes = {'OLLAMA_HABILITADO': '1', 'OLLAMA_URL': url, 'OLLAMA_MODEL': modelo}
    novas = []
    processadas = set()
    for linha in original.splitlines(keepends=True):
        chave = linha.split('=', 1)[0].strip() if '=' in linha and not linha.lstrip().startswith('#') else None
        if chave in alteracoes:
            if chave not in processadas:
                novas.append(f'{chave}={alteracoes[chave]}' + quebra)
                processadas.add(chave)
        else:
            novas.append(linha)
    if novas and not novas[-1].endswith(('\r', '\n')):
        novas[-1] += quebra
    for chave in CHAVES:
        if chave not in processadas:
            novas.append(f'{chave}={alteracoes[chave]}' + quebra)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fd, temporario = tempfile.mkstemp(prefix='.env.ollama.', suffix='.tmp', dir=str(caminho.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as arquivo:
            arquivo.write(bom + ''.join(novas))
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, caminho)
    finally:
        Path(temporario).unlink(missing_ok=True)


def instrucoes(modelo=MODELO_PADRAO):
    print('Instale e abra o Ollama: https://ollama.com/download')
    print(f'Para baixar este modelo, execute: ollama pull {validar_modelo(modelo)}')
    print(f'Ou execute: configurar_ia_local.bat --baixar-modelo {modelo}')
    print('O download pode ocupar vários GB; a execução usa a RAM/CPU/GPU do seu PC.')
    print('Nenhum crédito de Gemini, OpenAI, Claude ou Exa é necessário para a IA local.')


def verificar(modelo=MODELO_PADRAO, url=URL_PADRAO):
    modelos = listar_modelos(url)
    encontrado = modelo_instalado(modelo, modelos)
    print('Serviço Ollama: respondeu à consulta local /api/tags.')
    print('Modelos instalados: ' + (', '.join(modelos[:20]) if modelos else 'nenhum.'))
    if encontrado:
        print(f'Modelo disponível no disco: {encontrado}. Geração de respostas ainda não testada.')
        return True
    print(f'O modelo {modelo} ainda não consta entre os instalados.')
    instrucoes(modelo)
    return False


def configurar_modelo(modelo, url=URL_PADRAO, caminho=ENV):
    modelo = validar_modelo(modelo)
    url = validar_url(url)
    encontrado = modelo_instalado(modelo, listar_modelos(url))
    if encontrado is None:
        raise FalhaConfiguracao(f'O modelo {modelo} não está instalado. Execute ollama pull {modelo} antes de ativá-lo.')
    atualizar_env(encontrado, url, caminho)
    return encontrado


def baixar_modelo(modelo, url=URL_PADRAO, caminho=ENV):
    """Download explícito com progresso; nunca usa shell nem instala programas."""
    modelo = validar_modelo(modelo)
    url = validar_url(url)
    encontrado = modelo_instalado(modelo, listar_modelos(url))
    if encontrado is None:
        executavel = shutil.which('ollama')
        if not executavel:
            raise FalhaConfiguracao('O comando ollama não foi encontrado. Instale e abra o Ollama e reabra este terminal.')
        print(f'Download solicitado: {modelo}. Pode ocupar vários GB; aguarde o progresso abaixo.', flush=True)
        ambiente = dict(os.environ)
        ambiente['OLLAMA_HOST'] = url
        try:
            resultado = subprocess.run([executavel, 'pull', modelo], env=ambiente,
                                       shell=False, timeout=TIMEOUT_DOWNLOAD, check=False)
        except subprocess.TimeoutExpired:
            raise FalhaConfiguracao(
                'O limite de espera de 30 minutos terminou. O serviço pode continuar o download. '
                'Execute --verificar depois; a configuração não foi alterada.'
            ) from None
        except OSError:
            raise FalhaConfiguracao('Não foi possível executar ollama pull. Confira a instalação do Ollama.') from None
        if resultado.returncode:
            raise FalhaConfiguracao('O download não foi concluído pelo comando ollama pull. A configuração não foi alterada.')
        encontrado = modelo_instalado(modelo, listar_modelos(url))
        if encontrado is None:
            raise FalhaConfiguracao('O comando terminou, mas o modelo não apareceu em /api/tags. A configuração não foi alterada.')
    atualizar_env(encontrado, url, caminho)
    return encontrado


def assistente(url=URL_PADRAO, caminho=ENV, modelo=MODELO_PADRAO):
    print('=== IA local com Ollama ===')
    instrucoes(modelo)
    modelos = listar_modelos(url)
    print('Modelos instalados: ' + (', '.join(modelos[:20]) if modelos else 'nenhum.'))
    if not modelos:
        return 2
    escolhido = input(f'Modelo instalado para ativar [{modelo}] (Enter mantém a opção): ').strip() or modelo
    encontrado = configurar_modelo(escolhido, url, caminho)
    print(f'IA local configurada: {encontrado}. Reinicie o MeuControlePC e teste uma pergunta.')
    print('Serviço e presença do modelo foram verificados; a geração de respostas ainda não foi testada.')
    return 0


def main(argv=None, caminho=ENV):
    parser = argparse.ArgumentParser(description=__doc__)
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument('--verificar', action='store_true', help='Consulta somente a lista de modelos instalados.')
    grupo.add_argument('--modelo', help='Ativa somente um modelo já instalado.')
    grupo.add_argument('--baixar-modelo', metavar='NOME', help='Baixa explicitamente um modelo e o ativa após verificar sua presença.')
    parser.add_argument('--url', help='Endereço HTTP local por IP literal; padrão http://127.0.0.1:11434.')
    args = parser.parse_args(argv)
    try:
        atuais = valores_env(caminho)
        url = validar_url(args.url or os.getenv('OLLAMA_URL') or atuais.get('OLLAMA_URL') or URL_PADRAO)
        modelo = validar_modelo(args.modelo or args.baixar_modelo or os.getenv('OLLAMA_MODEL') or atuais.get('OLLAMA_MODEL') or MODELO_PADRAO)
        if args.verificar:
            return 0 if verificar(modelo, url) else 2
        if args.modelo or args.baixar_modelo:
            acao = baixar_modelo if args.baixar_modelo else configurar_modelo
            encontrado = acao(modelo, url, caminho)
            print(f'IA local configurada: {encontrado}. Reinicie o MeuControlePC e teste uma pergunta.')
            print('Geração de respostas ainda não testada. Nenhuma API cloud foi consultada.')
            return 0
        return assistente(url, caminho, modelo)
    except (ValueError, FalhaConfiguracao) as erro:
        print('Configuração não concluída: ' + str(erro))
        return 2
    except OSError:
        print('Não foi possível acessar a configuração local. Confira permissões e espaço livre no disco.')
        return 2
    except (KeyboardInterrupt, EOFError):
        print('\nOperação interrompida. Confira --verificar antes de reiniciar o assistente.')
        return 2


if __name__ == '__main__':
    sys.exit(main())
