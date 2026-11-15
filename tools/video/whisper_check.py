"""Retranscreve trechos com Whisper para conferir cortes. Uso: python3 whisper_check.py arquivo.wav:ini:fim [...] (janelas de até 28 s)"""
import sys, os, sherpa_onnx, soundfile as sf
M = os.environ.get('CVL_MODELS', os.path.expanduser('~/.cache/cvl_models')); d = f'{M}/sherpa-onnx-whisper-turbo/'
r = sherpa_onnx.OfflineRecognizer.from_whisper(encoder=d+'turbo-encoder.int8.onnx', decoder=d+'turbo-decoder.int8.onnx', tokens=d+'turbo-tokens.txt', language='pt', num_threads=4)
for spec in sys.argv[1:]:
    f, a0, a1 = spec.rsplit(':', 2); a, sr = sf.read(f, dtype='float32')
    st = r.create_stream(); st.accept_waveform(sr, a[int(float(a0)*sr):int(float(a1)*sr)]); r.decode_stream(st)
    print(f'{a0}-{a1} |', st.result.text.strip(), flush=True)
