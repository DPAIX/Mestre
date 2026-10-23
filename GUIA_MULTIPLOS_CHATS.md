# Usar vários chats para desenvolver o MeuControlePC

Os três modos estão disponíveis: conversas independentes no Telegram/painel, contribuições trazidas de chats web e equipe de provedores via APIs.

**v2.4.0:** mensagens comuns agora entram em conversa por padrão. Leia [como conversar e executar pedidos](GUIA_CONVERSA.md). Para corrigir o padrão Ollama sem reiniciar, liste com `/modelos ollama` e selecione uma tag instalada com `/modelos padrao NOME`, ou use **Definir como padrão do Ollama** no painel. Isso salva a configuração, seleciona Ollama na conversa atual e descarta apenas a pausa ligada à configuração Ollama anterior, sem afirmar que o novo modelo já respondeu.

## Começar sem créditos de API

1. Execute `instalar_windows.bat` na pasta nova do projeto.
2. Se já tem Ollama e modelos, execute `configurar_ia_local.bat --listar` e depois `configurar_ia_local.bat --modelo qwen3.5:4b` (use o nome que aparecer na sua lista). Isso reaproveita o modelo sem outro download. Se ainda não tem Ollama, execute `instalar_ia_local.bat`: ele instala pelo `winget` se necessário, inicia o serviço e reaproveita um modelo local existente. Só solicita `qwen2.5:3b` se não houver modelo local. O download usa alguns GB de disco e memória do PC. Sem `winget`, instale em https://ollama.com/download e execute o script novamente.
3. `configurar_ia_local.py` só ativa o modelo no `.env` após confirmar que ele está instalado. Para verificar: `configurar_ia_local.bat --verificar`. Para outro modelo já disponível: `configurar_ia_local.bat --modelo nome:tag`. Para baixar um modelo menor, por exemplo: `configurar_ia_local.bat --baixar-modelo qwen2.5:0.5b`.
4. Encerre o processo antigo e inicie `iniciar_windows.bat` ou `iniciar_somente_painel.bat` na pasta nova. A configuração é carregada ao iniciar.
5. No Telegram: `/chat novo Desenvolvimento`, depois `/chat provedor Ollama` e `/ia Olá, ajude a desenvolver o assistente`. No painel, abra **Chats e projeto**, crie a conversa com **Ollama** e envie a mensagem.

Ollama precisa estar funcionando no seu computador. Modelos locais executam nele; modelos com `-cloud`, `:cloud` ou indicação remota no catálogo usam a nuvem Ollama e dependem de conta, internet e cota. A classificação utiliza o nome e os metadados que o serviço informa, não mede tráfego nem saldo. Os scripts não recuperam créditos de Gemini, OpenAI ou Claude. Não confunda assinatura dos chats web com acesso pago às APIs correspondentes.

### Qwen, Gemma e outros modelos já disponíveis

O menu `ollama` mostra integrações como Claude Code, OpenCode e Cline. Esses nomes são agentes/aplicativos; o modelo está entre parênteses. Selecionar um no launcher não altera automaticamente o MeuControlePC.

Depois de configurar o Ollama e reiniciar o assistente:

```text
/modelos ollama
/chat novo Código com Qwen
/chat modelo qwen3.5:4b
/ia Proponha uma melhoria no assistente
/chat novo Revisão com Gemma
/chat modelo gemma4:31b-cloud
/ia Revise a proposta que vou colar a seguir
```

Os nomes precisam aparecer no catálogo do seu próprio Ollama. A seleção não baixa modelos e não faz inferência; a primeira pergunta testa a geração. Se uma tag não aparecer, confira `ollama list` no PowerShell. Configure/registre o nome pelo próprio Ollama antes de selecioná-lo. O print do menu não prova que o modelo esteja registrado nem que uma resposta será gerada.

No painel, abra **Chats e projeto → Atualizar modelos do Ollama**, selecione um modelo e clique **Usar modelo nesta conversa**. Cada conversa guarda sua escolha sem alterar o modelo padrão das outras. `/chat modelo padrao` volta ao `.env`. Uma falha de um modelo explicitamente escolhido não pausa os outros modelos nem reativa o padrão automaticamente. Cada nova pergunta é uma tentativa única, sem troca silenciosa para outro modelo. Para manter o contexto de modelos distintos separado, crie uma conversa para cada um; trocar o modelo na mesma conversa preserva seu histórico.

## 1. Conversas e tópicos independentes

### Mistral, Llama 3.2 e Qwen dos novos prints — v2.3.2

Esses modelos usam a integração Ollama diretamente, pelo mesmo protocolo de conversa e equipe. O catálogo identifica a família pelo nome da tag e sugere usos; isso organiza o trabalho, sem afirmar desempenho ou compatibilidade com agentes externos.

