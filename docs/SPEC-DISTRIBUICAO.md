# Distribuição Windows

## Contrato

- Distribuir instalador por usuário e ZIP com `ComprasTG.exe` para Windows x64.
- Ambos incluem Electron, Python embutido e dependências Python; o usuário não instala Node.js ou Python.
- Executar monitor, configuração e worker com o mesmo Python embutido, fora do ASAR.
- Em desenvolvimento, manter Python pelo PATH e dados na raiz.
- No aplicativo empacotado, persistir dados em `app.getPath('userData')/data`; criar o diretório antes de abrir processos. Atualizar ou extrair outra versão não apaga esses dados.
- `COMPRAS_DATA_DIR` continua permitindo diretório explícito; não importar dados pessoais do workspace.
- Empacotar somente arquivos de aplicação explicitamente selecionados. Não incluir `.env`, sessão, bancos, listas pessoais, backups, locks ou logs.
- Validar o EXE empacotado com diretório temporário, PATH sem Python/Node, renderer, preload, configuração, simulador, catálogo e worker. Não autenticar nem acessar Telegram real.
- Publicar binários e SHA256 em uma nova release, preservando a release anterior.

## Aceitação

1. Instalação por usuário, sem exigir administrador, com atalho para abrir o app.
2. ZIP extraído abre pelo EXE e encontra seus recursos em pastas com espaços.
3. Dados são gravados fora da instalação, inclusive quando ela não tem permissão de escrita.
4. Falta do runtime embutido produz erro visível, sem buscar Python no computador.
5. Smoke do EXE confirma funcionalidades locais sem criar sessão Telegram ou seen.db.

## Limites

Publicação inicial sem certificado de assinatura de código. Autenticação e envio reais permanecem validações manuais. O ZIP deve ser extraído inteiro; o EXE depende dos recursos que o acompanham.
