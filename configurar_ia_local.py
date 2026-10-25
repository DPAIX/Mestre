"""Configura modelos no serviço Ollama do próprio PC.

Instale e abra o Ollama em https://ollama.com/download. Este assistente não
instala programas nem baixa modelos sem --baixar-modelo explícito. Modelos
cloud são remotos e dependem da conexão, conta e limites do Ollama.
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
from caminhos_instalacao import arquivo_env

BASE = Path(__file__).resolve().parent
ENV = BASE / '.env'
URL_PADRAO = 'http://127.0.0.1:11434'
MODELO_PADRAO = 'qwen2.5:3b'
CHAVES = ('OLLAMA_HABILITADO', 'OLLAMA_URL', 'OLLAMA_MODEL','OLLAMA_PERFIL','OLLAMA_NUVEM_HABILITADA')
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


def modelo_em_nuvem(modelo):
    """Reconhece os sufixos cloud; aliases também exigem metadados do catálogo."""
    return isinstance(modelo, str) and modelo.lower().endswith(('-cloud', ':cloud'))


class SemRedirecionamento(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def listar_catalogo(url=URL_PADRAO):
    """Consulta /api/tags sem inferência; projeta nome, nuvem e tamanho opcional.

    Não retorna hosts remotos nem outros metadados fornecidos pelo serviço.
    Não segue redirecionamentos e nunca consulta uma URL remota do catálogo.
    """
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
        modelos = {}
        tamanhos = {}
        for item in itens:
            nome = item.get('name') or item.get('model')
            nome = validar_modelo(nome)
            detalhes = item.get('details')
            detalhes = detalhes if isinstance(detalhes, dict) else {}
            remoto = any(isinstance(dados.get(chave), str) and dados[chave].strip()
                         for dados in (item, detalhes) for chave in ('remote_model', 'remote_host'))
            nuvem = bool(modelo_em_nuvem(nome) or remoto)
            modelos[nome] = bool(modelos.get(nome, False) or nuvem)
            tamanho=item.get('size')
            if type(tamanho) is int and 0<tamanho<=1024**4:
                tamanhos[nome]=max(tamanhos.get(nome,0),tamanho)
        return [{'nome': nome, 'nuvem': nuvem,
                 **({'tamanho_bytes':tamanhos[nome]} if nome in tamanhos else {})}
                for nome, nuvem in modelos.items()]
    except (ValueError, UnicodeError, KeyError, TypeError, AttributeError):
        raise FalhaConfiguracao('O serviço local retornou uma lista de modelos inválida.') from None


def listar_modelos(url=URL_PADRAO):
    """Compatibilidade para configuração por nome e verificações existentes."""
    return [item['nome'] for item in listar_catalogo(url)]


def mostrar_modelo(modelo, url=URL_PADRAO):
    """Projeta metadados de /api/show; não retorna prompts nem gera respostas.

    contexto_maximo é a capacidade declarada pelo modelo, não a janela ativa
    do servidor ou do Claude Code. Nunca segue hosts remotos do documento.
    """
    modelo = validar_modelo(modelo)
    url = validar_url(url)
    cliente = urllib.request.build_opener(urllib.request.ProxyHandler({}), SemRedirecionamento())
    pedido = urllib.request.Request(
        url + '/api/show', json.dumps({'model': modelo, 'verbose': False}).encode('utf-8'),
        headers={'Accept': 'application/json', 'Content-Type': 'application/json'}, method='POST')
    try:
        with cliente.open(pedido, timeout=TIMEOUT_CONSULTA) as resposta:
            corpo = resposta.read(LIMITE_RESPOSTA + 1)
    except urllib.error.HTTPError as erro:
        with erro:
            codigo = erro.code
        if codigo == 404:
            raise FalhaConfiguracao(
                f'Ollama respondeu HTTP 404 para {modelo}. Confira a tag com --listar; '
                'o modelo pode estar ausente ou a rota indisponível.'
            ) from None
        raise FalhaConfiguracao(f'Ollama respondeu HTTP {codigo}; os metadados não foram verificados.') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise FalhaConfiguracao(
            'O serviço Ollama não respondeu no endereço local. Instale e abra o Ollama; '
            'se necessário, execute ollama serve em outro terminal.'
        ) from None
    if len(corpo) > LIMITE_RESPOSTA:
        raise FalhaConfiguracao('Os metadados do modelo excederam o tamanho permitido.')
    try:
        dados = json.loads(corpo.decode('utf-8'))
        if not isinstance(dados, dict) or 'error' in dados:
            raise ValueError
        if not any(chave in dados for chave in ('details', 'model_info', 'capabilities', 'remote_model', 'remote_host')):
            raise ValueError
        detalhes = dados.get('details', {})
        informacoes = dados.get('model_info', {})
        capacidades = dados.get('capabilities', [])
        if not isinstance(detalhes, dict) or not isinstance(informacoes, dict) or not isinstance(capacidades, list):
            raise ValueError
        from nucleo import redigir
        def texto(valor):
            return str(redigir(' '.join(valor.split())))[:100] if isinstance(valor, str) else ''
        limites = {chave: valor for chave, valor in informacoes.items()
                   if isinstance(chave, str) and chave.endswith('.context_length')
                   and isinstance(valor, int) and not isinstance(valor, bool) and 1 <= valor <= 10_000_000}
        arquitetura = informacoes.get('general.architecture')
        contexto = limites.get(arquitetura + '.context_length') if isinstance(arquitetura, str) else None
        if contexto is None and limites:
            contexto = min(limites.values())
        lista_capacidades = []
        for capacidade in capacidades[:20]:
            if isinstance(capacidade, str):
                nome = texto(capacidade)
                if nome and nome not in lista_capacidades:
                    lista_capacidades.append(nome)
        remoto = any(isinstance(item.get(chave), str) and item[chave].strip()
                     for item in (dados, detalhes) for chave in ('remote_model', 'remote_host'))
        return {'nome': modelo, 'familia': texto(detalhes.get('family') or arquitetura),
                'parametros': texto(detalhes.get('parameter_size')),
                'quantizacao': texto(detalhes.get('quantization_level')),
                'capacidades': lista_capacidades, 'contexto_maximo': contexto,
                'nuvem': bool(modelo_em_nuvem(modelo) or remoto)}
    except (ValueError, UnicodeError, KeyError, TypeError, AttributeError):
        raise FalhaConfiguracao('O serviço local retornou metadados de modelo inválidos.') from None


def modelo_instalado(modelo, modelos):
    validar_modelo(modelo)
    candidatos = (modelo, modelo + ':latest') if ':' not in modelo else (modelo,)
    return next((nome for nome in candidatos if nome in modelos), None)


def valores_env(caminho=None):
    """Lê somente opções de Ollama; nunca imprime conteúdo do .env."""
    caminho = Path(caminho) if caminho is not None else arquivo_env(BASE)
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


def atualizar_env(modelo, url=URL_PADRAO, caminho=None,*,perfil=None):
    """Substitui só opções locais selecionadas, preservando demais linhas e segredos."""
    modelo = validar_modelo(modelo)
    url = validar_url(url)
    if perfil is not None and perfil not in ('cpu','padrao'):raise ValueError('Perfil Ollama inválido.')
    alteracoes = {'OLLAMA_HABILITADO': '1', 'OLLAMA_URL': url, 'OLLAMA_MODEL': modelo}
    if perfil is not None:alteracoes['OLLAMA_PERFIL']=perfil
    _atualizar_opcoes_env(alteracoes,caminho)


def configurar_nuvem(ativo,caminho=None):
    """Autoriza nuvem no perfil CPU sem alterar modelo, perfil ou outras opções."""
    if type(ativo) is not bool:raise ValueError('A autorização de nuvem deve ser booleana.')
    _atualizar_opcoes_env({'OLLAMA_NUVEM_HABILITADA':'1' if ativo else '0'},caminho)


def _atualizar_opcoes_env(alteracoes,caminho=None):
    # Um único escritor atômico evita implementações de persistência divergentes.
    caminho = Path(caminho) if caminho is not None else arquivo_env(BASE)
    bruto = caminho.read_bytes() if caminho.exists() else b''
    bom = '\ufeff' if bruto.startswith(b'\xef\xbb\xbf') else ''
    original = bruto.decode('utf-8-sig')
    quebra = '\r\n' if '\r\n' in original else '\n'
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
    for chave in alteracoes:
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


def configurar_perfil(perfil,url=URL_PADRAO,caminho=None):
    if perfil not in ('cpu','padrao'):raise ValueError('Perfil Ollama inválido.')
    url=validar_url(url)
    atuais=valores_env(caminho)
    modelo='llama3.2:latest' if perfil=='cpu' else atuais.get('OLLAMA_MODEL') or os.getenv('OLLAMA_MODEL') or MODELO_PADRAO
    modelo=validar_modelo(modelo)
    catalogo=listar_catalogo(url)
    nomes=[m['nome'] for m in catalogo if perfil!='cpu' or not m['nuvem']]
    encontrado=modelo_instalado(modelo,nomes)
    if encontrado is None:
        raise FalhaConfiguracao('Perfil não configurado: o modelo '+modelo+' não foi confirmado no catálogo'+(' local.' if perfil=='cpu' else '.'))
    atualizar_env(encontrado,url,caminho,perfil=perfil)
    return encontrado


def instrucoes(modelo=MODELO_PADRAO):
    print('Instale e abra o Ollama: https://ollama.com/download')
    print(f'Para registrar ou baixar este modelo, execute: ollama pull {validar_modelo(modelo)}')
    print(f'Ou execute: configurar_ia_local.bat --baixar-modelo {modelo}')
    if modelo_em_nuvem(modelo):
        print('Este é um modelo cloud: as respostas dependem de internet, conta e cota do Ollama.')
    else:
        print('Para modelos locais, o download pode ocupar vários GB e a execução usa a RAM/CPU/GPU do PC.')
        print('Modelos locais não usam créditos de Gemini, OpenAI, Claude ou Exa.')
    print('Use configurar_ia_local.bat --listar para ver os modelos já registrados, sem baixar outro.')


def mostrar_catalogo(catalogo):
    print('Modelos registrados no serviço Ollama:')
    for item in catalogo[:100]:
        tipo = 'cloud — internet, conta e cota do Ollama' if item['nuvem'] else 'local'
        print(f'  {item["nome"]} — {tipo}')
    if not catalogo:
        print('  nenhum.')
    print('A presença no catálogo não testa a geração nem a disponibilidade da conta cloud.')


def verificar(modelo=MODELO_PADRAO, url=URL_PADRAO):
    catalogo = listar_catalogo(url)
    modelos = [item['nome'] for item in catalogo]
    encontrado = modelo_instalado(modelo, modelos)
    print('Serviço Ollama: respondeu à consulta local /api/tags.')
    mostrar_catalogo(catalogo)
    if encontrado:
        item = next(item for item in catalogo if item['nome'] == encontrado)
        tipo = 'cloud, com execução remota' if item['nuvem'] else 'local'
        print(f'Modelo registrado: {encontrado} ({tipo}). Geração de respostas ainda não testada.')
        return True
    print(f'O modelo {modelo} ainda não consta no catálogo.')
    instrucoes(modelo)
    return False


def configurar_modelo(modelo, url=URL_PADRAO, caminho=None):
    caminho = Path(caminho) if caminho is not None else arquivo_env(BASE)
    modelo = validar_modelo(modelo)
    url = validar_url(url)
    encontrado = modelo_instalado(modelo, listar_modelos(url))
    if encontrado is None:
        raise FalhaConfiguracao(f'O modelo {modelo} não consta no catálogo. Execute ollama pull {modelo} antes de ativá-lo.')
    atualizar_env(encontrado, url, caminho)
    return encontrado


def usar_existente(url=URL_PADRAO, caminho=None, preferido=MODELO_PADRAO):
    """Reaproveita um modelo local sem pull; nunca escolhe cloud automaticamente."""
    caminho = Path(caminho) if caminho is not None else arquivo_env(BASE)
    url = validar_url(url)
    catalogo = listar_catalogo(url)
    locais = [item['nome'] for item in catalogo if not item['nuvem']]
    if not locais:
        mostrar_catalogo(catalogo)
        print('Nenhum modelo local foi encontrado. Nenhuma configuração foi alterada.')
        if catalogo:
            print('Para selecionar cloud explicitamente, use --modelo NOME; isso depende da conta Ollama.')
        return None
    escolhido = modelo_instalado(preferido, locais) or modelo_instalado(MODELO_PADRAO, locais) or locais[0]
    atualizar_env(escolhido, url, caminho)
    return escolhido


def baixar_modelo(modelo, url=URL_PADRAO, caminho=None):
    """Download explícito com progresso; nunca usa shell nem instala programas."""
    caminho = Path(caminho) if caminho is not None else arquivo_env(BASE)
    modelo = validar_modelo(modelo)
    url = validar_url(url)
    encontrado = modelo_instalado(modelo, listar_modelos(url))
    if encontrado is None:
        executavel = shutil.which('ollama')
        if not executavel:
            raise FalhaConfiguracao('O comando ollama não foi encontrado. Instale e abra o Ollama e reabra este terminal.')
        if modelo_em_nuvem(modelo):
            print(f'Registro cloud solicitado: {modelo}. O uso depende de internet, conta e cota do Ollama.', flush=True)
        else:
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


def assistente(url=URL_PADRAO, caminho=None, modelo=MODELO_PADRAO):
    caminho = Path(caminho) if caminho is not None else arquivo_env(BASE)
    print('=== Modelos Ollama ===')
    catalogo = listar_catalogo(url)
    modelos = [item['nome'] for item in catalogo]
    mostrar_catalogo(catalogo)
    if not modelos:
        instrucoes(modelo)
        return 2
    locais = [item['nome'] for item in catalogo if not item['nuvem']]
    padrao = modelo_instalado(modelo, locais) or modelo_instalado(MODELO_PADRAO, locais) or (locais[0] if locais else '')
    if not padrao:
        print('Só há modelos cloud. Digite um nome explicitamente para selecionar; Enter cancela.')
    escolhido = input(f'Modelo para ativar [{padrao}] (Enter aceita o modelo local): ').strip() or padrao
    if not escolhido:
        return 2
    encontrado = configurar_modelo(escolhido, url, caminho)
    print(f'Modelo Ollama configurado: {encontrado}. Reinicie o MeuControlePC e teste uma pergunta.')
    print('Serviço e presença do modelo foram verificados; a geração de respostas ainda não foi testada.')
    return 0


def main(argv=None, caminho=None):
    parser = argparse.ArgumentParser(description=__doc__)
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument('--listar', action='store_true', help='Lista modelos locais/cloud registrados, sem alterar configuração.')
    grupo.add_argument('--detalhes', metavar='NOME', help='Lê capacidades e contexto máximo do modelo, sem inferência nem alteração.')
    grupo.add_argument('--usar-existente', action='store_true', help='Ativa um modelo local já registrado, sem download; retorna 3 se nenhum existir.')
    grupo.add_argument('--verificar', action='store_true', help='Verifica a presença do modelo configurado no catálogo, sem inferência.')
    grupo.add_argument('--modelo', help='Ativa somente um modelo já registrado no catálogo local ou cloud.')
    grupo.add_argument('--baixar-modelo', metavar='NOME', help='Registra ou baixa explicitamente um modelo e o ativa após verificar sua presença.')
    grupo.add_argument('--perfil-cpu',action='store_true',help='Ativa Llama local em CPU com contexto pequeno; sem geração ou download.')
    grupo.add_argument('--perfil-padrao',action='store_true',help='Volta às opções padrão de execução do Ollama; mantém o modelo configurado.')
    parser.add_argument('--url', help='Endereço HTTP local por IP literal; padrão http://127.0.0.1:11434.')
    args = parser.parse_args(argv)
    try:
        caminho = Path(caminho) if caminho is not None else arquivo_env(BASE)
        atuais = valores_env(caminho)
        url = validar_url(args.url or os.getenv('OLLAMA_URL') or atuais.get('OLLAMA_URL') or URL_PADRAO)
        if args.perfil_cpu or args.perfil_padrao:
            perfil='cpu' if args.perfil_cpu else 'padrao'
            encontrado=configurar_perfil(perfil,url,caminho)
            print('Perfil Ollama salvo: '+perfil+'; modelo: '+encontrado+'. Nenhuma geração ou download executado.')
            print('Reinicie o assistente. Para o perfil CPU, use /chat equipe off e /chat modelo padrao nesta conversa.')
            return 0
        if args.listar:
            mostrar_catalogo(listar_catalogo(url))
            return 0
        if args.detalhes:
            detalhes = mostrar_modelo(args.detalhes, url)
            print(json.dumps(detalhes, ensure_ascii=False, indent=2))
            print('Contexto máximo é a capacidade declarada; não representa a janela ativa nem um teste de geração.')
            if detalhes['nuvem']:
                print('Modelo cloud: as respostas dependem de internet, conta e cota do Ollama.')
            return 0
        modelo = validar_modelo(args.modelo or args.baixar_modelo or os.getenv('OLLAMA_MODEL') or atuais.get('OLLAMA_MODEL') or MODELO_PADRAO)
        if args.usar_existente:
            encontrado = usar_existente(url, caminho, modelo)
            if encontrado is None:
                return 3
            print(f'Modelo local existente ativado: {encontrado}. Nenhum modelo adicional foi baixado.')
            print('Reinicie o MeuControlePC e teste uma pergunta. Geração de respostas ainda não testada.')
            return 0
        if args.verificar:
            return 0 if verificar(modelo, url) else 2
        if args.modelo or args.baixar_modelo:
            acao = baixar_modelo if args.baixar_modelo else configurar_modelo
            encontrado = acao(modelo, url, caminho)
            print(f'Modelo Ollama configurado: {encontrado}. Reinicie o MeuControlePC e teste uma pergunta.')
            print('Geração de respostas ainda não testada. Modelos cloud precisam de internet, conta e cota do Ollama.')
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
