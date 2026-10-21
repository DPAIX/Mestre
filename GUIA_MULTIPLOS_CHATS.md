# Usar vários chats para desenvolver o MeuControlePC

Os três modos estão disponíveis: conversas independentes no Telegram/painel, contribuições trazidas de chats web e equipe de provedores via APIs.

## Começar sem créditos de API

1. Execute `instalar_windows.bat` na pasta nova do projeto.
2. Execute `instalar_ia_local.bat`. Ele instala Ollama pelo `winget` se necessário, inicia o serviço e solicita o download explícito do modelo `qwen2.5:3b`. O modelo usa alguns GB de disco e memória do PC. Se `winget` não estiver disponível, instale o aplicativo em https://ollama.com/download e execute novamente o script.
3. `configurar_ia_local.py` só ativa o modelo no `.env` após confirmar que ele está instalado. Para verificar: `configurar_ia_local.bat --verificar`. Para outro modelo já disponível: `configurar_ia_local.bat --modelo nome:tag`. Para baixar um modelo menor, por exemplo: `configurar_ia_local.bat --baixar-modelo qwen2.5:0.5b`.
4. Encerre o processo antigo e inicie `iniciar_windows.bat` ou `iniciar_somente_painel.bat` na pasta nova. A configuração é carregada ao iniciar.
5. No Telegram: `/chat novo Desenvolvimento`, depois `/chat provedor Ollama` e `/ia Olá, ajude a desenvolver o assistente`. No painel, abra **Chats e projeto**, crie a conversa com **Ollama** e envie a mensagem.

Ollama executa um modelo real localmente e precisa estar funcionando no seu computador. Os scripts não recuperam créditos de Gemini, OpenAI ou Claude. Não confunda assinatura dos chats web com acesso pago às APIs correspondentes.

## 1. Conversas e tópicos independentes

Use `/chats` para ver as conversas do chat/tópico atual. `/chat novo Nome` cria e seleciona uma conversa; `/chat usar ID` alterna. `/chat provedor Gemini`, `OpenAI`, `Claude`, `Ollama` ou `auto` define o motor de resposta. O automático tenta os provedores configurados, respeitando pausas; a seleção explícita consulta somente o escolhido.

`/ia pergunta` usa o histórico da conversa selecionada. `/chat modo on` permite enviar mensagens comuns como conversa contínua; `/chat modo off` volta ao uso explícito de `/ia`. Ativar esse modo pode consumir créditos se um provedor externo estiver selecionado. No painel, cada pergunta também usa a conversa selecionada.

Históricos são persistidos localmente e separados por proprietário, chat e tópico do Telegram. O painel tem seu próprio contexto. Tarefas e propostas do projeto são compartilhadas entre esses espaços. São retidas até vinte trocas por conversa, com limites de tamanho. Históricos não entram no ZIP de contexto.

## 2. Aproveitar ChatGPT, Gemini e Claude dos sites

1. No painel **Chats e projeto**, cadastre tarefas concretas; ou use `/projeto tarefa Revisar API | Verificar autorização do painel | revisão`.
2. Clique **Exportar contexto** ou envie `/contexto`. O ZIP contém fontes sanitizadas, hashes da versão, tarefas e prompts em `prompts/chatgpt.md`, `prompts/gemini.md` e `prompts/claude.md`. Revise o conteúdo antes de compartilhá-lo. Arquivos de `.env`, rotina, finanças, logs de uso e históricos de conversas não são incluídos. As tarefas que você cadastrou para o projeto são incluídas.
3. Anexe o ZIP no chat web escolhido. Peça a uma conversa um plano, a outra a implementação e a outra a revisão/testes. Use os hashes do manifesto para identificar a base analisada.
4. Traga a resposta pela caixa **Importar contribuição** do painel, por `/contribuir Origem | Título | Texto`, ou envie ao bot um arquivo `.md`, `.txt` ou o JSON no formato `template_contribuicao.json`.
5. Revise as propostas e marque aceita/rejeitada. Uma base de código divergente exige revisão antes de aceitar. Aceitar registra uma decisão; aplicar código continua sendo um trabalho revisável no projeto, sem executar texto recebido como script.

Os chats dos sites não são lidos automaticamente nem têm suas sessões acessadas pelo assistente. O pacote de contexto e a importação permitem usar essas conversas sem chave de API e sem compartilhar a senha das contas.

## 3. Consultar uma equipe de IAs pelas APIs

Use `/equipe Descreva uma tarefa concreta e o trecho que deseja revisar`, ou a seção **Equipe de IAs** no painel. Escolha os provedores e confirme. Cada provedor configurado e disponível recebe no máximo uma consulta, em paralelo, com um papel definido. O conteúdo enviado é o objetivo/trecho que você forneceu e instruções fixas de colaboração; não há leitura automática dos seus dados pessoais para essa consulta.

As respostas são guardadas como contribuições no projeto. Falhas parciais são apresentadas por provedor, sem repetir consultas nem aplicar código. Uma equipe em andamento bloqueia outra equipe concorrente. Exa continua sendo usado para `/pesquisar`, não como substituto dos modelos de conversa.

`/conexoes` ou **Testar conexões configuradas** executa uma chamada por provedor configurado após confirmação, inclusive se havia uma pausa local. Pode consumir cota. O resultado diz se a consulta respondeu; não mede saldo. Gemini com cota gratuita ou `RESOURCE_EXHAUSTED` não deve ser chamado de “sem créditos” apenas porque a mensagem cita faturamento.

## Rotina, lembretes e Kanban

`/atividade Quarta | 14:00 | Estudar | 15:00 | Biblioteca` cadastra uma atividade semanal. Uma data específica pode usar `2026-10-22`. `/concluir ID` alterna a conclusão.

`/lembretes on 60` ativa avisos quinze minutos antes e na hora das atividades, além de água a cada sessenta minutos. `/lembretes off` desativa. O bot precisa estar aberto e o proprietário continuar autorizado. Avisos são deduplicados; paradas longas não geram uma tempestade de notificações antigas. O fuso é `America/Sao_Paulo`; o instalador inclui `tzdata` no Windows.

`/tarefa Descrição` adiciona ao Kanban; `/mover A_Fazer 0 Em_Andamento` move o item de índice zero. Finanças continuam disponíveis por `/gasto`, `/entrada`, `/saldo` e `/ru`, sem depender de IA.
