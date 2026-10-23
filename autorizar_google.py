"""Seleciona credenciais OAuth Desktop e autoriza Google Calendar somente leitura."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

import agenda_google as agenda
from nucleo import BASE, ler_env
from caminhos_instalacao import arquivo_env as arquivo_env_instalacao


def instrucoes():
    print('Google Agenda precisa de um arquivo OAuth próprio do Google Cloud.')
    print('1. Habilite Google Calendar API no seu projeto: https://console.cloud.google.com/apis/library/calendar-json.googleapis.com')
    print('2. Configure a tela de consentimento e inclua sua conta como usuário de teste, se o aplicativo estiver em teste.')
    print('3. Em APIs e serviços > Credenciais, crie ID do cliente OAuth > Aplicativo para computador (Desktop app).')
    print('4. Baixe o JSON. Coloque-o como credentials.json nesta pasta ou informe seu caminho abaixo.')
    print('Esse arquivo não é uma chave Gemini. Mantenha-o no PC; não envie seu conteúdo ao chat.')


def salvar_caminho(caminho, arquivo_env=None):
    """Altera só GOOGLE_OAUTH_CREDENTIALS após validar uma escolha explícita."""
    caminho = agenda.validar_credenciais(caminho)
    arquivo_env = Path(arquivo_env) if arquivo_env is not None else arquivo_env_instalacao(BASE)
    bruto = arquivo_env.read_bytes() if arquivo_env.exists() else b''
    bom = '\ufeff' if bruto.startswith(b'\xef\xbb\xbf') else ''
    original = bruto.decode('utf-8-sig')
    quebra = '\r\n' if '\r\n' in original else '\n'
    linhas = []
    processada = False
    for linha in original.splitlines(keepends=True):
        chave = linha.split('=', 1)[0].strip() if '=' in linha and not linha.lstrip().startswith('#') else ''
        if chave == 'GOOGLE_OAUTH_CREDENTIALS':
            if not processada:
                linhas.append('GOOGLE_OAUTH_CREDENTIALS=' + str(caminho) + quebra)
                processada = True
        else:
            linhas.append(linha)
    if linhas and not linhas[-1].endswith(('\r', '\n')):
        linhas[-1] += quebra
    if not processada:
        linhas.append('GOOGLE_OAUTH_CREDENTIALS=' + str(caminho) + quebra)
    arquivo_env.parent.mkdir(parents=True, exist_ok=True)
    fd, temporario = tempfile.mkstemp(prefix='.env.google.', suffix='.tmp', dir=str(arquivo_env.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as arquivo:
            arquivo.write(bom + ''.join(linhas))
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, arquivo_env)
    finally:
        Path(temporario).unlink(missing_ok=True)
    return caminho


def main(argv=None, *, interativo=None, arquivo_env=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('arquivo', nargs='?', help='Caminho do JSON OAuth Desktop baixado do Google Cloud.')
    parser.add_argument('--verificar', action='store_true', help='Valida somente o arquivo; não abre navegador nem grava configuração.')
    args = parser.parse_args(argv)
    try:
        ler_env()
        explicito = args.arquivo is not None
        try:
            caminho = agenda.encontrar_credenciais(args.arquivo)
        except agenda.FalhaAgenda as erro:
            print('Configuração Google incompleta: ' + str(erro))
            instrucoes()
            if args.verificar or explicito or not (sys.stdin.isatty() if interativo is None else interativo):
                return 2
            escolhido = input('Caminho do JSON OAuth (Enter cancela): ').strip()
            if not escolhido:
                print('Autorização cancelada; configuração preservada.')
                return 2
            caminho = agenda.encontrar_credenciais(escolhido)
            explicito = True
        if args.verificar:
            print('Arquivo OAuth Desktop válido localmente. Nenhuma conta, conexão ou permissão foi autenticada.')
            return 0
        if explicito:
            salvar_caminho(caminho, arquivo_env)
        agenda.autorizacao(caminho)
        print('Google Calendar autorizado para consultas de leitura. Reinicie o assistente se ele já estava aberto.')
        return 0
    except agenda.FalhaAgenda as erro:
        print('Autorização Google não concluída: ' + str(erro))
        return 2
    except ValueError:
        print('Configuração de caminho inválida. MEUCONTROLEPC_ENV deve indicar um arquivo absoluto; confira a configuração local.')
        return 2
    except (OSError, UnicodeError):
        print('Não foi possível acessar a configuração local. Confira permissões da pasta e espaço disponível.')
        return 2
    except (KeyboardInterrupt, EOFError):
        print('\nAutorização cancelada; nenhuma confirmação de acesso foi recebida.')
        return 2


if __name__ == '__main__':
    sys.exit(main())
