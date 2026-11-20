"""Builder de Reel falado (talking head) a partir de 1 ou mais vídeos brutos já transcritos (transcribe.py).
Uso: python3 talk_builder.py config.json
config: {
 "out": pasta, "src": {"X": "video.mp4", ...}, "words": {"X": "w.json", ...},
 "segs": [["X", i0, i1], ...]                       # faixas de palavras (inclusive), na ordem do Reel
 "fix": {"X:i": "texto"}                             # grafia na legenda
 "keys": ["heineken", ...]                           # palavras com destaque (escala 130)
 "curve": "0/0 0.25/0.36 0.5/0.66 0.8/0.9 1/1", "gamma": 1.03,
 "hook": ["LINHA1\\NLINHA2", "LINHA GOLD"],  "hook_end": 3.2,
 "cards": [["X:i", dur, "TITULO", "GOLD ou vazio"], ...]   # começa na palavra i do vídeo X
 "q": ["PERGUNTA\\NFINAL", "COMENTA X"], "tail": 2.8
}
Cortes: cada trecho começa/termina no vale de energia entre a palavra vizinha e a palavra do trecho.
Legendas: karaokê (layout.caption_chunks) e follow_face.py; somem enquanto gancho/card/pergunta baixos estão na tela.
Cards e gancho vão na zona baixa (abaixo do queixo) quando não cabem acima da cabeça.
"""
import json, os, subprocess, sys, numpy as np, soundfile as sf
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import layout
C = json.load(open(sys.argv[1])); O = C['out']; os.makedirs(O, exist_ok=True)
def run(a): subprocess.run(['ffmpeg', '-threads', '2', '-v', 'error', '-y'] + a, check=True)
W = {k: json.load(open(v)) for k, v in C['words'].items()}
AUD = {}
for k, v in C['src'].items():
    wav = f'{O}/{k}.wav'
    if not os.path.exists(wav): run(['-i', v, '-ac', '1', '-ar', '16000', wav])
    AUD[k] = sf.read(wav)[0]
def env(k, a, b):
    x = AUD[k]; i0, i1 = int(a * 16000), int(b * 16000)
    if i1 - i0 < 400: return (a + b) / 2
    seg = x[i0:i1] ** 2; win = 320
    e = np.convolve(seg, np.ones(win) / win, 'same')
    return a + (int(np.argmin(e)) / 16000)
segs = []
for sg in C['segs']:
    k, i0, i1 = sg[:3]; w = W[k]
    prev_end = w[i0 - 1][2] if i0 > 0 else max(0, w[i0][1] - 0.3)
    nxt = w[i1 + 1][1] if i1 + 1 < len(w) else w[i1][2] + 0.4
    s = env(k, max(prev_end, w[i0][1] - 0.45), w[i0][1] - 0.02) if w[i0][1] - prev_end > 0.06 else (prev_end + w[i0][1]) / 2
    e = env(k, w[i1][2] + 0.02, min(nxt, w[i1][2] + 0.45)) if nxt - w[i1][2] > 0.06 else (w[i1][2] + nxt) / 2
    e = min(e, w[i1][2] + 0.35)
    if len(sg) > 3 and sg[3] is not None: s = sg[3]
    if len(sg) > 4 and sg[4] is not None: e = sg[4]
    segs.append((k, i0, i1, max(0, s), e))
