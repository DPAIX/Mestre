"""Destino novo em F: trava/implantação reais, serviços e processos simulados."""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import controlar_instancia_preparacao as controle
import implantacao_assistente as implantacao
import instalacao_em_f as politica
import preparacao_autonoma as preparacao
import redirecionar_assistente as redirecionar


class PrimeiraInstalacaoF(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name).resolve() / 'F'
        self.raiz.mkdir()
        self.codigo = self.raiz / 'aplicativo'
        self.dados = self.raiz / 'dados'
        self.dados.mkdir()
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(patch.object(controle, '_WINDOWS', True))
        self.metadados = self.patches.enter_context(patch.object(controle, '_metadados_windows'))
        self.handle = self.patches.enter_context(patch.object(controle, '_ProcessoWindows'))

    def parar(self):
        return controle.parar_assistente(self.codigo, self.dados, autorizado=True)

    def test_destino_inexistente_e_trava_ausente_permitem_primeira_implantacao(self):
        resultado = self.parar()
        self.assertTrue(resultado['livre'])
        self.assertFalse(resultado['pendente'])
        self.assertFalse(resultado['parado'])
        self.assertFalse(self.codigo.exists())
        self.metadados.assert_not_called()
        self.handle.assert_not_called()

    def test_destino_vazio_e_trava_livre_com_pid_antigo_nao_exigem_fontes(self):
        self.codigo.mkdir()
        trava = self.dados / controle.instancia.NOME_TRAVA
        anterior = b'\x009876'
        trava.write_bytes(anterior)
        resultado = self.parar()
        self.assertTrue(resultado['livre'])
        self.assertFalse(resultado['parado'])
        self.assertEqual(trava.read_bytes(), anterior)
        self.assertEqual(list(self.codigo.iterdir()), [])
        self.metadados.assert_not_called()
        self.handle.assert_not_called()

    def test_trava_ativa_sem_fontes_deixa_pendencia_sem_escolher_processo(self):
        for criar_destino in (False, True):
            if criar_destino:
                self.codigo.mkdir()
            with self.subTest(destino_existe=criar_destino), patch.object(
                    controle, '_inspecionar_trava', return_value={'ativa': True, 'pid': 9876}):
                resultado = self.parar()
            self.assertEqual(resultado['estado'], 'destino_sem_fontes')
            self.assertTrue(resultado['pendente'])
            self.assertFalse(resultado['livre'])
            self.assertFalse(resultado['parado'])
        self.metadados.assert_not_called()
        self.handle.assert_not_called()

    def test_destino_redirecionado_continua_recusado_antes_da_trava(self):
        alvo = self.raiz / 'outro_codigo'
        alvo.mkdir()
        try:
            self.codigo.symlink_to(alvo, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('Symlink indisponível nesta sessão.')
        with patch.object(controle, '_inspecionar_trava') as inspecionar:
            with self.assertRaises(ValueError):
                self.parar()
        inspecionar.assert_not_called()
        self.metadados.assert_not_called()
        self.handle.assert_not_called()
        self.assertEqual(list(alvo.iterdir()), [])

    def test_trava_redirecionada_nao_e_tratada_como_destino_novo_livre(self):
        alvo = self.raiz / 'outro_arquivo'
        alvo.write_bytes(b'\x009876')
        trava = self.dados / controle.instancia.NOME_TRAVA
        try:
            trava.symlink_to(alvo)
        except (OSError, NotImplementedError):
            self.skipTest('Symlink indisponível nesta sessão.')
        resultado = self.parar()
        self.assertTrue(resultado['pendente'])
        self.assertFalse(resultado['livre'])
        self.metadados.assert_not_called()
        self.handle.assert_not_called()
        self.assertEqual(alvo.read_bytes(), b'\x009876')

    def test_preparador_implanta_destino_novo_usando_helper_e_trava_reais(self):
        origem = self.raiz / 'pacote'
        origem.mkdir()
        arquivos = {}
        for nome in ('assistente_pc.py', 'nucleo.py', 'caminhos_instalacao.py'):
            bruto = ('# fonte ficticia: ' + nome + '\n').encode()
            (origem / nome).write_bytes(bruto)
            arquivos[nome] = hashlib.sha256(bruto).hexdigest()
        manifesto = origem / 'manifesto_instalacao.json'
        manifesto.write_text(json.dumps({'versao': 1, 'arquivos': arquivos}), encoding='utf-8')
        env = self.raiz / '.env'
        env.write_bytes(b'OUTRA_OPCAO=ficticia_preservada\n')
        dados_ficticios = self.dados / 'rotina_ficticia.json'
        dados_ficticios.write_bytes(b'{"preservar": true}')
        antes_env, antes_dados = env.read_bytes(), dados_ficticios.read_bytes()

        with ExitStack() as mocks:
            mocks.enter_context(patch.dict(os.environ, {'MEUCONTROLEPC_SOMENTE_F': '1'}, clear=True))
            # O disco F é representado somente por uma pasta temporária nos dois SOs.
            mocks.enter_context(patch.object(politica, 'raiz', return_value=self.raiz))
            mocks.enter_context(patch.object(politica, 'validar_caminho', side_effect=lambda p: Path(p)))
            ctx = preparacao.caminhos(origem, self.codigo, env, self.dados)
            motor = preparacao.Preparador(ctx)
            mocks.enter_context(patch.object(motor, '_configuracao', return_value={}))
            for nome in ('_componentes', '_servicos', '_gateway', '_modelo_27b_em_f'):
                mocks.enter_context(patch.object(motor, nome))
            mocks.enter_context(patch.object(motor, '_contas', return_value=False))
            mocks.enter_context(patch('startup_windows.consolidar_inicio'))
            mocks.enter_context(patch.object(redirecionar, 'plano_execucao', return_value={
                'comando': ['python-ficticio', 'assistente-ficticio'],
                'cwd': str(self.codigo), 'ambiente': {},
            }))
            iniciar = mocks.enter_context(patch.object(preparacao.subprocess, 'Popen', return_value=Mock()))
            implantar = mocks.enter_context(patch.object(implantacao, 'implantar', wraps=implantacao.implantar))
            helper = mocks.enter_context(patch.object(controle, 'parar_assistente', wraps=controle.parar_assistente))
            self.assertFalse(self.codigo.exists())
            motor._executar(None)

        helper.assert_called_once_with(self.codigo, self.dados, autorizado=True)
        implantar.assert_called_once()
        iniciar.assert_called_once()
        for nome in arquivos:
            self.assertEqual((self.codigo / nome).read_bytes(), (origem / nome).read_bytes())
        self.assertEqual(env.read_bytes(), antes_env)
        self.assertEqual(dados_ficticios.read_bytes(), antes_dados)
        estado = motor.snapshot()
        self.assertTrue(estado['bot_iniciado'])
        self.assertTrue(estado['finalizado'])
        self.assertEqual(next(i['estado'] for i in estado['itens'] if i['id'] == 'parada'), 'pronto')
        self.assertEqual(next(i['estado'] for i in estado['itens'] if i['id'] == 'fontes'), 'pronto')
        self.assertFalse(estado['pendencias'])
        self.metadados.assert_not_called()
        self.handle.assert_not_called()


if __name__ == '__main__':
    unittest.main()
