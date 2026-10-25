"""Catálogo de aplicativos e abertura interativa pelo lançador oficial Ollama.

Um aplicativo de agente não é um modelo de inferência. Este módulo não importa
SDKs dos agentes, não lê suas credenciais e não executa prompts ou instalações
na importação. A confirmação do assistente autoriza abrir o lançador; seleção,
instalação, autenticação e permissões adicionais acontecem na janela do Ollama.

Fontes primárias: https://docs.ollama.com/cli e
https://github.com/ollama/ollama/blob/main/cmd/launch/registry.go
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import unicodedata

from configurar_ia_local import URL_PADRAO, modelo_em_nuvem, validar_modelo, validar_url

BASE = Path(__file__).resolve().parent
PRAZO_AJUDA = 5
LIMITE_AJUDA = 65_536


@dataclass(frozen=True)
class Integracao:
    agente: str
    nome: str
    comandos: tuple[str, ...]
    aliases: tuple[str, ...] = ()


# IDs canônicos do lançador oficial; nenhuma entrada é interpretada como shell.
INTEGRACOES = (
    Integracao('claude', 'Claude Code', ('claude',), ('claude code',)),
    Integracao('opencode', 'OpenCode', ('opencode',), ('open code',)),
    Integracao('hermes', 'Hermes Agent', ('hermes',), ('hermes agent',)),
    Integracao('hermes-desktop', 'Hermes Desktop', (), ('hermes desktop',)),
    Integracao('copilot', 'Copilot CLI', ('copilot',), ('copilot cli', 'copilot-cli')),
    Integracao('cline', 'Cline', ('cline',)),
    Integracao('dsh', 'DeepSeek Harness', ('dsh',), ('deepseek harness', 'deepseek-harness')),
    Integracao('pi', 'Pi', ('pi',)),
    Integracao('openclaw', 'OpenClaw', ('openclaw', 'clawdbot'), ('clawdbot', 'moltbot')),
    Integracao('chatgpt', 'ChatGPT Desktop', (), ('chatgpt desktop', 'codex-app', 'codex-desktop', 'codex-gui')),
    Integracao('codex', 'Codex CLI', ('codex',), ('codex cli',)),
    Integracao('omp', 'Oh My Pi', ('omp',), ('oh my pi', 'oh-my-pi')),
    Integracao('droid', 'Droid', ('droid',)),
    Integracao('qwen', 'Qwen Code', ('qwen',), ('qwen code',)),
)
_LANCAMENTOS = {}
_TRAVA_LANCAMENTOS = threading.Lock()


def _normalizar_nome(texto):
    if not isinstance(texto, str) or len(texto) > 80:
        raise ValueError('Escolha um agente do catálogo.')
    return ' '.join(''.join(c for c in unicodedata.normalize('NFD', texto)
                            if unicodedata.category(c) != 'Mn').lower().split())


def validar_agente(agente):
    nome = _normalizar_nome(agente)
    for item in INTEGRACOES:
        if nome in (item.agente, _normalizar_nome(item.nome), *item.aliases):
            return item.agente
    raise ValueError('Agente desconhecido. Consulte o catálogo de agentes.')


def _integracao(agente):
    agente = validar_agente(agente)
    return next(item for item in INTEGRACOES if item.agente == agente)


def catalogo_agentes():
    """Somente PATH, sem executar binários nem ler configurações pessoais.

    Encontrar um comando não comprova instalação completa ou funcionamento.
    Apps desktop exigem verificação no lançador; o menu sozinho não é prova.
    """
    lancador = bool(shutil.which('ollama.exe') or shutil.which('ollama'))
    resultado = []
    for item in INTEGRACOES:
        encontrado = any(shutil.which(comando) for comando in item.comandos)
        estado = ('comando_no_path' if encontrado else
                  'verificar_no_lancador' if not item.comandos else 'nao_localizado_no_path')
        resultado.append({'agente': item.agente, 'nome': item.nome, 'estado': estado,
                          'lancador_no_path': lancador})
    return resultado


def resumo_agentes():
    itens = catalogo_agentes()
    rotulos = {'comando_no_path': 'comando localizado no PATH',
               'nao_localizado_no_path': 'comando não localizado no PATH',
               'verificar_no_lancador': 'verificação pelo lançador'}
    linhas = ['🤖 Aplicativos de agentes integrados ao lançador Ollama:']
    linhas.extend(f"• {item['nome']} ({item['agente']}): {rotulos[item['estado']]}" for item in itens)
    linhas += ['Ollama no PATH: ' + ('localizado.' if itens[0]['lancador_no_path'] else 'não localizado.'),
               'Esses aplicativos não são modelos participantes da equipe. PATH e menu não comprovam funcionamento.',
               'Diga “abra o agente Claude Code” ou “configure o agente OpenCode”. A abertura pede confirmação; '
               'o terminal oficial pode solicitar instalação, modelo, login e permissões.']
    return '\n'.join(linhas)


def preparar_lancamento(agente, modelo=None, configurar=False):
    """Validação pura para o plano do Telegram/painel, sem leitura de estado."""
    item = _integracao(agente)
    if type(configurar) is not bool:
        raise ValueError('O modo de configuração deve ser verdadeiro ou falso.')
    modelo = '' if modelo is None or modelo == '' else validar_modelo(modelo)
    verbo = 'Configurar' if configurar else 'Abrir'
    descricao = f'{verbo} {item.nome} em outra janela pelo lançador oficial Ollama.'
    if modelo:
        descricao += f' Modelo: {modelo}.'
        if modelo_em_nuvem(modelo):
            descricao += ' Modelo de nuvem: requer Internet, conta e limites do provedor.'
    else:
        descricao += ' O modelo será escolhido ou validado no terminal (local ou nuvem).'
    descricao += (' Pode instalar o aplicativo, baixar modelos e alterar sua configuração. '
                  'Confira permissões e login no PC. Não envia histórico ou chaves do assistente.')
    return {'agente': item.agente, 'modelo': modelo, 'configurar': configurar, 'descricao': descricao}


def _ambiente_lancador():
    # O bot carrega chaves no ambiente. Não as herdar para os aplicativos.
    permitidas = {'PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'SYSTEMDRIVE',
                  'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH', 'APPDATA', 'LOCALAPPDATA',
                  'PROGRAMFILES', 'PROGRAMFILES(X86)', 'PROGRAMDATA', 'TEMP', 'TMP',
                  'USERNAME', 'USERDOMAIN', 'OS', 'NUMBER_OF_PROCESSORS',
                  'PROCESSOR_ARCHITECTURE', 'LANG', 'LC_ALL', 'TERM', 'COLORTERM'}
    ambiente = {nome: valor for nome, valor in os.environ.items() if nome.upper() in permitidas}
    ambiente['OLLAMA_HOST'] = validar_url(os.getenv('OLLAMA_URL', URL_PADRAO))
    if os.getenv('OLLAMA_NO_CLOUD', '').lower() in ('1', 'true'):
        ambiente['OLLAMA_NO_CLOUD'] = '1'
    return ambiente


def _executavel_ollama():
    caminho = shutil.which('ollama.exe') or shutil.which('ollama')
    if not caminho:
        raise RuntimeError('Ollama CLI não localizado no PATH. Instale ou abra o Ollama no PC.')
    caminho = Path(caminho).resolve()
    if caminho.suffix.lower() != '.exe' or not caminho.is_file():
        raise RuntimeError('Use o executável ollama.exe instalado no Windows; scripts de shell não são aceitos.')
    return str(caminho)


def _conferir_lancador(executavel, agente, ambiente):
    try:
        resultado = subprocess.run([executavel, 'launch', '--help'], shell=False,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                                   errors='replace', timeout=PRAZO_AJUDA, check=False,
                                   cwd=str(BASE), env=ambiente)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError('Não foi possível conferir o lançador Ollama em até 5 segundos. Nenhum agente foi aberto.') from None
    ajuda = resultado.stdout
    if (resultado.returncode != 0 or not isinstance(ajuda, str) or len(ajuda) > LIMITE_AJUDA
            or not re.search(r'(?m)^\s*' + re.escape(agente) + r'\s+\S', ajuda)):
        raise RuntimeError('A ajuda do Ollama instalado não confirma essa integração. Atualize o Ollama e confira “ollama launch --help” no PC.')


def abrir_agente(agente, modelo=None, configurar=False, *, confirmado=False):
    """Após autorização do chamador, abre o fluxo oficial em console separado.

    Não envia pedidos ou código ao agente e não usa --yes. Retornar não comprova
    instalação, autenticação, inferência ou conclusão de uma tarefa no aplicativo.
    """
    plano = preparar_lancamento(agente, modelo, configurar)
    if confirmado is not True:
        raise PermissionError('Confirme a abertura ou configuração do agente antes de executar.')
    if sys.platform != 'win32':
        raise RuntimeError('A abertura de agentes exige Windows com sessão gráfica local.')
    executavel = _executavel_ollama()
    ambiente = _ambiente_lancador()
    _conferir_lancador(executavel, plano['agente'], ambiente)
    argumentos = [executavel, 'launch', plano['agente']]
    if plano['modelo']:
        argumentos += ['--model', plano['modelo']]
    if plano['configurar']:
        argumentos.append('--config')
    chave = plano['agente']
    with _TRAVA_LANCAMENTOS:
        anterior = _LANCAMENTOS.get(chave)
        if anterior is not None and anterior.poll() is None:
            return f'Já existe uma janela do lançador ativa para {_integracao(chave).nome}. Confira essa janela no PC.'
        try:
            processo = subprocess.Popen(argumentos, shell=False, cwd=str(BASE),
                                        env=ambiente, close_fds=True,
                                        creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0x10))
        except OSError:
            raise RuntimeError('O Windows não abriu o lançador Ollama. Confira a instalação e as permissões locais.') from None
        _LANCAMENTOS[chave] = processo
    modo = 'Configuração' if plano['configurar'] else 'Abertura'
    return (f'{modo} de {_integracao(chave).nome} solicitada em outra janela. '
            'Acompanhe a seleção de modelo, instalação ou login no PC. '
            'A abertura não comprova que o aplicativo ou modelo respondeu.')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Catálogo e lançador interativo dos agentes Ollama.')
    parser.add_argument('--listar', action='store_true', help='Apenas listar; não executar aplicativos.')
    parser.add_argument('--agente', help='ID do catálogo, como claude, codex ou opencode.')
    parser.add_argument('--modelo', default='', help='Tag opcional do Ollama; não será baixada por este módulo.')
    parser.add_argument('--configurar', action='store_true', help='Abrir o modo de configuração oficial.')
    parser.add_argument('--confirmar', action='store_true', help='Autorizar explicitamente abrir o lançador.')
    args = parser.parse_args(argv)
    if args.listar:
        print(resumo_agentes())
        return 0
    try:
        agente = args.agente
        modelo = args.modelo
        if not agente:
            print(resumo_agentes())
            agente = input('\nID do agente (Enter para encerrar): ').strip()
            if not agente:
                return 0
            if not modelo:
                modelo = input('Modelo opcional (Enter para escolher no lançador): ').strip()
        plano = preparar_lancamento(agente, modelo, args.configurar)
        print('\n' + plano['descricao'])
        confirmado = args.confirmar
        if not confirmado:
            confirmado = input('Confirma? Digite sim: ').strip().casefold() == 'sim'
        if not confirmado:
            print('Abertura cancelada.')
            return 0
        print(abrir_agente(plano['agente'], plano['modelo'], plano['configurar'], confirmado=True))
        return 0
    except (ValueError, PermissionError, RuntimeError) as erro:
        print('Não foi possível abrir: ' + str(erro))
        return 1
    except (EOFError, KeyboardInterrupt):
        print('\nAbertura cancelada.')
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
