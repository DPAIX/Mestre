# Reparo de conexão do 9Remote 3.0.43

Extraia o pacote pequeno em Downloads e abra **`REPARAR_9REMOTE.bat`**. Ele usa o Python já instalado com o assistente, confere os arquivos oficiais, guarda os originais, reinicia somente os processos identificados do 9Remote gerenciado e abre **http://127.0.0.1:2208/ui/index.html**.

Não é necessário reinstalar o bot ou copiar configurações. A chave existente do 9Remote continua sendo usada. O reparador não solicita que ela seja enviada ao chat.

## Causa confirmada pelo diagnóstico

No computador analisado, o DNS do Windows e os DNS públicos responderam em cerca de 60 ms. O acesso HTTPS por IPv6 respondeu HTTP 200 em 262 ms; o acesso por IPv4 expirou. O 9Remote 3.0.43 substitui o `dns.lookup` do Node e, havendo respostas IPv4, descarta as respostas IPv6. Isso reproduziu a falha de conexão dessa instalação.

O reparo mantém o `dns.lookup` nativo do Node nos dois bundles do pacote. O Node pode usar as duas famílias conforme o suporte de sua rede, incluindo o caminho IPv6 já demonstrado funcionando. DNS, hosts, adaptadores, proxy, firewall e configurações do navegador do Windows não são modificados.

## O que o reparador confere

- Pacote gerenciado em `%LOCALAPPDATA%\MeuControlePC\integracoes\9remote\node_modules\9remote`, nome `9remote` e versão `3.0.43`.
- SHA256 dos dois bundles completos e transformações literais únicas. Outra versão ou arquivo modificado causa interrupção antes de sobrescrever as fontes.
- Backups dos originais em `.meucontrolepc-dns-3.0.43`, dentro da pasta do pacote. Repetir o reparo reconhece a correção existente.
- Executável, argumentos, proprietário e HANDLE dos processos antes de reiniciá-los. Um processo desconhecido na porta 2208 impede o reinício automático.

O CLI original usa encerramento genérico por porta/PID em algumas rotinas de limpeza. A correção remove a seleção por porta e limita a limpeza do cloudflared aos objetos de processos filhos criados pelo CLI atual. O reparador não usa o shutdown original, `taskkill` genérico nem o nome `node.exe` como critério de encerramento.

O daemon PTY existente é preservado pelo reparador. O próprio 9Remote mantém seus controles de dispositivos, permissões e eventual migração do daemon por versão.

## Conferir no Windows

O painel do host deve avançar na conexão e mostrar as opções de pareamento. Use a chave/QR somente no dispositivo que deseja parear. Abrir o painel local comprova apenas que o servidor local respondeu; uma sessão remota precisa ser conectada e conferida no dispositivo de destino.

Se o reparador interromper, copie apenas sua mensagem de erro. Não envie chaves, QR codes, URLs de pareamento, arquivos `.env` ou a resposta completa de `/api/ui/state`.

## Reverter

Abra **`REVERTER_REPARO_9REMOTE.bat`**. Ele usa os backups conferidos para restaurar os dois bundles. A versão original não é relançada automaticamente. Os backups são preservados; executar `REPARAR_9REMOTE.bat` permite reaplicar.

O assistente v2.11.3 também aplica esta correção ao instalar ou iniciar seu pacote gerenciado. Para conservar os bundles originais após uma reversão, não solicite uma nova instalação/abertura do 9Remote por essa versão do assistente.

Fontes oficiais inspecionadas sem execução: `9remote@3.0.43`, commit upstream [`5f54ea2d70d8ea773676ca0f52419eecffe81d06`](https://github.com/decolua/9remote/tree/5f54ea2d70d8ea773676ca0f52419eecffe81d06), especialmente [`host/lib/constants.js`](https://github.com/decolua/9remote/blob/5f54ea2d70d8ea773676ca0f52419eecffe81d06/host/lib/constants.js).
