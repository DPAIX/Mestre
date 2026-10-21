"""Diagnóstico local e falhas externas com evidências fictícias, sem consultas remotas."""
import datetime as dt
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import evolucao_segura as evol
import nucleo


class DiagnosticoProvedores(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dados=patch.object(nucleo,'DADOS',Path(self.tmp.name))
        self.dados.start();self.addCleanup(self.dados.stop)
        self.status=patch.object(nucleo,'resumo_status',return_value={'disco_livre_mb':32768})
        self.status.start();self.addCleanup(self.status.stop)
        self.env=patch.dict(os.environ,{'TELEGRAM_TOKEN':'fixture-local','TELEGRAM_ALLOWED_USER_IDS':'1'})
        self.env.start();self.addCleanup(self.env.stop)
        self.agora=time.time()
        for nome,valor in (
            ('gestao_vida.json',{'rotina':[],'financeiro':{'saldo':0},'habitos_saude':{}}),
            ('minhas_macros.json',{}),('base_auto_aprendizado.json',{})
        ):
            nucleo.gravar_json(nome,valor)

    def evento(self,provedor='Gemini',idade=30,categoria='servidor_ocupado',codigo=503):
        return {
            'timestamp':dt.datetime.fromtimestamp(self.agora-idade,dt.timezone.utc).isoformat(),
            'acao':'api_'+provedor,'provedor':provedor,'status':'indisponivel',
            'detalhes':f'{provedor} ({codigo}/{categoria}): alta demanda simulada'
        }

    def estado(self,*,idade=30,em_pausa=True,categoria='servidor_ocupado',codigo=503,sucesso_em=None):
        return {
            'configurado':True,'em_pausa':em_pausa,'categoria':categoria,'codigo':codigo,
            'falha_em':self.agora-idade,'pausa_ate':self.agora+30 if em_pausa else self.agora-30,
            'espera_segundos':30 if em_pausa else 0,'sucesso_em':sucesso_em
        }

    def verificar_sem_recarga_recomendada(self,relatorio):
        orientacoes=' '.join(relatorio['sugestoes']).casefold()
        for trecho in ('adicione saldo','recarregue','compre créditos','adquira créditos'):
            self.assertNotIn(trecho,orientacoes)

    def test_gemini_503_e_aviso_externo_sem_erro_local(self):
        nucleo.gravar_json('log_acoes_e_erros.json',[self.evento()])
        relatorio=evol.analisar(registrar_resultado=False,estado_provedores={'Gemini':self.estado()})
        self.assertEqual(relatorio['problemas_locais'],[])
        self.assertEqual(relatorio['falhas_locais_recentes'],0)
        self.assertEqual(relatorio['falhas_externas_recentes'],1)
        self.assertEqual(relatorio['falhas_externas_pendentes'],1)
        aviso=relatorio['avisos_externos'][0]
        self.assertEqual(aviso['provedor'],'Gemini')
        self.assertEqual(aviso['categoria'],'servidor_ocupado')
        self.assertEqual(aviso['codigo'],503)
        self.assertIn('aguard',aviso['orientacao'].casefold())
        self.assertIn('/ia',aviso['orientacao'])
        self.assertNotIn('backup',aviso['orientacao'].casefold())
        self.verificar_sem_recarga_recomendada(relatorio)

    def test_creditos_antigos_nao_explica_gemini_503_atual(self):
        historico=[self.evento(provedor='OpenAI',idade=86400+i,categoria='sem_creditos',codigo=429) for i in range(7)]
        nucleo.gravar_json('log_acoes_e_erros.json',historico+[self.evento()])
        relatorio=evol.analisar(registrar_resultado=False,estado_provedores={'Gemini':self.estado()})
        self.assertEqual(relatorio['falhas_historicas'],7)
        self.assertEqual(relatorio['falhas_recentes'],1)
        self.assertEqual([a['provedor'] for a in relatorio['avisos_externos']],['Gemini'])
        self.verificar_sem_recarga_recomendada(relatorio)

    def test_fim_da_pausa_nao_confirma_recuperacao_do_provedor(self):
        nucleo.gravar_json('log_acoes_e_erros.json',[self.evento(idade=1200)])
        relatorio=evol.analisar(registrar_resultado=False,estado_provedores={'Gemini':self.estado(idade=1200,em_pausa=False)})
        self.assertEqual(relatorio['falhas_externas_recentes'],0)
        self.assertEqual(relatorio['falhas_historicas'],1)
        self.assertEqual(relatorio['falhas_externas_pendentes'],1)
        self.assertEqual(relatorio['estado_provedores']['Gemini']['situacao'],'falha_sem_nova_verificacao')
        self.assertFalse(relatorio['avisos_externos'][0]['em_pausa'])

    def test_sucesso_posterior_supera_ultima_falha_sem_garantir_online(self):
        falha=self.evento(idade=120)
        sucesso={
            'timestamp':dt.datetime.fromtimestamp(self.agora-30,dt.timezone.utc).isoformat(),
            'acao':'pergunta','provedor':'Gemini','status':'sucesso','detalhes':'consulta simulada'
        }
        nucleo.gravar_json('log_acoes_e_erros.json',[falha,sucesso])
        estado=self.estado(idade=120,em_pausa=False,sucesso_em=self.agora-30)
        relatorio=evol.analisar(registrar_resultado=False,estado_provedores={'Gemini':estado})
        self.assertEqual(relatorio['falhas_recentes'],1)
        self.assertEqual(relatorio['falhas_externas_pendentes'],0)
        self.assertEqual(relatorio['avisos_externos'],[])
        self.assertEqual(relatorio['estado_provedores']['Gemini']['situacao'],'sucesso_na_ultima_consulta')

    def test_sucesso_anterior_nao_supera_falha_mais_recente(self):
        nucleo.gravar_json('log_acoes_e_erros.json',[self.evento()])
        estado=self.estado(sucesso_em=self.agora-300)
        relatorio=evol.analisar(registrar_resultado=False,estado_provedores={'Gemini':estado})
        self.assertEqual(relatorio['falhas_externas_pendentes'],1)
        self.assertEqual(relatorio['estado_provedores']['Gemini']['situacao'],'falha_sem_nova_verificacao')

    def test_estado_persistido_sem_log_recente_preserva_ultima_evidencia(self):
        nucleo.gravar_json('log_acoes_e_erros.json',[])
        relatorio=evol.analisar(registrar_resultado=False,estado_provedores={'Gemini':self.estado(idade=1200,em_pausa=False)})
        self.assertEqual(relatorio['falhas_recentes'],0)
        self.assertEqual(relatorio['falhas_externas_pendentes'],1)
        self.assertEqual(relatorio['estado_provedores']['Gemini']['situacao'],'falha_sem_nova_verificacao')

    def test_log_gravado_no_segundo_seguinte_preserva_pendencia_apos_dez_minutos(self):
        # registrar_falha salva o epoch antes do fsync; o log pode sair depois.
        horario_log=float(int(self.agora)-1200)
        evento=self.evento(idade=1200)
        evento['timestamp']=dt.datetime.fromtimestamp(horario_log,dt.timezone.utc).isoformat(timespec='seconds')
        nucleo.gravar_json('log_acoes_e_erros.json',[evento])
        estado=self.estado(idade=1200,em_pausa=False)
        estado['falha_em']=horario_log-0.05
        relatorio=evol.analisar(registrar_resultado=False,estado_provedores={'Gemini':estado})
        self.assertEqual(relatorio['falhas_externas_recentes'],0)
        self.assertEqual(relatorio['falhas_historicas'],1)
        self.assertEqual(relatorio['falhas_externas_pendentes'],1)
        self.assertEqual(relatorio['estado_provedores']['Gemini']['situacao'],'falha_sem_nova_verificacao')
        self.assertEqual(relatorio['avisos_externos'][0]['categoria'],'servidor_ocupado')
        self.assertFalse(relatorio['avisos_externos'][0]['em_pausa'])

    def test_apenas_historico_de_creditos_nao_gera_alerta_atual(self):
        nucleo.gravar_json('log_acoes_e_erros.json',[self.evento(idade=86400,categoria='sem_creditos',codigo=429)])
        relatorio=evol.analisar(registrar_resultado=False)
        self.assertEqual(relatorio['falhas_historicas'],1)
        self.assertEqual(relatorio['falhas_recentes'],0)
        self.assertEqual(relatorio['avisos_externos'],[])
        self.assertEqual(relatorio['problemas_locais'],[])
        self.verificar_sem_recarga_recomendada(relatorio)

    def test_nova_falha_substitui_causa_antiga_no_mesmo_provedor(self):
        nucleo.gravar_json('log_acoes_e_erros.json',[
            self.evento(idade=86400,categoria='sem_creditos',codigo=429),self.evento()
        ])
        relatorio=evol.analisar(registrar_resultado=False,estado_provedores={'Gemini':self.estado()})
        self.assertEqual(len(relatorio['avisos_externos']),1)
        self.assertEqual(relatorio['avisos_externos'][0]['categoria'],'servidor_ocupado')
        self.verificar_sem_recarga_recomendada(relatorio)

    def test_snapshot_mais_novo_nao_reutiliza_detalhe_do_erro_antigo(self):
        antigo=self.evento(idade=86400,categoria='sem_creditos',codigo=429)
        antigo['detalhes']='Gemini (429/sem_creditos): saldo insuficiente; marcador-obsoleto'
        nucleo.gravar_json('log_acoes_e_erros.json',[antigo])
        relatorio=evol.analisar(registrar_resultado=False,estado_provedores={'Gemini':self.estado()})
        aviso=relatorio['avisos_externos'][0]
        self.assertEqual(aviso['categoria'],'servidor_ocupado')
        self.assertEqual(aviso['codigo'],503)
        self.assertIn('503',aviso['detalhe'])
        for trecho in ('429','sem_creditos','marcador-obsoleto','saldo insuficiente'):
            self.assertNotIn(trecho,aviso['detalhe'])
        self.verificar_sem_recarga_recomendada(relatorio)

    def test_detalhe_externo_resume_causa_sem_repetir_resposta_bruta(self):
        evento=self.evento()
        evento['detalhes']='Gemini (503/servidor_ocupado): '+('marcador-resposta-bruta '*100)
        nucleo.gravar_json('log_acoes_e_erros.json',[evento])
        relatorio=evol.analisar(registrar_resultado=False,estado_provedores={'Gemini':self.estado()})
        detalhe=relatorio['avisos_externos'][0]['detalhe']
        self.assertIn('503',detalhe)
        self.assertIn('demanda',detalhe.casefold())
        self.assertNotIn('marcador-resposta-bruta',detalhe)
        self.assertNotIn('Gemini',detalhe)
        self.assertLess(len(detalhe),250)

    def test_sucesso_supera_categoria_legada_sem_timestamp(self):
        nucleo.gravar_json('log_acoes_e_erros.json',[])
        estado=self.estado(em_pausa=False,categoria='sem_creditos',codigo=429,sucesso_em=self.agora)
        estado['falha_em']=None
        relatorio=evol.analisar(registrar_resultado=False,estado_provedores={'Gemini':estado})
        self.assertEqual(relatorio['avisos_externos'],[])
        self.assertEqual(relatorio['falhas_externas_pendentes'],0)
        self.assertEqual(relatorio['estado_provedores']['Gemini']['situacao'],'sucesso_na_ultima_consulta')
        self.verificar_sem_recarga_recomendada(relatorio)

    def test_agendador_encaminha_estado_local_sem_consulta_remota(self):
        parada=MagicMock()
        parada.wait.side_effect=[False,True]
        parada.is_set.return_value=False
        snapshot={'Gemini':self.estado()}
        obter_estado=MagicMock(return_value=snapshot)
        with patch.object(evol,'analisar') as analisar,patch.object(nucleo,'registrar') as registrar:
            evol.executar_agendador(parada,obter_estado_provedores=obter_estado)
        obter_estado.assert_called_once_with()
        analisar.assert_called_once_with(estado_provedores=snapshot)
        registrar.assert_not_called()

    def test_agendador_preserva_chamada_antiga_sem_fornecedor_de_estado(self):
        parada=MagicMock()
        parada.wait.side_effect=[False,True]
        parada.is_set.return_value=False
        with patch.object(evol,'analisar') as analisar,patch.object(nucleo,'registrar') as registrar:
            evol.executar_agendador(parada)
        analisar.assert_called_once_with(estado_provedores=None)
        registrar.assert_not_called()

    def test_falha_local_continua_identificada_com_sua_causa(self):
        nucleo.gravar_json('log_acoes_e_erros.json',[{
            'timestamp':dt.datetime.fromtimestamp(self.agora-30,dt.timezone.utc).isoformat(),
            'acao':'comando','status':'falha','detalhes':"name 'chat' is not defined"
        }])
        relatorio=evol.analisar(registrar_resultado=False)
        self.assertEqual(relatorio['falhas_locais_recentes'],1)
        self.assertEqual(relatorio['falhas_externas_recentes'],0)
        self.assertEqual(relatorio['avisos_externos'],[])
        self.assertTrue(any(p['alvo']=='log: comando' and "name 'chat'" in p['detalhe'] for p in relatorio['problemas_locais']))


if __name__=='__main__':unittest.main()
