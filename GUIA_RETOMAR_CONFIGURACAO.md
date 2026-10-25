# Retomar a configuração — v2.10.2

O registro enviado confirma que bibliotecas, voz, Node.js e Telegram foram preparados. Os pacotes 9Router/9Remote também foram encontrados. Ficaram pendentes o serviço Ollama e a configuração dos clientes 9Router/Gemini. A presença de uma chave ou pacote não comprova geração nem acesso à conta.

## Aplicar a correção

1. Encerre o assistente e o painel. Guarde as fontes v2.10.0 para reversão.
2. Copie o conteúdo da pasta `MeuControlePC_v2_10_2` do ZIP completo para `C:\Users\Mestre\Documents\GitHub\Mestre`, onde está `assistente_pc.py`. Preserve seu `.env`, dados, ambientes Python e modelos em F:. Não substitua o `.env` pelo exemplo.
3. Abra **`retomar_configuracao.bat`**. Ele oferece apenas Ollama, 9Router, Gemini, agentes e a conferência final. Não repete instalação de bibliotecas, Telegram, Startup, Node.js, pacotes 9Stack ou a abertura do 9Remote.

Na pergunta de cada etapa, `sim` abre a etapa e Enter pula. Dentro de uma etapa, responda conforme o campo: número, ID de modelo/combo ou chave oculta. O configurador agora avisa e permite corrigir entradas, com limite de três tentativas, antes de pedir a chave ou gravar opções.

## Ollama

A ordem foi corrigida: política de início → início do serviço → seleção de modelo → perfil CPU. Antes, apenas salvar `1` na política não iniciava o serviço naquela preparação.

- Na política, `1` permite que o assistente inicie o serviço ausente; `0` mantém o início manual. Escolher a política não abre um processo por si só.
- Na nova etapa de início, confirme para verificar a API e iniciar uma vez o Ollama instalado, se autorizado e se a porta estiver livre. A operação compartilha a trava de instância com o bot. Não baixa modelos, não encerra processos e não altera DNS/proxy/hosts/firewall.
- Continue à escolha de modelos quando aparecer que os metadados locais estão acessíveis. Use uma tag que conste no catálogo. Para o PC com cerca de 16 GiB, o perfil CPU compacto seleciona Llama se ele já estiver registrado; não transforma um modelo grande em pequeno.
- Se a porta estiver ocupada sem resposta, o assistente preserva o processo existente e não cria outro servidor. Abra `diagnosticar_ollama.bat` para conferir serviço, recursos e modelos carregados. A falta de resposta da API não demonstra queda da Internet.

## 9Router

O ID de **modelo/combo** e a **chave da API** são campos diferentes. No campo de modelo, informe exatamente o identificador do catálogo/dashboard. Não use uma chave, uma URL ou apenas `sim`. O configurador recusa valores com aparência de credencial sem repeti-los na mensagem.

O log compartilhado continha uma possível chave digitada no campo visível de modelo. Renove essa chave no dashboard do 9Router e digite a nova somente na entrada oculta do console. Não é necessário compartilhá-la no chat.

No configurador:

1. Informe o ID real do modelo/combo criado ou disponível no dashboard.
2. Enter na base mantém a salva, ou a base padrão `http://127.0.0.1:20128/v1`.
3. Responda `sim` para ativar quando as contas/modelo estiverem preparados.
4. No campo oculto, digite a nova chave. Enter preserva a salva somente se seu formato for válido. `APAGAR` prepara a remoção de uma chave opcional; use isso somente se o gateway estiver configurado para funcionar sem chave. A remoção exige a confirmação final.
5. Digite `confirmar` para salvar. Cancelar preserva arquivo e opções em memória.

O dashboard foi acessível no registro, mas provedores, cotas e geração ainda não foram testados. Depois de iniciar o assistente, use o catálogo e o botão de teste explícito do painel para conferir um modelo.

## Gemini

Na etapa Gemini:

```text
API: 1 = interactions, 2 = generate_content [1]:
```

Use **Enter ou `1`** para Interactions. No campo seguinte, use Enter para `gemini-3.8-flash` ou informe outro ID de modelo que esteja disponível à sua chave. Não digite `sim` nesses dois campos. A chave é solicitada depois, com entrada oculta; Enter mantém a atual. A frase final **`SALVAR GEMINI`** grava as opções.

A nova validação impede salvar `sim` como ID de modelo ou usar um valor com aparência de chave nesse campo. Erros da etapa Gemini agora mostram a orientação de Gemini, sem indicar Node.js como causa. Colab Pro e cota Gemini API continuam separados; salvar as opções não faz uma chamada de geração.

## Aplicativos de agentes e início do bot

Escolha um ID de aplicativo da lista, por exemplo `hermes` ou `codex`. O configurador abre a interface oficial, onde você escolhe o modelo. O campo de modelo foi retirado desta etapa para evitar confundir o nome de um aplicativo com uma tag de modelo.

Ao terminar, abra **`iniciar_redirecionado.bat`**. No painel local `http://127.0.0.1:8765`, confira as integrações e use testes explícitos quando quiser enviar uma geração. As configurações de rede que voltaram a funcionar e o início de aplicativos externos são preservados.

Para reverter o código, encerre bot/painel e restaure as fontes v2.10.0, mantendo `.env`, dados e modelos. Opções escolhidas no console são persistidas somente após suas confirmações; reverter fontes não desfaz uma chave renovada no dashboard. O início manual/automático do Ollama continua controlado pela política existente.

[Guia de todos os recursos](GUIA_ASSISTENTE_INTEGRADO.md) · [Revisão e validação v2.10.2](REVISAO_V2_10_2.md).
