# Skill: Marca d'água de texto estilo "NUAKY"

Aplica (e, se necessário, substitui) marca d'água de texto em vídeos no estilo definido
pelos projetos anteriores do usuário: texto branco suave, semitransparente, bordas
difusas, fonte arredondada em negrito — discreto e profissional.

## Quando usar

- Usuário pede para "usar a mesma marca NUAKY" / "colocar marca com o nome X" em um vídeo.
- Usuário pede para trocar uma marca d'água existente por texto no mesmo estilo.

## A fórmula (parâmetros extraídos de análise real)

| Parâmetro | Valor | Origem |
|---|---|---|
| Fonte | **Nunito ExtraBold** (variable font em `fonts/`, licença OFL) | combina visualmente com a marca original analisada |
| Cor/modo | **branco aditivo** (`saida = fundo + lift` com saturação) | medido na marca original: sempre ilumina o fundo |
| Presença (lift) | pico **26/255** (~10%) | idem — discreta mas legível |
| Bordas | blur gaussiano **σ ≈ 0,0545 × altura das caps** | marca original era suave/difusa |
| Tamanho padrão | caps = **2,34% da altura** do quadro | marca de referência (30 px em 1280) |
| Posição padrão | **centro horizontal, 71% da altura** | mesma da marca de referência |
| Posição "rodapé" | centro horizontal, **base a 8 px da borda interna do conteúdo** (nunca sobre faixa preta) | pedido do usuário no projeto Naruto |
| Estabilidade | camada 100% estática (mesmo px em todo frame) | zero tremulação/deslocamento |

### Ajustes validados

- "60% maior" ⇒ `--scale 1.6` (caps 22 px em 576 ⇒ bbox 108×23 px).
- Remoção de marca antiga: estimar o glifo por **mediana temporal** (mediana de ~110
  frames amostrados) → máscara estática (high-pass > 4, close 3×3, dilate 5×5) →
  **cv2.inpaint TELEA raio 5** por frame. Resultado limpo e temporalmente estável.

## Catálogo de fontes e textos observados (para futuros projetos no mesmo estilo)

1. **Marca d'água de referência ("Hossamosh")** — sans arredondada geométrica em
   negrito, branca, aditiva ~10-25%, caps ~2,3% da altura, centro-inferior (~71% H),
   bordas bem difusas. ⇒ Recriada fielmente com **Nunito ExtraBold** (projeto NUAKY).
2. **Avatar circular (projeto 1)** — logomarca em disco (personagem com boné vermelho),
   aplicada em Ø ≈ 7,5% da altura do quadro, corte circular com anti-aliasing 4×,
   centralizada no mesmo ponto da marca de texto substituída.
3. **Legendas animadas do vídeo Naruto** (kinetic typography — conteúdo, PRESERVAR):
   - Serifada de **alto contraste estilo Didone (Didot/Bodoni)**, pesos mistos,
     itálico intercalado, palavras-chave em caixa alta;
   - Paleta vibrante: amarelo-ouro, vermelho, verde, ciano, azul, branco e cinza;
   - Tamanhos grandes sobrepostos ("stacking"), posições variadas no quadro;
   - Texto alternativo: serifada branca grande central ("no entanto", "sábio").
   - Moldura: cantos arredondados com faixa preta (~5 px no centro do rodapé; conteúdo
     termina em y ≈ 570 de 576).

## Encode final (padrão dos projetos)

`libx264 preset slow crf 21–23`, `yuv420p`, tags **BT.709** (`-colorspace/-color_primaries/-color_trc bt709 -color_range tv`),
áudio **copiado** do original (`-c:a copy` — sem recodificação), `+faststart`,
mesmos fps/resolução/duração do vídeo de entrada.

## Como executar

```bash
# ambiente (uma vez por sandbox)
python3 -m venv .venv
.venv/bin/pip install opencv-python-headless pillow numpy imageio-ffmpeg

# aplicação padrão (centro a 71% da altura)
.venv/bin/python skills/marca-dagua-nuaky/apply_watermark.py \
    --input ENTRADA.mp4 --output SAIDA.mp4

# versão rodapé (fora da faixa preta) e 60% maior
.venv/bin/python skills/marca-dagua-nuaky/apply_watermark.py \
    --input ENTRADA.mp4 --output SAIDA.mp4 --scale 1.6 --position bottom
```

Outras opções: `--text`, `--cap-frac`, `--lift`, `--crf` (ver `apply_watermark.py -h`).

## Checklist de QA (fazer sempre)

1. Extrair 3–5 frames (início/meio/fim) e conferir: marca legível, discreta, na posição
   certa, fora de faixas pretas, sem cobrir elementos importantes.
2. Conferir metadados com `ffmpeg -i`: resolução, fps, duração e áudio idênticos à entrada.
3. Zoom 2–3× na marca: bordas suaves, sem halo, sem serrilhado.
4. Se substituiu marca antiga: verificar que o glifo antigo sumiu e o fundo ficou natural.

## Avisos

- A fonte Nunito é SIL Open Font License (ver `fonts/OFL.txt`) — redistribuição permitida.
- `imageio-ffmpeg` fornece o binário ffmpeg; não depende de instalação de sistema.
- Em sandboxes com reinício, o venv some: recriá-lo leva ~10 s (ver "Como executar").
