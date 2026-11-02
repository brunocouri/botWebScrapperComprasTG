# ComprasTG

Desktop e CLI que monitoram palavras-chave nos grupos da sua conta Telegram e enviam oportunidades para Mensagens Salvas, via Telethon/MTProto.

Inclui regras por preço e prioridade, simulador sem envio, atividade em tempo real e catálogo opcional para arquivar e pesquisar ofertas. Usa a sua conta Telegram; não é um bot criado pelo BotFather.

## Download

Baixe `ComprasTG-v0.1.0-source.zip` em [Releases](https://github.com/brunocouri/botWebScrapperComprasTG/releases) e extraia em uma pasta. A release distribui código-fonte: requer Python e Node.js instalados e não inclui instalador nem executável autossuficiente.

Também é possível clonar:

```powershell
git clone https://github.com/brunocouri/botWebScrapperComprasTG.git
cd botWebScrapperComprasTG
```

## Instalar e abrir

Requer Python e Node.js no PATH. Ambiente validado: Python 3.14.5, Telethon 1.40.0, Electron 44.10.0.

Use Node.js 22.12 ou superior. Abra o terminal na pasta extraída ou clonada. Os comandos abaixo usam um ambiente Python isolado; mantenha-o ativado ao iniciar o Electron, pois o aplicativo executa `python` pelo PATH.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cd electron
npm ci
npm run build
npm start
```

1. Em Configurações, preencha API ID, API Hash e telefone internacional. Obtenha as credenciais em https://my.telegram.org/apps.
2. Clique em Autorizar conta e informe código e senha 2FA, quando solicitada.
3. Em Grupos, use Atualizar do Telegram e selecione os grupos.
4. Cadastre palavras-chave, faixas e prioridade. O simulador permite conferir uma oferta sem enviar ou marcar mensagens.
5. Inicie o monitor e aguarde Monitorando. Fechar o aplicativo encerra o monitor; não há tray implementado.

Nas próximas aberturas, na raiz do projeto:

```powershell
.\.venv\Scripts\Activate.ps1
cd electron
npm start
```

Mudanças salvas durante monitoramento só entram após reiniciar. A interface compara configuração salva/aplicada.

## CLI

Execute na raiz:

Copie `.env.example` para `.env` e substitua os exemplos pelas suas credenciais, ou configure pela interface antes de usar a CLI.

```powershell
python bot.py --authenticate
python bot.py --list-groups
python bot.py --watch
python bot.py --watch --dry-run
python bot.py --stop
```

A autenticação CLI pede código/2FA no terminal. A listagem preserva seleção por ID. Watch, listagem e autenticação usam a mesma trava: pare o monitor antes de outra operação.

O comando de parada solicita encerramento apenas deste monitor headless, sem matar outros processos Python. Instâncias da versão antiga devem ser paradas pelo terminal que as iniciou.

`dry-run` não envia, mas marca mensagens em `seen.db`. O simulador da interface não altera dados.

## Regras, dados e recuperação

- Match exato/case-insensitive: A57 corresponde a a57 e A57, mas não a A570 ou XA57.
- Valores em centavos e limites inclusivos. A primeira regra elegível vence; máximo de um alerta por mensagem.
- Preço ambíguo é filtrado nas regras com faixa; sem faixa, o matching por termo é preservado. A associação é conservadora, sem classificação semântica de produtos.
- Deduplicação ocorre antes do envio. Queda entre marcação e envio pode perder um alerta; essa escolha evita duplicatas no replay.
- Dados padrão na raiz: `.env`, `session.session`, `keywords.json`, `watched_groups.json`, `seen.db` e `logs/`. `COMPRAS_DATA_DIR` permite outro diretório existente; não há migração automática de dados.
- Credenciais, sessão, listas pessoais, bancos e backups ficam fora do Git e da release. A sessão permite acesso à conta: não compartilhe esses arquivos. Faça backup dos dados com monitor e processamento parados.
- `bot.lock` permanece no disco. Exclusividade depende do lock do SO, não da existência do arquivo. Não apague locks durante operações.
- JSON inválido e conflito de revisão geram erro, preservando dados. Keywords legadas migram com backup e IDs estáveis.
- Logs rotacionam em até cinco arquivos de 5 MiB. Não há expiração automática de seen nem exclusão de offers.

## Desenvolvimento e validação

Instale `requirements-dev.txt` na raiz. Em `electron/`, use `npm run dev:electron`.

```powershell
cd electron
npm run build
npm run smoke
npm run lint
```

O smoke abre o build em janela oculta com diretório temporário e verifica renderer, preload, IPC, configuração e simulador Python. Não autentica nem envia ao Telegram.

Use pytest/Vitest com seleção dos arquivos afetados. Testes Python isolam dados via conftest. Não usar Playwright. Este workspace não possui artisan; a limpeza de configuração Laravel é inaplicável.

Contrato: `electron/src/lib/ipc.ts`. Documentos: [arquitetura](docs/ARCHITECTURE.md), [preços](docs/SPEC-PRECO.md), [plano](docs/PLANO-MELHORIAS.md) e [implementação/validação](docs/IMPLEMENTACAO-MELHORIAS.md).

## Catálogo parametrizável opcional

Grupos selecionados já recebem Arquivar habilitado por padrão. Em **Catálogo →
Coleta**, confira ou ajuste preferências e inicie/reinicie o monitor. Todas as mensagens desses grupos são guardadas a partir da habilitação,
independentemente de keywords ou modelos. Não há importação anterior ao marco.

Use Acervo para criar modelos por exemplo; publique e inicie o processamento.
Modelos extraem campos, preços, cupons, condições e links para busca em Ofertas.
Formatos desconhecidos entram em Pendências. Alertas estruturados são opcionais.

**Os alertas atuais funcionam sem ETL.** Falha de catálogo/worker não bloqueia o
caminho legado. `catalog.db` é separado de `seen.db` e da sessão Telegram.

Instruções, exemplos e backup: [Guia do catálogo](docs/GUIA-CATALOGO.md).
Contratos e validação: [Spec ETL](docs/SPEC-ETL.md) e
[Implementação ETL](docs/IMPLEMENTACAO-ETL.md).

Para ensinar alguém do zero: [Manual do usuário](docs/MANUAL-USUARIO.md).
