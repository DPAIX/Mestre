"""Perfil CPU com HTTP simulado e configuração/dados exclusivamente temporários."""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import colaboracao_chats as central
import configurar_ia_local as configurar
import multi_ia as ia
import nucleo
import redirecionar_assistente as redirecionar
import servicos_chat as servicos


class PerfilCpuRoteador(unittest.TestCase):
    def setUp(self):
        self.persistido = {}
        ambiente = patch.dict(os.environ, {
            'OLLAMA_HABILITADO': '1', 'OLLAMA_MODEL': 'llama3.2:latest',
            'OLLAMA_URL': 'http://127.0.0.1:11434',
            'OPENAI_API_KEY': 'fixture-provedor-pago',
        }, clear=True)
        ambiente.start(); self.addCleanup(ambiente.stop)
        for alvo, kwargs in (
                ('ler_json', {'side_effect': lambda *a, **kw: copy.deepcopy(self.persistido)}),
                ('gravar_json', {'side_effect': self.gravar}), ('registrar', {})):
            p = patch.object(ia, alvo, **kwargs)
            p.start(); self.addCleanup(p.stop)
        p = patch.object(configurar, 'listar_catalogo', return_value=[
            {'nome': 'llama3.2:latest', 'nuvem': False},
            {'nome': 'mistral:latest', 'nuvem': False}])
        self.consultar = p.start(); self.addCleanup(p.stop)
        self.roteador = ia.Roteador()

    def gravar(self, nome, valor):
        self.assertEqual(nome, 'estado_ia.json')
        self.persistido = copy.deepcopy(valor)

    def gerar(self, **kwargs):
        with patch.object(ia, 'postar', return_value={'message': {'content': 'Resposta curta'}}) as enviar:
            resposta = self.roteador.ollama('Mensagem atual', **kwargs)
        self.assertEqual(resposta, 'Resposta curta')
        enviar.assert_called_once()
        self.assertEqual(enviar.call_args.args[:2], ('http://127.0.0.1:11434/api/chat', ''))
        return enviar.call_args

    def test_cpu_envia_opcoes_compactas_e_preserva_mensagem_e_historico(self):
        os.environ['OLLAMA_PERFIL'] = 'CPU'
        historico = [{'role': 'user', 'content': 'Objetivo anterior'},
                     {'role': 'assistant', 'content': 'Plano anterior'}]
        antes = copy.deepcopy(historico)
        chamada = self.gerar(historico=historico)
        payload = chamada.args[2]
        self.assertEqual(payload['model'], 'llama3.2:latest')
        self.assertIs(payload['stream'], False)
        self.assertEqual(payload['keep_alive'], 0)
        self.assertEqual(payload['options'], {'num_gpu': 0, 'num_ctx': 1024, 'num_predict': 128})
        self.assertEqual(payload['messages'][0], {'role': 'system', 'content': ia.SISTEMA})
        self.assertEqual(payload['messages'][1:], historico + [{'role': 'user', 'content': 'Mensagem atual'}])
        self.assertEqual(historico, antes)
        self.assertEqual(chamada.kwargs['timeout'], 90)
        self.consultar.assert_called_once_with('http://127.0.0.1:11434')

    def test_padrao_sem_perfil_ou_explicito_preserva_payload_anterior(self):
        for perfil in (None, 'padrao'):
            with self.subTest(perfil=perfil):
                if perfil is not None:
                    os.environ['OLLAMA_PERFIL'] = perfil
                chamada = self.gerar()
                self.assertEqual(set(chamada.args[2]), {'model', 'stream', 'messages'})
        self.consultar.assert_not_called()

    def test_cpu_aplica_tambem_ao_modelo_explicito_da_equipe(self):
        os.environ['OLLAMA_PERFIL'] = 'cpu'
        chamada = self.gerar(modelo='mistral:latest')
        self.assertEqual(chamada.args[2]['model'], 'mistral:latest')
        self.assertEqual(chamada.args[2]['options']['num_gpu'], 0)
        self.assertEqual(os.environ['OLLAMA_MODEL'], 'llama3.2:latest')

    def test_perfil_invalido_ou_cpu_cloud_falham_antes_do_http(self):
        for perfil, modelo in (('inexistente', 'llama3.2:latest'),
                               ('cpu', 'gemma4:31b-cloud')):
            with self.subTest(perfil=perfil, modelo=modelo), \
                    patch.dict(os.environ, {'OLLAMA_PERFIL': perfil}), \
                    patch.object(ia, 'postar') as enviar:
                with self.assertRaises(ia.FalhaAPI) as erro:
                    self.roteador.ollama('Mensagem', modelo=modelo)
                self.assertEqual(erro.exception.categoria, 'configuracao')
                enviar.assert_not_called()

    def test_cpu_rejeita_alias_cloud_ou_catalogo_ausente_sem_geracao(self):
        os.environ['OLLAMA_PERFIL'] = 'cpu'
        for catalogo in ([], [{'nome': 'llama3.2:latest', 'nuvem': True}]):
            with self.subTest(catalogo=catalogo), \
                    patch.object(configurar, 'listar_catalogo', return_value=catalogo), \
                    patch.object(ia, 'postar') as enviar:
                with self.assertRaises(ia.FalhaAPI) as erro:
                    self.roteador.ollama('Mensagem')
                self.assertEqual(erro.exception.categoria, 'configuracao')
                enviar.assert_not_called()
        with patch.object(configurar, 'listar_catalogo', side_effect=configurar.FalhaConfiguracao('Indisponível')), \
                patch.object(ia, 'postar') as enviar:
            with self.assertRaises(ia.FalhaAPI):
                self.roteador.ollama('Mensagem')
            enviar.assert_not_called()

    def test_assinatura_padrao_continua_compativel_com_estado_legado(self):
        valores = [os.environ['OLLAMA_URL'], os.environ['OLLAMA_MODEL'], True]
        anterior = hashlib.sha256(json.dumps(valores, ensure_ascii=True).encode('utf-8')).hexdigest()
        self.assertEqual(ia.assinatura_configuracao_ollama(), anterior)
        os.environ['OLLAMA_PERFIL'] = 'padrao'
        self.assertEqual(ia.assinatura_configuracao_ollama(), anterior)
        os.environ['OLLAMA_PERFIL'] = 'cpu'
        self.assertNotEqual(ia.assinatura_configuracao_ollama(), anterior)

    def test_trocar_perfil_libera_so_pausa_ollama_sem_consulta(self):
        self.roteador.registrar_falha(ia.FalhaAPI('Ollama', 0, 'Timeout fictício', 'rede'))
        self.roteador.registrar_falha(ia.FalhaAPI('OpenAI', 401, 'Credencial fictícia', 'autenticacao'))
        antes = copy.deepcopy(self.roteador.estado_local()['OpenAI'])
        os.environ['OLLAMA_PERFIL'] = 'cpu'
        with patch.object(ia, 'postar') as enviar:
            self.assertTrue(self.roteador.atualizar_configuracao_ollama())
        enviar.assert_not_called()
        self.assertNotIn('Ollama', self.roteador.bloqueados)
        self.assertEqual(self.roteador.estado_local()['OpenAI'], antes)
        self.assertNotIn('Ollama', self.persistido)


