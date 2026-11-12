#!/usr/bin/env python3
"""QC de vídeo vertical para @carlosveiolima (Reels/TikTok/Shorts).

Uso:
  python3 qc_video.py FINAL.mp4 [--ass legendas.ass] [--base sem_texto.mp4] [--out pasta] [--max-dur 45]

--base  = o mesmo vídeo ANTES de queimar textos/cards (mesma duração). É o jeito mais
          preciso de saber onde há texto na tela. Sem ele, usa o .ass renderizado.
Sai com código 1 se houver FALHA. Gera report.json, report.txt e sheet.jpg (frames
problemáticos com rosto em vermelho e texto em amarelo) na pasta --out.
"""
import argparse, json, os, re, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
CV4 = os.path.join(HERE, 'cv4')  # OpenCV 4.x privado (o 5.x tirou o detector Haar)
if os.path.isdir(CV4): sys.path.insert(0, CV4)
import numpy as np, cv2
if not hasattr(cv2, 'CascadeClassifier'):
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', '--target', CV4,
                    'opencv-python-headless==4.10.0.84'], check=True)
    os.execv(sys.executable, [sys.executable] + sys.argv)
CASC = os.path.join(HERE, 'haarcascade_frontalface_default.xml')
if not os.path.exists(CASC): CASC = os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml')
W, H = 1080, 1920
S = 2                      # fator de redução para análise (540x960)
FPS_A = 4                  # quadros analisados por segundo

# ---- limites (canon) ------------------------------------------------------
SAFE = dict(x0=60, x1=1020, y0=150, y1=1560)        # área segura IG/TT/Shorts
RAIL = dict(x0=930, y0=860, y1=1560)                # botões laterais do TikTok/IG
FACE_PAD_TOP, FACE_PAD_BOT, FACE_PAD_X = 0.25, 0.35, 0.12   # zona protegida do rosto
FACE_OVERLAP_FAIL = 0.04   # >4% da zona do rosto coberta por texto = falha
FULLBLEED = 0.55           # >55% da tela coberta = card de tela cheia (B-roll), permitido
LUFS = (-15.0, -13.0); TP_MAX = -1.0
FACE_L = (112, 190)        # luminância média do rosto (L do LAB, 0-255)
CLIP_HI, CLIP_LO = 0.02, 0.04
CONTRAST_MIN = 34          # desvio-padrão de L do quadro
CAP_MIN, CAP_MAX = 0.55, 3.2      # tempo visível de cada bloco de legenda falada
READ_CPS = 15.0            # leitura de títulos/cards: 0,5 s + caracteres/15
TITLE_SLACK = 2.5          # título pode ficar até leitura + 2,5 s (exceto CTA final)
HOOK_MIN, HOOK_MAX = 1.2, 4.0
STATIC_MAX = 4.5           # máximo de segundos sem mudança visual (corte/zoom/card)
COVER_MIN = 0.90           # % da fala com legenda

def sh(a, **k):
    k.setdefault('text', True); return subprocess.run(a, capture_output=True, **k)

def probe(f):
    j = json.loads(sh(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', f]).stdout)
    v = next(s for s in j['streams'] if s['codec_type'] == 'video')
    a = next((s for s in j['streams'] if s['codec_type'] == 'audio'), None)
    n, d = map(int, v['r_frame_rate'].split('/'))
    return dict(w=v['width'], h=v['height'], fps=n / d, vcodec=v['codec_name'], pix=v.get('pix_fmt'),
                acodec=a and a['codec_name'], ar=a and int(a['sample_rate']), dur=float(j['format']['duration']))

def frames(f, fps=FPS_A, vf=None):
    w, h = W // S, H // S
    chain = f'fps={fps},scale={w}:{h}' + (',' + vf if vf else '')
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', f, '-vf', chain, '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'],
                         stdout=subprocess.PIPE)
    out = []
    while True:
        b = p.stdout.read(w * h * 3)
        if len(b) < w * h * 3: break
        out.append(np.frombuffer(b, np.uint8).reshape(h, w, 3))
    p.wait(); return out

def render_ass(ass, dur, styles=None, exclude=None):
    """Renderiza só os eventos do .ass (opcionalmente filtrando estilos) sobre preto."""
    txt = open(ass, encoding='utf-8').read()
    if styles or exclude:
        keep = []
        for ln in txt.splitlines():
            if ln.startswith('Dialogue:'):
                st = ln.split(',', 9)[3]
                if styles and st not in styles: continue
                if exclude and st in exclude: continue
            keep.append(ln)
        txt = '\n'.join(keep) + '\n'
    tf = tempfile.NamedTemporaryFile('w', suffix='.ass', delete=False, encoding='utf-8'); tf.write(txt); tf.close()
    tmp = tf.name.replace('.ass', '.mp4')
    sh(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'color=black:s={W}x{H}:r=30:d={dur:.3f}',
        '-vf', f'ass={tf.name}', '-c:v', 'libx264', '-crf', '12', '-preset', 'ultrafast', tmp], check=True)
    fr = frames(tmp); os.unlink(tmp); os.unlink(tf.name)
    return [(f.max(2) > 14) for f in fr]

