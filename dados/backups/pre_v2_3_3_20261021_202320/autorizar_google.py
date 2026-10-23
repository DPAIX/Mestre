from nucleo import ler_env,inicializar
from agenda_google import autorizacao
if __name__=='__main__':
    ler_env();inicializar()
    autorizacao();print('Google Calendar autorizado para consultas de leitura.')
