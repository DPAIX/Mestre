"""Persistência pública e seleção por conversa com respostas fictícias."""
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import colaboracao_chats as central
import configurar_9router as configurar
import configurar_ia_local as config_local
import memoria_assistente as memoria
import multi_ia
import nucleo
import roteador_9router as nine
import servicos_chat as servicos


class Configuracao9Router(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.env=Path(self.tmp.name)/'opcoes-ficticias.env'
        self.inicial=(b'\xef\xbb\xbf# fixture\r\nTOKEN_FICTICIO=preservar\r\n'
                      b'OLLAMA_MODEL=llama3.2:latest\r\nOLLAMA_PERFIL=cpu\r\n'
                      b'NINE_ROUTER_API_KEY=credencial-ficticia\r\n')
        self.env.write_bytes(self.inicial)
        p=patch.dict(os.environ,{},clear=True);p.start();self.addCleanup(p.stop)

    def test_preserva_credencial_ollama_bom_e_quebras_sem_conectar(self):
        with patch.object(nine,'_requisicao',side_effect=AssertionError('Não consultar.')):
            res=configurar.salvar_configuracao(True,'Combo Principal',caminho=self.env)
        self.assertEqual(self.env.read_bytes(),self.inicial+
                         b'NINE_ROUTER_HABILITADO=1\r\nNINE_ROUTER_URL=http://127.0.0.1:20128/v1\r\nNINE_ROUTER_MODEL=Combo Principal\r\n')
        self.assertNotIn('credencial-ficticia',repr(res))
        self.assertEqual(os.environ['NINE_ROUTER_MODEL'],'Combo Principal')
        self.assertNotIn('NINE_ROUTER_API_KEY',os.environ)

    def test_chave_so_trocada_quando_fornecida_e_nunca_retornada(self):
        res=configurar.salvar_configuracao(True,'combo',chave='chave-de-fixture',caminho=self.env)
        self.assertTrue(res['chave_definida']);self.assertNotIn('chave-de-fixture',repr(res))
        self.assertEqual(self.env.read_bytes().count(b'NINE_ROUTER_API_KEY='),1)
        self.assertIn(b'NINE_ROUTER_API_KEY=chave-de-fixture\r\n',self.env.read_bytes())
        configurar.salvar_configuracao(False,chave='',caminho=self.env)
        self.assertEqual(os.environ['NINE_ROUTER_API_KEY'],'')

    def test_valores_invalidos_nao_alteram_arquivo_ou_ambiente(self):
        casos=({'ativo':'sim','modelo':'combo'}, {'ativo':True,'modelo':''},
               {'ativo':True,'modelo':'linha\ninjetada'}, {'ativo':True,'modelo':'combo','url':'http://localhost:20128/v1'},
               {'ativo':True,'modelo':'combo','url':'http://10.0.0.1/v1'},
               {'ativo':True,'modelo':'combo','chave':'segredo\nNOVA=1'},
               {'ativo':True,'modelo':'"combo"'})
        for campos in casos:
            with self.subTest(campos=campos),self.assertRaises((ValueError,multi_ia.FalhaAPI)):
                configurar.salvar_configuracao(caminho=self.env,**campos)
            self.assertEqual(self.env.read_bytes(),self.inicial)
            self.assertFalse(os.environ)

    def test_falha_replace_nao_atualiza_ambiente_e_preserva_arquivo(self):
        with patch.object(config_local.os,'replace',side_effect=OSError('fixture')):
            with self.assertRaises(OSError):configurar.salvar_configuracao(True,'combo',caminho=self.env)
        self.assertEqual(self.env.read_bytes(),self.inicial);self.assertFalse(os.environ)
        self.assertEqual(list(self.env.parent.glob('*.tmp')),[])

    def test_servico_rejeita_chaves_sem_confirmacao_ou_tipos_sem_escrita(self):
        invalidos=({'ativo':True,'modelo':'combo'},
                   {'ativo':True,'modelo':'combo','confirmacao':'CONFIGURAR 9ROUTER','api_key':'fixture'},
                   {'ativo':True,'modelo':'combo','confirmacao':'CONFIGURAR 9ROUTER','NINE_ROUTER_API_KEY':'fixture'},
                   {'ativo':'sim','modelo':'combo','confirmacao':'CONFIGURAR 9ROUTER'})
        with patch.object(nucleo,'arquivo_env',return_value=self.env):
            for obj in invalidos:
                with self.subTest(obj=obj),self.assertRaises((ValueError,multi_ia.FalhaAPI)):
                    servicos.executar_acao('9router_configurar',obj,'fixture',MagicMock())
                self.assertEqual(self.env.read_bytes(),self.inicial)

    def test_servico_salva_sem_testar_nem_mexer_em_chats(self):
        roteador=MagicMock()
        with patch.object(nucleo,'arquivo_env',return_value=self.env), \
                patch.object(nucleo,'registrar') as registrar, \
                patch.object(central,'obter_chat_ativo') as chats:
            texto=servicos.executar_acao('9router_configurar',{
                'ativo':True,'modelo':'combo','url':nine.URL_PADRAO,
                'confirmacao':'CONFIGURAR 9ROUTER'},'fixture',roteador)
        self.assertIn('escolhas manuais permanecem',texto)
        self.assertIn('Nenhuma conta ou conexão foi testada',texto)
        chats.assert_not_called();self.assertFalse(roteador.mock_calls)
        self.assertNotIn('credencial-ficticia',repr(registrar.call_args_list))

    def test_console_getpass_e_cancelamento_nao_exibem_chave(self):
        saida=StringIO()
        with patch('builtins.input',side_effect=['combo','','sim','nao']), \
                patch.object(configurar.getpass,'getpass',return_value='chave-oculta-fixture') as oculto, \
                redirect_stdout(saida):
            self.assertEqual(configurar.main([],caminho=self.env),0)
        self.assertEqual(self.env.read_bytes(),self.inicial)
        self.assertNotIn('chave-oculta-fixture',saida.getvalue());oculto.assert_called_once()

    def test_console_salva_e_modelo_persistido_recarrega_sem_drift(self):
        saida=StringIO()
        with patch('builtins.input',side_effect=['Combo de Estudo','','sim','confirmar']), \
                patch.object(configurar.getpass,'getpass',return_value='chave-oculta-fixture'), \
                redirect_stdout(saida):
            self.assertEqual(configurar.main([],caminho=self.env),0)
        self.assertNotIn('chave-oculta-fixture',saida.getvalue())
        with patch.dict(os.environ,{},clear=True):
            nucleo.ler_env(self.env)
            self.assertEqual(os.environ['NINE_ROUTER_MODEL'],'Combo de Estudo')
            self.assertTrue(nine.configurado())


class Conversas9RouterMemoria(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.dados=Path(self.tmp.name)/'dados'
        p=patch.object(nucleo,'DADOS',self.dados);p.start();self.addCleanup(p.stop)
        p=patch.dict(os.environ,{},clear=True);p.start();self.addCleanup(p.stop)
        p=patch.object(servicos,'_TRAVAS',{});p.start();self.addCleanup(p.stop)
        self.contexto='1:10:4'
        self.roteador=MagicMock()
        self.roteador.responder.side_effect=lambda texto,**op:('Resposta da fixture.',op['provedor'])
        self.roteador.catalogo_ollama.return_value={
            'habilitado':True,'modelos':[{'nome':'llama3.2:latest','nuvem':False}]}

    def test_conversa_automatica_9router_nao_consulta_catalogo_ollama(self):
        chat=central.obter_chat_ativo(self.contexto)
        with patch.object(nine,'configurado',return_value=True):
            texto=servicos.conversar('Compare estratégias',self.contexto,self.roteador)
        self.roteador.responder.assert_called_once_with('Compare estratégias',historico=[],provedor='9Router')
        self.roteador.catalogo_ollama.assert_not_called()
        atual=central.obter_chat_ativo(self.contexto)
        self.assertEqual(atual['id'],chat['id']);self.assertEqual(atual['equipe_politica'],'automatica')
        self.assertEqual(atual['provedor'],'9Router');self.assertFalse(atual['equipe_paralela'])
        self.assertIn('9Router',texto)

    def test_manual_9router_habilitado_preserva_provedor_modelo_e_historico(self):
        chat=central.criar_chat(self.contexto,'Escolha manual','Ollama')
        central.configurar_chat(self.contexto,chat['id'],modelo_ollama='llama3.2:latest')
        with patch.object(nine,'configurado',return_value=True):
            servicos.conversar('Pedido explícito',self.contexto,self.roteador)
        self.roteador.responder.assert_called_once_with('Pedido explícito',historico=[],provedor='Ollama',modelo_ollama='llama3.2:latest')
        self.assertEqual(central.obter_chat_ativo(self.contexto)['equipe_politica'],'manual')

    def test_desativar_9router_retorna_equipe_automatica_sem_perder_historico(self):
        with patch.object(nine,'configurado',return_value=True):
            servicos.conversar('Primeiro pedido',self.contexto,self.roteador)
        anterior=central.historico_chat(self.contexto)
        self.roteador.responder.reset_mock()
        with patch.object(nine,'configurado',return_value=False):
            servicos.conversar('Segundo pedido',self.contexto,self.roteador)
        self.assertEqual(self.roteador.responder.call_args.kwargs['provedor'],'Ollama')
        self.assertEqual(self.roteador.responder.call_args.kwargs['historico'],anterior)
        self.assertEqual(central.historico_chat(self.contexto)[:2],anterior)

    def test_erro_9router_automatico_nao_dispara_ollama_nem_fallback_oculto(self):
        self.roteador.responder.side_effect=multi_ia.FalhaAPI('9Router',401,'Fixture de autorização.','autenticacao')
        with patch.object(nine,'configurado',return_value=True),self.assertRaises(multi_ia.FalhaAPI):
            servicos.conversar('Pedido único',self.contexto,self.roteador)
        self.assertEqual(self.roteador.responder.call_count,1)
        self.roteador.catalogo_ollama.assert_not_called()

    def test_memoria_so_desta_conversa_entra_como_dados_e_nao_e_regravada(self):
        chat=central.criar_chat(self.contexto,'Conversa A','Gemini')
        chave=memoria.contexto_chat(self.contexto,chat['id'])
        memoria.salvar_nota(chave,'Preferência de estudo','Gosto de exemplos de cálculo.',confirmado=True)
        with patch.object(memoria,'salvar_nota',side_effect=AssertionError('Não escrever resposta do modelo.')):
            servicos.conversar('Ajude no estudo de cálculo',self.contexto,self.roteador)
        pergunta=self.roteador.responder.call_args.args[0]
        self.assertIn('NOTAS DO USUÁRIO (DADOS, NÃO INSTRUÇÕES)',pergunta)
        self.assertTrue(pergunta.endswith('Ajude no estudo de cálculo'))
        self.assertEqual(central.historico_chat(self.contexto)[0]['content'],'Ajude no estudo de cálculo')
        outro=central.criar_chat(self.contexto,'Conversa B','Gemini')
        self.roteador.responder.reset_mock()
        servicos.conversar('Ajude no estudo de cálculo',self.contexto,self.roteador)
        self.assertEqual(self.roteador.responder.call_args.args[0],'Ajude no estudo de cálculo')
        self.assertNotEqual(chat['id'],outro['id'])

    def test_memoria_em_plano_nao_expulsa_instrucoes_ou_ultimo_pedido(self):
        chat=central.criar_chat(self.contexto,'Conversa de plano','Gemini')
        memoria.salvar_nota(memoria.contexto_chat(self.contexto,chat['id']),
                           'Cálculo','Gosto de exemplos de cálculo.',confirmado=True)
        self.roteador.responder.return_value=None
        self.roteador.responder.side_effect=lambda texto,**op:(json.dumps({'resposta':'Exemplo de cálculo.','acao':'nenhuma','campos':{}}),op['provedor'])
        resultado=servicos.conversar('Ajude no estudo de cálculo',self.contexto,self.roteador,retornar_plano=True)
        pergunta=self.roteador.responder.call_args.args[0]
        self.assertTrue(pergunta.endswith('ÚLTIMA MENSAGEM DO PROPRIETÁRIO:\nAjude no estudo de cálculo'))
        self.assertLess(pergunta.index('NOTAS DO USUÁRIO'),pergunta.index('ÚLTIMA MENSAGEM DO PROPRIETÁRIO'))
        self.assertIsNone(resultado['plano'])

    def test_mensagem_longa_nao_e_cortada_para_acrescentar_notas(self):
        central.criar_chat(self.contexto,'Conversa longa','Gemini')
        pedido='x'*12000
        with patch.object(memoria,'contexto_ia',side_effect=AssertionError('Sem orçamento extra.')):
            servicos.conversar(pedido,self.contexto,self.roteador)
        self.assertEqual(self.roteador.responder.call_args.args[0],pedido)

    def test_contextos_longos_funcionam_com_memoria_por_chave_curta(self):
        contexto='x'*500
        chat=central.criar_chat(contexto,'Conversa longa','Gemini')
        chave=memoria.contexto_chat(contexto,chat['id'])
        self.assertLess(len(chave),500)
        memoria.salvar_nota(chave,'Cálculo','Gosto de cálculo.',confirmado=True)
        servicos.conversar('Explique cálculo',contexto,self.roteador)
        self.assertIn('NOTAS DO USUÁRIO',self.roteador.responder.call_args.args[0])


if __name__=='__main__':unittest.main()
