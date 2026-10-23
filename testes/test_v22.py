"""Regressões para os problemas encontrados nas capturas da v2.1."""
import datetime as dt
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import nucleo
import assistente_pc as app
import evolucao_segura as evo
import multi_ia
from verificacao_ambiente import verificar

class TesteV22(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.p=patch.object(nucleo,'DADOS',Path(self.tmp.name));self.p.start()
        nucleo.gravar_json('gestao_vida.json',{'rotina':[],'financeiro':{'saldo':100},'habitos_saude':{}})
        nucleo.gravar_json('minhas_macros.json',{})
        nucleo.gravar_json('base_auto_aprendizado.json',{'frequencia_acoes':{}})
        nucleo.gravar_json('robotask_conhecimento.json',{'tarefas':[]})
    def tearDown(self):self.p.stop();self.tmp.cleanup()
    def test_peca_desligamento_negada_sem_api(self):
        for texto in ('desligar computador','desligue o pc','shutdown /s','desligar o windows'):
            self.assertEqual(nucleo.classificar_texto(texto),'desligamento_bloqueado')
            with patch.object(app.ROTEADOR,'responder',side_effect=AssertionError('não deve chegar à IA')):
                self.assertIn('não oferece desligamento',app.interpretar_comando(texto))
    def test_avisos_historicos_nao_sao_falhas_ativas(self):
        passado=(dt.datetime.now()-dt.timedelta(days=4)).isoformat()
        nucleo.gravar_json('log_acoes_e_erros.json',[
            {'timestamp':passado,'acao':'api_Gemini','status':'indisponivel','detalhes':'servidor'} for _ in range(3)])
        relatorio=evo.analisar(registrar_resultado=False)
        self.assertEqual(relatorio['falhas_recentes'],0)
        self.assertEqual(relatorio['falhas_historicas'],3)
        self.assertNotIn('falhas_ativas',[p['alvo'] for p in relatorio['problemas']])
    def test_erro_muito_recente_consta_na_analise(self):
        recente=dt.datetime.now().isoformat(timespec='seconds')
        nucleo.gravar_json('log_acoes_e_erros.json',[
            {'timestamp':recente,'acao':'api_Claude','status':'falha','detalhes':'sem_creditos'}])
        r=evo.analisar(registrar_resultado=False)
        self.assertEqual(r['falhas_recentes'],1)
        self.assertTrue(any('créditos' in s for s in r['sugestoes']))
    def test_repetir_melhoria_nao_gera_novo_backup(self):
        # Simula Windows com catálogo existente, sem acionar tarefas.
        windows=SimpleNamespace(name='nt',environ=os.environ,path=os.path,replace=os.replace)
        with patch.object(evo,'os',windows),patch('evolucao_segura.nucleo.catalogo_robotask',return_value=[]):
            a=evo.melhorar(); b=evo.melhorar()
        self.assertFalse(a['sem_alteracoes'])
        self.assertTrue(b['sem_alteracoes'])
        self.assertEqual(len(list((nucleo.DADOS/'backups').glob('*.zip'))),1)
        self.assertIn('já atualizado',app.texto_melhorias(b))
    def test_mudanca_dados_produz_novo_backup(self):
        windows=SimpleNamespace(name='nt',environ=os.environ,path=os.path,replace=os.replace)
        with patch.object(evo,'os',windows),patch('evolucao_segura.nucleo.catalogo_robotask',return_value=[]):
            evo.melhorar()
            d=nucleo.vida();d['financeiro']['saldo']=122.0;nucleo.gravar_json('gestao_vida.json',d)
            b=evo.melhorar()
        self.assertFalse(b['sem_alteracoes'])
        self.assertEqual(len(list((nucleo.DADOS/'backups').glob('*.zip'))),2)
    def test_suspensao_por_credito_resiste_reinicio(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'somente-para-teste','GEMINI_API_KEY':'','ANTHROPIC_API_KEY':'','EXA_API_KEY':''}):
            roteador=multi_ia.Roteador()
            self.assertEqual(roteador.status()['Gemini'],'sem chave')
            self.assertEqual(roteador.status()['OpenAI'],'configurado; não testado')
            roteador.registrar_falha(multi_ia.FalhaAPI('OpenAI',429,'créditos esgotados','sem_creditos'))
            recarregado=multi_ia.Roteador()
            self.assertIn('sem créditos',recarregado.status()['OpenAI'])
    def test_reativacao_manual_apos_creditos(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'teste'}):
            roteador=multi_ia.Roteador()
            roteador.registrar_falha(multi_ia.FalhaAPI('OpenAI',429,'sem crédito','sem_creditos'))
            self.assertIn('sem créditos',roteador.status()['OpenAI'])
            self.assertIn('pausa(s) locais removidas',roteador.reativar())
            self.assertEqual(roteador.status()['OpenAI'],'configurado; não testado')
            self.assertEqual(nucleo.ler_json('estado_ia.json',{}),{})
    def test_verificador_nao_chama_api_e_nao_revela_chave(self):
        segredo='sk-proj-'+'X'*35
        with patch.dict(os.environ,{'OPENAI_API_KEY':segredo,'GEMINI_API_KEY':'','ANTHROPIC_API_KEY':'','EXA_API_KEY':''}):
            r=verificar()
        self.assertIn('OpenAI: chave definida',r['texto'])
        self.assertNotIn(segredo,r['texto'])
        self.assertIn('não',r['texto'].lower())
    def test_documento_painel_sem_opcao_desligar(self):
        html=(nucleo.BASE/'painel_rotina.html').read_text(encoding='utf8')
        self.assertIn('v2.7.0',html)
        self.assertNotIn('Desligar computador',html)
        self.assertNotIn('shutdown /s',html)
        self.assertIn('🔎 Verificar configuração',html)

if __name__=='__main__':unittest.main()
