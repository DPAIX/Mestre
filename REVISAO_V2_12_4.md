# MeuControlePC v2.12.4 — primeira instalação em F:

A preparação da v2.12.3 parava em “Instância anterior” quando
F:\MeuControlePC_v2\aplicativo ainda não continha assistente_pc.py.
O verificador exigia o arquivo antes de consultar a trava dos dados, embora
a cópia das fontes fosse uma etapa posterior. A falha acabava exibida como
“A etapa encerrou sem confirmação”. Esse caso foi reproduzido em testes.

Agora o verificador consulta a trava antes de exigir fontes instaladas.
Com os dados livres, a instalação pode implantar no destino novo. Se houver
instância ativa e faltarem as fontes do destino, pede para fechar a janela
do assistente anterior. Não escolhe outro processo nem remove a trava.
As verificações de identidade, caminhos, links e junctions são preservadas.

Falhas da preparação passam a mostrar um código público e uma orientação
na etapa correspondente. Mensagens de exceção, credenciais, ambiente e
argumentos dos processos não aparecem na interface.

## Aplicar no PC

1. Feche o console antigo que mostra “Preparação automática”. Fechar apenas
   a aba não encerra esse preparador. Feche também a janela do assistente
   anterior se ainda estiver aberta.
2. Salve e extraia o ZIP novo em **F:\Instaladores**, em uma pasta nova,
   fora de F:\MeuControlePC_v2\aplicativo.
3. Abra **INSTALAR_EM_F_COM_27B.bat** no pacote novo. Não use Retomar na
   página antiga: ela ainda executa a versão anterior em memória.
4. Confira se “Instância anterior” conclui e a etapa “Fontes e backup”
   aparece. A preparação dos modelos continua sujeita à conferência local.

Todos os destinos da v2.12.3 continuam em F:, incluindo código, venv,
modelos, caches, temporários e backups. Configuração e dados existentes
são preservados. O pequeno atalho de logon continua na pasta do Windows,
apontando para F:.

## Validação e reversão

Os testes de regressão usam destino inexistente, diretório vazio e dados
temporários com o verificador real, além de processos e serviços simulados.
Conferem que a implantação começa com a trava livre e que uma trava ativa
continua bloqueando a cópia e o início de outro bot. Falhas de acesso e
exceções com credenciais fictícias geram somente códigos públicos.

Testes locais e CI não substituem a instalação no computador do usuário.
Não foram baixados pesos nem executados serviços Windows reais nesta revisão.

Para reverter as fontes, encerre assistente/preparador e restaure o backup
verificado em F:\MeuControlePC_v2\backups_codigo. Preserve configuração,
dados e alterações posteriores. A revisão não muda opções de rede nem o
arquivo hosts; a reversão do 27B segue RESTAURAR_27B_LEVE.bat.
