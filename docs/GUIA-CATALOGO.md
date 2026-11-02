# Catálogo parametrizável

Os alertas atuais continuam funcionando sem catálogo, modelos ou worker. Arquivar
é uma seleção independente da seleção de grupos para alertas. Falhas do catálogo
aparecem na Atividade e não impedem os alertas legados. Falha em seen.db mantém
a proteção original: não enviar sem conseguir deduplicar.

## Começar

1. Selecione grupos na tela **Grupos**: eles já recebem **Arquivar** por padrão.
   Em **Catálogo → Coleta**, confira a seleção ou ajuste preferências existentes.
2. Inicie o monitor, ou reinicie-o para aplicar a nova seleção de escuta.
3. Veja as mensagens recebidas em **Coletados**, acima de Grupos, ou em
   **Catálogo → Acervo**, inclusive as que não têm keyword.
4. Abra uma mensagem e escolha **Parametrizar esta mensagem**.
5. Informe nome e marcadores fixos do formato, como `Produto:` e `Pix:`.
6. Adicione campos com nome livre e escolha o tipo e a forma de extração.
   Para o preço depois de `Pix:`, use Dinheiro e Texto após marcador.
7. Teste a extração, confira os trechos usados e teste outras amostras.
8. Salve o rascunho e publique. Rascunhos não alteram o processamento ativo.
9. Use **Iniciar processamento** para interpretar a fila continuamente, ou
   **Processar próximo lote** para executar até 25 mensagens.
10. Pesquise em **Ofertas**, combinando campos, origem, loja, período e condições.

O monitor recebe mensagens; o worker interpreta mensagens já salvas. Pode parar
qualquer um separadamente. Fechar o Electron encerra ambos os processos que ele
iniciou. A fila e as configurações ficam no banco e podem ser retomadas.

## Parametrização

Campos são reutilizáveis entre grupos: escolha um campo publicado existente
quando quiser comparar a mesma informação em origens diferentes. Renomear
preserva identidade. Alterar seu tipo exige um novo campo.

Selecione o valor variável no exemplo para sugerir um campo e seu marcador.
Confira a sugestão: selecionar um produto não deve fixar seu nome no modelo.
O editor não exige regex, JSON ou scripts.

Use separador literal para várias ofertas na mesma postagem. Se houver um
cabeçalho, informe um marcador obrigatório dos blocos, como `Produto:`, para
excluir o cabeçalho da geração de ofertas. Campos com escopo Toda a mensagem
são herdados explicitamente. Os demais ficam no respectivo bloco.

Pix e cartão podem usar nomes de opção diferentes. Associe condições e cupons
à opção correspondente; filtros que dependam da mesma opção devem informá-la.
Um código como GALAXY100 não calcula desconto. Parcelamento mantém quantidade,
parcela e total aritmético separados.

Condição não encontrada significa Não informada, a menos que marque a regra
explícita para considerá-la Ausente. Obrigatório inválido/ambíguo gera pendência.
Mais de um modelo compatível também gera pendência; não se escolhe por ordem.

Para mensagens recorrentes sem promoção, crie um modelo com a classificação
**Este formato é conteúdo sem oferta**. A mensagem continua no acervo.

## Lojas e URLs

Em Lojas e links, cadastre o hostname completo, por exemplo `s.shopee.com.br`, e
o nome da loja. Subdomínios só participam se autorizados. A classificação lê a URL
real em texto, hyperlink e botão. Não abre links externos nem expande encurtadores.
Uma URL de botão sem vínculo a um bloco não é herdada por todos os produtos.

## Pendências e reprocessamento

Pendências agrupam exemplos por origem, motivo e estrutura aproximada. O grupo
é uma ajuda de revisão, não uma garantia de equivalência. Abra outros exemplos,
separe um exemplo mal agrupado ou marque só aquela mensagem como sem oferta.

Publicar um modelo agenda pendências. Resultados já concluídos são preservados.
Para alterá-los, em Ofertas escolha origem/período e veja o impacto antes de
confirmar. A prévia fixa mensagens e versões atuais. O histórico mostra progresso,
cancelamento do restante e retomada, inclusive depois de reabrir o aplicativo.
Execuções antigas continuam disponíveis nos detalhes da mensagem.

Reprocessamento, prévia, edição e recuperação não disparam alertas retroativos.

## Alertas estruturados opcionais

Depois de publicar campos, configure filtros em **Alertas estruturados** e ative
explicitamente cada regra. Todas as condições devem casar na mesma oferta.
Esses alertas exigem captura, monitor e worker; palavras-chave continuam usando
o caminho original. Regras estruturadas distintas e regras legadas são sistemas
independentes e podem gerar alertas diferentes da mesma postagem.

O histórico distingue pronto, envio reivindicado, enviado, falho, simulado e
suprimido por mudança de regra/mensagem. A deduplicação ocorre antes do envio.
Queda depois de reivindicar e antes de confirmar pode perder um alerta; não há
reenvio automático que possa duplicar uma compra potencial. O acervo permanece.

## Período de captura e recuperação

O marco inicial é persistido por grupo. Não há busca anterior à ativação.
Reiniciar não muda o marco. Recuperação consulta somente o período autorizado,
com uma pequena sobreposição idempotente no checkpoint por precisão de segundos.
O checkpoint só avança ao concluir a recuperação; recebimento ao vivo não o adianta.

Ao reativar uma origem, escolha recuperar a pausa ou começar novo intervalo agora.
Pausas e retomadas ficam registradas. Edições observadas de mensagens capturadas
geram revisões; o texto original é preservado. Não se garante recuperar toda edição
ou exclusão ocorrida enquanto o app estava indisponível.

## Banco, backup e execução sem interface

Dados novos ficam em `catalog.db`, no diretório de dados (`COMPRAS_DATA_DIR` ou
raiz do app). `session.session`, `seen.db` e a configuração legada são preservados.
Grupos selected recebem arquivamento padrão ao inicializar catálogo/monitor;
preferências já salvas, inclusive pausas, prevalecem. Não há exclusão automática do acervo.

Comando do worker na raiz:

```powershell
python etl_worker.py
python etl_worker.py --once
```

O primeiro mantém o processamento até Ctrl+C; o segundo processa um lote.
Use apenas uma instância persistente. O worker não usa sessão Telegram.
O monitor headless continua sendo `python bot.py --watch`.

Backup consistente via API SQLite, inclusive com WAL:

```powershell
python -c "from pathlib import Path; from catalog_storage import Catalog; p=Path('catalog.db'); db=Catalog(p); db.backup('catalog.backup.db'); db.db.close()"
```

Adapte o caminho se usar COMPRAS_DATA_DIR. Não copie apenas catalog.db enquanto
estiver ativo. Antes de restaurar, pare monitor e worker, preserve os arquivos
atuais e use um backup íntegro; não misture WAL/SHM de outro banco. Migrações de
versões anteriores criam backup consistente antes de mudar o schema.

Sem OCR, IA, importação histórica, confirmação de preço/estoque ou teste de cupom.
Os resultados representam a postagem, não uma garantia de compra.
