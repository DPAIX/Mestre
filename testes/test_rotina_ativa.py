"""Atividades, Kanban e lembretes com relógio controlado e dados temporários."""
from pathlib import Path
from datetime import datetime,timezone
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import nucleo
import rotina_ativa as rotina


class RotinaAtivaTeste(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.p=patch.object(nucleo,'DADOS',Path(self.tmp.name));self.p.start();self.addCleanup(self.p.stop)
        nucleo.gravar_json('gestao_vida.json',{'rotina':[],'kanban':{'A_Fazer':['Tarefa'],'Em_Andamento':[]},'financeiro':{'saldo':0}})
        self.agora=datetime(2026,10,21,15,0,tzinfo=timezone.utc)

    def ativar(self):
        with patch.object(rotina,'_agora',return_value=self.agora):
            rotina.configurar_lembretes(True,60,123,456)

    def test_crud_preserva_demais_dados(self):
        tarefa=rotina.cadastrar_tarefa('Estudar','Quarta','12:15',local='Biblioteca')
        rotina.atualizar_tarefa(tarefa['id'],atividade='Revisar')
        self.assertEqual(nucleo.vida()['rotina'][0]['atividade'],'Revisar')
        self.assertEqual(nucleo.vida()['financeiro']['saldo'],0)
        self.assertTrue(rotina.remover_tarefa(tarefa['id']))
        self.assertFalse(rotina.remover_tarefa(tarefa['id']))

    def test_dados_invalidos_nao_gravam(self):
        antes=nucleo.vida()
        for dia,hora in [('diaqualquer','12:00'),('2026-02-30','12:00'),('Segunda','25:00')]:
            with self.subTest(dia=dia,hora=hora),self.assertRaises(ValueError):rotina.cadastrar_tarefa('Teste',dia,hora)
        self.assertEqual(nucleo.vida(),antes)

    def test_kanban_move_sem_duplicar(self):
        rotina.mover_kanban('A_Fazer',0,'Em_Andamento')
        self.assertEqual(nucleo.vida()['kanban'],{'A_Fazer':[],'Em_Andamento':['Tarefa']})
        with self.assertRaises(ValueError):rotina.mover_kanban('A_Fazer',0,'Em_Andamento')

    def test_lembretes_desativados_por_padrao(self):
        rotina.cadastrar_tarefa('Teste','Quarta','12:15')
        self.assertEqual(rotina.processar_lembretes(self.agora),[])

    def test_antecedencia_e_horario_sao_deduplicados(self):
        from datetime import timedelta
        rotina.cadastrar_tarefa('Teste','Quarta','12:15')
        self.ativar()
        eventos=rotina.processar_lembretes(self.agora)
        self.assertEqual(len(eventos),1)
        self.assertIn('15 minutos',eventos[0]['texto'])
        self.assertEqual(eventos[0]['chat_id'],123)
        rotina.confirmar_envio(eventos[0]['chave'],True)
        self.assertEqual(rotina.processar_lembretes(self.agora),[])
        pontual=rotina.processar_lembretes(self.agora+timedelta(minutes=15))
        self.assertEqual(len(pontual),1)
        self.assertIn('Agora',pontual[0]['texto'])

    def test_agua_so_apos_intervalo_e_sem_tempestade_apos_parada(self):
        from datetime import timedelta
        self.ativar()
        self.assertEqual(rotina.processar_lembretes(self.agora),[])
        eventos=rotina.processar_lembretes(self.agora+timedelta(hours=3))
        self.assertEqual(len(eventos),1)
        self.assertIn('água',eventos[0]['texto'])

    def test_ativacao_exige_destino_e_autorizacao(self):
        with self.assertRaises(ValueError):rotina.configurar_lembretes(True)
        self.ativar()
        rotina.configurar_lembretes(False)
        self.assertEqual(rotina.processar_lembretes(self.agora),[])


if __name__=='__main__':unittest.main()
