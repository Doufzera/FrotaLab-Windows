# Instruções do FrotaLab

1. Abra a aba **Actions** deste repositório, selecione **Build Windows EXE** e aguarde a conclusão.
2. Abra a execução bem-sucedida, seção **Artifacts**, e baixe **FrotaLab-Windows**.
3. Extraia o arquivo baixado e execute `FrotaLab.exe`.
4. Na aba Downloads, selecione as fontes e baixe os ZIPs. O processo pode usar muito espaço e levar tempo; recomendamos ao menos 50 GB livres.
5. Na aba Auditoria, gere os relatórios. Na aba Exportação, gere os ZIPs por fonte.

## Limitações importantes

- Esta é uma **primeira versão funcional conservadora**; ela não remove duplicações automaticamente nem edita geometria ou texturas YFT/YTD. Os ZIPs exportados preservam as fontes, não representam frota otimizada para FPS.
- Não instale simultaneamente ZIPs de fontes com códigos/modelos repetidos. Avalie `duplicados.json` e referências `.meta` antes de consolidar.
- A verificação de XML não substitui testes no FiveM. Todas as configurações e recursos devem passar por teste em servidor de homologação.
- A aplicação mantém downloads originais e não modifica o conteúdo de origem.
- Caso Windows SmartScreen avise sobre um executável sem assinatura digital, confira que ele foi baixado diretamente do build do seu repositório.


## Instalação do Pack 1 no FiveM

- A partir da versão com a correção de exportação, a aba Exportação cria `PLOKS_CARS.zip` para o primeiro pacote. Depois de extrair, deve existir exatamente `resources/[carros]/PLOKS_CARS/fxmanifest.lua`, juntamente com `data/`, `stream/`, `server.lua` e `vehicle_names.lua`.
- No `server.cfg`, use `ensure PLOKS_CARS`, **não** `ensure pacote_01` nem `ensure FiveM-Civ-Car-Pack-master`.
- Inicie o servidor sem os outros packs de veículos para isolar conflitos. Se o servidor reiniciar durante a carga, desabilite temporariamente o recurso e consulte as primeiras linhas de erro do console/txAdmin antes do reinício.
- O Pack 1 é muito grande. A correção de pastas não reduz o peso dos modelos ou o custo de carregamento. Os outros ZIPs do FrotaLab continuam sendo arquivos de origem, não recursos FiveM consolidados.


## Aba Instalação — selecione o destino de cada pack

1. Baixe e extraia os quatro pacotes pela aba **Downloads**.
2. Abra a aba **Instalação**. Há um botão **Escolher pasta** independente para cada um dos quatro packs.
3. Selecione a pasta de recursos do seu servidor, por exemplo D:\FiveM\server\resources. Pode ser a mesma pasta resources para todos ou pastas resources de servidores diferentes.
4. Para cada pack, o FrotaLab **cria automaticamente** a categoria:
   - Pack 1 → resources\[carros]\
   - Pack 2 → resources\[carros2]\
   - Pack 3 → resources\[carros3]\
   - Pack 4 → resources\[carros4]\
5. Se você selecionar a própria pasta [carrosN], o programa a usa diretamente e **não** cria [carrosN]\[carrosN].
6. Clique em **Instalar Pack N**, um a um, ou em **Instalar os 4 packs nos destinos escolhidos**.
7. A instalação cria um INSTRUCOES_FROTALAB.txt dentro de cada categoria, com os nomes dos recursos para iniciar individualmente.
8. O FrotaLab **não substitui nem apaga** uma categoria já ocupada. Para reinstalar, faça backup e deixe a categoria vazia; o original exportado e os downloads permanecem intactos.

### Conteúdo das categorias

- [carros]: o Pack 1 é dividido por fabricante por padrão (CIV_ACURA, CIV_AUDI, etc.), para permitir testes separados. A opção de manter PLOKS_CARS inteiro existe, **mas já provocou travamento svMain neste servidor**.
- [carros2]: Lore_Friendly_Car_Pack e os seis packs de rodas encontrados.
- [carros3]: LNWK-CARS (sem as configurações alternativas de DriftHandling, que permanecem salvas na pasta originais).
- [carros4]: LIVID_LF_CARS e seus recursos de som auxiliares, em pastas separadas.

**Cuidado**: ensure [carros] pode ativar muitas marcas e reintroduzir o travamento. Após a instalação, no console txAdmin use refresh seguido de ensure CIV_ACURA e avance uma marca por vez. Teste também os demais pacotes separadamente; nomes de spawn repetidos continuam sendo uma fonte possível de conflito. **Instalar os arquivos não inicia os recursos no servidor**. O processo copia arquivos, não altera o server.cfg nem reinicia o FiveM.


## Erro de XML no Pack 1 — Bugatti Bolide

A origem PLOKMJNB/FiveM-Civ-Car-Pack inclui um comentário XML inválido na linha 132 do arquivo `PLOKS_CARS/data/[BUGATTI]/bolide/vehicles.meta`. Agora, ao instalar o Pack 1 (inteiro ou dividido) ou exportá-lo por fabricante, o FrotaLab identifica separadores de hífens malformados, corrige-os **somente na cópia** e registra `CORRECOES_META.txt` no recurso corrigido. O arquivo na pasta `originais` permanece intocado. Outros tipos de XML inválido não são corrigidos automaticamente: serão relatados para revisão manual.

Se a instalação anterior falhou, preserve backup dos recursos existentes, remova ou renomeie a categoria `resources/[carros]` antiga **para fora da pasta resources**, e refaça a instalação do Pack 1 na aba **Instalação**, com a opção dividir por fabricantes marcada. O FrotaLab não sobrescreve categoria já ocupada. **Não é necessário baixar tudo outra vez se os arquivos originais já estiverem em `Documents/FrotaLab/originais/pacote_01`**.

Depois, no console txAdmin, use `refresh` e `ensure CIV_ACURA`; caso funcione, experimente `ensure CIV_BUGATTI`. Não use `ensure PLOKS_CARS` ou `ensure [carros]` para testar todos juntos. Corrigir XML não elimina problemas de memória, colisões de spawn ou travamentos associados ao tamanho dos arquivos.
