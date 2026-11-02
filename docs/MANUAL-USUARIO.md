# Manual do usuário — ComprasTG

## O que o aplicativo faz

O ComprasTG acompanha os grupos/canais acessíveis à sua conta do Telegram.
Ele pode avisar sobre palavras-chave e guardar postagens para formar um catálogo
pesquisável de ofertas. O catálogo registra o que foi anunciado, com sua origem.
Não confirma preço no checkout, estoque, desconto ou funcionamento de cupom.

O funcionamento tem três partes:

1. **Monitor:** recebe as mensagens e executa os alertas tradicionais.
2. **Acervo:** guarda as mensagens originais dos grupos com coleta habilitada.
3. **Processamento:** interpreta o acervo usando os modelos cadastrados.

Os alertas tradicionais não dependem dos modelos nem do processamento do catálogo.
Falha no catálogo não bloqueia esses alertas. O monitor precisa permanecer aberto
e conectado para receber postagens ao vivo.

## Abrir o aplicativo

Na versão Windows, instale pelo arquivo `setup-x64.exe` e abra pelo atalho, ou extraia o ZIP completo e abra `ComprasTG.exe`. Não é necessário instalar Python ou Node.js. Configurações, sessão e bancos ficam em `%APPDATA%\ComprasTG\data` e não são removidos ao trocar os arquivos do aplicativo.

No PowerShell, para uma instalação pelo código-fonte já preparada:

```powershell
cd .\botWebScrapperComprasTG
.\.venv\Scripts\Activate.ps1
cd electron
npm start
```

Fechar a janela encerra o monitor e o processamento iniciados pelo Electron.
Não há funcionamento em segundo plano via bandeja ou início automático implementados.

## Configurações da conta

Na tela **Configurações**:

| Campo/ação | Como usar |
|---|---|
| API ID | Identificador da aplicação Telegram, obtido em my.telegram.org/apps |
| API Hash | Credencial da aplicação; depois de salvo aparece mascarado |
| Telefone | Número da conta com código do país, como +5511999999999 |
| Salvar configurações | Grava as alterações; reinicie o monitor para aplicá-las |
| Autorizar conta | Inicia a entrada na conta; monitor deve estar parado |
| Código | Informe o código solicitado pelo Telegram |
| Senha de duas etapas | Informe quando a conta exigir 2FA |

Se o API Hash já estiver configurado, deixar o campo vazio mantém o valor salvo.
O telefone deve corresponder à sessão existente; mudar o campo não troca
automaticamente uma sessão autenticada em outra conta.

As credenciais são pessoais. Não envie seu hash, código ou senha a outra pessoa.
Normalmente você autoriza uma vez e reutiliza a sessão nas próximas aberturas.

## Grupos e coleta padrão

Com o monitor parado, abra **Grupos → Atualizar do Telegram**. O app carrega os
grupos e canais que sua conta pode acessar, preservando seleções anteriores por ID.

Marque as origens desejadas. A seleção é salva ao alterar os checkboxes.
Buscar pelo nome/ID e filtrar os selecionados ajudam a localizar origens.
**Selecionar resultados** atua apenas sobre o que aparece no filtro;
**Selecionar todos os grupos** atua sobre a lista inteira.

**Grupos selecionados já recebem arquivamento habilitado por padrão.** Não é
necessário marcar uma segunda vez em Catálogo. Isso vale também para grupos que
já estavam selected antes desta atualização, quando o catálogo for inicializado
ou o monitor for iniciado. O marco é criado agora, sem reconstruir o passado.

Em **Catálogo → Coleta**, você pode conferir a seleção, pausar um arquivamento
ou incluir uma origem apenas para o acervo. Preferências de coleta já existentes
são preservadas: um grupo pausado manualmente não é reativado a cada abertura.

Desmarcar um grupo em Grupos retira sua seleção para alertas tradicionais.
Para interromper também o arquivamento já habilitado, desmarque Arquivar em Coleta.
O conteúdo salvo permanece pesquisável. Ao reativar, escolha recuperar desde o
checkpoint ou começar um novo intervalo agora.

Mudanças de origens escutadas exigem iniciar/reiniciar o monitor. Atualizar a lista
do Telegram e autorizar conta também usam a sessão; pare o monitor antes dessas ações.

## Palavras-chave e alertas tradicionais

