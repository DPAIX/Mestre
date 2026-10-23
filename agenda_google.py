"""Google Calendar somente leitura, mediante OAuth explícito do proprietário."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

from nucleo import BASE, DADOS, registrar
from caminhos_instalacao import arquivo_env

ESCOPOS = ['https://www.googleapis.com/auth/calendar.readonly']
TOKEN = DADOS / 'token_google.json'
LIMITE_CREDENCIAIS = 1_000_000


class FalhaAgenda(RuntimeError):
    """Erro controlado; respostas OAuth e credenciais não entram na mensagem."""


def _caminho(texto):
    if not isinstance(texto, (str, os.PathLike)):
        raise FalhaAgenda('Informe o caminho do JSON OAuth para aplicativo de computador.')
    texto = os.fspath(texto).strip()
    if len(texto) >= 2 and texto[0] == texto[-1] and texto[0] in ('"', "'"):
        texto = texto[1:-1].strip()
    if not texto or any(c in texto for c in ('\x00','\r','\n')):
        raise FalhaAgenda('Informe o caminho do JSON OAuth para aplicativo de computador.')
    texto = re.sub(r'%([^%]+)%', lambda m: os.environ.get(m[1], m[0]), texto)
    caminho = Path(os.path.expandvars(os.path.expanduser(texto)))
    if not caminho.is_absolute():
        caminho = arquivo_env(BASE).parent / caminho
    return caminho.resolve()


def validar_credenciais(caminho):
    """Valida um cliente OAuth Desktop sem imprimir/copiar os seus segredos."""
    caminho = _caminho(caminho)
    try:
        if not caminho.is_file():
            raise FalhaAgenda('O arquivo OAuth não foi encontrado. Escolha o credentials.json baixado do Google Cloud.')
        with caminho.open('rb') as arquivo:
            bruto = arquivo.read(LIMITE_CREDENCIAIS + 1)
        if len(bruto) > LIMITE_CREDENCIAIS:
            raise FalhaAgenda('O arquivo OAuth excede o tamanho permitido.')
        dados = json.loads(bruto.decode('utf-8-sig'))
    except (OSError, UnicodeError, ValueError):
        raise FalhaAgenda('Não foi possível ler um JSON OAuth válido. Baixe novamente as credenciais do Google Cloud.') from None
    cliente = dados.get('installed') if isinstance(dados, dict) else None
    if (not isinstance(cliente, dict) or
            any(not isinstance(cliente.get(campo), str) or not cliente[campo].strip()
                for campo in ('client_id', 'client_secret', 'auth_uri', 'token_uri'))):
        raise FalhaAgenda('Use um cliente OAuth do tipo Aplicativo para computador (Desktop app). Conta de serviço, chave de API e cliente Web não atendem a este fluxo.')
    for campo, hosts in (('auth_uri', {'accounts.google.com'}),
                         ('token_uri', {'oauth2.googleapis.com', 'www.googleapis.com', 'accounts.google.com'})):
        try:
            url = urlsplit(cliente[campo])
            valido = (url.scheme == 'https' and url.hostname in hosts and url.port in (None, 443)
                      and url.username is None and url.password is None and not url.fragment)
        except ValueError:
            valido = False
        if not valido:
            raise FalhaAgenda('O JSON OAuth não contém os endereços oficiais do Google. Baixe um cliente Desktop diretamente do Google Cloud.')
    return caminho


def encontrar_credenciais(caminho=None):
    """Arquivo explícito, configuração local ou credentials.json junto ao projeto."""
    if caminho is None:
        caminho = os.environ.get('GOOGLE_OAUTH_CREDENTIALS', '').strip() or arquivo_env(BASE).parent / 'credentials.json'
    return validar_credenciais(caminho)


def _gravar_token(texto):
    """Troca atômica: uma falha preserva o token anterior."""
    if not isinstance(texto, str):
        raise FalhaAgenda('O Google não retornou um token válido; a autorização anterior foi preservada.')
    try:
        if not isinstance(json.loads(texto), dict):
            raise ValueError
    except ValueError:
        raise FalhaAgenda('O Google não retornou um token válido; a autorização anterior foi preservada.') from None
    TOKEN.parent.mkdir(parents=True, exist_ok=True)
    fd, temporario = tempfile.mkstemp(prefix='.token_google.', suffix='.tmp', dir=str(TOKEN.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as arquivo:
            arquivo.write(texto)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, TOKEN)
    finally:
        Path(temporario).unlink(missing_ok=True)


def autorizacao(caminho=None):
    cred = encontrar_credenciais(caminho)
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        raise FalhaAgenda('Instale as bibliotecas opcionais: pip install -r requirements-google.txt') from None
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(cred), ESCOPOS)
        creds = flow.run_local_server(port=0)
        _gravar_token(creds.to_json())
    except FalhaAgenda:
        raise
    except OSError:
        raise FalhaAgenda('Não foi possível concluir a autorização ou salvar o token. Confira navegador, permissões da pasta e conexão.') from None
    except Exception:
        raise FalhaAgenda('A autorização Google não foi concluída. Confira o cliente OAuth Desktop, a conta de teste e a tela de consentimento; execute novamente quando estiver pronto.') from None
    registrar('agenda_google', 'autorizado', 'OAuth somente leitura concluído')
    return True


def proximos_eventos(quantidade=10):
    if isinstance(quantidade, bool) or not isinstance(quantidade, int) or not 1 <= quantidade <= 100:
        raise ValueError('Informe entre 1 e 100 eventos.')
    if not TOKEN.exists():
        return None
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        raise FalhaAgenda('Instale as bibliotecas opcionais: pip install -r requirements-google.txt') from None
    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN), ESCOPOS)
        if not creds.valid and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _gravar_token(creds.to_json())
        if not creds.valid:
            raise FalhaAgenda('Autorização Google expirada; execute autorizar_google.bat.')
        agora = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        servico = build('calendar', 'v3', credentials=creds, cache_discovery=False)
        try:
            eventos = servico.events().list(calendarId='primary', timeMin=agora,
                maxResults=quantidade, singleEvents=True, orderBy='startTime').execute().get('items', [])
        finally:
            if hasattr(servico, 'close'):
                servico.close()
        if not isinstance(eventos, list):
            raise ValueError
        saida = [{'titulo': e.get('summary', 'Sem título'),
                  'inicio': e.get('start', {}).get('dateTime') or e.get('start', {}).get('date'),
                  'fim': e.get('end', {}).get('dateTime') or e.get('end', {}).get('date')}
                 for e in eventos]
    except FalhaAgenda:
        raise
    except Exception:
        raise FalhaAgenda('Não foi possível consultar ou renovar a autorização Google. Confira conexão e Calendar API; se necessário, execute autorizar_google.bat novamente.') from None
    registrar('agenda_google', 'consulta', 'Eventos obtidos: ' + str(len(saida)))
    return saida
