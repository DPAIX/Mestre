# Revisão v2.11.1 — início do Ollama e retomada

A captura mostrava o bot v2.11.0 iniciado, mas o Ollama pendente: a conexão de teste não confirmava acesso e a consulta do Windows não encontrava um listener na porta 11434. O código tratava qualquer timeout ou erro de conexão de 0,3 segundo como porta ocupada. Isso podia impedir o início mesmo com o endpoint disponível. A captura não comprova a causa de rede específica do computador.

## Correção

No Windows, quando a conexão curta fica inconclusiva, o iniciador tenta vincular temporariamente um socket exclusivo ao mesmo IP de loopback e à mesma porta. Só um vínculo exclusivo bem-sucedido permite uma tentativa de início do Ollama. O socket temporário não escuta nem aceita conexões e é fechado antes da tentativa. Porta ocupada, reservada, sem permissão ou sem suporte à exclusividade continua impedindo o início.

A disponibilidade é uma amostra: outro programa pode ocupar a porta depois da verificação. O Ollama ainda precisa conseguir vincular o endpoint e responder aos metadados. Não há encerramento de processos existentes, segunda tentativa automática, download de modelos ou alteração de firewall, DNS, hosts ou proxy.

O botão **Retomar** também volta a conferir as pendências quando o bot já está aberto a partir das fontes instaladas. Antes, a otimização de reaproveitamento podia encerrar a conferência cedo demais. A retomada conserva a verificação de identidade antes de parar o próprio bot e a trava antes de atualizar os arquivos.

O preparador também reaproveita `OLLAMA_NO_CLOUD` e `OLLAMA_MODELS` do `.env` externo, preservando a política de nuvem e o diretório de pesos definidos nessa configuração ao iniciar o serviço.

## Aplicar no computador

1. Feche a janela de console da preparação anterior, a que mostra **Preparação automática: http://127.0.0.1:...**. Esse processo antigo mantém a trava da preparação; abrir outro pacote enquanto ele estiver ativo apenas reabre a janela antiga.
2. Extraia o pacote v2.11.1 em Downloads e abra **INSTALAR_E_INICIAR.bat**. O instalador verifica o próprio bot antes de atualizá-lo; reaproveita configuração, dados e componentes existentes.
3. Confira a etapa Ollama na página local de progresso. **API respondeu** confirma os metadados; uma conversa continua sendo necessária para comprovar a geração do modelo.

O 9Remote mostrar **UI ready** confirma somente a interface local em http://localhost:2208. O aviso de hooks do Codex pertence ao 9Remote; esta correção não altera a confiança de hooks nem executa macros. Não havia um Windows conectado ao Codex para realizar o reparo diretamente no computador.

## Validação e reversão

As regressões cobrem conexão lenta, vínculo livre/ocupado/negado, IPv4/IPv6, liberação do socket, políticas de início e tentativa única de processo. O CI Windows inclui verificações de vínculo exclusivo em portas locais efêmeras; os testes que iniciariam programas usam simulações. Nenhuma conta, macro ou geração externa é usada nesses testes. Os resultados finais constam no PR e no relatório da entrega.

Os backups continuam em `backups_codigo`, fora das fontes e dos dados. Para reverter, encerre o assistente e a preparação e restaure somente os arquivos afetados do backup desta implantação, conferindo o índice `manifesto_reversao.json`. O procedimento completo está no [guia de instalação e reversão](GUIA_INSTALACAO_AUTONOMA.md).
