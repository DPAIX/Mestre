> **v2.12.4:** se a preparação anterior parou em “Instância anterior” antes de copiar fontes, use o [pacote corrigido](REVISAO_V2_12_4.md). Feche o console da preparação antiga antes de abrir o pacote novo; Retomar na página antiga mantém o código antigo em memória.

# Instalação automática — MeuControlePC v2.12.4

Salve e extraia o ZIP diretamente em **F:\Instaladores**, fora da pasta instalada, e abra **INSTALAR_EM_F_COM_27B.bat**. O destino é **F:\MeuControlePC_v2\aplicativo**. O fluxo prepara as dependências, confere/importa os modelos e solicita o teste da versão leve antes de iniciar. Para atualizar sem repetir a preparação do 27B, use INSTALAR_E_INICIAR.bat. Os iniciadores recusam execução fora de F:; não escolhem C: como alternativa. Consulte [os caminhos e limites da revisão](REVISAO_V2_12_3.md).

Para atualizar uma preparação anterior ainda aberta, feche antes o console que mostra **Preparação automática: http://127.0.0.1:...**. A trava desse processo impede executar dois preparadores. Consulte a [correção v2.11.1](REVISAO_V2_11_1.md).

A janela local mostra o progresso e as pendências de conta. A preparação começa ao abrir o arquivo; **Retomar** repete a conferência depois que você concluir uma pendência. Não abra vários instaladores ao mesmo tempo.

## O que acontece automaticamente

1. O iniciador usa Python existente para bootstrap e cria/reaproveita uma venv em F:. Não instala pacotes no Python global nem chama winget com destino padrão em C:. Se um executável necessário estiver ausente, informa a pendência para instalação em F:.
2. O preparador identifica esta instalação do assistente. Se houver um bot anterior, só o encerra quando consegue comprovar o executável, os argumentos, o proprietário e a identidade do processo. Se não houver essa comprovação, mostra a pendência e aguarda o fechamento daquela janela.
3. Confere os hashes do pacote público, guarda as fontes que serão substituídas e atualiza a pasta de código. Configuração, dados, ambientes virtuais e modelos não entram nessa cópia.
4. Confere as bibliotecas, o ambiente e a voz local. Reaproveita uma instalação saudável; prepara os componentes faltantes quando necessário. A preparação inicial de voz e bibliotecas pode baixar arquivos e levar vários minutos.
5. Prepara Node.js e os componentes gerenciados 9Router/9Remote quando faltarem, solicita o início do 9Router e abre a interface do 9Remote para pareamento. O 9Remote 3.0.43 recebe a correção verificada para usar DNS nativo e limpar somente seus filhos conhecidos. A abertura da interface não equivale a uma sessão remota autorizada.
6. Comprova o armazenamento e o perfil do daemon Ollama em F:. Se necessário, copia manifests/pesos conferidos para F:, preservando a origem, e inicia um servidor dedicado em 127.0.0.1:11435. Porta desconhecida ou espaço insuficiente bloqueiam a etapa. O instalador com 27B solicita então o download explícito da variante leve e uma consulta curta sem histórico; só uma resposta OK concluída permite selecioná-la.
7. Configura o cliente 9Router por sua API oficial local. Reaproveita o modelo manual ou um combo adequado existente; quando necessário, procura uma opção compacta em um provedor com credencial local. Se a seleção continuar ambígua, mostra o catálogo para uma escolha.
8. Confere o Telegram por `getMe` se token e ID já estiverem configurados; confere o catálogo Gemini se houver chave. Prepara a entrada gerenciada de início após logon e solicita o início do bot, ou do painel local se o Telegram ainda estiver pendente.

O instalador pode concluir as etapas disponíveis e deixar apenas um serviço opcional pendente. “Início solicitado”, “catálogo respondeu” e “configurado” têm significados diferentes: a preparação comum não gera respostas. O iniciador com 27B solicita o teste local descrito acima; não testa respostas pagas automaticamente.

## Contas e chaves com menos etapas

As chaves existentes ficam no `.env` externo e não são devolvidas à página de progresso. Para o 9Router, o preparador usa a autenticação oficial da CLI que já existir no mesmo perfil gerenciado em F: e cria uma chave dedicada chamada **`MeuControlePC automatico`**. A criação ocorre pela API; o banco local é consultado apenas para leitura de metadados. Uma identificação local evita criar uma chave nova a cada retomada.

As chaves mostradas anteriormente em capturas de tela não são usadas para esta integração. A nova chave dedicada não revoga outras chaves: revogue as que foram expostas no dashboard correspondente, se ainda estiverem ativas.

Quando faltarem login, autenticação da CLI, permissão de projeto ou uma credencial de provedor, a janela oferece a página oficial. Login, senha, CAPTCHA, 2FA e consentimento da conta são concluídos pelo proprietário. O programa não coleta cookies, não procura chaves em capturas de tela e não contorna essas etapas.

Para Gemini ou Telegram, cole a credencial somente no **campo oculto da janela local** e clique em **Salvar localmente**. Para Telegram, informe também o ID numérico do proprietário no campo correspondente. Em seguida, use **Retomar**. A resposta da página confirma a gravação sem repetir o conteúdo. Nunca cole `.env`, tokens ou chaves no chat ou no GitHub.

A assinatura Colab não confirma cota da API Gemini. A presença de uma conta no 9Router também não comprova acesso, saldo ou geração para todos os modelos. A instalação não compra créditos nem testa respostas pagas automaticamente.

## Caminhos e preservação

