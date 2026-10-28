"""Baixa e testa uma alternativa textual do 27B, sem remover o original.

Uso explícito no Windows. Somente uma geração curta concluída e válida permite
ativar a alternativa. Configuração e histórico não entram no download ou teste.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from alternativa_27b import (
    DIGEST_MANIFESTO, MODELO_LEVE, MODELO_ORIGINAL, TAMANHO_BYTES,
    conferir_alternativa,
)
import configurar_ia_local as configurar
from instancia_assistente import InstanciaAtiva, instancia_unica

TIMEOUT_DOWNLOAD = 30 * 60
TIMEOUT_TESTE = 90
LIMITE_RESPOSTA = 2_000_000
APLICADAS = {'OLLAMA_PERFIL': 'equilibrado', 'OLLAMA_27B_LEVE': '1'}
AMBIENTE_PUBLICO = frozenset({
    'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP',
    'USERPROFILE', 'HOME', 'LOCALAPPDATA', 'APPDATA', 'HOMEDRIVE', 'HOMEPATH',
})


class FalhaPreparacao(RuntimeError):
    """Falha controlada sem corpo do serviço, configuração ou credenciais."""


def _caminho_existente(valor, *, diretorio=False):
    caminho = Path(valor)
    if not caminho.is_absolute():
        raise FalhaPreparacao('Use caminhos absolutos para a configuração e os dados externos.')
    for parte in (caminho, *caminho.parents):
        if parte.is_symlink() or (parte.exists() and
                getattr(parte.lstat(), 'st_file_attributes', 0) & 0x400):
            raise FalhaPreparacao('Os caminhos da preparação não podem seguir links ou junctions.')
    if not (caminho.is_dir() if diretorio else caminho.is_file()):
        raise FalhaPreparacao('A configuração e a pasta de dados externos precisam existir. Nada foi criado.')
    return caminho


def _consultar(url, rota, dados=None, *, timeout=4):
    """HTTP somente no loopback validado, sem proxy ou redirecionamentos."""
    url = configurar.validar_url(url)
    cliente = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), configurar.SemRedirecionamento())
    corpo = None if dados is None else json.dumps(dados).encode('utf-8')
    pedido = urllib.request.Request(url + rota, data=corpo,
        headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
        method='GET' if dados is None else 'POST')
    try:
        with cliente.open(pedido, timeout=timeout) as resposta:
            bruto = resposta.read(LIMITE_RESPOSTA + 1)
    except urllib.error.HTTPError as erro:
        with erro:
            codigo = erro.code
        raise FalhaPreparacao('O Ollama respondeu HTTP ' + str(codigo) +
            '. A operação não foi repetida e a configuração permanece.') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise FalhaPreparacao(
            'A consulta local não concluiu. A operação pode continuar no Ollama; '
            'nenhuma nova tentativa ou alteração de configuração foi feita.') from None
    try:
        if len(bruto) > LIMITE_RESPOSTA:
            raise ValueError
        resultado = json.loads(bruto.decode('utf-8'))
        if not isinstance(resultado, dict) or 'error' in resultado:
            raise ValueError
        return resultado
    except (ValueError, UnicodeError):
        raise FalhaPreparacao('O Ollama não devolveu uma resposta local válida. A configuração permanece.') from None


def _conferir_ocioso(url):
    modelos = _consultar(url, '/api/ps').get('models')
    if not isinstance(modelos, list):
        raise FalhaPreparacao('Não foi possível conferir os modelos ativos no Ollama.')
    if modelos:
        raise FalhaPreparacao(
            'Há modelos carregados no Ollama. Aguarde as consultas e a liberação '
            'desses modelos antes de tentar novamente; nenhum processo foi encerrado.')


def _baixar(url):
    executavel = shutil.which('ollama')
    if not executavel:
        candidato = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Ollama' / 'ollama.exe'
        if candidato.is_absolute() and candidato.is_file():
            executavel = str(candidato)
    if not executavel:
        raise FalhaPreparacao('O executável do Ollama não foi encontrado. Abra o Ollama instalado e tente novamente.')
    ambiente = {k: v for k, v in os.environ.items() if k.upper() in AMBIENTE_PUBLICO}
    import instalacao_em_f as politica
    if politica.ativo():
        ambiente.update(politica.ambiente())
        perfil=politica.raiz()/'perfil_ollama'
        ambiente.update({'USERPROFILE':str(perfil),'LOCALAPPDATA':str(perfil/'AppData'/'Local'),
                         'APPDATA':str(perfil/'AppData'/'Roaming')})
    ambiente['OLLAMA_HOST'] = configurar.validar_url(url)
    print('Baixando ' + MODELO_LEVE + '; aproximadamente '
          f'{TAMANHO_BYTES / 1024**3:.2f} GiB. Aguarde o progresso do Ollama.', flush=True)
    try:
        resultado = subprocess.run([executavel, 'pull', MODELO_LEVE],
            env=ambiente, shell=False, check=False, timeout=TIMEOUT_DOWNLOAD)
    except subprocess.TimeoutExpired:
        raise FalhaPreparacao(
            'O download excedeu 30 minutos e pode continuar no serviço. '
            'Nenhum teste ou alteração de configuração foi enviado.') from None
    except OSError:
        raise FalhaPreparacao('Não foi possível iniciar o download pelo Ollama instalado.') from None
    if resultado.returncode:
        raise FalhaPreparacao('O download não foi concluído. A configuração permanece e o modelo original foi preservado.')


def _opcoes(valores):
    resultado = {'OLLAMA_PERFIL': valores.get('OLLAMA_PERFIL', 'padrao'),
                 'OLLAMA_27B_LEVE': valores.get('OLLAMA_27B_LEVE', '0')}
    if resultado['OLLAMA_PERFIL'] not in ('cpu', 'padrao', 'equilibrado') or resultado['OLLAMA_27B_LEVE'] not in ('0', '1'):
        raise FalhaPreparacao('As opções atuais de perfil ou alternativa são inválidas. A configuração permanece.')
    return resultado


def _prazo_teste(valores):
    """Teto igual ou menor que o orçamento das próximas consultas da equipe.

    Replica somente o cálculo público de limites, sem importar/instanciar o
    roteador, alterar o ambiente ou consultar estado de uso. Valores inválidos
    seguem os mesmos padrões e limites finitos da implementação nativa.
    """
    def segundos(nome, padrao, maximo):
        try:
            valor = float(valores.get(nome, str(padrao)))
        except (TypeError, ValueError, OverflowError):
            valor = padrao
        if not math.isfinite(valor):
            valor = padrao
        return max(5, min(maximo, valor))
    politica = valores.get('OLLAMA_EQUIPE_ORCAMENTO', 'adaptativo').strip().casefold()
    if politica not in ('adaptativo', 'legado'):
        raise FalhaPreparacao('A política de orçamento da equipe é inválida. A configuração permanece.')
    individual = segundos('OLLAMA_TIMEOUT', 90, 120)
    por_modelo = segundos('OLLAMA_EQUIPE_TIMEOUT_MODELO', 30, 120)
    rodada = segundos('OLLAMA_EQUIPE_TIMEOUT', 90, 900)
    if politica == 'adaptativo' and por_modelo == 30 and rodada == 90:
        por_modelo = individual
        # A rodada adaptativa nativa reserva várias consultas; não limita um
        # único teste além do prazo individual já conferido.
        rodada = individual
    elif politica == 'legado':
        rodada = min(180, rodada)
    return float(min(TIMEOUT_TESTE, individual, por_modelo, rodada))


def _salvar_json(caminho, valor):
    if caminho.is_symlink() or caminho.parent.is_symlink():
        raise FalhaPreparacao('O backup da preparação não pode seguir links.')
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fd, nome = tempfile.mkstemp(prefix='.27b_leve.', suffix='.tmp', dir=str(caminho.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as arquivo:
            json.dump(valor, arquivo, ensure_ascii=False, allow_nan=False)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(nome, caminho)
    finally:
        Path(nome).unlink(missing_ok=True)


def _ler_backup(caminho):
    try:
        if caminho.is_symlink() or caminho.stat().st_size > 4000:
            raise ValueError
        valor = json.loads(caminho.read_text(encoding='utf-8'))
        if (not isinstance(valor, dict) or set(valor) != {'versao', 'modelo', 'digest', 'anteriores', 'aplicadas'}
                or type(valor['versao']) is not int or valor['versao'] != 1 or valor['modelo'] != MODELO_LEVE
                or valor['digest'] != DIGEST_MANIFESTO or valor['aplicadas'] != APLICADAS
                or not isinstance(valor['anteriores'], dict)
                or set(valor['anteriores']) != set(APLICADAS)
                or _opcoes(valor['anteriores']) != valor['anteriores']):
            raise ValueError
        return valor
    except (OSError, ValueError, TypeError):
        raise FalhaPreparacao('O backup público desta preparação não foi encontrado ou é inválido. Nenhuma opção foi alterada.') from None


def _restaurar(caminho_env, backup):
    estado = _ler_backup(backup)
    atuais = _opcoes(configurar.valores_env(caminho_env))
    if atuais == estado['anteriores']:
        return {'estado': 'ja_restaurado', 'modelo': MODELO_LEVE}
    if atuais != estado['aplicadas']:
        raise FalhaPreparacao('As opções foram alteradas depois da preparação. A restauração preservou essas alterações posteriores.')
    configurar._atualizar_opcoes_env(estado['anteriores'], caminho_env)
    if _opcoes(configurar.valores_env(caminho_env)) != estado['anteriores']:
        raise FalhaPreparacao('Não foi possível confirmar a restauração das opções públicas.')
    return {'estado': 'restaurado', 'modelo': MODELO_LEVE}


def preparar(caminho_env, dados, *, autorizado=False, restaurar=False):
    """Download/teste explícitos ou reversão das duas opções públicas.

    As funções são testáveis em Linux com serviços simulados; o iniciador de
    uso real exige Windows. Nenhum modelo, dado ou conversa é removido.
    """
    if autorizado is not True or not isinstance(restaurar, bool):
        raise FalhaPreparacao('Escolha explicitamente baixar e testar ou restaurar a preparação.')
    caminho_env = _caminho_existente(caminho_env)
    dados = _caminho_existente(dados, diretorio=True)
    backup = caminho_env.parent / 'preparacao' / '27b_leve.json'
    # Conferir todos os ancestrais do destino antes de ler ou criar o backup.
    for parte in (backup, *backup.parents):
        if parte.is_symlink() or (parte.exists() and getattr(parte.lstat(), 'st_file_attributes', 0) & 0x400):
            raise FalhaPreparacao('O backup da preparação não pode seguir links ou junctions.')
    try:
        with instancia_unica(dados):
            if restaurar:
                return _restaurar(caminho_env, backup)
            iniciais = configurar.valores_env(caminho_env)
            anteriores = _opcoes(iniciais)
            if iniciais.get('OLLAMA_HABILITADO') != '1':
                raise FalhaPreparacao('Habilite o Ollama pela preparação do assistente antes de preparar a alternativa.')
            import instalacao_em_f as politica
            if politica.ativo():
                # O cliente não escolhe o disco de um daemon já existente.
                from iniciar_servicos_locais import garantir_ollama_em_f
                os.environ['MEUCONTROLEPC_ENV']=str(caminho_env)
                confirmado=garantir_ollama_em_f(iniciais.get('OLLAMA_URL',configurar.URL_PADRAO))
                if not confirmado['ok']:raise FalhaPreparacao(confirmado['mensagem'])
                iniciais=configurar.valores_env(caminho_env)
            prazo_teste = _prazo_teste(iniciais)
            url = configurar.validar_url(iniciais.get('OLLAMA_URL', configurar.URL_PADRAO))
            _conferir_ocioso(url)
            catalogo = configurar.listar_catalogo(url)
            if not any(item.get('nome') == MODELO_LEVE for item in catalogo):
                _baixar(url)
                catalogo = configurar.listar_catalogo(url)
            conferir_alternativa(catalogo)
            metadados = configurar.mostrar_modelo(MODELO_LEVE, url)
            if (metadados.get('nuvem') is not False
                    or metadados.get('familia') != 'qwen35'
                    or metadados.get('quantizacao') != 'IQ3_XXS'):
                raise FalhaPreparacao('A quantização local não corresponde aos metadados conferidos. A configuração permanece.')
            # Outro aplicativo pode ter começado uma consulta durante o pull.
            _conferir_ocioso(url)
            print('Conferindo uma resposta curta, sem histórico, com CPU/GPU automática '
                  f'e contexto reduzido; prazo de até {prazo_teste:g} s...', flush=True)
            inicio = time.monotonic()
            resposta = _consultar(url, '/api/chat', {
                'model': MODELO_LEVE, 'stream': False, 'think': False, 'keep_alive': 0,
                'options': {'num_ctx': 1024, 'num_predict': 64},
                'messages': [{'role': 'user', 'content': 'Responda somente OK.'}],
            }, timeout=prazo_teste)
            mensagem = resposta.get('message')
            if (resposta.get('done') is not True or resposta.get('done_reason') == 'length'
                    or not isinstance(mensagem, dict) or mensagem.get('role') != 'assistant'
                    or mensagem.get('tool_calls') or not isinstance(mensagem.get('content'), str)
                    or mensagem['content'].strip().rstrip('.!').strip().casefold() != 'ok'):
                raise FalhaPreparacao('O teste não produziu OK com conclusão confirmada. A alternativa não foi ativada; nenhuma nova tentativa foi enviada.')
            duracao = round(max(0., time.monotonic() - inicio), 1)
            # A tag pode ter sido atualizada por outro cliente durante o teste.
            # Uma resposta válida não autoriza selecionar outro artefato.
            conferir_alternativa(configurar.listar_catalogo(url))
            if configurar.valores_env(caminho_env) != iniciais:
                raise FalhaPreparacao('A configuração mudou durante o teste. Essas alterações foram preservadas e a alternativa não foi ativada.')
            estado = {'versao': 1, 'modelo': MODELO_LEVE, 'digest': DIGEST_MANIFESTO,
                      'anteriores': anteriores, 'aplicadas': dict(APLICADAS)}
            if backup.exists() and anteriores == APLICADAS:
                # Uma nova conferência não destrói o primeiro ponto de reversão.
                estado = _ler_backup(backup)
            else:
                _salvar_json(backup, estado)
            configurar._atualizar_opcoes_env(APLICADAS, caminho_env)
            if _opcoes(configurar.valores_env(caminho_env)) != APLICADAS:
                raise FalhaPreparacao('O teste concluiu, mas não foi possível confirmar a ativação. O backup público foi mantido.')
            return {'estado': 'configurado', 'modelo': MODELO_LEVE, 'duracao_s': duracao}
    except InstanciaAtiva:
        raise FalhaPreparacao('Encerre a janela do assistente antes desta preparação. Nenhum processo foi encerrado.') from None
    except (configurar.FalhaConfiguracao, ValueError, OSError):
        raise FalhaPreparacao('A preparação local não concluiu. Confira serviço, espaço e acesso aos arquivos; configuração, modelo original e dados foram preservados.') from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument('--baixar-e-testar', action='store_true')
    grupo.add_argument('--restaurar', action='store_true')
    parser.add_argument('--env', help='Configuração externa existente; não será exibida.')
    parser.add_argument('--dados', help='Pasta externa de dados existente.')
    args = parser.parse_args(argv)
    if sys.platform != 'win32':
        print('Esta preparação de uso real está disponível somente no Windows.')
        return 2
    try:
        from preparacao_autonoma import caminhos
        contexto = caminhos(arquivo_env=args.env, dados=args.dados)
        if not args.restaurar:
            print('Alternativa comunitária IQ3 para texto e áudio transcrito, sem visão. '
                  'O modelo ' + MODELO_ORIGINAL + ' permanece instalado.', flush=True)
        resultado = preparar(contexto.arquivo_env, contexto.dados,
                             autorizado=True, restaurar=args.restaurar)
        print('PREPARACAO_27B=' + resultado['estado'], flush=True)
        if resultado['estado'] == 'configurado':
            print('O modelo respondeu ao teste em ' + str(resultado['duracao_s']) + ' s. '
                  'Isso confirma esta consulta; uso da VRAM e desempenho futuro não foram medidos. '
                  'Abra o assistente novamente para usar a versão leve na equipe.', flush=True)
        else:
            print('Opções anteriores restauradas. Os dois modelos e os dados foram preservados. Abra o assistente novamente.', flush=True)
        return 0
    except FalhaPreparacao as erro:
        print('PREPARACAO_27B=nao_concluida\n' + str(erro), flush=True)
        return 2
    except (ValueError, OSError):
        print('PREPARACAO_27B=nao_concluida\nConfira os caminhos externos e as permissões locais.', flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
