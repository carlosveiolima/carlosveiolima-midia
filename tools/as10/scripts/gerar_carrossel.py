#!/usr/bin/env python3
"""Gerador do carrossel "As 10 da Semana" (@carlosveiolima).

Uso:
  python3 gerar_carrossel.py spec.json

spec.json:
{
  "saida": "carrossel_03-09out",
  "capa": {
    "olho": "As 10 da semana · 03 a 09/10",
    "headline": "Uma semana sem caça e o teto *desabou* para 4,0",
    "apoio": "33 check-ins, 20 cervejarias, 1 vinho expulso do ranking.",
    "midia": "foto.jpg",            # opcional: foto (jpg/png/heic convertido) ou vídeo (mp4/mov)
    "foco_y": 0.5                    # opcional: 0 = topo, 1 = base, no recorte 4:5
  },
  "cervejas": [ {"pos":1,"cerveja":"...","cervejaria":"...","estilo":"Imperial Stout · 15%","nota":"4,8","slug":"Neuronova_Oscillation"}, ... ],
  "fechamento": ["Comenta MERCADO", "que te mando a", "newsletter no direct"],   # CTA do Instagram (linhas curtas)
  "fechamento_tiktok": ["As notas de cada uma", "no Substack,", "link na bio"],   # opcional
  "formato": "A",   # A (padrão): capa + 1 a 8 + card final com 9ª, 10ª e CTA
                    # B (teste nov/26): capa + 1 a 5 + lista 6 a 10 + números da semana + frase + CTA
  "frase": "Frase controversa da semana com *uma* palavra em dourado",   # só formato B
  "numeros": [["31", "check-ins"], ["8", "cervejarias"], ["9", "cervejas de 12% ou mais"]],  # só formato B
  # NUNCA publicar as piores notas da semana: reservado para o produto pago de Carlos.
}

Sempre 10 slides: o Metricool só publica 10 imagens por carrossel (o resto some sem aviso).

Na headline, palavras entre *asteriscos* saem em dourado (uma ou duas, no máximo).

Identidade fixa (não mudar sem Carlos pedir):
- 1080x1440 (3:4), margem 110px
- Verde #14251A, creme #F5F0E4, dourado #B8935A
- Playfair Display (números, notas, fechamento) + Archivo variável (nomes; condensada na capa)
- Cards alternam verde/creme; texto nunca é cortado (encolhe até caber) e nada sai da margem
- Letra pequena maior que nas versões até set/26 (legibilidade)
- Arquivos: slide_NN_posPP_<Cervejaria>_<Cerveja>.png, capa slide_01_capa, fecho slide_NN_fim
"""
import json, os, re, sys, glob, shutil, subprocess
from PIL import Image, ImageDraw, ImageFont, ImageOps

W, H = 1080, 1440
M = 110
CX0, CY0, CX1, CY1 = M, M, W - M, H - M
CW = CX1 - CX0
GREEN = (20, 37, 26)       # #14251A
CREAM = (245, 240, 228)    # #F5F0E4
GOLD = (184, 147, 90)      # #B8935A
MUTED_DARK = (188, 196, 180)
MUTED_LIGHT = (92, 104, 94)
SB = 1160                  # linha de base da nota
FD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "fonts")

# tamanhos de "letra pequena" (subidos em out/26 a pedido de Carlos)
SZ_CERVEJARIA = 50
SZ_ESTILO = 44
SZ_LABEL = 34
SZ_OLHO = 34
SZ_APOIO = 40
SZ_RODAPE = 30

_violacoes = []


def font(nome, size, weight=None, width=None):
    f = ImageFont.truetype(os.path.join(FD, nome), size)
    try:
        axes = []
        for ax in f.get_variation_axes():
            n = ax["name"].decode() if isinstance(ax["name"], bytes) else ax["name"]
            if n == "Weight":
                axes.append(weight if weight else ax["default"])
            elif n == "Width":
                axes.append(width if width else ax["default"])
            else:
                axes.append(ax["default"])
        f.set_variation_by_axes(axes)
    except Exception:
        pass
    return f


