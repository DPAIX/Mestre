# Conversar e controlar o MeuControlePC v2.4.0

Na v2.5.1, para executar o código em C: com configuração/dados em F:, siga primeiro [GUIA_REDIRECIONAMENTO.md](GUIA_REDIRECIONAMENTO.md) e use `iniciar_redirecionado.bat`. Para consultar todos os modelos Ollama na conversa, ative `/chat equipe on`: [guia da equipe](GUIA_EQUIPE_PARALELA.md). O fluxo de conversa abaixo permanece disponível.

## Começar

Atualize em pasta nova seguindo o LEIA-ME, preserve sua configuração e dados locais, encerre o processo antigo e inicie a versão nova. No Telegram, escreva normalmente: “Olá, me ajude a organizar meu dia”. Não precisa começar com `/ia`. No painel, use a caixa de mensagem em **Chats e projeto**.

Conversas novas e conversas legadas acessadas nesta atualização ficam com conversa contínua ativada. `/chat modo off` pausa as perguntas comuns daquele chat/tópico; `/chat modo on` retoma. Pedidos locais reconhecidos continuam disponíveis, e `/ia pergunta` continua sendo uma consulta explícita. O painel e cada proprietário/chat/tópico do Telegram mantêm seus próprios históricos. A seleção do provedor determina onde as mensagens de conversa são processadas; APIs cloud podem consumir cota.

Se o Telegram recebe suas mensagens e responde pelo Gemini, como no print, já existe um provedor funcionando para aquela consulta. O saldo insuficiente de OpenAI/Claude é uma condição independente. Não é necessário habilitar todos para conversar.

## Pedir ajuda e ações

Você pode escrever, por exemplo:

- “Mostre minha rotina”, “Qual meu saldo?”, “Como está o PC?”, “Mostre meu Kanban”, “Mostre minha agenda”.
- “Abra o VS Code”, “Abra a calculadora”, “Mostre a área de trabalho”, “Capture a tela”, “Pressione F8”.
- “Gastei 15,50 com almoço”, “Recebi 50 reais de reembolso”.
- “Adicione uma tarefa revisar relatório”, “Conclua r1”, “Já bebi água”, “Inicie o Pomodoro”.
- “Agende estudar na sexta às 14:00 até 15:00”. Isso cadastra na **rotina local**; a integração Google Calendar continua somente leitura.
- “Use mistral como padrão”, desde que a tag exista no catálogo Ollama.

Pedidos locais completos são reconhecidos sem chamada de IA. Para formulações mais livres, a IA recebe o histórico selecionado, a mensagem atual, uma referência de data/hora e a lista limitada de ferramentas. Ela pode responder, pedir um dado que falta ou propor uma única ação. Não recebe acesso direto ao terminal, arquivos de credenciais ou execução de código.

Consultas leem os dados reais do assistente. Mudanças e ações do PC mostram o que foi entendido, com os valores/alvos: só depois da confirmação são executadas. No Telegram use os botões ou responda “sim”/“cancele” quando houver um único pedido pendente. Se houver mais de um, use o botão do pedido desejado. No painel, confirme ou cancele no cartão exibido abaixo da resposta.

Pedidos expiram e a mesma confirmação não é reaproveitada. Trocar de conversa impede executar o pedido da conversa anterior. Cancelar não altera os dados. O resultado registrado vem da função local, e não de uma afirmação de execução feita pela IA. “Conclua r1” preserva uma tarefa já concluída.

A captura solicitada no painel aparece ali somente após confirmação. O Pomodoro registra o foco ao concluir; mantenha o assistente aberto. Os atalhos RoboTask usam as configurações existentes e continuam dependendo do RoboTask/sessão gráfica no seu Windows.

## Corrigir Ollama HTTP 404

O print mostra que o teste do padrão Ollama retornou 404. O código sozinho não confirma qual tag estava configurada no seu PC. A nova mensagem confere o catálogo depois do erro para diferenciar uma tag ausente de uma rota que retorna 404 mesmo com o modelo presente. Não baixa modelos nem tenta outra geração automaticamente.

No Telegram:

```text
/modelos ollama
/modelos padrao mistral
/modelos testar mistral
```

Use o nome exibido na sua própria lista; `mistral` só é aceito se existir como esse nome ou `mistral:latest`. No painel, atualize o catálogo, escolha o modelo e clique **Definir como padrão do Ollama**. O assistente salva somente as opções Ollama, habilita essa integração e seleciona o padrão na conversa atual, preservando o histórico. Não exige reiniciar e não limpa pausas de OpenAI/Claude. A geração deve ser confirmada por uma pergunta ou pelo teste explícito.

Se o catálogo tem o modelo mas `/api/chat` retorna 404, confira o serviço/versão e `OLLAMA_URL`. Se o serviço não responde, abra Ollama no PC. Para uso local, selecione uma tag local; modelos `-cloud` dependem da conta, internet e cota Ollama.

## Google Agenda

Execute `autorizar_google.bat`. O autorizador orienta a criação do cliente OAuth Desktop e a seleção do arquivo se não encontrar configuração válida. Também aceita o JSON `credentials.json` junto ao projeto. Veja [o passo a passo](GOOGLE_AGENDA.md). Instalar bibliotecas e fazer backup não criam esse arquivo: a conta precisa concluir a autorização OAuth no navegador. Depois peça “Mostre minha agenda”.

## Limites práticos

O assistente oferece as ferramentas listadas: consultas, rotina/Kanban/finanças, programas e atalhos conhecidos, captura, água, Pomodoro e escolha de modelo. Ele pode ajudar a planejar outras necessidades em conversa, mas não executa comandos arbitrários ou aplica código retornado pelos chats. O desligamento remoto permanece indisponível. Reinício do Windows mantém seu fluxo próprio, desabilitado por padrão e com dupla confirmação.

A qualidade da interpretação livre depende do modelo e da disponibilidade da integração selecionada. Perguntas com parâmetros incompletos devem ser esclarecidas; revise a descrição antes de confirmar. As funções de Windows, modelos reais e OAuth precisam ser validadas no seu computador/conta, pois os testes do pacote usam simulação.
