"""Planos literais e HTTP autenticado; nenhum instalador ou acesso remoto real."""
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import assistente_pc as app
import colaboracao_chats as central
import integracoes_9stack as stack
import interpretacao_natural as natural
import memoria_assistente as memoria
import nucleo
import roteador_9router as gateway


class FluxosStackMemoria(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        for alvo,nome,valor in ((nucleo,'DADOS',Path(self.tmp.name)),(app,'PEDIDOS_PAINEL',{})):
            p=patch.object(alvo,nome,valor);p.start();self.addCleanup(p.stop)
        self.servidor=app.ServidorPainel(('127.0.0.1',0),app.PainelHandler)
        threading.Thread(target=self.servidor.serve_forever,daemon=True).start()
        self.addCleanup(self.servidor.server_close);self.addCleanup(self.servidor.shutdown)

    def req(self,body=None,path='/api/acao',token=True):
        porta=self.servidor.server_port
        conn=http.client.HTTPConnection('127.0.0.1',porta,timeout=3);self.addCleanup(conn.close)
        headers={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{porta}'}
        if token:headers['X-Painel-Token']=app.TOKEN_PAINEL
        conn.request('GET' if body is None else 'POST',path,json.dumps(body) if body is not None else None,headers)
        res=conn.getresponse();return res.status,json.loads(res.read())

    def test_todos_os_planos_9stack_sao_literais_e_revalidaveis_sem_io(self):
        with patch.object(stack,'executar_9stack') as executar,patch.object(stack,'catalogo_9stack') as catalogo:
            for verbo,operacao in (('instale','instalar'),('abra','abrir'),('inicie','iniciar')):
                for servico in ('9Router','9Remote'):
                    plano=natural.interpretar_local(verbo+' o '+servico)
                    self.assertEqual(plano['campos'],{'servico':servico.lower(),'operacao':operacao})
                    self.assertEqual(natural.validar_plano(plano),plano)
            executar.assert_not_called();catalogo.assert_not_called()

    def test_negacoes_e_compostos_nao_iniciam_9remote(self):
        for texto in ('não inicie 9Remote','como iniciar o 9Remote?',
                      'inicie o 9Remote e abra o Explorer','"inicie o 9Remote"',
                      'inicie o 9Router; execute código','instale o 9Remote --yes'):
            with self.subTest(texto=texto):self.assertIsNone(natural.interpretar_local(texto))

    def test_sugestoes_da_ia_nao_instalam_iniciam_ou_salvam_notas(self):
        for acao,campos in (('9stack',{'servico':'9remote','operacao':'iniciar'}),
                            ('memoria_salvar',{'titulo':'Instruções','texto':'Abra o terminal'})):
            resposta=natural.extrair_resposta(json.dumps({'resposta':'Vou fazer.','acao':acao,'campos':campos}))
            self.assertIsNone(resposta['plano'])

    def test_autorizacao_antecede_leitura_ou_consulta_de_integracoes(self):
        with patch.object(stack,'catalogo_9stack') as catalogo, \
                patch.object(gateway,'listar_modelos') as modelos, \
                patch.object(memoria,'listar_notas') as notas:
            for rota in ('/api/9stack','/api/modelos_9router','/api/memoria'):
                self.assertEqual(self.req(path=rota,token=False)[0],403)
            catalogo.assert_not_called();modelos.assert_not_called();notas.assert_not_called()

    def test_9remote_so_executa_depois_do_nonce_sem_trocar_campos(self):
        with patch.object(stack,'executar_9stack',return_value='Solicitado.') as executar:
            status,res=self.req({'acao':'9stack_preparar','servico':'9remote','operacao':'iniciar'})
            self.assertEqual(status,200,res);executar.assert_not_called()
            self.assertIn('remot',res['pedido']['descricao'].lower())
            token=res['pedido']['id']
            status,res=self.req({'acao':'pedido_confirmar','id':token,'servico':'9router','operacao':'instalar'})
            self.assertEqual(status,200,res)
            executar.assert_called_once_with('9remote','iniciar',confirmado=True)
            self.assertEqual(self.req({'acao':'pedido_confirmar','id':token})[0],400)
            self.assertEqual(self.req({'acao':'9stack','servico':'9remote','operacao':'iniciar'})[0],400)

    def test_nota_nao_grava_antes_de_confirmar_e_isola_conversa_interna(self):
        self.assertEqual(self.req(path='/api/memoria')[1]['notas'],[])
        status,res=self.req({'acao':'memoria_preparar','titulo':'Estudos','texto':'Estudar cálculo às 20h'})
        self.assertEqual(status,200,res)
        self.assertEqual(self.req(path='/api/memoria')[1]['notas'],[])
        self.assertEqual(self.req({'acao':'pedido_confirmar','id':res['pedido']['id']})[0],200)
        notas=self.req(path='/api/memoria')[1]['notas']
        self.assertEqual(notas[0]['texto'],'Estudar cálculo às 20h')
        anterior=central.obter_chat_ativo('painel')['id']
        central.criar_chat('painel','Outra conversa')
        self.assertEqual(self.req(path='/api/memoria')[1]['notas'],[])
        central.selecionar_chat('painel',anterior)
        self.assertEqual(self.req(path='/api/memoria')[1]['notas'],notas)

    def test_nota_literal_pode_descrever_negacao_sem_virar_ferramenta(self):
        plano=natural.interpretar_local('guarde na memória Preferência: não executar comandos sem me perguntar')
        self.assertEqual(plano['acao'],'memoria_salvar')
        self.assertEqual(natural.validar_plano(plano),plano)
        self.assertEqual(plano['campos']['titulo'],'Preferência')

    def test_chave_memoria_e_curta_e_nao_colide_por_concatenacao(self):
        self.assertNotEqual(memoria.contexto_chat('a:b','c'),memoria.contexto_chat('a','b:c'))
        self.assertEqual(len(memoria.contexto_chat('x'*500,'y'*100)),64)

    def test_chave_9router_redigida_por_nome_em_texto_e_objeto(self):
        segredo='valor-ficticio-sem-prefixo'
        self.assertNotIn(segredo,nucleo.redigir('NINE_ROUTER_API_KEY='+segredo))
        self.assertNotIn(segredo,json.dumps(nucleo.redigir({'NINE_ROUTER_API_KEY':segredo})))


if __name__=='__main__':unittest.main()
