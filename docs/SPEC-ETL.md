# Contrato executável do catálogo

O catálogo é opcional. Alertas legados não dependem de catalog.db, modelos ou worker.
Falha de captura é diagnosticada sem impedir a avaliação legada. SeenStore mantém
seu contrato próprio de integridade. Nenhuma operação do catálogo envia ao Telegram.

Atualização de 30/10/2026: origens com selected=true em Grupos recebem arquivamento
habilitado por padrão na primeira inicialização do catálogo ou ao iniciar o monitor.
Não selecionar origens sem selected. Preferências de coleta já existentes, inclusive
pausa manual, prevalecem sobre esse padrão. O marco é a habilitação efetiva no banco;
não reconstruir a data em que selected foi marcado no passado. Desmarcar Grupos
altera alertas; pausar captura separadamente em Coleta preserva o acervo.

Coletados é uma entrada na navegação principal acima de Grupos. Mostra o acervo
original, inclusive mensagens sem modelo/keyword, com origem, data, estado,
paginação e detalhes. Reutiliza o mesmo acervo de Catálogo; não cria outro banco.
Atualiza enquanto a tela está visível e permite atualização manual. Parametrizar
uma mensagem abre o editor do Catálogo sem descartar rascunhos existentes.

Captura requer ativação explícita por origem, marco UTC persistido e intervalo aberto.
Reentrega é idempotente por origem/mensagem/data de revisão/hash. Edição não cria
mensagem anterior ao marco nem desconhecida. A versão atual é a maior data de revisão;
reversão de texto posterior é revisão nova. Captura e fila usam a mesma transação.
Recuperação percorre o intervalo autorizado em ordem; checkpoint de recuperação só
avança ao fim do lote completo. Recepção ao vivo não adianta esse checkpoint.

Modelos têm identidade e versões publicadas imutáveis. Rascunhos não participam.
Reconhecimento exige todos os marcadores. Zero modelos gera unknown_format;
mais de um gera ambiguous_template. Obrigatório ausente/ambíguo invalida a extração.
Extratores são dados: line, after, between, presence, constant, link; nenhum eval/regex
fornecido pelo usuário. Blocos são separados por delimitador literal e mantêm escopo.
Dinheiro é BRL em centavos; condição não encontrada é unknown. Evidência inclui
trecho e posição ou origem de configuração. Links vêm de texto, entidades e botões;
classificação compara hostname normalizado exato ou subdomínio autorizado.

Worker exclusivo via FileLock, sem sessão Telegram. Cada trabalho processa uma revisão
e configuração imutável. Commit troca projeção somente se a revisão ainda é atual.
Queda antes do commit deixa trabalho pendente; execuções antigas são preservadas.
Pendências são agrupadas por origem/motivo/estrutura. Reprocessamento exige prévia
com token do escopo e confirmação; não altera seen.db nem emite alertas retroativos.

Limites: texto 65536 caracteres, 100 blocos, 100 campos/modelo, 50 modelos/origem,
100 itens/página (UI usa 25), lotes de 25 trabalhos, 60 mil caracteres de saída
por extração. Buscas usam parâmetros SQL; detalhes carregam uma execução por vez.
Sem exclusão automática, importação anterior ao marco, rede externa ou OCR.
