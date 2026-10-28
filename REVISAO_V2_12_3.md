# MeuControlePC v2.12.3 — instalação em F:

O proprietário informou que o espaço disponível está em F:. O pacote anterior
ainda implantava o código no perfil de C:, herdava temporários do Windows e
não comprovava o disco do daemon antes do pull. A variável OLLAMA_MODELS no
cliente não muda o armazenamento de um servidor já em execução.

## Instalar

1. Salve o ZIP diretamente em **F:\Instaladores** e extraia nessa unidade,
   fora de F:\MeuControlePC_v2\aplicativo.
2. Feche o assistente e o preparador anteriores. Não é necessário remover
   arquivos antigos ou encerrar processos desconhecidos.
3. Abra **INSTALAR_EM_F_COM_27B.bat**. Ele atualiza as fontes, prepara as
   dependências, confere/importa os modelos, solicita o download e o teste do
   27B leve e inicia o assistente. Acompanhe o progresso no console e na
   janela local. Contas que exigirem login aparecem como pendências.

Para atualizar sem repetir a preparação do 27B, abra INSTALAR_E_INICIAR.bat.
O teste também pode ser solicitado separadamente por PREPARAR_27B_LEVE.bat.
Os iniciadores recusam execução fora de F: e não usam C: como destino alternativo.

## Destinos

| Conteúdo | Destino |
| --- | --- |
| Fontes | F:\MeuControlePC_v2\aplicativo |
| Ambiente Python | .venv nessa pasta, ou .venv existente na raiz F:\MeuControlePC_v2 |
| Configuração existente | F:\MeuControlePC_v2\.env |
| Dados existentes | F:\MeuControlePC_v2\dados |
| Caches e temporários | F:\MeuControlePC_v2\cache e temporarios |
| Voz local | F:\MeuControlePC_v2\modelos_voz |
| Pesos Ollama | Armazenamento existente comprovado em F:, ou F:\MeuControlePC_v2\modelos_ollama |
| Perfil do daemon dedicado | F:\MeuControlePC_v2\perfil_ollama |
| Pacotes/perfis 9Router e 9Remote | F:\MeuControlePC_v2\runtime |
| Backups | F:\MeuControlePC_v2\backups_codigo e preparacao\inicio_guardado |

Um Python, Node ou Ollama já instalado pode ser executado para bootstrap;
o instalador não instala bibliotecas nesse Python. Os pacotes ficam na venv
de F:. Se Python/Node/Ollama estiver ausente, o fluxo sinaliza o requisito e
não chama winget com destino padrão em C:. O PC apresentado já dispõe desses
executáveis. Não há reinstalação automática do Windows ou dos drivers.

O pequeno atalho gerenciado de logon permanece na pasta Startup do Windows,
apontando para F:. Arquivos internos de sistema do Windows e do navegador
não são realocados. Código, ambientes, pesos, caches e backups do aplicativo
usam F:.

## Modelos e serviços

`armazenamento_ollama_f.py` identifica o listener, o executável, os argumentos
serve e as opções públicas do processo, sem devolver seu ambiente bruto.
Só aceita um servidor cujo armazenamento e perfil estejam comprovados em F:.
Se os pesos estiverem em C:, copia apenas manifests/blobs referenciados pelo
catálogo, confere SHA256 e publica os manifests depois dos blobs completos.
Preserva a origem; não copia contas, chaves ou outros arquivos de .ollama.
Confere espaço livre antes da cópia. A cópia dos modelos existentes ocupa
espaço adicional em F:, além dos aproximadamente 11,2 GB da quantização nova.

Quando necessário, inicia o executável existente como servidor dedicado em
127.0.0.1:11435, com perfil e temporários em F:. Um listener desconhecido é
preservado e bloqueia a etapa. Não mata processos, não apaga pesos e não
aceita o PID salvo como prova. Só depois de conferir o catálogo troca as
opções públicas OLLAMA_URL/OLLAMA_MODELS. Um Python bootstrap sem psutil
executa essa conferência pela venv de F:, sem instalar no Python global.

O 27B leve continua sujeito ao teste real e aos limites da v2.12.2: IQ3
comunitário, texto/áudio transcrito, original preservado e nenhuma seleção
antes de resposta OK concluída. Falha deixa pendência e permite iniciar os
demais recursos, sem repetir inferência automaticamente.

9Router/9Remote usam pacotes e perfis filhos em F:, preservando o perfil
principal do Windows. Se uma instância antiga em C: ocupar a porta, o fluxo
não a encerra nem envia autenticação/escrita ao serviço sem comprovar perfil
em F:. Contas e pareamento podem precisar ser concluídos no novo perfil.

## Validação e reversão

Testes usam arquivos pequenos, processos, portas e APIs simulados. Cobrem
recusa de destino fora de F:, caches, criação/reuso da venv, prova do daemon,
cópia corrompida ou sem espaço, catálogo preservado, perfil de serviços,
nenhum pull antes da prova e transferência de atalhos entre volumes.
Nenhum peso ou instalador real foi baixado e nenhum processo Windows foi
executado na nuvem. A instalação e a geração reais exigem conferência no PC.
Totais e CI são registrados na entrega/PR.

As fontes e os modelos antigos em C: permanecem disponíveis. Para reverter,
encerre somente assistente/preparador, use os hashes do backup da implantação
e restaure as opções anteriores necessárias da cópia local da configuração,
preservando alterações posteriores. RESTAURAR_27B_LEVE.bat desfaz apenas
perfil/seleção do 27B. Não apague a instalação antiga, a origem dos pesos ou
os backups antes de conferir o novo fluxo. A reversão do atalho usa a cópia
em preparacao\inicio_guardado; não sobrescreva um atalho alterado depois.