class PerfilCpuConfiguracao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.codigo = self.raiz / 'codigo'
        self.codigo.mkdir()
        self.externo = self.raiz / 'instalacao externa' / '.env'
        self.externo.parent.mkdir()
        self.original = ('\ufeff# preservar comentário\r\nTELEGRAM_TOKEN=fixture-nao-exibir\r\n'
                         'OUTRA_CONFIG=fixture-preservada\r\nOLLAMA_MODEL=mistral:latest\r\n'
                         'OLLAMA_PERFIL=padrao\r\nOLLAMA_PERFIL=padrao\r\n').encode('utf-8')
        self.externo.write_bytes(self.original)
        self.local = self.codigo / '.env'
        self.local.write_bytes(b'FIXTURE_LOCAL=inalterada\n')
        self.catalogo = [{'nome': 'llama3.2:latest', 'nuvem': False},
                         {'nome': 'mistral:latest', 'nuvem': False}]
        for modulo in (configurar, nucleo):
            p = patch.object(modulo, 'BASE', self.codigo)
            p.start(); self.addCleanup(p.stop)
        p = patch.object(nucleo, 'DADOS', self.raiz / 'dados ficticios')
        p.start(); self.addCleanup(p.stop)
        p = patch.dict(os.environ, {'MEUCONTROLEPC_ENV': str(self.externo),
                                   'OLLAMA_URL': configurar.URL_PADRAO}, clear=True)
        p.start(); self.addCleanup(p.stop)
        p = patch.object(configurar, 'listar_catalogo', side_effect=lambda *a: copy.deepcopy(self.catalogo))
        self.consultar = p.start(); self.addCleanup(p.stop)
        p = patch.object(configurar.subprocess, 'run', side_effect=AssertionError('Sem download/processo'))
        p.start(); self.addCleanup(p.stop)
        p = patch.object(ia, 'postar', side_effect=AssertionError('Sem inferência'))
        p.start(); self.addCleanup(p.stop)

    def test_cpu_grava_env_externo_preservando_segredos_bom_crlf_e_codigo(self):
        antes = self.local.read_bytes()
        self.assertEqual(configurar.configurar_perfil('cpu'), 'llama3.2:latest')
        self.consultar.assert_called_once_with(configurar.URL_PADRAO)
        texto = self.externo.read_bytes()
        self.assertTrue(texto.startswith(b'\xef\xbb\xbf'))
        self.assertEqual(texto.count(b'OLLAMA_PERFIL='), 1)
        self.assertIn(b'TELEGRAM_TOKEN=fixture-nao-exibir\r\n', texto)
        self.assertIn(b'OUTRA_CONFIG=fixture-preservada\r\n', texto)
        self.assertNotIn(b'\n', texto.replace(b'\r\n', b''))
        self.assertEqual(configurar.valores_env()['OLLAMA_PERFIL'], 'cpu')
        self.assertEqual(configurar.valores_env()['OLLAMA_MODEL'], 'llama3.2:latest')
        self.assertEqual(self.local.read_bytes(), antes)
        self.assertEqual(list(self.externo.parent.glob('*.tmp')), [])

    def test_padrao_reverte_opcoes_mantendo_modelo_configurado(self):
        configurar.configurar_perfil('cpu')
        configurar.configurar_perfil('padrao')
        self.assertEqual(configurar.valores_env()['OLLAMA_PERFIL'], 'padrao')
        self.assertEqual(configurar.valores_env()['OLLAMA_MODEL'], 'llama3.2:latest')

    def test_alterar_modelo_sem_perfil_preserva_cpu(self):
        configurar.configurar_perfil('cpu')
        configurar.atualizar_env('mistral:latest')
        self.assertEqual(configurar.valores_env()['OLLAMA_PERFIL'], 'cpu')
        self.assertEqual(configurar.valores_env()['OLLAMA_MODEL'], 'mistral:latest')

    def test_perfil_invalido_nao_consulta_catalogo_ou_grava(self):
        with self.assertRaises(ValueError):
            configurar.configurar_perfil('gpu-turbo')
        self.consultar.assert_not_called()
        self.assertEqual(self.externo.read_bytes(), self.original)

    def test_cpu_modelo_ausente_ou_cloud_nao_grava_nem_baixa(self):
        for catalogo in ([], [{'nome': 'llama3.2:latest', 'nuvem': True}],
                          [{'nome': 'gemma4:31b-cloud', 'nuvem': True}]):
            with self.subTest(catalogo=catalogo):
                self.catalogo = catalogo
                with self.assertRaises(configurar.FalhaConfiguracao):
                    configurar.configurar_perfil('cpu')
                self.assertEqual(self.externo.read_bytes(), self.original)

    def test_falha_catalogo_preserva_env(self):
        self.consultar.side_effect = configurar.FalhaConfiguracao('Serviço fictício indisponível')
        with self.assertRaises(configurar.FalhaConfiguracao):
            configurar.configurar_perfil('cpu')
        self.assertEqual(self.externo.read_bytes(), self.original)

    def test_falha_substituicao_atomica_preserva_env_e_remove_temporario(self):
        with patch.object(configurar.os, 'replace', side_effect=OSError('Falha fictícia')):
            with self.assertRaises(OSError):
                configurar.configurar_perfil('cpu')
        self.assertEqual(self.externo.read_bytes(), self.original)
        self.assertEqual(list(self.externo.parent.glob('*.tmp')), [])

    def test_cli_cpu_e_padrao_persistem_sem_geracao_e_sem_vazar_fixture(self):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            self.assertEqual(configurar.main(['--perfil-cpu']), 0)
            self.assertEqual(configurar.valores_env()['OLLAMA_PERFIL'], 'cpu')
            self.assertEqual(configurar.main(['--perfil-padrao']), 0)
        self.assertEqual(configurar.valores_env()['OLLAMA_PERFIL'], 'padrao')
        self.assertNotIn('fixture-nao-exibir', saida.getvalue())
        self.assertIn('Nenhuma geração ou download', saida.getvalue())

    def test_redirecionador_aceita_um_perfil_e_rejeita_operacoes_combinadas(self):
        for opcao in ('--perfil-cpu', '--perfil-padrao'):
            args = [opcao, '--url', configurar.URL_PADRAO]
            self.assertEqual(redirecionar._argumentos_permitidos('ollama', args), args)
        for args in (['--perfil-cpu', '--perfil-padrao'], ['--perfil-cpu', '--modelo', 'llama3.2:latest']):
            with self.subTest(args=args), self.assertRaises(redirecionar.FalhaRedirecionamento):
                redirecionar._argumentos_permitidos('ollama', args)

    def preparar_chat(self):
        self.contexto = 'telegram:1:10:4'
        self.chat = central.criar_chat(self.contexto, 'Conversa fictícia', 'Ollama')
        central.configurar_chat(self.contexto, self.chat['id'], equipe_modelos=['mistral:latest'],
                               equipe_paralela=True, modo_conversa=False)
        central.registrar_troca(self.contexto, 'Plano anterior fictício', 'Resposta anterior fictícia', 'Ollama')
        self.roteador = MagicMock()

    def acao(self, **campos):
        obj = {'perfil': 'cpu', 'confirmacao': 'CONFIGURAR CPU', 'chat_id': self.chat['id'], **campos}
        return servicos.executar_acao('ollama_perfil', obj, self.contexto, self.roteador)

    def test_servico_aplica_ao_vivo_preserva_historico_e_desativa_so_equipe_atual(self):
        self.preparar_chat()
        anterior = central.historico_chat(self.contexto)
        outro_contexto = 'telegram:2:20:5'
        outro_chat = central.criar_chat(outro_contexto, 'Outro contexto fictício', 'Ollama')
        central.configurar_chat(outro_contexto, outro_chat['id'], equipe_modelos=['mistral:latest'],
                               equipe_paralela=True)
        outro_antes = central.obter_chat_ativo(outro_contexto)
        with patch.object(nucleo, 'registrar'):
            mensagem = self.acao()
        atual = central.obter_chat_ativo(self.contexto)
        self.assertEqual(atual['modelo_ollama'], 'llama3.2:latest')
        self.assertIs(atual['equipe_paralela'], False)
        self.assertEqual(atual['equipe_modelos'], [])
        self.assertIs(atual['modo_conversa'], True)
        self.assertEqual(central.historico_chat(self.contexto), anterior)
        self.assertEqual(central.obter_chat_ativo(outro_contexto), outro_antes)
        self.assertEqual(os.environ['OLLAMA_PERFIL'], 'cpu')
        self.assertEqual(os.environ['OLLAMA_MODEL'], 'llama3.2:latest')
        self.assertEqual(configurar.valores_env()['OLLAMA_PERFIL'], 'cpu')
        self.roteador.atualizar_configuracao_ollama.assert_called_once_with()
        self.roteador.responder.assert_not_called()
        self.assertIn('globalmente', mensagem)
        self.assertIn('histórico preservado', mensagem)

    def test_servico_exige_confirmacao_antes_de_consultar_ou_alterar(self):
        self.preparar_chat()
        antes = central.obter_chat_ativo(self.contexto)
        for confirmacao in (None, '', 'CONFIGURAR PADRAO', 'sim'):
            with self.subTest(confirmacao=confirmacao), self.assertRaises(ValueError):
                self.acao(confirmacao=confirmacao)
        self.consultar.assert_not_called()
        self.assertEqual(self.externo.read_bytes(), self.original)
        self.assertEqual(central.obter_chat_ativo(self.contexto), antes)
        self.roteador.atualizar_configuracao_ollama.assert_not_called()

    def test_servico_recusa_chat_trocado_antes_de_gravar_configuracao(self):
        self.preparar_chat()
        central.criar_chat(self.contexto, 'Segunda conversa fictícia', 'Ollama')
        with self.assertRaises(ValueError):
            self.acao()
        self.consultar.assert_not_called()
        self.assertEqual(self.externo.read_bytes(), self.original)

    def test_servico_falha_env_preserva_ambiente_e_chat(self):
        self.preparar_chat()
        chat_antes = central.obter_chat_ativo(self.contexto)
        ambiente_antes = os.environ.copy()
        with patch.object(configurar.os, 'replace', side_effect=OSError('Falha fictícia')):
            with self.assertRaises(OSError):
                self.acao()
        self.assertEqual(os.environ.copy(), ambiente_antes)
        self.assertEqual(central.obter_chat_ativo(self.contexto), chat_antes)
        self.assertEqual(self.externo.read_bytes(), self.original)
        self.roteador.atualizar_configuracao_ollama.assert_not_called()

    def test_configuracoes_simultaneas_preservam_ordem_de_disco_e_ambiente(self):
        self.preparar_chat()
        primeira_entrou = threading.Event()
        liberar_primeira = threading.Event()
        segunda_solicitada = threading.Event()
        segunda_entrou = threading.Event()
        observacoes = []
        erros = []
        configurar_real = configurar.configurar_perfil

        def configurar_controlado(perfil, *args, **kwargs):
            if perfil == 'cpu':
                primeira_entrou.set()
                if not liberar_primeira.wait(2):
                    raise AssertionError('Prazo da barreira CPU expirou.')
            else:
                segunda_entrou.set()
                observacoes.append((os.environ.get('OLLAMA_PERFIL'),
                                    configurar.valores_env()['OLLAMA_PERFIL']))
            return configurar_real(perfil, *args, **kwargs)

        def executar(perfil):
            if perfil == 'padrao':
                segunda_solicitada.set()
            try:
                self.acao(perfil=perfil, confirmacao='CONFIGURAR ' + perfil.upper())
            except Exception as erro:
                erros.append(erro)

        primeira = threading.Thread(target=executar, args=('cpu',), daemon=True)
        segunda = threading.Thread(target=executar, args=('padrao',), daemon=True)
        with patch.object(configurar, 'configurar_perfil', side_effect=configurar_controlado), \
                patch.object(nucleo, 'registrar'):
            try:
                primeira.start()
                self.assertTrue(primeira_entrou.wait(1), 'Primeira configuração não iniciou.')
                segunda.start()
                self.assertTrue(segunda_solicitada.wait(1), 'Segunda configuração não foi solicitada.')
                self.assertFalse(segunda_entrou.wait(0.1),
                                 'Segunda configuração entrou antes de concluir a primeira.')
            finally:
                liberar_primeira.set()
                primeira.join(timeout=2)
                if segunda.ident is not None:
                    segunda.join(timeout=2)
        self.assertFalse(primeira.is_alive())
        self.assertFalse(segunda.is_alive())
        self.assertEqual(erros, [])
        self.assertEqual(observacoes, [('cpu', 'cpu')])
        self.assertEqual(os.environ['OLLAMA_PERFIL'], 'padrao')
        self.assertEqual(configurar.valores_env()['OLLAMA_PERFIL'], 'padrao')
        self.assertEqual(os.environ['OLLAMA_MODEL'], configurar.valores_env()['OLLAMA_MODEL'])
        self.assertEqual(central.obter_chat_ativo(self.contexto)['modelo_ollama'],
                         configurar.valores_env()['OLLAMA_MODEL'])


if __name__ == '__main__':
    unittest.main()
