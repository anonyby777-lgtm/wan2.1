#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aplica marca NUAKY completa com moldura e tela final
- Remove marca antiga (SANTARONI27) via mediana + inpaint
- Aplica nova marca "© NUAKY COPYRIGHT RESERVED." no rodapé com moldura
- Substitui tela final preta por "NUAKY" grande + moldura + brasas

Uso: python aplicar_marca_completa.py --input input.mp4 --output output.mp4
"""
import argparse
import subprocess
import os
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_CINZEL = os.path.join(SKILL_DIR, "fonts", "Cinzel.ttf")
FONT_CINZEL_REG = FONT_CINZEL  # mesmo arquivo, pesos via variação
DEFAULT_FOOTER = "© NUAKY COPYRIGHT RESERVED."

def detect_content_bottom(cap, W, H, n_samples=24):
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    edges = []
    for i in np.linspace(0, n-1, min(n_samples, n)).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, fr = cap.read()
        if not ok:
            continue
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        seg = g[:, W//4:3*W//4].mean(axis=1)
        y = H-1
        while y > 0 and seg[y] < 14:
            y -= 1
        edges.append(int(y)+1)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    return int(np.median(edges)) if edges else H

def estimate_old_watermark_mask(input_path, W, H, n_samples=110):
    """Estima máscara da marca antiga via mediana temporal + high-pass"""
    cap = cv2.VideoCapture(input_path)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    idxs = np.linspace(0, n-1, min(n_samples, n)).astype(int)
    frames = []
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, fr = cap.read()
        if ok:
            frames.append(fr)
    cap.release()
    if not frames:
        return None
    stack = np.stack(frames, axis=0)  # N x H x W x 3
    median = np.median(stack, axis=0).astype(np.uint8)
    gray = cv2.cvtColor(median, cv2.COLOR_BGR2GRAY)
    # high-pass: subtrai blur e threshold
    blur = cv2.GaussianBlur(gray, (0,0), 3)
    hp = cv2.absdiff(gray, blur)
    _, thresh = cv2.threshold(hp, 4, 255, cv2.THRESH_BINARY)
    # focar no rodapé (onde fica a marca)
    roi_y0 = int(H*0.88)
    mask = np.zeros_like(gray, dtype=np.uint8)
    mask[roi_y0:H, :] = thresh[roi_y0:H, :]
    # limpar e dilatar
    kernel_close = np.ones((3,3), np.uint8)
    kernel_dilate = np.ones((5,5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close)
    mask = cv2.dilate(mask, kernel_dilate, iterations=1)
    # remover componentes muito grandes (não é texto) ou muito pequenos (ruído)
    # manter apenas região central horizontal (marca centralizada)
    # filtrar por área
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    filtered = np.zeros_like(mask)
    H_roi = H - roi_y0
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]
        # marca tem largura ~40% W e altura ~15-30px
        if 200 < area < 8000 and w > 100 and h < 50:
            filtered[labels==i] = 255
    # se filtragem remover tudo ou for muito pequena (watermark não detectado bem), usa fallback expandido
    if cv2.countNonZero(filtered) < 1500:
        # fallback: usa bbox central estimado - aumentado para vídeos 1280x718 com marca @JAPAEDITS
        filtered = np.zeros_like(mask)
        # estima bbox da marca antiga: centro horizontal, rodapé - ajustado para ser mais preciso
        est_w = int(W*0.35)  # 448 em 1280, cobre @JAPAEDITS__LG (~282) com margem generosa
        est_h = int(36 * (H/720))
        x0 = (W - est_w)//2
        y0 = H - est_h - 18  # 18px margem do fundo, centralizado verticalmente no rodapé
        # tenta detectar texto para refinar: usa thresh dentro do bbox
        # se não tiver detecção, cria máscara retangular mesmo (inpaint retangular funciona)
        # vamos usar retângulo + dilatação do thresh dentro dele
        crop = thresh[y0-6:y0+est_h+6, x0-10:x0+est_w+10]
        if crop.size>0 and cv2.countNonZero(crop)>20:
            filtered[y0-6:y0+est_h+6, x0-10:x0+est_w+10] = crop
            filtered = cv2.dilate(filtered, kernel_dilate, iterations=1)
        else:
            filtered[y0-6:y0+est_h+6, x0-10:x0+est_w+10] = 255
        print(f"[mask] fallback bbox x0={x0} y0={y0} w={est_w} h={est_h}")
    else:
        print(f"[mask] componentes filtrados: {cv2.countNonZero(filtered)} px")
    return filtered

def build_footer_lift(W, H, text, font_path, lift_peak=58, bottom_edge=None):
    """Cria lift aditivo para footer no rodapé - versão melhorada visibilidade"""
    # tamanho: ~16px altura em 720 => caps ~16px - ligeiramente maior que original 15 para legibilidade
    cap_px = int(16 * (H/720))
    if cap_px < 11:
        cap_px = 11
    size = max(8, int(round(cap_px / 0.60)))  # Cinzel tem cap menor, ajusta
    # Cinzel Bold vs Regular: usamos 600-700 peso visual, mas TTF único
    try:
        font = ImageFont.truetype(font_path, size)
    except:
        font = ImageFont.load_default()
    # medir
    im_dummy = Image.new("L", (W, H), 0)
    d_dummy = ImageDraw.Draw(im_dummy)
    bbox = d_dummy.textbbox((0,0), text, font=font)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    # tracking: Cinzel precisa espaçamento ~0.12em
    # PIL não tem tracking direto; vamos desenhar com espaçamento manual
    # aproximar: adiciona espacamento entre caracteres
    spacing = int(size * 0.12)
    tw_spaced = tw + spacing*(len(text)-1)
    x = (W - tw_spaced)//2 - bbox[0]
    if bottom_edge is not None:
        y = bottom_edge - bbox[3] - 2
    else:
        y = H - th - 12 - bbox[1]
    # desenha com tracking
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    cur_x = x
    for ch in text:
        d.text((cur_x, y), ch, font=font, fill=255)
        # avançar
        cb = d.textbbox((0,0), ch, font=font)
        cw = cb[2]-cb[0]
        cur_x += cw + spacing
    lift = np.array(im, dtype=np.float32)
    blur2 = cv2.GaussianBlur(lift, (0,0), 2)
    blur11 = cv2.GaussianBlur(lift, (0,0), 11)
    # combinar: núcleo forte + bloom suave para visibilidade em fundos escuros e claros
    lift_bloom = lift*0.90 + blur2*0.45 + blur11*0.20
    lift_bloom = np.clip(lift_bloom, 0, 255)
    if lift_bloom.max()>0:
        lift_bloom = lift_bloom / lift_bloom.max() * lift_peak
    lift_bloom = cv2.GaussianBlur(lift_bloom, (0,0), 0.8)
    ys, xs = np.nonzero(lift_bloom>1)
    if len(xs)>0:
        print(f"[footer] text '{text}' bbox x{xs.min()}-{xs.max()} y{ys.min()}-{ys.max()} ({xs.max()-xs.min()}x{ys.max()-ys.min()})")
    return lift_bloom

def build_moldura_mask(W, H, inset=9, radius=16, thickness=2):
    """Cria máscara de moldura arredondada (para overlay aditivo ou desenho direto)"""
    # vamos desenhar moldura como overlay: borda cinza ~150 com alfa
    # retorna imagem BGR com moldura
    img = np.zeros((H, W, 3), dtype=np.uint8)
    # inset pode ser proporcional se video menor
    inset_x = int(inset * (W/720)) if W<720 else inset
    inset_y = int(inset * (H/720)) if H<720 else inset
    rad = int(radius * (min(W,H)/720)) if min(W,H)<720 else radius
    x0, y0 = inset_x, inset_y
    x1, y1 = W - inset_x - 1, H - inset_y - 1
    # cv2 não tem rounded rect direto, vamos usar função
    # desenhar com PIL para anti-aliasing
    pil = Image.new("RGB", (W,H), (0,0,0))
    d = ImageDraw.Draw(pil)
    d.rounded_rectangle([x0, y0, x1, y1], radius=rad, outline=(150,150,150), width=thickness)
    mold = np.array(pil)
    # converter para BGR
    mold_bgr = cv2.cvtColor(mold, cv2.COLOR_RGB2BGR)
    return mold_bgr

def generate_tela_final(W, H, title="NUAKY", footer="© NUAKY COPYRIGHT RESERVED.", inset=9, radius=16):
    """Gera imagem da tela final NUAKY com moldura, fundo quase preto + brasas, título Cinzel - v2 corrigida"""
    bg_val = 11
    img = np.full((H, W, 3), bg_val, dtype=np.uint8)
    # brasas vermelho/laranja nos cantos (gaussianas baixa intensidade)
    # criar layer quente
    heat = np.zeros((H, W, 3), dtype=np.float32)
    # parâmetros: duas gaussianas nos cantos inferiores
    # usar desenho de elipses com blur
    # canto inferior direito e esquerdo
    for cx_frac, cy_frac, color, sigma_factor, intensity in [
        (0.15, 0.88, (45, 25, 120), 0.18, 0.9),  # inferior esquerdo avermelhado
        (0.85, 0.92, (30, 40, 130), 0.20, 0.7),  # inferior direito laranja
        (0.50, 0.95, (20, 30, 100), 0.30, 0.4),  # centro inferior difuso
    ]:
        cx = int(W * cx_frac)
        cy = int(H * cy_frac)
        sigma_x = int(W * sigma_factor)
        sigma_y = int(H * sigma_factor * 0.6)
        # criar gaussiana
        y_grid, x_grid = np.ogrid[:H, :W]
        gauss = np.exp(-(((x_grid - cx)**2)/(2*sigma_x**2) + ((y_grid - cy)**2)/(2*sigma_y**2)))
        heat[:, :, 2] += gauss * color[2] * intensity * 0.15  # R
        heat[:, :, 1] += gauss * color[1] * intensity * 0.12
        heat[:, :, 0] += gauss * color[0] * intensity * 0.10
    # linhas quentes quase imperceptíveis (faixa panorâmica sugerida)
    # adicionar linhas horizontais suaves no meio
    line_y = int(H*0.38)
    line_y2 = int(H*0.68)
    for ly in [line_y, line_y2]:
        y_grid = np.abs(np.arange(H)[:, None] - ly)
        line = np.exp(-(y_grid**2)/(2*(H*0.015)**2)) * 8
        heat[:, :, 2] += line * 0.3
        heat[:, :, 1] += line * 0.15
    # nuvem difusa atrás do título
    cx, cy = W//2, int(H*0.525)
    sigma_x, sigma_y = int(W*0.22), int(H*0.08)
    y_grid, x_grid = np.ogrid[:H, :W]
    cloud = np.exp(-(((x_grid - cx)**2)/(2*sigma_x**2) + ((y_grid - cy)**2)/(2*sigma_y**2)))
    heat[:, :, 2] += cloud * 18 * 0.2
    heat[:, :, 1] += cloud * 10 * 0.15
    heat[:, :, 0] += cloud *  5 * 0.10
    img = np.clip(img.astype(np.float32) + heat, 0, 255).astype(np.uint8)

    # título NUAKY - corrigido: caps 9.5% H (68px em 720) para caber com tracking 0.14 e margem 60px
    # skill diz 15% mas original visual é menor (~11% com tracking largo); reduzimos para evitar corte
    title_cap = int(H * 0.095)
    size = int(title_cap / 0.58)
    max_title_w = W - 2*inset - 60  # margem lateral 30 cada lado + inset
    # loop para garantir que cabe na largura máxima
    for _ in range(5):
        try:
            font_title = ImageFont.truetype(FONT_CINZEL, size)
        except:
            font_title = ImageFont.load_default()
        tracking = int(size * 0.12)
        dummy = Image.new("L", (W, H), 0)
        d_dummy = ImageDraw.Draw(dummy)
        total_w = 0
        for ch in title:
            cb = d_dummy.textbbox((0,0), ch, font=font_title)
            total_w += (cb[2]-cb[0]) + tracking
        total_w -= tracking
        if total_w <= max_title_w or size < 40:
            print(f"[tela] título size={size} tracking={tracking} total_w={total_w} max={max_title_w}")
            break
        size = int(size * 0.85)
        title_cap = int(size * 0.58)
        print(f"[tela] título muito largo, reduzindo para size={size}")
    # imagem título com canal alfa
    title_img = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(title_img)
    # centralizado em (50%, 52.5%)
    cy_title = int(H * 0.525)
    # calcular bbox sem tracking para y
    bbox0 = d.textbbox((0,0), title, font=font_title)
    th0 = bbox0[3]-bbox0[1]
    y_top = cy_title - th0//2 - bbox0[1]
    cur_x = (W - total_w)//2
    for ch in title:
        d.text((cur_x, y_top), ch, font=font_title, fill=255)
        cb = d.textbbox((0,0), ch, font=font_title)
        cw = cb[2]-cb[0]
        cur_x += cw + tracking
    title_arr = np.array(title_img, dtype=np.float32)
    # bloom sigma2 + sigma11 somados ao núcleo
    blur2 = cv2.GaussianBlur(title_arr, (0,0), 2)
    blur11 = cv2.GaussianBlur(title_arr, (0,0), 11)
    # cor: branco/cinza claro 235-245 com bloom
    # criar layer título em BGR branco
    # núcleo branco ~235, bloom adiciona halo
    title_core = title_arr / 255.0
    # combinar: núcleo + bloom
    # normalizar blur para não estourar
    bloom = blur2*0.35/255.0 + blur11*0.18/255.0
    alpha = np.clip(title_core*0.95 + bloom, 0, 1)
    # aplicar no img: onde alpha>0, misturar branco
    for c in range(3):
        img[:, :, c] = np.clip(img[:, :, c].astype(np.float32) * (1 - alpha*0.85) + 235 * alpha, 0, 255).astype(np.uint8)

    # rodapé
    footer_cap = int(15 * (H/720))
    if footer_cap < 10:
        footer_cap = 10
    footer_size = int(footer_cap / 0.60)
    try:
        font_footer = ImageFont.truetype(FONT_CINZEL, footer_size)
    except:
        font_footer = ImageFont.load_default()
    spacing_f = int(footer_size * 0.12)
    footer_dummy = Image.new("L", (W, H), 0)
    fd = ImageDraw.Draw(footer_dummy)
    tw_f = 0
    for ch in footer:
        cb = fd.textbbox((0,0), ch, font=font_footer)
        tw_f += (cb[2]-cb[0]) + spacing_f
    tw_f -= spacing_f
    footer_img = Image.new("L", (W, H), 0)
    d2 = ImageDraw.Draw(footer_img)
    # posição y ~704 em 720 (16px acima borda)
    fy = int(H - 16 - footer_size*0.8)  # ajustar
    # medir bbox para y
    fb0 = d2.textbbox((0,0), footer, font=font_footer)
    fh0 = fb0[3]-fb0[1]
    fy_top = H - 16 - fh0 - fb0[1] - 4  # inset 9 + 7?
    # para H=720, fy_top deve ser ~704? Vamos usar fórmula: content_bottom - margin
    # content_bottom ~720, margin 16
    cur_x = (W - tw_f)//2
    for ch in footer:
        d2.text((cur_x, fy_top), ch, font=font_footer, fill=255)
        cb = d2.textbbox((0,0), ch, font=font_footer)
        cw = cb[2]-cb[0]
        cur_x += cw + spacing_f
    footer_arr = np.array(footer_img, dtype=np.float32)
    blur2_f = cv2.GaussianBlur(footer_arr, (0,0), 2)
    blur11_f = cv2.GaussianBlur(footer_arr, (0,0), 7)
    footer_core = footer_arr/255.0
    bloom_f = blur2_f*0.30/255.0 + blur11_f*0.12/255.0
    alpha_f = np.clip(footer_core*0.9 + bloom_f, 0, 1)
    # cor footer levemente mais escura ~210-220
    for c in range(3):
        img[:, :, c] = np.clip(img[:, :, c].astype(np.float32) * (1 - alpha_f*0.9) + 215 * alpha_f, 0, 255).astype(np.uint8)

    # moldura retângulo arredondado fino inset 9, raio 16, traço 2, cinza ~150
    inset_x = int(inset * (W/720)) if W!=720 else inset
    inset_y = int(inset * (H/720)) if H!=720 else inset
    rad = int(radius * (min(W,H)/720)) if min(W,H)!=720 else radius
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(pil)
    x0, y0 = inset_x, inset_y
    x1, y1 = W - inset_x - 1, H - inset_y - 1
    d.rounded_rectangle([x0, y0, x1, y1], radius=rad, outline=(150,150,150), width=2)
    img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    return img

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--footer-text", default=DEFAULT_FOOTER)
    p.add_argument("--title", default="NUAKY")
    p.add_argument("--lift", type=float, default=58)
    p.add_argument("--crf", type=int, default=22)
    p.add_argument("--remove-old", action="store_true", default=True)
    p.add_argument("--no-remove-old", dest="remove_old", action="store_false")
    p.add_argument("--moldura", action="store_true", default=True)
    p.add_argument("--no-moldura", dest="moldura", action="store_false")
    p.add_argument("--tela-final", action="store_true", default=True)
    p.add_argument("--no-tela-final", dest="tela_final", action="store_false")
    args = p.parse_args()

    cap = cv2.VideoCapture(args.input)
    if not cap.isOpened():
        raise SystemExit(f"não consegui abrir {args.input}")
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"[info] {W}x{H}@{fps:g} {n_frames} frames input={args.input}")

    # detectar fundo conteúdo para posicionamento
    content_bottom = detect_content_bottom(cap, W, H)
    bottom_edge = content_bottom - 8
    print(f"[info] content_bottom={content_bottom} bottom_edge={bottom_edge}")

    # máscara antiga
    mask = None
    if args.remove_old:
        print("[step] estimando máscara da marca antiga...")
        mask = estimate_old_watermark_mask(args.input, W, H)
        if mask is not None:
            cv2.imwrite("/tmp/mask_old.png", mask)
            print(f"[mask] salva /tmp/mask_old.png nonzero {cv2.countNonZero(mask)}")
        else:
            print("[mask] não conseguiu estimar, segue sem remoção")

    # lift footer novo
    print("[step] construindo lift/footer novo...")
    footer_lift = build_footer_lift(W, H, args.footer_text, FONT_CINZEL, lift_peak=args.lift, bottom_edge=bottom_edge)
    # para debug salvar
    cv2.imwrite("/tmp/lift_footer.png", np.clip(footer_lift,0,255).astype(np.uint8))
    # moldura
    moldura_img = None
    if args.moldura:
        print("[step] gerando moldura...")
        moldura_img = build_moldura_mask(W, H, inset=9, radius=16, thickness=2)

    # tela final
    tela_final_img = None
    tela_start = None
    if args.tela_final:
        print("[step] gerando tela final...")
        tela_final_img = generate_tela_final(W, H, title=args.title, footer=args.footer_text)
        cv2.imwrite("/tmp/tela_final_preview.jpg", tela_final_img)
        print("[tela] preview salvo /tmp/tela_final_preview.jpg")
        # detectar onde começa a tela final no input (hard-cut para preto)
        # medir luminância dos últimos 60 frames
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, n_frames-60))
        means = []
        idxs = []
        for i in range(max(0, n_frames-60), n_frames):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, fr = cap.read()
            if ok:
                means.append(fr.mean())
                idxs.append(i)
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        # encontrar transição: queda brusca >80 para <20
        tela_start = n_frames  # default no tela final
        for j in range(1, len(means)):
            if means[j-1] > 80 and means[j] < 25:
                tela_start = idxs[j]
                print(f"[tela] corte detectado em frame {tela_start} (mean {means[j-1]:.1f} -> {means[j]:.1f})")
                break
        if tela_start == n_frames:
            # fallback: últimos 31 frames como observado
            tela_start = max(0, n_frames - 31)
            print(f"[tela] corte não detectado, usando fallback start={tela_start}")

    # preparar ffmpeg pipe
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
        stdin=subprocess.PIPE
    )

    # processar frames
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    n = 0
    # pré-calcular envelope de luminância da tela final original para replicar decaimento
    # vamos medir luminância original nos frames finais para escalar brilho da nova tela
    tela_means = []
    if tela_start is not None and tela_final_img is not None:
        cap_tmp = cv2.VideoCapture(args.input)
        for i in range(tela_start, n_frames):
            cap_tmp.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, fr = cap_tmp.read()
            if ok:
                tela_means.append(fr.mean())
        cap_tmp.release()
        # normalizar: primeiro frame da tela final tem pico, depois decai
        if len(tela_means)>0 and max(tela_means)>0:
            base = tela_means[0]
            # para NUAKY queremos manter brilho estável com leve decaimento
            # replicar envelope relativo: scale = mean_i / mean_0
            envelope = [m/base for m in tela_means]
        else:
            envelope = [1.0]* (n_frames - tela_start)
    else:
        envelope = []

    while True:
        ok, fr = cap.read()
        if not ok:
            break
        # inpaint marca antiga (se houver) - raio 5 para remoção mais limpa neste vídeo
        if mask is not None and cv2.countNonZero(mask)>0:
            fr = cv2.inpaint(fr, mask, 5, cv2.INPAINT_TELEA)
        # adicionar novo footer (additive)
        fr = np.clip(fr.astype(np.float32) + footer_lift[:, :, None], 0, 255).astype(np.uint8)
        # moldura (sobrepor)
        if moldura_img is not None:
            # moldura_img tem borda cinza 150 e fundo preto: onde >0 aplica
            gray_mold = cv2.cvtColor(moldura_img, cv2.COLOR_BGR2GRAY)
            _, mold_mask = cv2.threshold(gray_mold, 10, 255, cv2.THRESH_BINARY)
            # onde moldura existe, substituir pixel por moldura
            fr[mold_mask>0] = moldura_img[mold_mask>0]
        # se estamos na tela final, substituir por tela gerada (com envelope)
        if tela_start is not None and n >= tela_start and tela_final_img is not None:
            idx_tela = n - tela_start
            if idx_tela < len(envelope):
                scale = envelope[idx_tela]
                # o footer some antes do título? skill diz rodapé some antes
                # observar: nos últimos 5 frames, footer ainda visível em NUAKY mas em SANTARONI também?
                # vamos manter simples: se estivermos nos últimos 8 frames, reduzir alfa do footer?
                # para replicar fielmente, medimos que ambos mantêm footer até fim, então manter
                # aplicar escala de brilho geral (simula decaimento)
                tela_scaled = np.clip(tela_final_img.astype(np.float32) * (0.75 + 0.25*scale), 0, 255).astype(np.uint8)
                # mas manter moldura sempre nítida: já está na tela_final_img
                fr = tela_scaled
        proc.stdin.write(fr.tobytes())
        n += 1
        if n % 200 == 0:
            print(f"[progress] {n}/{n_frames} frames", flush=True)
    cap.release()
    proc.stdin.close()
    proc.wait()
    print(f"[done] OK -> {args.output} ({n} frames)")

if __name__ == "__main__":
    main()
