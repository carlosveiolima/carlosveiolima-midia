#!/usr/bin/env python3
"""As 10 da Semana: filtra o export CSV do Untappd e monta o ranking.

Uso:
  python3 ranking.py export.csv --inicio 2026-10-03 --fim 2026-10-09 \
      [--excluir-cervejaria "O Corvo"] [--excluir-cerveja "Nome"] \
      [--top 10] --saida ranking.json

Regras aplicadas (vêm do cânone de Carlos, não mudar sem ele pedir):
- Janela inclusiva: do início 00:00 ao fim 23:59:59 (data local do export).
- SÓ CERVEJA: fora vinho, destilado, sidra, mead, sake e afins. Barley wine e
  wheat wine são cerveja e ficam. Tudo que sai é listado em "excluidos" para
  Carlos conferir.
- Só check-ins com nota pessoal entram no ranking.
- Deduplica por ID da cerveja (bid): fica o check-in de maior nota; empate,
  o mais recente.
- Ordem: nota pessoal desc, nota global ponderada desc, data desc.
- ABV: número real entra como está; 0 só vira "sem álcool" se o beer_type
  confirmar Non-Alcoholic, senão é omitido; vazio/N/A é omitido e sinalizado.
- Nacionalidade vem do export e sai marcada como "verificar no site oficial"
  antes de qualquer menção em texto publicado.
"""
import argparse, json, re, sys
import pandas as pd

NAO_CERVEJA_PREFIXOS = ("wine", "sake", "spirit",
                        "whisk", "bourbon", "rum", "gin", "vodka", "tequila",
                        "mezcal", "brandy", "cachaça", "cachaca", "liqueur",
                        "kombucha", "hard seltzer", "hard tea", "hard coffee")
CERVEJA_COM_WINE = ("barleywine", "barley wine", "wheatwine", "wheat wine",
                    "rye wine", "ryewine")


def eh_cerveja(beer_type: str) -> bool:
    t = (beer_type or "").strip().lower()
    if not t:
        return True  # sem tipo: mantém, mas o relatório mostra
    if any(t.startswith(k) for k in CERVEJA_COM_WINE):
        return True
    return not any(t.startswith(p) for p in NAO_CERVEJA_PREFIXOS)


def fmt_abv(abv, beer_type):
    """Devolve (texto ou None, aviso ou None)."""
    if abv is None or (isinstance(abv, float) and pd.isna(abv)) or str(abv).strip().upper() in ("", "N/A", "NA"):
        return None, "ABV ausente: omitido, perguntar a Carlos"
    try:
        v = float(str(abv).replace(",", "."))
    except ValueError:
        return None, f"ABV ilegível ({abv}): omitido, perguntar a Carlos"
    if v == 0:
        if "non-alcoholic" in (beer_type or "").lower():
            return "sem álcool", None
        return None, "ABV 0 sem confirmação de Non-Alcoholic no beer_type: omitido"
    s = f"{v:.1f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{s}%", None


def estilo_curto(beer_type: str) -> str:
    """Sugestão de estilo curto. Carlos/Claude podem reescrever no JSON."""
    t = (beer_type or "").strip()
    mapa = [
        (r"^IPA - Imperial / Double New England / Hazy", "Imperial NEIPA (Hazy)"),
        (r"^IPA - Triple New England / Hazy", "Triple NEIPA (Hazy)"),
        (r"^IPA - Quadruple", "Quadruple IPA"),
        (r"^IPA - New England / Hazy", "NEIPA (Hazy)"),
        (r"^IPA - Imperial / Double Milkshake", "Imperial Milkshake IPA"),
        (r"^IPA - Milkshake", "Milkshake IPA"),
        (r"^IPA - Imperial / Double", "Imperial IPA"),
        (r"^IPA - Triple", "Triple IPA"),
        (r"^IPA - American", "American IPA"),
        (r"^Stout - Imperial / Double Pastry", "Imperial Pastry Stout"),
        (r"^Stout - Imperial / Double", "Imperial Stout"),
        (r"^Sour - Smoothie / Pastry", "Smoothie Sour"),
        (r"^Sour - Fruited", "Fruited Sour"),
        (r"^Lambic - Gueuze", "Gueuze"),
        (r"^Barleywine", "Barleywine"),
    ]
    for pad, curto in mapa:
        if re.match(pad, t):
            return curto
    if t.lower().startswith("non-alcoholic beer - "):
        return t.split(" - ", 1)[1].split(" / ")[0]
    if " - " in t:
        principal, sub = t.split(" - ", 1)
        return f"{sub.split(' / ')[0]} {principal}"
    return t


def fmt_nota(v):
    s = f"{float(v):.2f}"
    if s.endswith("0"):
        s = s[:-1]
    return s.replace(".", ",")


