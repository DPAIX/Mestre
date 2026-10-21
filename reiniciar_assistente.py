"""Helper de reinício, iniciado em nova janela com o mesmo Python da instalação."""
import os
import subprocess
import sys
import time

def main():
    if len(sys.argv)<3:raise SystemExit('Uso: reiniciar_assistente.py PID SCRIPT [args...]')
    pai=int(sys.argv[1]); script=sys.argv[2]
    if not os.path.isfile(script):raise SystemExit('Arquivo não encontrado.')
    try:
        import psutil
        try:processo=psutil.Process(pai)
        except psutil.NoSuchProcess:processo=None
        limite=time.monotonic()+35
        while processo and processo.is_running() and processo.status()!=psutil.STATUS_ZOMBIE and time.monotonic()<limite:
            time.sleep(.25)
        if processo and processo.is_running() and processo.status()!=psutil.STATUS_ZOMBIE:
            raise SystemExit('Processo anterior ainda ativo. Reinício cancelado para evitar conflito na porta do painel.')
    except ImportError:
        # Sem psutil, não arriscar iniciar duas instâncias.
        raise SystemExit('psutil ausente; reinício não executado.')
    time.sleep(.6)
    subprocess.Popen([sys.executable,script,*sys.argv[3:]],cwd=os.path.dirname(script),
                     creationflags=getattr(subprocess,'CREATE_NEW_CONSOLE',0))

if __name__=='__main__':main()
