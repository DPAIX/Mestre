# MeuControlePC v2.2.3

Assistente Python para Windows com bot Telegram, painel local, rotina, finanças, catálogo RoboTask e provedores de IA configuráveis.

Esta revisão separa falhas locais de alertas de APIs, explica a sobrecarga HTTP 503 e elimina avisos de recursos abertos nos testes do Python 3.14. Mantém as correções de segurança, persistência, finanças e interface da v2.2.2. Os formatos de dados existentes foram preservados.

## Instalação no Windows

1. Extraia o projeto em uma pasta nova e execute `instalar_windows.bat` (Python 3.11 ou superior).
2. Configure seu `.env` local a partir de `.env.exemplo`, ou use `configurar_telegram.bat`.
3. Para migrar uma instalação antiga, siga o [LEIA-ME](LEIA-ME.md) antes de iniciar.
4. Execute `iniciar_somente_painel.bat` ou `iniciar_windows.bat` e abra `http://127.0.0.1:8765` no computador.

Dados de uso, logs e credenciais ficam fora do controle de versão. `dados_iniciais/` contém os exemplos genéricos do ZIP fornecido. O painel aceita somente acesso local. As ações no Windows continuam sujeitas a confirmação.

## Verificação local

```console
python -m unittest discover -s testes -v
python -m compileall -q .
```

Node.js 18 ou superior habilita também as treze verificações comportamentais do painel. Sem Node, o teste correspondente informa que foi ignorado; o uso normal do assistente não depende de Node. O CI instala Node e executa a suíte em Linux e Windows, com Python 3.11, 3.12 e 3.14.

Os testes usam arquivos temporários e serviços simulados. A conexão real com Telegram, provedores de IA e RoboTask deve ser verificada no seu computador.

Veja o [relatório da revisão](REVISAO_V2_2_3.md) para causas, arquivos alterados, validação manual e reversão. A [documentação completa](LEIA-ME.md) descreve comandos, migração e integrações opcionais.
