#!/usr/env python3
# -*- coding: utf-8 -*-
"""
Aplica moldura fina arredondada + logo gótica NUAKY ao vídeo.

- Moldura com GAP no rodapé central (transparente onde a logo fica)
- Logo gótica NUAKY centralizada no canto inferior
- Remove marca d'água gótica existente do vídeo original
- Apenas moldura + logo, sem textos extras
"""
import argparse
import subprocess
import numpy as np
import cv2
from PIL import Image, ImageDraw
import imageio_ffmpeg
import os

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_GOTHIC = os.path.join(SKILL_DIR, "logo_NUAKY_gothic.png")


def detect_letterbox(cap, W, H, n_samples=30):
    """Detecta barras pretas (letterbox/pillarbox)."""
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    top_edges, bot_edges, left_edges, right_edges = [], [], [], []
    for i in np.linspace(0, n - 1, min(n_samples, n)).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, fr = cap.read()
        if not ok:
            continue
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        top = 0
        while top < H and g[top, W // 4:3 * W // 4].mean() < 10:
            top += 1
        top_edges.append(top)
        bot = H - 1
        while bot > 0 and g[bot, W // 4:3 * W // 4].mean() < 10:
            bot -= 1
        bot_edges.append(bot + 1)
        left = 0
        while left < W and g[H // 4:3 * H // 4, left].mean() < 10:
            left += 1
        left_edges.append(left)
        right = W - 1
        while right > 0 and g[H // 4:3 * H // 4, right].mean() < 10:
            right -= 1
        right_edges.append(right + 1)
    return int(np.median(top_edges)), int(np.median(bot_edges)), \
           int(np.median(left_edges)), int(np.median(right_edges))


def build_watermark_mask(cap, W, H, top_y, bot_y, left_x, right_x,
                          n_samples=30):
    """Cria máscara para a marca d'água gótica NUAKY no rodapé."""
    cw = right_x - left_x
    ch = bot_y - top_y
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1

    band_top = top_y + int(ch * 0.87)
    band_h = bot_y - band_top
    band_left = left_x + int(cw * 0.15)
    band_right = left_x + int(cw * 0.85)
    band_w = band_right - band_left

    acc = np.zeros((band_h, band_w, 3), dtype=np.float64)
    cnt = 0
    for i in np.linspace(0, n - 1, min(n_samples, n)).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, fr = cap.read()
        if not ok:
            continue
        region = fr[band_top:bot_y, band_left:band_right].astype(np.float64)
        acc += region
        cnt += 1
    if cnt == 0:
        return np.zeros((H, W), dtype=np.uint8)
    mean_frame = acc / cnt
    mean_gray = mean_frame.mean(axis=2)

    kernel_size = 61
    kernel = np.ones((1, kernel_size), np.float64) / kernel_size
    local_mean = cv2.filter2D(mean_gray, -1, kernel)
    diff = local_mean - mean_gray
    mask_region = (diff > 5).astype(np.uint8) * 255

    kernel_m = np.ones((3, 3), np.uint8)
    mask_region = cv2.morphologyEx(mask_region, cv2.MORPH_CLOSE, kernel_m, iterations=1)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask_region)
    cleaned = np.zeros_like(mask_region)
    for i in range(1, num_labels):
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]
        area = stats[i, cv2.CC_STAT_AREA]
        if 30 <= w <= 350 and 8 <= h <= 45 and area >= 60:
            cleaned[labels == i] = 255

    kernel_d = np.ones((3, 3), np.uint8)
    cleaned = cv2.dilate(cleaned, kernel_d, iterations=2)

    mask_full = np.zeros((H, W), dtype=np.uint8)
    mask_full[band_top:bot_y, band_left:band_right] = cleaned
    return mask_full


def build_frame_with_logo_gap(cw, ch, inset, radius, stroke, color,
                                logo_array, logo_w, logo_h, logo_x, logo_y,
                                gap_extra=12):
    """Cria overlay da moldura com GAP onde a logo fica + a logo.

    A moldura é desenhada como dois arcos: parte superior completa +
    duas laterais que param antes da logo. O espaço da logo fica
    transparente na moldura.
    """
    im = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    frame_color = (*color, 255)
    no_color = (0, 0, 0, 0)

    # Limites da moldura
    x1, y1 = inset, inset
    x2, y2 = cw - inset - 1, ch - inset - 1

    # Limites do GAP na parte inferior (onde a logo fica)
    gap_left = logo_x - gap_extra
    gap_right = logo_x + logo_w + gap_extra
    # A moldura inferior vai de y2, mas com gap no meio

    # Desenhar moldura em segmentos:
    # 1. Topo completo (arco superior + laterais superiores)
    # 2. Laterais até o gap
    # 3. Segmentos inferiores esquerdo e direito (fora do gap)

    # Usar rounded_rectangle completo e depois "apagar" o gap
    d.rounded_rectangle(
        [x1, y1, x2, y2],
        radius=radius,
        outline=frame_color,
        width=stroke,
    )

    # Apagar o segmento inferior da moldura dentro do gap
    # Desenhar linha transparente sobre o gap na parte de baixo
    gap_y = y2  # linha inferior da moldura
    # Apagar traço horizontal no gap (com margem para o stroke)
    d.line([(gap_left, gap_y), (gap_right, gap_y)], fill=no_color, width=stroke + 4)

    # Desenhar a logo no centro do gap
    logo_pil = Image.fromarray(logo_array).convert("RGBA")
    im.paste(logo_pil, (logo_x, logo_y), logo_pil if logo_pil.mode == "RGBA" else None)

    return np.array(im, dtype=np.float32) / 255.0


def apply(args):
    cap = cv2.VideoCapture(args.input)
    if not cap.isOpened():
        raise SystemExit(f"não consegui abrir {args.input}")
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0

    top_y, bot_y, left_x, right_x = detect_letterbox(cap, W, H)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    cw = right_x - left_x
    ch = bot_y - top_y
    print(f"[frame] entrada: {W}x{H} @ {fps:g} fps, {total_frames} frames")
    print(f"[frame] conteúdo: x[{left_x}:{right_x}] y[{top_y}:{bot_y}] = {cw}x{ch}")

    # Detecta e remove marca existente
    print("[frame] detectando marca d'água existente...")
    wm_mask = build_watermark_mask(cap, W, H, top_y, bot_y, left_x, right_x)
    ys, xs = np.nonzero(wm_mask > 0)
    if len(xs) > 0:
        print(f"[frame] marca encontrada: bbox x{xs.min()}-{xs.max()} "
              f"y{ys.min()}-{ys.max()} — será removida")
    else:
        print("[frame] nenhuma marca existente detectada")
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    # Carrega e prepara a logo gótica
    logo_src = Image.open(args.logo)
    # Se for grayscale (L), converter para RGBA com transparência:
    # pixels brancos = logo visível, pixels pretos = transparente
    if logo_src.mode == "L":
        # Cria alpha channel: branco = opaco, preto = transparente
        alpha = logo_src.copy()
        logo_rgba = Image.new("RGBA", logo_src.size, (0, 0, 0, 0))
        logo_rgba.putalpha(alpha)
        # Pinta a logo de branco
        logo_rgba = Image.fromarray(
            np.where(np.array(logo_src)[:, :, None] > 128,
                     np.array([255, 255, 255, 255], dtype=np.uint8),
                     np.array([0, 0, 0, 0], dtype=np.uint8))
        )
        logo_src = logo_rgba
    elif logo_src.mode != "RGBA":
        logo_src = logo_src.convert("RGBA")

    # Redimensiona a logo: largura = fração do conteúdo
    target_w = int(cw * args.logo_width_frac)
    aspect = logo_src.height / logo_src.width
    target_h = int(target_w * aspect)
    logo_resized = logo_src.resize((target_w, target_h), Image.LANCZOS)

    # Posição da logo: centralizada no rodapé, colada na borda inferior da moldura
    inset = args.frame_inset
    logo_x = (cw - target_w) // 2
    logo_y = ch - inset - target_h - args.logo_bottom_pad

    print(f"[frame] logo: {target_w}x{target_h} em ({logo_x},{logo_y})")
    print(f"[frame] moldura: inset={inset} radius={args.frame_radius} "
          f"stroke={args.frame_stroke} color={args.frame_color}")

    frame_color = tuple(int(c) for c in args.frame_color.split(","))

    overlay = build_frame_with_logo_gap(
        cw, ch,
        inset=inset,
        radius=args.frame_radius,
        stroke=args.frame_stroke,
        color=frame_color,
        logo_array=np.array(logo_resized),
        logo_w=target_w,
        logo_h=target_h,
        logo_x=logo_x,
        logo_y=logo_y,
        gap_extra=14,
    )

    overlay_alpha = overlay[:, :, 3:4]
    overlay_rgb = overlay[:, :, :3]

    overlay_full_rgb = np.zeros((H, W, 3), dtype=np.float32)
    overlay_full_a = np.zeros((H, W, 1), dtype=np.float32)
    overlay_full_rgb[top_y:top_y + ch, left_x:left_x + cw] = overlay_rgb
    overlay_full_a[top_y:top_y + ch, left_x:left_x + cw] = overlay_alpha

    FF = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.Popen(
        [FF, "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
         "-i", args.input, "-map", "0:v:0", "-map", "1:a:0?",
         "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
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
        fr = fr.astype(np.float32)

        if wm_mask.any():
            dst = cv2.inpaint(fr.astype(np.uint8), wm_mask, 5, cv2.INPAINT_TELEA)
            fr = dst.astype(np.float32)

        a = overlay_full_a
        fr = fr * (1 - a) + overlay_full_rgb * 255 * a
        fr = np.clip(fr, 0, 255).astype(np.uint8)

        proc.stdin.write(fr.tobytes())
        n += 1
        if n % 200 == 0:
            pct = f" ({n*100//total_frames}%)" if total_frames else ""
            print(f"[frame] {n} frames{pct}...", flush=True)

    cap.release()
    proc.stdin.close()
    proc.wait()
    print(f"[frame] OK -> {args.output} ({n} frames)")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Moldura + logo gótica NUAKY")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--logo", default=LOGO_GOTHIC, help="Logo a colocar no rodapé")
    p.add_argument("--logo-width-frac", type=float, default=0.50,
                   help="Largura da logo como fração do conteúdo (padrão 0.50)")
    p.add_argument("--logo-bottom-pad", type=int, default=2,
                   help="Padding da logo até a borda inferior da moldura")

    p.add_argument("--frame-inset", type=int, default=9)
    p.add_argument("--frame-radius", type=int, default=16)
    p.add_argument("--frame-stroke", type=int, default=2)
    p.add_argument("--frame-color", default="180,180,180")

    p.add_argument("--crf", type=int, default=21)
    p.add_argument("--preset", default="slow")

    args = p.parse_args()
    apply(args)
