# FrotaFusion — quatro packs na categoria [carros]

Ferramenta Windows independente do FrotaLab anterior. Aceita quatro ZIPs originais ou diretórios já extraídos, identifica os spawns em vehicles.meta, escolhe uma variante por spawn e monta a pasta resources/[carros] sem modificar as origens.

## Passos

1. Faça backup do FXServer e desligue o servidor.
2. Baixe FrotaFusion.exe na seção Actions > Build FrotaFusion Windows > Artifacts > FrotaFusion-Windows.
3. Abra o programa e selecione cada um dos 4 arquivos ZIP ou as respectivas pastas originais.
4. Selecione o destino resources do seu servidor.
5. Caso já exista resources/[carros], faça backup e mova a categoria antiga PARA FORA de resources. O programa não substitui instalações existentes.
6. Clique em ANALISAR, REMOVER REPETIDOS E GERAR [carros].
7. Leia o arquivo resources/[carros]/RELATORIO_FROTAFUSION.json, principalmente spawns_sem_selecao, alertas, conflitos_de_spawn e conflitos_de_arquivos_stream.
8. Remova ou comente os comandos antigos de inicialização dos quatro packs no server.cfg; configure somente ensure [carros].
9. Inicie o FXServer com os recursos parados e monitore o console/txAdmin. Faça testes de spawn, tuning, som, dirigibilidade e FPS.

## Resultado

resources/[carros]/PLOKS_CARS/  — pack 1 filtrado, com fxmanifest.lua
resources/[carros]/Lore_Friendly_Car_Pack/  — pack 2 filtrado, áudio incluso
resources/[carros]/LNWK-CARS/  — pack 3 filtrado
resources/[carros]/LIVID_LF_CARS/  — pack 4 filtrado
resources/[carros]/FROTA_RODAS_XX/  — pacotes originais de rodas
resources/[carros]/FROTA_SOM_nome/  — recursos auxiliares de som
resources/[carros]/RELATORIO_FROTAFUSION.json  — decisões registradas

A pasta [carros] é uma CATEGORIA FiveM; cada subpasta executável precisa do próprio fxmanifest.lua. O comando ensure [carros] inicia todos os recursos da categoria.

## Critério de duplicações

1. Compara o modelName real dos arquivos vehicles.meta, não apenas o nome do arquivo YFT.
2. Exige o modelo base YFT correspondente. Se faltar, registra problema e não o declara funcional.
3. Prefere conjuntos com texturas e metadados completos.
4. Favorece YTD menores, especialmente evitando texturas acima de 48 MiB quando há alternativa completa.
5. Desempata por menor tamanho agregado estimado dos arquivos (tuning incluído).
6. Apenas uma variante do mesmo código de spawn é copiada para a saída; a versão descartada permanece intacta no pack original.

IMPORTANTE: tamanho em disco NÃO equivale a otimização comprovada de polígonos, memória física ou FPS. O FrotaFusion escolhe a alternativa mais leve e íntegra ESTIMADA; não edita geometria YFT ou textura YTD. Modelos sem arquivo YFT identificável e conflitos complexos são informados no relatório para revisão manual. Arquivos de stream de mesmo nome mas spawns diferentes são alertados, não excluídos automaticamente para evitar quebrar veículos legítimos.

## Cuidados com o servidor

O antigo Pack 1 já ocasionou um travamento svMain e reinício pelo txAdmin quando muitos recursos foram ativados em lote. A fusão correta e a remoção de duplicações não garantem que o problema desapareça. Caso o servidor pare de responder após ensure [carros], não tente aumentar o watchdog e não continue iniciando todos repetidamente; teste as subpastas separadas para diagnosticar. Evite executar ensure [carros] enquanto recursos da categoria já estão ativos, pois ensure pode reiniciá-los.

Reserve espaço para os quatro downloads, extração e cópia final; use preferencialmente SSD. Preserve backup e respeite os direitos dos criadores originais antes de qualquer redistribuição.

## Testes

Os testes automatizados em tests/test_fusion.py usam packs sintéticos e não são equivalentes a validar os quatro downloads reais dentro do FiveM.
