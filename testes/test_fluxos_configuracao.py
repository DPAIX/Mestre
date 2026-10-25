"""Configuração local autenticada não depende da geração de modelos."""
import http.client
import json
from pathlib import Path
import os
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import assistente_pc as app
import colaboracao_chats as central
import configuracao_assistente as config
import nucleo


class FluxosConfiguracao(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        for alvo,nome,valor in ((nucleo,'DADOS',Path(self.tmp.name)),(app,'PENDENTES',{}),
                                (app,'PEDIDOS_PAINEL',{}),(app,'BOT',MagicMock()),
                                (app,'inline',MagicMock(return_value=None))):
            p=patch.object(alvo,nome,valor);p.start();self.addCleanup(p.stop)
        p=patch.dict(os.environ,{'TELEGRAM_ALLOWED_USER_IDS':'1'},clear=True)
        p.start();self.addCleanup(p.stop)
        p=patch.object(app.SERVICOS,'conversar',side_effect=AssertionError('Configuração não usa IA.'))
        self.conversar=p.start();self.addCleanup(p.stop)
        p=patch.object(config,'abrir_configuracao',return_value='Configuração aberta na janela do PC.')
        self.abrir=p.start();self.addCleanup(p.stop)

    def mensagem(self,texto,usuario=1,topico=4):
        return SimpleNamespace(text=texto,from_user=SimpleNamespace(id=usuario),
                               chat=SimpleNamespace(id=10),message_thread_id=topico)

    def servidor(self):
        self.http=app.ServidorPainel(('127.0.0.1',0),app.PainelHandler)
        threading.Thread(target=self.http.serve_forever,daemon=True).start()
        self.addCleanup(self.http.server_close);self.addCleanup(self.http.shutdown)

    def req(self,body=None,path='/api/acao',token=True):
        porta=self.http.server_port
        conn=http.client.HTTPConnection('127.0.0.1',porta,timeout=3);self.addCleanup(conn.close)
        headers={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{porta}'}
        if token:headers['X-Painel-Token']=app.TOKEN_PAINEL
        conn.request('GET' if body is None else 'POST',path,json.dumps(body) if body is not None else None,headers)
        res=conn.getresponse();return res.status,json.loads(res.read())

    def test_frase_da_captura_prepara_sem_consultar_ollama_e_confirma_uma_vez(self):
        with patch.object(app.ROTEADOR,'catalogo_ollama') as catalogo:
            app.tratar_pedido(self.mensagem('faça as configurações necessárias'))
        self.assertEqual(len(app.PENDENTES),1)
        pend=next(iter(app.PENDENTES.values()))
        self.assertEqual(pend['dados']['plano']['acao'],'configurar_assistente')
        self.assertEqual(pend['dados']['contexto'],'1:10:4')
        self.abrir.assert_not_called();self.conversar.assert_not_called();catalogo.assert_not_called()
        self.assertTrue(app.confirmar_pedido_por_texto(self.mensagem('sim'),'sim'))
        self.abrir.assert_called_once_with(confirmado=True)
        self.assertFalse(app.confirmar_pedido_por_texto(self.mensagem('sim'),'sim'))

    def test_botao_principal_usa_o_mesmo_pedido_local(self):
        app.tratar_pedido(self.mensagem(app.MENU_BOTOES[17]))
        self.assertEqual(next(iter(app.PENDENTES.values()))['dados']['plano']['acao'],'configurar_assistente')
        self.abrir.assert_not_called();self.conversar.assert_not_called()

    def test_usuario_nao_autorizado_nao_prepara_e_outro_topico_nao_confirma(self):
        app.tratar_pedido(self.mensagem('faça as configurações necessárias',usuario=2))
        self.assertFalse(app.PENDENTES)
        app.tratar_pedido(self.mensagem('configure o assistente'))
        self.assertFalse(app.confirmar_pedido_por_texto(self.mensagem('sim',topico=5),'sim'))
        self.assertTrue(app.confirmar_pedido_por_texto(self.mensagem('cancele'),'cancele'))
        self.abrir.assert_not_called()

    def test_consulta_local_nao_abre_ou_exige_modelos(self):
        with patch.object(config,'resumo_configuracao',return_value='Diagnóstico local fictício.') as resumo:
            resultado=app.preparar_pedido_natural('mostre a configuração do assistente','1:10:4')
        self.assertEqual(resultado['mensagem'],'Diagnóstico local fictício.')
        self.assertIsNone(resultado['plano']);resumo.assert_called_once_with()
        self.abrir.assert_not_called();self.conversar.assert_not_called()

    def test_http_autorizacao_antes_do_diagnostico(self):
        self.servidor()
        with patch.object(config,'resumo_configuracao',return_value='Diagnóstico local.') as resumo:
            self.assertEqual(self.req(path='/api/configuracao',token=False)[0],403)
            resumo.assert_not_called()
            status,res=self.req(path='/api/configuracao')
            self.assertEqual(status,200);self.assertEqual(res['mensagem'],'Diagnóstico local.')
        self.abrir.assert_not_called()

    def test_http_so_executa_nonce_guardado_na_conversa_correta(self):
        self.servidor()
        status,res=self.req({'acao':'configuracao_preparar'})
        self.assertEqual(status,200,res);self.abrir.assert_not_called()
        token=res['pedido']['id'];anterior=central.obter_chat_ativo('painel')['id']
        central.criar_chat('painel','Outra conversa')
        self.assertEqual(self.req({'acao':'pedido_confirmar','id':token})[0],400)
        self.abrir.assert_not_called()
        central.selecionar_chat('painel',anterior)
        status,res=self.req({'acao':'pedido_confirmar','id':token,'campos':{'remoto':True}})
        self.assertEqual(status,200,res);self.abrir.assert_called_once_with(confirmado=True)
        self.assertEqual(self.req({'acao':'pedido_confirmar','id':token})[0],400)

    def test_http_abertura_direta_ou_cancelamento_nao_executa(self):
        self.servidor()
        self.assertEqual(self.req({'acao':'configurar_assistente','confirmado':True})[0],400)
        status,res=self.req({'acao':'configuracao_preparar'})
        self.assertEqual(status,200)
        self.assertEqual(self.req({'acao':'pedido_cancelar','id':res['pedido']['id']})[0],200)
        self.abrir.assert_not_called();self.conversar.assert_not_called()


if __name__=='__main__':unittest.main()
