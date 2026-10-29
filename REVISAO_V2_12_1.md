# Revisão v2.12.1 — respostas utilizáveis da equipe

## Falha observada

Na captura do proprietário, a equipe contou Llama e Qwen como sucesso, mas apresentou o aviso local “A resposta do modelo veio em formato incompleto ou inválido” como contribuição e resposta final. O parser antigo convertia JSON inválido em um texto de orientação; a equipe confundia esse texto produzido pelo programa com uma resposta utilizável do modelo. O Mistral excedeu o prazo e o Qwen de 27B foi adiado, sem consulta nessa rodada.

A frase **“me diga do que você é capaz”** também não correspondia ao reconhecimento local de capacidades, provocando uma consulta desnecessária à equipe.

## Mudanças

- A frase da captura e variações completas de “do que você é capaz” agora recebem a descrição local dos recursos. Negação, citação, condições, qualificadores e pedidos compostos continuam no fluxo normal, sem descartar parte do pedido.
- Conversa comum e perguntas para completar dados solicitam texto simples. JSON é solicitado somente para propor uma ação. As validações, o consenso da equipe e a confirmação aplicável permanecem obrigatórios; texto simples não executa ferramentas.
- O parser oferece validação estrita para os caminhos de conversa. JSON cortado, envelope inválido, campos indevidos ou ação proibida geram falha de conteúdo, sem repetir o corpo retornado pelo modelo. Chamadas legadas conservam o contrato anterior.
- Participantes com formato inválido não contam como sucesso, não geram contribuição parcial e não votam no consenso. Uma síntese inválida conserva a contribuição válida anterior e não prepara ação. O relatório passa a contar **conteúdo válido**.
- A resposta é interpretada em memória antes de redigir seus campos. Isso evita que a redação de credenciais corrompa aspas escapadas de um JSON válido. Só o resultado redigido é cortado, apresentado ou registrado.
- A conversa individual também rejeita conteúdo inválido sem gravar o aviso local como fala da IA e sem repetir a consulta.
- Na próxima consulta, um filtro em memória exclui somente avisos locais antigos exatamente reconhecíveis e relatórios cooperativos cujo texto selecionado era um desses avisos. Registros persistidos, mensagens do proprietário, respostas reais, explicações técnicas e relatórios paralelos com conteúdo útil permanecem preservados.
- Uma resposta que declara `done_reason=length` é classificada como cortada pelo limite de saída. Não é anunciada como completa nem repetida automaticamente. Se o servidor não confirmou `done=true`, continua prevalecendo a classificação de geração sem conclusão confirmada.
- A bateria explícita dos modelos também valida o conteúdo e mostra o tempo de cada consulta quando disponível.

## Conferência no Windows

Extraia o pacote completo em Downloads, fora da instalação. Feche uma preparação anterior ainda aberta e execute **`INSTALAR_E_INICIAR.bat`**. O fluxo existente confere o manifesto e cria backup das fontes; configuração, dados, histórico, modelos e rede são preservados.

Depois diga **“me diga do que você é capaz”** por texto ou áudio. A resposta deve descrever os recursos locais, sem progresso de consulta aos modelos. Para uma conversa que realmente precise de IA, envie o pedido normalmente; formato inválido deve aparecer como falha, nunca como contribuição válida.

O teste individual executado pelo proprietário confirmou respostas de Mistral, Llama e Qwen de 4B. O modelo `qwen3.8:27b` foi adiado por recursos: seus pesos ocupam 16,52 GiB, acima dos 15,96 GiB de RAM física informados, antes da reserva e da memória de execução. Viabilizar esse arquivo exige outro dimensionamento; esta revisão não remove a proteção nem substitui a tag. A preferência entre uma quantização menor local, execução remota e uma máquina com mais RAM deve ser definida pelo proprietário.

O Mistral respondeu no teste individual, mas o timeout observado na equipe permanece uma observação distinta. Texto simples reduz a exigência de formato; isso não comprova recuperação de desempenho. A sessão não tem um dispositivo Desktop Commander conectado para medir a execução diretamente no computador.

## Validação e limites

As regressões reproduzem o aviso local contado como sucesso, JSON incompleto, ação proibida, síntese inválida, resposta cortada, redação de credenciais fictícias e a pergunta exata da captura. A integração verifica ausência de consulta para a descrição de capacidades e ausência de histórico falso após erro individual. Não há chamadas reais a modelos, Telegram ou ações Windows nos testes.

Esta revisão não aumenta indiscriminadamente timeouts ou o limite de tokens, não baixa modelos e não anuncia que os demais modelos funcionam por estarem no catálogo. Falhas de prazo ou conclusão incerta continuam interrompendo novos envios; não há fallback ou repetição automática. Resultados da suíte e da matriz Windows/Linux acompanham o PR da entrega.

## Reversão

Encerre somente o assistente e o preparador e restaure os arquivos correspondentes ao `manifesto_reversao.json` do backup em `backups_codigo\implantacao_<identificador>`, conferindo hashes e preservando alterações posteriores. O [guia de instalação](GUIA_INSTALACAO_AUTONOMA.md) detalha os caminhos. O filtro de contexto não grava alterações no histórico e não exige migração de JSON.
