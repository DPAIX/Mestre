"""Ponte compatível: apenas mapeia tarefas .tsk; não sobrescreve scripts/tarefas."""
from nucleo import ler_env,inicializar,catalogo_robotask
if __name__=='__main__':
    ler_env();inicializar()
    tarefas=catalogo_robotask()
    print(f'RoboTask: {len(tarefas)} tarefas catalogadas em dados/robotask_conhecimento.json')
    for t in tarefas[:30]:print('-',t['nome'],'|',t['external_name'])
