"""Análise do rosto e da luz ANTES de queimar textos. Use em toda edição.

    from layout import analyze, caption_chunks
    A = analyze('base.mp4')      # vídeo já cortado/recortado 1080x1920, sem texto
    A['gamma']                   # correção de exposição para o rosto chegar a L~145
    A['face_top'], A['chin']     # faixa do rosto (y em px, já com margem de testa/queixo)
    A['hook_zone']               # 'top' (cabe acima da cabeça) ou 'low' (vai para o terço inferior)
    A['hook_y'], A['cap_y']      # y sugerido do gancho e da legenda (centro do bloco)
"""
import os, sys, subprocess, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
CV4 = os.path.join(HERE, 'cv4')
if os.path.isdir(CV4): sys.path.insert(0, CV4)
import cv2
CASC = os.path.join(HERE, 'haarcascade_frontalface_default.xml')
if not os.path.exists(CASC): CASC = os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml')
W, H, S = 1080, 1920, 2
TARGET_L = 138

def _frames(f, fps=2, vf=None):
    w, h = W // S, H // S
    ch = (vf + ',' if vf else '') + f'fps={fps},scale={w}:{h}'
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', f, '-vf', ch, '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'], stdout=subprocess.PIPE)
    out = []
    while True:
        b = p.stdout.read(w * h * 3)
        if len(b) < w * h * 3: break
        out.append(np.frombuffer(b, np.uint8).reshape(h, w, 3))
    p.wait(); return out

def analyze(video, vf=None, hook_h=300):
    """vf: filtro a aplicar antes (ex.: recorte do vídeo bruto) se o vídeo ainda não for 1080x1920."""
    det = cv2.CascadeClassifier(CASC)
    tops, chins, Ls = [], [], []
    for f in _frames(video, vf=vf):
        g = cv2.equalizeHist(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY))
        fs = det.detectMultiScale(g, 1.1, 6, minSize=(70, 70))
        if not len(fs): continue
        x, y, w, h = max(fs, key=lambda r: r[2] * r[3])
        tops.append((y - 0.25 * h) * S); chins.append((y + 1.35 * h) * S)
        L = cv2.cvtColor(f, cv2.COLOR_BGR2LAB)[y + h // 4:y + h - h // 6, x + w // 5:x + w - w // 5, 0]
        Ls.append(L.mean())
    if not tops:
        return dict(face=False, gamma=1.0, face_top=None, chin=None, hook_zone='top', hook_y=330, cap_y=1330, face_L=None)
    top = float(np.percentile(tops, 10)); chin = float(np.percentile(chins, 90)); L = float(np.median(Ls))
    x, t = L / 255, TARGET_L / 255
    gamma = float(np.clip(np.log(x) / np.log(t), 1.0, 1.35)) if L < TARGET_L - 8 else 1.0
    # gancho: acima da cabeça se couber (topo seguro 160 px), senão no terço inferior
    zone = 'top' if top - 160 - 30 >= hook_h else 'low'
    cap_y = int(np.clip(max(chin + 90, 1260), 1260, 1470))
    hook_y = int(160 + hook_h / 2) if zone == 'top' else int(np.clip(chin + 40 + hook_h / 2, 1150, 1400))
    return dict(face=True, face_L=round(L, 1), gamma=round(gamma, 3), face_top=int(top), chin=int(chin),
                hook_zone=zone, hook_y=hook_y, cap_y=cap_y, face_frames=len(tops))

def caption_chunks(words, min_vis=0.7, max_words=4, max_chars=24, gap_break=0.9):
    """words: lista de (texto, início_s). Agrupa em blocos legíveis: cada bloco fica >= min_vis na
    tela (junta palavras rápidas), quebra em pontuação, pausa longa, 4 palavras ou 24 caracteres."""
    chunks, cur = [], []
    for j, w in enumerate(words):
        cur.append(w)
        nx = words[j + 1] if j + 1 < len(words) else None
        txt = ' '.join(x[0] for x in cur)
        span = (nx[1] if nx else w[1] + 0.6) - cur[0][1]
        punct = w[0][-1] in '.?!'
        if nx is None or punct or (nx[1] - w[1] > gap_break) or len(cur) >= max_words or \
           len(txt + ' ' + nx[0]) > max_chars or (len(cur) >= 2 and span >= min_vis and w[0][-1] == ','):
            chunks.append(cur); cur = []
        elif len(cur) >= 3 and span >= min_vis:
            chunks.append(cur); cur = []
    if cur: chunks.append(cur)
    # junta blocos que ainda ficariam rápidos demais com o seguinte
    out = []
    for c in chunks:
        if out:
            p = out[-1]; vis = c[0][1] - p[0][1]
            if vis < min_vis and len(p) + len(c) <= max_words + 1 and len(' '.join(x[0] for x in p + c)) <= max_chars + 6 \
               and p[-1][0][-1] not in '.?!':
                out[-1] = p + c; continue
        out.append(c)
    return out
