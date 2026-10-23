"""Amostras CPU e snapshots fictícios; nenhum arquivo de uso é consultado."""
from collections import namedtuple
import copy
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import nucleo


TemposWindows=namedtuple('TemposWindows','user system idle')
TemposLinux=namedtuple('TemposLinux','user nice system idle iowait guest guest_nice')


class StatusRapidoTeste(unittest.TestCase):
    def setUp(self):
        for nome,valor in (
            ('_CPU_LOCK',threading.Lock()),
            ('_CPU_ESTADO',{'instante':None,'total':None,'ocioso':None,'percentual':None}),
        ):
            p=patch.object(nucleo,nome,valor)
            p.start();self.addCleanup(p.stop)
        p=patch.object(nucleo.time,'monotonic',return_value=10)
        self.relogio=p.start();self.addCleanup(p.stop)
        self.psutil=SimpleNamespace(
            cpu_times=Mock(return_value=TemposWindows(100,20,100)),
            cpu_percent=Mock(side_effect=AssertionError('Não esperar por uma amostra bloqueante.')),
            virtual_memory=Mock(return_value=SimpleNamespace(percent=42.5)),
        )
        p=patch.dict(sys.modules,{'psutil':self.psutil})
        p.start();self.addCleanup(p.stop)
        p=patch.object(nucleo,'vida',return_value={})
        self.vida=p.start();self.addCleanup(p.stop)
        p=patch.object(nucleo,'ler_json',return_value={})
        self.ler=p.start();self.addCleanup(p.stop)
        p=patch.object(nucleo.shutil,'disk_usage',return_value=SimpleNamespace(free=4*1024**3))
        p.start();self.addCleanup(p.stop)
        p=patch.object(nucleo,'ancestral_existente',return_value=Path('/fixture'))
        p.start();self.addCleanup(p.stop)

    def test_primeira_amostra_nao_inventa_percentual_cpu(self):
        estado=nucleo.resumo_status()
        self.assertIsNone(estado['cpu_percentual'])
        self.assertEqual(estado['ram_percentual'],42.5)
        self.psutil.cpu_percent.assert_not_called()
        self.psutil.cpu_times.assert_called_once_with()

    def test_delta_windows_e_cache_entre_requisicoes(self):
        self.relogio.side_effect=[0,0.1,0.5,0.6]
        self.psutil.cpu_times.side_effect=[TemposWindows(100,20,100),TemposWindows(130,30,140)]
        self.assertIsNone(nucleo._uso_cpu(self.psutil))
        self.assertIsNone(nucleo._uso_cpu(self.psutil))
        self.assertEqual(nucleo._uso_cpu(self.psutil),50)
        self.assertEqual(nucleo._uso_cpu(self.psutil),50)
        self.assertEqual(self.psutil.cpu_times.call_count,2)
        self.psutil.cpu_percent.assert_not_called()

    def test_linux_nao_conta_guest_duas_vezes_e_iowait_e_ocioso(self):
        self.relogio.side_effect=[0,1]
        self.psutil.cpu_times.side_effect=[TemposLinux(20,5,10,50,5,4,1),TemposLinux(40,10,20,70,10,8,2)]
        self.assertIsNone(nucleo._uso_cpu(self.psutil))
        self.assertEqual(nucleo._uso_cpu(self.psutil),58.3)

    def test_segunda_thread_reaproveita_base_agregada(self):
        self.relogio.side_effect=[0,1]
        self.psutil.cpu_times.side_effect=[TemposWindows(100,20,100),TemposWindows(130,30,140)]
        self.assertIsNone(nucleo._uso_cpu(self.psutil))
        resultado=[]
        thread=threading.Thread(target=lambda:resultado.append(nucleo._uso_cpu(self.psutil)))
        thread.start();thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(resultado,[50])

    def test_contadores_invalidos_ou_falha_de_so_nao_impedem_resumo(self):
        erros=[OSError('fixture'),RuntimeError('fixture')]
        invalidos=[TemposWindows(-1,20,100),TemposWindows(float('nan'),20,100),
                   TemposWindows(float('inf'),20,100),TemposWindows(True,20,100),
                   SimpleNamespace(_asdict=lambda:{'user':10,'idle':'inválido'}),
                   SimpleNamespace(_asdict=lambda:{'user':10})]
        for valor in erros+invalidos:
            with self.subTest(valor=type(valor).__name__):
                nucleo._CPU_ESTADO.update(instante=None,total=None,ocioso=None,percentual=None)
                self.psutil.cpu_times.side_effect=valor if isinstance(valor,Exception) else None
                self.psutil.cpu_times.return_value=valor
                estado=nucleo.resumo_status()
                self.assertIsNone(estado['cpu_percentual'])
                self.assertEqual(estado['ram_percentual'],42.5)
                self.assertEqual(estado['disco_livre_mb'],4096)

    def test_contador_ou_relogio_regrediu_nao_inventa_cpu(self):
        for segundo,tempos in [(1,TemposWindows(90,20,90)),(-1,TemposWindows(130,30,140)),
                                (1,TemposWindows(90,20,150)),(1,TemposWindows(100,20,100))]:
            with self.subTest(segundo=segundo,tempos=tempos):
                nucleo._CPU_ESTADO.update(instante=None,total=None,ocioso=None,percentual=None)
                self.relogio.side_effect=[0,segundo]
                self.psutil.cpu_times.side_effect=[TemposWindows(100,20,100),tempos]
                self.assertIsNone(nucleo._uso_cpu(self.psutil))
                self.assertIsNone(nucleo._uso_cpu(self.psutil))

    def test_ram_invalida_ou_indisponivel_e_reportada_como_nao_disponivel(self):
        for valor in (None,'42',True,-1,101,float('nan'),float('inf')):
            with self.subTest(valor=valor):
                self.psutil.virtual_memory.return_value=SimpleNamespace(percent=valor)
                self.assertIsNone(nucleo.resumo_status()['ram_percentual'])
        self.psutil.virtual_memory.side_effect=OSError('fixture')
        self.assertIsNone(nucleo.resumo_status()['ram_percentual'])

    def test_dependencia_ausente_mantem_esquema_sem_metricas(self):
        with patch.dict(sys.modules,{'psutil':None}):
            estado=nucleo.resumo_status()
        self.assertIsNone(estado['cpu_percentual'])
        self.assertIsNone(estado['ram_percentual'])
        self.assertEqual(set(estado),{'concluidas','total_tarefas','saldo','cpu_percentual',
            'ram_percentual','comandos','disco_livre_mb','agua','robotask_total'})

    def test_snapshots_reutilizados_nao_leem_vida_ou_robotask_novamente(self):
        vida={'rotina':[{'status':'Concluído'},{'status':'Pendente'}],
              'financeiro':{'saldo':10.5},'habitos_saude':{'Agua_Copos':{'valor':2}}}
        catalogo={'tarefas':[{'nome':'fixture1'},{'nome':'fixture2'}]}
        antes=copy.deepcopy((vida,catalogo))
        self.vida.side_effect=AssertionError('Snapshot de vida já fornecido.')
        self.ler.side_effect=lambda nome,padrao: {'total_comandos_executados':7} if nome=='base_auto_aprendizado.json' else (_ for _ in ()).throw(AssertionError(nome))
        estado=nucleo.resumo_status(dados_vida=vida,dados_robotask=catalogo)
        self.assertEqual((estado['concluidas'],estado['total_tarefas'],estado['saldo'],estado['agua'],estado['robotask_total'],estado['comandos']),(1,2,10.5,2,2,7))
        self.assertEqual((vida,catalogo),antes)
        self.vida.assert_not_called()
        self.ler.assert_called_once_with('base_auto_aprendizado.json',{})

    def test_sem_snapshots_preserva_leituras_normais(self):
        nucleo.resumo_status()
        self.vida.assert_called_once_with()
        self.assertEqual([c.args[0] for c in self.ler.call_args_list],
                         ['robotask_conhecimento.json','base_auto_aprendizado.json'])

    def test_snapshots_invalidos_nao_sao_aceitos(self):
        for vida,catalogo in (([],{}),({},[])):
            with self.subTest(vida=vida,catalogo=catalogo):
                with self.assertRaises(ValueError):
                    nucleo.resumo_status(dados_vida=vida,dados_robotask=catalogo)


if __name__=='__main__':unittest.main()
