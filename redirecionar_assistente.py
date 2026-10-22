"""Executa o código atualizado usando configuração e dados de outra pasta.

Este bootstrap usa apenas stdlib e metadados de caminhos. Não importa nucleo,
não lê o .env e não move, copia ou apaga dados. --verificar nunca inicia filhos.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

CODIGO_PADRAO = r'C:\Users\Mestre\Documents\GitHub\Mestre'
ENV_PADRAO = r'F:\MeuControlePC_v2\.env'
FONTES_NECESSARIAS = ('assistente_pc.py', 'nucleo.py', 'caminhos_instalacao.py')
MODOS = {
    'start': ('assistente_pc.py', ()),
    'painel': ('assistente_pc.py', ('--somente-painel',)),
    'diagnostico': ('assistente_pc.py', ('--diagnostico',)),
    'telegram': ('configurar_telegram.py', ()),
    'ollama': ('configurar_ia_local.py', ()),
    'google': ('autorizar_google.py', ()),
    'inicio-automatico': ('startup_windows.py', ()),
}


class FalhaRedirecionamento(RuntimeError):
    """Erro de configuração sem ler ou expor credenciais."""


def _absoluto(valor, nome):
    if not isinstance(valor, (str, os.PathLike)):
        raise FalhaRedirecionamento(nome + ' deve ser um caminho absoluto.')
    texto = os.fspath(valor)
    if not texto or any(ord(c) < 32 for c in texto):
        raise FalhaRedirecionamento(nome + ' contém um caminho inválido.')
    caminho = Path(texto)
    if not caminho.is_absolute():
        raise FalhaRedirecionamento(nome + ' deve ser absoluto; informe o caminho completo.')
    return caminho.resolve()


def _fora_do_codigo(caminho, codigo, nome):
    if caminho.is_relative_to(codigo):
        raise FalhaRedirecionamento(nome + ' deve ficar fora da pasta do código. Escolha a configuração/dados da instalação externa.')


def _argumentos_permitidos(modo, argumentos):
    if not isinstance(argumentos, (list, tuple)) or any(
            not isinstance(a, str) or not a or '\x00' in a for a in argumentos):
        raise FalhaRedirecionamento('Argumentos de execução inválidos.')
    argumentos = list(argumentos)
    if argumentos[:1] == ['--']:
        argumentos.pop(0)
    if '--verificar' in argumentos:
        raise FalhaRedirecionamento('--verificar pertence ao redirecionador e não pode ser encaminhado ao filho.')
    if modo == 'start':
        if argumentos not in ([], ['--somente-painel'], ['--diagnostico']):
            raise FalhaRedirecionamento('Use start, painel ou diagnostico; argumentos de código/migração não são encaminhados.')
    elif modo in ('painel', 'diagnostico', 'telegram'):
        if argumentos:
            raise FalhaRedirecionamento('Este modo não recebe argumentos adicionais. --verificar apenas confere o redirecionamento.')
    elif modo == 'google':
        if len(argumentos) > 1 or any(a.startswith('-') for a in argumentos):
            raise FalhaRedirecionamento('google recebe somente o caminho opcional do JSON OAuth; não envie o conteúdo do arquivo.')
    elif modo == 'inicio-automatico':
        if argumentos not in (['--ativar'], ['--desativar']):
            raise FalhaRedirecionamento('Use inicio-automatico --ativar ou --desativar explicitamente.')
    elif modo == 'ollama':
        opcoes = {'--listar': 0, '--detalhes': 1, '--usar-existente': 0,
                  '--modelo': 1, '--baixar-modelo': 1, '--url': 1}
        quantidade_acoes = 0
        indice = 0
        while indice < len(argumentos):
            opcao = argumentos[indice]
            if opcao not in opcoes:
                raise FalhaRedirecionamento('Opção Ollama não permitida. Use --listar, --detalhes NOME, --modelo NOME ou outra opção documentada.')
            if opcao != '--url':
                quantidade_acoes += 1
            espera_valor = opcoes[opcao]
            if espera_valor:
                if indice + 1 >= len(argumentos) or argumentos[indice + 1].startswith('-'):
                    raise FalhaRedirecionamento('Falta um valor para a opção Ollama.')
                indice += 1
            indice += 1
        if quantidade_acoes > 1:
            raise FalhaRedirecionamento('Selecione apenas uma operação Ollama por execução.')
    return argumentos


def plano_execucao(codigo=CODIGO_PADRAO, arquivo_env=ENV_PADRAO, dados=None,
                   python=None, modo='start', argumentos=(), ambiente=None):
    """Planeja uma execução validada sem importar o app nem abrir arquivos privados.

    O retorno contém comando/cwd/ambiente para subprocess.run e caminhos para
    diagnóstico. A função não cria diretórios nem inicia processos.
    """
    if modo not in MODOS:
        raise FalhaRedirecionamento('Modo de execução não permitido.')
    codigo = _absoluto(codigo, 'Código')
    arquivo_env = _absoluto(arquivo_env, 'Arquivo .env')
    if not codigo.is_dir():
        raise FalhaRedirecionamento('A pasta do código atualizado não foi encontrada. Confira --codigo.')
    for nome in FONTES_NECESSARIAS:
        fonte = codigo / nome
        if not fonte.is_file() or not fonte.resolve().is_relative_to(codigo):
            raise FalhaRedirecionamento('A pasta de código está incompleta ou é antiga: falta ' + nome + '. Atualize o código antes de iniciar.')
    _fora_do_codigo(arquivo_env, codigo, 'O arquivo .env')
    if not arquivo_env.is_file():
        raise FalhaRedirecionamento('O arquivo .env externo não foi encontrado. Confira --env; nenhum arquivo foi criado.')
    explicito = dados is not None
    pasta_dados = _absoluto(dados if explicito else arquivo_env.parent / 'dados', 'Dados')
    _fora_do_codigo(pasta_dados, codigo, 'A pasta de dados')
    if pasta_dados.exists() and not pasta_dados.is_dir():
        raise FalhaRedirecionamento('O caminho de dados aponta para um arquivo; escolha uma pasta externa.')
    if explicito and not pasta_dados.is_dir():
        raise FalhaRedirecionamento('A pasta indicada em --dados não existe. Selecione os dados externos existentes ou faça a cópia manual antes de iniciar.')
    # Checagem conservadora só de metadados: não enumerar/ler dados privados.
    if not explicito and not pasta_dados.exists() and (codigo / 'dados').exists():
        raise FalhaRedirecionamento(
            'O destino externo de dados ainda não existe e há uma pasta dados no código. '
            'Para não iniciar vazio, escolha uma pasta externa existente com --dados ou copie manualmente os dados antes de iniciar. Nada foi migrado ou apagado.')
    script_nome, fixos = MODOS[modo]
    script = codigo / script_nome
    if not script.is_file() or not script.resolve().is_relative_to(codigo):
        raise FalhaRedirecionamento('O script deste modo não foi encontrado no código atualizado: ' + script_nome + '.')
    adicionais = _argumentos_permitidos(modo, argumentos)
    if python is not None:
        executavel = _absoluto(python, 'Python')
        if not executavel.is_file():
            raise FalhaRedirecionamento('O interpretador informado em --python não foi encontrado.')
    else:
        candidatos = (codigo / '.venv' / 'Scripts' / 'python.exe',
                      arquivo_env.parent / '.venv' / 'Scripts' / 'python.exe')
        executavel = next((p.resolve() for p in candidatos if p.is_file()), None)
        if executavel is None:
            if sys.version_info < (3, 11):
                raise FalhaRedirecionamento('Use Python 3.11 ou superior ou informe --python com o interpretador do ambiente existente.')
            executavel = _absoluto(sys.executable, 'Python atual')
            if not executavel.is_file():
                raise FalhaRedirecionamento('O interpretador Python atual não está disponível.')
    env_filho = dict(os.environ if ambiente is None else ambiente)
    # Impede que atalhos/shell antigos mudem os módulos importados pelo Python.
    env_filho.pop('PYTHONPATH', None)
    env_filho.pop('PYTHONHOME', None)
    env_filho['MEUCONTROLEPC_ENV'] = str(arquivo_env)
    env_filho['MEUCONTROLEPC_DADOS'] = str(pasta_dados)
    return {'modo': modo, 'codigo': codigo, 'arquivo_env': arquivo_env, 'dados': pasta_dados,
            'python': executavel, 'script': script, 'cwd': str(codigo), 'ambiente': env_filho,
            'comando': [str(executavel), str(script), *fixos, *adicionais]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codigo', default=CODIGO_PADRAO, help='Pasta absoluta com o código atualizado.')
    parser.add_argument('--env', dest='arquivo_env', default=ENV_PADRAO, help='Arquivo .env externo existente (somente o caminho).')
    parser.add_argument('--dados', help='Pasta absoluta externa de dados já existentes; padrão: dados junto ao .env.')
    parser.add_argument('--python', help='Interpretador absoluto; padrão: .venv do código, da instalação externa ou Python atual.')
    parser.add_argument('--verificar', action='store_true', help='Mostra apenas caminhos/modo, sem ler .env, iniciar processos ou chamar APIs.')
    parser.add_argument('modo', choices=tuple(MODOS), nargs='?', default='start')
    raw = list(sys.argv[1:] if argv is None else argv)
    # Reservado mesmo depois de um separador --: nunca consultar o app por engano.
    verificar = '--verificar' in raw
    raw = [a for a in raw if a != '--verificar']
    args, adicionais = parser.parse_known_args(raw)
    try:
        plano = plano_execucao(args.codigo, args.arquivo_env, args.dados, args.python,
                              args.modo, adicionais)
        if verificar or args.verificar:
            print('Modo: ' + plano['modo'])
            print('Código: ' + str(plano['codigo']))
            print('Configuração (.env): ' + str(plano['arquivo_env']))
            print('Dados: ' + str(plano['dados']))
            print('Python: ' + str(plano['python']))
            print('Script: ' + str(plano['script']))
            print('Somente caminhos conferidos; nenhuma configuração foi lida e nenhum processo foi iniciado.')
            return 0
        resultado = subprocess.run(plano['comando'], cwd=plano['cwd'], env=plano['ambiente'],
                                   shell=False, check=False)
        return resultado.returncode
    except FalhaRedirecionamento as erro:
        print('Redirecionamento não iniciado: ' + str(erro))
        return 2
    except OSError:
        print('Não foi possível acessar os caminhos ou iniciar o Python selecionado. Confira instalação e permissões; configuração e dados foram preservados.')
        return 2
    except KeyboardInterrupt:
        print('\nExecução interrompida pelo usuário.')
        return 130


if __name__ == '__main__':
    sys.exit(main())
