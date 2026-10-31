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
