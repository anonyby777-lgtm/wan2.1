#!/usr/bin/env bash
# =============================================================================
# Job: neon_city_walk — Wan2.1 T2V
# Especificacao: 5s | 480p (832x480) | 16 fps nativo (24 opcional via ffmpeg)
# Camera: acompanhando o personagem (ja descrito no prompt)
#
# Uso (na maquina com GPU):
#   ./run.sh                          # Wan2.1-T2V-14B (recomendado p/ realismo)
#   MODEL=t2v-1.3B ./run.sh           # Wan2.1-T2V-1.3B (roda em ~8 GB VRAM)
#   SEED=123 ./run.sh                 # seed fixa (padrao: 42)
#   SAVE_FPS=24 ./run.sh              # resample do video 16 -> 24 fps (ffmpeg)
#
# Checkpoints esperados (baixe antes de rodar):
#   huggingface-cli download Wan-AI/Wan2.1-T2V-14B  --local-dir ./Wan2.1-T2V-14B
#   huggingface-cli download Wan-AI/Wan2.1-T2V-1.3B --local-dir ./Wan2.1-T2V-1.3B
# =============================================================================
set -euo pipefail

# --- Config -------------------------------------------------------------------
MODEL="${MODEL:-t2v-14B}"                 # t2v-14B | t2v-1.3B
if [[ "$MODEL" == "t2v-1.3B" ]]; then
  CKPT_DIR="${CKPT_DIR:-./Wan2.1-T2V-1.3B}"
else
  CKPT_DIR="${CKPT_DIR:-./Wan2.1-T2V-14B}"
fi
SEED="${SEED:-42}"
SAVE_FPS="${SAVE_FPS:-16}"                 # 16 = fps nativo do Wan2.1; 24 = resample p/ ffmpeg

# 5 segundos a 16 fps = 81 frames (frame_num deve ser 4n+1 -> 81/16s ~= 5.06 s)
SIZE="832*480"                             # 480P landscape (16:9) do Wan2.1
FRAME_NUM=81

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "$REPO_ROOT"

PROMPT="$(cat "${SCRIPT_DIR}/PROMPT.txt")"
NEG_PROMPT="$(cat "${SCRIPT_DIR}/NEGATIVE_PROMPT.txt")"

# --- Command ------------------------------------------------------------------
# 14B: guide/shift padrao (5.0 / 5.0) — melhores resultados cinematicos.
# 1.3B: recomendacoes oficiais do README (shift 8, guide 6, offload + T5 em CPU).
CMD=(python generate.py
  --task "$MODEL"
  --size "$SIZE"
  --frame_num "$FRAME_NUM"
  --ckpt_dir "$CKPT_DIR"
  --base_seed "$SEED"
  --offload_model True
  --t5_cpu
  --prompt "$PROMPT"
  --neg_prompt "$NEG_PROMPT"
)
if [[ "$MODEL" == "t2v-1.3B" ]]; then
  CMD+=(--sample_shift 8 --sample_guide_scale 6)
fi

echo "[neon_city_walk] ${MODEL} | ${SIZE} | ${FRAME_NUM} frames | seed=${SEED}"
START_TS=$(date +%s)
"${CMD[@]}"

# --- Optional: resample do 16 fps nativo para SAVE_FPS (ex.: 24) --------------
if [[ "$SAVE_FPS" != "16" ]] && command -v ffmpeg >/dev/null 2>&1; then
  LATEST="$(find . -maxdepth 1 -name '*.mp4' -newermt "@${START_TS}" -printf '%T@ %p\n' | sort -rn | head -1 | cut -d' ' -f2-)"
  if [[ -n "${LATEST}" ]]; then
    DEST="${LATEST%.mp4}_${SAVE_FPS}fps.mp4"
    echo "[neon_city_walk] Resampling ${LATEST} -> ${SAVE_FPS} fps (${DEST})"
    ffmpeg -y -loglevel error -i "$LATEST" -r "$SAVE_FPS" \
      -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -an "$DEST"
  fi
fi
echo "[neon_city_walk] Done."
