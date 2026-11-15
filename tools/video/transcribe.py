"""Transcrição com tempo por palavra (Parakeet). Uso: python3 transcribe.py audio16k.wav saida.json [pasta_modelos]
Saída: lista [palavra, início_s, fim_s]."""
import sys, os, json, sherpa_onnx, soundfile as sf
M = sys.argv[3] if len(sys.argv) > 3 else os.path.expanduser('~/.cache/cvl_models')
d = f'{M}/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/'
r = sherpa_onnx.OfflineRecognizer.from_transducer(encoder=d+'encoder.int8.onnx', decoder=d+'decoder.int8.onnx', joiner=d+'joiner.int8.onnx',
                                                  tokens=d+'tokens.txt', model_type='nemo_transducer', num_threads=4)
a, sr = sf.read(sys.argv[1], dtype='float32'); out = []; CH = 25 * sr; pos = 0
while pos < len(a):  # janelas de 25 s cortadas em silêncio aproximado
    end = min(len(a), pos + CH)
    if end < len(a):
        import numpy as np
        w = a[end - 2 * sr:end]; fr = 320; e = [np.mean(w[i:i+fr]**2) for i in range(0, len(w) - fr, fr)]
        end = end - 2 * sr + int(np.argmin(e)) * fr
    st = r.create_stream(); st.accept_waveform(sr, a[pos:end]); r.decode_stream(st); res = st.result
    toks, ts = res.tokens, res.timestamps
    cur = None
    for tk, t in zip(toks, ts):
        t = t + pos / sr
        if tk.startswith('▁') or tk.startswith(' ') or cur is None:
            if cur: out.append(cur)
            cur = [tk.lstrip('▁ '), round(t, 2), round(t + 0.08, 2)]
        else:
            cur[0] += tk; cur[2] = round(t + 0.08, 2)
    if cur: out.append(cur)
    pos = end
out = [w for w in out if w[0]]
json.dump(out, open(sys.argv[2], 'w'), ensure_ascii=False); print(len(out), 'palavras')