curve, gam = C.get('curve', '0/0 0.2/0.27 0.5/0.6 0.85/0.9 1/1'), C.get('gamma', 1.0)
VF = f"scale=1080:1920,hqdn3d=2:1.5:4:3,curves=all='{curve}',eq=gamma={gam}:contrast=1.05:saturation=1.06,colorbalance=rs=0.0:bs=0.0,unsharp=5:5:0.6"
parts, words_out, t, AT, BL = [], [], 0.0, {}, []
for n, (k, i0, i1, s, e) in enumerate(segs):
    d = e - s; z = 1.14 if n in C.get('punch', []) else (1.0 if n % 2 == 0 else 1.07)
    zf = f',scale={int(1080*z)//2*2}:{int(1920*z)//2*2},crop=1080:1920' if z > 1 else ''
    last = n == len(segs) - 1
    tp = f",tpad=stop_mode=clone:stop_duration={C.get('tail', 2.8)}" if last else ''
    ap = f",apad=pad_dur={C.get('tail', 2.8)}" if last else ''
    f = f'{O}/s{n:02d}.mp4'; parts.append(f)
    if not os.path.exists(f.replace('.mp4', '.mkv')): run(['-ss', f'{s:.3f}', '-t', f'{d:.3f}', '-i', C['src'][k], '-vf', f'fps=30,{VF}{zf}{tp}',
         '-af', f'aresample=48000,highpass=f=80,afftdn=nr=8:nf=-40,afade=t=in:d=0.015,afade=t=out:st={d-0.02:.3f}:d=0.02{ap}',
         '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '17', '-c:a', 'pcm_s16le', f.replace('.mp4', '.mkv')])
    for i in range(i0, i1 + 1):
        tx = C.get('fix', {}).get(f'{k}:{i}', W[k][i][0])
        AT[f'{k}:{i}'] = t + W[k][i][1] - s
        if f'{k}:{i}' in C.get('bleep', []): BL.append((t + W[k][i][1] - s - 0.03, t + W[k][i][2] - s + 0.03)); tx = '...'
        if tx: words_out.append((tx, t + W[k][i][1] - s, t + W[k][i][2] - s))
    t += d
parts = [p.replace('.mp4', '.mkv') for p in parts]
open(f'{O}/list.txt', 'w').write(''.join(f"file '{p}'\n" for p in parts))
run(['-f', 'concat', '-safe', '0', '-i', f'{O}/list.txt', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', f'{O}/base.mp4'])
TOT = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f'{O}/base.mp4']))
json.dump(words_out, open(f'{O}/words_out.json', 'w'), ensure_ascii=False)
L = layout.analyze(f'{O}/base.mp4'); print('layout', L)
top_ok = L['face_top'] is None or L['face_top'] - 160 >= 250
fmt = lambda x: f"0:{int(x//60):02d}:{x%60:05.2f}"
# zonas: (y1, y2 de cada caixa) baixa = logo abaixo do queixo (QC usa 1.24h; layout chin usa 1.35h)
low_y = int(min(max(L['chin'] or 1300, 1290), 1330)) if not top_ok else None
ev, blocks = [], []   # blocks: intervalos em que a legenda some
SFX = []   # instantes de whoosh
def card(a, b, t1, t2, style1='Hook', style2='QG', fs1=66, fs2=52, sfx=True):
    n1 = t1.count('\\N') + 1; h1 = int(fs1 * 1.22 * n1) + 48
    y1 = 165 if top_ok else low_y
    y2 = (165 + int(fs1 * 1.25 * n1) + 60) if top_ok else low_y + h1 + 10
    if not top_ok and t2 and y2 + int(fs2 * 1.22) + 36 > 1552:
        y2 = 165   # não cabe embaixo: linha dourada vai acima da cabeça
    pop = '\\t(0,140,\\fscx108\\fscy108)\\t(140,260,\\fscx100\\fscy100)'
    ev.append(f"Dialogue: 3,{fmt(a)},{fmt(b)},{style1},,0,0,0,,{{\\an8\\move(640,{y1},540,{y1},0,220)\\fs{fs1}\\fad(120,140){pop}}}{t1}")
    if t2: ev.append(f"Dialogue: 3,{fmt(a+0.22)},{fmt(b)},{style2},,0,0,0,,{{\\an8\\move(440,{y2},540,{y2},0,220)\\fs{fs2}\\fad(120,140)}}{t2}")
    if not top_ok: blocks.append((a - 0.05, b + 0.05))
    if sfx: SFX.append(a)
h1, h2 = C['hook']
ev.append(f"Dialogue: 3,{fmt(0)},{fmt(C['hook_end'])},Lb,,0,0,0,,{{\\an8\\pos(540,165)\\fad(0,120)}}{C.get('tag')}") if C.get('tag') else None
card(0, C['hook_end'], h1, h2, fs1=C.get('hook_fs', 62), fs2=50, sfx=False)
for cd in C['cards']:
    anc, dur, t1, t2 = cd[:4]; st = cd[4] if len(cd) > 4 else 'Hook'
    a = AT[anc]; card(a, a + dur, t1, t2, style1=st, fs1=C.get('card_fs', 62), fs2=48)
q_start = TOT - C.get('tail', 2.8) - C.get('q_lead', 1.2)
card(q_start, TOT, C['q'][0], C['q'][1], style1='Q', fs1=62, fs2=50)
blocks.append((q_start - 0.05, TOT))
blocked = lambda a, b: any(a < y and b > x for x, y in blocks)
KEYS = set(C.get('keys', [])); GOLD = '&H70BAE2&'
ch = layout.caption_chunks([(w[0], w[1]) for w in words_out])
for ci, c in enumerate(ch):
    cend = ch[ci + 1][0][1] if ci + 1 < len(ch) else c[-1][1] + 0.8
    cend = min(cend, c[-1][1] + 1.2)
    cs, ce = c[0][1], cend; skip = False
    for x, y in blocks:
        if cs < y and ce > x:
            if x <= cs: cs = max(cs, y)
            elif y >= ce: ce = min(ce, x)
            else: skip = True
    if skip or ce - cs < 0.6: continue
    for j, w in enumerate(c):
        s = max(w[1], cs); e = min(c[j + 1][1] if j + 1 < len(c) else cend, ce)
        if j == 0: s = cs
        if e - s < 0.05: continue
        parts_ = []
        for jj, x in enumerate(c):
            tx = x[0].upper().rstrip(',')
            if jj == j:
                sc = 130 if x[0].strip('.,?!').lower() in KEYS else 116
                parts_.append(f"{{\\c{GOLD}\\t(0,90,\\fscx{sc+8}\\fscy{sc+8})\\t(90,170,\\fscx{sc}\\fscy{sc})}}{tx}{{\\c&HFFFFFF&\\fscx100\\fscy100}}")
            else: parts_.append(tx)
        ev.append(f"Dialogue: 1,{fmt(s)},{fmt(e)},Cap,,0,0,0,,{{\\an5\\pos(540,{L['cap_y']})}}{' '.join(parts_)}")
HEAD = open(f'{HERE}/head.ass').read()
BAD = 'Style: Bad,Inter ExtraBold,94,&H00FFFFFF,&H00FFFFFF,&H002A2AB8,&H002A2AB8,0,0,0,0,100,100,0,0,3,24,0,8,70,70,170,1'
GOOD = 'Style: Good,Inter ExtraBold,94,&H00FFFFFF,&H00FFFFFF,&H00347A1E,&H00347A1E,0,0,0,0,100,100,0,0,3,24,0,8,70,70,170,1'
HEAD = HEAD.replace('\n[Events]', BAD + '\n' + GOOD + '\n\n[Events]', 1) if '\n\n[Events]' not in HEAD else HEAD.replace('\n\n[Events]', '\n' + BAD + '\n' + GOOD + '\n\n[Events]', 1)
open(f'{O}/raw.ass', 'w').write(HEAD + '\n'.join(ev) + '\n')
subprocess.run([sys.executable, f'{HERE}/follow_face.py', f'{O}/base.mp4', f'{O}/raw.ass', f'{O}/legendas.ass'], check=True)
wh = f'{O}/whoosh.wav'
run(['-f', 'lavfi', '-i', 'anoisesrc=d=0.42:c=pink:a=0.5', '-af', 'highpass=f=700,lowpass=f=6000,afade=t=in:d=0.18,afade=t=out:st=0.2:d=0.22,volume=0.22,aresample=48000', '-ac', '2', wh])
inputs = ['-i', f'{O}/base.mp4']; fc = []
mute = '+'.join(f'between(t,{a:.3f},{b:.3f})' for a, b in BL)
fc.append(f"[0:a]aresample=48000{',volume=0:enable=' + chr(39) + mute + chr(39) if BL else ''}[v0]")
mix = ['[v0]']
for j, (a, b) in enumerate(BL):
    inputs += ['-f', 'lavfi', '-t', f'{b-a:.3f}', '-i', 'sine=f=1000:sample_rate=48000']
    fc.append(f"[{j+1}:a]volume=0.18,adelay={int(a*1000)}|{int(a*1000)},aformat=channel_layouts=stereo[b{j}]"); mix.append(f'[b{j}]')
nb = len(BL)
for j, a in enumerate(SFX):
    inputs += ['-i', wh]
    fc.append(f"[{nb+1+j}:a]adelay={int(max(0,a-0.12)*1000)}|{int(max(0,a-0.12)*1000)}[w{j}]"); mix.append(f'[w{j}]')
fc.append(f"[0:v]ass={O}/legendas.ass[v]")
fc.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0,loudnorm=I=-14:TP=-2:LRA=9,alimiter=limit=0.84:level=false[a]")
run(inputs + ['-filter_complex', ';'.join(fc), '-map', '[v]', '-map', '[a]',
     '-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-maxrate', '6M', '-bufsize', '12M', '-pix_fmt', 'yuv420p', '-r', '30', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
     '-movflags', '+faststart', f'{O}/final.mp4'])
print('TOT', round(TOT, 2), 'segs', len(segs), 'top_ok', top_ok, 'low_y', low_y)
