"""Fluxos novos com arquivos fictícios e clientes remotos inteiramente simulados."""
import copy
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import nucleo
import colaboracao_chats as central
import memoria_assistente as memoria
import servicos_chat as chats
import gemini_interactions as api
import servicos_gemini as jobs
import configurar_gemini as configurar
import prontidao_assistente as pronto
import roteador_9router as gateway
from multi_ia import FalhaAPI


class IntegracaoV210(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        p=patch.object(nucleo,'DADOS',Path(self.tmp.name));p.start();self.addCleanup(p.stop)
        p=patch.dict(os.environ,{'GEMINI_API_KEY':'fixture-chave-privada','GEMINI_API_MODO':'interactions','OLLAMA_HABILITADO':'1'},clear=True);p.start();self.addCleanup(p.stop)
        self.contexto='1:2:3';self.chat=central.obter_chat_ativo(self.contexto)['id']

    def test_tarefa_so_e_criada_apos_confirmacao_e_operacao_nao_repete(self):
        plano=jobs.preparar_tarefa('Compare dois algoritmos sem executar no PC.')
        with patch.object(api,'criar_tarefa',return_value={'remote_id':'remote-1','estado':'in_progress','texto':'','ambiente_id':'env-1'}) as criar:
            self.assertFalse(jobs.estado(self.contexto,self.chat)['tarefas']);criar.assert_not_called()
            jobs.executar(plano,self.contexto,self.chat);jobs.executar(plano,self.contexto,self.chat)
        criar.assert_called_once()
        self.assertEqual(len(jobs.estado(self.contexto,self.chat)['tarefas']),1)

    def test_consulta_remota_esta_isolada_por_conversa(self):
        plano=jobs.preparar_tarefa('Relatório simples.')
        with patch.object(api,'criar_tarefa',return_value={'remote_id':'remote-1','estado':'in_progress','texto':'','ambiente_id':'env-1'}):jobs.executar(plano,self.contexto,self.chat)
        outra=central.criar_chat(self.contexto,'Outra')['id']
        with patch.object(api,'consultar_tarefa') as consultar:
            with self.assertRaises(ValueError):jobs.consultar(self.contexto,outra,plano['campos']['operacao'])
            consultar.assert_not_called()

    def test_falha_incerta_fica_registrada_sem_reenvio_automatico(self):
        plano=jobs.preparar_tarefa('Pesquise uma alternativa.')
        with patch.object(api,'criar_tarefa',side_effect=FalhaAPI('Gemini',0,'tempo','tempo_esgotado')) as criar:
            with self.assertRaises(FalhaAPI):jobs.executar(plano,self.contexto,self.chat)
            jobs.executar(plano,self.contexto,self.chat)
        criar.assert_called_once()
        self.assertEqual(jobs.estado(self.contexto,self.chat)['tarefas'][0]['estado'],'resultado_incerto')

    def test_continuacao_exige_mesmo_agente_e_tarefa_concluida(self):
        primeiro=jobs.preparar_tarefa('Primeira tarefa.')
        with patch.object(api,'criar_tarefa',return_value={'remote_id':'remote-1','estado':'completed','texto':'resultado','ambiente_id':'env-1'}):jobs.executar(primeiro,self.contexto,self.chat)
        proximo=jobs.preparar_tarefa('Continue.',anterior=primeiro['campos']['operacao'])
        with patch.object(api,'criar_tarefa',return_value={'remote_id':'remote-2','estado':'completed','texto':'novo resultado','ambiente_id':'env-1'}) as criar:jobs.executar(proximo,self.contexto,self.chat)
        self.assertEqual(criar.call_args.kwargs['anterior']['remote_id'],'remote-1')
        errado=jobs.preparar_tarefa('Continue.',agente='deep-research-preview-04-2026',anterior=primeiro['campos']['operacao'])
        with patch.object(api,'criar_tarefa') as criar:
            with self.assertRaises(ValueError):jobs.executar(errado,self.contexto,self.chat)
            criar.assert_not_called()

    def test_resultado_virou_proposta_sem_executar_codigo(self):
        plano=jobs.preparar_tarefa('Proponha correção.')
        with patch.object(api,'criar_tarefa',return_value={'remote_id':'remote-1','estado':'completed','texto':'print("proposta")','ambiente_id':''}):jobs.executar(plano,self.contexto,self.chat)
        proposta={'acao':'gemini_contribuir','campos':{'id':plano['campos']['operacao']}}
        jobs.executar(proposta,self.contexto,self.chat);jobs.executar(proposta,self.contexto,self.chat)
        self.assertEqual(len(central.estado_central(self.contexto)['contribuicoes']),1)
        self.assertFalse((nucleo.DADOS/'proposta.py').exists())

    def test_exclusao_nao_oculta_tarefa_ainda_em_andamento(self):
        plano=jobs.preparar_tarefa('Tarefa longa.')
        with patch.object(api,'criar_tarefa',return_value={'remote_id':'remote-1','estado':'in_progress','texto':'','ambiente_id':''}):jobs.executar(plano,self.contexto,self.chat)
        with patch.object(api,'excluir_interacao') as excluir:
            with self.assertRaises(ValueError):jobs.executar({'acao':'gemini_excluir','campos':{'id':plano['campos']['operacao']}},self.contexto,self.chat)
            excluir.assert_not_called()

    def test_cliente_modelo_stateless_redige_chave_e_preserva_historico(self):
        cliente=SimpleNamespace(interactions=SimpleNamespace(create=Mock(return_value={'output_text':'Resposta fixture-chave-privada'})),close=Mock())
        with patch.object(api,'_cliente',return_value=cliente):
            texto=api.responder('Pedido fixture-chave-privada',[{'role':'assistant','content':'resposta anterior'}])
        opcoes=cliente.interactions.create.call_args.kwargs
        self.assertIs(opcoes['store'],False);self.assertIs(opcoes['background'],False)
        self.assertNotIn('fixture-chave-privada',repr(opcoes));self.assertNotIn('fixture-chave-privada',texto)
        self.assertEqual(opcoes['input'][-1]['type'],'user_input');cliente.close.assert_called_once()

    def test_agente_exige_confirmacao_e_nao_recebe_arquivos_chaves_ou_historico(self):
        with patch.object(api,'_chamar',return_value={'id':'remote-1','status':'queued','output_text':''}) as chamar:
            with self.assertRaises(PermissionError):api.criar_tarefa('Tarefa.')
            chamar.assert_not_called()
            api.criar_tarefa('Tarefa.',confirmado=True)
        body=chamar.call_args.kwargs
        self.assertTrue(body['background']);self.assertTrue(body['store'])
        self.assertEqual(body['environment'],{'type':'remote','network':'disabled'})
        self.assertNotIn('sources',body['environment']);self.assertNotIn('env',body['environment'])

    def test_configuracao_gemini_preserva_chave_omitida_e_outros_campos(self):
        caminho=nucleo.DADOS/'config-fixture.env';caminho.write_text('GEMINI_API_KEY=fixture-segredo\nOUTRO=preservar\n',encoding='utf-8')
        configurar.salvar_configuracao('interactions','gemini-3.8-flash',caminho=caminho)
        conteudo=caminho.read_text(encoding='utf-8')
        self.assertIn('GEMINI_API_KEY=fixture-segredo',conteudo);self.assertIn('OUTRO=preservar',conteudo)
        self.assertIn('GEMINI_API_MODO=interactions',conteudo)

    def test_memoria_invalida_nao_paralisa_conversa_e_arquivo_e_preservado(self):
        central.configurar_chat(self.contexto,self.chat,provedor='Gemini')
        nome=memoria._nome(memoria.contexto_chat(self.contexto,self.chat));arquivo=nucleo.DADOS/nome
        arquivo.write_text('{invalido',encoding='utf-8')
        roteador=SimpleNamespace(responder=Mock(return_value=('Resposta disponível','Gemini')))
        texto=chats.conversar('Olá assistente',self.contexto,roteador)
        self.assertIn('Resposta disponível',texto);self.assertIn(memoria.AVISO_MEMORIA_INDISPONIVEL,texto)
        self.assertEqual(arquivo.read_text(encoding='utf-8'),'{invalido');roteador.responder.assert_called_once()

    def test_memoria_remove_id_com_confirmacao_e_isolacao(self):
        chave=memoria.contexto_chat(self.contexto,self.chat)
        nota=memoria.salvar_nota(chave,'Preferência','Texto de teste',confirmado=True)
        with self.assertRaises(PermissionError):memoria.remover_nota(chave,nota['id'])
        outra=memoria.contexto_chat(self.contexto,'chat_outro')
        self.assertFalse(memoria.remover_nota(outra,nota['id'],confirmado=True)['removida'])
        self.assertTrue(memoria.remover_nota(chave,nota['id'],confirmado=True)['removida'])
        self.assertFalse(memoria.remover_nota(chave,nota['id'],confirmado=True)['removida'])

    def test_modelo_gateway_por_conversa_requer_id_ativo_e_nao_muda_padrao(self):
        roteador=SimpleNamespace(nine_router=Mock(return_value='OK'))
        base={'modelo':'combo-a','chat_id':self.chat,'confirmacao':'ALTERAR MODELO 9ROUTER'}
        with patch.object(gateway,'listar_modelos',return_value={'modelos':[{'id':'combo-a'}]}):
            with self.assertRaises(ValueError):chats.executar_acao('chat_modelo_9router',{**base,'chat_id':'outra'},self.contexto,roteador)
            chats.executar_acao('chat_modelo_9router',base,self.contexto,roteador)
        atual=central.obter_chat_ativo(self.contexto)
        self.assertEqual(atual['modelo_9router'],'combo-a');self.assertEqual(atual['provedor'],'9Router')
        self.assertNotIn('NINE_ROUTER_MODEL',os.environ)

    def test_prontidao_default_nao_consulta_apis_ou_inicia_programas(self):
        from diagnostico_ollama import consultar
        with patch('diagnostico_ollama.consultar') as consulta,patch.object(gateway,'listar_modelos') as modelos,patch('subprocess.Popen') as iniciar:
            resultado=pronto.coletar_prontidao()
        self.assertFalse(resultado['geracao_testada']);self.assertFalse(resultado['sondado'])
        consulta.assert_not_called();modelos.assert_not_called();iniciar.assert_not_called()
        self.assertGreater(len(resultado['itens']),10)

    def test_rejeicao_conhecida_e_removivel_sem_api_e_sem_reenvio(self):
        plano=jobs.preparar_tarefa('Tarefa recusada por cota.')
        with patch.object(api,'criar_tarefa',side_effect=FalhaAPI('Gemini',429,'cota','cota')) as criar:
            with self.assertRaises(FalhaAPI):jobs.executar(plano,self.contexto,self.chat)
            jobs.executar(plano,self.contexto,self.chat)
        criar.assert_called_once()
        self.assertEqual(jobs.estado(self.contexto,self.chat)['tarefas'][0]['estado'],'nao_enviada')
        with patch.object(api,'excluir_interacao') as excluir:
            jobs.executar({'acao':'gemini_excluir','campos':{'id':plano['campos']['operacao']}},self.contexto,self.chat)
            excluir.assert_not_called()
        self.assertEqual(jobs.estado(self.contexto,self.chat)['tarefas'],[])

    def test_nove_modelos_cooperativos_preservam_todos_participantes(self):
        from conversa_equipe import consultar_modelos
        modelos=['teste'+str(i)+':latest' for i in range(9)]
        roteador=Mock();roteador.responder.side_effect=lambda *a,**kw:('Uma proposta de teste.','Ollama')
        resultado=consultar_modelos('Compare as soluções.',[],modelos,roteador,modo='cooperativa')
        self.assertEqual([r['modelo'] for r in resultado['resultados']],modelos)
        for modelo in modelos:self.assertIn(modelo,resultado['texto'])
        roteador.reset_mock()
        with self.assertRaises(ValueError):consultar_modelos('Objetivo.',[],modelos,roteador,modo='paralela')
        roteador.responder.assert_not_called()

    def test_porta_ollama_ocupada_nao_abre_segundo_servidor(self):
        import iniciar_servicos_locais as inicio
        with patch.object(inicio,'consultar',return_value={'ok':False}),patch.object(inicio,'_porta_ocupada',return_value=True),patch.object(inicio,'diagnosticar_porta_ollama',return_value={'mensagem':'Porta ocupada.'}),patch.object(inicio.subprocess,'Popen') as criar:
            resultado=inicio.garantir_ollama()
        self.assertFalse(resultado['iniciado']);criar.assert_not_called()

    def test_politica_ollama_respeita_inicio_desabilitado(self):
        import iniciar_servicos_locais as inicio
        with patch.dict(os.environ,{'OLLAMA_INICIAR_SERVICO':'0'}),patch.object(inicio,'consultar',return_value={'ok':False}),patch.object(inicio.subprocess,'Popen') as criar:
            resultado=inicio.garantir_ollama()
        self.assertFalse(resultado['iniciado']);criar.assert_not_called()

    def test_gateway_override_serializa_modelo_sem_mudar_padrao(self):
        import io
        cfg={'NINE_ROUTER_HABILITADO':'1','NINE_ROUTER_MODEL':'padrao','NINE_ROUTER_URL':gateway.URL_PADRAO}
        cliente=Mock();cliente.open.return_value=io.BytesIO(b'{"choices":[{"message":{"content":"OK"}}]}')
        with patch.dict(os.environ,cfg),patch.object(gateway.urllib.request,'build_opener',return_value=cliente):
            self.assertEqual(gateway.responder('Teste.',modelo='combo-projeto'),'OK')
            self.assertEqual(json.loads(cliente.open.call_args.args[0].data)['model'],'combo-projeto')
            self.assertEqual(os.environ['NINE_ROUTER_MODEL'],'padrao')

    def test_dashboard_nao_abre_quando_servico_nao_responde(self):
        import configuracao_assistente as configurar
        import integracoes_9stack as stack
        with patch.object(configurar.sys,'platform','win32'),patch.object(configurar,'_aguardar_9router',return_value=False),patch.object(stack,'executar_9stack',return_value='Iniciado.') as executar:
            resultado=configurar.executar_etapa('preparar_9router',confirmado=True)
        executar.assert_called_once_with('9router','iniciar',confirmado=True)
        self.assertIn('pendente',resultado)

    def test_consolidacao_de_inicio_reverte_atalho_se_registro_falhar(self):
        import startup_windows as inicio
        pasta=nucleo.DADOS/'Startup';pasta.mkdir();arquivo=pasta/inicio.NOME
        legado=pasta/'assistente_pc.py - Atalho.lnk';legado.write_bytes(b'atalho-ficticio')
        externo=pasta/'OpenClaw Companion.lnk';externo.write_bytes(b'nao-alterar')
        with patch.object(inicio,'destino',return_value=arquivo),patch.object(inicio,'texto_inicio',return_value='script-ficticio'),patch.object(inicio,'registrar_inicio',side_effect=OSError('fixture')):
            with self.assertRaises(OSError):inicio.consolidar_inicio(confirmado=True,diretorio_backup=nucleo.DADOS/'backup')
        self.assertEqual(legado.read_bytes(),b'atalho-ficticio');self.assertEqual(externo.read_bytes(),b'nao-alterar');self.assertFalse(arquivo.exists())

    def test_equipe_aceita_dois_combos_gateway_e_registra_duas_propostas(self):
        import equipe_ia
        roteador=Mock();roteador.estado_local.return_value={'9Router':{'configurado':True}}
        roteador.responder.side_effect=lambda *a,**kw:('Proposta para '+kw['modelo_9router'],'9Router')
        with patch.object(gateway,'listar_modelos',return_value={'modelos':[{'id':'combo-a'},{'id':'combo-b'}]}):
            resultado=equipe_ia.consultar_equipe('Planeje melhorias.',roteador,provedores=['9Router'],modelos_9router=['combo-a','combo-b'],confirmacao='CONSULTAR EQUIPE')
        self.assertEqual(len(resultado['resultados']),2)
        self.assertTrue(all(r['ok'] for r in resultado['resultados']))
        self.assertEqual({r['modelo'] for r in resultado['resultados']},{'combo-a','combo-b'})
        self.assertTrue(all('local' not in r['papel'] for r in resultado['resultados']))
        self.assertEqual(len(central.estado_central(self.contexto)['contribuicoes']),2)


if __name__=='__main__':unittest.main()
