# MeuControlePC v2.4.1 — execução redirecionada e resultados do painel

## Problema e resultado

O código e a configuração estavam ligados à mesma pasta. Iniciar uma cópia antiga continuava respondendo como v2.3.2, e mover só as fontes não fazia os configuradores encontrarem o `.env` correto. O redirecionador passa a executar `C:\Users\Mestre\Documents\GitHub\Mestre` usando `F:\MeuControlePC_v2\.env` e `F:\MeuControlePC_v2\dados`, sem copiar credenciais para o repositório.

O usuário também apontou que a proteção de duplo clique existia apenas em cada painel aberto e que uma resposta HTTP perdida deixava o resultado incerto. O servidor agora guarda o resultado de cada chave de intenção durante a sessão; o painel consulta esse resultado após uma falha de transporte, sem reenviar o POST. Uma versão de snapshot impede que duas abas atuais executem alterações com o mesmo estado antigo.

## Alterações

- `caminhos_instalacao.py`, `nucleo.py`: seletores de processo para configuração e dados, `BASE` preservada como fontes, erro em vez de fallback quando o `.env` externo não existe e medição de espaço no destino dos dados. Sem seletores, a instalação convencional mantém os caminhos anteriores. O `.env` não redefine os seletores depois dos imports.
- `redirecionar_assistente.py` e `iniciar_redirecionado.bat`: caminhos solicitados como padrão, validação da árvore atualizada e caminhos externos, reaproveitamento da `.venv`, modos de início/configuração/diagnóstico e `--verificar` somente por metadados. Subprocessos usam lista de argumentos e `shell=False`; o bootstrap não lê o `.env`, não importa a aplicação e não migra/apaga dados.
- `configurar_telegram.py`, `configurar_ia_local.py`, `autorizar_google.py`, `agenda_google.py`, `servicos_chat.py`: leitura e gravação dinâmicas no mesmo `.env` selecionado. Credenciais OAuth relativas acompanham a pasta desse arquivo. Alterações continuam limitadas às chaves de cada configurador e são atômicas.
- `startup_windows.py`: o atalho gerenciado preserva o redirecionamento no próximo login, incluindo o Python reaproveitado. O reinício do assistente já herda os seletores do processo. Caminhos com percentuais são escapados e delayed expansion fica desligada.
- `idempotencia_painel.py`, `assistente_pc.py`: reserva atômica por chave e hash de corpo, conflito quando a chave representa outro pedido ou o snapshot ficou antigo, consulta autenticada de resultado e finalização antes da escrita no socket. Perder a conexão não troca um sucesso já retido por outro resultado. Cancelamento de reinício do Windows mantém sua via prioritária.
- `painel_rotina.html`: uma chave por intenção, versão obtida de leitura válida, recuperação limitada por GET após timeout/HTTP 202, atualização de estado após conflito e retenção em memória de pedidos incertos. Um novo clique no mesmo pedido incerto consulta o resultado, sem criar outra ação.
- `nucleo.py`, `servicos_chat.py`, `colaboracao_chats.py`: a auditoria reproduziu com fixtures um segredo Exa/OAuth nomeado no meio da mensagem que passava pela redação por prefixos. Agora campos sensíveis inline e em JSON são saneados antes da IA, resposta, histórico, logs e exportação. Capturas PNG validadas continuam no caminho binário separado.
- `evolucao_segura.py`, exportação de contexto, `.gitignore` e guias: os módulos novos entram na auditoria/allowlist de fontes, sem incluir configuração, histórico ou dados de uso. Arquivos OAuth comuns também ficam ignorados.

## Verificação

Baseline v2.4.0: 264 testes Python e compilação aprovados antes das mudanças. Versão final: 322 testes Python e 48 testes JavaScript; compilação, sintaxe, 80 IDs únicos/69 referências do painel e integridade do pacote verificados na entrega. Python 3.11, 3.12 e 3.14 são verificados localmente; a matriz Windows/Linux e seu resultado ficam na descrição do PR.

Os novos testes usam caminhos e dados temporários, subprocesso Python para confirmar a separação real entre imports/fontes e destino dos dados, HTTP loopback concorrente, perda simulada de socket, expiração/replay e mocks de integrações. A auditoria estática cobriu 21 módulos sem nomes globais indefinidos. Os cinco módulos de chats/equipe/Ollama/rotina mantêm números finitos, gravação atômica e isolamento por contexto; autorização/loopback também têm regressões.

Não foram acessados os discos C:/F: do usuário, credenciais reais, modelos reais, navegador OAuth, Telegram ou ações gráficas do Windows. O `.bat` precisa ser executado na máquina do usuário para a validação operacional. O código não recupera créditos de contas nem configura a sessão do Manus automaticamente.

## Limites e compatibilidade

A retenção HTTP fica somente na memória do processo, por 900 segundos após conclusão, até 256 resultados normais e 8 prioritários, com orçamento de memória de 64 MB mais a reserva pequena de cancelamento. Limites são verificados antes da execução; pedidos em andamento não são removidos. Reiniciar o processo ou expirar o resultado encerra essa garantia. Resultado desconhecido exige conferir o estado; não há repetição automática do POST.

A versão acompanha ações HTTP deste painel. Ela não é um contador global de alterações feitas pelo Telegram. Clientes HTTP antigos sem os dois cabeçalhos continuam aceitos e invalidam os snapshots dos clientes novos, mas não ganham execução única por chave. A interface atual exige um snapshot válido e envia ambos os cabeçalhos ao servidor atual.

F: é o destino ativo do redirecionador. Se existem dados tanto em C: quanto em F:, C: fica intacto e não é mesclado. Se `F:\MeuControlePC_v2\dados` ainda não existe e há uma pasta de dados junto às fontes, o início é bloqueado até selecionar/copiar os dados externos existentes. Isso evita trocar uma rotina já preenchida por exemplos vazios.

Compartilhar código pelo GitHub continua pelo fluxo normal do usuário; o redirecionador não executa pull, push, merge ou publicação automática. Os blobs de dados anteriormente rastreados no repositório foram preservados sem leitura do conteúdo; o ZIP não contém dados de uso ou credenciais. O PR permanece em revisão.

Google Calendar continua somente leitura. Agendamentos naturais continuam na rotina local. As confirmações de alterações, ações do PC e reinício do Windows são preservadas.

## Validar no Windows e reverter

Siga [GUIA_REDIRECIONAMENTO.md](GUIA_REDIRECIONAMENTO.md). Atualize as fontes na raiz da pasta GitHub em C:, preserve o `.env` e dados de F:, encerre a instalação antiga e execute `iniciar_redirecionado.bat --verificar`. Depois inicie sem argumentos e confirme `/start` com v2.4.1. Liste o catálogo Ollama e teste uma tag presente. Verifique uma leitura e uma alteração pequena com confirmação.

Para conferir o painel em duas abas, carregue ambas, registre uma ação na primeira e tente uma ação na segunda antes de atualizar. A segunda deve receber conflito, atualizar sua leitura e solicitar revisão, sem executar o pedido antigo. Os testes de perda de resposta cobrem a recuperação por consulta.

Para reverter, encerre a v2.4.1, desative o atalho gerenciado se ativado e inicie a pasta anterior v2.4.0 com uma cópia preservada dos dados/configuração. Não há mudança de esquema dos JSONs nem remoção de arquivos. O cache HTTP termina com o processo; ele não é gravado nos dados pessoais.
