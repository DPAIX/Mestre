# MeuControlePC v2.8.0

**Atualizar e otimizar:** encerre o bot, copie as fontes na raiz em C: e abra `atualizar_assistente.bat`. Ele confere bibliotecas da aplicação/voz/Google, executa `pip check`, limpa bytecode gerado e inicia o assistente, reaproveitando configuração/dados/modelos e o Startup existente. Respostas sociais são locais e rápidas; status sem espera; equipe CPU prioriza modelos menores e explica adiamento por RAM. [Guia de manutenção](GUIA_MANUTENCAO.md) · [Revisão v2.8.0](REVISAO_V2_8_0.md).

**Correção v2.7.1:** a equipe agora preserva os limites CPU do modelo individual e usa instruções/resumos compactos. Conversas sem ação mantêm sua resposta; timeouts não são tratados como prova de falha de rede. [Atualização, validação e reversão](REVISAO_V2_7_1.md).

Abra `ativar_assistente_automatico.bat` uma vez para preparar a voz local e o início após o logon. Depois envie texto ou áudio: Whisper local é o transcritor padrão e todos os modelos Ollama cooperam automaticamente, sem comandos de ativação. Código em C:, configuração/dados/pesos em F:. [Guia de preparação e reversão](GUIA_AUTOMATICO.md) · [Revisão v2.7.0](REVISAO_V2_7_0.md).

Histórico v2.6.0: todos os modelos instalados podem colaborar com `/chat equipe on`: consultas sequenciais, contribuições compartilhadas e uma resposta consolidada. O perfil CPU existente é preservado. [Ativação e limites](GUIA_EQUIPE_COOPERATIVA.md) · [Revisão v2.6.0](REVISAO_V2_6_0.md). A frase “mostre a minha rotina da semana” agora consulta os registros locais.

Se o teste isolado do Llama respondeu em CPU, ative o mesmo caminho no assistente com `/modelos perfil cpu` e confirme no Telegram. O perfil seleciona Llama, usa CPU/contexto pequeno e desativa a equipe desta conversa. [Ativação, limites e reversão](GUIA_PERFIL_CPU.md) · [Revisão v2.5.2](REVISAO_V2_5_2.md).

Para timeouts também reproduzidos no comando nativo do Ollama, há um [diagnóstico independente de RAM, GPU e modelos carregados](GUIA_DIAGNOSTICO_OLLAMA.md). A leitura padrão não gera texto nem altera a configuração.

Corrigida a validação que recusava hábitos textuais/fracionários do próprio projeto e o teste de instalação que confundia uma fixture anterior com nova gravação junto às fontes. [Correções e recuperação sem alterar os dados](REVISAO_V2_5_1.md).

Consulta simultânea opcional aos modelos Ollama: `/chat equipe paralelo`. Respostas identificadas por modelo, histórico por conversa e confirmação de ações preservados. [Guia](GUIA_EQUIPE_PARALELA.md) · [Revisão técnica](REVISAO_V2_5_0.md) · [Auditoria do arquivo enviado](AUDITORIA_ASSISTENTE_V2_5_0.md).

**Código em C: e configuração em F:** execute `iniciar_redirecionado.bat` para usar as fontes em `C:\Users\Mestre\Documents\GitHub\Mestre`, o `.env` em `F:\MeuControlePC_v2\.env` e os dados em `F:\MeuControlePC_v2\dados`. O redirecionador reaproveita o Python instalado, preserva os caminhos nos reinícios e nos configuradores e não copia credenciais para o repositório. Veja [preparação, comandos e reversão](GUIA_REDIRECIONAMENTO.md).

O painel passa a identificar cada pedido no servidor, rejeitar alterações com estado antigo entre abas e recuperar resultados por consulta após perda de resposta HTTP, sem reenviar a ação. [Mudanças e validação](REVISAO_V2_4_1.md).

Assistente Python para Windows com bot Telegram, painel local, rotina, finanças, catálogo RoboTask e provedores de IA configuráveis.

Converse por mensagens comuns para pedir ajuda e preparar ações: “mostre minha rotina”, “abra o VS Code”, “gastei 15,50 com almoço”. Consultas locais funcionam sem IA; pedidos mais livres podem ser interpretados pelo provedor escolhido. Alterações são propostas para confirmação, com histórico separado por conversa. Veja [o guia de conversa e controle](GUIA_CONVERSA.md) e [mudanças, testes e reversão](REVISAO_V2_4_0.md).

Inclui seleção do padrão Ollama no painel/Telegram sem reinício, diagnóstico 404 com catálogo real e assistente de seleção de arquivo OAuth para [Google Agenda](GOOGLE_AGENDA.md).

Conversas com histórico, contribuições de vários chats, equipe de IAs e opção de inferência local por Ollama. Também inclui rotina editável, Kanban e lembretes opcionais. Veja [como começar e usar os três modos de chats](GUIA_MULTIPLOS_CHATS.md).

Agora permite escolher modelos Ollama por conversa e consultar vários deles na equipe, aproveitando os já instalados. O contexto exportado inclui Manus, Claude Code, OpenCode e Cline. Veja [mudanças, testes e reversão da v2.3.1](REVISAO_V2_3_1.md).

Na v2.3.2, Mistral, Llama 3.2 e Qwen recebem identificação no catálogo, criação de conversas separadas em lote, detalhes de capacidades/contexto e teste explícito de resposta. A disponibilidade vem do seu Ollama; não são criadas tags fictícias nem baixados modelos automaticamente. Veja [a revisão atual](REVISAO_V2_3_2.md).

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

Node.js 18 ou superior habilita também as verificações comportamentais do painel. Sem Node, o teste correspondente informa que foi ignorado; o uso normal do assistente não depende de Node. O CI instala Node e executa a suíte em Linux e Windows, com Python 3.11, 3.12 e 3.14.

Os testes usam arquivos temporários e serviços simulados. A conexão real com Telegram, provedores de IA e RoboTask deve ser verificada no seu computador.

Veja o [relatório da revisão](REVISAO_V2_3_0.md) para causas, arquivos alterados, validação manual e reversão. A [documentação completa](LEIA-ME.md) descreve comandos, migração e integrações opcionais.
