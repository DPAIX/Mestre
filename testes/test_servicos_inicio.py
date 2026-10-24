"""Início local finito e singleton com fixtures, sem Ollama ou Windows reais."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import iniciar_servicos_locais as servicos
import instancia_assistente as instancia


class InicioOllamaTeste(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name).resolve()
        self.codigo = self.raiz / 'codigo'
        self.codigo.mkdir()
        self.env_externo = self.raiz / 'instalacao' / '.env'
        self.env_externo.parent.mkdir()
        self.executavel = self.raiz / 'ollama-fixture.exe'
        self.executavel.write_bytes(b'fixture-nao-executavel')
        self.segredo = 'fixture-chave-privada-nao-exibir'
        p = patch.dict(os.environ, {
            'OLLAMA_HABILITADO': '1', 'MEUCONTROLEPC_ENV': str(self.env_externo),
            'OPENAI_API_KEY': self.segredo, 'PYTHONPATH': self.segredo,
            'OLLAMA_HOST': 'http://192.168.1.5:11434',
        }, clear=True)
        p.start(); self.addCleanup(p.stop)
        p = patch.object(servicos, 'BASE', self.codigo)
        p.start(); self.addCleanup(p.stop)
        p = patch.object(servicos.shutil, 'which', return_value=str(self.executavel))
        self.which = p.start(); self.addCleanup(p.stop)
        p = patch.object(servicos, 'consultar', return_value={'ok': False, 'categoria': 'conexao'})
        self.consultar = p.start(); self.addCleanup(p.stop)
        p = patch.object(servicos.subprocess, 'Popen')
        self.iniciar = p.start(); self.addCleanup(p.stop)
        self.iniciar.return_value.poll.return_value = None
        p = patch.object(servicos.time, 'sleep')
        self.pausa = p.start(); self.addCleanup(p.stop)

    def respondeu(self):
        return {'ok': True, 'dados': {'version': '0.40.8'}}

    def test_desabilitado_nao_consulta_nem_inicia_servico(self):
        os.environ['OLLAMA_HABILITADO'] = '0'
        resultado = servicos.garantir_ollama()
        self.assertFalse(resultado['ok'])
        self.assertFalse(resultado['iniciado'])
        self.consultar.assert_not_called()
        self.which.assert_not_called()
        self.iniciar.assert_not_called()

    def test_endereco_remoto_ou_credencial_na_url_nao_abrem_rede(self):
        for url in ('https://example.invalid', 'http://192.168.1.1:11434',
                    'http://usuario:segredo@127.0.0.1:11434', 'http://localhost:11434'):
            with self.subTest(url=url), patch.dict(os.environ, {'OLLAMA_URL': url}):
                resultado = servicos.garantir_ollama()
                self.assertFalse(resultado['iniciado'])
                self.assertNotIn('segredo', resultado['mensagem'])
        self.consultar.assert_not_called()
        self.iniciar.assert_not_called()

    def test_servico_ativo_so_confirma_metadados_sem_iniciar_ou_gerar(self):
        self.consultar.return_value = self.respondeu()
        resultado = servicos.garantir_ollama()
        self.assertEqual(set(resultado), {'ok', 'iniciado', 'mensagem'})
        self.assertTrue(resultado['ok'])
        self.assertFalse(resultado['iniciado'])
        self.consultar.assert_called_once_with('http://127.0.0.1:11434', '/api/version', timeout=3)
        self.iniciar.assert_not_called()
        self.assertIn('geração ainda não verificada', resultado['mensagem'])

    def test_executavel_ausente_nao_instala_ou_abre_processo(self):
        self.which.return_value = None
        with patch.object(servicos, '_WINDOWS', False):
            resultado = servicos.garantir_ollama()
        self.assertFalse(resultado['ok'])
        self.assertFalse(resultado['iniciado'])
        self.iniciar.assert_not_called()
        self.consultar.assert_called_once()

    def test_windows_encontra_executavel_instalado_fora_do_path(self):
        self.which.return_value = None
        executavel = self.raiz / 'AppData' / 'Programs' / 'Ollama' / 'ollama.exe'
        executavel.parent.mkdir(parents=True)
        executavel.write_bytes(b'fixture-nao-executavel')
        self.consultar.side_effect = [{'ok': False}, self.respondeu()]
        with patch.object(servicos, '_WINDOWS', True), \
                patch.dict(os.environ, {'LOCALAPPDATA': str(self.raiz / 'AppData')}):
            resultado = servicos.garantir_ollama()
        self.assertTrue(resultado['ok'])
        self.assertEqual(self.iniciar.call_args.args[0], [str(executavel.resolve()), 'serve'])
        self.assertEqual(self.iniciar.call_args.kwargs['creationflags'], 0x08000000)

    def test_inicio_unico_preserva_modelos_e_ambiente_publico_sem_chaves_ou_host_remoto(self):
        self.consultar.side_effect = [{'ok': False}, {'ok': False}, self.respondeu()]
        ambiente = {'OLLAMA_URL': 'http://127.0.0.1:11435/', 'OLLAMA_MODELS': str(self.raiz / 'modelos'),
                    'USERPROFILE': 'fixture-perfil', 'PATH': 'fixture-path'}
        with patch.dict(os.environ, ambiente), patch.object(servicos, '_WINDOWS', False):
            resultado = servicos.garantir_ollama()
        self.assertTrue(resultado['ok'])
        self.assertTrue(resultado['iniciado'])
        self.iniciar.assert_called_once()
        opcoes = self.iniciar.call_args.kwargs
        self.assertIs(opcoes['shell'], False)
        self.assertEqual(opcoes['stdin'], subprocess.DEVNULL)
        self.assertEqual(opcoes['stdout'], subprocess.DEVNULL)
        self.assertEqual(opcoes['stderr'], subprocess.DEVNULL)
        self.assertEqual(opcoes['env']['OLLAMA_HOST'], 'http://127.0.0.1:11435')
        self.assertEqual(opcoes['env']['OLLAMA_MODELS'], ambiente['OLLAMA_MODELS'])
        self.assertEqual(opcoes['env']['USERPROFILE'], 'fixture-perfil')
        self.assertNotIn(self.segredo, repr(opcoes))
        self.assertTrue(all(c.args[:2] == ('http://127.0.0.1:11435', '/api/version')
                            for c in self.consultar.call_args_list))

    def test_estrutura_de_modelos_existente_e_reaproveitada_sem_criar_ou_ler_env(self):
        modelos = self.raiz / 'Models'
        (modelos / 'manifests').mkdir(parents=True)
        self.consultar.side_effect = [{'ok': False}, self.respondeu()]
        self.assertFalse(self.env_externo.exists())
        resultado = servicos.garantir_ollama()
        self.assertTrue(resultado['ok'])
        self.assertEqual(self.iniciar.call_args.kwargs['env']['OLLAMA_MODELS'], str(modelos))
        self.assertFalse(self.env_externo.exists())

    def test_bloqueio_nuvem_verdadeiro_e_preservado_normalizado_no_servidor(self):
        for valor in ('1', 'true', 'TRUE', 'TrUe'):
            with self.subTest(valor=valor), patch.dict(os.environ, {'OLLAMA_NO_CLOUD': valor}):
                self.consultar.side_effect = [{'ok': False}, self.respondeu()]
                self.iniciar.reset_mock()
                resultado = servicos.garantir_ollama()
                self.assertTrue(resultado['ok'])
                self.iniciar.assert_called_once()
                ambiente = self.iniciar.call_args.kwargs['env']
                self.assertEqual(ambiente['OLLAMA_NO_CLOUD'], '1')
                self.assertEqual(ambiente['OLLAMA_HOST'], 'http://127.0.0.1:11434')
                self.assertNotIn(self.segredo, repr(ambiente))

    def test_bloqueio_nuvem_aceita_nome_de_variavel_sem_distinguir_caixa_no_windows(self):
        for nome in ('ollama_no_cloud', 'Ollama_No_Cloud'):
            with self.subTest(nome=nome), patch.dict(os.environ, {
                    nome: 'TrUe', 'OLLAMA_MODELS': str(self.raiz / 'modelos')}, clear=True):
                ambiente = servicos._ambiente_servidor('http://127.0.0.1:11434')
                self.assertEqual(ambiente['OLLAMA_NO_CLOUD'], '1')
                self.assertEqual(sum(k.upper() == 'OLLAMA_NO_CLOUD' for k in ambiente), 1)

    def test_bloqueio_nuvem_ausente_ou_falso_nao_e_injetado_no_servidor(self):
        for valor in (None, '', '0', 'false', 'FALSE', 'yes', 'true-invalido'):
            entradas = {'OLLAMA_MODELS': str(self.raiz / 'modelos')}
            if valor is not None:
                entradas['OLLAMA_NO_CLOUD'] = valor
            with self.subTest(valor=valor), patch.dict(os.environ, entradas, clear=True):
                ambiente = servicos._ambiente_servidor('http://127.0.0.1:11434')
                self.assertNotIn('OLLAMA_NO_CLOUD', ambiente)

    def test_pasta_vazia_nao_substitui_diretorio_padrao_de_modelos(self):
        (self.raiz / 'Models').mkdir()
        self.consultar.side_effect = [{'ok': False}, self.respondeu()]
        servicos.garantir_ollama()
        self.assertNotIn('OLLAMA_MODELS', self.iniciar.call_args.kwargs['env'])

    def test_executavel_falha_nao_expoe_erro_bruto_ou_tenta_novamente(self):
        self.iniciar.side_effect = OSError(self.segredo)
        resultado = servicos.garantir_ollama()
        self.assertFalse(resultado['ok'])
        self.assertFalse(resultado['iniciado'])
        self.assertNotIn(self.segredo, resultado['mensagem'])
        self.iniciar.assert_called_once()

    def test_processo_encerrado_nao_e_reiniciado(self):
        self.iniciar.return_value.poll.return_value = 1
        resultado = servicos.garantir_ollama()
        self.assertFalse(resultado['ok'])
        self.assertTrue(resultado['iniciado'])
        self.iniciar.assert_called_once()
        self.assertEqual(self.consultar.call_count, 2)

    def test_espera_tem_numero_finito_de_consultas_e_um_so_processo(self):
        resultado = servicos.garantir_ollama()
        self.assertFalse(resultado['ok'])
        self.assertTrue(resultado['iniciado'])
        self.assertEqual(self.consultar.call_count, servicos.MAX_CONSULTAS + 1)
        self.iniciar.assert_called_once()
        self.assertLessEqual(self.pausa.call_count, servicos.MAX_CONSULTAS)

    def test_prazo_total_limita_timeout_final_e_interrompe_consultas(self):
        with patch.object(servicos.time, 'monotonic', side_effect=[0, 3, 6, 14.5, 15.1, 15.2]):
            resultado = servicos.garantir_ollama()
        self.assertFalse(resultado['ok'])
        self.assertEqual([c.kwargs['timeout'] for c in self.consultar.call_args_list], [3, 3, 0.5])
        self.iniciar.assert_called_once()


class InstanciaUnicaTeste(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name).resolve()

    def test_contem_pid_sem_segredos_e_libera_ao_sair_mantendo_arquivo(self):
        with instancia.instancia_unica(self.raiz):
            with self.assertRaises(instancia.InstanciaAtiva):
                with instancia.instancia_unica(self.raiz):
                    self.fail('Segunda instância não deve entrar.')
        self.assertTrue((self.raiz / instancia.NOME_TRAVA).is_file())
        self.assertEqual((self.raiz / instancia.NOME_TRAVA).read_bytes(), b'\0'+str(os.getpid()).encode('ascii'))
        with instancia.instancia_unica(self.raiz):
            pass

    def test_excecao_da_aplicacao_nao_retém_trava(self):
        with self.assertRaisesRegex(ValueError, 'fixture'):
            with instancia.instancia_unica(self.raiz):
                raise ValueError('fixture')
        with instancia.instancia_unica(self.raiz):
            pass

    def test_pastas_de_dados_diferentes_tem_instancias_independentes(self):
        with instancia.instancia_unica(self.raiz / 'primeiro'):
            with instancia.instancia_unica(self.raiz / 'segundo'):
                pass

    def test_outro_processo_respeita_trava_e_entrada_posterior_e_permitida(self):
        codigo = '''from instancia_assistente import instancia_unica, InstanciaAtiva
import sys
try:
    with instancia_unica(sys.argv[1]): print('ADQUIRIDA')
except InstanciaAtiva:
    print('BLOQUEADA')
'''
        def executar():
            return subprocess.run([sys.executable, '-c', codigo, str(self.raiz)],
                                  cwd=str(Path(instancia.__file__).resolve().parent),
                                  stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                  shell=False, timeout=5, check=True).stdout.strip()
        with instancia.instancia_unica(self.raiz):
            self.assertEqual(executar(), 'BLOQUEADA')
        self.assertEqual(executar(), 'ADQUIRIDA')

    def test_caminho_relativo_e_rejeitado_sem_criar_arquivo(self):
        with self.assertRaises(ValueError):
            with instancia.instancia_unica('fixture-relativa'):
                self.fail('Não deve aceitar caminho relativo.')

    def test_windows_lock_e_unlock_usam_primeiro_byte_sem_wait(self):
        modulo = SimpleNamespace(LK_NBLCK=2, LK_UNLCK=0, locking=MagicMock())
        with patch.object(instancia, '_WINDOWS', True), patch.dict(sys.modules, {'msvcrt': modulo}):
            with instancia.instancia_unica(self.raiz):
                self.assertEqual(modulo.locking.call_args.args[1:], (2, 1))
            self.assertEqual(modulo.locking.call_args.args[1:], (0, 1))
        self.assertEqual(modulo.locking.call_count, 2)

    def test_windows_lock_falho_nao_escreve_pid_nem_desbloqueia_instancia_alheia(self):
        modulo = SimpleNamespace(LK_NBLCK=2, LK_UNLCK=0, locking=MagicMock(side_effect=OSError('fixture')))
        with patch.object(instancia, '_WINDOWS', True), patch.dict(sys.modules, {'msvcrt': modulo}), \
                self.assertRaises(instancia.InstanciaAtiva):
            with instancia.instancia_unica(self.raiz):
                self.fail('Não pode entrar com trava indisponível.')
        modulo.locking.assert_called_once()
        self.assertEqual((self.raiz / instancia.NOME_TRAVA).read_bytes(), b'')


if __name__ == '__main__':
    unittest.main()
