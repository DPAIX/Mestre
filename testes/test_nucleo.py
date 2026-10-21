import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import nucleo
from multi_ia import analisar_erro,Roteador,FalhaAPI

class NucleoTestes(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.dados_patch=patch.object(nucleo,'DADOS',Path(self.temp.name));self.dados_patch.start()
        nucleo.gravar_json('gestao_vida.json',{'rotina':[{'id':'r1','status':'Pendente'}],
           'habitos_saude':{'Agua_Copos':{'valor':2,'meta':8}},'financeiro':{'saldo':100,'custo_unitario_ru':6,'movimentacoes':[]},
           'kanban':{'A_Fazer':[]}})
    def tearDown(self):
        self.dados_patch.stop();self.temp.cleanup()
    def test_comandos_locais_nao_sao_pesquisas(self):
        self.assertEqual(nucleo.classificar_texto('arrume'),'reparo')
        self.assertEqual(nucleo.classificar_texto('pesquise engenharia naval'),'pesquisa')
        self.assertEqual(nucleo.classificar_texto('qual é a formula?'),'conversa')
    def test_persistencia_estado(self):
        self.assertEqual(nucleo.concluir_tarefa('r1'),'Concluído')
        self.assertEqual(nucleo.vida()['rotina'][0]['status'],'Concluído')
        self.assertEqual(nucleo.registrar_agua(),(3,8))
        self.assertEqual(nucleo.movimentar('saida','12,50','RU'),87.5)
        self.assertEqual(nucleo.simular_ru(4),(24,63.5))
    def test_financas_valores_invalidos(self):
        for v in [-5,0,1000000,'banana']:
            with self.assertRaises(ValueError):nucleo.movimentar('saida',v,'teste')
    def test_exportacao_remover_segredos(self):
        import zipfile
        nucleo.gravar_json('log_acoes_e_erros.json',[{'detalhes':'sk-proj-'+'A'*37}])
        arq=nucleo.exportacao_segura()
        with zipfile.ZipFile(arq) as z:
            s=z.read('log_acoes_e_erros.json').decode()
            self.assertNotIn('sk-proj-',''.join(s.split('sk-proj-')[:1]))
            self.assertNotIn('A'*37,s)
            self.assertIn('CREDENCIAL-REDACTADA',s)
    def test_migracao_preserva_destino(self):
        origem=Path(self.temp.name)/'origem';origem.mkdir()
        (origem/'gestao_vida.json').write_text('{"rotina":[],"financeiro":{"saldo":500}}')
        nucleo.migrar(origem)
        self.assertEqual(nucleo.vida()['financeiro']['saldo'],100)
    def test_erro_credito_diferente_rate_limit(self):
        a=analisar_erro('OpenAI',429,'{"error":{"code":"insufficient_quota","message":"no credits remaining"}}')
        b=analisar_erro('OpenAI',429,'{"error":{"message":"rate limit exceeded"}}')
        self.assertEqual(a.categoria,'sem_creditos')
        self.assertEqual(b.categoria,'limite_temporario')
    def test_unicodes_robotask(self):
        pasta=Path(self.temp.name)/'tasks';pasta.mkdir()
        (pasta/'abc.tsk').write_text('[Root]\nName=STRING|"Teste com Ação"\nExternalName=STRING|"Task16"\n[Actions]\nActionID=STRING|"A_MOUSE_CLICK"',encoding='utf-8')
        tasks=nucleo.catalogo_robotask(pasta)
        self.assertEqual(tasks[0]['nome'],'Teste com Ação')
        self.assertEqual(tasks[0]['external_name'],'Task16')
    def test_bot_sem_permissoes(self):
        import assistente_pc
        with patch.dict('os.environ',{'TELEGRAM_ALLOWED_USER_IDS':'1234'}):
            self.assertTrue(assistente_pc.autenticado(1234))
            self.assertFalse(assistente_pc.autenticado(1235))
    def test_rota_nao_tenta_ia_sem_chave(self):
        with patch.dict('os.environ',{'GEMINI_API_KEY':'','OPENAI_API_KEY':'','ANTHROPIC_API_KEY':''}):
            with self.assertRaises(FalhaAPI):Roteador().responder('oi')

if __name__=='__main__':unittest.main()
