"""Preparação autorizada com caminhos fictícios, sem pip, Startup ou pesos reais."""
import contextlib
import io
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import preparar_inicio_automatico as preparar
import startup_windows as startup


class PrepararAutomaticoTeste(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.raiz=Path(self.tmp.name).resolve();self.codigo=self.raiz/'codigo';self.codigo.mkdir()
        self.env=self.raiz/'instalacao'/'.env';self.env.parent.mkdir()
        self.dados=self.env.parent/'dados';self.dados.mkdir()
        self.destino=self.raiz/'startup'/'inicio.cmd'
        for nome in ('requirements.txt','requirements-voz-local.txt','transcritor_local.py'):
            (self.codigo/nome).write_text('fixture',encoding='utf-8')
        self.env.write_bytes(b'fixture-segredo-preservado')
        self.python=self.codigo/'.venv'/'Scripts'/'python.exe';self.python.parent.mkdir(parents=True);self.python.write_bytes(b'fixture')
        self.plano={'codigo':self.codigo,'arquivo_env':self.env,'dados':self.dados,'python':self.python,
                    'cwd':str(self.codigo),'comando':[str(self.python),str(self.codigo/'assistente_pc.py')],
                    'ambiente':{'MEUCONTROLEPC_ENV':str(self.env),'MEUCONTROLEPC_DADOS':str(self.dados),
                                'OPENAI_API_KEY':'fixture-segredo','PYTHONPATH':'fixture-segredo',
                                'USERPROFILE':'fixture-usuario','PATH':'fixture-path','VOZ_MODELO_LOCAL':'base'}}
        for alvo,valor in ((preparar,'os'),):
            p=patch.object(alvo,valor,SimpleNamespace(name='nt'));p.start();self.addCleanup(p.stop)
        p=patch.object(preparar.redirecionar,'plano_execucao',return_value=self.plano)
        self.planejar=p.start();self.addCleanup(p.stop)
        p=patch.object(startup,'destino',return_value=self.destino);p.start();self.addCleanup(p.stop)
        p=patch.object(preparar.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='',stderr=''))
        self.run=p.start();self.addCleanup(p.stop)
        p=patch.object(preparar.subprocess,'Popen')
        self.popen=p.start();self.addCleanup(p.stop)
        p=contextlib.redirect_stdout(io.StringIO());p.__enter__();self.addCleanup(p.__exit__,None,None,None)

    def executar(self,**opcoes):
        return preparar.preparar(self.codigo,self.env,self.dados,**opcoes)

    def test_uma_preparacao_instala_pesos_registra_startup_e_inicia_sem_credenciais(self):
        original=self.env.read_bytes();resultado=self.executar()
        self.assertEqual(len(self.run.call_args_list),4)
        comandos=[c.args[0] for c in self.run.call_args_list]
        self.assertIn('pip',comandos[1]);self.assertIn('--no-cache-dir',comandos[1])
        self.assertIn(str(self.codigo/'requirements-voz-local.txt'),comandos[1])
        self.assertEqual(comandos[2][-2:],['pip','check'])
        self.assertIn('preparar_modelo',comandos[3][-1]);self.assertIn('ler_env',comandos[3][-1])
        self.assertEqual(self.run.call_args_list[3].kwargs['env']['VOZ_MODELO_LOCAL'],'base')
        for chamada in self.run.call_args_list:
            self.assertIs(chamada.kwargs['shell'],False)
            self.assertNotIn('fixture-segredo',repr(chamada.kwargs['env']))
            self.assertGreater(chamada.kwargs['timeout'],0)
        self.assertEqual(self.env.read_bytes(),original)
        atalho=self.destino.read_text()
        self.assertIn(str(self.codigo),atalho);self.assertIn(str(self.env),atalho)
        self.assertIn(str(self.dados),atalho);self.assertNotIn('fixture-segredo',atalho)
        self.assertEqual(resultado['inicio'],self.destino)
        self.popen.assert_called_once()
        self.assertEqual(self.popen.call_args.kwargs['env'],self.plano['ambiente'])

    def test_repetir_preparacao_mantem_um_unico_atalho_identico(self):
        self.executar(iniciar=False);antes=self.destino.read_bytes()
        self.executar(iniciar=False)
        self.assertEqual(self.destino.read_bytes(),antes)
        self.assertEqual([p.name for p in self.destino.parent.iterdir()],['inicio.cmd'])
        self.popen.assert_not_called()

    def test_arquivo_alheio_nao_e_modificado_e_nada_e_instalado(self):
        self.destino.parent.mkdir();self.destino.write_text('fixture-nao-gerenciado')
        with self.assertRaises(RuntimeError):self.executar()
        self.run.assert_not_called();self.popen.assert_not_called()
        self.assertEqual(self.destino.read_text(),'fixture-nao-gerenciado')

    def test_falha_pip_ou_modelo_nao_registra_inicio_nem_apaga_configuracao(self):
        for etapa in (1,2,3):
            retornos=[SimpleNamespace(returncode=0,stdout='',stderr='') for _ in range(4)]
            retornos[etapa]=SimpleNamespace(returncode=7,stdout='fixture-segredo',stderr='fixture-segredo')
            self.run.side_effect=retornos
            with self.assertRaises(RuntimeError) as erro:self.executar()
            self.assertNotIn('fixture-segredo',str(erro.exception))
            self.assertFalse(self.destino.exists())
            self.assertEqual(self.env.read_bytes(),b'fixture-segredo-preservado')
            self.popen.assert_not_called()

    def test_timeout_nao_reinicia_instalacao(self):
        self.run.side_effect=subprocess.TimeoutExpired('fixture',900,output='fixture-segredo')
        with self.assertRaises(RuntimeError) as erro:self.executar()
        self.assertIn('prazo',str(erro.exception));self.assertNotIn('fixture-segredo',str(erro.exception))
        self.run.assert_called_once();self.popen.assert_not_called()

    def test_bot_ativo_impede_instalacao_e_registro_de_startup(self):
        with patch.object(preparar,'instancia_unica',side_effect=preparar.InstanciaAtiva('fixture')), \
                patch.object(startup,'registrar_inicio') as registrar:
            with self.assertRaisesRegex(RuntimeError,'Encerre a janela'):
                self.executar()
        self.run.assert_not_called();registrar.assert_not_called();self.popen.assert_not_called()

    def test_trava_cobre_pip_e_registro_mas_e_liberada_antes_de_iniciar(self):
        eventos=[];ativa=False
        @contextlib.contextmanager
        def bloquear(pasta):
            nonlocal ativa
            self.assertEqual(pasta,self.dados)
            ativa=True;eventos.append('trava')
            try:yield
            finally:ativa=False;eventos.append('liberar')
        def componentes(plano,**opcoes):
            self.assertTrue(ativa);eventos.append('componentes');return plano
        def registrar(*args,**opcoes):
            self.assertTrue(ativa);eventos.append('startup');return self.destino
        def iniciar(plano):
            self.assertFalse(ativa);eventos.append('iniciar');return None
        with patch.object(preparar,'instancia_unica',side_effect=bloquear), \
                patch.object(preparar,'preparar_componentes',side_effect=componentes), \
                patch.object(startup,'registrar_inicio',side_effect=registrar), \
                patch.object(preparar,'iniciar_assistente',side_effect=iniciar):
            self.executar()
        self.assertEqual(eventos,['trava','componentes','startup','liberar','iniciar'])

    def test_fora_windows_nao_instala(self):
        with patch.object(preparar,'os',SimpleNamespace(name='posix')),self.assertRaises(RuntimeError):self.executar()
        self.run.assert_not_called();self.popen.assert_not_called()

    def test_gravacao_atomica_falha_preserva_atalho_gerenciado(self):
        startup.registrar_inicio(self.codigo,self.python,arquivo_env_externo=self.env,dados=self.dados)
        antes=self.destino.read_bytes()
        with patch.object(startup.os,'replace',side_effect=OSError('fixture-falha')),self.assertRaises(OSError):
            startup.registrar_inicio(self.codigo/'novo',self.python,arquivo_env_externo=self.env,dados=self.dados)
        self.assertEqual(self.destino.read_bytes(),antes)
        self.assertEqual([p.name for p in self.destino.parent.iterdir()],['inicio.cmd'])

    def test_cmd_preserva_porcentagem_e_nao_expande_exclamacao(self):
        texto=startup.texto_inicio(self.codigo/'100% pronto!',self.python,arquivo_env_externo=self.env,dados=self.dados)
        self.assertIn('100%% pronto!',texto);self.assertIn('DisableDelayedExpansion',texto)
        for caminho in ('fixture\ncomando','fixture" & comando'):
            with self.assertRaises(ValueError):startup._argumento_cmd(caminho)


if __name__=='__main__':unittest.main()
