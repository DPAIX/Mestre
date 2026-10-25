# Concluir a conexão local do 9Router

As capturas mostram o dashboard 9Router 0.5.109 acessível no PC, exigência de chave ligada e falha na verificação do túnel público. São estados diferentes: o túnel não é necessário para o MeuControlePC conversar com o gateway no mesmo computador. O catálogo e a renovação de tokens também não comprovam uma geração com o modelo escolhido.

## Atualização do assistente

As fontes completas v2.10.2 e o pacote em `distribuicao/MeuControlePC_v2_10_2_integrado.zip` correspondem à branch `codex/correcoes-melhorias`, na PR #4. A página `main` mostrada nas capturas ainda era anterior a essa atualização.

Encerre bot/painel e copie o conteúdo da pasta `MeuControlePC_v2_10_2` para `C:\Users\Mestre\Documents\GitHub\Mestre`. Preserve `F:\MeuControlePC_v2\.env`, dados e pesos. Não substitua seu `.env` pelo exemplo. Para retomar a configuração já preparada, use `retomar_configuracao.bat`; não precisa repetir bibliotecas, Telegram ou Startup.

## Endpoint, chave e modelo

Use estas três informações em seus campos próprios:

| Campo | Valor/origem |
| --- | --- |
| Base local | `http://127.0.0.1:20128/v1` |
| Chave | Uma chave válida criada no dashboard 9Router; entrada oculta do configurador |
| Modelo de conversa/combo | O identificador exato no catálogo de modelos ou o nome/ID de um combo configurado |

As imagens compartilhadas expõem chaves completas. Renove as chaves expostas no 9Router e digite as novas somente na entrada oculta; não as compartilhe em capturas ou mensagens. Como **Require API key** está ativo, o cliente precisa de chave válida: apagar a chave não resolve a autenticação nessa configuração.

No dashboard, conecte o provedor em **Providers** e escolha um modelo de conversa disponível àquela conta. Para um combo, configure-o em **Combo & Vision Adapter** e use seu identificador exato. A listagem `/v1/models` usa `data[].id`; combos são identificados pelo catálogo como `owned_by: combo`. A existência no catálogo não garante cota ou acesso à geração.

No configurador local do MeuControlePC:

1. Informe esse ID no campo de modelo/combo, sem colar uma chave ali.
2. Use a base local acima. A URL pública do túnel não é necessária para este caso.
3. Autorize a ativação quando o provedor/modelo estiver configurado.
4. Digite a chave renovada no campo oculto e confirme a gravação.
5. Inicie com `iniciar_redirecionado.bat` e, no painel `http://127.0.0.1:8765`, atualize o catálogo 9Router e escolha o mesmo ID.
6. Use o botão de teste explícito para uma única geração curta. Um catálogo lido com sucesso verifica metadados, não esse último passo.

Se usar **Usar nesta conversa**, a seleção é isolada e não muda o modelo global. Para escolher o gateway em outra conversa, faça a seleção nela. O teste pode consumir cota do provedor.

## Túnel e acesso remoto

O log do 9Router mostra um timeout de 60 segundos na verificação de `/api/health` da URL pública. Isso não comprova queda da Internet do Windows nem falha do endpoint local.

Para uso apenas no mesmo PC, mantenha a integração apontando para a base local. Se não precisa de acesso externo agora, o túnel pode ser desligado pelo próprio controle da interface oficial; a falha dele não deve impedir o teste local. Não é necessário mudar DNS, proxy, adaptadores ou Tailscale para completar essa ligação. A sessão 9Remote tem configuração e pareamento próprios; ela não se torna pronta por haver uma URL de túnel 9Router.

## CLI Tools e áudio das capturas

- **Not configured** indica instalação detectada sem a configuração correspondente para o 9Router. Abra o cartão do aplicativo para a configuração oficial. Isso é separado do lançador Ollama integrado ao MeuControlePC.
- **Not installed** indica que a instalação não foi detectada. **Guide** oferece instruções; não comprova que o aplicativo esteja configurado.
- Em AssemblyAI aparece **No connections yet**: falta uma conexão desse provedor antes de testar sua transcrição.
- As telas Google/Gemini TTS e STT são exemplos com requisições; sem uma resposta executada não demonstram áudio ou transcrição concluídos. IDs de TTS/STT não devem ser usados como modelos de conversa.
- A voz local Whisper do MeuControlePC e os provedores de mídia do 9Router são integrações diferentes. Configurar uma tela de mídia não troca automaticamente o transcritor da aplicação.

Conclua primeiro um teste de conversa local. Depois configure cada aplicativo ou provedor de mídia pela sua interface, conforme a conta e a função desejadas. A atualização v2.10.2 corrige os fluxos do assistente; não executa instaladores, gerações, túneis ou alterações no PC ao ser extraída.

## Fontes

- [9Router: configuração e descoberta](https://github.com/decolua/9router/blob/master/skills/9router/SKILL.md)
- [Conversa](https://github.com/decolua/9router/blob/master/skills/9router-chat/SKILL.md)
- [Verificação de saúde do túnel](https://github.com/decolua/9router/blob/master/src/lib/tunnel/cloudflare/healthCheck.js)
- [Estados de ferramentas CLI](https://github.com/decolua/9router/blob/master/src/app/%28dashboard%29/dashboard/cli-tools/components/ToolSummaryCard.js)
- [TTS](https://github.com/decolua/9router/blob/master/skills/9router-tts/SKILL.md) e [STT](https://github.com/decolua/9router/blob/master/skills/9router-stt/SKILL.md)
