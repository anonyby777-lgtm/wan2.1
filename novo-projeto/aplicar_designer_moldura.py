#!/usr/bin/env python3
# Aplica designer NUAKY com moldura (poster) ao vídeo 4AEE
# - Remove @JAPAEDITS__LG via inpaint
# - Adiciona moldura branca com gap inferior + logo NUAKY gótico do poster
import cv2, numpy as np, subprocess, os
from PIL import Image
import imageio_ffmpeg

VIDEO_INPUT = "novo-projeto/4AEE9DC0-B490-4915-BBE9-CAAD88BDEC1C.mp4"
LOGO_PATH = "/tmp/logo_final.png"  # RGBA clean sem borda
OUTPUT = "novo-projeto/video_NUAKY_moldura_final.mp4"

# criar venv já deve ter sido feito

def estimate_mask(video_path, W, H, n_samples=100):
    cap = cv2.VideoCapture(video_path)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    idxs = np.linspace(0, n-1, min(n_samples, n)).astype(int)
    frames=[]
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, fr = cap.read()
        if ok:
            frames.append(fr)
    cap.release()
    stack = np.stack(frames, axis=0)
    median = np.median(stack, axis=0).astype(np.uint8)
    gray = cv2.cvtColor(median, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (0,0), 3)
    hp = cv2.absdiff(gray, blur)
    _, thr = cv2.threshold(hp, 5, 255, cv2.THRESH_BINARY)
    # focar rodapé: 85% a 100% H
    roi_y0 = int(H*0.86)
    mask = np.zeros_like(gray)
    mask[roi_y0:H, :] = thr[roi_y0:H, :]
    # limpar
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3,3),np.uint8))
    mask = cv2.dilate(mask, np.ones((5,5),np.uint8), iterations=1)
    # filtrar componentes centrais
    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    filtered = np.zeros_like(mask)
    for i in range(1, num):
        area = stats[i, cv2.CC_STAT_AREA]
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]
        x = stats[i, cv2.CC_STAT_LEFT]
        # marca @JAPAEDITS__LG: largura ~250-350, altura ~15-25, centralizada
        cx = x + w//2
        if 200 < area < 12000 and w > 120 and h < 50 and abs(cx - W//2) < W*0.25:
            filtered[labels==i]=255
    if cv2.countNonZero(filtered) < 100:
        # fallback: bbox central estimado para @JAPAEDITS__LG - aumentado para garantir remoção total
        est_w = int(W*0.32)  # ~410 at 1280, maior para cobrir texto todo
        est_h = 30  # maior altura
        x0 = (W - est_w)//2
        y0 = H - est_h - 12
        filtered = np.zeros_like(mask)
        # criar máscara retangular sólida maior com dilatação extra para garantir inpaint limpo
        filtered[y0-6:y0+est_h+6, x0-12:x0+est_w+12] = 255
        filtered = cv2.dilate(filtered, np.ones((7,7),np.uint8), iterations=1)
        print(f"[mask] fallback bbox x0={x0} y0={y0} w={est_w} h={est_h} (expandido)")
    else:
        print(f"[mask] filtrado {cv2.countNonZero(filtered)} px")
    cv2.imwrite("/tmp/mask_japa.png", filtered)
    print(f"[mask] salvo /tmp/mask_japa.png")
    return filtered

def prepare_logo(logo_path, video_w, scale_factor=0.38):
    # logo original 900x164
    logo = Image.open(logo_path).convert("RGBA")
    orig_w, orig_h = logo.size
    target_w = int(video_w * scale_factor)  # 38% da largura
    # limitar entre 300 e 600
    target_w = max(300, min(600, target_w))
    target_h = int(orig_h * target_w / orig_w)
    logo_scaled = logo.resize((target_w, target_h), Image.LANCZOS)
    print(f"[logo] original {orig_w}x{orig_h} -> scaled {target_w}x{target_h} ({scale_factor*100:.0f}% W)")
    return logo_scaled

def create_moldura(W, H, gap_width, inset=14, radius=18, thickness=2, color=(255,255,255)):
    # cria imagem moldura RGB com gap central inferior
    pil = Image.new("RGB", (W, H), (0,0,0))
    x0, y0 = inset, inset
    x1, y1 = W - inset -1, H - inset -1
    from PIL import ImageDraw as ID
    d = ID.Draw(pil)
    d.rounded_rectangle([x0, y0, x1, y1], radius=radius, outline=color, width=thickness)
    mold = np.array(pil)
    # agora apagar gap no centro inferior: criar máscara preta sobre o gap
    # gap: centro horizontal, na borda inferior
    gap_x0 = (W - gap_width)//2
    gap_x1 = (W + gap_width)//2
    # apagar segmento inferior da moldura no gap: y = y1 - thickness .. y1
    # também estender 10px acima para deixar respiro
    gap_y0 = y1 - thickness - 8
    gap_y1 = y1 + 2
    # fazer buraco: pintar de preto (0,0,0) sobre a moldura nessa região
    cv2_mold = cv2.cvtColor(mold, cv2.COLOR_RGB2BGR)
    # encontrar onde moldura tem cor branca nessa região e apagar
    # simplificar: desenhar retângulo preto sobre gap
    cv2.rectangle(cv2_mold, (gap_x0-12, gap_y0), (gap_x1+12, gap_y1+6), (0,0,0), -1)
    # também apagar cantos arredondados inferiores próximos ao gap? já apagado
    # recriar cantos: não precisa
    return cv2_mold

def main():
    from PIL import ImageDraw
    inp = VIDEO_INPUT
    logo_path = LOGO_PATH
    out = OUTPUT
    cap = cv2.VideoCapture(inp)
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"[info] {W}x{H}@{fps} {n_frames} frames")
    # mask
    mask = estimate_mask(inp, W, H)
    # logo
    logo = prepare_logo(logo_path, W, scale_factor=0.38)
    lw, lh = logo.size
    # gap width = lw + 40
    gap_w = lw + 60
    # moldura
    mold = create_moldura(W, H, gap_w, inset=int(12* (W/1280)), radius=int(18* (min(W,H)/720)), thickness=2, color=(255,255,255))
    gray_mold = cv2.cvtColor(mold, cv2.COLOR_BGR2GRAY)
    _, mold_mask = cv2.threshold(gray_mold, 10, 255, cv2.THRESH_BINARY)
    # posição logo: centro horizontal, y = H - inset - lh - 8 (8px acima da borda inferior, dentro do gap)
    inset = int(12* (W/1280))
    logo_x = (W - lw)//2
    logo_y = H - inset - lh - 12  # 12px acima da borda
    # se gap, logo_y deve ficar alinhado com gap (ligeiramente acima da linha da moldura)
    print(f"[pos] logo x={logo_x} y={logo_y} lw={lw} lh={lh} gap={gap_w} inset={inset}")
    # converter logo para BGRA para overlay
    logo_arr = np.array(logo)  # RGBA
    logo_bgr = cv2.cvtColor(logo_arr, cv2.COLOR_RGBA2BGRA)  # keep alpha
    # preparar ffmpeg pipe
    FF = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.Popen(
        [FF, "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-i", inp, "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-profile:v", "high", "-pix_fmt", "yuv420p", "-vsync", "cfr", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv", "-c:a", "copy", "-movflags", "+faststart", out],
        stdin=subprocess.PIPE
    )
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    n=0
    # pre converter mold mask para overlay rápido
    mold_alpha = (mold_mask>0)
    # para cada frame
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        # inpaint marca antiga - raio 5 para remoção mais limpa
        if cv2.countNonZero(mask)>0:
            fr = cv2.inpaint(fr, mask, 5, cv2.INPAINT_TELEA)
        # moldura
        fr[mold_alpha] = mold[mold_alpha]
        # logo overlay alpha
        # roi
        y1 = logo_y
        y2 = logo_y + lh
        x1 = logo_x
        x2 = logo_x + lw
        # garantir dentro
        y1c = max(0, y1); y2c = min(H, y2); x1c = max(0, x1); x2c = min(W, x2)
        if y2c > y1c and x2c > x1c:
            # crop logo correspondente
            ly1 = y1c - y1
            ly2 = ly1 + (y2c - y1c)
            lx1 = x1c - x1
            lx2 = lx1 + (x2c - x1c)
            logo_crop = logo_arr[ly1:ly2, lx1:lx2]  # RGBA
            alpha = logo_crop[:,:,3].astype(float)/255.0
            # need to handle glow: onde alpha >0, fazer blend
            for c in range(3):
                # logo_crop RGB, fr BGR
                # logo R-> fr 2, G->1, B->0
                # mapear: logo RGB 0:R,1:G,2:B ; fr BGR 0:B,1:G,2:R
                # então c=0(B) usa logo B (2), c=1(G) usa 1, c=2(R) usa 0
                lc = logo_crop[:,:, 2-c].astype(float)  # because logo is RGB
                fr[y1c:y2c, x1c:x2c, c] = np.clip(fr[y1c:y2c, x1c:x2c, c].astype(float)*(1-alpha) + lc*alpha, 0,255).astype(np.uint8)
        proc.stdin.write(fr.tobytes())
        n+=1
        if n%200==0:
            print(f"[progress] {n}/{n_frames}")
    cap.release()
    proc.stdin.close()
    proc.wait()
    print(f"[done] {out} {n} frames")

if __name__=="__main__":
    main()
