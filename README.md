# ComprasTG

Acompanhe grupos e canais do Telegram, receba alertas de produtos em **Mensagens Salvas** e consulte um catálogo local de ofertas. O ComprasTG usa a sua própria conta Telegram e só acessa as origens disponíveis para ela.

**Para usar no Windows, baixe o instalador ou o ZIP com executável. Não precisa instalar Python ou Node.js.**

[Baixar a versão mais recente](https://github.com/brunocouri/botWebScrapperComprasTG/releases/latest) · [Manual completo](docs/MANUAL-USUARIO.md) · [Guia do catálogo](docs/GUIA-CATALOGO.md)

## Neste guia

- [Instalação no Windows](#instalação-no-windows)
- [Primeira configuração](#primeira-configuração)
- [Criar e testar uma regra](#criar-e-testar-uma-regra)
- [Iniciar o monitor e receber alertas](#iniciar-o-monitor-e-receber-alertas)
- [Consultar mensagens e montar o catálogo](#consultar-mensagens-e-montar-o-catálogo)
- [Uso no dia a dia](#uso-no-dia-a-dia)
- [Atualização, dados e backup](#atualização-dados-e-backup)
- [Resolver problemas](#resolver-problemas)
- [Executar pelo código-fonte](#executar-pelo-código-fonte)

## Instalação no Windows

Requer **Windows 10 ou 11 de 64 bits**, conexão com a internet e uma conta Telegram ativa. Tenha acesso ao Telegram para receber o código de autorização e à sua senha de duas etapas, caso esteja configurada.

Abra a página de [Releases](https://github.com/brunocouri/botWebScrapperComprasTG/releases/latest) e, em **Assets**, escolha:

| Opção | Arquivo da v0.1.1 | Como abrir |
|---|---|---|
| Instalador | `ComprasTG-0.1.1-setup-x64.exe` | Execute, conclua a instalação e abra pelo atalho ComprasTG. |
| ZIP com executável | `ComprasTG-0.1.1-windows-x64.zip` | Extraia tudo em uma pasta e abra `ComprasTG.exe`. |

No ZIP, mantenha o EXE, os demais arquivos e a pasta `resources` juntos. Abrir dentro do arquivo compactado ou copiar apenas o EXE deixa o aplicativo sem os recursos necessários.

Os links **Source code** são destinados a quem vai executar ou compilar o projeto pelo código-fonte. Para abrir o app diretamente, escolha um dos dois arquivos da tabela.

Os binários desta versão não têm assinatura digital. Baixe deste repositório; os hashes de integridade estão em `SHA256SUMS.txt`, na mesma release.

## Primeira configuração

### 1. Obter API ID e API Hash

Você precisa das credenciais de uma aplicação Telegram vinculada à sua conta. Elas são diferentes do código de login e de um token do BotFather.

1. Entre no [portal oficial do Telegram](https://my.telegram.org) com seu número.
2. Abra **API development tools**.
3. Se ainda não existir uma aplicação, preencha o formulário apresentado pelo Telegram.
4. Copie os valores **App api_id** e **App api_hash**.

Esse é o procedimento descrito na [documentação oficial do Telegram](https://core.telegram.org/api/obtaining_api_id). Guarde essas credenciais para preencher o aplicativo; não publique o API Hash.

### 2. Salvar as credenciais no ComprasTG

Abra **Configurações** no menu lateral e preencha:

| Campo | O que informar |
|---|---|
| API ID | O número `api_id` fornecido pelo Telegram. |
| API Hash | O `api_hash` fornecido pelo Telegram. |
| Telefone | Seu número com `+`, código do país e DDD, sem espaços. Exemplo fictício: `+5511999999999`. |

Clique em **Salvar configurações**. Se o hash já estiver salvo, deixar esse campo vazio mantém o valor anterior.

### 3. Autorizar a conta

1. Com o monitor parado e as configurações salvas, clique em **Autorizar conta**.
2. Informe o código recebido pelo Telegram no campo exibido pelo app e envie.
3. Se for solicitada a **Senha de verificação em duas etapas**, informe a senha da sua conta.
4. Aguarde a confirmação **Sessão autorizada. O monitor pode ser iniciado.**

A autorização normalmente é reutilizada nas próximas aberturas. Alterar o telefone no formulário não troca uma sessão que já está autorizada em outra conta.

### 4. Selecionar os grupos e canais

1. Abra **Grupos**.
2. Clique em **Atualizar do Telegram**, com o monitor parado.
3. Aguarde a listagem e marque os grupos/canais que deseja acompanhar.

A seleção é salva ao marcar ou desmarcar. A busca aceita nome ou ID; **Selecionar resultados** altera apenas os resultados do filtro atual. Atualizar a lista preserva as seleções por ID.

A conta precisa ter acesso ao grupo ou canal no próprio Telegram para que ele possa ser acompanhado.

## Criar e testar uma regra

Exemplo: receber um alerta quando aparecer **A57 por até R$ 1.900,00**.

1. Abra **Palavras-chave**.
2. Em **Nova palavra-chave**, digite `A57` e clique em **Adicionar**.
3. Clique na regra para abrir o editor.
4. Deixe **Regra ativa** marcada.
5. Deixe **Preço mínimo (R$)** vazio e preencha **Preço máximo (R$)** com `1.900,00`.
6. Clique em **Salvar 1 alteração**, ou **Salvar N alterações** se houver outras edições pendentes.

Adicionar um termo já o grava como uma regra ativa sem limites de preço. As mudanças feitas no editor exigem o botão de salvar. Fechar o editor ou navegar para outra tela preserva o rascunho, mas não o salva.

### Conferir no simulador

Na mesma tela, em **Testar uma mensagem**, cole:

```text
Samsung Galaxy A57 por R$ 1.899,90
```

Clique em **Simular regras**. Com a configuração acima e sem outra regra elegível com prioridade maior, o resultado esperado é **Alerta pela regra A57**. Troque o preço por `R$ 1.999,90` e simule novamente: a oferta deve ser filtrada pelo limite.

O simulador não conecta ao Telegram, não envia alertas e não marca mensagens como vistas. Se houver edições pendentes, ele usa esses rascunhos; salve-os antes de iniciar o monitor.

### Como o matching funciona

| Regra ou mensagem | Comportamento |
|---|---|
| `A57`, `a57` ou `A57,` | Correspondem ao termo `A57`. |
| `A570`, `XA57` ou `A57PRO` | Não correspondem ao termo `A57`. |
| Mínimo/máximo vazio | Não limita aquele lado da faixa. |
| Preço exatamente igual ao mínimo ou máximo | Está dentro da faixa. |
| Regra com faixa, mas sem preço identificável ou com preço ambíguo | A mensagem é filtrada. |
| Regra sem faixa | Pode alertar pelo termo mesmo sem um preço utilizável. |

Use preços no formato brasileiro, como `1.899,90`. A busca não adivinha sinônimos ou equivalência entre produtos. Em postagens com vários produtos/preços, o app evita assumir uma associação incerta; veja o motivo **Preço ambíguo** no simulador ou na atividade.

**Subir** e **Descer** mudam a prioridade. A primeira regra elegível vence, gerando no máximo um alerta por mensagem no monitoramento por palavras-chave.

## Iniciar o monitor e receber alertas

1. Confira que há pelo menos um grupo selecionado e uma regra ativa para receber alertas por palavras-chave.
2. Clique em **Iniciar monitor**, no topo do aplicativo.
3. Aguarde o estado **Monitorando**. Conexão e sincronização podem aparecer antes.
4. Mantenha o aplicativo aberto e o computador conectado à internet.
5. Quando uma nova mensagem atender à regra, procure o alerta em **Mensagens Salvas**, no Telegram da mesma conta autorizada.

Os alertas incluem informações da mensagem e um link de origem quando disponível. O aplicativo registra mensagens já avaliadas para evitar repetição; reiniciar o monitor não é um comando para reenviar alertas antigos.

Abra **Atividade** para acompanhar envios, filtros, erros e sincronização. Use **Mostrar**, a busca e os detalhes de cada evento para entender o resultado. A atividade é um buffer da sessão; para consultar as mensagens arquivadas, use **Coletados**.

Se aparecer **Configuração salva diferente da aplicada**, clique em **Reiniciar e aplicar**. Salvar novas regras, grupos ou credenciais não altera automaticamente a configuração do monitor que já está rodando.

**Fechar o aplicativo encerra o monitor e o processamento.** Não há bandeja nem início automático implementados. Com o computador desligado, suspenso ou sem conexão, não há acompanhamento ao vivo.

## Consultar mensagens e montar o catálogo

O catálogo é opcional. Alertas por palavras-chave funcionam sem criar modelos ou iniciar o processamento.

| Parte | Para que serve |
|---|---|
| Monitor | Recebe mensagens do Telegram e executa os alertas por palavras-chave. |
| Coletados / Catálogo → Acervo | Exibe as mensagens originais arquivadas, mesmo sem uma palavra-chave correspondente. |
| Processamento | Interpreta as mensagens arquivadas usando os modelos publicados. |
| Catálogo → Ofertas | Permite pesquisar os dados extraídos das postagens. |

### Arquivar e consultar as mensagens

Grupos selecionados recebem **Arquivar** habilitado por padrão quando o catálogo/monitor é inicializado. Preferências de coleta já salvas são preservadas: uma origem pausada não é reativada automaticamente.

1. Em **Catálogo → Coleta**, confira quais origens estão com **Arquivar** habilitado.
2. Inicie ou reinicie o monitor para aplicar mudanças de escuta.
3. Abra **Coletados**, no menu lateral, para consultar as postagens originais.
4. Use o filtro por origem e a paginação. Clique numa mensagem para ver os detalhes.

A coleta começa no marco registrado para cada origem; habilitar não importa todo o histórico anterior do grupo. O acervo não depende das palavras-chave. Para coletar sem alertas tradicionais, basta ter uma origem com arquivamento habilitado; não é obrigatório manter regras de palavras-chave ativas.

Desmarcar um grupo em **Grupos** interrompe sua seleção para alertas tradicionais. Para também interromper uma coleta já habilitada, pause **Arquivar** em **Catálogo → Coleta**. O que já foi salvo permanece no acervo.

### Criar o primeiro modelo de extração

Um modelo descreve o formato das postagens de um grupo. Por exemplo:

```text
Produto: Samsung Galaxy A57 256 GB
Pix: R$ 1.899,90
```

1. Abra uma mensagem em **Coletados** e clique em **Parametrizar esta mensagem**. Também é possível começar por **Catálogo → Modelos → Criar modelo** e colar o exemplo.
2. Preencha **Nome do modelo** e confira **Grupo do modelo**.
3. Em **Marcadores de reconhecimento**, coloque `Produto:` e `Pix:`, um por linha. Use partes fixas do formato, sem fixar o nome ou o preço do produto de exemplo.
4. Use **Criar campo a partir da seleção** para adicionar os campos e confira as sugestões. Para o exemplo acima, configure:

| Nome do campo | Tipo | Extrair usando | Marcador inicial |
|---|---|---|---|
| Produto | Texto | Texto após marcador, até o fim da linha | `Produto:` |
| Preço Pix | Dinheiro | Texto após marcador, até o fim da linha | `Pix:` |

5. Clique em **Testar extração** e confira os valores extraídos. Teste também outras postagens com o mesmo formato.
6. Clique em **Salvar rascunho**. Se o modelo ou o texto de teste mudar, teste novamente.
7. Com o rascunho salvo e uma prévia válida, clique em **Publicar modelo e processar pendências**.
8. No Catálogo, clique em **Iniciar processamento**. **Processar próximo lote** executa apenas um lote, sem manter o processamento contínuo.
9. Consulte **Ofertas**. Formatos desconhecidos ou campos que precisam de revisão aparecem em **Pendências** depois de processados.

Para coleta e interpretação contínuas, mantenha **monitor e processamento ativos**. Para consultar resultados já salvos, ambos podem estar parados. O app não interpreta formatos sozinho por IA, não faz OCR e não confirma preço, estoque ou cupom na loja.

Modelos, ofertas antigas, reprocessamento e alertas por campos têm instruções no [Guia do catálogo](docs/GUIA-CATALOGO.md). **Alertas estruturados** exigem configuração e ativação próprias, coleta, monitor e processamento; são independentes das regras por palavras-chave e podem produzir outro alerta da mesma postagem. Prévia, recuperação e reprocessamento não enviam alertas estruturados retroativos.

## Uso no dia a dia

1. Abra o ComprasTG. As configurações e a sessão anteriores são reutilizadas quando válidas.
2. Confira suas regras e clique em **Iniciar monitor**; aguarde **Monitorando**.
3. Se usa modelos de catálogo, inicie também o processamento.
4. Veja alertas em **Mensagens Salvas**, mensagens originais em **Coletados** e resultados extraídos em **Catálogo → Ofertas**.
5. Ao alterar configurações, salve e use **Reiniciar e aplicar** quando indicado.
6. Para encerrar, use **Parar operação** ou feche a janela, confirmando a parada quando solicitado. Salve os rascunhos antes de sair.

## Atualização, dados e backup

No aplicativo Windows distribuído, os dados ficam em:

```text
%APPDATA%\ComprasTG\data
```

Para abrir a pasta, pressione `Win + R`, cole o caminho acima e pressione Enter.

| Arquivo/pasta | Conteúdo |
|---|---|
| `.env` | API ID, API Hash e telefone. |
| `session.session` | Sessão de acesso à conta Telegram. |
| `keywords.json` / `watched_groups.json` | Regras e seleção de grupos. |
| `seen.db` | Controle de mensagens já avaliadas. |
| `catalog.db` | Mensagens arquivadas, modelos, ofertas e dados do catálogo. |
| `logs/` | Diagnósticos do monitor. |

O instalador e o ZIP usam essa mesma pasta de dados. Trocar a pasta do ZIP não cria outra conta ou outro acervo. Os downloads não incluem dados pessoais do desenvolvedor.

**Backup:** salve seus rascunhos, feche o app e aguarde o encerramento do monitor/processamento. Copie a pasta `data` inteira para um local seguro, incluindo arquivos auxiliares de banco que existirem. Não copie apenas `catalog.db` enquanto ele estiver em uso.

**Atualização:** feche o aplicativo, faça backup e instale a nova versão ou extraia o novo ZIP em outra pasta. Abra o novo EXE; os dados permanecem no perfil do usuário. Não execute as duas versões ao mesmo tempo usando a mesma sessão.

**Restauração ou mudança de computador:** com as instâncias do app fechadas, preserve uma cópia dos dados atuais e restaure o backup completo na pasta de dados da versão compatível. Dados de execução pelo código-fonte ficam na raiz do projeto por padrão e não são importados automaticamente pelo instalador.

A pasta contém credenciais, dados das mensagens e uma sessão que permite acesso à sua conta. Não publique nem compartilhe esse conteúdo. Não apague `seen.db` para tentar reenviar alertas ou arquivos `.lock` para forçar operações simultâneas.

## Resolver problemas

| Situação | O que conferir |
|---|---|
| EXE não abre ou informa runtime ausente | Extraia o ZIP inteiro ou reinstale pelo instalador. Não mova apenas `ComprasTG.exe`. |
| Autorizar conta está desabilitado | Pare a operação atual, salve as configurações e confira se o API Hash está preenchido. |
| Código expirou ou autorização não concluiu | Pare a operação e tente autorizar novamente, usando o código atual e a senha 2FA quando solicitada. |
| Outra instância usa a sessão | Pare o monitor/CLI da outra instância. Autorização e atualização de grupos também precisam da sessão exclusiva; não apague locks. |
| Iniciar monitor está desabilitado | Para alertas tradicionais, selecione um grupo e ative uma regra; para só arquivar, habilite uma origem em Coleta. Aguarde o carregamento das configurações. |
| Conectando ou Sincronizando | Aguarde e consulte Atividade. Só considere o monitor pronto quando aparecer Monitorando. |
| Nenhum alerta chega | Confira grupo, regra ativa, prioridade, faixa de preço, configuração aplicada e conexão. Cole a postagem no simulador e veja o motivo do filtro. |
| Preço ambíguo | A associação entre produto/preço não é segura. Revise o texto e a regra; retirar a faixa passa a aceitar o termo sem garantir o preço. |
| Configuração mudou, mas o monitor segue igual | Salve as edições pendentes e use Reiniciar e aplicar. |
| Coletados está vazio | Confira Arquivar em Coleta e o monitor ativo. Aguarde mensagens posteriores à habilitação; a coleta não importa todo o passado. |
| Coletados tem mensagens, mas Ofertas está vazio | Publique um modelo compatível, inicie o processamento e confira Pendências. Sem modelos, os originais continuam no acervo. |
| Publicar modelo está desabilitado | Salve o rascunho e execute Testar extração com resultado válido para a versão atual do modelo e do texto. |
| Sessão pertence a outra conta | Mudar o telefone não substitui a sessão. Preserve os dados existentes; use um diretório de dados separado para outra conta. |
| Erro de JSON ou conflito ao salvar | Preserve os arquivos e as edições. Recarregue a configuração em caso de conflito; restaure um backup íntegro em caso de corrupção. |

Se precisar relatar um erro, descreva a tela, a ação e a mensagem exibida. Em **Atividade**, há **Modo técnico** e **Copiar logs**; revise e remova dados pessoais antes de compartilhar. Nunca envie API Hash, código de login, senha 2FA ou `session.session`.

## Executar pelo código-fonte

Esta seção é para desenvolvimento ou uso da CLI. Quem baixou o instalador/ZIP com EXE pode usar o passo a passo acima.

<details>
<summary>Instalação e execução pelo código-fonte</summary>

Requer Python e Node.js no PATH. O ambiente da release foi validado com Python 3.14.5, Telethon 1.40.0 e Electron 44.10.0. Use Node.js 22.12 ou superior.

No PowerShell:

```powershell
git clone https://github.com/brunocouri/botWebScrapperComprasTG.git
cd botWebScrapperComprasTG
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cd electron
npm ci
npm run build
npm start
```

Nas próximas aberturas, a partir da raiz do projeto:

```powershell
.\.venv\Scripts\Activate.ps1
cd electron
npm start
```

Mantenha o ambiente ativado ao iniciar o Electron: em desenvolvimento, ele executa `python` pelo PATH. Dados ficam na raiz do projeto, salvo `COMPRAS_DATA_DIR` apontando para outro diretório.

Para evitar ativar um script PowerShell, é possível usar CMD: execute `.venv\Scripts\activate.bat` antes dos comandos de instalação/abertura.

</details>

<details>
<summary>CLI e validação de desenvolvimento</summary>

Na raiz do projeto, com o ambiente Python ativo, copie `.env.example` para `.env`, preencha suas credenciais e autorize a conta:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
python bot.py --authenticate
python bot.py --list-groups
```

Edite a seleção em `watched_groups.json` e configure `keywords.json` pela interface antes de monitorar. Se `.env` já existir, preserve-o em vez de executar a cópia novamente. A CLI e o desktop devem usar o mesmo diretório de dados para compartilhar configuração.

```powershell
python bot.py --watch
python bot.py --stop
```

Execute `--stop` em outro terminal para solicitar a parada do monitor headless. Não use a mesma sessão em operações simultâneas.

`python bot.py --watch --dry-run` não envia alertas, mas marca mensagens em `seen.db`. Para conferir regras sem esse efeito, use o simulador da interface.

Para desenvolvimento, instale `requirements-dev.txt` na raiz. Em `electron/`, use `npm run dev:electron`. Testes devem ser focados e usar dados temporários, sem autenticação ou envio real ao Telegram; não usar Playwright. Este projeto não possui `artisan`.

Em `electron/`:

```powershell
npm run build
npm run lint
npm run smoke
```

Para gerar instalador e ZIP Windows x64, com Python 3.14 no ambiente de build:

```powershell
npm run package:win
npm run smoke:packaged
```

Os artefatos ficam em `artifacts/windows/`, na raiz do projeto. O runtime embutido tem SHA256 fixado e recebe somente fontes explicitamente selecionadas. O smoke empacotado usa dados temporários e PATH sem Python/Node.

</details>

## Documentação técnica e limites

- [Manual completo](docs/MANUAL-USUARIO.md), [Guia do catálogo](docs/GUIA-CATALOGO.md) e [Arquitetura](docs/ARCHITECTURE.md).
- Contratos de [preços](docs/SPEC-PRECO.md), [catálogo](docs/SPEC-ETL.md) e [distribuição Windows](docs/SPEC-DISTRIBUICAO.md).
- O contrato IPC implementado está em `electron/src/lib/ipc.ts`. A estrutura FastAPI de `backend/` é planejada; não é o servidor usado pelo aplicativo.
- Alertas usam deduplicação anterior ao envio. Uma queda entre a marcação e a confirmação pode perder um alerta; não há garantia de reenvio automático.
- Não há limpeza automática de `seen.db` ou do acervo. Acompanhe o espaço disponível e mantenha backups.
- Os resultados refletem anúncios dos grupos. Confirme condições e preço no destino antes de comprar.
