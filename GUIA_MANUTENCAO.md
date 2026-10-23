# Atualizar e otimizar o assistente — v2.8.0

## No seu Windows

1. Encerre a janela do bot antigo. Copie o conteúdo da pasta interna do ZIP para a raiz de `C:\Users\Mestre\Documents\GitHub\Mestre`.
2. Abra **`atualizar_assistente.bat`** por duplo clique. Ele reutiliza a `.venv` existente em C: ou junto ao `.env` em F:, instala/confere as bibliotecas da aplicação, voz local e Google Agenda, executa `pip check`, confere os pesos do Whisper, limpa bytecode gerado e inicia o assistente.
3. Aguarde a conclusão e envie texto ou áudio normalmente. Não são necessários comandos no Telegram para ativar a conversa/equipe. O Startup que já foi configurado continua valendo nos próximos logons.

O fluxo usa `F:\MeuControlePC_v2\.env` e `F:\MeuControlePC_v2\dados`. Ele não solicita credenciais novamente, não copia o `.env` para o código e não registra ou remove Startup. Na primeira instalação, use `ativar_assistente_automatico.bat` para preparar também o início ao logar.

A manutenção precisa de internet para obter bibliotecas ausentes. O cache de voz preparado é reaproveitado; pesos ausentes exigem o download público inicial. Pacotes instalados são verificados por `pip check`; isso confere dependências, não autenticação de contas ou funcionamento real das APIs. As bibliotecas Google permitem o conector já existente, mas não substituem a autorização OAuth da agenda.

Se o bot estiver aberto, a manutenção para antes do pip e orienta encerrá-lo. Ela não mata processos. Cada etapa tem prazo e uma falha preserva os arquivos pessoais; não há compra de créditos ou tentativas de geração para testar a instalação.

## Velocidade e uso dos modelos

- Cumprimentos, agradecimentos e testes simples como `teste123?` recebem confirmação local de recebimento, sem esperar pela equipe. Isso não comprova geração de IA. Pedidos como “Olá, explique...” e “teste os modelos” seguem o fluxo completo, sem perder a tarefa.
- Leituras locais de rotina/saldo/status continuam usando os registros reais. O status não espera 100 ms por consulta para medir CPU; usa amostras agregadas entre requisições. A primeira leitura de CPU é N/D. O painel reutiliza a leitura de vida e do catálogo RoboTask dentro da mesma resposta, mantendo os dados atualizados.
- A equipe CPU prioriza os pesos menores declarados no catálogo. Todas as tags continuam selecionadas e aparecem no resultado. Metadados CPU podem ser reutilizados por cinco segundos; uma consulta explícita ao catálogo continua fresca.
- Se o peso de um modelo exceder a RAM física menos 512 MiB, a cooperação CPU o adia com motivo explícito antes de pedir geração. É uma estimativa conservadora, não uma medição da memória exata de inferência. Sem metadados/RAM conhecidos, a tentativa normal continua. O perfil padrão e a escolha individual explícita não recebem esse adiamento automático.
- Um participante adiado ou que falhou não conta como concordância. Preparar uma ação por IA ainda exige o consenso já validado e confirmação. Os pedidos locais reconhecidos seguem disponíveis.

No diagnóstico enviado, o 27B tinha 16,52 GiB em disco, acima da RAM total de 15,96 GiB. Nesse perfil CPU, a verificação evita esperar por sua tentativa a cada pergunta. Ela não torna o modelo menor nem garante que os demais responderão: a latência real depende de CPU, memória, contexto e serviço Ollama. Não há encerramento do Ollama, alteração de driver, ampliação de memória virtual ou download de outros modelos de conversa.

## Limpeza e recuperação

A limpeza percorre somente a raiz das fontes, `testes` e seus `__pycache__`, com limite de entradas. Remove bytecode reconhecido gerado por Python; bytecode solto exige fonte correspondente. Não segue symlinks/junctions nem faz exclusão recursiva. Arquivos desconhecidos são preservados. O relatório informa a quantidade e os bytes efetivamente liberados, sem mostrar conteúdo pessoal.

Fontes, documentação, testes, `.venv`, `.env`, dados, modelos, ZIPs e backups são necessários à operação ou recuperação e ficam preservados. Caches removidos podem reaparecer durante o uso normal do Python. A limpeza reduz arquivos gerados; não é apresentada como aceleração de inferência.

Para reverter o código, encerre o bot, restaure todas as fontes v2.7.1 e abra `iniciar_redirecionado.bat`, mantendo configuração, dados e modelos. Não há necessidade de restaurar bytecode. Para desativar o início ao logar, use `desabilitar_inicio_com_windows.bat`.

Os testes automatizados e a instalação de bibliotecas foram executados em ambiente Linux isolado. O duplo clique, a GUI, as credenciais, o áudio real e o tempo de geração ainda precisam ser validados no seu Windows.
