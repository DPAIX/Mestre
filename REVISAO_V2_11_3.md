# Revisão v2.11.3 — conexão IPv6 e reinício do 9Remote

## Problema e resultado

O 9Remote gerenciado encontrava sua chave, mas falhava em registrar a sessão externa com `fetch failed`. O diagnóstico real no Windows mostrou DNS rápido, HTTPS IPv6 funcionando e HTTPS IPv4 expirando. A versão 3.0.43 do 9Remote substitui `dns.lookup`, consulta DNS públicos e prefere exclusivamente IPv4 quando há registros A.

`correcao_dns_9remote.py` restaura o lookup nativo do Node nos dois bundles gerenciados exatos. Assim a aplicação pode usar IPv6 e a seleção entre famílias que já respondeu no teste do mesmo Node. A correção é local ao pacote 9Remote; não altera rede do Windows nem TLS.

O mesmo patch remove a limpeza genérica por porta na entrada do CLI e restringe limpeza do cloudflared aos objetos `ChildProcess` criados pelo próprio CLI. Preserva o controle dos filhos conhecidos, sem selecionar navegadores ou processos através de PIDs antigos.

## Aplicação

O [pacote de reparo separado](REPARO_9REMOTE.md) permite abrir `REPARAR_9REMOTE.bat` sem atualizar o bot. O driver identifica os processos do pacote gerenciado e usa HANDLEs Windows antes de reiniciá-los. Se a identidade ou a porta não puderem ser confirmadas, interrompe a execução.

Nas instalações completas, `integracoes_9stack.py` passa a conferir e aplicar o patch antes de concluir a instalação ou lançar o pacote 9Remote. Nome/versão, SHA256 dos bundles e backups precisam concordar; fontes desconhecidas não são sobrescritas. A operação não lê a configuração nem as chaves do 9Remote.

## Validação e limites

O diagnóstico de DNS/HTTPS acima foi executado pelo proprietário no Windows real. A validação local aprovou **1.161 testes Python**, com três casos específicos de Windows ignorados no Linux; a suíte também verifica os fluxos JavaScript. Inclui 64 regressões novas sobre correção, reversão, serialização, identidade e parada restrita de processos. Os processos e arquivos dos testes são fictícios. Os contratos JavaScript executam pequenos blocos em VM sem executar o produto, e os dois bundles completos resultantes passaram por `node --check`. A matriz Windows/Linux consta no PR da entrega.

Os testes não iniciam o 9Remote, não estabelecem sessões remotas e não executam tarefas RoboTask. O pareamento real continua pendente de executar o reparo no computador e conectar o dispositivo de destino. O reparador não possui acesso direto ao PC por meio desta conversa.

## Reversão

`REVERTER_REPARO_9REMOTE.bat` restaura os originais por backup e SHA256, sem relançar a versão original. Detalhes, caminhos e conferência estão no [guia do reparo](REPARO_9REMOTE.md). Os dados, credenciais, modelos e fontes do bot não fazem parte do pacote pequeno de reparo.
