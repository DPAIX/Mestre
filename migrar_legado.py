"""Migração não destrutiva. python migrar_legado.py "C:\\Users\\...\\Desktop"""
import sys
from pathlib import Path
from nucleo import inicializar,DADOS
if __name__=='__main__':
    if len(sys.argv)<2:
        print('Uso: python migrar_legado.py "C:\\caminho\\para\\pasta\\antiga"')
        raise SystemExit(2)
    origem=Path(sys.argv[1])
    if not origem.is_dir():raise SystemExit('Pasta não encontrada: '+str(origem))
    inicializar(origem)
    print('Migração concluída. Dados seguros em:',DADOS)
    print('Não foram importados tokens/chaves, logs brutos nem código autoexecutável.')
