# Revisão v2.11.2 — painel do host 9Remote e progresso da preparação

## 9Remote voltando ao login ou à apresentação

A versão gerenciada `9remote@3.0.43` redireciona `/` e `/ui` para o workspace do cliente. O botão Host QR desse cliente aponta para `/`, de modo que voltar por esse botão podia levar ao mesmo login ou à apresentação sem mostrar as chaves do computador.

O painel do host continua empacotado em **http://127.0.0.1:2208/ui/index.html**. A integração e o botão de pareamento do MeuControlePC agora usam esse caminho explícito. Quem já está com o 9Remote aberto pode acessar esse endereço diretamente; não precisa reinstalar o serviço para conferir o painel.

O comportamento foi verificado no tarball oficial exato de `9remote@3.0.43`, correspondente ao commit `5f54ea2d70d8ea773676ca0f52419eecffe81d06`. O pacote foi inspecionado sem executar seus scripts. Fontes imutáveis: [redirecionamento do cliente](https://github.com/decolua/9remote/blob/5f54ea2d70d8ea773676ca0f52419eecffe81d06/host/index.js#L365) e [servidor do painel do host](https://github.com/decolua/9remote/blob/5f54ea2d70d8ea773676ca0f52419eecffe81d06/host/index.js#L433).

## Preparação que parecia continuar executando

Cada tentativa agora limpa os itens da tentativa anterior. Ao concluir ou interromper uma etapa, o resumo termina como concluído ou pendente; não mantém uma etapa antiga em execução. O formulário de credencial só aparece quando há uma pendência de chave, e o seletor de modelo só aparece para uma pendência de modelo. Uma instância anterior ainda aberta não deve solicitar uma chave Gemini.

Quando o preparador retoma e precisa parar o bot que ele próprio criou, usa a referência original de `Popen`. No Windows ela mantém o HANDLE daquele processo; não seleciona outro processo pelo número do PID. A referência só é utilizada se código, dados, configuração e Python continuarem correspondendo à instalação. Depois do encerramento, a trava de instância ainda é conferida antes da implantação. Falha ou timeout de encerramento impede atualizar e iniciar outro bot.

Bots abertos por outra janela continuam sujeitos à verificação independente de identidade. Se essa verificação não concluir, o preparador pede o fechamento da janela indicada. Serviços como Ollama e 9Remote não são encerrados por esse controle.

## Estado dos serviços e diagnóstico

As janelas de console de serviços podem ficar sem novas linhas enquanto aguardam trabalho. Use a página de progresso para conferir as pendências. A mensagem de início solicitado não comprova que a API, a geração de modelos ou o pareamento responderam.

O erro de vínculo Windows **10048** significa endereço/porta em uso. Um listener identificado como Ollama ainda precisa responder em `/api/version`; não é autorização para iniciar outro servidor ou encerrar um processo indiscriminadamente. Essa correção não muda portas, firewall, DNS, hosts, proxy ou modelos do Ollama.

## Aplicação, testes e reversão

Para o 9Remote já aberto, use o endereço direto acima. Para atualizar as fontes e o preparador, feche a janela da preparação anterior, extraia o pacote novo em Downloads e abra `INSTALAR_E_INICIAR.bat`. Configuração, dados, ambientes e modelos externos são reaproveitados.

As regressões cobrem as duas entradas de abertura do painel 9Remote, campos visíveis apenas para as pendências correspondentes, encerramento dos estados de progresso e parada somente do filho conhecido, incluindo timeout e contexto diferente. Processos e serviços reais são simulados nesses testes; os resultados completos constam no PR e no relatório da entrega.

Os backups por arquivo e a cópia privada da configuração continuam fora das fontes e dos dados. A reversão é descrita no [guia de instalação](GUIA_INSTALACAO_AUTONOMA.md); restaure somente os arquivos afetados, conferindo o índice do backup. Nenhum dispositivo Windows estava conectado ao Codex para aplicar esta atualização diretamente no computador do usuário.
