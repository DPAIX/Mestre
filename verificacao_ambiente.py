"""Verificação offline e sem cobranças das configurações, dependências e do ambiente.
Não revela valores de chaves nem conecta a fornecedores externos.
"""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
from nucleo import BASE,DADOS,resumo_status

PROVEDORES={'Gemini':('GEMINI_API_KEY','GOOGLE_API_KEY'),
            'OpenAI':('OPENAI_API_KEY',),'Claude':('ANTHROPIC_API_KEY',),'Exa':('EXA_API_KEY',)}

def chave_preenchida(nome):
    val=os.environ.get(nome,'').strip()
    return bool(val) and not val.upper().startswith(('COLOQUE','SEU_','SUA_'))

def verificar():
    avisos=[]
    ok=[]
    token=os.environ.get('TELEGRAM_TOKEN','')
    if token:
        try:
            from configurar_telegram import validar_token
            if validar_token(token):ok.append('Token Telegram com formato válido (não autenticado remotamente)')
            else:avisos.append('Token Telegram: formato inválido. Use configurar_telegram.bat')
        except ImportError:avisos.append('Validador Telegram indisponível')
    else:avisos.append('Telegram sem token: painel local ainda pode ser usado')
    if os.environ.get('TELEGRAM_ALLOWED_USER_IDS','').strip():
        try:
            from configurar_telegram import validar_ids
            if validar_ids(os.environ['TELEGRAM_ALLOWED_USER_IDS']):ok.append('Lista local de proprietários preenchida')
            else:avisos.append('Lista de proprietários inválida')
        except ImportError:avisos.append('Validador de proprietários indisponível')
    else:avisos.append('Telegram sem IDs autorizados: somente /id funcionará')
    for nome,chaves in PROVEDORES.items():
        if any(chave_preenchida(x) for x in chaves):ok.append(f'{nome}: chave definida, saldo e disponibilidade NÃO verificados')
        else:avisos.append(f'{nome}: chave ausente — consultas via esse provedor indisponíveis')
    for mod,etiqueta in [('telebot','pyTelegramBotAPI'),('pyautogui','PyAutoGUI')]:
        if importlib.util.find_spec(mod):ok.append('Dependência encontrada: '+etiqueta)
        else:avisos.append('Dependência ausente: '+etiqueta)
    try:
        if importlib.util.find_spec('google.genai'):ok.append('Dependência encontrada: google-genai')
        else:avisos.append('Dependência ausente: google-genai')
    except ModuleNotFoundError:avisos.append('Dependência ausente: google-genai')
    if not (BASE/'painel_rotina.html').is_file():avisos.append('Painel HTML ausente')
    if not (BASE/'reiniciar_assistente.py').is_file():avisos.append('Mecanismo de reinício do assistente ausente')
    try:
        livre=resumo_status()['disco_livre_mb']
        if livre<2048:avisos.append(f'Disco com pouco espaço livre: {livre} MiB')
        else:ok.append(f'Disco com {livre} MiB livres')
    except Exception:avisos.append('Disco não pôde ser inspecionado')
    if os.name!='nt':avisos.append('Fora do Windows: RoboTask e GUI não podem ser testados aqui')
    texto='🔎 Verificação OFFLINE (sem consulta às APIs):\n'
    texto+='\n'.join('✅ '+s for s in ok)+'\n'
    texto+='\n'.join('⚠️ '+s for s in avisos)+'\n'
    texto+='Nenhuma chave, crédito ou conexão foi validada pela rede.'
    return {'ok':ok,'avisos':avisos,'texto':texto}

if __name__=='__main__':
    from nucleo import ler_env,inicializar
    ler_env();inicializar()
    print(verificar()['texto'])