def slug(texto, n=28):
    s = re.sub(r"[^\w\s-]", "", texto, flags=re.UNICODE)
    s = re.sub(r"\s+", "_", s.strip())
    return s[:n].rstrip("_")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--inicio", required=True)
    ap.add_argument("--fim", required=True)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--excluir-cervejaria", action="append", default=[])
    ap.add_argument("--excluir-cerveja", action="append", default=[])
    ap.add_argument("--saida", default="ranking.json")
    a = ap.parse_args()

    df = pd.read_csv(a.csv)
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    ini = pd.Timestamp(a.inicio)
    fim = pd.Timestamp(a.fim) + pd.Timedelta(days=1)
    w = df[(df["created_at"] >= ini) & (df["created_at"] < fim)].copy()

    excl = []
    mask_cerv = w["beer_type"].fillna("").map(eh_cerveja)
    for _, r in w[~mask_cerv].iterrows():
        excl.append({"cerveja": r["beer_name"], "cervejaria": r["brewery_name"],
                     "tipo": r["beer_type"], "motivo": "não é cerveja"})
    w = w[mask_cerv]
    for nome in a.excluir_cervejaria:
        m = w["brewery_name"].fillna("").str.lower() == nome.lower()
        for _, r in w[m].iterrows():
            excl.append({"cerveja": r["beer_name"], "cervejaria": r["brewery_name"],
                         "tipo": r["beer_type"], "motivo": f"cervejaria excluída por Carlos ({nome})"})
        w = w[~m]
    for nome in a.excluir_cerveja:
        m = w["beer_name"].fillna("").str.lower() == nome.lower()
        for _, r in w[m].iterrows():
            excl.append({"cerveja": r["beer_name"], "cervejaria": r["brewery_name"],
                         "tipo": r["beer_type"], "motivo": "cerveja excluída por Carlos"})
        w = w[~m]

    stats = {
        "checkins_cerveja": int(len(w)),
        "cervejas_unicas": int(w["bid"].nunique()),
        "com_nota": int(w["rating_score"].notna().sum()),
        "sem_nota": int(w["rating_score"].isna().sum()),
        "cervejarias": int(w["brewery_id"].nunique()) if "brewery_id" in w else int(w["brewery_name"].nunique()),
        "checkins_por_cervejaria": w["brewery_name"].value_counts().head(5).to_dict(),
    }

    rated = w.dropna(subset=["rating_score"]).copy()
    rated = rated.sort_values(["rating_score", "created_at"], ascending=[False, False])
    dups = int(rated.duplicated("bid").sum())
    rated = rated.drop_duplicates("bid", keep="first")
    gw = "global_weighted_rating_score" if "global_weighted_rating_score" in rated else "global_rating_score"
    rated = rated.sort_values(["rating_score", gw, "created_at"], ascending=[False, False, False])

    top = []
    for i, (_, r) in enumerate(rated.head(a.top).iterrows(), 1):
        abv_txt, aviso = fmt_abv(r.get("beer_abv"), r.get("beer_type"))
        est = estilo_curto(r.get("beer_type"))
        top.append({
            "pos": i,
            "cerveja": r["beer_name"],
            "cervejaria": r["brewery_name"],
            "tipo_untappd": r.get("beer_type"),
            "estilo": f"{est} · {abv_txt}" if abv_txt else est,
            "abv_aviso": aviso,
            "nota": fmt_nota(r["rating_score"]),
            "nota_global": None if pd.isna(r.get(gw)) else round(float(r[gw]), 2),
            "pais_export": r.get("brewery_country"),
            "cidade_export": r.get("brewery_city"),
            "estado_export": None if pd.isna(r.get("brewery_state")) else r.get("brewery_state"),
            "nacionalidade_status": "VERIFICAR no site oficial antes de citar em texto",
            "slug": f"{slug(str(r['brewery_name']), 18)}_{slug(str(r['beer_name']), 24)}",
            "data_checkin": str(r["created_at"]),
        })

    # empates na fronteira do top: Carlos decide
    corte = None
    if len(rated) > a.top:
        nota_corte = rated.iloc[a.top - 1]["rating_score"]
        fora = rated.iloc[a.top:]
        empatados = fora[fora["rating_score"] == nota_corte]
        if len(empatados):
            corte = [f"{r['beer_name']} ({r['brewery_name']}) {r['rating_score']}" for _, r in empatados.iterrows()]

    # decepção da semana (formato B): fora do top, maior distância entre a nota global e a de Carlos
    decepcao = None
    resto = rated.iloc[a.top:].copy()
    resto = resto[resto[gw].notna()]
    if len(resto):
        resto["_gap"] = resto[gw].astype(float) - resto["rating_score"].astype(float)
        resto = resto[resto["_gap"] > 0].sort_values(["_gap", gw], ascending=[False, False])
        if len(resto):
            r = resto.iloc[0]
            abv_txt, aviso = fmt_abv(r.get("beer_abv"), r.get("beer_type"))
            est = estilo_curto(r.get("beer_type"))
            decepcao = {"cerveja": r["beer_name"], "cervejaria": r["brewery_name"],
                        "estilo": f"{est} · {abv_txt}" if abv_txt else est, "abv_aviso": aviso,
                        "nota": fmt_nota(r["rating_score"]), "nota_global": fmt_nota(round(float(r[gw]), 2)),
                        "brewery_url": r.get("brewery_url"),
                        "slug": f"{slug(str(r['brewery_name']), 18)}_{slug(str(r['beer_name']), 24)}"}

    out = {"janela": [a.inicio, a.fim], "stats": stats, "duplicatas_removidas": dups,
           "excluidos": excl, "empatados_fora_do_top": corte, "top": top, "decepcao": decepcao}
    with open(a.saida, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)

    print(json.dumps(stats, ensure_ascii=False))
    print(f"duplicatas removidas: {dups} | excluídos: {len(excl)}")
    for e in excl:
        print("  FORA:", e)
    if corte:
        print("  EMPATE NA FRONTEIRA (fora do top):", corte)
    if decepcao:
        print("  DECEPÇÃO (formato B):", decepcao["cerveja"], "|", decepcao["cervejaria"], "| sua", decepcao["nota"], "x global", decepcao["nota_global"])
    for t in top:
        print(f"{t['pos']:2d}. {t['nota']} | {t['cerveja']} | {t['cervejaria']} | {t['estilo']} | "
              f"{t['pais_export']}/{t['cidade_export']}/{t['estado_export']}" + (f" | {t['abv_aviso']}" if t['abv_aviso'] else ""))


if __name__ == "__main__":
    sys.exit(main())
