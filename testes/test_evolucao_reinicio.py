import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import nucleo
import evolucao_segura as evol
import reinicio_seguro as reboot
import assistente_pc as app

class AutoMelhoriaTeste(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.p=patch.object(nucleo,'DADOS',Path(self.tmp.name));self.p.start()
        for nome,obj in [('gestao_vida.json',{'rotina':[],'financeiro':{'saldo':1},'habitos_saude':{}}),
                         ('minhas_macros.json',{}),('base_auto_aprendizado.json',{'total_comandos_executados':0})]:
            nucleo.gravar_json(nome,obj)
    def tearDown(self):self.p.stop();self.tmp.cleanup()
    def test_analise_nao_muda_codigo(self):
        antes=(nucleo.BASE/'assistente_pc.py').read_bytes()
        x=evol.analisar()
        self.assertTrue(x['verificacoes_ok']>=3)
        self.assertEqual(x['modo'],'inspecao_sem_alteracao')
        self.assertEqual((nucleo.BASE/'assistente_pc.py').read_bytes(),antes)
        self.assertTrue((nucleo.DADOS/'ultima_autoanalise.json').exists())
    def test_backup_redige_segredos(self):
        import zipfile
        segredinho="sk-proj-"+"Q"*35
        nucleo.gravar_json("minhas_macros.json",{"teste":{"chave":segredinho}})
        destino=evol.melhorar(("backup",))["backup"]
        with zipfile.ZipFile(destino) as z:
            self.assertNotIn(segredinho,z.read("minhas_macros.json").decode("utf-8"))

    def test_melhoria_faz_backup_e_notebook(self):
        antes=nucleo.vida()
        r=evol.melhorar(('notebook','backup'))
        self.assertFalse(r['codigo_modificado'])
        self.assertTrue(Path(r['backup']).exists())
        self.assertTrue((nucleo.DADOS/'analise_autonoma_rotina.ipynb').exists())
        self.assertEqual(nucleo.vida(),antes)
    def test_sem_codigo_dinamico(self):
        with self.assertRaises(ValueError):evol.melhorar(('codigo_python_arbitrario',))
        self.assertFalse((nucleo.DADOS/'backups').exists())
    def test_detecta_json_invalido_e_nao_aplica(self):
        (nucleo.DADOS/'gestao_vida.json').write_text('{erro',encoding='utf-8')
        with self.assertLogs(nucleo._LOG,level='ERROR') as logs:
            r=evol.analisar()
        self.assertTrue(any(x['alvo']=='gestao_vida.json' for x in r['problemas']))
        self.assertTrue(any('gestao_vida.json' in item for item in logs.output))
        with self.assertLogs(nucleo._LOG,level='ERROR'),self.assertRaises(RuntimeError):evol.melhorar()
    def test_pedidos_naturais(self):
        self.assertEqual(nucleo.classificar_texto('arrume e melhore'),'pedido_melhoria')
        self.assertEqual(nucleo.classificar_texto('reinicie o windows'),'pedido_reinicio_windows')
        self.assertIn('/reiniciar_windows',app.interpretar_comando('reinicie o pc'))
    def test_reinicio_win_requer_ativacao(self):
        with patch.dict(os.environ,{'REINICIO_WINDOWS_HABILITADO':'0'}),patch.object(reboot.os,'name','nt'),patch.object(reboot.subprocess,'run') as run:
            with self.assertRaises(RuntimeError):reboot.reiniciar_windows()
            run.assert_not_called()
    def test_reinicio_win_agenda_sem_executar_aqui(self):
        with patch.dict(os.environ,{'REINICIO_WINDOWS_HABILITADO':'1','REINICIO_WINDOWS_ATRASO_SEG':'120'}),patch.object(reboot.os,'name','nt'),patch.object(reboot.subprocess,'run',return_value=MagicMock(returncode=0)) as run:
            r=reboot.reiniciar_windows()
            self.assertIn('120 segundos',r)
            argv=run.call_args.args[0]
            self.assertEqual(argv[:4],['shutdown.exe','/r','/t','120'])
            self.assertNotIn('/f',argv)
    def test_reinicio_win_cancelar(self):
        with patch.object(reboot.os,'name','nt'),patch.object(reboot.subprocess,'run',return_value=MagicMock(returncode=0)) as run:
            self.assertIn('cancelamento',reboot.cancelar_reinicio_windows())
            self.assertEqual(run.call_args.args[0],['shutdown.exe','/a'])

if __name__=='__main__':unittest.main()
