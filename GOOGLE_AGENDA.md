# Autorizar Google Agenda

O erro `Configure GOOGLE_OAUTH_CREDENTIALS...` significa que o programa não encontrou um JSON OAuth válido. O autorizador já carregava o `.env`; instalar bibliotecas ou fazer backup não cria esse arquivo.

1. No [Google Cloud](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com), habilite Google Calendar API no seu projeto.
2. Configure a tela de consentimento. Se o aplicativo estiver em teste, adicione a sua conta aos usuários de teste.
3. Em **APIs e serviços → Credenciais → Criar credenciais → ID do cliente OAuth**, escolha **Aplicativo para computador (Desktop app)**.
4. Baixe o JSON. Você pode colocá-lo como `credentials.json` na pasta do assistente ou guardar em outra pasta do seu PC.
5. Execute `autorizar_google.bat`. Se o arquivo não for encontrado, o assistente explica o procedimento e pede apenas o caminho local. Outra opção, no PowerShell aberto na pasta do projeto:

```powershell
.\autorizar_google.bat "C:\minha pasta\credentials.json"
```

O caminho pode ter aspas, ser relativo à pasta do projeto ou usar variáveis como `%USERPROFILE%`. Um caminho explícito é salvo no `.env` somente após validar o JSON; as outras configurações são preservadas. Sem configuração explícita, `credentials.json` ao lado do projeto é reconhecido automaticamente. Um caminho configurado incorreto não é substituído silenciosamente: escolha o arquivo correto no autorizador.

Para conferir o arquivo sem abrir o navegador nem alterar a configuração:

```powershell
.\autorizar_google.bat --verificar "C:\minha pasta\credentials.json"
```

Na autorização, faça login na janela aberta pelo Google e permita a leitura do calendário. O token é salvo atomicamente em `dados/token_google.json`. Depois use `/agenda` no Telegram. Esse fluxo não escreve eventos e não usa chaves de Gemini, OpenAI, Claude ou Exa. A validação local do JSON não confirma que a conta esteja autorizada: isso depende da etapa OAuth no navegador.

Mantenha `credentials.json`, `.env` e o token no computador. Não envie esses arquivos ou seus conteúdos ao chat ou ao GitHub. Não use chave de API, cliente OAuth Web ou conta de serviço neste fluxo.

Se o navegador informar bloqueio de acesso, confira o tipo Desktop, a tela de consentimento e a conta de teste no seu projeto. Se a autorização tiver expirado ou sido revogada, execute o autorizador novamente. Falhas não apagam o token anterior; o programa não anuncia sucesso até o Google concluir o fluxo.

Para reverter a atualização do autorizador, encerre a versão nova e volte à pasta anterior do assistente. Preserve seus arquivos locais de configuração e token. Para desfazer uma seleção de caminho, altere apenas `GOOGLE_OAUTH_CREDENTIALS` no `.env`; isso não modifica outras credenciais.
