"""Preparação e reversão simuladas; nenhum peso, rede ou dado de uso real."""
from contextlib import ExitStack
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

import configurar_ia_local as configurar
import preparar_27b_leve as preparar
from alternativa_27b import DIGEST_MANIFESTO, MODELO_LEVE
from instancia_assistente import InstanciaAtiva, instancia_unica


class Preparar27BLeveTeste(unittest.TestCase):
    def setUp(self):
        self.temporario = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporario.cleanup)
        self.base = Path(self.temporario.name)
        self.env = self.base / '.env'
        self.env.write_text('OLLAMA_HABILITADO=1\nOLLAMA_URL=http://127.0.0.1:11434\n'
            'OLLAMA_PERFIL=cpu\nOLLAMA_MODEL=llama3.2:latest\nOUTRA_OPCAO=preservar\n', encoding='utf-8')
        self.dados = self.base / 'dados'
        self.dados.mkdir()
        (self.dados / 'historico.json').write_text('["fixture intacta"]', encoding='utf-8')
        self.catalogo = [{'nome': MODELO_LEVE, 'nuvem': False, 'digest': DIGEST_MANIFESTO}]
        self.resposta = {'done': True, 'done_reason': 'stop',
                         'message': {'role': 'assistant', 'content': 'OK.'}}
        self.pedidos = []
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.listar = self.patches.enter_context(patch.object(configurar, 'listar_catalogo', return_value=self.catalogo))
        self.mostrar = self.patches.enter_context(patch.object(configurar, 'mostrar_modelo',
            return_value={'nuvem': False, 'familia': 'qwen35', 'quantizacao': 'IQ3_XXS'}))
        self.http = self.patches.enter_context(patch.object(preparar, '_consultar', side_effect=self.consultar))
        self.download = self.patches.enter_context(patch.object(preparar, '_baixar'))

    def consultar(self, url, rota, dados=None, **opcoes):
        self.pedidos.append((url, rota, dados, opcoes))
        return {'models': []} if rota == '/api/ps' else self.resposta

    def executar(self, **extras):
        return preparar.preparar(self.env, self.dados, autorizado=True, **extras)

    def test_autorizacao_e_caminhos_obrigatorios_sem_efeitos(self):
        for autorizado in (False, None, 1, 'sim'):
            with self.subTest(autorizado=autorizado), self.assertRaises(preparar.FalhaPreparacao):
                preparar.preparar(self.env, self.dados, autorizado=autorizado)
        with self.assertRaises(preparar.FalhaPreparacao):
            preparar.preparar(Path('relativo'), self.dados, autorizado=True)
        with self.assertRaises(preparar.FalhaPreparacao):
            preparar.preparar(self.env, self.base / 'ausente', autorizado=True)
        self.assertFalse((self.base / 'ausente').exists())
        self.http.assert_not_called()
        self.download.assert_not_called()

    def test_assistente_ativo_bloqueia_antes_da_rede(self):
        with instancia_unica(self.dados), self.assertRaisesRegex(preparar.FalhaPreparacao, 'Encerre'):
            self.executar()
        self.http.assert_not_called()
        self.download.assert_not_called()

    def test_consulta_unica_antes_de_ativar_com_opcoes_reduzidas(self):
        original = self.env.read_text(encoding='utf-8')
        gravar = configurar._atualizar_opcoes_env
        def verificar_antes(alteracoes, caminho):
            self.assertEqual(self.env.read_text(encoding='utf-8'), original)
            self.assertEqual(len([p for p in self.pedidos if p[1] == '/api/chat']), 1)
            self.assertTrue((self.base / 'preparacao' / '27b_leve.json').is_file())
            return gravar(alteracoes, caminho)
        with patch.object(configurar, '_atualizar_opcoes_env', side_effect=verificar_antes) as escrita:
            resultado = self.executar()
        self.assertEqual(resultado['estado'], 'configurado')
        escrita.assert_called_once_with(preparar.APLICADAS, self.env)
        self.download.assert_not_called()
        envio = [p for p in self.pedidos if p[1] == '/api/chat'][0]
        self.assertEqual(envio[3], {'timeout': 90})
        self.assertEqual(envio[2], {'model': MODELO_LEVE, 'stream': False, 'think': False,
            'keep_alive': 0, 'options': {'num_ctx': 1024, 'num_predict': 64},
            'messages': [{'role': 'user', 'content': 'Responda somente OK.'}]})
        self.assertEqual((self.dados / 'historico.json').read_text(), '["fixture intacta"]')
        atual = self.env.read_text()
        self.assertIn('OUTRA_OPCAO=preservar\n', atual)
        self.assertIn('OLLAMA_MODEL=llama3.2:latest\n', atual)
        self.assertIn('OLLAMA_PERFIL=equilibrado\n', atual)
        self.assertIn('OLLAMA_27B_LEVE=1\n', atual)

    def test_backup_contem_so_opcoes_publicas_e_preserva_primeira_reversao(self):
        self.executar()
        backup = self.base / 'preparacao' / '27b_leve.json'
        primeiro = backup.read_bytes()
        valor = json.loads(primeiro)
        self.assertEqual(set(valor['anteriores']), set(preparar.APLICADAS))
        self.assertEqual(valor['anteriores'], {'OLLAMA_PERFIL': 'cpu', 'OLLAMA_27B_LEVE': '0'})
        self.assertNotIn('OUTRA_OPCAO', primeiro.decode())
        self.executar()
        self.assertEqual(backup.read_bytes(), primeiro)

    def test_download_apenas_ausente_e_catalogo_reconferido(self):
        self.listar.side_effect = [[], self.catalogo, self.catalogo]
        self.executar()
        self.download.assert_called_once_with(configurar.URL_PADRAO)
        self.assertEqual(self.listar.call_count, 3)

    def test_digest_alterado_ou_modelo_remoto_nao_gera_nem_ativa(self):
        for registro in ({'nome': MODELO_LEVE, 'nuvem': False, 'digest': 'f' * 64},
                         {'nome': MODELO_LEVE, 'nuvem': True, 'digest': DIGEST_MANIFESTO}):
            with self.subTest(registro=registro):
                self.listar.return_value = [registro]
                self.pedidos.clear()
                with self.assertRaises(preparar.FalhaPreparacao):
                    self.executar()
                self.assertFalse(any(p[1] == '/api/chat' for p in self.pedidos))
                self.assertNotIn('OLLAMA_27B_LEVE', self.env.read_text())
                self.download.assert_not_called()

    def test_metadados_divergentes_nao_geram(self):
        for detalhe in ({'nuvem': True, 'familia': 'qwen35', 'quantizacao': 'IQ3_XXS'},
                        {'nuvem': False, 'familia': 'outra', 'quantizacao': 'IQ3_XXS'},
                        {'nuvem': False, 'familia': 'qwen35', 'quantizacao': 'Q4_K_M'}):
            with self.subTest(detalhe=detalhe):
                self.mostrar.return_value = detalhe
                self.pedidos.clear()
                with self.assertRaises(preparar.FalhaPreparacao):
                    self.executar()
                self.assertFalse(any(p[1] == '/api/chat' for p in self.pedidos))

    def test_troca_de_digest_durante_inferencia_nao_ativa(self):
        def alterar_tag(url, rota, dados=None, **opcoes):
            if rota == '/api/chat':
                self.listar.return_value = [dict(self.catalogo[0], digest='f' * 64)]
                return self.resposta
            return {'models': []}
        self.http.side_effect = alterar_tag
        with self.assertRaises(preparar.FalhaPreparacao):
            self.executar()
        self.assertEqual(self.listar.call_count, 2)
        self.assertEqual(sum(p.args[1] == '/api/chat' for p in self.http.call_args_list), 1)
        self.assertNotIn('OLLAMA_27B_LEVE', self.env.read_text())
        self.assertFalse((self.base / 'preparacao' / '27b_leve.json').exists())

    def test_prazos_compativeis_com_producao_sem_alargar_limites(self):
        from multi_ia import Roteador
        casos = [({}, 90), ({'OLLAMA_TIMEOUT': '120'}, 90),
            ({'OLLAMA_TIMEOUT': '12'}, 12),
            ({'OLLAMA_EQUIPE_TIMEOUT_MODELO': '15'}, 15),
            ({'OLLAMA_EQUIPE_TIMEOUT': '10'}, 10),
            ({'OLLAMA_EQUIPE_ORCAMENTO': 'legado'}, 30),
            ({'OLLAMA_EQUIPE_ORCAMENTO': 'legado', 'OLLAMA_TIMEOUT': '20'}, 20),
            ({'OLLAMA_TIMEOUT': 'nan', 'OLLAMA_EQUIPE_TIMEOUT_MODELO': 'invalido'}, 90),
            ({'OLLAMA_TIMEOUT': '0'}, 5)]
        for valores, esperado in casos:
            with self.subTest(valores=valores):
                self.assertEqual(preparar._prazo_teste(valores), esperado)
                # O método nativo não usa self nem lê estado persistido.
                with patch.dict(os.environ, valores, clear=True):
                    limites = Roteador.limites_equipe(None, 4)
                self.assertLessEqual(esperado, limites['por_modelo'])
                self.assertLessEqual(esperado, limites['rodada'])
        with self.assertRaises(preparar.FalhaPreparacao):
            preparar._prazo_teste({'OLLAMA_EQUIPE_ORCAMENTO': 'invalido'})

    def test_prazo_menor_configurado_chega_a_consulta_real_simulada(self):
        self.env.write_text(self.env.read_text() + 'OLLAMA_TIMEOUT=17\n', encoding='utf-8')
        self.executar()
        envio = next(p for p in self.pedidos if p[1] == '/api/chat')
        self.assertEqual(envio[3], {'timeout': 17})

    def test_modelos_ativos_bloqueiam_antes_e_depois_do_download(self):
        for respostas in ([{'models': [{}]}], [{'models': []}, {'models': [{}]}]):
            with self.subTest(respostas=respostas):
                self.http.side_effect = respostas
                with self.assertRaisesRegex(preparar.FalhaPreparacao, 'carregados'):
                    self.executar()
                self.assertNotIn('OLLAMA_27B_LEVE', self.env.read_text())

    def test_resposta_incompleta_truncada_invalida_ou_acao_nao_ativa(self):
        for resposta in ({'message': {'role': 'assistant', 'content': 'OK'}},
                        {'done': False, 'message': {'role': 'assistant', 'content': 'OK'}},
                        {'done': True, 'done_reason': 'length', 'message': {'role': 'assistant', 'content': 'OK'}},
                        {'done': True, 'message': {'role': 'assistant', 'content': 'não'}},
                        {'done': True, 'message': {'role': 'assistant', 'content': 'OK', 'tool_calls': [{}]}}):
            with self.subTest(resposta=resposta):
                self.resposta = resposta
                self.pedidos.clear()
                with self.assertRaises(preparar.FalhaPreparacao):
                    self.executar()
                self.assertEqual(len([p for p in self.pedidos if p[1] == '/api/chat']), 1)
                self.assertNotIn('OLLAMA_27B_LEVE', self.env.read_text())
                self.assertFalse((self.base / 'preparacao' / '27b_leve.json').exists())

    def test_timeout_de_teste_nao_repete_nem_altera(self):
        def timeout(url, rota, dados=None, **opcoes):
            if rota == '/api/chat':
                raise preparar.FalhaPreparacao('Consulta não concluiu.')
            return {'models': []}
        self.http.side_effect = timeout
        with self.assertRaises(preparar.FalhaPreparacao):
            self.executar()
        self.assertEqual(sum(p.args[1] == '/api/chat' for p in self.http.call_args_list), 1)
        self.assertNotIn('OLLAMA_27B_LEVE', self.env.read_text())

    def test_falha_no_backup_impede_configurar(self):
        with patch.object(preparar, '_salvar_json', side_effect=PermissionError), \
                patch.object(configurar, '_atualizar_opcoes_env') as escrita, \
                self.assertRaises(preparar.FalhaPreparacao):
            self.executar()
        escrita.assert_not_called()

    def test_falha_atomica_na_escrita_preserva_config_e_backup(self):
        original = self.env.read_bytes()
        substituir = os.replace
        def negar_config(origem, destino):
            if Path(destino) == self.env:
                raise PermissionError
            return substituir(origem, destino)
        with patch.object(configurar.os, 'replace', side_effect=negar_config), self.assertRaises(preparar.FalhaPreparacao):
            self.executar()
        self.assertEqual(self.env.read_bytes(), original)
        self.assertTrue((self.base / 'preparacao' / '27b_leve.json').is_file())

    def test_mudanca_durante_consulta_preservada(self):
        def alterar(url, rota, dados=None, **opcoes):
            if rota == '/api/chat':
                self.env.write_text(self.env.read_text() + 'OLLAMA_27B_LEVE=0\n', encoding='utf-8')
                return self.resposta
            return {'models': []}
        self.http.side_effect = alterar
        with self.assertRaisesRegex(preparar.FalhaPreparacao, 'mudou'):
            self.executar()
        self.assertNotIn('OLLAMA_PERFIL=equilibrado', self.env.read_text())
        self.assertFalse((self.base / 'preparacao' / '27b_leve.json').exists())

    def test_restauracao_usa_cas_e_nao_consulta_modelos(self):
        self.executar()
        self.http.reset_mock()
        self.listar.reset_mock()
        resultado = self.executar(restaurar=True)
        self.assertEqual(resultado['estado'], 'restaurado')
        self.assertEqual(configurar.valores_env(self.env)['OLLAMA_PERFIL'], 'cpu')
        self.assertEqual(configurar.valores_env(self.env)['OLLAMA_27B_LEVE'], '0')
        self.assertEqual(self.executar(restaurar=True)['estado'], 'ja_restaurado')
        self.http.assert_not_called()
        self.listar.assert_not_called()

    def test_restauracao_preserva_alteracoes_posteriores(self):
        self.executar()
        configurar._atualizar_opcoes_env({'OLLAMA_PERFIL': 'padrao'}, self.env)
        atual = self.env.read_bytes()
        with self.assertRaisesRegex(preparar.FalhaPreparacao, 'posteriores'):
            self.executar(restaurar=True)
        self.assertEqual(self.env.read_bytes(), atual)

    def test_backup_invalido_nao_altera(self):
        backup = self.base / 'preparacao' / '27b_leve.json'
        backup.parent.mkdir()
        backup.write_text('{"fixture":true}')
        with self.assertRaises(preparar.FalhaPreparacao):
            self.executar(restaurar=True)
        self.assertNotIn('OLLAMA_27B_LEVE', self.env.read_text())

    def test_downloader_nao_recebe_segredos_nem_shell_e_tem_prazo(self):
        # Chamar implementação original guardada na classe evita rede ou CLI real.
        with patch.dict(os.environ, {'PATH': 'fixture', 'OPENAI_API_KEY': 'segredo-ficticio',
                'TELEGRAM_TOKEN': 'ficticio', 'OLLAMA_API_KEY': 'ficticio'}, clear=True), \
                patch.object(preparar.shutil, 'which', return_value='/fixture/ollama'), \
                patch.object(preparar.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as executar:
            BAIXAR_REAL(configurar.URL_PADRAO)
        args, kwargs = executar.call_args
        self.assertEqual(args[0], ['/fixture/ollama', 'pull', MODELO_LEVE])
        self.assertFalse(kwargs['shell'])
        self.assertEqual(kwargs['timeout'], 1800)
        self.assertEqual(kwargs['env'], {'PATH': 'fixture', 'OLLAMA_HOST': configurar.URL_PADRAO})

    def test_download_expirado_nao_repete(self):
        with patch.object(preparar.shutil, 'which', return_value='/fixture/ollama'), \
                patch.object(preparar.subprocess, 'run', side_effect=subprocess.TimeoutExpired('fixture', 1800)) as executar, \
                self.assertRaisesRegex(preparar.FalhaPreparacao, '30 minutos'):
            BAIXAR_REAL(configurar.URL_PADRAO)
        executar.assert_called_once()

    def test_main_fora_do_windows_nao_inicia_operacao(self):
        with patch.object(preparar.sys, 'platform', 'linux'), patch.object(preparar, 'preparar') as operacao:
            self.assertEqual(preparar.main(['--baixar-e-testar']), 2)
        operacao.assert_not_called()

    def test_cliente_loopback_sem_proxy_redirecionamento_ou_corpo_no_erro(self):
        erro = urllib.error.HTTPError(configurar.URL_PADRAO + '/api/chat', 500,
            'fixture privada', {}, io.BytesIO(b'conteudo privado ficticio'))
        with patch.object(preparar.urllib.request, 'build_opener') as criar:
            criar.return_value.open.side_effect = erro
            with self.assertRaisesRegex(preparar.FalhaPreparacao, r'HTTP 500') as capturado:
                CONSULTAR_REAL(configurar.URL_PADRAO, '/api/chat', {'fixture': 'publica'}, timeout=7)
        self.assertNotIn('privad', str(capturado.exception))
        self.assertTrue(erro.closed)
        handlers = criar.call_args.args
        self.assertEqual(handlers[0].proxies, {})
        self.assertIsInstance(handlers[1], configurar.SemRedirecionamento)
        pedido = criar.return_value.open.call_args.args[0]
        self.assertEqual(pedido.full_url, configurar.URL_PADRAO + '/api/chat')
        self.assertEqual(criar.return_value.open.call_args.kwargs['timeout'], 7)

    def test_cliente_rejeita_url_remota_antes_de_abrir(self):
        with patch.object(preparar.urllib.request, 'build_opener') as criar, self.assertRaises(ValueError):
            CONSULTAR_REAL('https://example.invalid', '/api/ps')
        criar.assert_not_called()

    def test_ollama_desabilitado_nao_consulta(self):
        configurar._atualizar_opcoes_env({'OLLAMA_HABILITADO': '0'}, self.env)
        with self.assertRaisesRegex(preparar.FalhaPreparacao, 'Habilite'):
            self.executar()
        self.http.assert_not_called()


BAIXAR_REAL = preparar._baixar
CONSULTAR_REAL = preparar._consultar


if __name__ == '__main__':
    unittest.main()
