# MeuControlePC v2.4.0 — conversa, interpretação e correções de configuração

## Problema e resultado

O usuário conseguia testar provedores, mas mensagens comuns eram recusadas quando o modo contínuo estava desligado; o assistente respondia texto sem preparar ferramentas. Os prints também mostram Google OAuth sem caminho válido e teste do padrão Ollama com HTTP 404. Backup/CSV não corrigem essas condições.

A versão habilita conversa comum por padrão para proprietários autorizados, preserva `/chat modo off` e cria um fluxo de interpretação: reconhecimento local para pedidos completos e resposta estruturada da IA para linguagem livre. Planos passam por validação de lista permitida. Consultas usam os dados locais/agenda autorizada; alterações aguardam confirmação vinculada à conversa. Execução não vem do texto do modelo: é feita pelas funções do assistente após o proprietário confirmar.

## Arquivos e comportamento

- `interpretacao_natural.py`: reconhecimento local, validação de ações/campos/valores/datas e extração estrita de resposta JSON. Sem execução, arquivos ou shell.
- `servicos_chat.py`: histórico com interpretação opcional, referência temporal, resultado como proposta; ação de padrão Ollama salva somente três opções e atualiza o processo sem reinício.
- `assistente_pc.py`: mensagens comuns, leituras reais, ações propostas, confirmação/cancelamento por nonce e texto, expiração, vínculo com conversa e proteção contra repetição. Captura aparece após confirmação no painel; dados binários não são corrompidos pela redação textual. Conclusão natural de atividade é idempotente.
- `colaboracao_chats.py`: conversa contínua padrão e marcador de atualização compatível com JSON antigo; exportação inclui módulos/guias novos, sem histórico/credenciais/dados operacionais.
- `painel_rotina.html`: cartões de ação e seleção do padrão Ollama; mensagens naturais e controle de conversa; renderização como texto.
- `multi_ia.py`: pausa padrão Ollama identificada por hash de configuração, descarte seletivo após troca de modelo/URL, proteção contra resultados atrasados e diagnóstico 404 com uma leitura de catálogo, sem repetir inferência. Pausas de outros provedores são preservadas.
- `agenda_google.py`, `autorizar_google.py`, `.bat` e `GOOGLE_AGENDA.md`: resolução de caminho contra a pasta do projeto, seleção/validação OAuth Desktop, erros controlados e gravação atômica de configuração/token. O autorizador já carregava `.env`; o problema era o caminho/arquivo ausente ou inválido.
- `evolucao_segura.py`, testes e documentação: auditoria de sintaxe do módulo novo e regressões das integrações.

## Verificação

Baseline v2.3.2: 211 testes Python aprovados antes das mudanças. Nova suíte: 264 testes Python e 36 testes JavaScript aprovados, além de compilação. A cobertura inclui interpretação, propostas inválidas, execução só após confirmação, cancelamento/expiração/repetição, outros proprietários e conversas, finanças/atividades, contexto, captura, configuração Ollama e OAuth com arquivos temporários. A matriz Windows/Linux fica na descrição do PR. Sintaxe e IDs do painel, diff e integridade do ZIP também são verificados na entrega.

Os testes usam mocks e servidor HTTP loopback que simula o protocolo Ollama. Não fazem inferência em modelos reais, login Google, envio Telegram, hotkeys, abertura de programas ou ações destrutivas. Nenhum saldo é recuperado pelo código. A resposta Gemini/Exa mostrada no print é evidência daquela consulta no PC do usuário, não validação efetuada neste ambiente.

## Validar e reverter

Siga [GUIA_CONVERSA.md](GUIA_CONVERSA.md). Atualize em pasta nova, mantenha seus dados/configuração locais, encerre a versão anterior e inicie a nova. Converse, consulte sua rotina e prepare uma ação pequena; confira a descrição e confirme/cancele. Liste o catálogo Ollama e escolha uma tag presente. Para Google, use o JSON OAuth Desktop do seu próprio projeto e conclua o navegador.

Para reverter, encerre a v2.4.0 e inicie a pasta v2.3.2 com uma cópia preservada dos dados. Campos novos dos chats são adicionais, sem troca de esquema. As três opções Ollama salvas são compatíveis com a versão anterior; se voltar a um modelo antigo, selecione-o na pasta anterior. Tokens/credenciais Google permanecem locais e não precisam ser apagados para reverter.

Conversa contínua passa a estar ligada nesta atualização para atender à solicitação do proprietário; desative por contexto com `/chat modo off`. As mensagens vão ao provedor selecionado e podem consumir cota. Windows, modelos grandes, rede e OAuth continuam dependendo da máquina/conta. Google Calendar permanece somente leitura; agendamentos naturais entram na rotina local. O assistente não ganha execução arbitrária de código nem dispensa as confirmações das ações existentes.