def wrap(d, texto, f, mw):
    out, cur = [], ""
    for w in texto.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= mw:
            cur = t
        else:
            if cur:
                out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out


def lh(f, fac=1.12):
    a, de = f.getmetrics()
    return int((a + de) * fac)


def texto(d, xy, s, f, fill, slide, anchor="la"):
    """Desenha e confere se ficou dentro da área segura."""
    d.text(xy, s, font=f, fill=fill, anchor=anchor)
    x0, y0, x1, y1 = d.textbbox(xy, s, font=f, anchor=anchor)
    if x0 < CX0 - 2 or x1 > CX1 + 2 or y0 < 40 or y1 > H - 40:
        _violacoes.append(f"{slide}: '{s}' fora da área segura {x0,y0,x1,y1}")
    if d.textlength(s, font=f) > CW + 2:
        _violacoes.append(f"{slide}: '{s}' mais largo que a coluna")


# ---------- cards de cerveja ----------
def card(pos, cerveja, cervejaria, estilo, nota, escuro, out):
    bg = GREEN if escuro else CREAM
    fg = CREAM if escuro else GREEN
    mu = MUTED_DARK if escuro else MUTED_LIGHT
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    nome = os.path.basename(out)

    # posição gigante, dourada, canto superior
    pf = font("Playfair.ttf", 230, 700)
    texto(d, (CX0, CY0 - 30), f"{pos:02d}", pf, GOLD, nome)
    y = CY0 + lh(pf, 0.92)
    d.line([(CX0, y), (CX0 + 120, y)], fill=GOLD, width=4)
    y += 50

    # nome da cerveja: encolhe até caber em 4 linhas e acima da zona da nota
    cf = font("Archivo.ttf", SZ_CERVEJARIA, 700, 100)
    sf = font("ArchivoItalic.ttf", SZ_ESTILO, 500, 100)
    limite = SB - 250
    bf, linhas = None, []
    for s in range(92, 30, -3):
        bf = font("Archivo.ttf", s, 800, 100)
        linhas = wrap(d, cerveja, bf, CW)
        larg_ok = all(d.textlength(l, font=bf) <= CW for l in linhas)
        lc = wrap(d, cervejaria, cf, CW)
        ls = wrap(d, estilo, sf, CW)
        total = y + len(linhas) * lh(bf, 1.06) + 24 + len(lc) * lh(cf, 1.05) + 10 + len(ls) * lh(sf, 1.1)
        if len(linhas) <= 4 and larg_ok and total <= limite:
            break
    for l in linhas:
        texto(d, (CX0, y), l, bf, fg, nome)
        y += lh(bf, 1.06)
    y += 24
    for l in wrap(d, cervejaria, cf, CW):
        texto(d, (CX0, y), l, cf, GOLD, nome)
        y += lh(cf, 1.05)
    y += 10
    for l in wrap(d, estilo, sf, CW):
        texto(d, (CX0, y), l, sf, mu, nome)
        y += lh(sf, 1.1)

    # nota
    nf = font("Playfair.ttf", 210, 700)
    lb = font("Archivo.ttf", SZ_LABEL, 700, 100)
    s = str(nota).replace(".", ",")
    texto(d, (CX1, SB - 205), "NOTA", lb, mu, nome, anchor="rs")
    texto(d, (CX1, SB), s, nf, GOLD, nome, anchor="rs")
    rf = font("Archivo.ttf", SZ_RODAPE, 600, 100)
    texto(d, (CX0, H - 75), "@carlosveiolima", rf, mu, nome, anchor="ls")
    im.save(out)