def loudness(f):
    e = sh(['ffmpeg', '-v', 'info', '-nostats', '-i', f, '-af', 'ebur128=peak=true', '-f', 'null', '-']).stderr
    I = re.findall(r'I:\s+(-?[\d.]+) LUFS', e); P = re.findall(r'Peak:\s+(-?[\d.]+) dBFS', e)
    return (float(I[-1]) if I else None, float(P[-1]) if P else None)

def speech_mask(f, dur):
    raw = sh(['ffmpeg', '-v', 'error', '-i', f, '-ac', '1', '-ar', '16000', '-f', 'f32le', '-'], text=False).stdout
    a = np.frombuffer(raw, np.float32)
    n = int(dur * FPS_A); hop = 16000 // FPS_A
    db = np.array([20 * np.log10(np.sqrt(np.mean(a[i * hop:(i + 1) * hop] ** 2)) + 1e-6) for i in range(n)])
    return db > max(-38, np.percentile(db, 90) - 22)

# ---- ASS ------------------------------------------------------------------
def ts(x):
    h, m, s = x.split(':'); return int(h) * 3600 + int(m) * 60 + float(s)

def plain(t): return re.sub(r'\{[^}]*\}', '', t).replace('\\N', ' ').strip()

def ass_events(ass):
    ev = []
    for ln in open(ass, encoding='utf-8'):
        if ln.startswith('Dialogue:'):
            p = ln.rstrip('\n').split(',', 9)
            ev.append(dict(st=p[3], a=ts(p[1]), b=ts(p[2]), txt=plain(p[9])))
    return ev

def check_ass(ass, dur, cap_styles, hook_styles, cta_styles):
    issues, ev = [], ass_events(ass)
    caps = sorted([e for e in ev if e['st'] in cap_styles], key=lambda e: e['a'])
    # junta eventos contíguos com o mesmo texto = um bloco visível
    blocks = []
    for e in caps:
        if blocks and blocks[-1]['txt'] == e['txt'] and abs(blocks[-1]['b'] - e['a']) < 0.05:
            blocks[-1]['b'] = e['b']
        else: blocks.append(dict(e))
    short = [b for b in blocks if b['b'] - b['a'] < CAP_MIN]
    long_ = [b for b in blocks if b['b'] - b['a'] > CAP_MAX]
    if blocks and len(short) / len(blocks) > 0.10:
        issues.append(('FALHA', f'{len(short)}/{len(blocks)} blocos de legenda ficam menos de {CAP_MIN}s na tela (ilegível). Ex.: ' +
                       '; '.join(f'"{b["txt"]}" {b["b"]-b["a"]:.2f}s @{b["a"]:.1f}s' for b in short[:4])))
    elif short:
        issues.append(('AVISO', f'{len(short)} blocos curtos (<{CAP_MIN}s): ' + '; '.join(f'"{b["txt"]}" @{b["a"]:.1f}s' for b in short[:4])))
    if long_:
        issues.append(('FALHA', 'Legenda parada tempo demais: ' + '; '.join(f'"{b["txt"]}" {b["b"]-b["a"]:.1f}s @{b["a"]:.1f}s' for b in long_[:4])))
    for b in blocks:
        if len(b['txt']) > 26 or len(b['txt'].split()) > 4:
            issues.append(('AVISO', f'Bloco de legenda longo demais para leitura rápida: "{b["txt"]}"')); break
    for e in ev:
        if e['st'] in cap_styles: continue
        d = e['b'] - e['a']; need = 0.5 + len(e['txt']) / READ_CPS
        if e['st'] in hook_styles:
            if d < max(HOOK_MIN, need * 0.8): issues.append(('FALHA', f'Gancho "{e["txt"]}" fica só {d:.1f}s (mín. {max(HOOK_MIN, need*0.8):.1f}s)'))
            if d > HOOK_MAX: issues.append(('FALHA', f'Gancho "{e["txt"]}" fica {d:.1f}s (máx. {HOOK_MAX}s): tapa o rosto no momento mais importante'))
            continue
        if e['st'] in cta_styles and e['b'] >= dur - 0.2: continue
        if d < need * 0.9: issues.append(('FALHA', f'Texto "{e["txt"][:40]}" fica {d:.1f}s, precisa de {need:.1f}s para ler'))
        elif d > need + TITLE_SLACK: issues.append(('AVISO', f'Texto "{e["txt"][:40]}" fica {d:.1f}s (leitura pede {need:.1f}s): tirar antes'))
    hooks = [e for e in ev if e['st'] in hook_styles]
    if not hooks or min(e['a'] for e in hooks) > 0.25:
        issues.append(('FALHA', 'Sem gancho em texto no primeiro quadro (0,0s). O vídeo precisa abrir com a tese escrita na tela.'))
    return issues, blocks

