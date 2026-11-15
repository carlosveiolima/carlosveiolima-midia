"""capa.py VIDEO_BASE T SAIDA.jpg Y_INICIO 'LINHA1|*LINHA2' 'TAG'
Linhas com * vão em caixa dourada; as outras em verde-escura. Texto começa em Y_INICIO+10 (mín. 260)
e precisa terminar antes de y=1680 (zona da grade 3:4). Escolha Y_INICIO acima da cabeça ou abaixo do queixo."""
import sys, subprocess, tempfile
v, t, out, chin, lines, tag = sys.argv[1], float(sys.argv[2]), sys.argv[3], int(sys.argv[4]), sys.argv[5].split('|'), sys.argv[6]
LH, FS = 128, 96
tot = len(lines) * LH + 80
y0 = max(chin + 10, 260)
if y0 + tot > 1660:
    sc = (1660 - y0) / tot; LH = int(LH * sc); FS = int(FS * sc)
head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: G,Inter ExtraBold,{FS},&H00E4F0F5,&H00FFFFFF,&H001A2514,&H001A2514,0,0,0,0,100,100,0,0,3,20,0,8,60,60,0,1
Style: O,Inter ExtraBold,{FS},&H001A2514,&H00FFFFFF,&H0070BAE2,&H0070BAE2,0,0,0,0,100,100,0,0,3,20,0,8,60,60,0,1
Style: T,Inter ExtraBold,{int(FS*0.45)},&H0070BAE2,&H00FFFFFF,&H001A2514,&H001A2514,0,0,0,0,100,100,1,0,3,12,0,8,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
ev = []; y = y0
for ln in lines:
    st = 'O' if ln.startswith('*') else 'G'
    ev.append(f"Dialogue: 1,0:00:00.00,0:00:05.00,{st},,0,0,0,,{{\\pos(540,{y})}}{ln.lstrip('*')}"); y += LH
ev.append(f"Dialogue: 1,0:00:00.00,0:00:05.00,T,,0,0,0,,{{\\pos(540,{y+10})}}{tag}")
f = tempfile.NamedTemporaryFile('w', suffix='.ass', delete=False); f.write(head + '\n'.join(ev) + '\n'); f.close()
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(t), '-i', v, '-frames:v', '1', '-vf', f'ass={f.name}', '-q:v', '2', out], check=True)
print(out, 'y0', y0, 'fim', y + 10 + int(FS * 0.45) + 24)