# ---------- capa (modelo out/26) ----------
def segmentos(headline):
    """'texto *dourado* texto' -> [(palavra, dourado?)]"""
    out = []
    for parte in re.split(r"(\*[^*]+\*)", headline):
        if not parte:
            continue
        dour = parte.startswith("*") and parte.endswith("*")
        for w in parte.strip("*").split():
            out.append((w, dour))
    return out


def wrap_seg(d, segs, f, mw):
    linhas, cur, larg = [], [], 0
    esp = d.textlength(" ", font=f)
    for w, g in segs:
        lw = d.textlength(w, font=f)
        add = lw if not cur else larg + esp + lw
        if cur and add > mw:
            linhas.append(cur)
            cur, larg = [(w, g)], lw
        else:
            cur.append((w, g))
            larg = add
    if cur:
        linhas.append(cur)
    return linhas


def preparar_fundo(midia, foco_y):
    im = Image.open(midia)
    im = ImageOps.exif_transpose(im).convert("RGB")
    r = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * r + 0.5), int(im.height * r + 0.5)), Image.LANCZOS)
    x = (im.width - W) // 2
    y = int((im.height - H) * foco_y)
    return im.crop((x, y, x + W, y + H))


def overlay_capa(cfg, com_midia):
    """Camada RGBA com gradiente + tipografia. Sem mídia, fundo verde sólido."""
    camada = Image.new("RGBA", (W, H), (0, 0, 0, 0) if com_midia else GREEN + (255,))
    if com_midia:
        grad = Image.new("RGBA", (W, H))
        gd = ImageDraw.Draw(grad)
        for yy in range(H):
            t = yy / H
            a = int(165 - 40 * min(1, t / 0.45) + 120 * max(0, (t - 0.45) / 0.55))  # escurece para baixo
            gd.line([(0, yy), (W, yy)], fill=GREEN + (min(a, 245),))
        camada = Image.alpha_composite(camada, grad)
    d = ImageDraw.Draw(camada)
    nome = "slide_01_capa"

    of = font("Archivo.ttf", SZ_OLHO, 700, 100)
    texto(d, (CX0, 120), cfg.get("olho", "As 10 da semana").upper(), of, GOLD, nome)
    d.rectangle([CX0, 178, CX0 + 120, 183], fill=GOLD)

    segs = segmentos(cfg["headline"])
    apoio = cfg.get("apoio", "")
    af = font("Playfair.ttf", SZ_APOIO, 400)
    la = wrap(d, apoio, af, CW) if apoio else []
    h_apoio = len(la) * lh(af, 1.2) + (60 if la else 0)
    base_rodape = H - 150
    for s in range(132, 60, -4):
        hf = font("Archivo.ttf", s, 800, 70)   # condensada
        linhas = wrap_seg(d, segs, hf, CW)
        altura = len(linhas) * lh(hf, 1.0)
        if len(linhas) <= 7 and 240 + altura + h_apoio <= base_rodape:
            break
    y = 250
    for ln in linhas:
        x = CX0
        for i, (w, g) in enumerate(ln):
            if i:
                x += d.textlength(" ", font=hf)
            texto(d, (x, y), w, hf, GOLD if g else CREAM, nome)
            x += d.textlength(w, font=hf)
        y += lh(hf, 1.0)
    if la:
        y += 40
        d.rectangle([CX0, y, CX1, y + 2], fill=(GOLD[0], GOLD[1], GOLD[2], 160))
        y += 30
        for l in la:
            texto(d, (CX0, y), l, af, MUTED_DARK, nome)
            y += lh(af, 1.2)

    rf = font("Archivo.ttf", SZ_RODAPE, 700, 100)
    texto(d, (CX0, H - 75), "@carlosveiolima", rf, MUTED_DARK, nome, anchor="ls")
    arr = "ARRASTA"
    tw = d.textlength(arr, font=rf)
    texto(d, (CX1 - 34, H - 75), arr, rf, GOLD, nome, anchor="rs")
    d.polygon([(CX1 - 20, H - 97), (CX1, H - 86), (CX1 - 20, H - 75)], fill=GOLD)
    return camada


