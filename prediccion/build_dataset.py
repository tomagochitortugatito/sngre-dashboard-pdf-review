"""
Pipeline de features para el modelo predictivo sobre la Sección 2
(Monitoreo de Eventos Adversos) de los reportes SNGR.

Parte de `dashboard/data/eventos_raw.csv` (TODAS las apariciones de cada
evento en cada boletín, ya generado por `dashboard/build_dataset.py` — no
volvemos a parsear los 2865 JSON aquí, para no duplicar esa lógica de
limpieza) y construye, en tres etapas, un dataset a nivel de "evento único"
con features conocidas al inicio del evento y un objetivo a predecir:

  1. Dedup EXACTA (igual que dashboard): agrupa apariciones por
     (zone, event_type, event_start_date, location_key). Cada grupo es un
     "evento exacto"; nos quedamos con su primera y su última/pico aparición.
  2. Dedup DIFUSA: algunos eventos exactos son en realidad el mismo evento
     real narrado con variantes de texto en location_key o con el
     event_start_date desplazado un par de días entre boletines. Se agrupan
     (union-find) los eventos exactos cuando comparten zona+tipo, sus fechas
     de inicio están a <= 5 días, y la similitud de texto (difflib) de sus
     location_key es >= 0.85. Cada grupo resultante es un "clúster" = evento
     único final.
  3. Extracción de impactos: `impacts` es texto libre ("-3 viviendas
     afectadas.-1 familia damnificada (4 personas)..."). Se extraen con
     regex conteos numéricos por categoría (viviendas, familias, personas,
     hectáreas, puentes, metros de vía) para cada aparición, y se combinan
     en un índice compuesto `impact_score` (ver IMPACT_WEIGHTS). Se calcula
     tanto en el primer boletín del clúster (features "conocidas al inicio")
     como el máximo alcanzado en todo su ciclo de vida (posible objetivo).

Salida: prediccion/data/eventos_features.parquet (uno por clúster/evento
único) + prediccion/data/pipeline_stats.json (contadores para la sección de
Arquitectura de la app).
"""
import json
import os
import re
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

RAW_CSV = Path(os.environ.get(
    "EVENTOS_RAW_CSV", Path(__file__).parent.parent / "dashboard" / "data" / "eventos_raw.csv"
))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", Path(__file__).parent / "data"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_FEATURES = OUTPUT_DIR / "eventos_features.parquet"
OUT_STATS = OUTPUT_DIR / "pipeline_stats.json"

KEY_COLS = ["zone", "event_type", "event_start_date", "location_key"]

# Fechas cercanas + texto de location parecido -> se considera el mismo
# evento real narrado con variantes.
FUZZY_MAX_DAYS = 5
FUZZY_MIN_RATIO = 0.85

# ---------------------------------------------------------------------------
# Extracción de cifras de impacto desde texto libre (español, SNGR)
# ---------------------------------------------------------------------------
NUM = r"(\d+(?:[.,]\d+)?)"

IMPACT_PATTERNS = [
    ("viviendas_destruidas", rf"{NUM}\s*viviend\w*\s*destruid\w*"),
    ("viviendas_afectadas", rf"{NUM}\s*viviend\w*\s*afectad\w*"),
    ("familias_damnificadas", rf"{NUM}\s*famil\w*\s*damnificad\w*"),
    ("familias_afectadas", rf"{NUM}\s*famil\w*\s*afectad\w*"),
    ("familias_evacuadas", rf"{NUM}\s*famil\w*\s*evacuad\w*"),
    ("personas_afectadas", rf"{NUM}\s*person\w*\s*afectad\w*"),
    ("personas_damnificadas", rf"{NUM}\s*person\w*\s*damnificad\w*"),
    ("personas_evacuadas", rf"{NUM}\s*person\w*\s*evacuad\w*"),
    ("personas_fallecidas", rf"{NUM}\s*person\w*\s*fallecid\w*"),
    ("hectareas_afectadas", rf"{NUM}\s*(?:ha\b|hect[aá]reas?)"),
    ("puentes_afectados", rf"{NUM}\s*puentes?\s*(?:afectad\w*|destruid\w*|colapsad\w*)"),
    ("metros_via_afectada", rf"{NUM}\s*metros?\s*(?:lineal\w*\s*)?(?:de\s*)?v[ií]a\s*afectad\w*"),
]
IMPACT_PATTERNS = [(name, re.compile(pat, re.IGNORECASE)) for name, pat in IMPACT_PATTERNS]
IMPACT_COLS = [name for name, _ in IMPACT_PATTERNS]

