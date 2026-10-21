"""Google Calendar somente leitura, mediante OAuth explícito do proprietário."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from pathlib import Path
import os
from nucleo import DADOS,registrar
ESCOPOS=['https://www.googleapis.com/auth/calendar.readonly']
TOKEN=DADOS/'token_google.json'

def autorizacao():
    try:from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:raise RuntimeError('Instale as bibliotecas opcionais: pip install -r requirements-google.txt')
    cred=os.environ.get('GOOGLE_OAUTH_CREDENTIALS','')
    if not cred or not Path(cred).is_file():raise RuntimeError('Configure GOOGLE_OAUTH_CREDENTIALS no .env com o caminho de credentials.json.')
    DADOS.mkdir(exist_ok=True)
    flow=InstalledAppFlow.from_client_secrets_file(cred,ESCOPOS)
    creds=flow.run_local_server(port=0)
    TOKEN.write_text(creds.to_json(),encoding='utf-8')
    registrar('agenda_google','autorizado','OAuth somente leitura concluído')
    return True

def proximos_eventos(quantidade=10):
    if not TOKEN.exists():return None
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:raise RuntimeError('Instale: pip install -r requirements-google.txt')
    creds=Credentials.from_authorized_user_file(str(TOKEN),ESCOPOS)
    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request());TOKEN.write_text(creds.to_json(),encoding='utf-8')
    if not creds.valid:raise RuntimeError('Autorização Google expirada; execute autorizar_google.bat.')
    agora=datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
    events=build('calendar','v3',credentials=creds,cache_discovery=False).events().list(calendarId='primary',timeMin=agora,
                      maxResults=quantidade,singleEvents=True,orderBy='startTime').execute().get('items',[])
    registrar('agenda_google','consulta','Eventos obtidos: '+str(len(events)))
    return [{'titulo':e.get('summary','Sem título'), 'inicio':e.get('start',{}).get('dateTime') or e.get('start',{}).get('date'),
             'fim':e.get('end',{}).get('dateTime') or e.get('end',{}).get('date')} for e in events]
