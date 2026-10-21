"""Falhas simuladas de provedores: nenhum acesso externo ou credencial real."""
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
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
        self.assertEqual(erro.categoria,'limite_temporario')
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


if __name__=='__main__':unittest.main()
