"""Integrações autenticadas e contribuições provisórias, sem agentes reais."""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import assistente_pc as app
import colaboracao_chats as central
import integracoes_agentes as agentes
import nucleo
import servicos_chat as servicos


class FluxosAgentes(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        for alvo,nome,valor in (
                (nucleo,'DADOS',Path(self.tmp.name)),(app,'PENDENTES',{}),
                (app,'PEDIDOS_PAINEL',{}),(app,'BOT',MagicMock()),
                (app,'inline',MagicMock(return_value=None)),
                (servicos,'_TRAVAS',{})):
            p=patch.object(alvo,nome,valor);p.start();self.addCleanup(p.stop)
        p=patch.dict(os.environ,{'TELEGRAM_ALLOWED_USER_IDS':'1'},clear=True)
        p.start();self.addCleanup(p.stop)
        self.contexto='1:10:4'
        self.chat=central.criar_chat(self.contexto,'Conversa de teste','Ollama')
        self.abrir=patch.object(agentes,'abrir_agente',return_value='Janela solicitada.')
        self.lancamento=self.abrir.start();self.addCleanup(self.abrir.stop)

    def mensagem(self,texto,usuario=1,topico=4):
        return SimpleNamespace(text=texto,chat=SimpleNamespace(id=10),
                               from_user=SimpleNamespace(id=usuario),message_thread_id=topico)

    def iniciar_http(self):
        servidor=app.ServidorPainel(('127.0.0.1',0),app.PainelHandler)
        self.servidor=servidor
        threading.Thread(target=servidor.serve_forever,daemon=True).start()
        self.addCleanup(servidor.server_close);self.addCleanup(servidor.shutdown)

    def req(self,body=None,path='/api/acao',token=True):
        porta=self.servidor.server_port
        conn=http.client.HTTPConnection('127.0.0.1',porta,timeout=3)
        self.addCleanup(conn.close)
        headers={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{porta}'}
        if token:headers['X-Painel-Token']=app.TOKEN_PAINEL
        conn.request('GET' if body is None else 'POST',path,
                     json.dumps(body) if body is not None else None,headers)
        res=conn.getresponse();return res.status,json.loads(res.read())

    def test_frase_da_captura_responde_sem_equipe_no_telegram(self):
        with patch.object(servicos,'conversar') as conversar:
            app.tratar_pedido(self.mensagem('me diga quais as suas capacidades'))
        conversar.assert_not_called();self.lancamento.assert_not_called()
        self.assertIn('Rotina local',app.BOT.send_message.call_args.args[1])

    def test_abertura_por_texto_so_ocorre_apos_sim_uma_vez(self):
        app.tratar_pedido(self.mensagem('abra o agente Claude Code com o modelo gemma4:31b-cloud'))
        self.lancamento.assert_not_called()
        self.assertEqual(len(app.PENDENTES),1)
        pend=next(iter(app.PENDENTES.values()))
        self.assertEqual(pend['dados']['contexto'],self.contexto)
        self.assertEqual(pend['dados']['plano']['campos']['modelo'],'gemma4:31b-cloud')
        self.assertTrue(app.confirmar_pedido_por_texto(self.mensagem('sim'),'sim'))
        self.lancamento.assert_called_once_with('claude',modelo='gemma4:31b-cloud',configurar=False,confirmado=True)
        self.assertFalse(app.confirmar_pedido_por_texto(self.mensagem('sim'),'sim'))

    def test_negado_ou_outro_topico_nao_abre_agente(self):
        app.tratar_pedido(self.mensagem('abra o agente OpenCode',usuario=2))
        self.assertFalse(app.PENDENTES)
        app.tratar_pedido(self.mensagem('abra o agente OpenCode'))
        self.assertFalse(app.confirmar_pedido_por_texto(self.mensagem('sim',topico=5),'sim'))
        self.lancamento.assert_not_called()
        self.assertTrue(app.confirmar_pedido_por_texto(self.mensagem('cancele'),'cancele'))
        self.lancamento.assert_not_called()

    def test_comando_alternativo_configura_com_mesmo_plano_confirmado(self):
        app.tratar_pedido(self.mensagem('/agente configurar opencode | llama3.2:latest'))
        self.lancamento.assert_not_called()
        self.assertTrue(app.confirmar_pedido_por_texto(self.mensagem('sim'),'sim'))
        self.lancamento.assert_called_once_with('opencode',modelo='llama3.2:latest',configurar=True,confirmado=True)

    def test_catalogo_http_exige_autenticacao_antes_de_sondar_path(self):
        self.iniciar_http()
        with patch.object(agentes,'catalogo_agentes',return_value=[{'agente':'codex','nome':'Codex CLI'}]) as catalogo:
            self.assertEqual(self.req(path='/api/agentes',token=False)[0],403)
            catalogo.assert_not_called()
            status,res=self.req(path='/api/agentes')
            self.assertEqual(status,200)
            self.assertEqual(res['agentes'][0]['agente'],'codex')
            catalogo.assert_called_once_with()

    def test_painel_guarda_campos_e_executa_uma_vez_apos_confirmar(self):
        self.iniciar_http()
        status,res=self.req({'acao':'agente_preparar','agente':'codex','modelo':'gemma4:31b-cloud'})
        self.assertEqual(status,200,res);self.lancamento.assert_not_called()
        token=res['pedido']['id']
        status,res=self.req({'acao':'pedido_confirmar','id':token,'agente':'opencode','modelo':'adulterado'})
        self.assertEqual(status,200,res)
        self.lancamento.assert_called_once_with('codex',modelo='gemma4:31b-cloud',configurar=False,confirmado=True)
        self.assertEqual(self.req({'acao':'pedido_confirmar','id':token})[0],400)
        self.assertEqual(self.lancamento.call_count,1)

    def test_painel_nao_aceita_abertura_direta_e_cancelamento_nao_executa(self):
        self.iniciar_http()
        self.assertEqual(self.req({'acao':'agente_abrir','agente':'codex','confirmado':True})[0],400)
        status,res=self.req({'acao':'agente_preparar','agente':'hermes'})
        self.assertEqual(status,200)
        self.assertEqual(self.req({'acao':'pedido_cancelar','id':res['pedido']['id']})[0],200)
        self.lancamento.assert_not_called()

    def test_painel_rejeita_tipos_e_injecao_sem_preparar(self):
        self.iniciar_http()
        for campos in ({'agente':'codex; whoami'},{'agente':'codex','configurar':'sim'},
                       {'agente':'claude','modelo':'--help'},{'agente':'nao-existe'}):
            with self.subTest(campos=campos):
                self.assertEqual(self.req({'acao':'agente_preparar',**campos})[0],400)
        self.assertFalse(app.PEDIDOS_PAINEL);self.lancamento.assert_not_called()

    def test_primeira_contribuicao_e_provisoria_nao_executa_ou_confirma(self):
        central.configurar_chat(self.contexto,self.chat['id'],provedor='Ollama',
            equipe_paralela=True,equipe_modo='cooperativa',equipe_modelos=['llama3.2:latest','mistral:latest'])
        evento={'modelo':'llama3.2:latest','texto':'Proposta inicial.','respondidos':1,'total':2,'provisoria':True}
        def preparar(texto,contexto,**opcoes):
            self.assertIn('parcial',opcoes)
            opcoes['parcial'](evento);opcoes['parcial'](evento)
            self.assertFalse(app.PENDENTES);self.lancamento.assert_not_called()
            return {'mensagem':'Resposta final.','plano':None,'chat_id':self.chat['id']}
        with patch.object(app,'preparar_pedido_natural',side_effect=preparar), \
                patch.object(app,'executar_plano_natural') as executar:
            app.responder_natural_telegram(self.mensagem('Compare alternativas'),'Compare alternativas')
        textos=[c.args[1] for c in app.BOT.send_message.call_args_list]
        self.assertEqual(sum('Primeira contribuição' in x for x in textos),1)
        self.assertIn('provisória',textos[0]);self.assertEqual(textos[-1],'Resposta final.')
        executar.assert_not_called()


if __name__=='__main__':unittest.main()
