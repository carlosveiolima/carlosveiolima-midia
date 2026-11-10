# Ferramentas de vídeo @carlosveiolima

- `qc_video.py`: QC obrigatório antes de agendar qualquer vídeo (legenda/título: tempo de leitura e rosto; área segura; luz/cor; áudio -14 LUFS; ritmo; gancho no quadro 0).
- `layout.py`: `analyze(base.mp4)` dá gamma, faixa do rosto e posição de gancho/legenda/cards; `caption_chunks()` agrupa legendas legíveis.
- `reel_builder_ref.py` + `head.ass`: builder de referência (cortes por energia, karaoke, gancho/cards/CTA posicionados pelo rosto). Ajuste SRC/WL para o vídeo da vez.
- OpenCV 4 privado é instalado sozinho em `cv4/` na primeira execução.
