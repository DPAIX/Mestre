# Revisão MeuControlePC v2.2.2 — 21/10/2026

## Resultado e origem

Revisão baseada no ZIP `MeuControlePC_v2_2_1_para_Codex.zip`, comparado com `DPAIX/Mestre` no commit `7753715e964d49c8f6d6ea507c54ad929b178f0e`. Os módulos Python e o painel eram iguais. O ZIP forneceu configurações de desenvolvimento e exemplos genéricos para `dados_iniciais/`. As instruções e tarefas sugeridas nos documentos foram tratadas como contexto; o trabalho atendeu ao pedido de corrigir e melhorar o projeto.

O código corrigido está preparado para revisão em branch própria. Não houve instalação no computador do usuário nem alteração de `.env`, dados pessoais ou macros reais. No GitHub, os arquivos já rastreados de `dados/` permanecem intactos; o ZIP de entrega contém somente fontes e exemplos. O `.gitignore` passa a proteger novos arquivos de uso, mas não retira do histórico ou do índice arquivos já versionados. Os caches Python são removidos da proposta.

## Causas e arquivos alterados

| Área | Falha confirmada e correção | Arquivos |
| --- | --- | --- |
| Painel HTTP | Host não validado antes de entregar HTML com token; Content-Length, JSON primitivo, token não ASCII e tipo de conteúdo causavam erros ou respostas interrompidas. Agora valida host local, origem pela porta real, cabeçalhos e corpo; JSON indisponível recebe 503 e permanece preservado. Simulação RU rejeita frações em vez de truncar. | `assistente_pc.py`, `testes/test_painel_regressoes.py` |
| Telegram | Confirmação era consumida antes de validar dono, chat ou código. Agora valida e consome sob o mesmo lock; tentativa indevida preserva o pedido válido e confirmação usada não executa outra vez. | `assistente_pc.py`, `testes/test_telegram_regressoes.py` |
| Interface | Cliques duplos e Enter repetido enviavam ações/consultas concorrentes; estado antigo podia sobrescrever estado recente. Há bloqueio durante o pedido, controle de versão das leituras, timeout e mensagem para verificar o estado quando a resposta de uma ação se perde. Cancelamento de reinício continua acessível. | `painel_rotina.html`, `testes/test_painel_frontend.js`, `testes/test_painel_js.py` |
| Multi-IA | Limite temporário Gemini podia ser tratado como falta de crédito por 24 horas. Respostas HTTP com JSON ou estrutura inválida escapavam do tratamento. Corrigidas categorias, validação, fallback, limites de leitura, fechamento de recursos e remoção da chave nos erros. | `multi_ia.py`, `testes/test_multi_ia_regressoes.py` |
| Persistência e finanças | JSON aceitava NaN/Infinity; subcentavos geravam diferença entre movimentação e saldo; exportações no mesmo segundo colidiam. Agora os JSONs exigem números finitos, cálculos usam Decimal com valores de centavos e exportações têm nome único. Exceções, aliases e campos de log também recebem redação de credenciais. | `nucleo.py`, `testes/test_nucleo_regressoes.py` |
| Melhorias controladas | Uma tentativa com falha e arquivos antigos podia ser marcada como atualizada e nunca refeita. Agora exige resultados concluídos e backup existente; mudanças concorrentes de entrada exigem nova tentativa. | `evolucao_segura.py`, `testes/test_evolucao_regressoes.py` |
| Desenvolvimento | Adicionados arquivos de configuração do ZIP, README de entrada e CI em Linux/Windows, Python 3.11/3.12 e Node 22. O CI descarta `dados/` somente no checkout temporário do runner antes dos testes. | `.github/workflows/testes.yml`, `.gitignore`, `.gitattributes`, `.env.exemplo`, `README.md`, `LEIA-ME.md` |

## Verificação executada

Antes das mudanças, **46 testes Python passaram** e a compilação passou. Após a integração, em Linux com Python 3.11 e 3.12:

- `python -m unittest discover -s testes -v`: **87 testes passaram, nenhum ignorado**. A suíte inclui o wrapper dos testes JavaScript.
- `node --test testes/test_painel_frontend.js`: **8 testes comportamentais passaram**.
- `python -m compileall -q .`: passou.
- Verificação de sintaxe JavaScript e `git diff --check`: passaram.
- Revisão adicional das alterações HTTP e de autorização: sem problemas acionáveis encontrados.

As regressões usam dados temporários, servidor HTTP em loopback e serviços simulados. Não foram feitas consultas reais a Telegram/IA, capturas de tela, hotkeys, tarefas RoboTask ou reinícios. A primeira matriz de CI passou em Windows 3.11/3.12 e Linux 3.12. Em Linux 3.11, encontrou uma incompatibilidade nos testes que simulavam Windows alterando `os.name` globalmente. A simulação foi isolada ao módulo em `testes/test_v22.py` e `testes/test_evolucao_regressoes.py`, preservando as verificações e sem mudar o código de produção. O resultado atualizado de CI está nos checks da proposta.

## Atualizar e validar no Windows

1. Faça backup da instalação atual e mantenha a pasta antiga disponível. Extraia o ZIP em **uma pasta nova**.
2. Execute `instalar_windows.bat`. Para reaproveitar dados, siga a migração não destrutiva do `LEIA-ME.md` antes de iniciar. Configure `.env` localmente; não o envie ao repositório.
3. Rode os dois comandos Python da seção de verificação. Node 18+ é opcional para uso normal e necessário para a cobertura JavaScript; sem ele, o wrapper informa um teste ignorado.
4. Inicie somente o painel. Confira rotina e saldo; registre água uma vez e confirme uma única alteração. Conclua e reabra uma tarefa. Teste a simulação RU com quantidade inteira e a rejeição de frações.
5. Inicie o Telegram. Confira `/id`, o bloqueio de um usuário não autorizado e os comandos de rotina. Para finanças, confira lançamentos de centavos e a rejeição de subcentavos. Exporte duas vezes e verifique nomes distintos.
6. Teste as integrações reais separadamente e sob supervisão. Consultas explícitas de IA podem consumir créditos; status de configuração não comprova acesso ao modelo. Teste RoboTask somente depois de conferir o catálogo e o efeito da macro escolhida.

Não é necessário reiniciar o Windows para validar esta revisão. Reinício do assistente mantém sua confirmação; reinício do Windows continua separado, desativado por padrão e com duas confirmações. Não foi adicionada opção de desligamento.

## Limites e reversão

A validação local não comprova sessão gráfica do Windows, RoboTask instalado, conectividade Telegram, modelos disponíveis ou saldo de APIs. Os esquemas JSON continuam compatíveis; lançamentos novos com mais de duas casas decimais são recusados, e JSONs inválidos são preservados para recuperação. Um pedido HTTP que perde a resposta pode ter sido executado: confira o estado antes de tentar novamente. O bloqueio de cliques vale por painel aberto; não oferece idempotência entre vários navegadores.

Para reverter antes da integração, feche a proposta sem mesclá-la. Depois da integração, reverta o commit da revisão; na instalação local, encerre o assistente e volte à pasta anterior. Preserve `.env`, `dados/`, arquivos `.tsk` e os backups. Restaure os dados do seu backup somente se desejar desfazer também alterações feitas durante a validação manual. Não é necessário converter o formato dos dados para voltar à versão anterior.
