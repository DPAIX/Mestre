# v2.5.1 — compatibilidade dos hábitos e instalação em pasta já utilizada

## Problemas reproduzidos

A validação introduzida na v2.5.0 exigia inteiros não negativos para `valor` e `meta` de todos os hábitos. O próprio `dados_iniciais/gestao_vida.json` distribuído contém `Pausa_Mental_Foco` com rótulos textuais. Horas de sono e duração de exercício também podem ser fracionárias. Essa regra recusava dados compatíveis e bloqueava status, diagnóstico, água, finanças e melhorias com a mensagem genérica de estrutura inválida.

A causa foi reproduzida com a fixture genérica do pacote, sem ler dados do usuário. A validação do código estava errada; isso não demonstra corrupção do arquivo de uso.

O teste `test_imports_reais_gravam_somente_no_destino_externo` verificava se uma fixture existia na pasta original das fontes depois do subprocesso. Se o arquivo já estivesse presente, falhava mesmo sem nenhuma escrita nova. Foi reproduzido o mesmo `AssertionError: True is not false` em cópia temporária, com a fixture anterior intacta.

## Correções

- `nucleo.py`: inteiros continuam obrigatórios somente nos contadores `Agua_Copos` e `Pomodoros_Hoje`. Hábitos textuais, fracionários e campos desconhecidos são preservados. A leitura não converte nem grava esses hábitos. Números JSON não finitos e contêineres incompatíveis continuam recusados.
- `nucleo.py`: erros apontam o campo conhecido do esquema, como `financeiro.saldo`, sem incluir seu valor. Para nomes personalizados, a mensagem usa `*`. A meta de água numérica em string é convertida apenas no retorno de `registrar_agua`, para compatibilidade com o formato Telegram; a meta salva permanece original.
- `testes/test_caminhos_instalacao.py`: os imports reais passam a executar em cópia temporária somente dos `.py`, com Python isolado (`-I -B`). Compara-se a árvore antes/depois, e a gravação externa segue obrigatória. `.env`, dados, ambientes virtuais e symlinks da instalação não são copiados. A fixture antiga da instalação não é lida ou apagada pelo teste.
- `testes/test_vida_legada.py`: regressões usando o exemplo completo distribuído, hábitos mistos, operações locais, autoanálise, diagnóstico, backup/CSV/notebook e preservação byte a byte do estado. O módulo entra na exportação permitida do contexto.
- Banner, painel e documentação indicam v2.5.1. Os recursos da equipe de modelos, confirmação de ações e redirecionamento permanecem disponíveis.

## Validação

Baseline: 364 testes Python e compilação aprovados antes das mudanças. As novas regressões reproduziram o erro de hábitos e o falso positivo da instalação. Após as correções, os 373 testes Python passaram localmente em 3.11 e 3.12 e as 56 verificações JavaScript passaram. A matriz CI Windows/Linux em Python 3.11, 3.12 e 3.14 é conferida e seu resultado registrado no PR.

Também foram verificados compileall, sintaxe JavaScript e 22 módulos sem globais indefinidos. Os testes de instalação confirmam a criação no destino externo e detectam criação/sobrescrita indevida na cópia temporária das fontes. As operações locais usam somente JSONs fictícios, diretórios temporários e integração simulada quando necessário; nenhuma geração real, ação do Windows ou chamada paga foi executada.

## Atualizar e validar no PC

1. Encerre o assistente e atualize o pacote completo na raiz `C:\Users\Mestre\Documents\GitHub\Mestre`. Preserve `.env` e dados em `F:\MeuControlePC_v2`, incluindo `gestao_vida.json`. Não substitua esses dados por exemplos e não exclua a fixture antiga para fazer o teste passar.
2. Execute os testes da pasta atualizada: `python -m unittest discover -s testes -v` e `python -m compileall -q .`, usando o Python do ambiente do assistente. São esperados 373 testes nesta versão; uma suíte de 322 corresponde a fontes de testes anteriores.
3. Inicie `iniciar_redirecionado.bat`, confirme v2.5.1 em `/start`, consulte `/status` e `/autoanalise`. O estado textual de foco e as horas fracionárias não devem gerar erro de estrutura. Outros problemas locais reais continuam sendo informados; essa correção não ignora JSON inválido.
4. Opcionalmente solicite `/melhorar` e confirme a manutenção de arquivos locais. Não é necessário executar essa ação para instalar a correção do código.

## Ollama e erros externos

As capturas também mostraram falha de conexão ao serviço Ollama. Depois o catálogo voltou a listar os quatro modelos e a equipe foi ativada, confirmando a leitura do serviço naquele momento. A tentativa de geração seguinte excedeu o prazo nos quatro modelos. O catálogo não comprova geração nem memória suficiente para carregar o modelo de 27B junto com os demais. Timeout pode envolver fila, carregamento, memória ou serviço ocupado; as capturas não isolam essa causa.

Se `/modelos ollama` falhar, abra o Ollama no PC; se necessário, execute `ollama serve` em outro PowerShell. O serviço precisa usar o diretório com os modelos; nesta instalação foi informado `F:\Models`. Mantenha a janela do servidor aberta e fora do modo “Selecionar” do console. A correção não baixa modelos ou altera limites de memória automaticamente.

Quando o catálogo listar, envie novamente `/chat equipe on`: uma ativação que falhou antes da leitura do catálogo não ficou salva. Depois envie uma pergunta. Para isolar os timeouts mostrados, envie `/chat equipe off` e `/modelos testar llama3.2:latest`, confirmando o teste individual da tag local leve já listada. Se ela também expirar, confira `ollama ps` e o console do serviço no PC antes de tentar a equipe novamente. Consultar o catálogo não gera respostas; testar o modelo gera uma consulta explícita. Não houve aumento automático de timeout ou mudança silenciosa para consultas sequenciais.

Erros HTTP 401 de Gemini/OpenAI/Claude exigem credenciais/permissões válidas nessas contas. Eles não são corrigidos por backup, notebook ou remoção de pausas locais. Não compartilhe o `.env` para diagnosticá-los.

## Limites e reversão

Os dados do Windows do usuário não foram abertos, migrados ou reescritos para esta entrega. A validação foi reproduzida com o esquema genérico do próprio projeto. A validação real na instalação do usuário depende de atualizar e reiniciar as fontes.

Para reverter, encerre a v2.5.1 e restaure as fontes anteriores preservando os dados externos. A v2.5.0 volta a apresentar a regressão com hábitos textuais; não é necessário alterar o JSON para compatibilizá-lo com ela. O PR permanece em revisão, sem merge. O ZIP não inclui dados de uso nem credenciais; blobs de dados já rastreados no repositório são preservados sem leitura do conteúdo.