No computador apresentado nas capturas, os caminhos usuais são:

| Conteúdo | Caminho |
| --- | --- |
| Fontes implantadas | `F:\MeuControlePC_v2\aplicativo` |
| Configuração privada | `F:\MeuControlePC_v2\.env` |
| Dados existentes | `F:\MeuControlePC_v2\dados` |
| Estado público da preparação | `F:\MeuControlePC_v2\preparacao` |
| Backup das fontes e da configuração | `F:\MeuControlePC_v2\backups_codigo` |

O iniciador ativa o modo restrito a F:. Código, configuração, dados, caches, temporários e backups são validados nessa unidade. Um pequeno atalho gerenciado fica no Startup do Windows, apontando para F:. Arquivos internos do Windows e do navegador não são realocados. A instalação antiga e a origem dos modelos permanecem intactas até a conferência do novo fluxo. Se os dados externos não forem localizados, o preparador interrompe para não iniciar vazio.

O manifesto confere a integridade do pacote recebido; não é uma assinatura de origem. Use o pacote publicado no repositório do projeto. Arquivos privados, `.git`, `.venv`, caches e pesos não pertencem ao manifesto nem à atualização de fontes.

DNS, `hosts`, proxy, Firefox, adaptadores, firewall, Tailscale e a inicialização de aplicativos de terceiros são preservados. A entrada gerenciada do próprio assistente é preparada; a habilitação efetiva pelo Windows deve ser conferida no Gerenciador de Tarefas.

## Abrir o painel do computador no 9Remote

Na versão gerenciada 3.0.43, abra **http://127.0.0.1:2208/ui/index.html**. As rotas `/` e `/ui` levam ao cliente e podem voltar ao login ou à apresentação; o caminho completo abre o painel do host. O botão de pareamento desta preparação usa esse endereço. Uma instalação já aberta pode usar o link diretamente.

Nesse painel, confira o estado do host e os controles de pareamento. As chaves são próprias do 9Remote e devem permanecer no computador/dispositivo a parear. O login do cliente e a abertura do painel não comprovam uma sessão remota autorizada. Consulte a [correção v2.11.2](REVISAO_V2_11_2.md).

## RoboTask e acesso ao computador

A preparação usa scripts e APIs locais para os passos conhecidos. Detectar `RoboTask.exe` não comprova a revisão de uma macro. Macros pessoais `.tsk`, F8/F9/F10 e tarefas desconhecidas não são disparadas durante a instalação.

Este pacote executa no seu Windows depois que você abre o iniciador. O Codex na nuvem não ganha acesso ao computador por o RoboTask estar instalado. Nesta entrega, não havia um dispositivo Windows conectado ao ambiente de desenvolvimento; instalações, cliques e contas reais não foram validados remotamente.

Para chamar o mesmo preparador por uma tarefa local revisada, é possível usar `python preparacao_autonoma.py --sem-interface`, a partir das fontes completas e com o Python adequado. Essa opção executa a mesma preparação e retorna somente o estado público. Não aceita código arbitrário nem uma chave como argumento de linha de comando.

## Conferência no Windows

Após a primeira execução, confira o estado de cada etapa na janela local. Se o Ollama permanecer pendente por porta ocupada, a mensagem deve identificar o motivo disponível; concluir o 9Router permite usar essa integração sem forçar o encerramento do Ollama.

Abra o painel pelo botão da preparação. O cartão **Telegram** informa a última consulta observada e a idade dessa evidência; uma consulta bem-sucedida não confirma o processamento de um comando nem a entrega de uma resposta. O cartão é atualizado junto com os dados locais, sem consultas adicionais à API. Se o Telegram estiver pronto, diga “mostre o estado do computador” ao seu bot e faça uma pergunta simples no modelo escolhido. Texto e áudio usam o mesmo fluxo; “sim” confirma um pedido completo e “cancelar” o descarta. Para conferir a equipe, diga “teste todos os modelos” e confirme a consulta solicitada. Essa utilização é a conferência real do provedor, sujeita à conta e às cotas. Para áudio, envie um áudio curto e confira a transcrição no próprio ambiente. Testes automatizados usam simulações e não confirmam essas operações reais.

Se faltarem um executável compatível, acesso aos recursos oficiais, espaço em F: ou permissão do Windows, conclua o requisito mostrado e use **Retomar**. Uma solicitação de permissão do instalador oficial pertence ao Windows; a preparação não a confirma em seu lugar.

## Reversão

A implantação cria um diretório `backups_codigo\implantacao_<identificador>`, com as fontes anteriores em `fontes\` e o índice `manifesto_reversao.json`. Se a cópia falhar durante a implantação, tenta restaurar somente os arquivos que ela acabou de alterar; uma alteração concorrente é preservada e precisa ser conferida.

Para voltar a uma entrega anterior depois de uma instalação concluída, encerre somente o assistente e o preparador, consulte o índice do backup e restaure apenas as fontes substituídas para os mesmos caminhos relativos da instalação em F:. Os hashes do índice permitem conferir se o arquivo atual ainda corresponde à implantação antes de restaurá-lo. Não copie um backup inteiro sobre dados ou ambientes virtuais.

A configuração tem uma cópia privada em `backups_codigo\configuracao\.env.antes_preparacao_<identificador>.bak`. Restaure esse arquivo somente se precisar desfazer as opções de configuração, com o bot encerrado e preservando eventuais mudanças posteriores. O manifesto público anterior é guardado separadamente em `backups_codigo\manifestos`. Esses backups ficam no computador e não devem ser publicados.