1. Na pasta nova do projeto, execute `configurar_ia_local.bat --listar`. Para definir um Mistral já instalado como padrão e habilitar Ollama, use `configurar_ia_local.bat --modelo mistral` (o nome precisa constar no catálogo, possivelmente como `mistral:latest`). Reinicie o assistente.
2. No painel **Chats e projeto**, clique **Atualizar modelos do Ollama**. Marque os modelos disponíveis e clique **Criar conversas para modelos marcados**. São aceitos até quatro por vez. A operação cria uma conversa por tag, seleciona a primeira e não duplica conversas já preparadas para o mesmo modelo.
3. Selecione um modelo e clique **Ver detalhes do modelo**. A leitura informa família técnica, parâmetros, quantização, capacidades e contexto máximo declarado pelo Ollama. Não envia uma pergunta, não carrega uma nova janela de contexto nem baixa modelos.
4. Clique **Testar resposta deste modelo** e confirme para fazer uma consulta real curta, sem histórico. O teste não troca para outra IA; resposta, falha ou limite se referem ao modelo escolhido. Modelos cloud podem consumir cota. Depois converse normalmente ou marque os modelos na equipe para gerar propostas.

No Telegram, use os nomes da sua lista:

```text
/modelos ollama
/modelos preparar mistral,llama3.2,qwen3.8:27b
/modelos detalhes mistral
/modelos testar mistral
/ia Proponha melhorias para o assistente
```

A preparação só funciona se os três nomes estiverem registrados no seu Ollama. Nomes sem tag são normalizados para `:latest` quando esse alias estiver presente; outras tags precisam ser escritas por completo. Se algum nome estiver ausente, nenhuma conversa do lote é gravada. É possível preparar só os modelos presentes. O nome completo do Llama não está visível no print: não se deve inferir uma tag apenas pelos 3,2B parâmetros exibidos. O Qwen `qwen3.8:27b` mostrado no Claude Code também precisa ser confirmado no catálogo Ollama.

Para consultar metadados sem iniciar o assistente, execute `configurar_ia_local.bat --detalhes mistral`. Para listar modelos no PowerShell, saia primeiro da conversa `>>>` do Ollama com `/bye` e então execute `ollama list`. Dentro de `>>>`, `list` é texto enviado ao modelo, não um comando de terminal.

### Aviso do Claude Code sobre Qwen e 200 mil tokens

O aviso “model isn't recognized; context assumed to be 200k tokens” vem do cliente Claude Code. Não confirma que o modelo aceite 200 mil tokens, esteja disponível no Ollama ou tenha gerado resposta. O MeuControlePC não reutiliza essa estimativa: os detalhes vêm de `/api/show`, e o contexto máximo declarado continua distinto da janela ativa do serviço.

Para usar Claude Code com Ollama, confira primeiro a tag em `ollama list` e inicie pelo launcher oficial, por exemplo `ollama launch claude --model qwen3.8:27b`, somente se essa tag estiver disponível. Preserve as confirmações de permissões do cliente. O Ollama recomenda modelos com ferramentas e contexto de pelo menos 64k para projetos maiores no Claude Code. O Mistral do print declara 32.768 tokens: pode responder no MeuControlePC, mas fica abaixo dessa recomendação para o agente de código. Llama 3.2 no print declara 131.072; a janela ativa e a memória necessária continuam dependendo do serviço e da máquina. A atualização do Claude Code pode alterar o aviso; esta implementação não afirma removê-lo nem instala/atualiza esse cliente.

Referências: https://docs.ollama.com/integrations/claude-code e https://code.claude.com/docs/en/model-config.

Use `/chats` para ver as conversas do chat/tópico atual. `/chat novo Nome` cria e seleciona uma conversa; `/chat usar ID` alterna. `/chat provedor Gemini`, `OpenAI`, `Claude`, `Ollama` ou `auto` define o motor de resposta. O automático tenta os provedores configurados, respeitando pausas; a seleção explícita consulta somente o escolhido.

`/ia pergunta` usa o histórico da conversa selecionada. `/chat modo on` permite enviar mensagens comuns como conversa contínua; `/chat modo off` volta ao uso explícito de `/ia`. Ativar esse modo pode consumir créditos se um provedor externo estiver selecionado. No painel, cada pergunta também usa a conversa selecionada.

Históricos são persistidos localmente e separados por proprietário, chat e tópico do Telegram. O painel tem seu próprio contexto. Tarefas e propostas do projeto são compartilhadas entre esses espaços. São retidas até vinte trocas por conversa, com limites de tamanho. Históricos não entram no ZIP de contexto.

## 2. Aproveitar ChatGPT, Gemini, Claude, Manus e agentes de código

