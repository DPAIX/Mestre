"""Diagnóstico de dono da porta com metadados fictícios; sem processos Windows."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import iniciar_servicos_locais as servicos


class DiagnosticoPortaOllama(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.raiz=Path(self.tmp.name).resolve()
        self.powershell=self.raiz/'System32'/'WindowsPowerShell'/'v1.0'/'powershell.exe'
        self.powershell.parent.mkdir(parents=True);self.powershell.write_bytes(b'fixture')
        p=patch.dict(os.environ,{'SYSTEMROOT':str(self.raiz),'OLLAMA_HABILITADO':'1',
            'OLLAMA_MODELS':str(self.raiz/'Models'),'OPENAI_API_KEY':'fixture_segredo_privado',
            'HTTPS_PROXY':'http://fixture_segredo_privado.invalid','PYTHONPATH':'fixture_segredo_privado'},clear=True)
        p.start();self.addCleanup(p.stop)
        p=patch.object(servicos,'_WINDOWS',True);p.start();self.addCleanup(p.stop)
        p=patch.object(servicos,'consultar',return_value={'ok':False,'categoria':'timeout'});self.api=p.start();self.addCleanup(p.stop)
        p=patch.object(servicos.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='{"listeners":[]}'))
        self.run=p.start();self.addCleanup(p.stop)
        p=patch.object(servicos.subprocess,'Popen');self.iniciar=p.start();self.addCleanup(p.stop)

    def listeners(self,itens):
        self.run.return_value=SimpleNamespace(returncode=0,stdout=json.dumps({'listeners':itens}))

    def test_api_pronta_nao_executa_powershell_nem_inicia_processo(self):
        self.api.return_value={'ok':True,'dados':{'version':'fixture'}}
        d=servicos.diagnosticar_porta_ollama()
        self.assertEqual(d['estado'],'api_pronta');self.assertIs(d['api_responde'],True)
        self.api.assert_called_once_with(servicos.URL_PADRAO,'/api/version',timeout=3)
        self.run.assert_not_called();self.iniciar.assert_not_called()

    def test_dono_ollama_e_identificado_sem_autorizar_reinicio(self):
        self.listeners([{'pid':4321,'nome':'ollama'}])
        d=servicos.diagnosticar_porta_ollama()
        self.assertEqual(d['estado'],'ocupada_ollama')
        self.assertEqual(d['processos'],[{'pid':4321,'nome':'ollama.exe','tipo':'ollama'}])
        self.assertEqual(d['acao_recomendada'],'conferir_ollama_existente')
        self.assertFalse(d['reparo_automatico']);self.iniciar.assert_not_called()

    def test_consulta_windows_e_limitada_ao_endpoint_local_e_sem_segredos(self):
        self.listeners([{'pid':11,'nome':'node'}])
        d=servicos.diagnosticar_porta_ollama('http://[::1]:11435',sondar_api=False)
        self.assertEqual(d['estado'],'ocupada_outro');self.assertEqual(d['porta'],11435)
        self.api.assert_not_called();self.run.assert_called_once()
        args,kw=self.run.call_args
        self.assertEqual(args[0][0],str(self.powershell));self.assertEqual(args[0][1:4],['-NoProfile','-NonInteractive','-Command'])
        script=args[0][4]
        self.assertIn('LocalPort -eq 11435',script);self.assertIn("'::1'",script)
        self.assertNotIn('CommandLine',script);self.assertNotIn('ExecutablePath',script)
        self.assertEqual(kw['timeout'],4);self.assertIs(kw['shell'],False)
        self.assertEqual(kw['stderr'],subprocess.DEVNULL);self.assertEqual(kw['stdin'],subprocess.DEVNULL)
        self.assertNotIn('fixture_segredo_privado',repr(self.run.call_args))
        self.assertNotIn('fixture_segredo_privado',repr(d));self.iniciar.assert_not_called()

    def test_nome_arbitrario_e_omitido_mantendo_so_pid_e_rotulo(self):
        self.listeners([{'pid':987,'nome':'fixture_segredo_privado'}])
        d=servicos.diagnosticar_porta_ollama(sondar_api=False)
        self.assertEqual(d['processos'],[{'pid':987,'nome':'outro processo','tipo':'outro'}])
        self.assertNotIn('fixture_segredo_privado',repr(d))

    def test_pid_sem_nome_nao_e_tratado_como_ollama(self):
        self.listeners([{'pid':65,'nome':None}])
        d=servicos.diagnosticar_porta_ollama(sondar_api=False)
        self.assertEqual(d['estado'],'ocupada_nao_identificada')
        self.assertEqual(d['processos'][0]['tipo'],'nao_identificado')

    def test_sem_listener_e_amostra_nao_prova_api_ou_porta_livre(self):
        d=servicos.diagnosticar_porta_ollama(sondar_api=False)
        self.assertEqual(d['estado'],'sem_escuta_identificada');self.assertIsNone(d['api_responde'])
        self.assertEqual(d['processos'],[]);self.assertFalse(d['reparo_automatico'])
        self.api.assert_not_called();self.iniciar.assert_not_called()

    def test_timeout_ou_erro_windows_nao_expoe_erro_bruto(self):
        for erro in (OSError('fixture_segredo_privado'),subprocess.TimeoutExpired(['fixture_segredo_privado'],4)):
            with self.subTest(erro=type(erro).__name__):
                self.run.side_effect=erro
                d=servicos.diagnosticar_porta_ollama(sondar_api=False)
                self.assertEqual(d['estado'],'indeterminada');self.assertNotIn('fixture_segredo_privado',repr(d))
                self.assertFalse(d['reparo_automatico'])
        self.iniciar.assert_not_called()

    def test_schema_pid_e_tamanho_invalidos_nao_revelam_stdout(self):
        casos=['{nao json','{"listeners":[],"privado":"fixture_segredo_privado"}',
            json.dumps({'listeners':[{'pid':True,'nome':'ollama'}]}),
            json.dumps({'listeners':[{'pid':-1,'nome':'ollama'}]}),
            json.dumps({'listeners':[{'pid':1,'nome':'ollama','commandline':'fixture_segredo_privado'}]}),
            'fixture_segredo_privado'*600]
        for bruto in casos:
            with self.subTest(bruto=bruto[:20]):
                self.run.return_value=SimpleNamespace(returncode=0,stdout=bruto)
                d=servicos.diagnosticar_porta_ollama(sondar_api=False)
                self.assertEqual(d['estado'],'indeterminada');self.assertNotIn('fixture_segredo_privado',repr(d))
        self.iniciar.assert_not_called()

    def test_pid_duplicado_e_emitido_uma_vez(self):
        self.listeners([{'pid':12,'nome':'ollama'},{'pid':12,'nome':'ollama'}])
        self.assertEqual(len(servicos.diagnosticar_porta_ollama(sondar_api=False)['processos']),1)

    def test_executavel_windows_ausente_nao_procura_scripts_no_path(self):
        self.powershell.unlink()
        d=servicos.diagnosticar_porta_ollama(sondar_api=False)
        self.assertEqual(d['estado'],'indeterminada');self.run.assert_not_called()

    def test_endpoint_remoto_invalido_ou_flag_invalida_nao_executam_sondas(self):
        for url in ('http://example.invalid:11434','http://10.0.0.1:11434','http://usuario:fixture_segredo_privado@127.0.0.1:11434'):
            with self.subTest(url=url):
                d=servicos.diagnosticar_porta_ollama(url)
                self.assertEqual(d['estado'],'endereco_invalido');self.assertNotIn('fixture_segredo_privado',repr(d))
        with self.assertRaises(ValueError):servicos.diagnosticar_porta_ollama(sondar_api=1)
        self.api.assert_not_called();self.run.assert_not_called();self.iniciar.assert_not_called()

    def test_outro_sistema_nao_diagnostica_como_se_fosse_pc_windows(self):
        with patch.object(servicos,'_WINDOWS',False):
            d=servicos.diagnosticar_porta_ollama()
        self.assertEqual(d['estado'],'plataforma_nao_suportada')
        self.api.assert_not_called();self.run.assert_not_called()

    def test_inicio_com_porta_ocupada_identifica_sem_repetir_api_ou_servidor(self):
        self.listeners([{'pid':4321,'nome':'ollama'}])
        with patch.object(servicos,'_porta_ocupada',return_value=True):
            d=servicos.garantir_ollama()
        self.assertEqual(set(d),{'ok','iniciado','mensagem'})
        self.assertFalse(d['ok']);self.assertFalse(d['iniciado'])
        self.assertIn('PID 4321',d['mensagem']);self.assertIn('Nenhum segundo servidor',d['mensagem'])
        self.api.assert_called_once();self.run.assert_called_once();self.iniciar.assert_not_called()

    def test_politica_zero_impede_diagnostico_e_inicio_automatico(self):
        with patch.dict(os.environ,{'OLLAMA_INICIAR_SERVICO':'0'}),patch.object(servicos,'_porta_ocupada') as porta:
            d=servicos.garantir_ollama()
        self.assertFalse(d['iniciado']);porta.assert_not_called();self.run.assert_not_called();self.iniciar.assert_not_called()


if __name__=='__main__':unittest.main()
