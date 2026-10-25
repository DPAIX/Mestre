# v2.9.1 — configuração local sem depender de IA

## Causa e correção

A captura confirma que a resposta local sobre capacidades da v2.9.0 funcionou. Entretanto, “faça as configurações necessárias” não tinha intenção local reconhecida: `interpretar_local` retornava `None`, o fluxo acionava a equipe e o primeiro Llama atingia o prazo. O diagnóstico curto que respondeu antes não equivale ao prompt cooperativo completo; não foi comprovada a causa da lentidão do Ollama no Windows.

A frase exata, “configure o assistente” e variantes completas agora preparam uma configuração local confirmável. Consultas como “mostre a configuração do assistente” produzem um resumo local sem chamar modelos. Negativas, citações, condições, pedidos compostos e alvos específicos continuam preservados. Uma resposta da IA não pode iniciar esse configurador.

Após confirmar, abre-se uma janela no PC com uma passagem finita por etapas permitidas: instalar pacotes gerenciados faltantes, iniciar/abrir o 9Router, configurar modelo/combo e chave opcional pelo console, consultar metadados do Ollama e abrir a UI do 9Remote. Cada etapa é apresentada ao proprietário; pacotes presentes não são reinstalados. Login e escolhas de conta/modelo continuam na janela oficial. Node.js 22+ ausente permanece uma pendência com link oficial. Não há instalação de bibliotecas Python enquanto o bot está usando o ambiente.

Não se inicia túnel remoto, ativa nuvem, escolhe modelo pago ou testa geração automaticamente. A configuração não é declarada concluída só porque a janela abriu. Etapas recusadas ou com falha continuam pendentes. Se uma credencial for salva no console, o bot deve ser reiniciado para recarregá-la.

Também foi corrigido um aviso incorreto da equipe: participantes adiados depois do timeout não emitem mais o evento “início” que o Telegram traduzia como “Consultando modelo”. Os prazos, payloads e a política de não repetir gerações permanecem preservados.

## Arquivos e validação

- `configuracao_assistente.py` e `configurar_assistente.bat`: assistente local, resumo, confirmação, janela separada e etapas fixas; ambiente filho sem chaves do bot e controle de duplicação.
- `interpretacao_natural.py`: gramática de frases completas, validação de planos e bloqueio de configuração originada em LLM.
- `assistente_pc.py` e `painel_rotina.html`: Telegram, botão Configurar assistente, diagnóstico autenticado, cartões confirmáveis e cancelamento por nonce, isolados por conversa.
- `conversa_equipe.py`: progresso fiel aos participantes efetivamente consultados.
- Autoanálise, exportação e testes incluem o novo módulo.

Baseline: 802 testes Python e compilação aprovados. Final: **836 testes Python, 83 verificações JavaScript, compilação e auditoria estática de 34 módulos aprovados**. As 34 novas regressões Python cobrem a frase da imagem, condições/negações, ausência de IA, confirmação/cancelamento/autorização, isolamento de conversa, configurador e progresso de adiamentos. O resultado da matriz Windows/Linux consta no PR.

Não foram lidos `.env` ou dados privados. As instalações, subprocessos, portas e navegadores dos testes são simulados. Não houve geração real, login, conexão Telegram, ação Windows ou acesso remoto nesta validação. O único comportamento reproduzido da falha foi o encaminhamento incorreto para IA; o timeout real no computador não é declarado corrigido por testes simulados.

## Aplicar no Windows

1. Encerre o bot e faça backup das fontes atuais. Preserve `.venv`, `F:\MeuControlePC_v2\.env`, dados, modelos e backups.
2. Extraia o ZIP v2.9.1 separadamente e copie **o conteúdo da pasta interna** para `C:\Users\Mestre\Documents\GitHub\Mestre`, substituindo as fontes completas.
3. Abra `atualizar_assistente.bat` e confira v2.9.1 no console.
4. Envie novamente **“faça as configurações necessárias”** e confirme **Executar**. Acompanhe a janela de configuração no PC; essa etapa não espera uma resposta do Ollama.

Alternativas: botão Telegram **Configurar assistente**, cartão de configuração local na aba **Integrações & memória**, ou duplo clique em `configurar_assistente.bat`. Para apenas consultar pendências, use “mostre a configuração do assistente” ou **Verificar configuração local** no painel.

Se faltar Node.js, instale o LTS 22+ com npm pelo [site oficial](https://nodejs.org/en/download), reabra o terminal e repita somente a etapa pendente. Contas/combos/credenciais devem ser configurados no PC. Instalação de terceiros ou timeout não comprovam funcionamento de geração, saldo ou encerramento de scripts filhos.

## Reverter

Encerre o bot e restaure todas as fontes auditadas v2.9.0, mantendo os registros atuais. A troca de fontes não apaga contas ou pacotes externos nem encerra seus processos. Use as interfaces oficiais para encerrar serviços/remover dispositivos, se desejado. O Startup e as integrações já configuradas permanecem no local atual.

[Guia das integrações da v2.9](GUIA_INTEGRACOES_V2_9.md).