Em **Palavras-chave**, adicione termos como A57. Cada regra possui:

| Configuração | Efeito |
|---|---|
| Palavra-chave | Termo exato, sem diferenciar maiúsculas/minúsculas |
| Regra ativa | Liga ou desliga a regra sem apagá-la |
| Preço mínimo | Menor valor aceito, inclusive; vazio não impõe mínimo |
| Preço máximo | Maior valor aceito, inclusive; vazio não impõe máximo |
| Subir/Descer | Define a prioridade entre as regras |

A57 corresponde a a57 e A57 seguido de pontuação, mas não a A570 ou XA57.
Use a grafia do produto que costuma aparecer nos canais. A busca não adivinha
sinônimos, variantes ou equivalência de produtos.

Digite preços no formato brasileiro, como 1.899,90. Com faixa de preço,
mensagem sem preço utilizável ou com associação ambígua é filtrada.
Sem faixa, o termo pode gerar alerta mesmo que o preço seja ambíguo.

A primeira regra elegível vence: o caminho tradicional envia no máximo um alerta
por mensagem. O destino é **Mensagens Salvas** da própria conta Telegram.
Há deduplicação para impedir reenvio no replay de mensagens.

Ao editar regras, use **Salvar N alterações**. Fechar um editor ou navegar não
equivale a salvar. O aplicativo preserva os rascunhos e informa pendências.
Depois de salvar, reinicie o monitor quando a interface indicar configuração diferente.

No simulador, cole uma postagem e confira qual regra vence ou por que foi filtrada.
Simular não envia mensagem e não marca a postagem como já alertada.

## Iniciar e acompanhar o monitor

Clique em **Iniciar monitor**. Aguarde **Monitorando**; iniciar o processo não
significa que a conexão já está pronta. Os estados intermediários incluem conexão,
sincronização e reconexão. Pode monitorar somente para coletar, sem keywords ativas,
desde que existam origens com arquivamento habilitado.

O app compara configuração salva e aplicada. Quando diferirem, use
**Reiniciar e aplicar**. Configuração de conta, seleção de origens e regras
tradicionais exigem essa aplicação; publicar modelos atua no processamento local.

Em **Atividade**, confira mensagens encontradas, filtradas, simuladas, enviadas,
falhas e sincronização. Use filtros e expanda os detalhes para entender uma decisão.
A rolagem manual pausa o acompanhamento automático. O feed é um buffer de sessão,
não o histórico completo de mensagens; para consultar postagens use Acervo.

## Acervo e processamento

A aba **Coletados**, acima de Grupos na navegação principal, abre diretamente as
mensagens originais salvas. Use o filtro por origem, a paginação ou **Atualizar
mensagens**. A lista é atualizada a cada cinco segundos enquanto estiver aberta.
Clique numa postagem para ver o original, revisões e evidências; **Parametrizar
esta mensagem** abre o editor no Catálogo. É o mesmo acervo de Catálogo → Acervo.

O Acervo contém todas as postagens capturadas das origens habilitadas, com ou sem
palavra-chave e com ou sem modelo. Guarda texto/legenda, datas, origem, links reais
de texto/hyperlinks/botões e metadados básicos de mídia. Não baixa mídia nem faz OCR.

O processamento transforma mensagens em ofertas, cupons ou pendências:

| Controle | Função |
|---|---|
| Iniciar processamento | Mantém a interpretação da fila funcionando continuamente |
| Parar processamento | Interrompe a interpretação; o monitor pode continuar salvando |
| Processar próximo lote | Executa até 25 trabalhos sem manter o worker contínuo |
| Atualizar catálogo | Atualiza os dados exibidos nas telas |

Antes de interpretar, uma postagem está na fila. Depois de interpretar, ela pode
virar oferta, conteúdo sem oferta ou pendência. Sem modelos, o banco ainda cresce
com os originais; os formatos desconhecidos aparecem em Pendências após processados.

Para coletar e interpretar continuamente, mantenha **monitor e processamento ativos**.
Para somente pesquisar resultados prontos, ambos podem estar parados.

## Modelos: ensinar o formato das postagens

Abra uma mensagem no Acervo e escolha **Parametrizar esta mensagem**. Um grupo
pode ter vários modelos, pois pode publicar ofertas, listas e cupons em formatos distintos.
O aplicativo aplica regras declaradas; não aprende nem classifica sozinho por IA.

