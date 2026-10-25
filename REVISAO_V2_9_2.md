# v2.9.2 — diagnóstico da navegação no Windows

## Situação observada e alcance

O usuário relatou que apenas o PC perde a navegação ao abrir alguns programas,
possivelmente o Ollama: o Windows continua indicando conexão e as páginas ficam
carregando, sem código de erro. Ainda não há medição no computador para confirmar
se a falha é de DNS, proxy/VPN, adaptador, software de proteção ou recursos do PC.
Não há dispositivo Windows conectado ao ambiente desta revisão.

Na foto posterior, o serviço Tailscale está presente e o Cliente DNS aparece com
cerca de 15% de CPU; memória total em uso, 41%. Isso orienta um teste reversível de
desconexão do Tailscale e limpeza do cache DNS, sem confirmar causalidade. A captura
isolada não mostra saturação da memória nem comprova o estado da VPN ou do DNS.

A auditoria não encontrou comandos que alterem DNS, proxy, rotas, adaptadores,
firewall ou Winsock nas fontes de inicialização do assistente. O início normal
consulta metadados locais do Ollama e pode iniciar `ollama serve`; não baixa pesos
nem abre agentes, 9Router ou 9Remote nessa etapa. Instalações explícitas, downloads
de modelos, serviços de nuvem e os próprios aplicativos externos podem usar rede.
Isso não comprova que algum deles cause a interrupção.

## Mudanças

- `iniciar_servicos_locais.py`: preserva `OLLAMA_NO_CLOUD=1` quando a variável já
  estiver habilitada (`1` ou `true`, sem distinguir maiúsculas). O filtro de
  ambiente do processo antes descartava essa opção. O bloqueio não é ativado
  automaticamente, não modifica um Ollama já aberto e não configura outros
  agentes ou provedores. É uma correção de configuração, sem comprovação de
  relação com a queda da internet.
- `diagnostico_rede.py` e `diagnosticar_rede.bat`: verificação explícita, finita e
  somente de leitura, independente do bot, dos modelos e de pacotes Python
  adicionais. Registra metadados de conectividade e recursos em relatórios locais.
- Testes de regressão da configuração e do diagnóstico; atualização da versão,
  das listas de fontes e da exclusão de relatórios locais do Git e da distribuição.

O diagnóstico não instala pacotes, baixa modelos, abre programas, interrompe
processos, reinicia o Windows nem redefine a rede. Também não lê `.env`, dados do
assistente, históricos, perfis do navegador ou linhas de comando de processos.

## Como observar a falha

1. Extraia o pacote em uma pasta nova. É possível rodar o diagnóstico nessa pasta,
   sem substituir a instalação existente. Python 3.11+ deve estar disponível;
   o `.bat` também procura os ambientes virtuais existentes em C: e F:.
2. Com a internet funcionando, abra `diagnosticar_rede.bat`, sem administrador.
3. Durante a verificação, abra somente um dos programas suspeitos. Observe o
   momento em que as páginas deixam de carregar. Evite iniciar instalações ou
   downloads extras durante a medição.
4. Ao terminar, leia o resumo em `diagnosticos_rede/`. Compartilhe o resumo e o
   nome do programa aberto; o relatório JSON fica local para análise posterior.

A execução faz pequenos testes de TCP na porta 443 de `1.1.1.1` e `9.9.9.9` e
consulta DNS de `example.com`, além de observar metadados locais. Esses testes
usam a conexão do PC; não são um teste de velocidade nem navegação autenticada.
Nenhum relatório é enviado automaticamente. Os arquivos excluem endereços IP e
MAC locais, SSID, nome de usuário, URLs de proxy/PAC e credenciais.

## Como interpretar sem concluir uma causa indevida

| Observação | Próximo ponto a investigar |
| --- | --- |
| TCP externo responde e o teste DNS falha | Resolução DNS; falha isolada de um domínio também é possível |
| Testes externos deixam de responder | Caminho do PC até a internet; firewall ou bloqueio desses destinos também é possível |
| DNS e TCP respondem mas o navegador trava | Proxy/PAC, VPN, navegador, proteção web e recursos do PC |
| Estado de adaptador muda junto à falha | Adaptador, driver ou ligação local |
| Memória disponível cai muito ou CPU fica alta | Pressão de recursos; é correlação, não confirmação de falha de rede |

Gateway pode bloquear ping mesmo funcionando. TCP direto não passa pelo proxy do
navegador e não valida TLS, HTTP ou todas as páginas da internet. A presença de
proxy/PAC ou de um processo não prova que ele esteja com defeito. Nenhuma dessas
observações justifica automaticamente um reset de rede ou mudança de DNS.

## Validação e limites

Os testes usam respostas locais simuladas para falhas e metadados, sem acessar
Telegram, modelos ou destinos externos. Em Windows, o teste de sintaxe analisa o
PowerShell fixo sem executar os probes. Os resultados finais da suíte e do CI
constam no PR desta entrega. A medição real e o reparo específico ainda dependem
da reprodução da falha no PC do usuário.

## Aplicação e reversão

Para usar apenas a verificação, execute os dois arquivos novos na pasta extraída.
Para aplicar também a correção de inicialização, encerre o assistente, faça backup
das fontes e copie as fontes desta versão para a pasta de código em C:. Preserve
`.env`, `dados`, `.venv`, pesos Ollama e configuração de Startup em F:. Não é
necessário reinstalar dependências para as duas mudanças desta revisão. Reinicie
apenas o assistente pelo lançador habitual. Um Ollama já em execução mantém seu
ambiente anterior; a correção vale na próxima inicialização dele pelo assistente.

Para reverter, restaure as fontes v2.9.1 do backup e reinicie o assistente. Os
relatórios novos podem ser removidos manualmente depois de analisados. Não há
alteração de configuração de rede para desfazer.
