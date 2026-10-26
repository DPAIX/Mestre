"""9Stack com processos, navegador, portas e pacotes totalmente simulados."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import integracoes_9stack as stack


class Integracoes9Stack(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.raiz=Path(self.tmp.name)
        self.node=self.raiz/'node.exe';self.node.write_text('fixture')
        npm=self.raiz/'node_modules'/'npm'/'bin'/'npm-cli.js'
        npm.parent.mkdir(parents=True);npm.write_text('fixture')
        p=patch.dict(os.environ,{'LOCALAPPDATA':str(self.raiz/'local'),
            'PATH':'caminho-ficticio','SYSTEMROOT':'sistema-ficticio',
            'TELEGRAM_TOKEN':'SEGREDO_FIXTURE','OPENAI_API_KEY':'CHAVE_FIXTURE',
            'NINE_ROUTER_API_KEY':'ROUTER_FIXTURE','NODE_OPTIONS':'-r codigo-injetado'},clear=True)
        p.start();self.addCleanup(p.stop)
        p=patch.object(stack,'_PROCESSOS',{});p.start();self.addCleanup(p.stop)
        p=patch.object(stack.sys,'platform','win32');p.start();self.addCleanup(p.stop)
        p=patch.object(stack.shutil,'which',side_effect=lambda cmd:str(self.node) if cmd in ('node.exe','node') else None)
        p.start();self.addCleanup(p.stop)
        p=patch.object(stack,'_porta_ocupada',return_value=False);self.porta=p.start();self.addCleanup(p.stop)
        p=patch.object(stack.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='v22.16.0\n'))
        self.run=p.start();self.addCleanup(p.stop)
        p=patch.object(stack.subprocess,'Popen',return_value=SimpleNamespace(poll=lambda:None))
        self.popen=p.start();self.addCleanup(p.stop)
        p=patch.object(stack.webbrowser,'open',return_value=True);self.browser=p.start();self.addCleanup(p.stop)
        p=patch.object(stack,'_corrigir_9remote',return_value={'estado':'aplicada'})
        self.correcao=p.start();self.addCleanup(p.stop)

    def pacote(self,nome):
        item=stack.SERVICOS[nome]
        pasta=stack._pasta(nome)/'node_modules'/nome
        pasta.mkdir(parents=True,exist_ok=True)
        (pasta/'package.json').write_text(json.dumps({'name':nome,'version':item['versao']}))
        script=pasta/item['script'];script.parent.mkdir(parents=True,exist_ok=True);script.write_text('fixture')
        return script

    def test_planos_puros_tem_aviso_e_operacao_unica(self):
        with patch.object(stack,'_pasta',side_effect=AssertionError('Sem arquivos.')), \
                patch.object(stack,'catalogo_9stack',side_effect=AssertionError('Sem estado.')):
            for servico in ('9router','9remote'):
                for operacao in ('instalar','abrir','iniciar'):
                    with self.subTest(servico=servico,operacao=operacao):
                        plano=stack.preparar_9stack(servico,operacao)
                        self.assertEqual(set(plano),{'servico','operacao','descricao'})
                        self.assertLessEqual(len(plano['descricao']),500)
        self.assertIn('REMOTO',stack.preparar_9stack('9remote','iniciar')['descricao'])
        self.assertIn('terminal, arquivos e tela',stack.preparar_9stack('9remote','iniciar')['descricao'])
        self.popen.assert_not_called();self.run.assert_not_called()

    def test_ids_operacoes_e_tipos_extras_rejeitados(self):
        invalidos=(('9router; whoami','abrir'),('9remote','key'),('9remote','otk'),
                   ('9remote','stop'),('9remote','auto-approve'),('9router','connect'),
                   (None,'abrir'),([],False),('9router',None))
        for servico,operacao in invalidos:
            with self.subTest(servico=servico,operacao=operacao),self.assertRaises(ValueError):
                stack.preparar_9stack(servico,operacao)

    def test_execucao_sem_confirmacao_nao_sonda_nem_abre(self):
        for operacao in stack.OPERACOES:
            with self.subTest(operacao=operacao),self.assertRaises(PermissionError):
                stack.executar_9stack('9remote',operacao)
        self.run.assert_not_called();self.popen.assert_not_called();self.porta.assert_not_called()

    def test_fora_windows_nao_executa(self):
        with patch.object(stack.sys,'platform','linux'),self.assertRaises(RuntimeError):
            stack.executar_9stack('9router','instalar',confirmado=True)
        self.run.assert_not_called();self.popen.assert_not_called()

    def test_catalogo_e_somente_metadados_sem_claim_online(self):
        self.pacote('9router')
        resultado=stack.catalogo_9stack()
        self.assertTrue(resultado[0]['instalado_gerenciado'])
        self.assertFalse(resultado[1]['instalado_gerenciado'])
        self.assertNotIn('online',resultado[0])
        self.assertIn('nao comprovam funcionamento',stack.resumo_9stack())
        self.run.assert_not_called();self.popen.assert_not_called();self.porta.assert_not_called()

    def test_versao_diferente_e_manifesto_grande_nao_sao_confirmados(self):
        script=self.pacote('9remote');manifesto=script.parents[1]/'package.json'
        manifesto.write_text(json.dumps({'name':'9remote','version':'0.0.0'}))
        self.assertIsNone(stack._script('9remote'))
        manifesto.write_text('x'*65537)
        self.assertIsNone(stack._script('9remote'))

    def test_pacote_com_json_invalido_nao_quebra_catalogo(self):
        script=self.pacote('9router');(script.parent/'package.json').write_text('null')
        self.assertFalse(stack.catalogo_9stack()[0]['instalado_gerenciado'])

    def test_sem_localappdata_absoluto_nao_inventa_destino(self):
        with patch.dict(os.environ,{'LOCALAPPDATA':'relativo'}):
            self.assertFalse(stack.catalogo_9stack()[0]['instalado_gerenciado'])
            with self.assertRaises(RuntimeError):stack._pasta('9router')

    def test_pasta_redirecionada_nao_recebe_instalacao(self):
        destino=self.raiz/'local'/'MeuControlePC'
        destino.parent.mkdir(parents=True)
        outra=self.raiz/'fora';outra.mkdir()
        try:destino.symlink_to(outra,target_is_directory=True)
        except (OSError,NotImplementedError):self.skipTest('Symlink indisponivel nesta plataforma.')
        with self.assertRaises(RuntimeError):stack.instalar_9stack('9router',confirmado=True)
        self.assertFalse((outra/'integracoes').exists())
        self.popen.assert_not_called()

    def test_node_modules_redirecionado_tambem_e_recusado(self):
        destino=stack._pasta('9router');destino.mkdir(parents=True)
        outra=self.raiz/'fora';outra.mkdir()
        try:(destino/'node_modules').symlink_to(outra,target_is_directory=True)
        except (OSError,NotImplementedError):self.skipTest('Symlink indisponivel nesta plataforma.')
        with self.assertRaises(RuntimeError):stack.instalar_9stack('9router',confirmado=True)
        self.assertEqual(self.run.call_count,1)  # somente node --version

    def test_junction_windows_e_recusada_antes_de_npm(self):
        destino=stack._pasta('9remote')
        original=Path.lstat
        def lstat(pasta):
            if pasta==destino:
                return SimpleNamespace(st_mode=stat.S_IFDIR,st_file_attributes=0x400)
            return original(pasta)
        with patch.object(Path,'lstat',lstat), \
                patch.object(stack.stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400,create=True):
            with self.assertRaises(RuntimeError):stack.instalar_9stack('9remote',confirmado=True)
        self.assertEqual(self.run.call_count,1)

    def test_node_antigo_ou_saida_invalida_nao_abre_instalador(self):
        for stdout in ('v20.9.0','versao desconhecida','v22.0.0\nsegredo'):
            with self.subTest(stdout=stdout):
                self.run.return_value=SimpleNamespace(returncode=0,stdout=stdout)
                with self.assertRaises(RuntimeError):stack.executar_9stack('9router','instalar',confirmado=True)
        self.popen.assert_not_called()

    def test_timeout_node_nao_expoe_saida_de_processo(self):
        self.run.side_effect=subprocess.TimeoutExpired('node',5,output='SEGREDO_FIXTURE')
        with self.assertRaises(RuntimeError) as erro:stack.executar_9stack('9router','instalar',confirmado=True)
        self.assertNotIn('SEGREDO',str(erro.exception));self.popen.assert_not_called()

    def test_instalar_abre_worker_fixo_sem_npm_na_thread_do_bot(self):
        texto=stack.executar_9stack('9remote','instalar',confirmado=True)
        self.assertIn('solicitada',texto)
        args=self.popen.call_args.args[0]
        self.assertEqual(args,[sys.executable,str(Path(stack.__file__).resolve()),'--instalar','9remote','--confirmar'])
        self.assertIs(self.popen.call_args.kwargs['shell'],False)
        self.assertEqual(self.run.call_count,1)
        for segredo in ('TELEGRAM_TOKEN','OPENAI_API_KEY','NINE_ROUTER_API_KEY','NODE_OPTIONS'):
            self.assertNotIn(segredo,self.popen.call_args.kwargs['env'])

    def test_instalar_repetido_nao_abre_outro_worker_ativo(self):
        stack.executar_9stack('9router','instalar',confirmado=True)
        texto=stack.executar_9stack('9router','instalar',confirmado=True)
        self.popen.assert_called_once();self.assertIn('janela ativa',texto)

    def test_worker_npm_e_pinado_direto_por_node_com_timeout(self):
        self.pacote('9remote')
        self.run.side_effect=[SimpleNamespace(returncode=0,stdout='v24.0.0'),SimpleNamespace(returncode=0)]
        texto=stack.instalar_9stack('9remote',confirmado=True)
        self.assertIn('instalado',texto)
        args=self.run.call_args.args[0]
        self.assertEqual(args[0],str(self.node.resolve()))
        self.assertTrue(args[1].endswith('npm-cli.js'))
        self.assertIn('9remote@3.0.43',args);self.assertIn('--save-exact',args)
        self.assertIn('https://registry.npmjs.org',args)
        self.assertEqual(self.run.call_args.kwargs['timeout'],600)
        self.assertIs(self.run.call_args.kwargs['shell'],False)
        self.popen.assert_not_called()

    def test_worker_timeout_ou_npm_falha_nao_tenta_novamente(self):
        self.run.side_effect=[SimpleNamespace(returncode=0,stdout='v22.16.0'),subprocess.TimeoutExpired('npm',600)]
        with self.assertRaises(RuntimeError) as erro:stack.instalar_9stack('9router',confirmado=True)
        self.assertIn('10 minutos',str(erro.exception));self.assertEqual(self.run.call_count,2)

    def test_worker_sem_confirmacao_nao_cria_pasta(self):
        with self.assertRaises(PermissionError):stack.instalar_9stack('9remote')
        self.assertFalse((self.raiz/'local').exists());self.run.assert_not_called()

    def test_npm_cli_ausente_nao_invoca_cmd(self):
        (self.raiz/'node_modules'/'npm'/'bin'/'npm-cli.js').unlink()
        with self.assertRaises(RuntimeError):stack.instalar_9stack('9router',confirmado=True)
        self.assertEqual(self.run.call_count,1);self.popen.assert_not_called()

    def test_router_abrir_so_navegador_nao_inicia_servidor(self):
        texto=stack.executar_9stack('9router','abrir',confirmado=True)
        self.browser.assert_called_once_with('http://127.0.0.1:20128/dashboard')
        self.assertIn('nao inicia',texto);self.popen.assert_not_called();self.run.assert_not_called()

    def test_router_iniciar_forca_loopback_sem_update_ou_autostart(self):
        script=self.pacote('9router')
        texto=stack.executar_9stack('9router','iniciar',confirmado=True)
        self.assertIn('127.0.0.1:20128',texto)
        self.assertEqual(self.popen.call_args.args[0],[str(self.node.resolve()),str(script),
            '--host','127.0.0.1','--port','20128','--tray','--no-browser','--skip-update'])
        self.assertIs(self.popen.call_args.kwargs['shell'],False)
        self.assertNotIn('TELEGRAM_TOKEN',self.popen.call_args.kwargs['env'])

    def test_remote_abrir_ui_sem_solicitar_tunel(self):
        script=self.pacote('9remote')
        texto=stack.executar_9stack('9remote','abrir',confirmado=True)
        self.assertEqual(self.popen.call_args.args[0],[str(self.node.resolve()),str(script),'ui'])
        self.assertIn('sem pedir inicio do tunel',texto)
        self.assertEqual(self.popen.call_args.kwargs['cwd'],str(stack._pasta('9remote')))
        self.correcao.assert_called_once_with(script)

    def test_correcao_9remote_recusada_impede_inicio(self):
        self.pacote('9remote')
        self.correcao.side_effect=RuntimeError('Pacote diferente do oficial verificado.')
        with self.assertRaises(RuntimeError):
            stack.executar_9stack('9remote','iniciar',confirmado=True)
        self.popen.assert_not_called()

    def test_9router_nao_recebe_correcao_9remote(self):
        self.pacote('9router')
        stack.executar_9stack('9router','iniciar',confirmado=True)
        self.correcao.assert_not_called()

    def test_nova_instalacao_9remote_aplica_correcao_antes_de_concluir(self):
        script=self.pacote('9remote')
        stack.instalar_9stack('9remote',confirmado=True)
        self.correcao.assert_called_once_with(script)

    def test_remote_iniciar_e_acao_distinta_sem_capturar_chaves(self):
        script=self.pacote('9remote')
        texto=stack.executar_9stack('9remote','iniciar',confirmado=True)
        self.assertEqual(self.popen.call_args.args[0],[str(self.node.resolve()),str(script),'start'])
        self.assertNotIn('stdout',self.popen.call_args.kwargs)
        self.assertNotIn('stderr',self.popen.call_args.kwargs)
        self.assertIn('REMOTO',texto)

    def test_porta_ocupada_nao_inicia_ou_encerra_outro_aplicativo(self):
        self.porta.return_value=True
        for servico in ('9router','9remote'):
            texto=stack.executar_9stack(servico,'iniciar',confirmado=True)
            self.assertIn('Nenhuma instancia',texto)
        self.popen.assert_not_called();self.run.assert_not_called()

    def test_abrir_remote_ja_servindo_nao_repete_ui(self):
        self.porta.return_value=True
        texto=stack.executar_9stack('9remote','abrir',confirmado=True)
        self.browser.assert_called_once_with('http://127.0.0.1:2208/ui/index.html')
        self.assertIn('sem iniciar outra instancia',texto);self.popen.assert_not_called()

    def test_servico_ausente_nao_usa_npx_automatico(self):
        with self.assertRaises(RuntimeError):stack.executar_9stack('9remote','iniciar',confirmado=True)
        self.popen.assert_not_called();self.run.assert_not_called()

    def test_cli_listar_e_cancelar_nao_executam(self):
        with patch('sys.stdout',new=io.StringIO()):
            self.assertEqual(stack.main(['--listar']),0)
            with patch('builtins.input',return_value='nao'):
                self.assertEqual(stack.main(['--servico','9router','--operacao','iniciar']),0)
        self.run.assert_not_called();self.popen.assert_not_called()

    def test_cli_worker_requer_autorizacao_explicita(self):
        with patch('sys.stdout',new=io.StringIO()),patch.object(stack,'instalar_9stack') as instalar:
            self.assertEqual(stack.main(['--instalar','9remote']),1)
            instalar.assert_not_called()

    def test_cli_sem_argumentos_pergunta_operacao_antes_de_confirmar(self):
        with patch('sys.stdout',new=io.StringIO()), \
                patch('builtins.input',side_effect=['9router','instalar','sim']) as perguntas, \
                patch.object(stack,'executar_9stack',return_value='Fixture.') as executar:
            self.assertEqual(stack.main([]),0)
        self.assertEqual(perguntas.call_count,3)
        executar.assert_called_once_with('9router','instalar',confirmado=True)

    def test_cli_interativo_nao_aceita_operacao_livre(self):
        with patch('sys.stdout',new=io.StringIO()), \
                patch('builtins.input',side_effect=['9remote','key']) as perguntas, \
                patch.object(stack,'executar_9stack') as executar:
            self.assertEqual(stack.main([]),1)
        self.assertEqual(perguntas.call_count,2);executar.assert_not_called()


if __name__=='__main__':unittest.main()
