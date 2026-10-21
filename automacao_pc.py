"""Somente operações locais limitadas e invocadas por proprietário autenticado.
Nunca executa comandos shell ou código arbitrário recebido via Telegram/IA.
"""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time
import webbrowser
from nucleo import BASE,registrar

ATALHOS={'f8':('ctrl','alt','f8'),'f9':('ctrl','alt','f9'),'f10':('ctrl','alt','f10')}
LINKS={'furg':'https://sistemas.furg.br','agenda':'https://calendar.google.com',
       'colab':'https://colab.research.google.com','vscode':'https://code.visualstudio.com',
       'ru':'https://www.furg.br'}

def exigir_windows():
    if os.name!='nt':raise RuntimeError('Recurso disponível somente no Windows com sessão gráfica.')

def gui():
    exigir_windows()
    import pyautogui
    pyautogui.FAILSAFE=True
    pyautogui.PAUSE=.12
    return pyautogui

def executar(acao):
    """Ações autorizadas, lista explícita. Retorna uma mensagem honesta de resultado."""
    if acao in ATALHOS:
        gui().hotkey(*ATALHOS[acao]); retorno='Atalho enviado: Ctrl+Alt+'+acao.upper()
    elif acao=='desktop':
        gui().hotkey('win','d');retorno='Atalho Win+D enviado.'
    elif acao=='enter':
        gui().press('enter');retorno='Enter enviado.'
    elif acao=='taskmgr':
        exigir_windows();subprocess.Popen(['taskmgr.exe'],shell=False);retorno='Gerenciador de Tarefas solicitado.'
    elif acao in ('explorer','notepad','calc'):
        exigir_windows()
        nomes={'explorer':'explorer.exe','notepad':'notepad.exe','calc':'calc.exe'}
        subprocess.Popen([nomes[acao]],shell=False)
        retorno='Programa solicitado: '+nomes[acao]
    elif acao=='vscode_pc':
        exigir_windows()
        caminho=shutil.which('code') or shutil.which('code.cmd')
        if not caminho:raise RuntimeError('VS Code CLI não encontrado no PATH.')
        subprocess.Popen([caminho],shell=False)
        retorno='Abertura do VS Code solicitada.'
    elif acao in LINKS:
        webbrowser.open(LINKS[acao]);retorno='Abertura solicitada: '+LINKS[acao]
    else:raise ValueError('Ação não autorizada: '+str(acao))
    registrar('pc_'+acao,'executado',retorno)
    return retorno

def captura():
    p=gui().screenshot()
    from io import BytesIO
    arq=BytesIO();p.save(arq,format='PNG');arq.seek(0)
    registrar('captura_tela','executado','Imagem obtida para proprietário')
    return arq
