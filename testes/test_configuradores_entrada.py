"""Erros de preenchimento dos configuradores, sem chaves nem serviços reais."""
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import configurar_gemini as gemini
import configurar_9router as router
import roteador_9router as api
from multi_ia import FalhaAPI


class EntradasConfiguradores(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.env=Path(self.tmp.name)/'configuracao-ficticia.env'
        self.original='OUTRO=preservar\nNINE_ROUTER_API_KEY=fixture-preservada\nGEMINI_API_KEY=fixture-preservada\n'
        self.env.write_text(self.original,encoding='utf-8')
        p=patch.dict(os.environ,{},clear=True);p.start();self.addCleanup(p.stop)

    def test_gemini_sim_e_modelo_sim_sao_corrigidos_antes_de_pedir_chave(self):
        saida=io.StringIO()
        with patch.object(gemini,'arquivo_env',return_value=self.env),patch('builtins.input',side_effect=['sim','1','sim','','SALVAR GEMINI']),patch.object(gemini.getpass,'getpass',return_value='') as chave,contextlib.redirect_stdout(saida):
            self.assertEqual(gemini.main(),0)
        chave.assert_called_once()
        conteudo=self.env.read_text();self.assertIn('GEMINI_API_MODO=interactions',conteudo);self.assertIn('GEMINI_MODEL=gemini-3.8-flash',conteudo)
        self.assertIn('GEMINI_API_KEY=fixture-preservada',conteudo)
        self.assertIn('Não é uma pergunta de sim/não',saida.getvalue())
        self.assertIn('ID de modelo',saida.getvalue())
        self.assertNotIn('fixture-preservada',saida.getvalue())

    def test_gemini_tres_opcoes_invalidas_nao_pedem_chave_ou_gravam(self):
        saida=io.StringIO()
        with patch.object(gemini,'arquivo_env',return_value=self.env),patch('builtins.input',side_effect=['sim']*3),patch.object(gemini.getpass,'getpass') as chave,contextlib.redirect_stdout(saida):
            self.assertEqual(gemini.main(),2)
        chave.assert_not_called();self.assertEqual(self.env.read_text(),self.original)
        self.assertIn('Três entradas inválidas',saida.getvalue())

    def test_gemini_aceita_opcao_numerica_de_api_legada(self):
        with patch.object(gemini,'arquivo_env',return_value=self.env),patch('builtins.input',side_effect=['2','','SALVAR GEMINI']),patch.object(gemini.getpass,'getpass',return_value=''),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gemini.main(),0)
        self.assertIn('GEMINI_API_MODO=generate_content',self.env.read_text())

    def test_gemini_tres_modelos_invalidos_nao_pedem_chave_ou_gravam(self):
        with patch.object(gemini,'arquivo_env',return_value=self.env),patch('builtins.input',side_effect=['1','sim','sim','sim']),patch.object(gemini.getpass,'getpass') as chave,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gemini.main(),2)
        chave.assert_not_called();self.assertEqual(self.env.read_text(),self.original)

    def test_modelos_que_parecem_chave_nao_sao_persistidos_nem_exibidos(self):
        falsa='sk-'+'fixture_sem_valor_real_'*2
        for salvar in (lambda:router.salvar_configuracao(True,falsa,caminho=self.env),lambda:gemini.salvar_configuracao('interactions',falsa,caminho=self.env)):
            with self.subTest(salvar=salvar),self.assertRaises((ValueError,FalhaAPI)) as erro:salvar()
            self.assertNotIn(falsa,str(erro.exception));self.assertEqual(self.env.read_text(),self.original)
        with self.assertRaises(FalhaAPI) as erro:api.validar_modelo(falsa)
        self.assertNotIn(falsa,str(erro.exception))
        self.assertEqual(api.validar_modelo('Combo de Estudo'),'Combo de Estudo')
        self.assertEqual(api.validar_modelo('sk-modelo-curto'),'sk-modelo-curto')

    def test_console_router_recusa_chave_no_modelo_e_pede_correcao(self):
        falsa='sk-'+'fixture_sem_valor_real_'*2;saida=io.StringIO()
        with patch('builtins.input',side_effect=[falsa,'Combo de Estudo','','sim','confirmar']),patch.object(router.getpass,'getpass',return_value=''),contextlib.redirect_stdout(saida):
            self.assertEqual(router.main([],caminho=self.env),0)
        self.assertNotIn(falsa,saida.getvalue());self.assertNotIn(falsa,self.env.read_text());self.assertIn('NINE_ROUTER_MODEL=Combo de Estudo',self.env.read_text())

    def test_router_chave_salva_invalida_pode_ser_removida_com_confirmacao(self):
        self.env.write_text('OUTRO=preservar\nNINE_ROUTER_API_KEY=fixture com espacos\n',encoding='utf-8')
        saida=io.StringIO()
        with patch('builtins.input',side_effect=['Combo de Estudo','','sim','confirmar']),patch.object(router.getpass,'getpass',side_effect=['','APAGAR']) as chave,contextlib.redirect_stdout(saida):
            self.assertEqual(router.main([],caminho=self.env),0)
        self.assertEqual(chave.call_count,2)
        conteudo=self.env.read_text();self.assertIn('NINE_ROUTER_API_KEY=\n',conteudo);self.assertIn('OUTRO=preservar',conteudo)
        self.assertNotIn('fixture com espacos',saida.getvalue())

    def test_router_remocao_cancelada_preserva_arquivo_e_ambiente(self):
        with patch('builtins.input',side_effect=['Combo de Estudo','','sim','nao']),patch.object(router.getpass,'getpass',return_value='APAGAR'),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(router.main([],caminho=self.env),0)
        self.assertEqual(self.env.read_text(),self.original);self.assertFalse(os.environ)

    def test_router_chave_salva_invalida_nao_e_preservada_por_engano(self):
        original='OUTRO=preservar\nNINE_ROUTER_API_KEY=fixture com espacos\n'
        self.env.write_text(original,encoding='utf-8')
        saida=io.StringIO()
        with patch('builtins.input',side_effect=['Combo de Estudo','','sim']),patch.object(router.getpass,'getpass',return_value='') as chave,contextlib.redirect_stdout(saida):
            self.assertEqual(router.main([],caminho=self.env),2)
        self.assertEqual(chave.call_count,3);self.assertEqual(self.env.read_text(),original);self.assertFalse(os.environ)
        self.assertNotIn('fixture com espacos',saida.getvalue())

    def test_router_chave_nova_invalida_pede_outra_sem_exibir(self):
        saida=io.StringIO()
        with patch('builtins.input',side_effect=['Combo de Estudo','','sim','confirmar']),patch.object(router.getpass,'getpass',side_effect=['fixture com espacos','fixture-valida']),contextlib.redirect_stdout(saida):
            self.assertEqual(router.main([],caminho=self.env),0)
        self.assertIn('NINE_ROUTER_API_KEY=fixture-valida',self.env.read_text());self.assertNotIn('fixture com espacos',saida.getvalue());self.assertNotIn('fixture-valida',saida.getvalue())

    def test_url_invalida_e_corrigida_antes_da_entrada_oculta(self):
        with patch('builtins.input',side_effect=['Combo','sim','','sim','confirmar']),patch.object(router.getpass,'getpass',return_value='') as chave,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(router.main([],caminho=self.env),0)
        chave.assert_called_once();self.assertIn('NINE_ROUTER_URL=http://127.0.0.1:20128/v1',self.env.read_text())


if __name__=='__main__':unittest.main()
