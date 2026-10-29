# Hosts do Spotify e diagnostico de conectividade do Windows

O teste anterior retornou `RESULTADO_PROXY=inalterado`: a mudanca de proxy nao foi confirmada. Este pacote acrescenta uma sonda somente de leitura que identifica a ultima etapa concluida do componente de proxy e testa os endpoints publicos padrao usados pelo Windows para conferir a internet.

## Correcao especifica do hosts

A analise do arquivo enviado encontrou um bloqueio de `wl.spotify.com`, associado a links de conta do Spotify, como confirmacao de e-mail e redefinicao de senha. Nao foram encontrados bloqueios dos endpoints NCSI padrao nem dos endpoints centrais de autenticacao e reproducao do Spotify. Isso nao demonstra que o hosts seja a causa de o aplicativo inteiro estar offline.

1. Extraia `Reparo_Hosts_e_Diagnostico_Windows_v1.zip` em uma pasta.
2. Clique com o botao direito em **CORRIGIR_HOSTS.bat** e escolha **Executar como administrador**. O Windows exige essa permissao para editar seu arquivo de sistema `hosts`.
3. Confira o resultado `HOSTS` exibido. Se o arquivo estiver ocupado ou protegido, o programa informa a falha; nao agenda substituicao no reinicio nem altera permissoes.

O programa atua somente no alias exato `wl.spotify.com` quando associado a um dos destinos de bloqueio previstos. Os outros aliases, comentarios, finais de linha e entradas sao preservados. Enderecos de publicidade, rastreamento, phishing e nomes locais nao sao removidos. O arquivo original e o recibo de restauracao ficam privados, junto ao hosts no computador. O ZIP nao inclui o hosts enviado nem seu conteudo.

Para desfazer, execute **RESTAURAR_HOSTS.bat** como administrador. A restauracao verifica os hashes do backup e do arquivo atual e interrompe se outra alteracao tiver ocorrido. O backup original nao e substituido por uma reaplicacao.

## Investigar a falha que permanece

1. Abra **DIAGNOSTICAR_WINDOWS.bat** normalmente, na conta em que o Spotify e o Firefox sao usados.
2. Aguarde as linhas de resultado. As chamadas de proxy e as sondas HTTP tem limites de espera e usam somente filhos criados pelo teste.
3. Envie as linhas mostradas, ou uma captura da janela. Elas nao mostram tokens, URLs de proxy, corpo de respostas HTTP ou outros dados do hosts.

A consulta nao tenta alterar o proxy novamente. Ela confere o inicio do Python, identidade, registro, carregamento WinINet e consulta de flags para localizar a etapa que nao responde. A sonda NCSI le o estado de sondagem e verifica as paginas publicas padrao separadamente por IPv4 e IPv6, sem usar proxy e sem seguir redirecionamentos. Destinos NCSI personalizados sao sinalizados, sem serem exibidos ou acessados pelo programa.

Depois de um resultado `HOSTS` aplicado, saia do Spotify pelo icone na bandeja e abra-o novamente para conferir os links de conta. A recuperacao do aplicativo inteiro e do indicador de rede precisa ser conferida no PC; o diagnostico permite decidir o proximo ajuste com base no resultado.

## Validacao

Testes automatizados usam arquivos sinteticos e registro, processos e APIs Windows simulados. A copia enviada e analisada apenas no ambiente privado; ela nao vira fixture nem arquivo de distribuicao. Compilacao e testes nao comprovam funcionamento real do Spotify.

Referencias: https://github.com/StevenBlack/hosts/issues/1727 e https://github.com/StevenBlack/hosts/issues/3001 ; https://learn.microsoft.com/en-us/troubleshoot/windows-server/networking/troubleshoot-ncsi-guidance
