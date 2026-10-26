"""Identificação/parada do próprio bot com processos inteiramente simulados."""
import copy
import errno
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import controlar_instancia_preparacao as controle


class ControleInstanciaPreparacao(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.raiz=Path(self.tmp.name).resolve();self.codigo=self.raiz/'codigo';self.codigo.mkdir()
        self.dados=self.raiz/'instalacao'/'dados';self.dados.mkdir(parents=True)
        (self.codigo/'assistente_pc.py').write_text('# fonte fictícia',encoding='utf-8')
        self.python=self.codigo/'.venv'/'Scripts'/'python.exe';self.python.parent.mkdir(parents=True);self.python.write_bytes(b'fixture')
        self.pid=9876 if os.getpid()!=9876 else 9877
        self.trava={'ativa':True,'pid':self.pid,'assinatura':(1,2,3,5)}
        self.info={'pid':self.pid,'exe':str(self.python),'comando':'comando interno não exibido',
            'criado':'133000000000000000','owner_sid':'S-1-5-21-100','atual_sid':'S-1-5-21-100'}
        self.handle={n:v for n,v in self.info.items() if n!='comando'}
        self.processo=Mock();self.processo.identidade.return_value=self.handle;self.processo.aguardar.return_value=True
        for alvo,nome,valor in ((controle,'_WINDOWS',True),):
            p=patch.object(alvo,nome,valor);p.start();self.addCleanup(p.stop)
        p=patch.object(controle,'_inspecionar_trava',side_effect=[self.trava,self.trava,{'ativa':False}]);self.inspec=p.start();self.addCleanup(p.stop)
        p=patch.object(controle,'_metadados_windows',return_value=self.info);self.metadados=p.start();self.addCleanup(p.stop)
        p=patch.object(controle,'_argumentos_windows',return_value=[str(self.python),str(self.codigo/'assistente_pc.py')]);self.argv=p.start();self.addCleanup(p.stop)
        p=patch.object(controle,'_ProcessoWindows',return_value=self.processo);self.abrir=p.start();self.addCleanup(p.stop)

    def parar(self,**kw):
        return controle.parar_assistente(self.codigo,self.dados,autorizado=True,**kw)

    def test_autorizacao_estrita_precede_caminhos_processos_e_trava(self):
        with patch.object(controle,'_caminho') as caminho:
            for autorizado in (False,None,1,'sim'):
                with self.subTest(autorizado=autorizado),self.assertRaises(PermissionError):
                    controle.parar_assistente(self.codigo,self.dados,autorizado=autorizado)
        caminho.assert_not_called();self.inspec.assert_not_called();self.abrir.assert_not_called()

    def test_timeout_invalido_nao_consulta_processos(self):
        for valor in (True,0,31,float('nan'),float('inf'),'8'):
            with self.subTest(valor=valor),self.assertRaises(ValueError):self.parar(timeout=valor)
        self.inspec.assert_not_called();self.metadados.assert_not_called()

    def test_trava_livre_nao_encerra_nem_consulta_pid_antigo(self):
        self.inspec.side_effect=None;self.inspec.return_value={'ativa':False}
        resultado=self.parar()
        self.assertTrue(resultado['livre']);self.assertFalse(resultado['parado'])
        self.metadados.assert_not_called();self.abrir.assert_not_called()

    def test_somente_handle_identificado_e_encerrado_uma_vez(self):
        resultado=self.parar()
        self.assertTrue(resultado['parado']);self.assertTrue(resultado['livre']);self.assertFalse(resultado['pendente'])
        self.processo.parar.assert_called_once_with();self.processo.close.assert_called_once_with()
        self.abrir.assert_called_once_with(self.pid)
        self.assertEqual(self.processo.identidade.call_count,2)
        self.assertNotIn('comando',resultado);self.assertNotIn('S-1-',repr(resultado))

    def test_painel_sem_telegram_tambem_e_instancia_permitida(self):
        self.argv.return_value.append('--somente-painel')
        self.assertTrue(self.parar()['livre']);self.processo.parar.assert_called_once()

    def test_outros_argumentos_ou_scripts_nunca_sao_encerrados(self):
        casos=[[str(self.python),'-c','print(1)'],[str(self.python),str(self.codigo/'outro.py')],
            ['python.exe',str(self.codigo/'assistente_pc.py')],[str(self.python),'assistente_pc.py'],
            [str(self.python),str(self.codigo/'assistente_pc.py'),'--diagnostico'],
            [str(self.python),str(self.codigo/'assistente_pc.py'),'--somente-painel','extra']]
        for argv in casos:
            self.inspec.side_effect=None;self.inspec.return_value=self.trava;self.argv.return_value=argv
            with self.subTest(argv=argv):self.assertFalse(self.parar()['livre'])
        self.abrir.assert_not_called();self.processo.parar.assert_not_called()

    def test_outro_usuario_pid_executavel_ou_json_inesperado_e_recusado(self):
        casos=[{**self.info,'owner_sid':'S-1-5-21-200'}, {**self.info,'pid':self.pid+1},
            {**self.info,'exe':str(self.raiz/'outro'/'python.exe')}, {**self.info,'exe':str(self.codigo/'ollama.exe')},
            {**self.info,'criado':'invalido'}, {**self.info,'privado':'não permitido'}, {}]
        for info in casos:
            self.inspec.side_effect=None;self.inspec.return_value=self.trava;self.metadados.return_value=info
            with self.subTest(chaves=list(info)):self.assertFalse(self.parar()['livre'])
        self.abrir.assert_not_called();self.processo.parar.assert_not_called()

    def test_python_explicito_limita_a_instalacao_esperada(self):
        outro=self.raiz/'python.exe';outro.write_bytes(b'fixture')
        resultado=self.parar(python=outro)
        self.assertTrue(resultado['pendente']);self.abrir.assert_not_called()

    def test_pid_reutilizado_e_detectado_pelo_handle(self):
        self.processo.identidade.return_value={**self.handle,'criado':'133000000000000100'}
        resultado=self.parar()
        self.assertEqual(resultado['estado'],'identidade_alterada');self.processo.parar.assert_not_called()
        self.processo.close.assert_called_once()

    def test_precisao_cim_nao_rejeita_filetime_nativo_e_segunda_leitura_e_exata(self):
        nativo={**self.handle,'criado':'133000000000000007'}
        self.processo.identidade.return_value=nativo
        self.assertTrue(self.parar()['livre'])
        self.processo.parar.assert_called_once()

    def test_um_tick_alterado_na_segunda_leitura_do_handle_e_recusado(self):
        self.processo.identidade.side_effect=[self.handle,{**self.handle,'criado':'133000000000000001'}]
        self.assertEqual(self.parar()['estado'],'identidade_alterada');self.processo.parar.assert_not_called()

    def test_trava_trocada_ou_liberada_durante_identificacao_nao_dispara_parada(self):
        for atual in ({'ativa':False},{**self.trava,'assinatura':(1,2,4,5)},{**self.trava,'pid':self.pid+1}):
            self.inspec.side_effect=[self.trava,atual]
            with self.subTest(atual=atual):self.assertEqual(self.parar()['estado'],'identidade_alterada')
        self.processo.parar.assert_not_called()

    def test_identidade_revalidada_imediatamente_antes_da_parada(self):
        self.processo.identidade.side_effect=[self.handle,{**self.handle,'owner_sid':'S-1-5-21-200'}]
        self.assertEqual(self.parar()['estado'],'identidade_alterada');self.processo.parar.assert_not_called()

    def test_prazo_gasto_na_identificacao_nao_encerra_processo(self):
        with patch.object(controle.time,'monotonic',side_effect=[1,12]):resultado=self.parar(timeout=8)
        self.assertEqual(resultado['estado'],'prazo_esgotado');self.processo.parar.assert_not_called()

    def test_aguardar_falha_nao_repete_ou_presume_parada(self):
        self.processo.aguardar.return_value=False
        resultado=self.parar()
        self.assertFalse(resultado['livre']);self.assertFalse(resultado['parado'])
        self.processo.parar.assert_called_once();self.processo.close.assert_called_once()

    def test_outra_instancia_nao_e_encerrada_apos_a_primeira(self):
        self.inspec.side_effect=[self.trava,self.trava,{**self.trava,'pid':self.pid+1}]
        resultado=self.parar()
        self.assertTrue(resultado['parado']);self.assertFalse(resultado['livre']);self.assertEqual(resultado['estado'],'outra_instancia')
        self.processo.parar.assert_called_once();self.abrir.assert_called_once_with(self.pid)

    def test_erros_windows_nao_expoem_detalhes_ou_tentam_outro_alvo(self):
        self.metadados.side_effect=OSError('fixture-chave-privada')
        resultado=self.parar()
        self.assertTrue(resultado['pendente']);self.assertNotIn('fixture-chave',repr(resultado))
        self.abrir.assert_not_called();self.processo.parar.assert_not_called()

    def test_fora_windows_nao_tenta_metadados_ou_encerramento(self):
        with patch.object(controle,'_WINDOWS',False):resultado=self.parar()
        self.assertEqual(resultado['estado'],'indisponivel');self.metadados.assert_not_called();self.inspec.assert_not_called()


class LeituraTravaPreparacao(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.dados=Path(self.tmp.name)
        self.arquivo=self.dados/controle.instancia.NOME_TRAVA
        self.pid=9876 if os.getpid()!=9876 else 9877
        self.bruto=b'\x00'+str(self.pid).encode()

    def test_existencia_do_arquivo_nao_prova_instancia_ativa_nem_apaga_arquivo(self):
        self.arquivo.write_bytes(self.bruto)
        with patch.object(controle.instancia,'_bloquear') as bloquear,patch.object(controle.instancia,'_desbloquear') as desbloquear:
            self.assertEqual(controle._inspecionar_trava(self.dados),{'ativa':False})
        self.assertEqual(self.arquivo.read_bytes(),self.bruto);bloquear.assert_called_once();desbloquear.assert_called_once()

    def test_pid_so_e_lido_quando_lock_nao_pode_ser_adquirido(self):
        self.arquivo.write_bytes(self.bruto)
        with patch.object(controle.instancia,'_bloquear',side_effect=OSError(errno.EACCES,'fixture')),patch.object(controle.instancia,'_desbloquear') as desbloquear:
            resultado=controle._inspecionar_trava(self.dados)
        self.assertTrue(resultado['ativa']);self.assertEqual(resultado['pid'],self.pid);desbloquear.assert_not_called()
        self.assertEqual(self.arquivo.read_bytes(),self.bruto)

    def test_lock_corrompido_ou_pid_do_instalador_nao_e_utilizado(self):
        casos=[b'9876',b'\x009876;calc',b'\x000',b'\x00'+str(os.getpid()).encode(),b'x'*65]
        with patch.object(controle.instancia,'_bloquear',side_effect=OSError(errno.EACCES,'fixture')):
            for bruto in casos:
                self.arquivo.write_bytes(bruto)
                with self.subTest(bruto=bruto),self.assertRaises(ValueError):controle._inspecionar_trava(self.dados)

    def test_erros_de_acesso_diferentes_de_lock_nao_provam_trava_ativa(self):
        self.arquivo.write_bytes(b'\x009876')
        with patch.object(controle.instancia,'_bloquear',side_effect=OSError(errno.EINVAL,'fixture')):
            with self.assertRaises(ValueError):controle._inspecionar_trava(self.dados)

    def test_symlink_na_trava_e_recusado_sem_abrir_destino(self):
        alvo=self.dados/'outro';alvo.write_bytes(b'\x009876')
        try:self.arquivo.symlink_to(alvo)
        except (OSError,NotImplementedError):self.skipTest('Symlink indisponível nesta sessão.')
        with self.assertRaises(ValueError):controle._inspecionar_trava(self.dados)
        self.assertEqual(alvo.read_bytes(),b'\x009876')

    def test_metadados_powershell_usam_script_fixo_e_ambiente_sem_chaves(self):
        ps=self.dados/'System32'/'WindowsPowerShell'/'v1.0'/'powershell.exe';ps.parent.mkdir(parents=True);ps.write_bytes(b'fixture')
        retorno=SimpleNamespace(returncode=0,stdout='{}',stderr='')
        with patch.dict(os.environ,{'SYSTEMROOT':str(self.dados),'GEMINI_API_KEY':'fixture-segredo'},clear=True),patch.object(controle.subprocess,'run',return_value=retorno) as executar:
            self.assertEqual(controle._metadados_windows(9876,3),{})
        kw=executar.call_args.kwargs
        self.assertIs(kw['shell'],False);self.assertEqual(json.loads(kw['input']),{'pid':9876});self.assertEqual(kw['timeout'],3)
        self.assertNotIn('fixture-segredo',repr(executar.call_args));self.assertIn('-NoProfile',executar.call_args.args[0])


if __name__=='__main__':unittest.main()