Exemplo fictício:

```text
Produto: Samsung Galaxy A57 256 GB
Pix: R$ 1.899,90
Cartão: 10x R$ 209,90
Cupom: GALAXY100
Condição: comprar no app
https://s.shopee.com.br/exemplo
```

Configure o reconhecimento:

- **Nome do modelo:** uma descrição, como Celular com Pix e cupom.
- **Grupo do modelo:** origem a que o formato pertence; depois de salvo não se troca.
- **Marcadores de reconhecimento:** partes fixas, uma por linha, como Produto: e Pix:.
  Todos os marcadores precisam existir. Não use nome/preço de exemplo como parte fixa.
- **Conteúdo sem oferta:** marca um formato recorrente que deve ficar no acervo sem
  gerar oferta nem voltar como formato desconhecido.

Configure os campos:

| Nome sugerido | Tipo | Extrator | Marcador |
|---|---|---|---|
| Produto | Texto | Texto após marcador | Produto: |
| Preço Pix | Dinheiro | Texto após marcador | Pix: |
| Cartão | Parcelamento | Texto após marcador | Cartão: |
| Cupom | Texto | Texto após marcador | Cupom: |
| Compra pelo app | Condição | Presença de expressão | comprar no app |
| Comprar | Link | URL da postagem | Sem marcador obrigatório |

O nome do campo é livre. Reutilize um campo já publicado quando for a mesma
informação em outro grupo: isso permite comparar preços entre origens.
Renomear preserva a identidade; mudar o tipo exige outro campo.

Extratores disponíveis:

- **Após marcador:** conteúdo depois do marcador até o fim da linha.
- **Entre marcadores:** trecho entre início e fim configurados.
- **Número da linha:** conteúdo de uma linha fixa, começando em 1.
- **Presença de expressão:** identifica uma condição no texto.
- **Valor constante:** atribui um valor definido por você, identificado como configuração.
- **URL da postagem:** extrai links; pode limitar por hostname/posição ou aceitar vários.

Revise os marcadores de extração com a grafia do canal. Para Categoria, preencha
mapeamentos explícitos, como `Smartphones=Celulares`, um por linha.

**Obrigatório** impede concluir a extração quando o valor falta ou é inválido.
**Aceitar vários valores** permite cardinalidade múltipla; caso contrário,
múltiplos resultados podem gerar ambiguidade. Remover um campo do rascunho só
afeta a produção quando uma nova versão for publicada.

Condição não encontrada significa **Não informada**. Só significa **Ausente** se
você marcar explicitamente essa regra. Cupom GALAXY100 é um código, não uma
ordem para calcular R$ 100 de desconto. Parcelamento mantém parcelas e total aritmético.

## Vários produtos, preços e condições

Se uma postagem tem várias ofertas, informe o **separador literal entre ofertas**,
por exemplo uma linha `---`. O separador precisa corresponder ao formato real.
Cada bloco será interpretado separadamente.

Se houver cabeçalho/rodapé, use o **marcador obrigatório do bloco de oferta**,
por exemplo Produto:, para só gerar ofertas nos blocos correspondentes.

O **Escopo** de cada campo é fundamental:

| Escopo | A quem pertence o valor |
|---|---|
| Apenas este bloco de oferta | Somente àquele produto/bloco |
| Toda a mensagem | É herdado explicitamente pelos blocos de ofertas |
| Opção de preço deste bloco | A uma alternativa, como Pix ou Cartão |

Para opção de preço, informe um nome consistente. Condição/cupom exclusivo do
cartão deve estar associado a Cartão, não à opção Pix. Não herde cupom do cabeçalho
para todos os produtos sem que a postagem tenha esse significado.

## Testar, salvar e publicar

1. Cole uma amostra, ou use a mensagem aberta.
2. Se quiser, selecione um valor variável e use **Criar campo a partir da seleção**;
   a sugestão precisa ser revisada.
3. Clique em **Testar extração** e confira valores e evidências.
4. Teste outras postagens do mesmo formato, trocando produtos, preços e cupons.
5. Clique em **Salvar rascunho**.
6. Clique em **Publicar modelo e processar pendências**.
7. Inicie o processamento se estiver parado.

