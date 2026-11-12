import json,subprocess,os,sys,numpy as np
sys.path.insert(0,'/tmp/claude-0/-home-claude/8b78c0ee-8be5-5b5a-b18f-32b954b96fad/scratchpad/vqc')
import layout
W=os.path.dirname(os.path.abspath(__file__))
SRC={"34":"/mnt/user-data/uploads/139234.mp4","36":"/mnt/user-data/uploads/139236.mp4"}
WL={k:json.load(open(f"{W}/w{k}.json")) for k in SRC}
DB={}
for k in SRC:
    au=np.fromfile(f"{W}/a{k}.f32",dtype=np.float32)
    r=np.sqrt(np.convolve(au**2,np.ones(320)/320,'same'))[::80]; DB[k]=20*np.log10(r+1e-6)
def quiet(k,t0,t1):
    i0,i1=int(t0*200),int(t1*200)+1; return (i0+int(np.argmin(DB[k][i0:i1])))/200
def nxt(k,i): return WL[k][i+1][1] if i+1<len(WL[k]) else WL[k][i][2]+0.6
def prv(k,i): return WL[k][i-1][2] if i>0 else max(0,WL[k][i][1]-0.4)
def cut_start(k,i):
    lo,hi=prv(k,i)+0.02,WL[k][i][1]-0.06
    if hi-lo<0.03: return (prv(k,i)+WL[k][i][1])/2
    return quiet(k,max(lo,WL[k][i][1]-0.22),hi)
def wend(k,i): return min(WL[k][i][2],WL[k][i][1]+0.9)
def cut_end(k,i):
    n=nxt(k,i); return max(wend(k,i)+0.02,min(n-0.10,wend(k,i)+0.5))
def sp_end(k,t,lim,th=-30):
    d=DB[k];x=int(t*200);L=int(lim*200)
    while x<L-8 and not all(d[x:x+8]<th): x+=1
    return x/200
