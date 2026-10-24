"""Autorizacao CPU persiste atomicamente sem tocar selecao ou dados reais."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import configurar_ia_local as local
import nucleo
import servicos_chat as servicos


class NuvemConfiguracao(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.env=Path(self.tmp.name)/'configuracao-ficticia.env'
        self.inicial=b'\xef\xbb\xbf# exemplo\r\nCHAVE_FICTICIA=nao-exibir\r\nOLLAMA_PERFIL=cpu\r\nOLLAMA_MODEL=llama3.2:latest\r\n'
        self.env.write_bytes(self.inicial)
        self.roteador=MagicMock()

    def test_somente_flag_alterada_bom_quebras_e_modelo_preservados(self):
        local.configurar_nuvem(True,self.env)
        self.assertEqual(self.env.read_bytes(),self.inicial+b'OLLAMA_NUVEM_HABILITADA=1\r\n')
        local.configurar_nuvem(False,self.env)
        self.assertEqual(self.env.read_bytes(),self.inicial+b'OLLAMA_NUVEM_HABILITADA=0\r\n')
        self.assertEqual(list(self.env.parent.glob('*.tmp')),[])

    def test_falha_replace_preserva_original_e_remove_temporario(self):
        with patch.object(local.os,'replace',side_effect=OSError('fixture')):
            with self.assertRaises(OSError):local.configurar_nuvem(True,self.env)
        self.assertEqual(self.env.read_bytes(),self.inicial)
        self.assertEqual(list(self.env.parent.glob('*.tmp')),[])

    def test_duplicadas_normalizadas_e_tipos_invalidos_nao_gravam(self):
        self.env.write_bytes(self.inicial+b'OLLAMA_NUVEM_HABILITADA=0\r\nOLLAMA_NUVEM_HABILITADA=1\r\n')
        local.configurar_nuvem(True,self.env)
        self.assertEqual(self.env.read_bytes().count(b'OLLAMA_NUVEM_HABILITADA='),1)
        anterior=self.env.read_bytes()
        for valor in (None,1,'sim',[],{}):
            with self.subTest(valor=valor),self.assertRaises(ValueError):local.configurar_nuvem(valor,self.env)
        self.assertEqual(self.env.read_bytes(),anterior)

    def test_servico_exige_confirmacao_antes_de_tocar_configuracao(self):
        for obj in ({'ativo':True},{'ativo':'sim','confirmacao':'AUTORIZAR NUVEM'},
                    {'ativo':False,'confirmacao':'AUTORIZAR NUVEM'}):
            with self.subTest(obj=obj),patch.object(local,'configurar_nuvem') as salvar:
                with self.assertRaises(ValueError):servicos.executar_acao('ollama_nuvem',obj,'fixture',self.roteador)
                salvar.assert_not_called()

    def test_servico_atualiza_flag_sem_modelos_historico_ou_inferencia(self):
        with patch.dict(os.environ,{},clear=True), \
                patch.object(nucleo,'arquivo_env',return_value=self.env), \
                patch.object(nucleo,'registrar') as registrar, \
                patch.object(servicos.central,'obter_chat_ativo') as chat:
            for ativo in (True,False):
                mensagem=servicos.executar_acao('ollama_nuvem',{
                    'ativo':ativo,'confirmacao':'AUTORIZAR NUVEM' if ativo else 'DESATIVAR NUVEM'},'fixture',self.roteador)
                self.assertEqual(os.environ['OLLAMA_NUVEM_HABILITADA'],'1' if ativo else '0')
                self.assertIn('perfil CPU',mensagem)
                self.assertIn('perfil padrão',mensagem)
            self.assertNotIn('nao-exibir',repr(registrar.call_args_list))
            self.assertFalse(self.roteador.mock_calls);chat.assert_not_called()

    def test_falha_persistencia_nao_atualiza_ambiente(self):
        with patch.dict(os.environ,{'OLLAMA_NUVEM_HABILITADA':'0'},clear=True), \
                patch.object(local,'configurar_nuvem',side_effect=OSError('fixture')):
            with self.assertRaises(OSError):servicos.executar_acao('ollama_nuvem',{
                'ativo':True,'confirmacao':'AUTORIZAR NUVEM'},'fixture',self.roteador)
            self.assertEqual(os.environ['OLLAMA_NUVEM_HABILITADA'],'0')


if __name__=='__main__':unittest.main()