# ---- principal ------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('video'); ap.add_argument('--ass'); ap.add_argument('--base'); ap.add_argument('--out')
    ap.add_argument('--max-dur', type=float, default=45)
    ap.add_argument('--cap-styles', default='Cap'); ap.add_argument('--hook-styles', default='Hook,HookG')
    ap.add_argument('--cta-styles', default='Q,QG,Sig,CTA')
    A = ap.parse_args()
    out = A.out or os.path.splitext(A.video)[0] + '_qc'; os.makedirs(out, exist_ok=True)
    cap_st, hook_st, cta_st = (set(x.split(',')) for x in (A.cap_styles, A.hook_styles, A.cta_styles))
    R = []  # (nível, mensagem)

    p = probe(A.video)
    if (p['w'], p['h']) != (W, H): R.append(('FALHA', f'Resolução {p["w"]}x{p["h"]}, precisa 1080x1920'))
    if abs(p['fps'] - 30) > 0.5 and abs(p['fps'] - 60) > 0.5: R.append(('AVISO', f'fps {p["fps"]:.2f}'))
    if p['vcodec'] != 'h264' or p['pix'] != 'yuv420p': R.append(('FALHA', f'Codec {p["vcodec"]}/{p["pix"]}, precisa h264/yuv420p'))
    if p['acodec'] != 'aac': R.append(('FALHA', f'Áudio {p["acodec"]}, precisa aac'))
    if p['dur'] > A.max_dur + 0.3: R.append(('FALHA', f'Duração {p["dur"]:.1f}s > {A.max_dur}s'))
    I, TP = loudness(A.video)
    if I is None or not (LUFS[0] <= I <= LUFS[1]): R.append(('FALHA', f'Volume {I} LUFS, alvo -14 (±1)'))
    if TP is not None and TP > TP_MAX: R.append(('FALHA', f'Pico {TP} dBFS > {TP_MAX} (distorce no celular)'))

    fin = frames(A.video); n = len(fin); t = np.arange(n) / FPS_A
    # máscara de texto/overlay
    masks = [np.zeros(fin[0].shape[:2], bool) for _ in range(n)]
    if A.base:
        base = frames(A.base)[:n]
        for i, b in enumerate(base):
            d = (cv2.absdiff(fin[i], b).max(2) > 45).astype(np.uint8)
            d = cv2.morphologyEx(d, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
            k, lab_, st, _ = cv2.connectedComponentsWithStats(d, 8)
            keep = np.zeros(d.shape, bool)
            for c in range(1, k):   # só blocos grandes (cards); boca/mão em movimento são pequenos
                if st[c, cv2.CC_STAT_AREA] >= 2500: keep |= lab_ == c
            masks[i] = keep
    if A.ass:
        am = render_ass(A.ass, p['dur'])[:n]
        for i, m in enumerate(am): masks[i] |= m
        cm = render_ass(A.ass, p['dur'], styles=cap_st)[:n]
        # textos não-legenda (gancho, faixa, pergunta, CTA) não podem encostar uns nos outros
        sts = sorted({e['st'] for e in ass_events(A.ass)} - cap_st)
        per = {st: render_ass(A.ass, p['dur'], styles={st})[:n] for st in sts}
        k_ = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        for i1 in range(len(sts)):
            for i2 in range(i1 + 1, len(sts)):
                hit = [t[i] if False else i / FPS_A for i in range(min(len(per[sts[i1]]), len(per[sts[i2]])))
                       if (cv2.dilate(per[sts[i1]][i].astype(np.uint8), k_) & per[sts[i2]][i].astype(np.uint8)).sum() > 50]
                if hit: R.append(('FALHA', f'"{sts[i1]}" encosta em "{sts[i2]}" (texto quebrou linha ou caixas sobrepostas) em {len(hit)/FPS_A:.1f}s, ex.: {hit[0]:.1f}s'))
        om = render_ass(A.ass, p['dur'], exclude=cap_st)[:n]
    # rosto
    det = cv2.CascadeClassifier(CASC)
    faces = []
    for f in fin:
        g = cv2.equalizeHist(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY))
        fs = det.detectMultiScale(g, 1.1, 6, minSize=(70, 70))
        faces.append(max(fs, key=lambda r: r[2] * r[3]) if len(fs) else None)
    # descarta detecções fora da posição típica do rosto (bolso, garrafa, estampa)
    ok_ = [f for f in faces if f is not None]
    if len(ok_) >= 5:
        my = np.median([f[1] + f[3] / 2 for f in ok_]); mx = np.median([f[0] + f[2] / 2 for f in ok_]); mh = np.median([f[3] for f in ok_])
        faces = [f if f is not None and abs(f[1] + f[3] / 2 - my) < 0.7 * mh and abs(f[0] + f[2] / 2 - mx) < 0.9 * mh and f[3] > 0.6 * mh else None for f in faces]
    # preenche buracos curtos (até 1 s) com o último rosto visto
    last, gap = None, 0
    for i in range(n):
        if faces[i] is not None: last, gap = faces[i], 0
        elif last is not None and gap < FPS_A: faces[i] = last; gap += 1
    zones = []
    for fc in faces:
        if fc is None: zones.append(None); continue
        x, y, w, h = fc
        zones.append((int(x - w * FACE_PAD_X), int(y - h * FACE_PAD_TOP), int(x + w * (1 + FACE_PAD_X)), int(y + h * (1 + FACE_PAD_BOT))))
    face_pct = np.mean([z is not None for z in zones])

    bad = {}  # índice -> motivo
    cover_hits, safe_hits, rail_hits, coll = [], [], [], []
    Lface, contr, hi, lo, cast = [], [], [], [], []
    # quadros de corte (troca brusca na base) dão falso positivo na comparação: pular
    cutf = set()
    if A.base:
        gb = [cv2.cvtColor(cv2.resize(b, (90, 160)), cv2.COLOR_BGR2GRAY).astype(np.int16) for b in base]
        for i in range(1, len(gb)):
            if np.abs(gb[i] - gb[i - 1]).mean() > 12: cutf |= {i - 1, i}
    for i in range(n):
        if i in cutf: continue
        m = masks[i]; cov = m.mean()
        full = cov > FULLBLEED
        z = zones[i]
        if z is not None and not full:
            x0, y0, x1, y1 = max(z[0], 0), max(z[1], 0), min(z[2], W // S), min(z[3], H // S)
            if x1 > x0 and y1 > y0:
                r = m[y0:y1, x0:x1].mean()
                if r > FACE_OVERLAP_FAIL: cover_hits.append((t[i], r)); bad.setdefault(i, f'texto sobre o rosto {r*100:.0f}%')
        if not full and m.any():
            sm = m.copy(); sm[SAFE['y0'] // S:SAFE['y1'] // S, SAFE['x0'] // S:SAFE['x1'] // S] = False
            if sm.sum() > 0.004 * m.size: safe_hits.append(t[i]); bad.setdefault(i, 'texto fora da área segura')
            rm = m[RAIL['y0'] // S:RAIL['y1'] // S, RAIL['x0'] // S:]
            if rm.mean() > 0.02: rail_hits.append(t[i])
        if A.ass and (cm[i] & om[i]).sum() > 400: coll.append(t[i]); bad.setdefault(i, 'legenda batendo em outro texto')
        if not full:
            lab = cv2.cvtColor(fin[i], cv2.COLOR_BGR2LAB); L = lab[..., 0][~m]
            if L.size:
                contr.append(L.std()); hi.append((L >= 250).mean()); lo.append((L <= 6).mean())
            if z is not None:
                x0, y0, x1, y1 = max(faces[i][0], 0), max(faces[i][1], 0), faces[i][0] + faces[i][2], faces[i][1] + faces[i][3]
                fz = lab[y0 + (y1 - y0) // 4:y1 - (y1 - y0) // 6, x0 + (x1 - x0) // 5:x1 - (x1 - x0) // 5]
                if fz.size:
                    Lface.append(fz[..., 0].mean()); cast.append((fz[..., 1].mean() - 128, fz[..., 2].mean() - 128))
    # legenda no rosto / área segura / colisões
    def persist(lst, key=lambda x: x):
        ts_ = sorted(key(x) for x in lst); st = set(round(x * FPS_A) for x in ts_)
        return [x for x in lst if round(key(x) * FPS_A) - 1 in st or round(key(x) * FPS_A) + 1 in st]
    cover_hits = persist(cover_hits, key=lambda x: x[0]); safe_hits = persist(safe_hits); coll = persist(coll)
    if cover_hits:
        dur_bad = len(cover_hits) / FPS_A
        R.append(('FALHA', f'Texto tapando o rosto em {dur_bad:.1f}s do vídeo (ex.: ' +
                  ', '.join(f'{a:.1f}s' for a, _ in cover_hits[:6]) + ')'))
    if safe_hits: R.append(('FALHA', f'Texto fora da área segura (some atrás da interface) em {len(safe_hits)/FPS_A:.1f}s: ' + ', '.join(f'{a:.1f}s' for a in safe_hits[:6])))
    if rail_hits: R.append(('AVISO', f'Texto na coluna dos botões laterais em {len(rail_hits)/FPS_A:.1f}s'))
    if coll: R.append(('FALHA', f'Legenda sobreposta a título/card em {len(coll)/FPS_A:.1f}s: ' + ', '.join(f'{a:.1f}s' for a in coll[:6])))
    if face_pct < 0.5: R.append(('AVISO', f'Rosto detectado em só {face_pct*100:.0f}% do vídeo (checagem de rosto parcial)'))
    # luz/cor
    if Lface:
        lf = np.median(Lface)
        if not (FACE_L[0] <= lf <= FACE_L[1]): R.append(('FALHA', f'Rosto {"escuro" if lf < FACE_L[0] else "estourado"}: luminância {lf:.0f} (alvo {FACE_L[0]}-{FACE_L[1]})'))
        a_, b_ = np.median([c[0] for c in cast]), np.median([c[1] for c in cast])
        if a_ > 26: R.append(('AVISO', f'Pele avermelhada/magenta (a*={a_:.0f})'))
        if b_ > 34: R.append(('AVISO', f'Pele amarelada/laranja demais (b*={b_:.0f})'))
        if b_ < 6: R.append(('AVISO', f'Pele acinzentada/azulada (b*={b_:.0f})'))
    if contr and np.median(contr) < CONTRAST_MIN: R.append(('FALHA', f'Imagem lavada: contraste {np.median(contr):.0f} (mín. {CONTRAST_MIN})'))
    if hi and np.mean(np.array(hi) > CLIP_HI) > 0.2: R.append(('AVISO', 'Altas luzes estouradas em mais de 20% dos quadros'))
    if lo and np.mean(np.array(lo) > CLIP_LO) > 0.2: R.append(('AVISO', 'Sombras esmagadas em mais de 20% dos quadros'))
    # ritmo: maior trecho sem mudança visual
    g = [cv2.cvtColor(cv2.resize(f, (90, 160)), cv2.COLOR_BGR2GRAY).astype(np.int16) for f in fin]
    chg = [0] + [np.abs(g[i] - g[i - 1]).mean() > 6 or (masks[i] ^ masks[i - 1]).mean() > 0.02 for i in range(1, n)]
    run_, best, bt = 0, 0, 0
    for i, c in enumerate(chg):
        run_ = 0 if c else run_ + 1
        if run_ > best: best, bt = run_, t[i]
    if best / FPS_A > STATIC_MAX: R.append(('AVISO', f'{best/FPS_A:.1f}s sem corte/zoom/card (até {bt:.1f}s): risco de queda de retenção'))
    # primeiro quadro
    if (A.ass or A.base) and masks[0].mean() < 0.01: R.append(('FALHA', 'Primeiro quadro sem texto: a tese precisa estar na tela em 0,0s'))
    if not (A.ass or A.base): R.append(('AVISO', 'Sem --ass/--base: rosto x texto e gancho no quadro 0 conferidos só no sheet.jpg (olhe com Read)'))
    if fin[0].mean() < 20: R.append(('FALHA', 'Primeiro quadro preto'))
    # ASS: tempos e cobertura da fala
    blocks = []
    if A.ass:
        iss, blocks = check_ass(A.ass, p['dur'], cap_st, hook_st, cta_st); R += iss
        sp = speech_mask(A.video, p['dur'])[:n]
        capon = np.array([cm[i].any() or (masks[i] & ~cm[i]).mean() > 0.01 for i in range(min(n, len(sp)))])  # card/título substitui a legenda
        if sp.sum():
            c = (capon & sp[:len(capon)]).sum() / sp.sum()
            if c < COVER_MIN: R.append(('FALHA', f'Só {c*100:.0f}% da fala tem legenda (mín. {COVER_MIN*100:.0f}%): 85% assiste sem som'))

    # folha de contato dos quadros problemáticos (ou amostra se tudo ok)
    idx = sorted(bad)[:12] or list(np.linspace(0, n - 1, 8).astype(int))
    tiles = []
    for i in idx:
        im = fin[i].copy(); ov = im.copy(); ov[masks[i]] = (0, 220, 255); im = cv2.addWeighted(ov, 0.45, im, 0.55, 0)
        if zones[i]: cv2.rectangle(im, zones[i][:2], zones[i][2:], (0, 0, 255), 3)
        cv2.rectangle(im, (SAFE['x0'] // S, SAFE['y0'] // S), (SAFE['x1'] // S, SAFE['y1'] // S), (0, 255, 0), 1)
        cv2.putText(im, f'{t[i]:.1f}s {bad.get(i, "")}'[:40], (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        tiles.append(cv2.resize(im, (270, 480)))
    while len(tiles) % 4: tiles.append(np.zeros_like(tiles[0]))
    sheet = np.vstack([np.hstack(tiles[k:k + 4]) for k in range(0, len(tiles), 4)])
    cv2.imwrite(os.path.join(out, 'sheet.jpg'), sheet)

    fails = [r for r in R if r[0] == 'FALHA']
    rep = dict(video=A.video, ok=not fails, dur=round(p['dur'], 2), lufs=I, true_peak=TP,
               face_detected_pct=round(float(face_pct) * 100), face_luma=round(float(np.median(Lface)), 1) if Lface else None,
               contrast=round(float(np.median(contr)), 1) if contr else None,
               caption_blocks=len(blocks), issues=[dict(level=a, msg=b) for a, b in R])
    json.dump(rep, open(os.path.join(out, 'report.json'), 'w'), ensure_ascii=False, indent=1)
    txt = f'{"APROVADO" if not fails else "REPROVADO"}  {os.path.basename(A.video)}  {p["dur"]:.1f}s  {I} LUFS  rosto L={rep["face_luma"]}  contraste={rep["contrast"]}\n' + \
          '\n'.join(f'  [{a}] {b}' for a, b in R)
    open(os.path.join(out, 'report.txt'), 'w').write(txt + '\n'); print(txt)
    sys.exit(1 if fails else 0)

if __name__ == '__main__':
    main()
