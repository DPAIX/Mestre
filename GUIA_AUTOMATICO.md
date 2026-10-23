# Assistente automático com voz local — v2.7.1

Se a preparação v2.7.0 já concluiu, atualize as fontes em C:, encerre o bot antigo e abra `iniciar_redirecionado.bat` uma vez. O Startup e o transcritor preparado são reaproveitados; não é necessário enviar comandos no Telegram ou preparar os pesos novamente. Veja a [correção CPU e conversa](REVISAO_V2_7_1.md).

Texto e áudio passam a ser a entrada normal do assistente. O transcritor padrão é Whisper `base` multilíngue em CPU/int8; não depende de créditos de Gemini. As conversas padrão usam todos os modelos do catálogo Ollama em cooperação sequencial e síntese, sem precisar enviar comandos de ativação.

## Preparar uma vez por duplo clique

1. Encerre o bot antigo e coloque todos os arquivos atualizados na raiz de `C:\Users\Mestre\Documents\GitHub\Mestre`. Preserve `.venv`, `F:\MeuControlePC_v2\.env` e `F:\MeuControlePC_v2\dados`.
2. Abra **`ativar_assistente_automatico.bat`** por duplo clique. Não é necessário abrir terminal ou enviar comandos pelo Telegram. Essa preparação instala/reaproveita dependências, baixa uma vez os pesos públicos do Whisper base, registra o início no Startup do seu usuário Windows e inicia o assistente. A primeira preparação precisa de internet e espaço para dependências e modelo; os pesos base ocupam aproximadamente 150 MB, além das bibliotecas.
3. Depois da conclusão, envie texto ou uma mensagem de voz ao bot. Os próximos logons do Windows iniciam o assistente com a mesma configuração externa. O início normal não instala pacotes nem baixa modelos novamente.

O código permanece em C:, a configuração/dados em F:, e o modelo de voz em `F:\MeuControlePC_v2\modelos_voz\base`. Não há cópia de segredos para o GitHub ou para o atalho. O Startup contém somente caminhos. A preparação preserva atalhos não identificados no mesmo destino e usa uma única entrada gerenciada.

Isso inicia depois de você entrar na sua conta do Windows. O PC precisa estar ligado e com a unidade F: acessível. Não foi instalado um serviço de sistema nem alterada a tela de logon.

## O que fica automático

- **Ollama:** ao iniciar o assistente no Windows, verifica o endpoint de loopback. Se não responder, tenta abrir o executável já instalado uma vez e aguarda por prazo limitado. Reaproveita `OLLAMA_MODELS`; na instalação redirecionada, também reconhece `F:\Models` quando já contém a estrutura de manifestos. Não baixa outro modelo de conversa nem encerra um serviço existente.
- **Todos os modelos:** a primeira mensagem que precisar de IA consulta o catálogo e usa suas tags, até oito, em cooperação sequencial. O catálogo é relido nas perguntas seguintes para incorporar os modelos disponíveis. As conversas anteriores sem a nova política recebem o padrão sob demanda, preservando o histórico. Não há migração em massa nem geração ao abrir menus.
- **Voz:** identifica o áudio, transcreve localmente em português e encaminha o texto ao mesmo fluxo de conversa e confirmação. Não é necessário configurar uma API de transcrição. O áudio não é enviado a Gemini como fallback.
- **Instância única:** uma trava do sistema impede duas instâncias do assistente usando os mesmos dados, inclusive se o iniciador for aberto mais de uma vez. O arquivo de trava pode permanecer após a saída; sua existência, sozinha, não impede o próximo início.

Pedidos reconhecidos de rotina, saldo e outras leituras usam os registros locais diretamente. Pedidos de alteração continuam aguardando confirmação do proprietário autorizado. A inicialização automática e a equipe padrão não autorizam execução de código de modelos, macros arbitrárias ou desligamento do PC.

## Voz e recursos

O Whisper usa `faster-whisper`/CTranslate2 em CPU/int8, até quatro threads e um processo por transcrição, com limite total de 120 segundos. O processo termina antes de a conversa prosseguir, liberando seus recursos. São aceitos áudios de até 8 MB e três minutos; transcrições vazias ou maiores que 8000 caracteres são recusadas sem enviar pedidos parciais. O arquivo temporário local é removido ao terminar a tentativa.

Uma transcrição usa somente o cache preparado, com Hub offline. A preparação inicial pode acessar o repositório público de pesos, usando a configuração de rede disponível; não envia áudio ou chaves do assistente. O cache fica fora das fontes e não entra no pacote de exportação. Se faltarem pesos/dependências, o bot orienta concluir a preparação; não tenta cobrar uma API externa.

Configurações públicas opcionais no `.env`:

```dotenv
VOZ_PROVEDOR=local
VOZ_MODELO_LOCAL=base
```

`tiny` ou `small` podem ser escolhidos antes da preparação, conforme velocidade/qualidade desejadas; `base` é o padrão. Se mudar o modelo depois, execute novamente a preparação para obter seus pesos. `VOZ_PROVEDOR=gemini` mantém a opção anterior por escolha explícita, dependente da conta e da credencial correspondente. A ausência dessa variável significa voz local.

O uso de todos os modelos não garante que todos responderão: o 27B continua exigindo memória e pode expirar no PC. Falhas e resultados parciais são mostrados; não há retries de geração. O perfil CPU que funcionou permanece inalterado. A síntese mantém os limites e a confirmação descritos no [guia da equipe](GUIA_EQUIPE_COOPERATIVA.md).

## Escolhas manuais, recuperação e reversão

Não são necessários `/start`, `/chat equipe on` ou `/ia` para uma conversa padrão. Os comandos continuam como opções avançadas. Escolher explicitamente modelo/provedor individual ou desligar a equipe na v2.7.0 salva uma política manual nessa conversa; ela não será sobrescrita na próxima pergunta. Conversas novas no padrão voltam a usar a equipe automática.

Para desativar o início ao logar, abra `desabilitar_inicio_com_windows.bat`. Isso remove somente a entrada gerenciada do Startup; dados, configuração e pesos permanecem. Abrir novamente `ativar_assistente_automatico.bat` registra o início de novo. Para sair do bot atual, encerre sua janela ou use o fluxo local apropriado; desativar o Startup não encerra o processo em execução.

Se a preparação falhar, ela não apaga `.env`, dados ou um atalho anterior. Confira rede, espaço, permissões e suporte do Python às bibliotecas de voz antes de abri-la novamente. Python 3.11 ou superior é exigido; uma `.venv` existente é reaproveitada. Com F: indisponível, o redirecionador não usa uma configuração alternativa em C:.

Para reverter o código, desative primeiro o Startup e restaure todas as fontes v2.6.0, preservando `.env`, dados e modelos. As fontes antigas ignoram a política automática e usam o transcritor anterior. A validação real de voz e do logon precisa ser feita no Windows; os testes automatizados não registram atalhos, não usam microfone nem executam ações do PC.
