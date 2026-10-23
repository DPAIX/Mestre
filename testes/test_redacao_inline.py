"""Redação de credenciais fictícias, com dados temporários e provedores simulados."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import colaboracao_chats as central
import equipe_ia
import multi_ia
import nucleo
import servicos_chat


class RedacaoInlineTeste(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name) / 'codigo'
        self.base.mkdir()
        self.dados = Path(self.tmp.name) / 'dados'
        for nome, valor in (('BASE', self.base), ('DADOS', self.dados)):
            p = patch.object(nucleo, nome, valor)
            p.start(); self.addCleanup(p.stop)
        p = patch.dict(os.environ, {'OPENAI_API_KEY': 'fixture-provider'}, clear=True)
        p.start(); self.addCleanup(p.stop)
        self.contexto = 'fixture-owner:fixture-chat:0'
        self.segredo = 'fixture-uuid-sem-prefixo-93fa'

    def test_campos_nomeados_inline_e_entre_aspas(self):
        for nome in ('TELEGRAM_TOKEN', 'GEMINI_API_KEY', 'GOOGLE_API_KEY',
                     'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'CLAUDE_API_KEY',
                     'EXA_API_KEY', 'API_KEY', 'access_token', 'refresh_token',
                     'client_secret', 'Authorization', 'X-API-Key', 'TOKEN'):
            for forma in ('Veja {nome}={segredo}; continue.',
                          'Veja {nome}: {segredo}, continue.',
                          'Veja {nome}="{segredo}"; continue.',
                          "Veja '{nome}': '{segredo}', continue."):
                with self.subTest(nome=nome, forma=forma):
                    texto = forma.format(nome=nome, segredo=self.segredo)
                    seguro = nucleo.redigir(texto)
                    self.assertNotIn(self.segredo, seguro)
                    self.assertIn('continue.', seguro)
                    self.assertEqual(nucleo.redigir(seguro), seguro)

    def test_json_aspas_escapadas_e_colecoes_permanecem_validos(self):
        valores = [self.segredo + '"parte-final', self.segredo + '\\parte-final',
                   [self.segredo, 'fixture-segundo-segredo'],
                   {'nested': [self.segredo, {'value': 'fixture-segundo-segredo'}]},
                   123456, None]
        for valor in valores:
            with self.subTest(valor=valor):
                texto = json.dumps({'CLIENT_SECRET': valor, 'outro': 'legivel'})
                seguro = nucleo.redigir(texto)
                atual = json.loads(seguro)
                self.assertEqual(atual['CLIENT_SECRET'], '[CREDENCIAL-REDACTADA]')
                self.assertEqual(atual['outro'], 'legivel')
                self.assertNotIn(self.segredo, seguro)
                self.assertNotIn('fixture-segundo-segredo', seguro)
        texto = 'POOL_CHAVES_API=["' + self.segredo + '",\n"fixture-segundo-segredo"]; fim'
        seguro = nucleo.redigir(texto)
        self.assertNotIn(self.segredo, seguro)
        self.assertNotIn('fixture-segundo-segredo', seguro)
        self.assertIn('; fim', seguro)

    def test_cabecalho_autorizacao_e_prefixos_existentes(self):
        for esquema in ('Bearer', 'Basic', 'Token'):
            texto = 'Diagnóstico Authorization: ' + esquema + ' ' + self.segredo + '; fim'
            self.assertNotIn(self.segredo, nucleo.redigir(texto))
        segredo = 'sk-proj-' + 'X' * 35
        self.assertNotIn(segredo, nucleo.redigir('Chave sem nome: ' + segredo))
        valor = {'client_secret': self.segredo, 'dados': [{'texto': 'EXA_API_KEY=' + self.segredo}],
                 'quantidade': 3, 'ativo': True}
        seguro = nucleo.redigir(valor)
        self.assertEqual(seguro['client_secret'], '[REDACTADO]')
        self.assertEqual(seguro['quantidade'], 3)
        self.assertIs(seguro['ativo'], True)
        self.assertNotIn(self.segredo, json.dumps(seguro))
        self.assertIn(self.segredo, valor['client_secret'])

    def test_payload_resposta_historico_log_e_exportacao_sem_segredos(self):
        (self.base / 'nucleo.py').write_text('# Exemplo inline: EXA_API_KEY=' + self.segredo + '; fim\n', encoding='utf-8')
        (self.base / '.env').write_text('fixture-privada-nao-exportar', encoding='utf-8')
        chat = central.obter_chat_ativo(self.contexto)
        central.configurar_chat(self.contexto, chat['id'], provedor='OpenAI')
        roteador = multi_ia.Roteador()
        resposta_secreta = 'fixture-resposta-confidencial'
        retorno = 'Revisão CLIENT_SECRET="' + resposta_secreta + '"; concluída.'
        with patch.object(multi_ia, 'postar', return_value={
                'choices': [{'message': {'content': retorno}}]}) as pedido:
            resposta = servicos_chat.conversar(
                'Analise EXA_API_KEY=' + self.segredo + '; contexto legível.',
                self.contexto, roteador)
        payload = pedido.call_args.args[2]
        self.assertNotIn(self.segredo, json.dumps(payload))
        self.assertIn('contexto legível.', json.dumps(payload, ensure_ascii=False))
        self.assertNotIn(resposta_secreta, resposta)
        central.criar_tarefa('Revisão', 'CLIENT_SECRET=' + self.segredo)
        central.importar_contribuicao('Fixture', 'Análise', 'EXA_API_KEY=' + self.segredo)
        conteudos = [json.dumps(central.historico_chat(self.contexto)),
                     json.dumps(nucleo.ler_json('log_acoes_e_erros.json', [])),
                     (self.dados / central.ARQUIVO).read_text(encoding='utf-8')]
        for caminho in (central.exportar_contexto(self.contexto), nucleo.exportacao_segura()):
            with zipfile.ZipFile(caminho) as pacote:
                conteudos.extend(pacote.read(nome).decode('utf-8') for nome in pacote.namelist())
        for conteudo in conteudos:
            self.assertNotIn(self.segredo, conteudo)
            self.assertNotIn(resposta_secreta, conteudo)
            self.assertNotIn('fixture-privada-nao-exportar', conteudo)

    def test_resposta_estruturada_ia_sanitizada_antes_do_plano(self):
        central.configurar_chat(self.contexto,central.obter_chat_ativo(self.contexto)['id'],equipe_politica='manual')
        roteador = MagicMock()
        roteador.responder.return_value = (json.dumps({
            'resposta': 'Veja EXA_API_KEY=' + self.segredo + '; fim.',
            'acao': None, 'campos': {}}), 'OpenAI')
        resultado = servicos_chat.conversar(
            'Veja CLIENT_SECRET="' + self.segredo + '"; continue.',
            self.contexto, roteador, retornar_plano=True)
        self.assertIsNone(resultado['plano'])
        self.assertNotIn(self.segredo, resultado['texto'])
        self.assertNotIn(self.segredo, roteador.responder.call_args.args[0])

    def test_equipe_sanitiza_objetivo_e_proposta(self):
        roteador = MagicMock()
        roteador.estado_local.return_value = {'OpenAI': {'configurado': True, 'em_pausa': False}}
        roteador.responder.return_value = ('CLIENT_SECRET=' + self.segredo, 'OpenAI')
        resultado = equipe_ia.consultar_equipe(
            'Analise EXA_API_KEY=' + self.segredo, roteador,
            provedores=['OpenAI'], confirmacao='CONSULTAR EQUIPE')
        self.assertTrue(resultado['resultados'][0]['ok'])
        self.assertNotIn(self.segredo, roteador.responder.call_args.args[0])
        self.assertNotIn(self.segredo, json.dumps(resultado))
        self.assertNotIn(self.segredo, (self.dados / central.ARQUIVO).read_text(encoding='utf-8'))

    def test_imagem_base64_confiavel_permanece_intacta_no_fluxo_painel(self):
        # O padrão AIza pode ocorrer por acaso no alfabeto base64. O handler
        # restaura a imagem interna depois de sanear os outros campos JSON.
        import assistente_pc as app
        imagem = 'data:image/png;base64,iVBORw0KGgoAIza' + 'A' * 40
        handler = SimpleNamespace(_headers=MagicMock(), wfile=io.BytesIO(), _encerrar_prazo_leitura=MagicMock())
        app.PainelHandler._json(handler, {'mensagem': 'EXA_API_KEY=' + self.segredo}, imagem=imagem)
        resposta = json.loads(handler.wfile.getvalue())
        self.assertEqual(resposta['imagem'], imagem)
        self.assertNotIn(self.segredo, resposta['mensagem'])


if __name__ == '__main__':
    unittest.main()
