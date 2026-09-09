#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aplica a marca d'água de texto "estilo NUAKY" em um vídeo.

Estilo (extraído da análise da marca original dos projetos anteriores):
  - Fonte: Nunito ExtraBold (arredondada, OFL) -- ver fonts/
  - Cor: branco aplicado de forma ADITIVA (quanto mais escuro o fundo,
    mais presente; nunca fica mais escura que o fundo)
  - Presença (lift) padrão: pico +26 de 255 (~10%)
  - Bordas suaves: gaussian blur proporcional ao tamanho do texto
  - Posição padrão: centro-inferior a 71% da altura (igual à marca de
    referência analisada). Opção "bottom": rodapé encostado a ~8 px da
    borda interna da área de conteúdo (nunca sobre faixas pretas de
    letterbox/pillarbox -- a borda de conteúdo é detectada).

Dependências (venv): opencv-python-headless pillow numpy imageio-ffmpeg

Uso básico:
  python apply_watermark.py --input video.mp4 --output saida.mp4
  python apply_watermark.py --input video.mp4 --output saida.mp4 \
      --text NUAKY --scale 1.6 --position bottom
"""
import argparse
import subprocess
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg
import os

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FONT = os.path.join(SKILL_DIR, "fonts", "Nunito-VariableFont_wght.ttf")

CAP_FRAC = 0.0234      # altura das maiúsculas como fração da altura do quadro (padrão analisado)


def build_lift(W, H, text, font_path, cap_px, position, bottom_margin, lift_peak):
    """Cria a camada de brilho aditivo (H x W float32) com o texto."""
    # tamanho da fonte para obter caps ~cap_px (Nunito: cap ~0.733 * size)
    size = max(8, int(round(cap_px / 0.733)))
    font = ImageFont.truetype(font_path, size)
    try:
        font.set_variation_by_name(b"ExtraBold")
    except Exception:
        pass
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    bbox = d.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (W - bbox[0] * 2 - tw) // 2  # centralizado pelo bbox visual
    x = (W // 2) - bbox[0] - tw // 2
    if position == "center71":
        cy = int(0.711 * H)
        y = cy - bbox[1] - (bbox[3] - bbox[1]) // 2
        d.text((x, y), text, font=font, fill=255)
    else:  # bottom: detecta borda interna do conteúdo na hora do render
        raise RuntimeError("position 'bottom' é resolvida em apply() com detecção de borda")
    lift = np.array(im, dtype=np.float32)
    sigma = max(0.4, cap_px * 0.0545)          # blur proporcional (~1.2 px p/ cap 22)
    lift = cv2.GaussianBlur(lift, (0, 0), sigma)
    if lift.max() > 0:
        lift = lift / lift.max() * lift_peak
    return lift


def detect_content_bottom(cap, W, H, n_samples=24):
    """Menor y de conteúdo válido perto do rodapé, medido em colunas centrais
    (robusto a faixas pretas de letterbox e cantos arredondados)."""
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    edges = []
    for i in np.linspace(0, n - 1, min(n_samples, n)).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, fr = cap.read()
        if not ok:
            continue
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        seg = g[:, W // 4: 3 * W // 4].mean(axis=1)
        y = H - 1
        while y > 0 and seg[y] < 14:
            y -= 1
        edges.append(int(y) + 1)  # primeira linha preta
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    return int(np.median(edges)) if edges else H


def apply(args):
    cap = cv2.VideoCapture(args.input)
    if not cap.isOpened():
        raise SystemExit(f"não consegui abrir {args.input}")
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    cap_px = args.cap_frac * H * args.scale
    if args.position == "bottom":
        content_bottom = detect_content_bottom(cap, W, H)
        cy = None
        bottom_edge = content_bottom - args.bottom_margin
    else:
        content_bottom = None
        cy = (0.711 if args.position == "center71" else args.y_frac) * H
        bottom_edge = None

    # cria camada de texto
    size = max(8, int(round(cap_px / 0.733)))
    font = ImageFont.truetype(args.font, size)
    try:
        font.set_variation_by_name(b"ExtraBold")
    except Exception:
        pass
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    bbox = d.textbbox((0, 0), args.text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (W // 2) - bbox[0] - tw // 2
    if bottom_edge is not None:
        y = bottom_edge - bbox[3]
    else:
        y = int(cy) - bbox[1] - th // 2
    d.text((x, y), args.text, font=font, fill=255)
    lift = np.array(im, dtype=np.float32)
    sigma = max(0.4, cap_px * 0.0545)
    lift = cv2.GaussianBlur(lift, (0, 0), sigma)
    if lift.max() > 0:
        lift = lift / lift.max() * args.lift
    ys, xs = np.nonzero(lift > 2)
    print(f"[skill] marca '{args.text}' bbox x{xs.min()}-{xs.max()} y{ys.min()}-{ys.max()} "
          f"({xs.max()-xs.min()}x{ys.max()-ys.min()} px) em {W}x{H}@{fps:g}")

    FF = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.Popen(
        [FF, "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
         "-i", args.input, "-map", "0:v:0", "-map", "1:a:0?",
         "-c:v", "libx264", "-preset", "slow", "-crf", str(args.crf),
         "-profile:v", "high", "-pix_fmt", "yuv420p", "-vsync", "cfr",
         "-colorspace", "bt709", "-color_primaries", "bt709",
         "-color_trc", "bt709", "-color_range", "tv",
         "-c:a", "copy", "-movflags", "+faststart", args.output],
        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        fr = np.clip(fr.astype(np.float32) + lift[:, :, None], 0, 255).astype(np.uint8)
        proc.stdin.write(fr.tobytes())
        n += 1
        if n % 400 == 0:
            print(f"[skill] {n} frames...", flush=True)
    cap.release()
    proc.stdin.close()
    proc.wait()
    print(f"[skill] OK -> {args.output} ({n} frames)")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Marca d'água de texto estilo NUAKY")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--text", default="NUAKY")
    p.add_argument("--font", default=DEFAULT_FONT)
    p.add_argument("--cap-frac", type=float, default=CAP_FRAC,
                   help="altura das caps como fração de H (padrão 0.0234)")
    p.add_argument("--scale", type=float, default=1.0,
                   help="multiplicador de tamanho (ex.: 1.6 = 60%% maior)")
    p.add_argument("--position", choices=["center71", "bottom"], default="center71")
    p.add_argument("--y-frac", type=float, default=0.711,
                   help="fração de altura p/ centro do texto quando --position center71")
    p.add_argument("--bottom-margin", type=int, default=8,
                   help="px acima da borda de conteúdo quando --position bottom")
    p.add_argument("--lift", type=float, default=26.0, help="pico aditivo (0-255)")
    p.add_argument("--crf", type=int, default=22)
    apply(p.parse_args())