def capa(cfg, pasta):
    midia = cfg.get("midia")
    foco = float(cfg.get("foco_y", 0.5))
    if midia and os.path.splitext(midia)[1].lower() in (".mp4", ".mov", ".m4v"):
        ov = overlay_capa(cfg, True)
        ovp = os.path.join(pasta, "_overlay_capa.png")
        ov.save(ovp)
        out = os.path.join(pasta, "slide_01_capa.mp4")
        vf = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
              f"crop={W}:{H}:(iw-{W})/2:(ih-{H})*{foco}[bg];[bg][1:v]overlay=0:0,format=yuv420p")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", midia, "-i", ovp,
                        "-filter_complex", vf, "-c:v", "libx264", "-crf", "20", "-preset", "medium",
                        "-c:a", "aac", "-movflags", "+faststart", out], check=True)
        # quadro estático para a folha de contato e para thumbnail
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "0.5", "-i", out,
                        "-frames:v", "1", os.path.join(pasta, "_capa_frame.png")], check=True)
        os.remove(ovp)
        return out
    if midia:
        bg = preparar_fundo(midia, foco).convert("RGBA")
        im = Image.alpha_composite(bg, overlay_capa(cfg, True)).convert("RGB")
    else:
        im = overlay_capa(cfg, False).convert("RGB")
    out = os.path.join(pasta, "slide_01_capa.png")
    im.save(out)
    return out