Rascunho não modifica o modelo publicado. Publicar cria outra versão imutável.
A prévia compara com os modelos publicados do mesmo grupo e informa conflitos.
Editar o exemplo/modelo invalida a prévia anterior; teste novamente.
Arquivar um modelo impede novos usos, preservando resultados e histórico.

## Lojas e links

Em **Lojas e links**, cadastre um hostname completo e o nome da loja:

| Hostname | Loja |
|---|---|
| s.shopee.com.br | Shopee |

Não inclua https:// nem caminho. **Incluir subdomínios** autoriza também hosts
abaixo daquele domínio; deixe desmarcado para correspondência exata.
Use **Salvar regras de lojas** para aplicar as edições.

O modelo precisa extrair um campo Link para exibir/classificar o link da oferta.
URLs desconhecidas são preservadas. A classificação usa a URL real do hyperlink
ou botão e não visita a loja, expande encurtadores ou remove parâmetros de afiliação.
Canal de origem, loja e vendedor de marketplace são informações diferentes.

## Pendências

Pendências indicam formato desconhecido, modelos conflitantes ou campos
obrigatórios inválidos/ambíguos. Elas não apagam nem impedem salvar os originais.

Abra exemplos, crie/ajuste um modelo, separe mensagens mal agrupadas ou marque
somente um exemplo como sem oferta. O agrupamento é aproximado; não assuma que
todos os exemplos têm o mesmo significado. Não há uma janela interrompendo a
operação a cada mensagem desconhecida.

## Pesquisar ofertas e reprocessar

Em **Ofertas**, pesquise produto/cupom/texto e abra os filtros detalhados para
combinar origem, loja, datas, campo, mínimo/máximo, condição e opção de preço.
**Adicionar condição à busca** permite combinar vários campos da mesma oferta.
Preços usam formato brasileiro. Os resultados mostram origem e evidências;
abra a mensagem original e, quando disponível, seu link no Telegram.

Exemplo: produto contendo Galaxy A57, Preço Pix máximo 1.900,00, origem desejada
e loja Shopee. Campo não informado é diferente de zero ou condição ausente.

Mudança de modelo/loja não reescreve automaticamente resultados concluídos.
Use **Reprocessar acervo local**, escolha origem/período, veja o impacto e confirme.
As mensagens e versões usadas ficam fixadas na prévia. O histórico permite
acompanhar, cancelar o restante e retomar lotes. Resultados anteriores permanecem.
Reprocessamento, teste, recuperação e edição não disparam alertas retroativos.

## Alertas estruturados opcionais

Depois de publicar campos, use **Alertas estruturados** para criar uma regra
com nome, grupo e condições sobre esses campos. Adicione condições e marque
**Ativar para novas postagens** quando quiser receber avisos. Salve a regra.

Exemplo: Produto contém A57 e Preço Pix é no máximo 1.900,00.
Todos os filtros precisam corresponder à mesma oferta; quando necessário,
use a mesma opção de preço para vincular preço, cupom e condições.

Esses alertas exigem coleta, monitor e processamento. Os tradicionais continuam
independentes. Ativar ambos pode produzir avisos diferentes sobre a mesma mensagem.
Confira o histórico de entregas para enviados, falhos, simulados ou suprimidos.

## Rotina recomendada e limites

No primeiro dia: configure conta, carregue grupos, escolha um grupo selecionado,
inicie o monitor e confira uma mensagem no Acervo. Parametrize um formato simples,
teste outras amostras, publique e inicie o processamento. Depois amplie para outros grupos.

No dia a dia: inicie monitor e processamento, confira erros/fila/pendências e use
Ofertas para pesquisar. Não confunda Monitorando com processamento ativo: são controles separados.

Não há importação anterior ao marco inicial, IA, OCR, avaliação de estoque ou
garantia de preço vigente. Mudanças no padrão dos canais exigem manutenção dos modelos.
Desconexões podem ser recuperadas dentro do período autorizado quando Telegram permitir;
não se garante reconstruir toda edição/exclusão ocorrida offline.

O catálogo é local e não é apagado automaticamente. Faça backup consistente
conforme GUIA-CATALOGO.md; não copie apenas um SQLite ativo sem considerar seu WAL.
Fechar o app não apaga o banco nem os modelos. Eles permanecem para a próxima abertura.
