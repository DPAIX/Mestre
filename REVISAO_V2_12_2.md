# MeuControlePC v2.12.2

## Problema e evidência

O proprietário confirmou geração individual em Mistral, Llama e Qwen de 4B.
O `qwen3.8:27b` oficial ocupa 16,52 GiB para 15,96 GiB de RAM física e era
adiado pelo perfil CPU. O PC tem GTX 1660 com 6 GB de VRAM; o proprietário
escolheu uma quantização local menor, preservando o modelo original.

A captura também mostrou “me agende uma tarefa” mobilizando a equipe e
devolvendo um aviso local contado incorretamente como resposta. A contagem e
o formato foram corrigidos na v2.12.1, incluída integralmente nesta entrega.
A nova revisão reconhece o pedido incompleto antes de qualquer consulta à IA.

## Mudanças

- `esclarecimento_conversa.py`: reconhece “me agende uma tarefa”, pergunta o
  título, dia e horário ausentes e preserva os campos informados. Texto e
  áudio transcrito usam o mesmo fluxo, isolado por proprietário, conversa e
  tópico. O plano da rotina local continua exigindo confirmação. Não cria
  eventos Google ou alarmes que a integração não implementa.
- `configurar_ia_local.py`, `multi_ia.py`, `conversa_equipe.py`: perfil
  `equilibrado` com contexto 1024, saída de até 256 tokens, `think=false` e
  `keep_alive=0`. O Ollama escolhe CPU/GPU; não é enviado `num_gpu=0`.
  A equipe continua sequencial, inclusive quando solicitado modo paralelo.
  Catálogo, autorização de nuvem e bloqueio explícito de nuvem permanecem.
  O guard de RAM do perfil CPU não foi removido.
- `preparar_27b_leve.py`: operação explícita por duplo clique. Com o bot
  encerrado, confere o serviço local ocioso, baixa a tag somente se ausente,
  verifica manifesto/quantização e envia uma única pergunta curta sem histórico.
  Exige resposta `OK` com conclusão confirmada e sem truncamento. O prazo do
  teste não excede o orçamento normal. Após a resposta, confere novamente
  o manifesto e as opções públicas antes de ativar.
- `alternativa_27b.py`, `servicos_chat.py`, `bateria_modelos.py`: após esse teste
  e opt-in, a equipe usa a tag leve no lugar da original e informa os dois
  nomes. O original permanece no catálogo e em disco. Equipes manuais antigas
  recebem a seleção somente na execução; os históricos não são reescritos.
  Uma tag ausente, remota ou com outro digest bloqueia a seleção, sem fallback
  silencioso. “Teste todos os modelos” informa qual variante foi testada.
- A preparação guarda somente os valores anteriores de `OLLAMA_PERFIL` e
  `OLLAMA_27B_LEVE`, em JSON local de reversão. Não copia credenciais ou
  histórico. A escrita preserva as outras opções, inclusive o modelo geral.

## Artefato escolhido e limites

[batiai/qwen3.8-27b:iq3](https://ollama.com/batiai/qwen3.8-27b:iq3) é uma
quantização **comunitária IQ3_XXS**, com 11.186.385.185 bytes no catálogo
(aproximadamente 11,2 GB ou 10,42 GiB). O autor declara origem nos pesos BF16
oficiais, com imatrix; não reproduzimos essa conversão. A precisão menor pode
reduzir a qualidade das respostas. Esta variante não inclui o projetor de
visão nem MTP: serve para texto e áudio já transcrito. O original multimodal
é preservado.

[Manifesto conferido](https://registry.ollama.ai/v2/batiai/qwen3.8-27b/manifests/iq3):
`sha256:abca93dece6899e6b1f4a98dfb8089c328fadc65a3df825d33ca5e39e0961d64`.
Se o publicador mudar a tag, a preparação interrompe; não aceita automaticamente
outro artefato. Os padrões upstream de contexto16384/saída2048 são substituídos
por limites curtos no teste e no perfil equilibrado.

A GTX 1660 é compatível com a faixa de GPU NVIDIA documentada pelo Ollama,
dependendo do driver instalado. Não alteramos drivers. RAM e VRAM não são um
único bloco somável; o espaço necessário e a velocidade exigem teste real.
O uso efetivo da VRAM não é medido por esta preparação. O timeout do Mistral
na equipe é distinto do sucesso individual e não é anunciado como resolvido
sem nova execução no PC. Contas/cotas dos provedores externos não são
validadas por testes locais de código.

## Instalar e conferir no Windows

1. Feche as janelas antigas do assistente e da preparação. Mantenha o serviço
   Ollama aberto, sem outra consulta em andamento.
2. Extraia o ZIP completo em Downloads, fora da pasta instalada.
3. Abra **PREPARAR_27B_LEVE.bat** na pasta extraída. Aguarde o download e o
   teste. Somente `PREPARACAO_27B=configurado` confirma a seleção. Se falhar,
   as opções anteriores permanecem; o modelo baixado pode ficar no catálogo.
   Nenhum processo ou modelo existente é encerrado/apagado.
4. Abra **INSTALAR_E_INICIAR.bat** dessa mesma pasta para implantar as fontes
   com backup e iniciar. Configuração e dados externos existentes são usados.
5. Envie “me agende uma tarefa”, responda às perguntas e confira a confirmação
   antes de gravar. Envie “teste todos os modelos” para uma consulta real a
   cada participante selecionado; o relatório deve mostrar a tag IQ3 e dizer
   que o original foi preservado. Use texto ou áudio, sem comando com barra.

## Validação e reversão

Os testes automáticos usam catálogos, HTTP e inferências simulados. Conferem
digest, falhas de download/inferência, nenhuma gravação antes do sucesso,
reversão sem sobrescrever alterações posteriores, seleção explícita,
restrições de nuvem, perfil GPU/CPU e esclarecimentos por texto/áudio.
Nenhum peso ou driver é instalado na nuvem e nenhuma chamada real a modelo,
Telegram, macro ou ação Windows faz parte da suíte. Os totais e o CI são
registrados na entrega e no PR.

Para desfazer a seleção e o perfil, feche assistente/preparador e abra
**RESTAURAR_27B_LEVE.bat**. Ele restaura só as duas opções públicas quando
a configuração ainda corresponde à aplicação desta preparação. Alterações
posteriores são preservadas; os pesos baixados permanecem em disco.
Depois, inicie o assistente novamente. Para reverter também as fontes, use
o `manifesto_reversao.json` do backup da implantação, conferindo hashes e
preservando alterações posteriores. Não restaure configuração ou dados
pessoais a partir de um pacote de fontes.