# Peso relativo de cada métrica en el índice compuesto `impact_score`. Es un
# índice ILUSTRATIVO (no una métrica oficial SNGR): pondera más lo
# irreversible (fallecidos, viviendas/puentes destruidos) que lo reversible
# (personas evacuadas, metros de vía).
IMPACT_WEIGHTS = {
    "viviendas_destruidas": 5.0,
    "viviendas_afectadas": 1.5,
    "familias_damnificadas": 4.0,
    "familias_afectadas": 1.5,
    "familias_evacuadas": 2.0,
    "personas_afectadas": 0.5,
    "personas_damnificadas": 1.0,
    "personas_evacuadas": 0.7,
    "personas_fallecidas": 10.0,
    "hectareas_afectadas": 0.3,
    "puentes_afectados": 3.0,
    "metros_via_afectada": 0.01,
}


# "national"/"nacional" son la misma zona escrita distinto en el texto fuente
# — se unifican en una sola categoría.
ZONE_FIXES = {"national": "Nacional", "nacional": "Nacional"}


def clean_zone(z):
    z = str(z).strip()
    return ZONE_FIXES.get(z.lower(), z)


def _to_float(s):
    s = s.strip()
    if "," in s and "." in s:
        # el último separador es el decimal; el otro, miles
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # "1,5" (decimal) vs "1,234" (miles) — heurística por longitud
        frac = s.split(",")[-1]
        s = s.replace(",", "." if len(frac) <= 2 else "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def extract_impacts(text):
    """Devuelve {métrica: suma_de_apariciones} para un texto de `impacts`."""
    out = {name: 0.0 for name in IMPACT_COLS}
    if not text or not isinstance(text, str):
        return out
    for name, rx in IMPACT_PATTERNS:
        for m in rx.finditer(text):
            out[name] += _to_float(m.group(1))
    return out


def impact_score(row_like):
    return sum(row_like.get(k, 0.0) * w for k, w in IMPACT_WEIGHTS.items())


# ---------------------------------------------------------------------------
# Flags de contenido narrativo (background) — features de texto simples,
# sin NLP pesado: presencia de palabras clave relevantes.
# ---------------------------------------------------------------------------
KEYWORD_FLAGS = {
    "bg_menciona_declaratoria": r"declarat\w*|resoluci[oó]n\s*sgr|estado\s*de\s*excepci",
    "bg_menciona_recurrencia": r"reincid\w*|recurrent\w*|nuevamente|de\s*forma\s*reiterada|desde\s*(?:el\s*)?20\d{2}",
    "bg_menciona_rio_quebrada": r"\br[ií]o\b|quebrada",
    "bg_menciona_lluvias": r"lluvias?\s*intensas?|precipitac",
    "bg_menciona_talud_erosion": r"talud|erosi[oó]n|socavamiento",
}
KEYWORD_FLAGS = {k: re.compile(v, re.IGNORECASE) for k, v in KEYWORD_FLAGS.items()}


def text_flags(text):
    if not text or not isinstance(text, str):
        return {k: False for k in KEYWORD_FLAGS}
    return {k: bool(rx.search(text)) for k, rx in KEYWORD_FLAGS.items()}


# ---------------------------------------------------------------------------
# Union-Find para la fuzzy-dedup
# ---------------------------------------------------------------------------
class UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def main():
    if not RAW_CSV.exists():
        raise SystemExit(
            f"No se encontró {RAW_CSV}. Ejecuta primero dashboard/build_dataset.py "
            "(genera eventos_raw.csv a partir de los JSON fuente)."
        )

    print(f"Leyendo {RAW_CSV} ...")
    usecols = ["source_file", "report_last_update", "zone", "event_type", "province",
               "canton", "parish", "location_key", "event_start_date", "year", "month",
               "background", "impacts"]
    df = pd.read_csv(RAW_CSV, usecols=usecols)
    n_raw = len(df)
    print(f"Apariciones crudas: {n_raw}")

    df["report_last_update"] = pd.to_datetime(df["report_last_update"], errors="coerce")
    df["event_start_date"] = pd.to_datetime(df["event_start_date"], errors="coerce", format="mixed")
    df = df.dropna(subset=["zone", "event_type", "event_start_date", "location_key"])
    df["zone"] = df["zone"].astype(str).apply(clean_zone)

    # Cifras de impacto por aparición
    impacts_expanded = df["impacts"].apply(extract_impacts).apply(pd.Series)
    df = pd.concat([df, impacts_expanded], axis=1)
    df["impact_score_row"] = df[IMPACT_COLS].mul(pd.Series(IMPACT_WEIGHTS)).sum(axis=1)

    # -----------------------------------------------------------------
    # Etapa 1: dedup EXACTA -> un registro por evento exacto, con su
    # primer boletín (features "conocidas al inicio") y el pico de
    # impacto alcanzado en todo su ciclo de vida.
    # -----------------------------------------------------------------
    df = df.sort_values("report_last_update")
    exact_rows = []
    for key, g in df.groupby(KEY_COLS, dropna=False, sort=False):
        zone, event_type, event_start_date, location_key = key
        first = g.iloc[0]
        exact_rows.append({
            "zone": zone,
            "event_type": event_type,
            "event_start_date": event_start_date,
            "location_key": location_key,
            "province": g["province"].mode().iat[0] if not g["province"].mode().empty else None,
            "canton": g["canton"].mode().iat[0] if not g["canton"].mode().empty else None,
            "parish": g["parish"].mode().iat[0] if not g["parish"].mode().empty else None,
            "background_first": first["background"],
            "n_snapshots": len(g),
            "initial_impact_score": first["impact_score_row"],
            "peak_impact_score": g["impact_score_row"].max(),
            **{f"initial_{c}": first[c] for c in IMPACT_COLS},
            **{f"peak_{c}": g[c].max() for c in IMPACT_COLS},
        })
    exact_df = pd.DataFrame(exact_rows)
    n_exact = len(exact_df)
    print(f"Eventos exactos (zone+tipo+fecha+location idénticos): {n_exact}")

    # -----------------------------------------------------------------
    # Etapa 2: dedup DIFUSA entre eventos exactos — bloqueo por
    # (zone, event_type, año) y unión si fechas <=5 días y similitud de
    # location_key >= 0.85.
    # -----------------------------------------------------------------
    exact_df["_year"] = exact_df["event_start_date"].dt.year
    uf = UnionFind(n_exact)
    n_merges = 0
    for _, idx in exact_df.groupby(["zone", "event_type", "_year"], sort=False).groups.items():
        idx = list(idx)
        for i in range(len(idx)):
            ri = idx[i]
            for j in range(i + 1, len(idx)):
                rj = idx[j]
                dt_i = exact_df.at[ri, "event_start_date"]
                dt_j = exact_df.at[rj, "event_start_date"]
                if abs((dt_i - dt_j).days) > FUZZY_MAX_DAYS:
                    continue
                loc_i = exact_df.at[ri, "location_key"] or ""
                loc_j = exact_df.at[rj, "location_key"] or ""
                ratio = SequenceMatcher(None, loc_i, loc_j).ratio()
                if ratio >= FUZZY_MIN_RATIO:
                    if uf.find(ri) != uf.find(rj):
                        n_merges += 1
                    uf.union(ri, rj)
    exact_df["cluster_root"] = [uf.find(i) for i in range(n_exact)]
    n_clusters = exact_df["cluster_root"].nunique()
    print(f"Fusiones difusas aplicadas: {n_merges}")
    print(f"Eventos únicos tras dedup difusa (clústeres): {n_clusters}")

    # -----------------------------------------------------------------
    # Agregación a nivel de clúster = evento único final
    # -----------------------------------------------------------------
    exact_df = exact_df.sort_values("event_start_date")
    cluster_rows = []
    for root, g in exact_df.groupby("cluster_root", sort=False):
        g = g.sort_values("event_start_date")
        first = g.iloc[0]
        flags = text_flags(first["background_first"])
        row = {
            "event_type": first["event_type"],
            "zone": first["zone"],
            "province": first["province"] or "No especificado",
            "canton": first["canton"],
            "parish": first["parish"],
            "location_key": first["location_key"],
            "event_start_date": first["event_start_date"],
            "month": int(first["event_start_date"].month) if pd.notna(first["event_start_date"]) else None,
            "n_exact_variants": len(g),
            "n_snapshots_total": int(g["n_snapshots"].sum()),
            "background_len": len(first["background_first"]) if isinstance(first["background_first"], str) else 0,
            "initial_impact_score": float(first["initial_impact_score"]),
            "peak_impact_score": float(g["peak_impact_score"].max()),
            **flags,
            **{f"initial_{c}": float(first[f"initial_{c}"]) for c in IMPACT_COLS},
        }
        cluster_rows.append(row)
    feat_df = pd.DataFrame(cluster_rows)

    # Recurrencia previa: cuántos eventos del mismo tipo ya habían ocurrido
    # antes (misma fecha de corte) en el mismo location_key.
    feat_df = feat_df.sort_values("event_start_date").reset_index(drop=True)
    feat_df["recurrence_prior"] = (
        feat_df.groupby(["location_key", "event_type"]).cumcount()
    )

    # Objetivo de clasificación: ¿el impacto empeoró respecto de lo
    # reportado en el primer boletín? (margen 5% para evitar ruido de
    # redondeo cuando initial == peak)
    feat_df["escalamiento"] = (
        feat_df["peak_impact_score"] > feat_df["initial_impact_score"] * 1.05
    ).astype(int)

    feat_df.to_parquet(OUT_FEATURES, index=False)
    print(f"Guardado: {OUT_FEATURES} ({len(feat_df)} eventos únicos)")

    stats = {
        "n_raw_apariciones": int(n_raw),
        "n_eventos_exactos": int(n_exact),
        "n_fusiones_difusas": int(n_merges),
        "n_eventos_unicos": int(n_clusters),
        "tasa_escalamiento": round(float(feat_df["escalamiento"].mean()), 4),
    }
    with open(OUT_STATS, "w", encoding="utf-8") as fh:
        json.dump(stats, fh, indent=2, ensure_ascii=False)
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
