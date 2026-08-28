# Job: neon city walk (T2V — Wan2.1)

Geração de vídeo text-to-video: homem sozinho caminhando por cidade futurista
neon após chuva pesada, câmera acompanhando o personagem.

## Especificação → parâmetros Wan2.1

| Spec (brief)              | Parâmetro Wan2.1            | Detalhe |
|---------------------------|-----------------------------|---------|
| Duração: 5 s              | `--frame_num 81`            | 81 frames ÷ 16 fps = 5,06 s. `frame_num` deve ser `4n+1` (81 = 4·20+1). |
| Resolução: 480p           | `--size 832*480`            | 480P landscape 16:9 do Wan2.1. |
| FPS: 16–24                | nativo **16 fps**           | O Wan2.1 amostra a 16 fps. Para 24 fps, rode `SAVE_FPS=24 ./run.sh` (resample via ffmpeg). |
| Prompt (inglês)           | `--prompt`                  | `PROMPT.txt` — o movimento de câmera ("camera tracks backward ... moves closer to his face") já está incluído no texto. |
| Negative prompt           | `--neg_prompt`              | `NEGATIVE_PROMPT.txt`. Flag adicionada neste repositório; se vazia, o pipeline usa o negative prompt embutido (em chinês), que cobre essencialmente os mesmos itens (qualidade baixa, dedos extras, telenovela/anime, texto/subtítulo, etc.). |
| Movimento: câmera acompanhando o personagem | descrito no prompt | O T2V do Wan2.1 não tem parâmetro de câmera separado — o direcionamento de câmera vem do texto. |

## Como rodar (na máquina com GPU)

```sh
# 1) Dependências
pip install -r requirements.txt

# 2) Download do checkpoint
huggingface-cli download Wan-AI/Wan2.1-T2V-14B --local-dir ./Wan2.1-T2V-14B
# ou (alternativa leve, ~8 GB VRAM):
huggingface-cli download Wan-AI/Wan2.1-T2V-1.3B --local-dir ./Wan2.1-T2V-1.3B

# 3) Gerar
./jobs/neon_city_walk/run.sh                  # t2v-14B (melhor realismo)
MODEL=t2v-1.3B ./jobs/neon_city_walk/run.sh   # fallback p/ GPUs menores
SEED=7 ./jobs/neon_city_walk/run.sh           # trocar seed p/ tentar variações
SAVE_FPS=24 ./jobs/neon_city_walk/run.sh      # saída em 24 fps
```

## Recomendações

- **Modelo:** para humanos realistas e cinematografia, use **t2v-14B**
  (guide scale 5.0 / shift 5.0, padrão). O 1.3B já roda em ~8,2 GB VRAM
  (≈4 min por clip de 5 s em RTX 4090) e usa `--sample_shift 8
  --sample_guide_scale 6` (recomendação oficial do README), que o
  `run.sh` aplica automaticamente.
- **VRAM do 14B:** ~24 GB+ com `--offload_model True --t5_cpu`
  (já incluídos no script); multi-GPU: ver seção "Multi-GPU" do README raiz.
- **Iteração:** fixe `SEED` e ajuste o prompt (ex.: reforçar "slow dolly
  backward, medium shot tightening to close-up on face") antes de gastar
  gerações inteiras mudando tudo de uma vez.
- O vídeo sai no diretório raiz do repositório com nome automático
  (`t2v-14B_832*480_1_1_<prompt>_<timestamp>.mp4`).
