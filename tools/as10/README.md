# Gerador do "As 10 da Semana"

Versão em uso pela rotina semanal (prevalece sobre a cópia da skill carrossel-untappd).

```bash
python3 tools/as10/scripts/ranking.py export.csv --inicio AAAA-MM-DD --fim AAAA-MM-DD --saida ranking.json
python3 tools/as10/scripts/gerar_carrossel.py spec.json
```

- Sempre 10 slides (limite do Metricool).
- Formato A: capa, posições 1 a 8, card final com 9ª, 10ª e CTA.
- Formato B: capa, posições 1 a 5, lista 6 a 10, frase da semana, decepção da semana, CTA.
- `ranking.json` traz `decepcao`: a cerveja fora do top com maior distância entre a nota global e a de Carlos.
- Fontes em `assets/fonts` (licença OFL).
