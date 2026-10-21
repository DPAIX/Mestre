"""Falhas simuladas de provedores: nenhum acesso externo ou credencial real."""
import io
import json
import os
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import patch,MagicMock
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.error import HTTPError, URLError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import multi_ia as ia


class MultiIARegressoes(unittest.TestCase):
    def setUp(self):
        for alvo,kwargs in [
            ('multi_ia.ler_json',{'return_value':{}}),
            ('multi_ia.gravar_json',{}),
            ('multi_ia.registrar',{}),
        ]:
            simulacao=patch(alvo,**kwargs)
            simulacao.start()
            self.addCleanup(simulacao.stop)
        ambiente=patch.dict(os.environ,{
            'EXA_API_KEY':'chave-ficticia-exa',
            'OPENAI_API_KEY':'chave-ficticia-openai',
            'ANTHROPIC_API_KEY':'chave-ficticia-claude',
        },clear=True)
        ambiente.start()
        self.addCleanup(ambiente.stop)

    def test_cota_por_minuto_nao_bloqueia_por_falta_de_credito(self):
        corpo=json.dumps({'error':{'status':'RESOURCE_EXHAUSTED',
            'message':'Quota exceeded for metric requests_per_minute'}})
        erro=ia.analisar_erro('Gemini',429,corpo)
        self.assertEqual(erro.categoria,'cota_temporaria')
        roteador=ia.Roteador()
        with patch('multi_ia.time.time',return_value=1000):
            roteador.registrar_falha(erro)
        self.assertEqual(roteador.bloqueados['Gemini'],1120)

    def test_codigo_credito_nao_e_ocultado_pelo_tipo(self):
        corpo=json.dumps({'error':{'type':'tokens','code':'insufficient_quota',
            'message':'quota exhausted'}})
        self.assertEqual(ia.analisar_erro('OpenAI',429,corpo).categoria,'sem_creditos')

    def test_erros_http_billing_e_servidor(self):
        self.assertEqual(ia.analisar_erro('Exa',402,'Payment required').categoria,'sem_creditos')
        self.assertEqual(ia.analisar_erro('Claude',529,'Overloaded').categoria,'servidor_ocupado')

    def test_json_http_invalido_vira_falha_controlada(self):
        for corpo in (b'<html>falha</html>',b'\xff',b'[]',b'null'):
            with self.subTest(corpo=corpo),patch('multi_ia.urllib.request.urlopen',return_value=io.BytesIO(corpo)):
                with self.assertRaises(ia.FalhaAPI) as exc:
                    ia.postar('https://exemplo.invalid','ficticia',{},'Exa')
                self.assertEqual(exc.exception.categoria,'resposta_invalida')

    def test_resposta_grande_e_limitada_e_fechada(self):
        resposta=io.BytesIO(b'x'*(ia.LIMITE_RESPOSTA+20))
        with patch('multi_ia.urllib.request.urlopen',return_value=resposta):
            with self.assertRaises(ia.FalhaAPI) as exc:
                ia.postar('https://exemplo.invalid','ficticia',{},'Exa')
        self.assertEqual(exc.exception.categoria,'resposta_invalida')
        self.assertTrue(resposta.closed)

    def test_erro_http_remove_chave_sem_prefixo_e_fecha_resposta(self):
        chave='segredo-ficticio-sem-prefixo'
        corpo=io.BytesIO(json.dumps({'error':{'message':'Invalid key '+chave}}).encode())
        erro=HTTPError('https://exemplo.invalid',401,'Unauthorized',{},corpo)
        with patch('multi_ia.urllib.request.urlopen',side_effect=erro):
            with self.assertRaises(ia.FalhaAPI) as exc:
                ia.postar('https://exemplo.invalid',chave,{},'Exa')
        self.assertNotIn(chave,str(exc.exception))
        self.assertEqual(exc.exception.categoria,'autenticacao')
        self.assertTrue(corpo.closed)

    def test_erro_de_rede_remove_chave_sem_prefixo(self):
        chave='credencial-ficticia-123'
        with patch('multi_ia.urllib.request.urlopen',side_effect=URLError('Invalid '+chave)):
            with self.assertRaises(ia.FalhaAPI) as exc:
                ia.postar('https://exemplo.invalid',chave,{},'Exa')
        self.assertEqual(exc.exception.categoria,'rede')
        self.assertNotIn(chave,str(exc.exception))

    def test_erro_em_resposta_200_nao_e_sucesso(self):
        resposta=io.BytesIO(b'{"error":{"code":"insufficient_quota"}}')
        with patch('multi_ia.urllib.request.urlopen',return_value=resposta):
            with self.assertRaises(ia.FalhaAPI) as exc:
                ia.postar('https://exemplo.invalid','ficticia',{},'Exa')
        self.assertEqual(exc.exception.categoria,'sem_creditos')

    def test_schemas_de_resposta_invalidos(self):
        roteador=ia.Roteador()
        casos=[(roteador.openai,{}),(roteador.openai,{'choices':[]}),
            (roteador.openai,{'choices':[{'message':{'content':None}}]}),
            (roteador.claude,{'content':None}),
            (roteador.claude,{'content':[{'type':'text','text':3}]}),
            (roteador.pesquisa_exa,{}),(roteador.pesquisa_exa,{'results':[None]})]
        for funcao,resposta in casos:
            with self.subTest(provedor=funcao.__name__,resposta=resposta),patch('multi_ia.postar',return_value=resposta):
                with self.assertRaises(ia.FalhaAPI) as exc:funcao('teste')
                self.assertEqual(exc.exception.categoria,'resposta_invalida')

    def test_exa_resposta_invalida_entra_em_pausa(self):
        roteador=ia.Roteador()
        with patch('multi_ia.urllib.request.urlopen',return_value=io.BytesIO(b'not json')) as consulta:
            with self.assertRaises(ia.FalhaAPI):roteador.responder('teste',pesquisa=True)
            self.assertFalse(roteador.disponivel('Exa'))
            with self.assertRaises(ia.FalhaAPI) as exc:roteador.responder('teste',pesquisa=True)
            self.assertEqual(exc.exception.categoria,'suspenso')
        self.assertEqual(consulta.call_count,1)

    def test_provedor_com_schema_invalido_permite_fallback(self):
        roteador=ia.Roteador()
        with patch('multi_ia.postar',side_effect=[{}, {'content':[{'type':'text','text':'Resposta correta'}]}]):
            self.assertEqual(roteador.responder('teste'),('Resposta correta','Claude'))
        self.assertFalse(roteador.disponivel('OpenAI'))

    def test_pesquisa_vazia_continua_valida(self):
        with patch('multi_ia.postar',return_value={'results':[]}):
            self.assertIn('não encontrou',ia.Roteador().pesquisa_exa('teste'))

    def test_estado_invalido_de_um_provedor_preserva_pausa_dos_outros(self):
        dados={'Gemini':{'ate':'invalido'},'OpenAI':{'ate':1100,'categoria':'sem_creditos'}}
        with patch('multi_ia.ler_json',return_value=dados),patch('multi_ia.time.time',return_value=1000):
            roteador=ia.Roteador()
            self.assertFalse(roteador.disponivel('OpenAI'))

    def test_todos_indisponiveis_inclui_pausas_anteriores_e_causas_distintas(self):
        with patch.dict(os.environ,{'GEMINI_API_KEY':'chave-ficticia-gemini'}):
            roteador=ia.Roteador()
            with patch('multi_ia.time.time',return_value=1000):
                for nome in ('OpenAI','Claude'):
                    roteador.registrar_falha(ia.FalhaAPI(nome,429,'saldo fictício','sem_creditos'))
            erro=ia.FalhaAPI('Gemini',503,'overloaded','servidor_ocupado')
            with patch('multi_ia.time.time',return_value=3340),patch.object(roteador,'gemini',side_effect=erro) as gemini,\
                    patch.object(roteador,'openai') as openai,patch.object(roteador,'claude') as claude:
                with self.assertRaises(ia.FalhaAPI) as exc:roteador.responder('teste')
            texto=str(exc.exception)
            self.assertIn('Gemini: servidor ocupado (HTTP 503)',texto)
            self.assertIn('pausa local por mais 1 min',texto)
            self.assertIn('OpenAI: sem créditos (HTTP 429)',texto)
            self.assertIn('Claude: sem créditos (HTTP 429)',texto)
            self.assertIn('23 h 21 min',texto)
            self.assertIn('Exa atende apenas /pesquisar',texto)
            self.assertIn('Nenhuma nova tentativa foi agendada',texto)
            gemini.assert_called_once()
            openai.assert_not_called()
            claude.assert_not_called()

    def test_sobrecarga_isolada_nao_recomenda_creditos(self):
        with patch.dict(os.environ,{'GEMINI_API_KEY':'ficticia','OPENAI_API_KEY':'','ANTHROPIC_API_KEY':''}):
            roteador=ia.Roteador()
            erro=ia.analisar_erro('Gemini',503,'Temporary overload. See billing docs.')
            self.assertEqual(erro.categoria,'servidor_ocupado')
            with patch.object(roteador,'gemini',side_effect=erro):
                with self.assertRaises(ia.FalhaAPI) as exc:roteador.responder('teste')
            texto=str(exc.exception)
            self.assertIn('servidor ocupado (HTTP 503)',texto)
            self.assertNotIn('créditos',texto)
            self.assertNotIn('faturamento',texto)

    def test_snapshot_preserva_falha_apos_expirar_pausa_sem_prometer_recuperacao(self):
        roteador=ia.Roteador()
        with patch('multi_ia.time.time',return_value=1000):
            roteador.registrar_falha(ia.FalhaAPI('OpenAI',503,'conteúdo não deve integrar snapshot','servidor_ocupado'))
        with patch('multi_ia.time.time',return_value=1061):
            estado=roteador.estado_local()['OpenAI']
            self.assertFalse(estado['em_pausa'])
            self.assertEqual(estado['espera_segundos'],0)
            self.assertEqual(estado['categoria'],'servidor_ocupado')
            self.assertEqual(estado['codigo'],503)
            self.assertEqual(estado['falha_em'],1000)
            self.assertEqual(estado['pausa_ate'],1060)
            self.assertIsNone(estado['sucesso_em'])
            self.assertEqual(roteador.status()['OpenAI'],'configurado; não testado')

    def test_snapshot_sucesso_registra_somente_resposta_observada_na_sessao(self):
        roteador=ia.Roteador()
        with patch('multi_ia.time.time',return_value=1000):
            roteador.registrar_falha(ia.FalhaAPI('OpenAI',503,'erro fictício','servidor_ocupado'))
        with patch('multi_ia.time.time',return_value=1061),patch.object(roteador,'openai',return_value='resposta fictícia'):
            self.assertEqual(roteador.responder('teste'),('resposta fictícia','OpenAI'))
            estado=roteador.estado_local()['OpenAI']
            self.assertFalse(estado['em_pausa'])
            self.assertEqual(estado['falha_em'],1000)
            self.assertEqual(estado['sucesso_em'],1061)
            self.assertIsNone(estado['pausa_ate'])

    def test_snapshot_sem_chaves_perguntas_ou_detalhes_e_sem_consultas(self):
        roteador=ia.Roteador()
        with patch('multi_ia.time.time',return_value=1000):
            roteador.registrar_falha(ia.FalhaAPI('OpenAI',429,'segredo-ficticio-interno','sem_creditos'))
        with patch('multi_ia.urllib.request.urlopen',side_effect=AssertionError('snapshot não consulta APIs')):
            estado=roteador.estado_local()
        serializado=json.dumps(estado)
        self.assertNotIn('segredo-ficticio-interno',serializado)
        self.assertNotIn('chave-ficticia',serializado)
        self.assertEqual(set(estado),{'Gemini','OpenAI','Claude','Exa'})
        estado['OpenAI']['categoria']='mudança externa'
        self.assertEqual(roteador.estado_local()['OpenAI']['categoria'],'sem_creditos')

    def test_metadados_bloqueio_restaurados_e_legado_aceito(self):
        dados={'OpenAI':{'ate':1100,'categoria':'sem_creditos','codigo':429,'falha_em':990},
            'Claude':{'ate':1200,'categoria':'autenticacao'}}
        with patch('multi_ia.ler_json',return_value=dados),patch('multi_ia.time.time',return_value=1000):
            roteador=ia.Roteador()
            estados=roteador.estado_local()
        self.assertEqual(estados['OpenAI']['codigo'],429)
        self.assertEqual(estados['OpenAI']['falha_em'],990)
        self.assertIsNone(estados['Claude']['codigo'])
        self.assertTrue(estados['Claude']['em_pausa'])

    def test_reativar_nao_e_considerado_resposta_bem_sucedida(self):
        roteador=ia.Roteador()
        with patch('multi_ia.time.time',return_value=1000):
            roteador.registrar_falha(ia.FalhaAPI('OpenAI',429,'erro fictício','sem_creditos'))
            roteador.reativar()
            estado=roteador.estado_local()['OpenAI']
        self.assertFalse(estado['em_pausa'])
        self.assertIsNone(estado['sucesso_em'])
        self.assertEqual(estado['falha_em'],1000)

    def test_pesquisa_em_pausa_informa_causa_e_espera_sem_nova_consulta(self):
        roteador=ia.Roteador()
        with patch('multi_ia.time.time',return_value=1000):
            roteador.registrar_falha(ia.FalhaAPI('Exa',503,'erro fictício','servidor_ocupado'))
            with patch.object(roteador,'pesquisa_exa') as consulta:
                with self.assertRaises(ia.FalhaAPI) as exc:roteador.responder('teste',pesquisa=True)
        self.assertEqual(exc.exception.categoria,'suspenso')
        self.assertIn('servidor ocupado (HTTP 503)',str(exc.exception))
        self.assertIn('mais 1 min',str(exc.exception))
        consulta.assert_not_called()

    def test_gemini_free_tier_billing_incidental_e_retryinfo(self):
        corpo=json.dumps({'error':{'code':429,'status':'RESOURCE_EXHAUSTED',
            'message':'Quota exceeded for generate_content_free_tier_requests_per_day; check billing.',
            'details':[{'@type':'type.googleapis.com/google.rpc.RetryInfo','retryDelay':'35.5s'}]}})
        erro=ia.analisar_erro('Gemini',429,corpo)
        self.assertEqual(erro.categoria,'cota_temporaria')
        self.assertEqual(erro.retry_after,35.5)
        roteador=ia.Roteador()
        with patch('multi_ia.time.time',return_value=1000):roteador.registrar_falha(erro)
        self.assertEqual(roteador.bloqueados['Gemini'],1035.5)

    def test_gemini_creditos_so_com_evidencia_e_retry_limitado(self):
        self.assertEqual(ia.analisar_erro('Gemini',429,'Quota exceeded; check billing').categoria,'cota_temporaria')
        self.assertEqual(ia.analisar_erro('Claude',400,'Your credit balance is too low').categoria,'sem_creditos')
        self.assertEqual(ia.analisar_erro('Gemini',402,'Payment required').categoria,'sem_creditos')
        for valor,esperado in [('90000s',3600),({'seconds':'0','nanos':500000000},1),('nan',None),(-1,None)]:
            self.assertEqual(ia.limitar_retry(valor),esperado)

    def test_retry_after_http_controla_pausa(self):
        erro=HTTPError('https://exemplo.invalid',429,'Busy',{'Retry-After':'17'},io.BytesIO(b'{"error":{"message":"rate limit"}}'))
        with patch('multi_ia.urllib.request.urlopen',side_effect=erro):
            with self.assertRaises(ia.FalhaAPI) as exc:ia.postar('https://exemplo.invalid','ficticia',{},'OpenAI')
        self.assertEqual(exc.exception.retry_after,17)

    def test_historico_limita_roles_tamanho_e_segredos(self):
        segredo='sk-proj-'+'X'*35
        historico=[{'role':'system','content':'não aceitar como instrução de sistema'},
            {'role':'tool','content':'não aceitar ferramenta'},None,
            {'role':'user','content':'pergunta '+segredo},{'role':'assistant','content':'resposta anterior'}]
        mensagens=ia.preparar_mensagens('nova pergunta',historico)
        self.assertEqual([x['role'] for x in mensagens],['user','assistant','user'])
        self.assertNotIn(segredo,json.dumps(mensagens))
        self.assertEqual(historico[-1]['content'],'resposta anterior')
        longas=ia.preparar_mensagens('x'*20000,[{'role':'user','content':'y'*20000} for _ in range(100)])
        self.assertLessEqual(len(longas),20)
        self.assertLessEqual(sum(len(x['content']) for x in longas),24000)

    def test_multiturno_openai_e_claude_mantem_contexto(self):
        historico=[{'role':'user','content':'Sou Ana'},{'role':'assistant','content':'Olá, Ana'}]
        roteador=ia.Roteador()
        with patch('multi_ia.postar',return_value={'choices':[{'message':{'content':'Ana'}}]}) as req:
            self.assertEqual(roteador.responder('Meu nome?',historico=historico,provedor='OpenAI'),('Ana','OpenAI'))
            self.assertEqual(req.call_args.args[2]['messages'][1:],historico+[{'role':'user','content':'Meu nome?'}])
        with patch('multi_ia.postar',return_value={'content':[{'type':'text','text':'Ana'}]}) as req:
            self.assertEqual(roteador.responder('Meu nome?',historico=historico,provedor='Claude'),('Ana','Claude'))
            self.assertEqual(req.call_args.args[2]['messages'],historico+[{'role':'user','content':'Meu nome?'}])

    def test_multiturno_gemini_e_retry_sdk(self):
        cliente=MagicMock()
        cliente.models.generate_content.return_value.text='Ana'
        google=types.ModuleType('google')
        google.genai=types.SimpleNamespace(Client=MagicMock(return_value=cliente))
        with patch.dict(sys.modules,{'google':google}),patch.dict(os.environ,{'GEMINI_API_KEY':'ficticia'}):
            roteador=ia.Roteador()
            self.assertEqual(roteador.gemini('Meu nome?',[{'role':'assistant','content':'Olá Ana'}]),'Ana')
            conteudo=cliente.models.generate_content.call_args.kwargs['contents']
            self.assertEqual(conteudo[0],{'role':'model','parts':[{'text':'Olá Ana'}]})
            cliente.close.assert_called_once()
            erro=RuntimeError('Quota exceeded; check billing')
            erro.code=429
            erro.response_json={'error':{'status':'RESOURCE_EXHAUSTED','details':[{'retryDelay':'42s'}]}}
            cliente.models.generate_content.side_effect=erro
            with self.assertRaises(ia.FalhaAPI) as exc:roteador.gemini('teste')
            self.assertEqual(exc.exception.categoria,'cota_temporaria')
            self.assertEqual(exc.exception.retry_after,42)

    def test_selecao_explicita_nao_faz_fallback(self):
        roteador=ia.Roteador()
        with patch.object(roteador,'openai',side_effect=ia.FalhaAPI('OpenAI',503,'falha','servidor_ocupado')) as escolhido,\
                patch.object(roteador,'claude') as outro:
            with self.assertRaises(ia.FalhaAPI):roteador.responder('teste',provedor='openai')
        escolhido.assert_called_once()
        outro.assert_not_called()
        with self.assertRaises(ValueError):roteador.responder('teste',provedor='inventado')

    def test_ollama_gate_e_url_loopback(self):
        roteador=ia.Roteador()
        self.assertNotIn('Ollama',roteador.status())
        with patch('multi_ia.urllib.request.build_opener') as abrir:
            with self.assertRaises(ia.FalhaAPI):roteador.ollama('teste')
        abrir.assert_not_called()
        invalidas=['http://localhost:11434','http://example.com','http://192.168.0.1:11434',
            'http://127.0.0.1.evil','http://2130706433','http://user:pass@127.0.0.1',
            'http://127.0.0.1:0','http://127.0.0.1:65536','http://127.0.0.1/api/chat',
            'http://127.0.0.1?','http://127.0.0.1#','http://[::1%25lo]:11434',' http://127.0.0.1']
        for url in invalidas:
            with self.subTest(url=url),patch.dict(os.environ,{'OLLAMA_URL':url}):
                with self.assertRaises(ia.FalhaAPI):ia.endpoint_ollama()
        for url,esperado in [('http://127.0.0.1:11434/','http://127.0.0.1:11434/api/chat'),
            ('http://[::1]:11434','http://[::1]:11434/api/chat')]:
            with patch.dict(os.environ,{'OLLAMA_URL':url}):self.assertEqual(ia.endpoint_ollama(),esperado)

    def test_ollama_timeout_e_modelo_sem_instalacao(self):
        with patch.dict(os.environ,{'OLLAMA_HABILITADO':'1','OLLAMA_TIMEOUT':'9999'}),\
                patch('multi_ia.postar',return_value={'message':{'content':'resposta local'}}) as req:
            roteador=ia.Roteador()
            self.assertIn('Ollama',roteador.estado_local())
            self.assertEqual(roteador.ollama('teste'),'resposta local')
            self.assertEqual(req.call_args.kwargs['timeout'],120)
            self.assertEqual(req.call_args.args[2]['model'],'qwen2.5:3b')
            self.assertFalse(req.call_args.args[2]['stream'])
        with patch.dict(os.environ,{'OLLAMA_HABILITADO':'1','OLLAMA_MODEL':'modelo;comando'}),patch('multi_ia.postar') as req:
            with self.assertRaises(ia.FalhaAPI):roteador.ollama('teste')
            req.assert_not_called()

    def test_auto_pode_usar_ollama_habilitado_sem_chaves(self):
        with patch.dict(os.environ,{'OLLAMA_HABILITADO':'1','OPENAI_API_KEY':'','ANTHROPIC_API_KEY':'','EXA_API_KEY':''}),\
                patch('multi_ia.postar',return_value={'message':{'content':'local'}}):
            self.assertEqual(ia.Roteador().responder('teste'),('local','Ollama'))

    def test_modelo_explicito_nao_muda_ambiente_nem_usa_outro_provedor(self):
        with patch.dict(os.environ,{'OLLAMA_HABILITADO':'1','OLLAMA_MODEL':'qwen2.5:3b'}),\
                patch('multi_ia.postar',return_value={'message':{'content':'resposta'}}) as req:
            roteador=ia.Roteador()
            resultado=roteador.responder('Explique',provedor='Ollama',modelo_ollama='qwen3.5:4b',
                                         historico=[{'role':'user','content':'Anterior'}])
            self.assertEqual(resultado,('resposta','Ollama'))
            req.assert_called_once()
            self.assertEqual(req.call_args.args[2]['model'],'qwen3.5:4b')
            self.assertIn({'role':'user','content':'Anterior'},req.call_args.args[2]['messages'])
            self.assertEqual(os.environ['OLLAMA_MODEL'],'qwen2.5:3b')
            with self.assertRaises(ValueError):
                roteador.responder('Explique',provedor='OpenAI',modelo_ollama='qwen3.5:4b')
            with self.assertRaises(ValueError):
                roteador.responder('Explique',provedor='Ollama',modelo_ollama='modelo;comando')
            self.assertEqual(req.call_count,1)

    def test_falha_modelo_cloud_nao_pausa_local_ou_reativa_padrao(self):
        with patch.dict(os.environ,{'OLLAMA_HABILITADO':'1'}):
            roteador=ia.Roteador()
            roteador.bloqueados['Ollama']=ia.time.time()+3600
            padrao=roteador.bloqueados.copy()
            with patch('multi_ia.postar',side_effect=ia.FalhaAPI('Ollama',401,'Autentique sua conta','autenticacao')) as req:
                with self.assertRaises(ia.FalhaAPI) as erro:
                    roteador.responder('Teste',provedor='Ollama',modelo_ollama='gemma4:31b-cloud')
                self.assertIn('gemma4:31b-cloud',str(erro.exception))
                req.assert_called_once()
            self.assertEqual(roteador.bloqueados,padrao)
            with patch('multi_ia.postar',return_value={'message':{'content':'local responde'}}) as req:
                self.assertEqual(roteador.responder('Teste local',provedor='Ollama',modelo_ollama='qwen3.5:4b'),('local responde','Ollama'))
                req.assert_called_once()
            self.assertEqual(roteador.bloqueados,padrao)

    def test_sondagem_explicita_no_maximo_uma_chamada_sem_fallback(self):
        roteador=ia.Roteador()
        with patch.object(roteador,'openai',return_value='OK') as openai,\
                patch.object(roteador,'claude',side_effect=ia.FalhaAPI('Claude',402,'falha','sem_creditos')) as claude,\
                patch.object(roteador,'pesquisa_exa',return_value='resultado') as exa:
            resultado=roteador.verificar_conexoes()
        openai.assert_called_once()
        claude.assert_called_once()
        exa.assert_called_once()
        self.assertTrue(resultado['OpenAI']['ok'])
        self.assertFalse(resultado['Claude']['ok'])
        self.assertIsNone(resultado['Gemini']['verificado_em'])
        self.assertIn('não informa créditos',resultado['OpenAI']['mensagem'])
        self.assertIsNotNone(roteador.estado_local()['OpenAI']['sucesso_em'])

    def test_sondagem_provedor_escolhido_nao_aciona_outros(self):
        roteador=ia.Roteador()
        with patch.object(roteador,'openai',return_value='OK') as openai,patch.object(roteador,'claude') as claude:
            self.assertEqual(set(roteador.verificar_conexoes('OpenAI')),{'OpenAI'})
        openai.assert_called_once()
        claude.assert_not_called()


if __name__=='__main__':unittest.main()
