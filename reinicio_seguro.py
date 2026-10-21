"""Reinicializações separadas: aplicação e Windows. Todas exigem autorização na interface.
Nunca executa comandos arbitrários. No Windows, um timeout > 0 implica fechamento forçado dos aplicativos ao fim da espera (Microsoft).
"""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
from nucleo import BASE,registrar


def reiniciar_windows():
    if os.name!='nt':raise RuntimeError('Disponível apenas no Windows.')
    if os.environ.get('REINICIO_WINDOWS_HABILITADO','0').strip()!='1':
        raise RuntimeError('Reinício do Windows desabilitado. Configure REINICIO_WINDOWS_HABILITADO=1 no .env.')
    try:espera=int(os.environ.get('REINICIO_WINDOWS_ATRASO_SEG','60'))
    except ValueError:espera=60
    espera=max(60,min(espera,600))
    # IMPORTANTE: /t > 0 IMPLICA /f no Windows. O usuário deve salvar documentos antes do prazo.
    processo=subprocess.run(['shutdown.exe','/r','/t',str(espera),'/c','MeuControlePC: reinicio AUTORIZADO; SALVE ARQUIVOS, o Windows fechara apps ao final da espera.'],
                            capture_output=True,text=True,timeout=12,check=False)
    if processo.returncode:
        registrar('reiniciar_windows','falha',f'Código {processo.returncode}')
        raise RuntimeError('O Windows recusou o agendamento do reinício; confira permissões e logs.')
    registrar('reiniciar_windows','agendado',f'Windows: reinício solicitado em {espera} segundos, fechamento forcado de apps apos o prazo.')
    return f'Windows: reinício solicitado para daqui a {espera} segundos. ATENÇÃO: aplicativos serão encerrados ao final do prazo, inclusive com dados não salvos. Salve imediatamente. Use /cancelar_reinicio ou o botão no painel para tentar cancelar.'


def cancelar_reinicio_windows():
    if os.name!='nt':raise RuntimeError('Disponível apenas no Windows.')
    r=subprocess.run(['shutdown.exe','/a'],capture_output=True,text=True,timeout=12,check=False)
    if r.returncode:
        raise RuntimeError('Nenhum reinício pendente ou o Windows recusou o cancelamento.')
    registrar('cancelar_reinicio_windows','executado','Comando shutdown /a confirmado.')
    return 'Pedido de cancelamento enviado e aceito pelo Windows.'


def preparar_reinicio_assistente():
    """Agenda um lançador externo que aguardará o processo antigo encerrar.
    A chamada devolve controle ao solicitante; saída do processo deve ocorrer depois da resposta.
    """
    if os.name!='nt':raise RuntimeError('Reinício controlado disponível somente no Windows.')
    comando=[sys.executable,str(BASE/'reiniciar_assistente.py'),str(os.getpid()),
             str(BASE/'assistente_pc.py'),*sys.argv[1:]]
    # Nova janela independente do processo que receberá o encerramento.
    p=subprocess.Popen(comando,cwd=str(BASE),creationflags=subprocess.CREATE_NEW_CONSOLE,
                       stdin=subprocess.DEVNULL)
    registrar('reiniciar_assistente','agendado','Lançador independente iniciado (PID %d).'%p.pid)
    return 'Reinicialização do assistente agendada. O painel e o Telegram ficarão brevemente indisponíveis.'