1. No painel **Chats e projeto**, cadastre tarefas concretas; ou use `/projeto tarefa Revisar API | Verificar autorização do painel | revisão`.
2. Clique **Exportar contexto** ou envie `/contexto`. O ZIP contém fontes sanitizadas, hashes da versão, tarefas e prompts em `prompts/chatgpt.md`, `prompts/gemini.md`, `prompts/claude.md`, `prompts/manus.md`, `prompts/claude_code.md`, `prompts/opencode.md` e `prompts/cline.md`. Revise o conteúdo antes de compartilhá-lo. Arquivos de `.env`, rotina, finanças, logs de uso e históricos de conversas não são incluídos. As tarefas que você cadastrou para o projeto são incluídas.
3. Anexe o ZIP no chat web escolhido. Peça a uma conversa um plano, a outra a implementação e a outra a revisão/testes. Use os hashes do manifesto para identificar a base analisada.
4. Traga a resposta pela caixa **Importar contribuição** do painel, por `/contribuir Origem | Título | Texto`, ou envie ao bot um arquivo `.md`, `.txt` ou o JSON no formato `template_contribuicao.json`.
5. Revise as propostas e marque aceita/rejeitada. Uma base de código divergente exige revisão antes de aceitar. Aceitar registra uma decisão; aplicar código continua sendo um trabalho revisável no projeto, sem executar texto recebido como script.

Os chats dos sites não são lidos automaticamente nem têm suas sessões acessadas pelo assistente. O pacote de contexto e a importação permitem usar essas conversas sem chave de API e sem compartilhar a senha das contas.

No Manus, crie uma tarefa, anexe o ZIP de contexto e use `prompts/manus.md` para pedir uma proposta em texto ou no `template_contribuicao.json`. Traga o resultado como `/contribuir Manus | Revisão | Texto` ou envie o arquivo ao bot. O acesso ao aplicativo Manus mostrado no print é suficiente para esse fluxo manual; não foi adicionada uma API Manus nem automação da sessão do navegador. O mesmo pacote pode ser usado em uma cópia de trabalho por Claude Code, OpenCode ou Cline; o MeuControlePC não os inicia nem concede acesso à instalação em uso.

## 3. Consultar uma equipe de IAs pelas APIs

Use `/equipe Descreva uma tarefa concreta e o trecho que deseja revisar`, ou a seção **Equipe de IAs** no painel. Escolha os provedores e confirme. Cada participante recebe no máximo uma consulta, com um papel definido; há no máximo quatro participantes por equipe. Provedores externos podem executar em paralelo; consultas Ollama da mesma equipe executam em sequência para reduzir a pressão sobre a memória. O conteúdo enviado é o objetivo/trecho que você forneceu e instruções fixas de colaboração; não há leitura automática dos seus dados pessoais para essa consulta.

Para consultar só os seus dois modelos:

```text
/equipe modelos qwen3.5:4b,gemma4:31b-cloud | Proponha melhorias para a criação de atividades
```

No painel, atualize os modelos e marque os desejados em **Modelos Ollama para a equipe**. Cada modelo selecionado substitui o participante Ollama padrão e conta no limite de quatro. Ao selecionar somente modelos, nenhum outro provedor é incluído. O Gemma cloud pode consumir cota Ollama; a confirmação identifica os modelos. A origem de cada contribuição guarda o modelo que respondeu. Não há compartilhamento automático de respostas entre participantes: eles recebem o mesmo objetivo e produzem propostas independentes.

As respostas são guardadas como contribuições no projeto. Falhas parciais são apresentadas por provedor, sem repetir consultas nem aplicar código. Uma equipe em andamento bloqueia outra equipe concorrente. Exa continua sendo usado para `/pesquisar`, não como substituto dos modelos de conversa.

`/conexoes` ou **Testar conexões configuradas** executa uma chamada por provedor configurado após confirmação, inclusive se havia uma pausa local. Pode consumir cota. O resultado diz se a consulta respondeu; não mede saldo. Gemini com cota gratuita ou `RESOURCE_EXHAUSTED` não deve ser chamado de “sem créditos” apenas porque a mensagem cita faturamento.

## Rotina, lembretes e Kanban

`/atividade Quarta | 14:00 | Estudar | 15:00 | Biblioteca` cadastra uma atividade semanal. Uma data específica pode usar `2026-10-22`. `/concluir ID` alterna a conclusão.

`/lembretes on 60` ativa avisos quinze minutos antes e na hora das atividades, além de água a cada sessenta minutos. `/lembretes off` desativa. O bot precisa estar aberto e o proprietário continuar autorizado. Avisos são deduplicados; paradas longas não geram uma tempestade de notificações antigas. O fuso é `America/Sao_Paulo`; o instalador inclui `tzdata` no Windows.

`/tarefa Descrição` adiciona ao Kanban; `/mover A_Fazer 0 Em_Andamento` move o item de índice zero. Finanças continuam disponíveis por `/gasto`, `/entrada`, `/saldo` e `/ru`, sem depender de IA.
