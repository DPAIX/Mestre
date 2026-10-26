# Teste reversivel da deteccao automatica de proxy

O Firefox voltou a carregar sites depois de selecionar **Sem proxy**. A consulta das configuracoes persistidas do Windows mostrou proxy manual e script desativados, com **deteccao automatica ativada**. As duas interfaces de configuracao de proxy ficaram sem responder. Esses resultados sustentam testar a deteccao automatica; ainda nao confirmam a causa da falha do Spotify nem do indicador de conectividade do Windows.

## Executar no computador apresentado

1. Baixe e extraia todos os arquivos de `Teste_Proxy_Windows_v1.zip` em uma pasta de Downloads.
2. Abra **TESTAR_SEM_DETECCAO.bat**. Ele usa o Python ja instalado com o assistente.
3. Aguarde a linha `RESULTADO_PROXY` na janela. O estado anterior e guardado localmente antes do ajuste.
4. Na bandeja do Windows, junto ao relogio, clique com o botao direito no icone do Spotify e escolha **Sair**. Abra o Spotify novamente.
5. Informe a linha `RESULTADO_PROXY`, se o Spotify carrega e se o indicador de rede se atualiza.

O iniciador altera somente a deteccao automatica de proxy da conexao LAN do usuario, usando a API WinINet do Windows. A configuracao de proxy e conferida novamente antes de aplicar. Os enderecos de proxy e script nao sao copiados nem exibidos. O ajuste nao altera DNS, hosts, adaptadores, firewall, WinHTTP, modelos ou configuracao do assistente.

As chamadas que podem travar rodam em processos filhos exclusivos do teste, com limite de espera. Quando uma chamada nao retorna, o programa confere o estado persistido para distinguir ajuste aplicado, estado inalterado e resultado incerto. Ele nao repete a alteracao automaticamente. A verificacao final de navegacao e do Spotify ocorre no PC.

## Restauracao

Abra **RESTAURAR_DETECCAO.bat** na mesma conta do Windows. O programa usa o backup local em `%LOCALAPPDATA%\MeuControlePC\reparo_proxy` e verifica se o estado atual ainda corresponde ao ajuste deste teste antes de restaurar. Nao substitua o backup por arquivos enviados por outras pessoas. Quando outra configuracao tiver mudado, a restauracao interrompe e informa a divergencia.

## Validacao e limites

O codigo e os testes ficam em `ajustar_autodeteccao_proxy.py` e `testes/test_ajustar_autodeteccao_proxy.py`. Testes automatizados usam registro, API Windows e processos simulados; nao alteram a rede real. A execucao no Windows do usuario e a recuperacao do Spotify ainda precisam ser conferidas. Nao e um teste de acesso real a APIs de IA nem ao Telegram.

Referencia da API: https://learn.microsoft.com/en-us/windows/win32/api/wininet/ns-wininet-internet_per_conn_optionw
