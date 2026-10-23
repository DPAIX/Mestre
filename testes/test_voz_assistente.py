"""Áudio em memória com Gemini simulado, sem Telegram/rede ou credenciais reais."""
from __future__ import annotations

import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import voz_assistente as voz
from multi_ia import FalhaAPI


class VozAssistenteTeste(unittest.TestCase):
    def setUp(self):
        self.chave = 'fixture-chave-privada-nao-exibir'
        ambiente = patch.dict(os.environ, {'GEMINI_API_KEY': self.chave}, clear=True)
        ambiente.start(); self.addCleanup(ambiente.stop)
        self.cliente = MagicMock()
        self.cliente.models.generate_content.return_value = SimpleNamespace(text='Abra o VS Code.')
        self.genai = SimpleNamespace(Client=MagicMock(return_value=self.cliente))
        modulos = patch.dict(sys.modules, {'google': SimpleNamespace(genai=self.genai)})
        modulos.start(); self.addCleanup(modulos.stop)
        self.roteador = MagicMock()
        self.roteador.estado_local.return_value = {'Gemini': {'em_pausa': False}}

    def test_sem_chave_nao_tenta_cliente_e_diferencia_modelos_de_texto(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(FalhaAPI) as erro:
            voz.verificar_disponibilidade_voz(self.roteador)
        self.assertEqual(erro.exception.categoria, 'configuracao')
        self.assertIn('não transcrevem', erro.exception.detalhe)
        self.roteador.estado_local.assert_not_called()
        self.genai.Client.assert_not_called()

    def test_pausa_de_autenticacao_falha_antes_do_cliente_sem_reativar(self):
        self.roteador.estado_local.return_value = {'Gemini': {
            'em_pausa': True, 'categoria': 'autenticacao', 'codigo': 401}}
        with self.assertRaises(FalhaAPI) as erro:
            voz.transcrever_audio(b'fixture-audio', 'audio/ogg', self.roteador)
        self.assertEqual(erro.exception.categoria, 'suspenso')
        self.assertIn('credencial rejeitada', erro.exception.detalhe)
        self.genai.Client.assert_not_called()
        self.roteador.reativar.assert_not_called()

    def test_voice_usa_ogg_e_audio_comum_preserva_mime_real(self):
        arquivo = SimpleNamespace(file_size=20, mime_type='audio/mpeg')
        self.assertEqual(voz.tipo_audio(arquivo, voz=True), 'audio/ogg')
        self.assertEqual(voz.tipo_audio(arquivo), 'audio/mpeg')
        self.genai.Client.assert_not_called()

    def test_metadados_invalidos_e_arquivo_grande_nao_iniciam_api(self):
        for tamanho in (-1, True, 3.0, '13', voz.LIMITE_AUDIO+1):
            with self.subTest(tamanho=tamanho), self.assertRaises(ValueError):
                voz.tipo_audio(SimpleNamespace(file_size=tamanho), voz=True)
        for arquivo in (None, SimpleNamespace(file_size=10, mime_type='video/mp4'),
                        SimpleNamespace(file_size=10, mime_type=None)):
            with self.subTest(arquivo=arquivo), self.assertRaises(ValueError):
                voz.tipo_audio(arquivo)
        self.genai.Client.assert_not_called()

    def test_corpo_vazio_grande_ou_mime_invalido_nao_inicia_api(self):
        for dados in (b'', bytearray(b'fixture'), None, 'fixture', b'x'*(voz.LIMITE_AUDIO+1)):
            with self.subTest(tipo=type(dados).__name__), self.assertRaises(ValueError):
                voz.transcrever_audio(dados, 'audio/ogg', self.roteador)
        with self.assertRaises(ValueError):
            voz.transcrever_audio(b'fixture', 'application/octet-stream', self.roteador)
        self.genai.Client.assert_not_called()

    def test_uma_chamada_inline_sem_arquivos_ou_execucao_da_transcricao(self):
        with patch('builtins.open', side_effect=AssertionError('Sem arquivos')):
            texto = voz.transcrever_audio(b'fixture-audio', 'audio/mpeg', self.roteador)
        self.assertEqual(texto, 'Abra o VS Code.')
        self.genai.Client.assert_called_once_with(api_key=self.chave, http_options={
            'timeout': 18000, 'retry_options': {'attempts': 1}})
        self.cliente.models.generate_content.assert_called_once()
        opcoes = self.cliente.models.generate_content.call_args.kwargs
        self.assertEqual(opcoes['contents'][0]['parts'][1], {
            'inline_data': {'mime_type': 'audio/mpeg', 'data': b'fixture-audio'}})
        self.assertIn('somente a transcrição', opcoes['contents'][0]['parts'][0]['text'])
        self.cliente.files.upload.assert_not_called()
        self.cliente.close.assert_called_once_with()
        self.roteador.responder.assert_not_called()
        self.roteador.registrar_falha.assert_not_called()

    def test_erro_401_mostra_causa_sem_repetir_corpo_chave_ou_texto(self):
        erro_sdk = RuntimeError('Corpo privado: '+self.chave+' fixture-fala-pessoal')
        erro_sdk.code = 401
        self.cliente.models.generate_content.side_effect = erro_sdk
        with self.assertRaises(FalhaAPI) as erro:
            voz.transcrever_audio(b'fixture-audio', 'audio/ogg', self.roteador)
        self.assertEqual(erro.exception.codigo, 401)
        self.assertEqual(erro.exception.categoria, 'autenticacao')
        self.assertIn('credencial', erro.exception.detalhe)
        self.assertNotIn(self.chave, str(erro.exception))
        self.assertNotIn('fixture-fala-pessoal', str(erro.exception))
        self.cliente.models.generate_content.assert_called_once()
        self.roteador.registrar_falha.assert_called_once_with(erro.exception)
        self.cliente.close.assert_called_once_with()

    def test_timeout_sem_retry_e_falha_de_close_nao_oculta_causa(self):
        self.cliente.models.generate_content.side_effect = TimeoutError(self.chave)
        self.cliente.close.side_effect = OSError('fixture-erro-close')
        with self.assertRaises(FalhaAPI) as erro:
            voz.transcrever_audio(b'fixture-audio', 'audio/ogg', self.roteador)
        self.assertEqual(erro.exception.categoria, 'rede')
        self.assertIn('timeout', erro.exception.detalhe)
        self.assertNotIn(self.chave, str(erro.exception))
        self.cliente.models.generate_content.assert_called_once()
        self.cliente.close.assert_called_once_with()

    def test_creditos_insuficientes_sao_diferentes_de_problema_de_rede(self):
        erro_sdk = RuntimeError('insufficient_quota '+self.chave)
        erro_sdk.code = 402
        self.cliente.models.generate_content.side_effect = erro_sdk
        with self.assertRaises(FalhaAPI) as erro:
            voz.transcrever_audio(b'fixture-audio', 'audio/ogg', self.roteador)
        self.assertEqual(erro.exception.categoria, 'sem_creditos')
        self.assertIn('sem créditos', erro.exception.detalhe)
        self.cliente.close.assert_called_once_with()

    def test_resposta_vazia_invalida_ou_extensa_nao_vira_pedido_truncado(self):
        for texto in ('', '   ', None, 10, 'x'*(voz.LIMITE_TRANSCRICAO+1)):
            with self.subTest(tipo=type(texto).__name__):
                self.cliente.models.generate_content.return_value = SimpleNamespace(text=texto)
                with self.assertRaises(FalhaAPI) as erro:
                    voz.transcrever_audio(b'fixture-audio', 'audio/ogg', self.roteador)
                self.assertEqual(erro.exception.categoria, 'resposta_invalida')
        self.assertEqual(self.cliente.models.generate_content.call_count, 5)
        self.assertEqual(self.cliente.close.call_count, 5)
        self.roteador.responder.assert_not_called()

    def test_alias_google_api_key_e_modelo_configurado_sao_respeitados(self):
        with patch.dict(os.environ, {'GOOGLE_API_KEY': self.chave, 'GEMINI_MODEL': 'fixture-audio-model'}, clear=True):
            self.assertEqual(voz.transcrever_audio(b'fixture-audio', 'audio/wav'), 'Abra o VS Code.')
        self.assertEqual(self.cliente.models.generate_content.call_args.kwargs['model'], 'fixture-audio-model')
        self.assertEqual(self.genai.Client.call_args.kwargs['api_key'], self.chave)


if __name__ == '__main__':
    unittest.main()
