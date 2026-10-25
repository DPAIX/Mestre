# Revisão v2.10.1 — corrigir a preparação e retomar pendências

O log de configuração mostrou três causas concretas: o seletor de modelos era oferecido antes de existir uma etapa que iniciasse o Ollama; o campo de modelo 9Router aceitava um valor com aparência de chave; e o Gemini aceitava `sim` como nome de modelo, enquanto a API inválida acabava produzindo uma mensagem genérica sobre Node.js no configurador principal. Escolher `codex` no campo de modelo de outro aplicativo também confundia conceitos.

A correção reordena a preparação do Ollama e acrescenta início explícito com a trava de instância já usada pelo bot. Preserva política de início desabilitado, porta ocupada/incerta, diretório de modelos, `OLLAMA_NO_CLOUD`, limites de tempo e ausência de download/geração. A nova retomada exclui bibliotecas, Telegram, Startup e aplicativos externos já preparados.

Gemini oferece API por número ou nome, valida campos antes da chave e permite correção finita. 9Router valida ID/base/ativação antes da entrada oculta, rejeita credenciais em modelo também no cliente central e permite substituir/remover uma chave inválida no console com confirmação. Mensagens não reproduzem o conteúdo identificado como chave. O modelo dos aplicativos passa a ser escolhido na interface oficial.

Arquivos principais: `configuracao_assistente.py`, `configurar_gemini.py`, `configurar_9router.py`, `roteador_9router.py`, `retomar_configuracao.bat` e testes dos configuradores. Versão, documentação, exportação de fontes e exemplo Colab acompanham o pacote completo.

A base v2.10.0 passou em 903 testes Python, com um teste específico Windows ignorado no Linux, antes das alterações. Foram adicionados testes de ordem/pré-requisito, exclusão mútua, retomada limitada, entradas incorretas, credencial em modelo, correção/remoção de chave e cancelamento sem gravação. Validação local final: 923 testes Python aprovados, com um teste específico Windows ignorado no Linux; 87 testes JavaScript aprovados; compilação e análise estática de 39 fontes sem globais indefinidos. A matriz Windows/Linux com Python 3.11, 3.12 e 3.14 fica nos checks da PR. Nenhuma conta ou chave real foi usada nos testes; o log enviado não integra o código nem o pacote.

Não houve alteração de rede, dados pessoais, modelos ou instalação no PC por esta sessão. A validação real do serviço Ollama, contas e geração continua no Windows. Consulte [passos exatos e reversão](GUIA_RETOMAR_CONFIGURACAO.md).
