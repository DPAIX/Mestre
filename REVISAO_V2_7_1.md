# Revisão v2.7.1 — equipe CPU e conversa sem ação

## Causa e resultado

A instalação v2.7.0 concluiu no Windows e a equipe automática consultou os quatro modelos. Na imagem enviada, somente Llama 3.2 respondeu; os outros excederam o prazo. A auditoria reproduziu um erro concreto: `multi_ia.py` aplicava o perfil CPU (contexto 1024, saída 128, GPU zero) e depois o modo cooperativo o sobrescrevia com contexto 4096 e saída 384. Isso aumentava a carga apesar da indicação de perfil preservado. A correção mantém os mesmos limites do CPU individual.

Essa evidência não demonstra a causa única dos timeouts. No diagnóstico anterior o modelo 27B tinha 16,52 GiB em disco, para 15,96 GiB de RAM total e cerca de 9 GiB livres. Tamanho em disco não determina exatamente a memória de inferência; paginação, processamento e outros recursos ainda podem impedir uma resposta dentro do prazo. Não se declara que os quatro modelos já funcionam no PC.

## Alterações

- `multi_ia.py`: preserva as opções CPU também em participantes e síntese. Cooperação solicita `think=false` para reservar a saída curta à contribuição textual. O modo individual e as opções cooperativas do perfil padrão permanecem com seus contratos anteriores. Não há retry, fallback pago, mudança no `.env` ou encerramento de processos.
- O histórico enviado somente à cooperação CPU recebe orçamento de até 600 caracteres e espaço restante de 2400 caracteres junto ao pedido/sistema. Instruções, prefixos e resumos CPU são mais curtos em `interpretacao_natural.py`, `conversa_equipe.py` e `servicos_chat.py`. O histórico persistido é preservado, e o limitador não corta novamente a mensagem atual. Caracteres são uma heurística, não a contagem de tokens: pedidos longos e Unicode ainda podem exceder o contexto do modelo.
- Testes e cumprimentos recebem orientação de conversa direta. O parser conserva o texto de envelopes inertes com ação ausente/nula/nenhuma e campos ausentes/nulos/vazios. Essa tolerância nunca prepara uma ação. Planos reais continuam com validação estrita de ação/campos, consenso e confirmação. JSON malformado informa falha de formato, sem presumir pedido de ação. Sem a resposta bruta do modelo na imagem, não é possível afirmar qual variação ocorreu nela.
- Timeout do Ollama informa prazo esgotado, sem apresentar isso como comprovação de falha de rede ou cancelamento da geração no servidor. Todos os modelos continuam selecionados, com uma consulta por participante e uma síntese adicional quando aplicável; os participantes que falharem permanecem identificados.

## Verificação

Baseline v2.7.0: 539 testes Python e compilação aprovados antes das alterações. Resultado final local: 559 testes Python, 59 verificações JavaScript, compilação e auditoria dos 27 módulos principais aprovados. As 20 novas regressões cobrem as quatro tags no CPU, comparação com individual, preservação de histórico/pedido, ausência de retry/fallback pago, conversa inerte, JSON inválido, síntese e consenso. O resultado da matriz Windows/Linux consta no PR.

As chamadas são simuladas, sem `.env` ou dados reais, inferência, Telegram, microfone ou ações Windows. Os testes reproduzem a sobrescrita de opções e validam o novo contrato; não medem a velocidade real dos modelos nem comprovam que o 27B cabe na memória.

## Atualizar no Windows e reverter

1. Encerre o bot v2.7.0 e atualize todos os arquivos de código na raiz de `C:\Users\Mestre\Documents\GitHub\Mestre`.
2. Preserve `.venv`, `F:\MeuControlePC_v2\.env`, `F:\MeuControlePC_v2\dados`, os modelos Ollama e o cache de voz. Abra `iniciar_redirecionado.bat` para executar a versão atualizada. A preparação automática já concluída e o Startup não precisam ser refeitos.
3. Envie uma mensagem curta por texto. Confira a versão 2.7.1 no console e o relatório de participação. A equipe permanece automática; não é necessário `/start` ou `/chat equipe on`. Uma resposta válida do Llama deve continuar útil mesmo se outro participante falhar. Se o 27B expirar, o relatório deve mostrar essa limitação, sem anunciar sucesso dos quatro.

Para uma primeira instalação, o fluxo `ativar_assistente_automatico.bat` continua disponível e prepara voz/início automático. As mudanças desta revisão não reiniciam Ollama, alteram drivers ou ampliam memória virtual.

Para reverter, encerre o bot, restaure todas as fontes v2.7.0 e abra o iniciador existente, mantendo os mesmos dados/configuração/pesos. O início automático pode ser desativado com `desabilitar_inicio_com_windows.bat`; isso não remove dados nem encerra o bot em execução.
