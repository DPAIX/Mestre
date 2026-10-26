from contextlib import nullcontext
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import corrigir_hosts_spotify as app


class TransformacaoHosts(unittest.TestCase):
    def test_mapeamento_unico_e_comentado_preservando_bytes(self):
        original = b'# utf8: \xc3\xa1\r\n0.0.0.0 wl.spotify.com # nota\r\n127.0.0.1 local\r\n'
        esperado = original.replace(b'0.0.0.0 wl.spotify.com', b'# MeuControlePC: bloqueio desativado; 0.0.0.0 wl.spotify.com')
        novo, quantidade = app.transformar(original)
        self.assertEqual((novo, quantidade), (esperado, 1))
        self.assertEqual(app.transformar(novo), (novo, 0))

    def test_aliases_comentarios_espacos_e_lf_preservados(self):
        original = b'  127.0.0.1\tprimeiro WL.Spotify.COM.\tultimo # wl.spotify.com nota\n'
        novo, quantidade = app.transformar(original)
        self.assertEqual(novo, b'  127.0.0.1\tprimeiro \tultimo # wl.spotify.com nota\n')
        self.assertEqual(quantidade, 1)

    def test_outros_enderecos_bloqueios_e_comentarios_intactos(self):
        original = b'192.0.2.4 wl.spotify.com\r\n0.0.0.0 pixel.spotify.com\r\n0.0.0.0 falso-spotify.invalid\r\n# 0.0.0.0 wl.spotify.com\r\n'
        self.assertEqual(app.transformar(original), (original, 0))
        for endereco in ('0.0.0.0', '127.0.0.1', '::', '::1', '0:0:0:0:0:0:0:1'):
            with self.subTest(endereco=endereco):
                self.assertEqual(app.transformar((endereco+' wl.spotify.com').encode())[1], 1)

    def test_bom_e_encoding_preservados(self):
        for bom, codec in [(b'\xef\xbb\xbf','utf-8'), (b'\xff\xfe','utf-16-le'), (b'\xfe\xff','utf-16-be'), (b'\xff\xfe\0\0','utf-32-le')]:
            with self.subTest(codec=codec):
                texto = '# exemplo ficticio\r\n::1 wl.spotify.com\r\n'
                origem = bom + texto.encode(codec)
                novo, quantidade = app.transformar(origem)
                self.assertEqual(novo, bom + texto.replace('::1 wl', '# MeuControlePC: bloqueio desativado; ::1 wl').encode(codec))
                self.assertEqual(quantidade, 1)


class ReparoHosts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.alvo = Path(self.temp.name)/'hosts'
        self.original = b'127.0.0.1 localhost\r\n0.0.0.0 wl.spotify.com\r\n0.0.0.0 pixel.spotify.com\r\n'
        self.alvo.write_bytes(self.original)
        for objeto, nome, valor in [(app,'_windows',True), (app,'_administrador',True), (app,'_hosts_do_windows',self.alvo)]:
            p = patch.object(objeto, nome, return_value=valor)
            p.start(); self.addCleanup(p.stop)
        p = patch.object(app, '_trava', side_effect=lambda: nullcontext())
        p.start(); self.addCleanup(p.stop)
        p = patch.object(app, '_substituir_nativo', side_effect=lambda alvo,temp: os.replace(temp,alvo))
        self.replace = p.start(); self.addCleanup(p.stop)

    def test_backup_corrige_reaplica_e_restaura_sem_sobrescrever(self):
        self.assertEqual(app.executar('corrigir'), {'estado':'corrigido','alteracoes':1})
        backup = self.alvo.with_name(app.BACKUP)
        recibo = self.alvo.with_name(app.RECIBO)
        self.assertEqual(backup.read_bytes(), self.original)
        salvo = recibo.read_bytes()
        self.assertNotIn(b'pixel', salvo)
        self.assertEqual(app.executar('corrigir')['estado'], 'sem_bloqueio')
        self.assertEqual(recibo.read_bytes(), salvo)
        self.assertEqual(app.executar('restaurar')['estado'], 'restaurado')
        self.assertEqual(self.alvo.read_bytes(), self.original)
        self.assertEqual(app.executar('restaurar')['estado'], 'ja_restaurado')
        self.assertEqual(backup.read_bytes(), self.original)

    def test_recusa_restauracao_com_alteracao_externa(self):
        app.executar('corrigir')
        self.alvo.write_bytes(self.alvo.read_bytes()+b'# alteracao posterior\r\n')
        esperado = self.alvo.read_bytes()
        self.assertEqual(app.executar('restaurar')['estado'], 'arquivo_alterado')
        self.assertEqual(self.alvo.read_bytes(), esperado)

    def test_backup_adulterado_impede_restauracao(self):
        app.executar('corrigir')
        self.alvo.with_name(app.BACKUP).write_bytes(b'nao e o original')
        self.assertEqual(app.executar('restaurar')['estado'], 'backup_incompativel')

    def test_backup_existente_incompativel_nao_sobrescreve(self):
        backup = self.alvo.with_name(app.BACKUP)
        backup.write_bytes(b'outro arquivo')
        self.assertEqual(app.executar('corrigir')['estado'], 'backup_incompativel')
        self.assertEqual(backup.read_bytes(), b'outro arquivo')
        self.assertEqual(self.alvo.read_bytes(), self.original)
        self.replace.assert_not_called()

    def test_sem_admin_ou_sem_windows_nao_modifica(self):
        with patch.object(app, '_administrador', return_value=False):
            self.assertEqual(app.executar('corrigir')['estado'], 'requer_administrador')
        with patch.object(app, '_windows', return_value=False):
            self.assertEqual(app.executar('corrigir')['estado'], 'execute_no_windows')
        self.replace.assert_not_called()

    def test_link_e_limite_recusados(self):
        with patch.object(app, 'MAX_ARQUIVO', 4):
            with self.assertRaises(app.FalhaHosts): app.transformar(b'12345')
        outro = Path(self.temp.name)/'fora'
        outro.write_bytes(self.original)
        self.alvo.unlink()
        try: self.alvo.symlink_to(outro)
        except OSError: return
        self.assertEqual(app.executar('corrigir')['estado'], 'caminho_inseguro')
        self.assertEqual(outro.read_bytes(), self.original)

    def test_arquivo_alterado_antes_replace_nao_e_substituido(self):
        novo = app.transformar(self.original)[0]
        with self.assertRaisesRegex(app.FalhaHosts, 'arquivo_alterado'):
            app._substituir(self.alvo, novo, '0'*64)
        self.replace.assert_not_called()
        self.assertEqual(self.alvo.read_bytes(), self.original)
        self.assertFalse(list(self.alvo.parent.glob('.hosts-spotify-*.tmp')))

    def test_cli_so_exibe_codigos_e_winerror_numerico(self):
        erro = OSError('DOMINIO_PRIVADO_SIMULADO')
        erro.winerror = 32
        saida = io.StringIO()
        with patch.object(app, '_hosts_do_windows', side_effect=erro), patch('sys.stdout',saida):
            self.assertEqual(app.main(['--corrigir']),1)
        self.assertEqual(saida.getvalue(), 'HOSTS_RESULTADO=falha_de_acesso\nHOSTS_WINERROR=32\n')
        self.assertNotIn('DOMINIO_PRIVADO', saida.getvalue())


if __name__ == '__main__':
    unittest.main()
