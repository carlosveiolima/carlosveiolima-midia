"""Reposiciona cada legenda falada (estilo Cap) conforme o rosto naquele trecho.
Uso: python3 follow_face.py base.mp4 legendas.ass saida.ass
Regra: logo abaixo do queixo (queixo + margem) se couber até y=1545; senão acima da cabeça; nunca sobre o rosto."""
import sys, os, re, subprocess, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cv2
CASC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'haarcascade_frontalface_default.xml')
base, ass_in, ass_out = sys.argv[1:4]
FPS, S, BOXH = 4, 2, 100           # altura aproximada do bloco de legenda (px)
w, h = 540, 960
p = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', base, '-vf', f'fps={FPS},scale={w}:{h}', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], stdout=subprocess.PIPE)
det = cv2.CascadeClassifier(CASC); faces = []
while True:
    b = p.stdout.read(w * h)
    if len(b) < w * h: break
    g = cv2.equalizeHist(np.frombuffer(b, np.uint8).reshape(h, w))
    fs = det.detectMultiScale(g, 1.1, 6, minSize=(70, 70))
    faces.append(max(fs, key=lambda r: r[2] * r[3]) if len(fs) else None)
ok = [f for f in faces if f is not None]
my = np.median([f[1] + f[3] / 2 for f in ok]); mh = np.median([f[3] for f in ok])
faces = [f if f is not None and abs(f[1] + f[3] / 2 - my) < 0.7 * mh and f[3] > 0.6 * mh else None for f in faces]
chin = [(f[1] + f[3] * 1.24) * S if f is not None else None for f in faces]
top = [(f[1] - f[3] * 0.25) * S if f is not None else None for f in faces]
def ts(x):
    hh, mm, ss = x.split(':'); return int(hh) * 3600 + int(mm) * 60 + float(ss)
def win(a, b, arr, fn):
    v = [arr[i] for i in range(int(a * FPS), min(len(arr), int(b * FPS) + 2)) if i < len(arr) and arr[i] is not None]
    return fn(v) if v else None
lines = open(ass_in, encoding='utf-8').readlines()
plain = lambda t: re.sub(r'\{[^}]*\}', '', t).strip()
# agrupa eventos consecutivos do mesmo bloco (karaokê) para a legenda não pular dentro da frase
groups, cur = [], None
for i, ln in enumerate(lines):
    if ln.startswith('Dialogue:') and ln.split(',', 9)[3] == 'Cap':
        pp = ln.split(',', 9); a, b, tx = ts(pp[1]), ts(pp[2]), plain(pp[9])
        if cur and cur['tx'] == tx and abs(a - cur['b']) < 0.06: cur['b'] = b; cur['idx'].append(i)
        else: cur = {'tx': tx, 'a': a, 'b': b, 'idx': [i]}; groups.append(cur)
stats = {'baixo': 0, 'cima': 0}
for g in groups:
    c = win(g['a'] - 0.25, g['b'] + 0.25, chin, max); t = win(g['a'] - 0.25, g['b'] + 0.25, top, min)
    g['low'] = int(max(1300, (c or 1300) + 30 + BOXH)) if (c is None or c + 30 + BOXH <= 1545) else None
    g['high'] = int(t - 30) if (t is not None and t - 30 - BOXH >= 170) else None
# fica do mesmo lado da frase anterior enquanto couber; troca só quando aquele lado não cabe
side = 'low' if groups and groups[0]['low'] is not None else 'high'; switches = 0
for g in groups:
    if g[side] is None:
        o = 'high' if side == 'low' else 'low'
        if g[o] is not None: side = o; switches += 1
    yb = g[side] if g[side] is not None else 1545
    stats['baixo' if side == 'low' else 'cima'] += 1
    stats['trocas'] = switches
    for i in g['idx']:
        pp = lines[i].split(',', 9); pp[9] = re.sub(r'\\pos\(540,\d+\)', lambda m: f'\\pos(540,{yb})', pp[9]); lines[i] = ','.join(pp)
open(ass_out, 'w', encoding='utf-8').writelines(lines); print(stats, len(groups), 'blocos')
