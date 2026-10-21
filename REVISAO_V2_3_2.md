# MeuControlePC v2.3.2 — Mistral, Llama 3.2 e Qwen

## Causa e mudança

A integração anterior já encaminhava tags Ollama arbitrárias, mas exigia preparar cada conversa manualmente e não oferecia capacidades/contexto nem teste individual. O usuário mostrou Mistral, um Llama 3.2 sem tag completa visível e Qwen `qwen3.8:27b` no Claude Code com aviso de contexto presumido de 200k. O launcher externo não confirma disponibilidade no Ollama, e contexto presumido não é capacidade validada.

Esta versão identifica famílias no catálogo real, prepara até quatro conversas por operação e consulta metadados sem inferência. O teste explícito envia uma única pergunta curta ao modelo selecionado, sem histórico nem fallback. Todas as tags continuam vindo do serviço Ollama do PC: modelos não são instalados, baixados, renomeados ou anunciados disponíveis por causa dos prints.

## Arquivos

- `multi_ia.py`: catálogo com família/uso sugerido e ponte para metadados `/api/show`.
- `configurar_ia_local.py`: projeção limitada de metadados e CLI `--detalhes NOME`. Não retorna template, prompt de sistema, Modelfile nem resposta bruta; mantém bloqueio de proxy/redirecionamento e URL loopback.
- `colaboracao_chats.py`: preparação atômica e idempotente de conversas por modelo, sem migração destrutiva nem duplicação em chamadas repetidas.
- `servicos_chat.py`: ações de preparação e teste individual; confirmação antes da geração, catálogo validado, uma chamada por teste.
- `assistente_pc.py`: `/modelos preparar A,B`, `/modelos detalhes NOME`, `/modelos testar NOME` com confirmação de uso único; GET autenticado `/api/modelo_ollama?nome=TAG`.
- `painel_rotina.html`: família/uso, criação de conversas marcadas, detalhes e teste explícito. Mantém autenticação de requisições, limites e renderização como texto.
- Testes Python/JavaScript e guias de uso/atualização.

## Validação e limites

Baseline anterior: 199 testes Python aprovados e compilação válida. Nova suíte: 211 testes Python e 25 testes JavaScript aprovados, além de compilação e sintaxe do painel. A matriz Windows/Linux é registrada no PR. Testes usam arquivos temporários, mocks e HTTP loopback com protocolo Ollama simulado, incluindo Mistral/Llama/Qwen, contexto declarado, isolamento de históricos, preparação idempotente/atômica e confirmação de geração. Não houve inferência em modelos reais, atualização do Claude Code, instalação de programas, acesso a contas ou ações Windows durante a implementação.

O máximo de contexto declarado pelo modelo não indica janela ativa, memória disponível ou desempenho. Modelos grandes como 27B podem exigir recursos além dos disponíveis; o teste mantém os limites de espera da integração anterior. A disponibilidade de ferramentas no Ollama não prova que todas as funções do Claude Code sejam compatíveis. Esta versão não altera a configuração nem promete remover o aviso desse cliente externo.

Manus, exportação de contexto, equipe e propostas revisáveis da versão anterior continuam disponíveis. Nenhuma resposta de IA é executada como código pelo assistente.

## Validar no Windows e reverter

Extraia em pasta nova, execute o instalador do projeto e siga o LEIA-ME para manter dados/credenciais locais. Use `configurar_ia_local.bat --listar`, configure um nome presente com `--modelo NOME`, encerre o processo antigo e inicie a nova pasta. No painel, atualize modelos, prepare conversas, consulte detalhes e confirme um teste por modelo. Para o Llama, use a tag exibida na lista, pois o print não mostra o nome completo.

Se precisar reverter, encerre a nova versão e inicie a pasta anterior v2.3.1, mantendo uma cópia dos dados. As conversas adicionais usam o mesmo esquema; não é preciso apagar modelos, histórico nem credenciais. O procedimento não depende de modificar a instalação do Ollama ou do Claude Code.
