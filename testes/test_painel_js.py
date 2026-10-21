"""Executa regressões do JavaScript quando Node.js está disponível."""
from pathlib import Path
import shutil
import subprocess
import unittest


class PainelJavaScriptTeste(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js não instalado; JavaScript não validado')
    def test_fluxos_do_painel(self):
        script = Path(__file__).with_name('test_painel_frontend.js')
        resultado = subprocess.run(
            ['node', '--test', str(script)], capture_output=True, text=True,
            encoding='utf-8', timeout=20,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
