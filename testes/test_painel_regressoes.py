"""Requisições locais reais com dados temporários; nenhuma ação do PC."""
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import nucleo
import assistente_pc as app


class PainelRegressoes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.dados=patch.object(nucleo,'DADOS',Path(cls.tmp.name));cls.dados.start()
        nucleo.gravar_json('gestao_vida.json',{'rotina':[],'financeiro':{'saldo':0},'habitos_saude':{}})
        with patch.dict(os.environ,{'PAINEL_PORTA':'0'}):
            cls.server=app.iniciar_painel()
        cls.port=cls.server.server_port
        cls.origin=f'http://127.0.0.1:{cls.port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close()
        cls.dados.stop();cls.tmp.cleanup()

    def request(self,path='/api/acao',body=b'{"acao":"agua"}',headers=None,method='POST'):
        cab={'X-Painel-Token':app.TOKEN_PAINEL,'Origin':self.origin,'Content-Type':'application/json'}
        cab.update(headers or {})
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
        try:
            conn.request(method,path,body=body,headers=cab)
            res=conn.getresponse()
            return res.status,json.loads(res.read()) if path!='/' or res.status!=200 else res.read().decode()
        finally:conn.close()

    def test_html_nao_entrega_token_a_host_externo(self):
        status,res=self.request('/',method='GET',body=None,headers={'Host':f'invasor.example:{self.port}'})
        self.assertEqual(status,403)
        self.assertNotIn(app.TOKEN_PAINEL,str(res))

    def test_host_localhost_valido(self):
        status,res=self.request('/',method='GET',body=None,headers={'Host':f'localhost:{self.port}'})
        self.assertEqual(status,200)
        self.assertIn('MeuControlePC',res)

    def test_origem_usa_porta_do_servidor(self):
        # A variável foi restaurada; o servidor deve continuar usando a sua porta real.
        status,res=self.request()
        self.assertEqual(status,200)
        self.assertTrue(res['ok'])

    def test_token_nao_ascii_negado(self):
        status,_=self.request('/api/estado',body=None,method='GET',headers={'X-Painel-Token':'inválido'})
        self.assertEqual(status,403)

    def test_comprimento_invalido_recebe_400(self):
        for valor in ('abc','-1','0','8193'):
            with self.subTest(valor=valor):
                status,_=self.request(headers={'Content-Length':valor})
                self.assertEqual(status,400)

    def test_corpos_invalidos_recebem_400_sem_acao(self):
        for body in (b'[]',b'null',b'1',b'"agua"',b'{',b'\xff',b'{"acao":"ru","quantidade":NaN}'):
            with self.subTest(body=body),patch.object(app,'registrar_agua') as agua:
                status,_=self.request(body=body)
                self.assertEqual(status,400)
                agua.assert_not_called()

    def test_content_type_obrigatorio(self):
        status,_=self.request(headers={'Content-Type':'text/plain'})
        self.assertEqual(status,415)

    def test_ru_nao_trunca_fracao(self):
        for quantidade in (1.5,True,None,'2'):
            with self.subTest(quantidade=quantidade):
                status,_=self.request(body=json.dumps({'acao':'ru','quantidade':quantidade}).encode())
                self.assertEqual(status,400)

    def test_json_corrompido_recebe_503_preservando_arquivo(self):
        arquivo=Path(self.tmp.name)/'gestao_vida.json'
        original=arquivo.read_bytes()
        try:
            arquivo.write_bytes(b'{quebrado')
            with self.assertLogs(nucleo._LOG,level='ERROR') as logs:
                status,res=self.request('/api/estado',body=None,method='GET')
            self.assertEqual(status,503)
            self.assertIn('JSON',res['erro'])
            self.assertIn('gestao_vida.json',logs.output[0])
            self.assertEqual(arquivo.read_bytes(),b'{quebrado')
        finally:arquivo.write_bytes(original)


if __name__=='__main__':unittest.main()