# ---------- fechamento ----------
def fechamento(linhas, out):
    im = Image.new("RGB", (W, H), GREEN)
    d = ImageDraw.Draw(im)
    nome = os.path.basename(out)
    d.line([(W // 2 - 45, H // 2 - 200), (W // 2 + 45, H // 2 - 200)], fill=GOLD, width=5)
    tf = font("Playfair.ttf", 72, 700)
    y = H // 2 - 130
    for l in linhas:
        w = d.textlength(l, font=tf)
        texto(d, ((W - w) // 2, y), l, tf, CREAM, nome)
        y += lh(tf, 1.1)
    hf = font("Archivo.ttf", 56, 800, 100)
    h = "@carlosveiolima"   # sempre só @carlosveiolima, nunca @_plantaocervejeiro
    w = d.textlength(h, font=hf)
    texto(d, ((W - w) // 2, y + 50), h, hf, GOLD, nome)
    im.save(out)


# ---------- card final duplo (9ª + 10ª + CTA) ----------
# Publicação por API (Metricool) aceita no máximo 10 imagens por carrossel.
# Capa + 8 cards + este card = 10. Nunca publicar só até a 9ª.
def card_duplo(itens, cta, out):
    im = Image.new("RGB", (W, H), GREEN)
    d = ImageDraw.Draw(im)
    n = os.path.basename(out)
    pf = font("Playfair.ttf", 120, 700)
    lb = font("Archivo.ttf", SZ_LABEL, 700, 100)
    cf = font("Archivo.ttf", SZ_CERVEJARIA, 700, 100)
    sf = font("ArchivoItalic.ttf", SZ_ESTILO, 500, 100)
    y = CY0 - 10
    for k, c in enumerate(itens):
        if k:
            d.line([(CX0, y), (CX1, y)], fill=GOLD, width=2)
            y += 34
        nota = str(c["nota"]).replace(".", ",")
        texto(d, (CX0, y), f"{c['pos']:02d}", pf, GOLD, n)
        texto(d, (CX1, y), nota, pf, GOLD, n, anchor="ra")
        bx = d.textbbox((CX1, y), nota, font=pf, anchor="ra")
        texto(d, (bx[0] - 24, bx[3]), "NOTA", lb, MUTED_DARK, n, anchor="rs")
        y = bx[3] + 28
        for s in range(64, 36, -2):
            bf = font("Archivo.ttf", s, 800, 100)
            ls = wrap(d, c["cerveja"], bf, CW)
            if len(ls) <= 2:
                break
        for l in ls:
            texto(d, (CX0, y), l, bf, CREAM, n)
            y += lh(bf, 1.06)
        y += 14
        texto(d, (CX0, y), c["cervejaria"], cf, GOLD, n)
        y += lh(cf, 1.05) + 6
        texto(d, (CX0, y), c["estilo"], sf, MUTED_DARK, n)
        y += lh(sf, 1.1) + 30
    tf = font("Playfair.ttf", 52, 700)
    yc = max(y + 20, H - 210 - len(cta) * lh(tf, 1.1) - 40)
    d.line([(W // 2 - 45, yc), (W // 2 + 45, yc)], fill=GOLD, width=5)
    yc += 40
    for l in cta:
        w = d.textlength(l, font=tf)
        texto(d, ((W - w) // 2, yc), l, tf, CREAM, n)
        yc += lh(tf, 1.1)
    hf = font("Archivo.ttf", 48, 800, 100)
    h = "@carlosveiolima"
    w = d.textlength(h, font=hf)
    texto(d, ((W - w) // 2, yc + 30), h, hf, GOLD, n)
    im.save(out)


# ---------- formato B (teste nov/26): lista 6 a 10, números, frase ----------
def _cores(escuro):
    return (GREEN, CREAM, MUTED_DARK) if escuro else (CREAM, GREEN, MUTED_LIGHT)


def _olho(d, txt, n):
    of = font("Archivo.ttf", SZ_OLHO, 700, 100)
    texto(d, (CX0, CY0), txt.upper(), of, GOLD, n)
    d.rectangle([CX0, CY0 + 58, CX0 + 120, CY0 + 63], fill=GOLD)
    return CY0 + 110


def _rodape(d, mu, n):
    rf = font("Archivo.ttf", SZ_RODAPE, 600, 100)
    texto(d, (CX0, H - 75), "@carlosveiolima", rf, mu, n, anchor="ls")


def card_lista(itens, escuro, out):
    bg, fg, mu = _cores(escuro)
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    n = os.path.basename(out)
    y = _olho(d, f"Da {itens[0]['pos']}ª à {itens[-1]['pos']}ª", n)
    pf = font("Playfair.ttf", 64, 700)
    nf = font("Playfair.ttf", 80, 700)
    cf = font("Archivo.ttf", 44, 700, 100)
    sf = font("ArchivoItalic.ttf", 40, 500, 100)
    colx = CX0 + 110
    for k, c in enumerate(itens):
        nota = str(c["nota"]).replace(".", ",")
        wn = d.textlength(nota, font=nf)
        mw = CX1 - colx - wn - 30
        for sz in range(50, 34, -2):
            bf = font("Archivo.ttf", sz, 800, 100)
            ls = wrap(d, c["cerveja"], bf, mw)
            if len(ls) <= 2:
                break
        texto(d, (CX0, y - 4), f"{c['pos']:02d}", pf, GOLD, n)
        texto(d, (CX1, y - 8), nota, nf, GOLD, n, anchor="ra")
        for l in ls:
            texto(d, (colx, y), l, bf, fg, n)
            y += lh(bf, 1.05)
        y += 4
        texto(d, (colx, y), c["cervejaria"], cf, GOLD, n)
        y += lh(cf, 1.05)
        for l in wrap(d, c["estilo"], sf, CX1 - colx):
            texto(d, (colx, y), l, sf, mu, n)
            y += lh(sf, 1.08)
        if k < len(itens) - 1:
            y += 16
            d.line([(CX0, y), (CX1, y)], fill=GOLD, width=1)
            y += 26
    _rodape(d, mu, n)
    im.save(out)


def card_frase(frase, escuro, out, olho="A frase da semana"):
    bg, fg, mu = _cores(escuro)
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    n = os.path.basename(out)
    y0 = _olho(d, olho, n)
    segs = segmentos(frase)
    for sz in range(92, 44, -4):
        ff = font("Playfair.ttf", sz, 700)
        linhas = wrap_seg(d, segs, ff, CW)
        if y0 + 60 + len(linhas) * lh(ff, 1.12) <= H - 200:
            break
    y = max(y0 + 60, (H - len(linhas) * lh(ff, 1.12)) // 2)
    for ln in linhas:
        x = CX0
        for i, (w, g) in enumerate(ln):
            if i:
                x += d.textlength(" ", font=ff)
            texto(d, (x, y), w, ff, GOLD if g else fg, n)
            x += d.textlength(w, font=ff)
        y += lh(ff, 1.12)
    _rodape(d, mu, n)
    im.save(out)


def card_numeros(itens, escuro, out, olho="A semana em números"):
    """itens: lista de até 4 pares [valor, rótulo], ex.: ["31", "check-ins"]."""
    bg, fg, mu = _cores(escuro)
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    n = os.path.basename(out)
    y = _olho(d, olho, n) + 40
    vf = font("Playfair.ttf", 150, 700)
    lf = font("Archivo.ttf", 44, 700, 100)
    passo = (H - 160 - y) // max(1, len(itens[:4]))
    for valor, rotulo in itens[:4]:
        texto(d, (CX0, y), str(valor), vf, GOLD, n)
        yy = y + lh(vf, 0.9) + 24
        for l in wrap(d, rotulo, lf, CW):
            texto(d, (CX0, yy), l, lf, fg, n)
            yy += lh(lf, 1.05)
        y += passo
    _rodape(d, mu, n)
    im.save(out)


def main():
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    so_cervejas = "--so-cervejas" in sys.argv   # capa e fecho aprovados não são refeitos
    pasta = spec["saida"]
    os.makedirs(pasta, exist_ok=True)
    padrao = "slide_*_pos*" if so_cervejas else "slide_*"
    for f in glob.glob(os.path.join(pasta, padrao)):
        os.remove(f)

    arquivos = []
    tem_capa = "capa" in spec
    if tem_capa:
        if so_cervejas:
            existentes = sorted(glob.glob(os.path.join(pasta, "slide_01_capa.*")))
            if not existentes:
                sys.exit("--so-cervejas pedido, mas não há capa gerada nesta pasta")
            arquivos.append(existentes[0])
        else:
            arquivos.append(capa(spec["capa"], pasta))
    n0 = 2 if tem_capa else 1
    cervs = sorted(spec["cervejas"], key=lambda c: c["pos"])
    formato = str(spec.get("formato", "A")).upper()
    cta = spec.get("fechamento", ["As notas e o comentário", "de cada uma no Substack"])
    cta_tt = spec.get("fechamento_tiktok", ["As notas de cada uma", "no Substack,", "link na bio"])
    if formato == "B":
        # capa, 1 a 5 (um por card), lista 6 a 10, números, frase, CTA = 10 slides
        if not (tem_capa and len(cervs) == 10 and spec.get("frase") and spec.get("numeros")):
            sys.exit("formato B precisa de capa, 10 cervejas, 'frase' e 'numeros' no spec")
        for i, c in enumerate(cervs[:5]):
            slug = re.sub(r"[^\w-]", "_", c.get("slug") or f"{c['cervejaria']}_{c['cerveja']}")[:48]
            out = os.path.join(pasta, f"slide_{n0 + i:02d}_pos{c['pos']:02d}_{slug}.png")
            card(c["pos"], c["cerveja"], c["cervejaria"], c["estilo"], c["nota"], i % 2 == 0, out)
            arquivos.append(out)
        out = os.path.join(pasta, "slide_07_pos06-10_lista.png")
        card_lista(cervs[5:], False, out); arquivos.append(out)
        out = os.path.join(pasta, "slide_08_numeros.png")
        card_numeros(spec["numeros"], True, out); arquivos.append(out)
        out = os.path.join(pasta, "slide_09_frase.png")
        card_frase(spec["frase"], False, out); arquivos.append(out)
        fim = os.path.join(pasta, "slide_10_fim.png")
        fechamento(cta, fim)
        fim_tt = os.path.join(pasta, "slide_10_fim_tiktok.png")
        fechamento(cta_tt, fim_tt)
        cervs = []
    # formato A: com capa e 10 cervejas, a 9ª e a 10ª vão juntas no card final com o CTA
    duplo = tem_capa and len(cervs) == 10
    simples = cervs[:8] if duplo else cervs
    for i, c in enumerate(simples):
        slug = re.sub(r"[^\w-]", "_", c.get("slug") or f"{c['cervejaria']}_{c['cerveja']}")[:48]
        out = os.path.join(pasta, f"slide_{n0 + i:02d}_pos{c['pos']:02d}_{slug}.png")
        card(c["pos"], c["cerveja"], c["cervejaria"], c["estilo"], c["nota"], i % 2 == 0, out)
        arquivos.append(out)
    if formato == "B":
        pass
    elif duplo:
        fim = os.path.join(pasta, f"slide_{n0 + 8:02d}_pos09-10_fim.png")
        card_duplo(cervs[8:], cta, fim)
        fim_tt = fim.replace("_fim.png", "_fim_tiktok.png")
        card_duplo(cervs[8:], cta_tt, fim_tt)
    else:
        fim = os.path.join(pasta, f"slide_{n0 + len(cervs):02d}_fim.png")
        if not (so_cervejas and os.path.exists(fim)):
            fechamento(cta, fim)
        fim_tt = fim.replace("_fim.png", "_fim_tiktok.png")
        fechamento(cta_tt, fim_tt)
    arquivos.append(fim)

    # JPEGs para upload (Drive/Metricool), mesma numeração
    up = os.path.join(pasta, "upload")
    os.makedirs(up, exist_ok=True)
    for f in glob.glob(os.path.join(up, "*")):
        os.remove(f)
    for a in arquivos + [fim_tt]:
        base = os.path.splitext(os.path.basename(a))[0]
        if a.endswith(".png"):
            Image.open(a).convert("RGB").save(os.path.join(up, base + ".jpg"), quality=92, optimize=True)
        else:
            shutil.copy(a, up)
            # TikTok (modo foto) não mistura vídeo e imagem: quadro estático da capa
            Image.open(os.path.join(pasta, "_capa_frame.png")).convert("RGB").save(
                os.path.join(up, base + "_quadro.jpg"), quality=92, optimize=True)

    # folha de contato para conferência visual
    prev = [os.path.join(pasta, "_capa_frame.png") if a.endswith(".mp4") else a for a in arquivos]
    tw, th, cols = 270, 360, 4
    rows = (len(prev) + cols - 1) // cols
    sh = Image.new("RGB", (cols * tw + (cols + 1) * 10, rows * th + (rows + 1) * 10), (45, 45, 45))
    for i, f in enumerate(prev):
        r, c = divmod(i, cols)
        sh.paste(Image.open(f).convert("RGB").resize((tw, th)), (10 + c * (tw + 10), 10 + r * (th + 10)))
    sh.save(os.path.join(pasta, "_folha_contato.png"))

    for a in arquivos:
        print(a)
    if len(arquivos) > 10:
        _violacoes.append(f"{len(arquivos)} slides: o Metricool só publica 10 por carrossel")
    if _violacoes:
        print("\nVIOLAÇÕES DE ÁREA SEGURA (corrigir antes de entregar):")
        for v in _violacoes:
            print(" ", v)
        sys.exit(2)
    print(f"\nOK: {len(arquivos)} slides, nenhuma palavra fora da área segura.")


if __name__ == "__main__":
    main()