VF="hqdn3d=2:1.5:4:3,curves=all='0/0 0.2/0.27 0.5/0.6 0.85/0.9 1/1',eq=gamma=1.06:contrast=1.05:saturation=1.08,colorbalance=rs=-0.04:bs=0.05:rm=-0.04:bm=0.04,unsharp=5:5:0.7"
def run(a): subprocess.run(["ffmpeg","-threads","3","-v","error","-y"]+a,check=True)
GOLD="&H70BAE2&"
def build(name,segs,fixes,keys,hook,q,chips,cards,cover_ms=None,gamma=1.0,tail=2.8):
    VFX=VF+(f',eq=gamma={gamma:.3f}' if gamma>1.001 else '')
    # silence floor per source for internal trims
    pieces=[];t=0;words=[];z=0
    for si,(k,i0,i1) in enumerate(segs):
        subs=[];cur=cut_start(k,i0)
        for i in range(i0,i1):
            gap=WL[k][i+1][1]-wend(k,i)
            if gap>0.7:
                e_=min(wend(k,i)+0.30,WL[k][i+1][1]-0.25); s_=WL[k][i+1][1]-0.12
                if s_-e_>0.25: subs.append((cur,e_,i)); cur=s_
        subs.append((cur,cut_end(k,i1),i1))
        for a,b,_ in subs:
            zoom=[1.0,1.07][z%2];z+=1;d=b-a
            f=f"{W}/p_{k}_{a:.3f}_{b:.3f}_{zoom}_g{gamma:.2f}.mp4"
            if not os.path.exists(f):
                run(["-ss",f"{a:.3f}","-i",SRC[k],"-t",f"{d:.3f}","-vf",f"scale={int(1080*zoom)//2*2}:{int(1920*zoom)//2*2},crop=1080:1920,fps=30,{VFX}",
                     "-af",f"highpass=f=80,afftdn=nr=8:nf=-40,afade=t=in:d=0.015,afade=t=out:st={d-0.02:.3f}:d=0.02","-c:v","libx264","-preset","veryfast","-crf","17","-c:a","aac","-b:a","192k","-ar","48000",f])
            dur=float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",f]))
            for i in range(i0,i1+1):
                if a<=WL[k][i][1]<b: words.append([fixes.get((k,i),fixes.get(WL[k][i][0],WL[k][i][0])),t+WL[k][i][1]-a,si,(k,i)])
            pieces.append((f,t,dur,si));t+=dur
    TOT=t
    words=[w for w in words if w[0]]
    open(f"{W}/{name}.txt","w").write("".join(f"file '{p[0]}'\n" for p in pieces))
    run(["-f","concat","-safe","0","-i",f"{W}/{name}.txt","-c","copy",f"{W}/{name}_raw.mp4"])
    # quadro final congelado (end card): pergunta/CTA entram depois da última palavra, sem tapar legenda
    run(["-i",f"{W}/{name}_raw.mp4","-vf",f"tpad=stop_mode=clone:stop_duration={tail}","-af",f"apad=pad_dur={tail}","-c:v","libx264","-preset","veryfast","-crf","17","-c:a","aac","-b:a","192k","-ar","48000",f"{W}/{name}_base.mp4"])
    SPEECH_END=TOT; TOT=TOT+tail
    LA=layout.analyze(f"{W}/{name}_base.mp4"); print("layout",LA)
    def wt(key): return next(w[1] for w in words if w[3]==key)
    def T(x):
        if isinstance(x,(int,float)): return x if x>=0 else TOT+x
        return wt(x)
    fmt=lambda x:f"0:{int(x//60):02d}:{x%60:05.2f}"
    hook_end=min(T(hook[2]),3.5)
    cw=[w for w in words if w[1]>=hook_end-0.05]
    chunks=layout.caption_chunks([(w[0],w[1]) for w in cw])
    m={id(w):w for w in cw}; it=iter(cw); chunks=[[next(it) for _ in c] for c in chunks]
    ev=[]
    for ci,ch in enumerate(chunks):
        cend=chunks[ci+1][0][1] if ci+1<len(chunks) else TOT
        cend=min(cend,ch[-1][1]+1.0)
        for j,w in enumerate(ch):
            s=w[1]; e=ch[j+1][1] if j+1<len(ch) else cend
            parts=[]
            for jj,x in enumerate(ch):
                txt=x[0].upper().rstrip(",")
                if jj==j:
                    sc=130 if x[0].strip(".,?!").lower() in keys else 116
                    parts.append(f"{{\\c{GOLD}\\t(0,90,\\fscx{sc+8}\\fscy{sc+8})\\t(90,170,\\fscx{sc}\\fscy{sc})}}{txt}{{\\c&HFFFFFF&\\fscx100\\fscy100}}")
                else: parts.append(txt)
            ev.append(f"Dialogue: 1,{fmt(s)},{fmt(e)},Cap,,0,0,0,,{{\\pos(540,{LA['cap_y']+40})}}{' '.join(parts)}")
    nl=hook[0].count(chr(92)+'N')+1; HH=130*nl+20+110; hs=100
    if LA['hook_zone']=='low':
        hy=LA['chin']+5
        if hy+HH>1550: hs=max(70,int(100*(1550-hy)/HH))
    else: hy=160
    sc=f'\\fscx{hs}\\fscy{hs}'
    ev.append(f"Dialogue: 3,{fmt(0)},{fmt(hook_end)},Hook,,0,0,0,,{{\\an8\\pos(540,{hy}){sc}\\fad(0,150)}}{hook[0]}")
    ev.append(f"Dialogue: 3,{fmt(0.2)},{fmt(hook_end)},HookG,,0,0,0,,{{\\an8\\pos(540,{hy+int((130*nl+20)*hs/100)}){sc}\\fad(120,150)}}{hook[1]}")
    q0=SPEECH_END+0.05
    ql=q[0].count(chr(92)+'N')+1; QH=110*ql+20+90
    qy=160 if LA['face_top']-30-160>=QH else int(min(LA['chin']-10,1545-QH))
    ev.append(f"Dialogue: 3,{fmt(q0)},{fmt(TOT)},Q,,0,0,0,,{{\\an8\\pos(540,{qy})\\fad(150,0)}}{q[0]}")
    ev.append(f"Dialogue: 3,{fmt(q0+0.4)},{fmt(TOT)},QG,,0,0,0,,{{\\an8\\pos(540,{qy+110*ql+20})\\fad(150,0)}}{q[1]}")
    if qy==160: ev.append(f"Dialogue: 3,{fmt(TOT-2.6)},{fmt(TOT)},Sig,,0,0,0,,{{\\fad(200,0)}}@carlosveiolima")
    for txt,a,b in chips:
        ev.append(f"Dialogue: 2,{fmt(T(a))},{fmt(T(b))},Lb,,0,0,0,,{{\\fad(150,150)}}{txt}")
    win=[(T(a),min(T(b),T(a)+3.6)) for (png,a,b,_s,_y,_w) in cards if not png.endswith('.jpg')]
    def _t(x):
        h,m_,s_=x.split(':'); return int(h)*3600+int(m_)*60+float(s_)
    keep=[]
    for e in ev:
        pp=e.split(',',9)
        if pp[3]=='Cap':
            a_,b_=_t(pp[1]),_t(pp[2])
            if any(a_<wb and b_>wa for wa,wb in win): continue
            if a_>=q0: continue
            if b_>q0: pp[2]=fmt(q0); e=','.join(pp)
        keep.append(e)
    ev=keep
    ass=open(f"{W}/head.ass").read()+"\n".join(ev)+"\n"
    open(f"{W}/{name}.ass","w").write(ass)
    ins=["-i",f"{W}/{name}_base.mp4"];fc=[];last="0:v"
    for n,(png,a,b,side,y,wd) in enumerate(cards):
        ta=T(a); tb=min(T(b),ta+3.6)
        if not png.endswith('.jpg'):
            from PIL import Image as _I
            iw,ih=_I.open(png if os.path.isabs(png) else f'{W}/{png}').size; wd=min(wd,800); ch_=ih*wd//iw
            y=160 if LA['face_top']-30-160>=ch_ else int(min(LA['chin']+5,1545-ch_)); side=(1080-wd)//2
        if png.endswith(".jpg"):  # full-bleed
            ins+=["-itsoffset",f"{ta:.3f}","-loop","1","-framerate","30","-t",f"{tb-ta:.3f}","-i",png]
            fc.append(f"[{n+1}:v]scale=w='trunc(1080*(1.0+0.05*t/{tb-ta:.3f})/2)*2':h=-2:eval=frame,crop=1080:1920,setsar=1[c{n}]")
            fc.append(f"[{last}][c{n}]overlay=0:0:eof_action=pass[v{n}]")
        else:
            ins+=["-itsoffset",f"{ta:.3f}","-loop","1","-framerate","30","-t",f"{tb-ta:.3f}","-i",png]
            fc.append(f"[{n+1}:v]scale={wd}:-1[c{n}]")
            x0=f"W+({side}-W)*(t-{ta:.3f})/0.22" if side>300 else f"-w+({side}+w)*(t-{ta:.3f})/0.22"
            fc.append(f"[{last}][c{n}]overlay=x='if(lt(t-{ta:.3f},0.22),{x0},{side})':y={y}:eof_action=pass:eval=frame[v{n}]")
        last=f"v{n}"
    fc.append(f"[{last}]ass={W}/{name}.ass[vout]")
    run(ins+["-filter_complex",";".join(fc),"-map","[vout]","-map","0:a","-af","loudnorm=I=-14:TP=-1.5:LRA=9","-c:v","libx264","-preset","medium","-crf","19","-pix_fmt","yuv420p","-r","30","-c:a","aac","-b:a","192k","-ar","48000","-movflags","+faststart","-t",f"{TOT:.3f}",f"{W}/out_{name}.mp4"])
    print(name,"TOT",round(TOT,2))
    for p in pieces: print(" ",os.path.basename(p[0]),round(p[1],2),round(p[2],2))
    return TOT
