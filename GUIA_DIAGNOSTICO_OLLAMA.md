# Diagnosticar o Ollama quando o catálogo responde e a geração expira

O catálogo do PC lista quatro tags e a equipe foi ativada. As gerações do bot expiraram; depois, o comando nativo `ollama run llama3.2:latest "Responda apenas OK"` também ficou sem resposta durante a observação. Isso coloca o problema de geração abaixo do fluxo Telegram. Ainda não identifica memória, GPU, fila ou tempo de carregamento como causa.

A v2.5.1 corrigiu os hábitos e os testes de instalação do assistente. Esse diagnóstico é um complemento independente; não requer reinstalar ou reconfigurar o bot.

## Executar a leitura

1. Envie `/chat equipe off` e interrompa com Ctrl+C os testes CLI que estejam esperando. Evite iniciar novos pedidos durante a coleta.
2. Extraia o pequeno ZIP de diagnóstico em uma pasta do PC. Mantenha seus quatro arquivos juntos. Python 3.11+ é suficiente; não precisa instalar dependências.
3. Abra `diagnosticar_ollama.bat`. Aguarde o relatório JSON e copie o resultado para o chat. Ele mostra RAM, VRAM/driver quando disponíveis, versão informada pelo CLI, versão do servidor, catálogo e modelos realmente carregados em `/api/ps`.

Por padrão são feitas somente leituras de metadados. O programa não abre `.env`, arquivos do assistente, histórico ou logs, não salva relatório em disco e não gera texto, baixa/desinstala modelos, encerra processos ou modifica configurações. A saída contém campos selecionados, sem mensagens brutas do serviço/comandos. Não é necessário enviar seu `.env` ou dados de uso.

As leituras HTTP têm prazo total de três segundos cada, inclusive cabeçalhos e corpo; os comandos de diagnóstico locais têm limite de cinco segundos. A coleta padrão pode levar aproximadamente vinte segundos quando as consultas não respondem. O diagnóstico não fica repetindo chamadas. Ele acessa diretamente IP de loopback, sem proxy nem redirecionamento.

O endereço padrão é `http://127.0.0.1:11434`, o mesmo endereço local usado nesta investigação. A configuração do `.env` não é carregada. Para uma porta diferente, execute, na pasta extraída:

```powershell
.\diagnosticar_ollama.bat --url http://127.0.0.1:11435
```

Somente IP literal de loopback é aceito. O programa não consulta hosts remotos.

## Interpretar o relatório

- `servico` e `catalogo`: confirmam somente metadados, não inferência.
- `carregados`: mostra as tags realmente carregadas e a memória/contexto informados pelo servidor. Uma tag no catálogo não significa que esteja usando RAM ou VRAM agora.
- `memoria`: total/livre de RAM física. No Windows, os campos `commit_*` representam limite/disponibilidade de commit do sistema, não o tamanho literal do arquivo de paginação.
- `gpu`: VRAM total/livre, utilização e versão do driver obtidas por `nvidia-smi`. Ausência ou falha da ferramenta deixa essa informação desconhecida; não prova ausência ou defeito da GPU.
- `cli`: versão extraída da saída de `ollama --version`; quando há versão explícita do cliente, ela tem preferência. `servico.versao` vem de `/api/version` e permite comparar.

`tamanho_gib` em `catalogo` é o tamanho registrado do modelo. Em `carregados`, vem do campo `size` de `/api/ps`; `vram_gib` vem de `size_vram`. Esses números não são uma medição completa de toda a memória usada pelo processo.

O modelo de 27B informado ocupa cerca de 17 GB e não cabe integralmente nos 6 GB de VRAM da GTX 1660. Ele pode usar RAM/CPU; isso não prova que seja impossível executar nem explica sozinho a falta de resposta do Llama menor. Não aumente paralelismo, contexto ou número de modelos residentes antes de observar os recursos.

## Teste opcional isolado

Abra `testar_ollama_cpu.bat` para solicitar explicitamente **uma** geração curta de `llama3.2:latest` local. O teste exige que a tag esteja no catálogo sem indicação de cloud; não instala modelos. Solicita `num_gpu=0`, contexto 1024, até oito tokens, sem histórico, com prazo total de 30 segundos e `keep_alive=0`. Isso usa RAM/CPU e pode carregar o modelo; após a chamada o serviço recebe a instrução de não mantê-lo carregado.

Essas opções valem somente para a chamada de teste. Nenhum `.env` ou limite global é gravado. O relatório informa se recebeu texto, sem incluir o texto gerado. Metadados mais o teste podem levar aproximadamente cinquenta segundos. Um timeout, mesmo nesse teste, ainda não prova travamento infinito ou falha permanente.

Se o teste CPU responder e a geração padrão não, isso ajuda a investigar GPU/carga/contexto; sozinho não prova defeito do driver, porque o contexto e a quantidade de saída também foram reduzidos. Não há fallback automático do assistente para CPU.

## Recuperação manual com o mínimo de mudanças

Se a janela que executa `ollama serve` estiver com **Selecionar** no título, pressione Esc. Esse modo do console pode bloquear a saída. Mantenha apenas uma instância de serviço: se necessário, saia do Ollama pelo ícone da bandeja e abra novamente, sem iniciar vários `ollama serve` em paralelo. A reabertura interrompe os pedidos atuais; não apaga os modelos.

Se `/api/ps` mostrar um modelo grande carregado que você quer liberar, `ollama stop NOME_EXATO` descarrega essa tag da memória. Isso pode interromper seu uso atual; não exclui seus arquivos. O diagnóstico não faz essa operação automaticamente. Teste primeiro uma tag local menor antes de ativar novamente a equipe inteira.

Não foram modificados drivers, paginação, diretório de modelos ou inicialização do Windows. O programa fornece evidências para escolher o próximo ajuste; não declara o serviço recuperado sem uma geração real concluída.

## Validação e remoção

O código é independente da aplicação e usa somente a biblioteca padrão. Passaram 25 testes específicos, incluindo HTTP em loopback com cabeçalhos/corpos lentos, limites de resposta, campos filtrados, teste CPU com uma tentativa e simulação de GPU/memória Windows. Nenhuma inferência real ou API paga foi usada. A suíte integrada passou com 398 testes Python e 56 verificações JavaScript; a matriz CI Windows/Linux fica registrada no PR.

O ZIP original do assistente v2.5.1 contém 373 testes; os 25 novos pertencem a este complemento. O bot permanece v2.5.1. Para remover o diagnóstico, exclua apenas os quatro arquivos extraídos. Isso não altera o assistente, `.env`, dados, modelos ou serviço.
