"""Ações HTTP recuperáveis em loopback, sem rede externa ou ação real no PC."""
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import assistente_pc as app
import colaboracao_chats as central
import nucleo
from idempotencia_painel import ControleAcoes, FalhaControle


class HandlerComPerda(app.PainelHandler):
    def _headers(self, codigo, tipo):
        if self.path == '/api/acao' and getattr(self.server, 'perder_resposta', False):
            self.server.perder_resposta = False
            raise BrokenPipeError('Conexão encerrada antes da resposta')
        return super()._headers(codigo, tipo)


class IdempotenciaHTTP(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        dados = patch.object(nucleo, 'DADOS', Path(tmp.name)); dados.start(); self.addCleanup(dados.stop)
        nucleo.gravar_json('gestao_vida.json', {'rotina': [], 'financeiro': {'saldo': 0}, 'habitos_saude': {}})
        self.controle = ControleAcoes()
        controle = patch.object(app, 'CONTROLE_PAINEL', self.controle); controle.start(); self.addCleanup(controle.stop)
        self.servidor = app.ThreadingHTTPServer(('127.0.0.1', 0), HandlerComPerda)
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        self.addCleanup(self.servidor.server_close); self.addCleanup(self.servidor.shutdown)
        self.porta = self.servidor.server_port
        self.origem = f'http://127.0.0.1:{self.porta}'

    def requisicao(self, obj=None, *, caminho='/api/acao', chave=None, versao=0, headers=None):
        cab = {'X-Painel-Token': app.TOKEN_PAINEL, 'Origin': self.origem, 'Content-Type': 'application/json'}
        if chave is not None:
            cab.update({'X-Idempotency-Key': chave, 'X-Estado-Versao': str(versao)})
        cab.update(headers or {})
        conn = http.client.HTTPConnection('127.0.0.1', self.porta, timeout=4)
        try:
            conn.request('GET' if obj is None else 'POST', caminho,
                         body=None if obj is None else json.dumps(obj).encode(), headers=cab)
            resposta = conn.getresponse()
            return resposta.status, json.loads(resposta.read())
        finally:
            conn.close()

    def test_mesma_intencao_replay_e_outra_aba_com_snapshot_antigo_nao_repete(self):
        with patch.object(app, 'registrar_agua', return_value=(1, 8)) as agua:
            inicial = self.requisicao(caminho='/api/estado')[1]['versao_estado']
            primeiro = self.requisicao({'acao': 'agua'}, chave='intencao-agua-0001', versao=inicial)
            repetido = self.requisicao({'acao': 'agua'}, chave='intencao-agua-0001', versao=inicial)
            status, rejeitado = self.requisicao({'acao': 'agua'}, chave='outra-aba-agua-0002', versao=inicial)
        self.assertEqual(primeiro[0], 200)
        self.assertEqual(repetido, primeiro)
        self.assertEqual(status, 409)
        self.assertGreater(rejeitado['versao_estado'], inicial)
        agua.assert_called_once()

    def test_concorrente_inflight_consulta_resultado_e_cancelamento_windows_livre(self):
        entrou, liberar = threading.Event(), threading.Event()
        self.addCleanup(liberar.set)
        def registrar():
            entrou.set()
            if not liberar.wait(3):raise RuntimeError('O teste não liberou a operação')
            return 1, 8
        with patch.object(app, 'registrar_agua', side_effect=registrar) as agua, \
                patch.object(app, 'cancelar_reinicio_windows', return_value='Cancelamento solicitado') as cancelar, \
                ThreadPoolExecutor(max_workers=1) as executor:
            futuro = executor.submit(self.requisicao, {'acao': 'agua'}, chave='intencao-lenta-0001')
            self.assertTrue(entrou.wait(2))
            status, res = self.requisicao({'acao': 'agua'}, chave='intencao-lenta-0001')
            self.assertEqual(status, 202)
            self.assertEqual(res['estado'], 'em_andamento')
            status, consulta = self.requisicao(caminho='/api/resultado_acao?id=intencao-lenta-0001')
            self.assertEqual(status, 200); self.assertEqual(consulta['estado'], 'em_andamento')
            self.assertEqual(self.requisicao({'acao': 'agua'}, chave='segunda-intencao-0002')[0], 409)
            status, _ = self.requisicao({'acao': 'cancelar_reinicio_windows'}, chave='cancelar-windows-0003', versao=0)
            self.assertEqual(status, 200); cancelar.assert_called_once()
            liberar.set()
            self.assertEqual(futuro.result(timeout=3)[0], 200)
            agua.assert_called_once()
        consulta = self.requisicao(caminho='/api/resultado_acao?id=intencao-lenta-0001')[1]
        self.assertEqual(consulta['estado'], 'concluido')
        self.assertEqual(consulta['codigo_http'], 200)

    def test_chave_reutilizada_com_outro_payload_recebe409(self):
        with patch.object(app, 'registrar_agua', return_value=(1, 8)) as agua, \
                patch.object(app, 'simular_ru') as simular:
            self.assertEqual(self.requisicao({'acao': 'agua'}, chave='mesma-chave-0001')[0], 200)
            status, _ = self.requisicao({'acao': 'ru', 'quantidade': 5}, chave='mesma-chave-0001')
            self.assertEqual(status, 409)
            agua.assert_called_once(); simular.assert_not_called()

    def test_resposta_http_perdida_recupera_sucesso_sem_novo_post(self):
        self.servidor.perder_resposta = True
        with patch.object(app, 'registrar_agua', return_value=(1, 8)) as agua:
            with self.assertRaises(http.client.RemoteDisconnected):
                self.requisicao({'acao': 'agua'}, chave='resposta-perdida-0001')
            status, recuperado = self.requisicao(caminho='/api/resultado_acao?id=resposta-perdida-0001')
            self.assertEqual(status, 200)
            self.assertEqual(recuperado['estado'], 'concluido')
            self.assertEqual(recuperado['codigo_http'], 200)
            self.assertTrue(recuperado['resposta']['ok'])
            self.assertNotIn('erro', recuperado['resposta'])
            agua.assert_called_once()

    def test_consulta_nega_token_host_e_origem_antes_de_olhar_cache(self):
        with patch.object(self.controle, 'consultar', wraps=self.controle.consultar) as consultar, \
                patch.object(self.controle, 'reservar', wraps=self.controle.reservar) as reservar:
            for headers in ({'X-Painel-Token': 'incorreto'},
                            {'Host': 'invasor.example:' + str(self.porta)},
                            {'Origin': 'http://invasor.example'}):
                with self.subTest(headers=headers):
                    self.assertEqual(self.requisicao(caminho='/api/resultado_acao?id=privado-0001', headers=headers)[0], 403)
                    self.assertEqual(self.requisicao({'acao': 'agua'}, chave='privado-0001', headers=headers)[0], 403)
            consultar.assert_not_called()
            reservar.assert_not_called()

    def test_png_e_preservado_no_replay_e_na_consulta_aninhada(self):
        chat = central.obter_chat_ativo('painel')
        pendente = {'contexto': 'painel', 'chat_id': chat['id'], 'expira': time.monotonic() + 60,
                    'plano': {'acao': 'pc', 'campos': {'comando': 'print'}, 'descricao': 'Capturar tela'}}
        # A sequência parece credencial ao redator genérico: a imagem já validada
        # deve atravessar tanto a resposta inicial quanto o cache sem alteração.
        imagem = 'data:image/png;base64,AIza' + 'A' * 40
        with patch.object(app, 'PEDIDOS_PAINEL', {'pedido-foto': pendente}), \
                patch.object(app, 'executar_plano_natural', return_value={'mensagem': 'Captura obtida', 'imagem': imagem}) as executar:
            primeiro = self.requisicao({'acao': 'pedido_confirmar', 'id': 'pedido-foto'}, chave='foto-confirmada-0001')
            segundo = self.requisicao({'acao': 'pedido_confirmar', 'id': 'pedido-foto'}, chave='foto-confirmada-0001')
            status, consulta = self.requisicao(caminho='/api/resultado_acao?id=foto-confirmada-0001')
        self.assertEqual(primeiro[0], 200); self.assertEqual(segundo, primeiro)
        self.assertEqual(status, 200)
        self.assertEqual(primeiro[1]['imagem'], imagem)
        self.assertEqual(consulta['resposta']['imagem'], imagem)
        executar.assert_called_once()

    def test_headers_incompletos_ou_invalidos_nao_executam(self):
        with patch.object(app, 'registrar_agua') as agua:
            for headers in ({'X-Idempotency-Key': 'chave-valida-0001'},
                            {'X-Estado-Versao': '0'},
                            {'X-Idempotency-Key': 'curta', 'X-Estado-Versao': '0'},
                            {'X-Idempotency-Key': 'chave-valida-0001', 'X-Estado-Versao': '-1'}):
                with self.subTest(headers=headers):
                    self.assertEqual(self.requisicao({'acao': 'agua'}, headers=headers)[0], 400)
            agua.assert_not_called()

    def test_cliente_legado_funciona_e_invalida_snapshot_dos_novos(self):
        with patch.object(app, 'registrar_agua', return_value=(1, 8)) as agua:
            versao = self.requisicao(caminho='/api/estado')[1]['versao_estado']
            self.assertEqual(self.requisicao({'acao': 'agua'})[0], 200)
            self.assertEqual(self.requisicao({'acao': 'agua'}, chave='novo-cliente-0001', versao=versao)[0], 409)
            atual = self.requisicao(caminho='/api/estado')[1]['versao_estado']
            self.assertEqual(self.requisicao({'acao': 'agua'}, chave='novo-cliente-0002', versao=atual)[0], 200)
            self.assertEqual(agua.call_count, 2)


class LimitesIdempotencia(unittest.TestCase):
    def test_ttl_nao_remove_inflight_e_capacidade_recusa_antes_da_execucao(self):
        agora = [100]
        controle = ControleAcoes(ttl=5, capacidade=1, relogio=lambda: agora[0])
        self.assertTrue(controle.reservar('primeiro-pedido', {'acao': 'agua'}, 0)['executar'])
        agora[0] = 200
        self.assertEqual(controle.consultar('primeiro-pedido')['estado'], 'em_andamento')
        with self.assertRaises(FalhaControle) as erro:
            controle.reservar('segundo-pedido', {'acao': 'agua'}, controle.versao())
        self.assertEqual(erro.exception.codigo, 409)
        controle.finalizar('primeiro-pedido', 200, {'ok': True})
        with self.assertRaises(FalhaControle) as erro:
            controle.reservar('segundo-pedido', {'acao': 'agua'}, controle.versao())
        self.assertEqual(erro.exception.codigo, 503)
        self.assertEqual(controle.consultar('primeiro-pedido')['estado'], 'concluido')
        agora[0] += 5
        self.assertTrue(controle.reservar('segundo-pedido', {'acao': 'agua'}, controle.versao())['executar'])

    def test_resultado_excessivo_e_retido_sem_reexecucao(self):
        controle = ControleAcoes(max_resposta=1024, max_bytes=2048)
        controle.reservar('resultado-grande', {'acao': 'teste'}, 0)
        codigo, resposta = controle.finalizar('resultado-grande', 200, {'mensagem': 'X' * 2000})
        self.assertEqual(codigo, 500)
        self.assertTrue(resposta['resultado_incompleto'])
        replay = controle.reservar('resultado-grande', {'acao': 'teste'}, 0)
        self.assertFalse(replay['executar'])
        self.assertEqual(replay['codigo_http'], 500)
        self.assertEqual(replay['resposta'], resposta)


if __name__ == '__main__':
    unittest.main()
