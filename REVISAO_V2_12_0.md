# Revisão v2.12.0 — equipe e conversa por texto ou áudio

## Como usar

Escreva ou grave o pedido no Telegram, sem precisar de comandos com barra. Exemplos:

- **“Trabalhem juntos”** prepara a ativação da equipe cooperativa com os modelos registrados no Ollama.
- **“Teste todos os modelos”** prepara uma consulta curta por modelo Ollama, sem histórico. Confirme para iniciar e acompanhe o progresso.
- **“Mostre os modelos disponíveis”** consulta somente o catálogo.
- **“Use somente o modelo llama3.2:latest nesta conversa”** prepara a seleção individual, sem mudar o padrão global.
- **“Use Gemini”** ou **“Quero conversar com Claude”** prepara a escolha do provedor nesta conversa. Configuração, acesso e cota continuam necessários.
- **“Adicione uma tarefa”** faz o assistente perguntar o título. A resposta pode ser escrita ou falada.
- **“Agende estudar”** gera perguntas sobre dia e horário. A atividade é da rotina local; isso não cria um alarme nem grava na Agenda Google.
- **“Abra a calculadora”** prepara a ação. Diga **“sim”** para confirmar ou **“cancelar”** para desistir, por texto ou áudio.

Uma pergunta sobre dados ausentes não é uma confirmação de execução. O assistente primeiro completa o pedido e depois apresenta a ação aplicável para confirmação. Dados inválidos ou ambíguos geram outra pergunta. O áudio usa a transcrição configurada e passa pelo mesmo fluxo autorizado do texto.

Se você pausou a conversa anteriormente, diga **“volte a conversar”** para retomá-la. A pausa explícita continua respeitada. Os comandos antigos permanecem compatíveis; não são necessários para os fluxos acima.

## Equipe: problema e mudança

No computador do proprietário, o Llama respondeu ao teste individual e à conversa individual, mas excedeu o prazo na equipe. O código impunha 30 segundos por modelo no perfil CPU e 90 segundos compartilhados entre todos os participantes e a síntese. O modo individual permitia 90 segundos por padrão. A equipe também acrescentava instruções e resumos ao pedido. Essa diferença foi reproduzida nos testes de orçamento; ela não identifica sozinha toda causa de lentidão no computador.

O adaptador nativo agora fornece o orçamento da rodada. A política **adaptativo** reconhece o par padrão antigo 90/30 e reserva para cada participante o prazo individual configurado, incluindo uma oportunidade para síntese. Com quatro modelos e prazo individual padrão de 90 segundos, o orçamento de novos envios é de até 450 segundos. Há teto de 900 segundos; valores personalizados continuam respeitados. A política **legado**, pela opção avançada `OLLAMA_EQUIPE_ORCAMENTO`, preserva também os limites antigos. O `.env` existente não é regravado por essa mudança.

Os prompts compactos da equipe foram reduzidos. No perfil CPU, uma seleção de participantes independentes usa execução sequencial, inclusive quando o modo solicitado era paralelo, para evitar enfileirar várias cargas de modelos locais simultaneamente. O relatório distingue o modo solicitado da execução efetiva. O perfil padrão e os adaptadores legados conservam seus contratos.

Todos os participantes continuam na seleção e no relatório. Falha de memória, modelo ausente, autenticação e timeout não são apresentados como sucesso. Um modelo de 27 bilhões de parâmetros pode exceder os recursos disponíveis; o programa mostra a estimativa e permite escolher outro modelo instalado ou um gateway já configurado, mediante pedido do proprietário. Não substitui tags silenciosamente, baixa pesos ou autoriza nuvem por conta própria.

## Teste dos modelos e conclusão incerta

`bateria_modelos.py` faz uma consulta curta por tag, sem histórico, síntese, fallback ou repetição automática. Usa a mesma trava da equipe, mantém cada participante no resultado e informa quantos responderam. A ordenação pode priorizar modelos menores; o resultado conserva a seleção original.

Uma resposta que declara explicitamente `done` diferente de `true` é tratada como geração sem conclusão confirmada. Timeout também não comprova cancelamento no servidor. Nessas situações, a equipe e a bateria adiam novos envios; continuam mostrando os modelos que não foram consultados. Isso evita acumular novas gerações sobre uma consulta cujo estado é desconhecido.

Os orçamentos restringem novos envios e o timeout de socket do transporte existente. Não constituem prazo absoluto se o servidor transmitir dados continuamente. Esta revisão não mata o Ollama, não usa a lista de modelos carregados como prova de ociosidade e não garante que todas as tags caibam no hardware.

## Esclarecimentos e áudio

`esclarecimento_conversa.py` mantém rascunhos em memória por até cinco minutos, com limite de 500, separados por usuário, canal e conversa selecionada. Completar um rascunho produz apenas um plano validado. Mudança de conversa, expiração, cancelamento ou novo pedido não executam o rascunho anterior. Não há migração dos JSON existentes nem gravação desses rascunhos em disco.

`assistente_pc.py` encaminha o texto transcrito ao mesmo tratamento de mensagem. Antes, o áudio passava diretamente à interpretação, e um “sim” falado podia deixar de confirmar um pedido que funcionava por texto. Agora a autorização, o tópico, a validade e o consumo único da confirmação são comuns aos dois caminhos. Frases com negação ou outro pedido não confirmam uma ação por conterem a palavra “sim”.

## Atualização e validação

Extraia o pacote completo em Downloads, fora da instalação, feche uma preparação anterior ainda aberta e abra **`INSTALAR_E_INICIAR.bat`**. A implantação existente confere o manifesto, guarda backup das fontes e preserva configuração, dados, modelos, ambientes virtuais e rede.

No PC, diga **“teste todos os modelos”**, confirme e confira o relatório de cada tag. Depois diga **“trabalhem juntos”**, confirme e envie o pedido real. Para verificar perguntas e áudio, diga **“adicione uma tarefa”**, responda ao título em áudio e confirme ou cancele. Esses passos validam o hardware, a transcrição e as contas reais; não exigem comandos com barra.

Os testes automatizados usam modelos, áudio e mensagens fictícios, relógios controlados e HTTP em loopback. Verificam orçamento, conclusão incerta, preservação dos participantes, ausência de fallback, perguntas por campos, isolamento de identidade, transcrição encaminhada, confirmação e cancelamento. Os resultados da suíte, do pacote extraído e da matriz Windows/Linux estão no PR desta entrega. Esta sessão não possui um dispositivo Desktop Commander conectado para executar os testes reais no computador do proprietário.

A validação local das fontes públicas aprovou 1.354 testes Python, com três casos de Windows ignorados no Linux, compilação e os 94 testes JavaScript do painel. Há 76 regressões novas nesta revisão. Entre elas, a sequência “abra a calculadora”, “adicione uma tarefa”, “sim” não executa a ação antiga: a nova pergunta invalida a confirmação anterior, inclusive seu botão. Esse comportamento foi verificado por texto e áudio simulados.

## Reversão

Encerre somente o assistente e o preparador. Restaure os arquivos correspondentes ao índice `manifesto_reversao.json` do backup gerado em `backups_codigo\implantacao_<identificador>`, conferindo hashes e preservando alterações posteriores. O [guia de instalação](GUIA_INSTALACAO_AUTONOMA.md) detalha os caminhos. Rascunhos em memória desaparecem ao encerrar; não há novos arquivos privados de estado a restaurar.
