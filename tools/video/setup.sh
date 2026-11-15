#!/bin/bash
# Reinstala o ambiente de edição de vídeo (rodar sempre que a máquina for trocada).
# Uso: bash tools/video/setup.sh [pasta_dos_modelos]
M=${1:-$HOME/.cache/cvl_models}; mkdir -p "$M"
pip install -q --break-system-packages sherpa-onnx soundfile opencv-python-headless==4.10.0.84 pandas >/dev/null 2>&1
for f in sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8 sherpa-onnx-whisper-turbo; do
  if [ ! -f "$M/$f/tokens.txt" ] && [ ! -f "$M/$f/turbo-tokens.txt" ]; then
    curl -sL -o "$M/$f.tar.bz2" https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/$f.tar.bz2 && tar xjf "$M/$f.tar.bz2" -C "$M" && rm "$M/$f.tar.bz2"
  fi
done
echo "MODELS=$M"; ls "$M"
