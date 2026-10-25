# Revisão v2.10.0 — assistente integrado e Gemini

O pedido era tornar utilizáveis as integrações e a configuração do assistente, incluindo os agentes gerenciados Gemini indicados nos links. A revisão anterior já tinha lançadores de agentes e 9Router/9Remote, mas faltavam escolhas 9Router por conversa, operações completas de memória, acompanhamento dos recursos e um cliente Gemini Interactions/Managed Agents integrado às interfaces.

## Alterações

- `gemini_interactions.py` implementa o protocolo pelo SDK Google: modelos com `store=False`; tarefas remotas com `background/store=True`; consulta, cancelamento, exclusão e perfis personalizados. As respostas são texto/propostas, sem execução local. O transporte limita cada operação a uma saída HTTP, inclusive quando o SDK tenta repetir uma criação recusada ou sem resposta.
- `servicos_gemini.py` mantém tarefas/perfis isolados por proprietário, tópico e conversa, com gravação atômica, limite por conversa, validação e ID de operação registrado antes do envio. Preserva resultado incerto em timeout e exige consulta/decisão explícita; não repete a criação. Continuação e importação de resultado ficam disponíveis no painel.
- `assistente_pc.py` oferece rotas autenticadas, confirmação vinculada à conversa, comandos `/gemini` e `/integracoes`, exportação de memória e seleção `/chat gateway`. O painel inicia antes da preparação Ollama em segundo plano.
- `painel_rotina.html` reúne estado das integrações, tarefas/perfis Gemini, memória com exclusão/exportação, seleção/teste de modelo 9Router por conversa e modelos/combos 9Router na equipe de propostas. Descarta respostas de confirmação de conversas antigas e renderiza conteúdo remoto como texto.
- `roteador_9router.py`, `multi_ia.py`, `servicos_chat.py`, `colaboracao_chats.py` e `equipe_ia.py` preservam o padrão global ao escolher um modelo/combinação por conversa. A equipe aceita participantes explícitos 9Router e guarda contribuições para revisão.
- `memoria_assistente.py` remove notas somente com confirmação, exporta Markdown e permite continuar a conversa quando um arquivo de memória inválido precisa ser preservado para reparo.
- `conversa_equipe.py` admite até 32 modelos na cooperação sequencial, mantém oito no paralelo e informa todos os participantes. Preserva limites CPU, orçamento, unanimidade para ações e tratamento de timeout sem repetir geração.
- `iniciar_servicos_locais.py` respeita a política de início do Ollama e não cria outro servidor quando a porta está ocupada ou a sondagem de porta é incerta.
- `startup_windows.py` inspeciona conflitos e oferece consolidação reversível do atalho legado exato; preserva aplicativos externos e restaura o atalho se o registro falhar.
- `configuracao_assistente.py`, `configurar_gemini.py`, `prontidao_assistente.py` e os novos `.bat` preparam dependências, voz, Node.js, contas, modelos, integrações e início gerenciado por etapas finitas. A presença de configuração é separada de uma conexão ou geração comprovada.
- `requirements.txt` atualiza `google-genai` para `>=2.9,<3`; CI instala esse SDK para testar o contrato HTTP com transporte fictício. Guia completo e notebook Colab sem resultados acompanham as fontes.

## Validação

A base v2.9.2 passou em 857 testes, com um teste específico Windows ignorado no Linux, antes das alterações. A nova versão usa testes Python, JavaScript do HTML real, HTTP loopback e o SDK Google real com HTTP simulado. São cobertos autenticação, confirmação, vínculo de conversa, criação única após timeout/429, continuação, cancelamento, importação de proposta, exclusão de memória, catálogo/override 9Router, porta Ollama ocupada e reversão de Startup. Não são executados comandos perigosos, macros, acesso remoto ou reinício do Windows.

Validação local final: **903 testes Python, sem falhas, com um teste Windows ignorado no Linux**, usando Python 3.12 e google-genai 2.33.0; **87 testes JavaScript aprovados**. A matriz Windows/Linux com Python 3.11, 3.12 e 3.14 fica nos checks da PR. Compilação Python e análise estática das 39 fontes de execução não apontaram nomes globais indefinidos. O notebook foi validado como JSON, células Python compiláveis e sem saídas/execuções. Nenhuma geração foi enviada a uma conta externa para estes testes.

## Limites e operação

Instalação e uso real no PC do proprietário continuam dependendo de suas contas, cota, modelos, permissões e pareamento. Colab Pro não garante acesso à Gemini API. Os 14 aplicativos de agentes são integrações interativas pelo lançador oficial; não há delegação automática irrestrita a esses CLIs. A implementação Managed Agents usa a API Google e um sandbox remoto, sem ferramentas do PC. 9Remote é preparado e aberto na interface oficial; o túnel exige pareamento e decisão local.

Não houve alteração de DNS, hosts, proxy, Firefox, firewall, adaptadores ou Tailscale. A atualização preserva a recuperação de rede observada. O ZIP não inclui `.env`, dados reais, credenciais, pesos ou o hosts enviado pelo usuário. As entradas privadas já existentes no Git são preservadas pela árvore-base, sem publicar seu conteúdo nesta revisão.

Veja [instalação, uso e reversão no Windows](GUIA_ASSISTENTE_INTEGRADO.md). Para reverter o código, pare bot/painel e restaure as fontes v2.9.2; preserve configuração/dados/pesos. Tarefas e perfis Google não desaparecem com a reversão local: acompanhe ou encerre-os pelo serviço. A configuração do início gerenciado possui backup próprio para o atalho legado, sem reativar aplicativos externos.
