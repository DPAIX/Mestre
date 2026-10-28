"""Perfis Node e validação do gateway simulados, sem serviço ou credenciais reais."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import configuracao_assistente as configuracao
import configurar_gateway_automatico as gateway
import correcao_dns_9remote as correcao
import instalacao_em_f as instalacao
import integracoes_9stack as stack


class IntegracoesSomenteF(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.raiz=Path(self.tmp.name)/'disco_f'
        self.c=Path(self.tmp.name)/'perfil_c'
        self.node=self.raiz/'ferramentas'/'nodejs'/'node.exe'
        self.node.parent.mkdir(parents=True);self.node.write_text('fixture')
        self.npm=self.node.parent/'node_modules'/'npm'/'bin'/'npm-cli.js'
        self.npm.parent.mkdir(parents=True);self.npm.write_text('fixture')
        for contexto in (patch.object(instalacao,'ativo',return_value=True),
                patch.object(instalacao,'raiz',return_value=self.raiz),
                patch.object(instalacao,'validar_caminho',side_effect=lambda p:Path(p)),
                patch.object(instalacao,'preparar_pastas'),
                patch.object(stack.sys,'platform','win32'),
                patch.dict(os.environ,{'APPDATA':str(self.c/'Roaming'),
                    'LOCALAPPDATA':str(self.c/'Local'),'USERPROFILE':str(self.c),
                    'PATH':'fixture-path','TELEGRAM_TOKEN':'fixture-nao-herdar',
                    'OPENAI_API_KEY':'fixture-nao-herdar','NODE_OPTIONS':'fixture-nao-herdar',
                    'MEUCONTROLEPC_ENV':str(self.raiz/'configuracao.env'),
                    'MEUCONTROLEPC_DADOS':str(self.raiz/'dados')},clear=True)):
            contexto.start();self.addCleanup(contexto.stop)

    def pacote(self,servico):
        raiz=stack._pasta(servico)/'node_modules'/servico
        raiz.mkdir(parents=True)
        (raiz/'package.json').write_text(json.dumps({'name':servico,'version':stack.SERVICOS[servico]['versao']}))
        script=raiz/stack.SERVICOS[servico]['script']
        script.parent.mkdir(parents=True,exist_ok=True);script.write_text('fixture')
        return raiz,script

    def test_perfis_e_caches_dos_filhos_f_sem_mudar_windows_ou_copiar_segredos(self):
        anterior=dict(os.environ)
        env=stack._ambiente()
        for chave in ('APPDATA','LOCALAPPDATA','USERPROFILE','TEMP','TMP','NPM_CONFIG_CACHE','HF_HOME'):
            self.assertTrue(Path(env[chave]).is_relative_to(self.raiz),chave)
        for chave in ('TELEGRAM_TOKEN','OPENAI_API_KEY','NODE_OPTIONS','HOME','CODEX_HOME'):
            self.assertNotIn(chave,env)
        self.assertEqual(dict(os.environ),anterior)
        self.assertFalse((self.c/'Local').exists())

    def test_pacotes_somente_no_localappdata_do_perfil_f(self):
        esperado=self.raiz/'runtime'/'Local'/'MeuControlePC'/'integracoes'
        self.assertEqual(stack._pasta('9router'),esperado/'9router')
        self.assertEqual(stack._pasta('9remote'),esperado/'9remote')
        self.assertFalse(esperado.exists())  # A consulta não cria pastas.

    def test_ancestral_redirecionado_nao_recebe_npm(self):
        outro=Path(self.tmp.name)/'outro';outro.mkdir()
        try:(self.raiz/'runtime').symlink_to(outro,target_is_directory=True)
        except (OSError,NotImplementedError):self.skipTest('Symlink indisponível.')
        with self.assertRaises(RuntimeError):stack._pasta('9router')

    def test_node_existente_no_f_e_preferido_sem_winget(self):
        with patch.object(stack.shutil,'which',side_effect=AssertionError('Node F já existe.')), \
                patch.object(stack.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='v24.12.0\n')) as run:
            self.assertEqual(stack._node(stack._ambiente()),self.node.resolve())
        self.assertEqual(run.call_args.args[0],[str(self.node.resolve()),'--version'])

    def test_node_ausente_fica_pendente_sem_instalador_em_c(self):
        with patch.object(stack,'_node',side_effect=RuntimeError('fixture')), \
                patch.object(configuracao.subprocess,'run') as run, \
                patch.object(configuracao.shutil,'which') as which:
            with self.assertRaisesRegex(RuntimeError,'portable oficial'):
                configuracao._preparar_node()
        run.assert_not_called();which.assert_not_called()

    def test_npm_e_perfil_preparados_em_f_sem_apagar_origem(self):
        _,script=self.pacote('9router')
        with patch.object(stack.shutil,'which',return_value=None),patch.object(stack.subprocess,'run',side_effect=[
                SimpleNamespace(returncode=0,stdout='v24.12.0\n'),SimpleNamespace(returncode=0)]) as run:
            stack.instalar_9stack('9router',confirmado=True)
        chamada=run.call_args
        self.assertEqual(chamada.args[0][:2],[str(self.node.resolve()),str(self.npm)])
        self.assertEqual(chamada.kwargs['cwd'],str(stack._pasta('9router')))
        self.assertEqual(chamada.kwargs['env']['APPDATA'],str(self.raiz/'runtime'/'Roaming'))
        self.assertTrue(script.is_file())
        self.assertFalse(self.c.exists())

    def test_configurador_principal_preserva_appdata_para_startup_do_windows(self):
        env=configuracao._ambiente_configurador()
        self.assertEqual(env['APPDATA'],str(self.c/'Roaming'))
        self.assertEqual(env['USERPROFILE'],str(self.c))
        self.assertEqual(env['TEMP'],str(self.raiz/'temporarios'))
        self.assertEqual(env['MEUCONTROLEPC_SOMENTE_F'],'1')
        self.assertNotIn('TELEGRAM_TOKEN',env)

    def test_correcao_9remote_reconhece_somente_pacote_f_gerenciado(self):
        raiz,_=self.pacote('9remote')
        self.assertEqual(correcao._pacote(raiz),raiz.resolve())
        with self.assertRaises(correcao.FalhaCorrecao):
            correcao._pacote(self.c/'Local'/'MeuControlePC'/'integracoes'/'9remote'/'node_modules'/'9remote')

    def test_perfil_gateway_em_f_sem_ler_c(self):
        with patch.object(Path,'read_text',side_effect=AssertionError('Consulta pura.')):
            self.assertEqual(gateway._diretorio(),self.raiz/'runtime'/'Roaming'/'9router')

    def test_bootstrap_sem_psutil_prova_pela_venv_f_sem_instalar_no_c(self):
        python=self.raiz/'aplicativo'/'.venv'/'Scripts'/'python.exe'
        python.parent.mkdir(parents=True);python.write_text('fixture')
        with patch.dict(sys.modules,{'psutil':None}), \
                patch.object(stack.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='{"comprovado":true}')) as run:
            self.assertTrue(stack.servico_f_comprovado('9router'))
        self.assertEqual(run.call_args.args[0][0],str(python))
        self.assertNotIn('pip',run.call_args.args[0])

    def test_filho_sem_psutil_nao_inicia_recursao_ou_servico(self):
        with patch.dict(sys.modules,{'psutil':None}),patch.object(stack.subprocess,'run') as run:
            self.assertFalse(stack.servico_f_comprovado('9router',_filho=True))
        run.assert_not_called()

    def psutil(self,**alteracoes):
        env=stack._perfil_f()
        processo=Mock()
        processo.exe.return_value=str(self.node)
        processo.environ.return_value=env
        pasta=stack._pasta('9router')
        processo.cwd.return_value=str(pasta)
        processo.cmdline.return_value=[str(self.node),str(pasta/'node_modules'/'9router'/'cli.js')]
        for nome,valor in alteracoes.items():getattr(processo,nome).return_value=valor
        conexao=SimpleNamespace(status='LISTEN',pid=42,laddr=SimpleNamespace(port=20128))
        modulo=SimpleNamespace(CONN_LISTEN='LISTEN',net_connections=Mock(return_value=[conexao]),
                               Process=Mock(return_value=processo))
        return modulo

    def test_listener_node_em_f_pode_ser_reconhecido_sem_expor_ambiente(self):
        modulo=self.psutil()
        modulo.Process.return_value.environ.return_value['DADO_PRIVADO']='fixture-nao-exibir'
        with patch.dict(sys.modules,{'psutil':modulo}):
            self.assertIs(stack.servico_f_comprovado('9router'),True)
        modulo.net_connections.assert_called_once_with(kind='tcp')

    def test_listener_perfil_c_ou_sem_identidade_nao_e_autorizado(self):
        variacoes=({'environ':{'APPDATA':str(self.c)}},
                   {'cwd':str(self.c)}, {'exe':str(self.node.parent/'outro.exe')},
                   {'cmdline':[str(self.node),str(self.c/'script.js')]})
        for alteracao in variacoes:
            with self.subTest(alteracao=alteracao),patch.dict(sys.modules,{'psutil':self.psutil(**alteracao)}):
                self.assertIs(stack.servico_f_comprovado('9router'),False)

    def test_sem_acesso_ao_ambiente_do_processo_continua_pendente(self):
        modulo=self.psutil();modulo.Process.return_value.environ.side_effect=PermissionError('fixture-nao-exibir')
        with patch.dict(sys.modules,{'psutil':modulo}):
            self.assertFalse(stack.servico_f_comprovado('9router'))

    def test_porta_antiga_c_nao_e_reaberta_ou_encerrada(self):
        with patch.object(stack,'_porta_ocupada',return_value=True), \
                patch.object(stack,'servico_f_comprovado',return_value=False), \
                patch.object(stack.subprocess,'Popen') as popen, \
                patch.object(stack.webbrowser,'open') as browser:
            with self.assertRaisesRegex(RuntimeError,'perfil em F nao foi comprovado'):
                stack.executar_9stack('9remote','abrir',confirmado=True)
        popen.assert_not_called();browser.assert_not_called()

    def test_gateway_nao_autentica_nem_escreve_em_instancia_antiga(self):
        env=self.raiz/'configuracao.env';env.write_text('NINE_ROUTER_URL=http://127.0.0.1:20128/v1\n')
        with patch.object(stack,'servico_f_comprovado',return_value=False), \
                patch.object(gateway,'_metadados') as metadados, \
                patch.object(gateway,'_token_cli') as token, \
                patch.object(gateway,'_requisicao') as requisicao, \
                patch.object(gateway,'_atualizar_opcoes_env') as escrever:
            resultado=gateway.configurar_gateway(caminho_env=env,autorizado=True)
        self.assertFalse(resultado['alterado'])
        self.assertIn('perfil em F',resultado['pendencias'][0])
        metadados.assert_not_called();token.assert_not_called();requisicao.assert_not_called();escrever.assert_not_called()

    def test_gateway_porta_diferente_nao_reusa_prova_da_20128(self):
        env=self.raiz/'configuracao.env';env.write_text('NINE_ROUTER_URL=http://127.0.0.1:20129/v1\n')
        with patch.object(stack,'servico_f_comprovado',return_value=True), \
                patch.object(gateway,'_requisicao') as requisicao:
            resultado=gateway.configurar_gateway(caminho_env=env,autorizado=True)
        self.assertIn('outra porta',resultado['pendencias'][0]);requisicao.assert_not_called()

    def test_planejamento_gateway_permanece_leitura_pura_sem_inspecao_processos(self):
        env=self.raiz/'configuracao.env';env.write_text('NINE_ROUTER_URL=http://127.0.0.1:20128/v1\n')
        with patch.object(stack,'servico_f_comprovado',side_effect=AssertionError('Não sondar.')), \
                patch.object(gateway,'_metadados',return_value={'combos':[],'provedores_ativos':False}):
            resultado=gateway.planejar_gateway(caminho_env=env)
        self.assertFalse(resultado['configurado'])


if __name__=='__main__':unittest.main()
