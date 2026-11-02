# ComprasTG v0.1.1 — Windows x64

Instalador e ZIP com executável, incluindo Python, Electron e dependências. Não é necessário instalar Python ou Node.js.

## Download e abertura

- **Instalador:** execute `ComprasTG-0.1.1-setup-x64.exe` e abra o ComprasTG pelo atalho. Instalação por usuário, sem exigir administrador.
- **ZIP:** extraia `ComprasTG-0.1.1-windows-x64.zip` inteiro e abra `ComprasTG.exe`. Mantenha todos os arquivos extraídos juntos.
- **Integridade:** confira os hashes dos downloads em `SHA256SUMS.txt`.

Requer Windows 10/11 de 64 bits. Os executáveis não têm assinatura digital nesta versão.

## Primeira configuração

Abra Configurações, preencha API ID, API Hash e telefone da sua aplicação Telegram e autorize a conta. Depois atualize/selecione os grupos, cadastre as regras e inicie o monitor.

Dados ficam em `%APPDATA%\ComprasTG\data`, fora da instalação. O ZIP compartilha essa mesma pasta: os dados não ficam ao lado do EXE. Não há importação automática da pasta usada na execução pelo código-fonte. A release não contém credenciais, sessão, listas pessoais ou bancos do desenvolvedor.

## Validação

- Testes focados para caminhos de runtime, processos e protocolo; testes Python de segurança, regras e catálogo.
- Build e lint aprovados.
- EXE empacotado validado com dados temporários e PATH sem Python/Node: renderer, preload, IPC, configuração, simulador, catálogo e worker.
- Validação do ZIP extraído em pasta com espaços e da pasta padrão de dados do aplicativo.
- Nenhuma autenticação ou mensagem enviada ao Telegram nos testes.

Autenticação e entrega reais permanecem validações manuais. Fechar o app encerra o monitor; mudanças de configuração exigem reinício do monitor.

[Manual do usuário](https://github.com/brunocouri/botWebScrapperComprasTG/blob/v0.1.1/docs/MANUAL-USUARIO.md)
