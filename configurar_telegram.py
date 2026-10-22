"""Assistente local para configurar o Telegram sem imprimir credenciais no console.

Uso: python configurar_telegram.py [--verificar]
Não acessa a rede; valida apenas o formato do token.
"""
from __future__ import annotations
import argparse
import getpass
import os
from pathlib import Path
import re
import sys
import tempfile
from caminhos_instalacao import arquivo_env

BASE = Path(__file__).resolve().parent
ENV = BASE / '.env'
EXEMPLO = BASE / '.env.exemplo'
CHAVES = ('TELEGRAM_TOKEN', 'TELEGRAM_ALLOWED_USER_IDS')
PADRAO_TOKEN = re.compile(r'^[1-9][0-9]{5,19}:[A-Za-z0-9_-]{20,}$')


def validar_token(token: str) -> bool:
    """Somente formato. A existência do bot depende da API Telegram."""
    return bool(PADRAO_TOKEN.fullmatch(token.strip()))


def validar_ids(texto: str) -> bool:
    return not texto or bool(re.fullmatch(r'[0-9]+(?:\s*[,;]\s*[0-9]+)*', texto.strip()))


def valores_env(path: Path | None = None) -> dict[str, str]:
    path = Path(path) if path is not None else arquivo_env(BASE)
    if not path.is_file():
        return {}
    valores = {}
    for linha in path.read_text(encoding='utf-8-sig').splitlines():
        if '=' in linha and not linha.lstrip().startswith('#'):
            chave, valor = linha.split('=', 1)
            if chave.strip() in CHAVES:
                valores[chave.strip()] = valor.strip().strip('"\'')
    return valores


def atualizar_env(alteracoes: dict[str, str], path: Path | None = None, exemplo: Path = EXEMPLO) -> None:
    """Atualiza somente as chaves desejadas; preserva as outras configurações."""
    if any(k not in CHAVES for k in alteracoes):
        raise ValueError('Chave de configuração não permitida.')
    path = Path(path) if path is not None else arquivo_env(BASE)
    exemplo = Path(exemplo)
    base = path.read_text(encoding='utf-8-sig') if path.exists() else (exemplo.read_text(encoding='utf-8-sig') if exemplo.exists() else '')
    novo = []
    processadas = set()
    for linha in base.splitlines():
        if '=' in linha and not linha.lstrip().startswith('#'):
            chave = linha.split('=', 1)[0].strip()
            if chave in alteracoes:
                if chave not in processadas:
                    novo.append(f'{chave}={alteracoes[chave]}')
                    processadas.add(chave)
                continue
        novo.append(linha)
    for chave, valor in alteracoes.items():
        if chave not in processadas:
            novo.append(f'{chave}={valor}')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.env.tmp.', dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(novo).rstrip('\n') + '\n')
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def verificar(path: Path | None = None) -> bool:
    configuracao = valores_env(path)
    if not validar_token(configuracao.get('TELEGRAM_TOKEN', '')):
        print('Telegram nao configurado: TELEGRAM_TOKEN ausente ou invalido no .env.')
        print('Execute configurar_telegram.bat para informar um NOVO token do @BotFather.')
        return False
    if not validar_ids(configuracao.get('TELEGRAM_ALLOWED_USER_IDS', '')):
        print('IDs permitidos invalidos no .env. Execute configurar_telegram.bat.')
        return False
    print('Formato do token Telegram: OK (ainda nao testado com a API).')
    if not configuracao.get('TELEGRAM_ALLOWED_USER_IDS', ''):
        print('ID de proprietario pendente: apos iniciar, envie /id no Telegram;')
        print('depois edite TELEGRAM_ALLOWED_USER_IDS no .env e reinicie.')
    else:
        print('ID(s) de proprietario configurados.')
    return True


def assistente(path: Path | None = None) -> int:
    path = Path(path) if path is not None else arquivo_env(BASE)
    print('=== Configuracao segura do Telegram ===')
    print('Revogue o token antigo se ele apareceu em arquivos ou mensagens compartilhados.')
    print('O token sera armazenado apenas em seu arquivo local .env.')
    atual = valores_env(path)
    tem_token = validar_token(atual.get('TELEGRAM_TOKEN', ''))
    if tem_token:
        print('Ja existe um token com formato valido. Tecle Enter para mante-lo.')
    token = getpass.getpass('Novo token do @BotFather (entrada oculta): ').strip()
    if not token and tem_token:
        token = atual['TELEGRAM_TOKEN']
    if not validar_token(token):
        print('ERRO: token invalido. Formato esperado: numeros:letras (sem espacos).')
        print('Nenhum arquivo foi alterado.')
        return 2
    print('Se ainda nao sabe seu ID, pressione Enter; depois envie /id ao bot.')
    atual_ids = atual.get('TELEGRAM_ALLOWED_USER_IDS', '')
    ids = input('Seu(s) ID(s) numerico(s) [' + ('configurado' if atual_ids else 'vazio') + ']: ').strip()
    if not ids:
        ids = atual_ids
    if not validar_ids(ids):
        print('ERRO: informe somente numeros separados por virgulas.')
        print('Nenhum arquivo foi alterado.')
        return 2
    atualizar_env({'TELEGRAM_TOKEN': token, 'TELEGRAM_ALLOWED_USER_IDS': ids}, path)
    print('Configuracao salva no .env. O token nao sera exibido.')
    print('Execute iniciar_windows.bat; o Telegram depende de rede e token ativo.')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verificar', action='store_true')
    args = parser.parse_args()
    try:
        if args.verificar:
            return 0 if verificar() else 2
        return assistente()
    except ValueError:
        print('Configuracao de caminho invalida. MEUCONTROLEPC_ENV deve indicar um arquivo absoluto; confira a configuracao local.')
        return 2
    except (OSError, UnicodeError):
        print('Nao foi possivel acessar a configuracao local. Confira permissoes da pasta e espaco disponivel.')
        return 2
    except (KeyboardInterrupt, EOFError):
        print('\nConfiguracao cancelada; nada foi alterado.')
        return 2


if __name__ == '__main__':
    sys.exit(main())
