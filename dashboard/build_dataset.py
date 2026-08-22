"""
Extrae y deduplica los eventos de la Sección 2 (Adverse Event Monitoring / Monitoreo
de Eventos Adversos) de todos los reportes JSON del SNGR.

Por qué deduplicar
-------------------
Cada reporte cubre una ventana corta (ej. 2024/03/11 21:00 -> 2024/03/12 09:00) y
un mismo evento (ej. una inundación) aparece repetido en decenas de reportes
consecutivos mientras sigue activo, solo actualizando su "current_situation" /
"impacts". Si contáramos cada aparición como un evento nuevo, sobreestimaríamos
la frecuencia real ~19x (22 477 filas crudas vs ~1 200 eventos únicos).

Se considera que dos filas son EL MISMO evento si coinciden en:
  (zone, event_type, event_start_date, location_key)

- zone: la zona SNGR del propio JSON (campo estructurado, no inferido) — es
  determinante: dos eventos iguales en zonas distintas nunca son el mismo evento.
- location_key: location.original_narrative saneado (ver sanitize_location),
  como texto completo — NO se separa en columnas de provincia/cantón/parroquia/
  sector para la comparación (esas columnas sí se guardan aparte en el parquet
  de salida, pero no forman parte de la clave de deduplicación).
- event_start_date es la fecha real de inicio del evento (declarada dentro del
  propio evento), NO la fecha/hora del reporte (metadata.start/end/last_update),
  que solo indica cuándo se emitió ese boletín concreto.

(Ver el comentario junto a `key_cols` más abajo para el detalle exacto.)

Para cada evento único nos quedamos con la ÚLTIMA aparición (mayor
metadata.last_update), asumiendo que es la actualización más reciente/completa.
"""
import json
import glob
import os
import re
from datetime import datetime
from pathlib import Path

import unicodedata

import pandas as pd

# Carpeta con los 2865 JSON fuente y carpeta de salida para los .parquet/.csv
# generados; ambas configurables por variable de entorno para no depender de
# rutas absolutas de una máquina en particular (relevante porque esta carpeta
# se comparte). Por defecto: "../pdf_review/data/json" (los mismos JSON que usa
# el visor PDF↔JSON) y "data/" junto a este script.
DATA_DIR = Path(os.environ.get(
    "SOURCE_JSON_DIR", Path(__file__).parent.parent / "pdf_review" / "data" / "json"
))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", Path(__file__).parent / "data"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CANONICAL_PROVINCES = [
    "Azuay", "Bolívar", "Cañar", "Carchi", "Chimborazo", "Cotopaxi", "El Oro",
    "Esmeraldas", "Galápagos", "Guayas", "Imbabura", "Loja", "Los Ríos",
    "Manabí", "Morona Santiago", "Napo", "Orellana", "Pastaza", "Pichincha",
    "Santa Elena", "Santo Domingo de los Tsáchilas", "Sucumbíos", "Tungurahua",
    "Zamora Chinchipe",
]

# Correcciones manuales para variantes/erratas vistas en los datos que la
# búsqueda por substring no resuelve bien (typos, truncamientos, nombres de
# cantón usados como si fueran provincia).
MANUAL_PROVINCE_FIXES = {
    "manabì": "Manabí",
    "bolivar": "Bolívar",
    "olívar": "Bolívar",  # "Bolívar" truncado
    "los rios": "Los Ríos",
    "galapagos": "Galápagos",
    "zamora": "Zamora Chinchipe",
    "daule": "Guayas",  # Daule es cantón de Guayas
}


def _strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def clean_province(raw):
    """Normaliza el campo province, que en ~3% de filas viene contaminado con
    texto de encabezado del reporte, nombres de zona SNGR, erratas de tildes,
    o nombres de cantón. Devuelve un nombre canónico o 'No especificado'."""
    if not raw or not isinstance(raw, str):
        return "No especificado"
    s = raw.strip()
    if not s:
        return "No especificado"

    key = _strip_accents(s).lower()
    if key in MANUAL_PROVINCE_FIXES:
        return MANUAL_PROVINCE_FIXES[key]

    # Buscamos el nombre de provincia canónico más a la derecha en el texto
    # (en las cadenas contaminadas por encabezados, la provincia real queda
    # al final: "...No. 0722 Orellana-Napo" -> Orellana).
    best_pos, best_prov = -1, None
    for prov in CANONICAL_PROVINCES:
        prov_key = _strip_accents(prov).lower()
        pos = _strip_accents(s).lower().rfind(prov_key)
        if pos > best_pos:
            best_pos, best_prov = pos, prov
    if best_prov is not None:
        return best_prov

    return "No especificado"
OUT_PARQUET = OUTPUT_DIR / "eventos_dedup.parquet"
OUT_CSV = OUTPUT_DIR / "eventos_dedup.csv"
OUT_RAW_CSV = OUTPUT_DIR / "eventos_raw.csv"

OUT_VOLCANOES = OUTPUT_DIR / "volcanes.parquet"
OUT_ROADS = OUTPUT_DIR / "vias.parquet"
OUT_FIRES = OUTPUT_DIR / "incendios_activos.parquet"
OUT_WATER = OUTPUT_DIR / "cuerpos_agua.parquet"
OUT_SEISMIC = OUTPUT_DIR / "sismos.parquet"
OUT_HYDROMET = OUTPUT_DIR / "alertas_hidromet.parquet"

# ---------------------------------------------------------------------------
# Limpieza — section_1 (volcanes) y section_3 (vías)
# ---------------------------------------------------------------------------
CANONICAL_VOLCANOES = [
    "Volcán Reventador", "Volcán Chiles-Cerro Negro", "Volcán Cotopaxi",
    "Volcán Sierra Negra", "Volcán Sangay", "Volcán Guagua Pichincha",
    "Volcán La Fernandina", "Volcán Cayambe", "Volcán Tungurahua",
    "Volcán Wolf", "Volcán Cerro Azul", "Volcán Pululahua",
]

ALERT_LEVELS = ["NARANJA", "AMARILLA", "BLANCA", "ROJA", "Sin alerta declarada"]
ASSESSMENT_LEVELS = ["VERDE", "AMARILLO", "ROJO"]


def clean_volcano(raw):
    """El nombre de volcán viene a veces con narrativa completa pegada
    (texto de 'current_situation' filtrado al campo equivocado por el OCR/
    parser de origen). Igual que con provincia, buscamos el nombre canónico
    conocido más largo/temprano dentro del texto."""
    if not raw or not isinstance(raw, str):
        return None
    key = _strip_accents(raw).lower()
    for volc in CANONICAL_VOLCANOES:
        if _strip_accents(volc).lower() in key:
            return volc
    return None


# "national"/"nacional" son la misma zona escrita distinto en el texto
# fuente — se unifican en una sola categoría. Zona vacía/en blanco -> None
# (se descarta más abajo junto con el resto de filas sin zona reconocible).
ZONE_FIXES = {"national": "Nacional", "nacional": "Nacional"}


def clean_zone(raw):
    if not raw or not isinstance(raw, str):
        return None
    z = raw.strip()
    if not z:
        return None
    return ZONE_FIXES.get(z.lower(), z)


def sanitize_location(raw):
    """Normaliza location.original_narrative para poder compararlo por
    igualdad exacta entre boletines, SIN separarlo en columnas (provincia/
    cantón/parroquia/sector quedan juntos, tal como los redactó el reporte):
      - quita el prefijo de zona SNGR ('Zona 9/', 'ZONA 7 /'...) — es
        redundante para la comparación porque la zona ya se usa aparte como
        columna propia ('zone') en la clave de deduplicación.
      - normaliza espacios alrededor de cada '/'.
      - colapsa espacios múltiples.
      - quita el punto final.
    No se intenta extraer provincia/cantón/parroquia de aquí: eso sigue
    viniendo de los campos ya estructurados location.province/canton/parish."""
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    s = re.sub(r"(?i)^\s*zona\s*\d+\s*/\s*", "", s)
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"\s+", " ", s)
    s = s.rstrip(".").strip()
    return s or None


def clean_level(raw, levels):
    """Los niveles de alerta/valoración vienen con texto extra pegado
    (dirección del viento, notas). Nos quedamos con el nivel conocido si
    aparece al inicio del texto; si no hay coincidencia, None."""
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    for lvl in levels:
        if s.upper().startswith(lvl.upper()):
            return lvl
    return None


ADVERSE_EVENT_MAP = [
    ("deslizam", "Deslizamiento"),
    ("socavam", "Socavamiento"),
    ("scavamiento", "Socavamiento"),
    ("hundim", "Hundimiento"),
    ("inundac", "Inundación"),
    ("inindac", "Inundación"),
    ("colaps", "Colapso estructural"),
    ("aluvion", "Aluvión"),
    ("subsidenc", "Subsidencia"),
    ("erosion", "Erosión hídrica"),
    ("oleaje", "Oleaje"),
    ("lluvias intensas", "Lluvias intensas"),
]


def clean_adverse_event(raw):
    """Tipo de evento causante del cierre de vía; texto crudo trae erratas
    ('DESLIZAMIENO'), encabezados de tabla mal cortados, o varias palabras
    pegadas. Buscamos la primera coincidencia de palabra clave conocida."""
    if not raw or not isinstance(raw, str):
        return "No especificado"
    key = _strip_accents(raw).lower()
    for kw, canonical in ADVERSE_EVENT_MAP:
        if kw in key:
            return canonical
    return "No especificado"


ROAD_TABLE_SPECS = [
    ("first_order_closed", "Primer orden", "Cerrada"),
    ("first_order_partially_enabled", "Primer orden", "Parcialmente habilitada"),
    ("second_order_closed", "Segundo orden", "Cerrada"),
    ("second_order_partially_enabled", "Segundo orden", "Parcialmente habilitada"),
    ("third_order_closed", "Tercer orden", "Cerrada"),
    ("third_order_partially_enabled", "Tercer orden", "Parcialmente habilitada"),
]


def parse_dt(s):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def parse_event_start(s):
    """event_start_date llega en formatos variados: 'YYYY/MM/DD', 'YYYY/MM',
    a veces con texto extra. Devolvemos (fecha_normalizada_str, year, month, date_obj)."""
    if not s or not isinstance(s, str):
        return None, None, None, None
    s = s.strip()
    m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            dt = datetime(y, mo, d)
            return dt.strftime("%Y-%m-%d"), y, mo, dt
        except ValueError:
            return s, y, mo, None
    m = re.match(r"^(\d{4})/(\d{1,2})$", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        return f"{y:04d}-{mo:02d}", y, mo, None
    m = re.match(r"^(\d{4})$", s)
    if m:
        y = int(m.group(1))
        return s, y, None, None
    return s, None, None, None


def parse_seismic_datetime(s):
    """local_datetime de seismic_hazard viene en varios formatos según el
    reporte: 'DD/MM/YYYY HH:MM' (convención local), 'YYYY-MM-DD HH:MM:SS',
    o a veces solo la fecha sin hora. Formatos truncados/malformados
    ('2023-09-14 04:', '16-06-2023 - 02:0') se descartan (fracción pequeña)."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def is_placeholder(s):
    """Celdas vacías representadas como '--', '---', '- -', espacios, etc."""
    return s is None or re.fullmatch(r"[\s\-]*", str(s).strip()) is not None


def parse_leading_number(s):
    """Extrae un número de un texto: depth viene como '67.0', '38.0 Km' o
    '6Km'; magnitude a veces trae la escala pegada ('3.5 Mlv', '4.5MLv') o,
    en filas con corrupción de columnas vecinas, un dígito suelto colado
    ('8 3.6', donde el '8' es un resto de la hora). Se prioriza un número
    decimal (X.Y) sobre un entero suelto, porque magnitud/profundidad casi
    siempre vienen con decimales y el ruido colado suele ser un entero."""
    if s is None:
        return None
    decimals = re.findall(r"\d+\.\d+", str(s))
    if decimals:
        return float(decimals[0])
    m = re.search(r"\d+", str(s))
    return float(m.group()) if m else None


def parse_magnitude(s):
    """La magnitud reportada siempre trae un decimal en la fuente (3.5, 4.2,
    ...); un entero suelto sin decimal ('6', '8', '53') es en la práctica
    ruido de OCR (resto de otra columna), no una lectura real — se descarta
    en vez de mostrarlo como si fuera un sismo M6+."""
    if s is None:
        return None
    decimals = re.findall(r"\d+\.\d+", str(s))
    if not decimals:
        return None
    val = float(decimals[0])
    return val if 0 < val <= 10 else None


def clean_felt_by_population(s):
    """felt_by_population es casi siempre 'NO'/'SI'/'SI LEVE', pero a veces
    trae texto de otra columna filtrado (nombres de cantón). Solo clasificamos
    lo reconocible; el resto queda como 'No especificado' (no se descarta la fila)."""
    if not s or not isinstance(s, str):
        return "No especificado"
    key = _strip_accents(s.strip()).lower()
    if key.startswith("si"):
        return "Sí"
    if key.startswith("no"):
        return "No"
    return "No especificado"


def extract_section1_section3(d, fp, report_name, last_update,
                               volc_rows, fire_rows, water_rows, road_rows,
                               seismic_rows, hydromet_rows):
    """Section 1 (Threat Monitoring) y Section 3 (Road Status) son snapshots
    por reporte, no 'eventos' con fecha de inicio propia salvo excepciones
    puntuales (incendios, vías sí traen event_date/start_date)."""
    s1 = d.get("section_1", {}).get("tables", {}) or {}
    s3 = d.get("section_3", {}).get("tables", {}) or {}

    # --- Volcanes ---------------------------------------------------------
    vh = s1.get("volcanic_hazard", {}) or {}
    for row in vh.get("rows", []):
        if len(row) < 4:
            continue
        location, alert_raw, situation, assessment_raw = row[0], row[1], row[2], row[3]
        volcano = clean_volcano(location)
        if volcano is None:
            continue
        volc_rows.append({
            "source_file": Path(fp).name,
            "report_name": report_name,
            "report_last_update": last_update,
            "volcano": volcano,
            "location_raw": location,
            "alert_level": clean_level(alert_raw, ALERT_LEVELS),
            "assessment": clean_level(assessment_raw, ASSESSMENT_LEVELS),
            "current_situation": situation,
        })

    # --- Incendios forestales activos --------------------------------------
    fires = s1.get("forest_fires", {}).get("active_forest_fires", {}) or {}
    for row in fires.get("rows", []):
        if len(row) < 6:
            continue
        province, canton, parish, sector, area_ha, start_raw = row[:6]
        start_norm, year, month, start_dt = parse_event_start(start_raw)
        fire_rows.append({
            "source_file": Path(fp).name,
            "report_last_update": last_update,
            "province": clean_province(province),
            "canton": canton,
            "parish": parish,
            "sector": sector,
            "affected_area_ha": pd.to_numeric(area_ha, errors="coerce"),
            "start_date": start_norm,
            "year": year,
            "month": month,
        })

    # --- Cuerpos de agua desbordados / creciendo ---------------------------
    wbo = s1.get("water_body_overflow", {}) or {}
    for subtype_key, status in [("overflowed_water_bodies", "Desbordado"),
                                 ("water_bodies_rising_level", "Creciendo")]:
        for row in wbo.get(subtype_key, {}).get("rows", []) or []:
            if len(row) < 5:
                continue
            province, canton, parish, sector, name = row[:5]
            water_rows.append({
                "source_file": Path(fp).name,
                "report_last_update": last_update,
                "status": status,
                "province": clean_province(province),
                "canton": canton,
                "parish": parish,
                "sector": sector,
                "name": name,
            })

    # --- Sismos -------------------------------------------------------------
    sh = s1.get("seismic_hazard", {}) or {}
    for row in sh.get("rows", []):
        if len(row) < 5:
            continue
        dt_raw, magnitude, depth, near, felt = row[:5]
        if is_placeholder(dt_raw):
            continue
        event_dt = parse_seismic_datetime(str(dt_raw))
        if event_dt is None:
            continue
        seismic_rows.append({
            "source_file": Path(fp).name,
            "report_last_update": last_update,
            "event_datetime": event_dt,
            "magnitude": parse_magnitude(magnitude),
            "depth_km": parse_leading_number(depth),
            "near": near,
            "province": clean_province(str(near).split(",")[-1] if near else None),
            "felt_by_population": clean_felt_by_population(felt),
        })

    # --- Situación hidrometeorológica (alertas por lluvias, viento, etc.) --
    hm = s1.get("hydrometeorological_situation", {}) or {}
    hazard = hm.get("hazard", {}) or {}
    primary_family = hazard.get("primary_family")
    if primary_family:
        phenomena = hazard.get("phenomena") or []
        hydromet_rows.append({
            "source_file": Path(fp).name,
            "report_last_update": last_update,
            "warning_number": hm.get("warning_number"),
            "hazard_original": hazard.get("original"),
            "primary_family": primary_family,
            "phenomena": "; ".join(phenomena) if phenomena else None,
            "validity_start": hm.get("validity_start") or None,
            "validity_end": hm.get("validity_end") or None,
            "description": hm.get("description") or hm.get("original_narrative"),
        })

    # --- Vías (1º/2º/3º orden, cerradas / parcialmente habilitadas) -------
    for table_key, road_order, road_status in ROAD_TABLE_SPECS:
        tbl = s3.get(table_key, {}) or {}
        for row in tbl.get("rows", []):
            if len(row) < 8:
                continue
            province, canton, parish, road_sector, event_raw, meters, event_date_raw, alt_routes = row[:8]
            start_norm, year, month, start_dt = parse_event_start(event_date_raw)
            road_rows.append({
                "source_file": Path(fp).name,
                "report_last_update": last_update,
                "road_order": road_order,
                "road_status": road_status,
                "province": clean_province(province),
                "canton": canton,
                "parish": parish,
                "road_sector": road_sector,
                "adverse_event": clean_adverse_event(event_raw),
                "affected_linear_meters": pd.to_numeric(meters, errors="coerce"),
                "event_date": start_norm,
                "year": year,
                "month": month,
                "alternative_routes": alt_routes,
            })


def _stringify_object_cols(df):
    """Algunas columnas de texto traen floats/NaN mezclados (celdas vacías o
    con errores de OCR en la fuente) lo que rompe la escritura a parquet.
    Normalizamos a string o None."""
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(lambda v: None if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v))
    return df


def build_volcanoes(volc_rows):
    if not volc_rows:
        return pd.DataFrame()
    df = pd.DataFrame(volc_rows)
    # ~20% de las lecturas traen declared_alert_level/current_assessment vacío o
    # "--" en la fuente (cámara sin visibilidad, corte sin novedad reportada).
    # No se descartan (perderíamos la evidencia de que ese día no hubo lectura
    # válida) — se etiquetan como "Sin dato", igual que 'No especificado' en provincia.
    df["alert_level"] = df["alert_level"].fillna("Sin dato")
    df["assessment"] = df["assessment"].fillna("Sin dato")
    df = df.sort_values("report_last_update")
    # Un registro por (volcán, fecha de reporte) — nos quedamos con la última
    # lectura de ese día si un mismo reporte lo repite.
    df["report_date"] = pd.to_datetime(df["report_last_update"]).dt.normalize()
    df = df.drop_duplicates(subset=["volcano", "report_date"], keep="last")
    return _stringify_object_cols(df)


def build_fires(fire_rows):
    if not fire_rows:
        return pd.DataFrame()
    df = pd.DataFrame(fire_rows)
    usable = df.dropna(subset=["province", "start_date"]).copy()
    key_cols = ["province", "canton", "parish", "sector", "start_date"]
    usable = usable.sort_values("report_last_update")
    counts = usable.groupby(key_cols, dropna=False).size().rename("n_reportes").reset_index()
    dedup = usable.drop_duplicates(subset=key_cols, keep="last").merge(counts, on=key_cols, how="left")
    return _stringify_object_cols(dedup)


def build_water(water_rows):
    if not water_rows:
        return pd.DataFrame()
    df = pd.DataFrame(water_rows)
    df = df.dropna(subset=["province", "name"])
    df = df[df["name"].str.strip() != ""]
    key_cols = ["status", "province", "canton", "parish", "sector", "name"]
    df = df.sort_values("report_last_update")
    counts = df.groupby(key_cols, dropna=False).size().rename("n_reportes").reset_index()
    first_seen = df.groupby(key_cols, dropna=False)["report_last_update"].min().rename("first_seen").reset_index()
    dedup = df.drop_duplicates(subset=key_cols, keep="last").merge(counts, on=key_cols, how="left")
    dedup = dedup.merge(first_seen, on=key_cols, how="left")
    return _stringify_object_cols(dedup)


def build_seismic(seismic_rows):
    if not seismic_rows:
        return pd.DataFrame()
    df = pd.DataFrame(seismic_rows)
    df = df.dropna(subset=["event_datetime"])
    # Redondeamos al minuto: el mismo sismo puede venir con segundos
    # ligeramente distintos entre boletines por el formato de fuente.
    df["event_datetime"] = pd.to_datetime(df["event_datetime"]).dt.floor("min")
    key_cols = ["event_datetime", "magnitude", "near"]
    df = df.sort_values("report_last_update")
    counts = df.groupby(key_cols, dropna=False).size().rename("n_reportes").reset_index()
    dedup = df.drop_duplicates(subset=key_cols, keep="last").merge(counts, on=key_cols, how="left")
    return _stringify_object_cols(dedup)


def build_hydromet(hydromet_rows):
    if not hydromet_rows:
        return pd.DataFrame()
    df = pd.DataFrame(hydromet_rows)
    df = df.dropna(subset=["primary_family", "validity_start"])
    df = df[df["validity_start"].str.strip() != ""]
    # warning_number se reinicia cada año, por eso solo es único combinado
    # con validity_start (que sí incluye el año).
    key_cols = ["warning_number", "primary_family", "validity_start", "validity_end"]
    df = df.sort_values("report_last_update")
    counts = df.groupby(key_cols, dropna=False).size().rename("n_reportes").reset_index()
    dedup = df.drop_duplicates(subset=key_cols, keep="last").merge(counts, on=key_cols, how="left")
    return _stringify_object_cols(dedup)


def normalize_road_sector(s):
    """El texto de road_sector viene con distintos grados de corrupción de OCR
    entre un reporte y el siguiente para el MISMO tramo: código de vía cortado
    a mitad ('...Naranjal [E-'), o con texto de columnas vecinas filtrado
    dentro del corchete ('[E-582] Eve', '[E- DE 582]', '[E-58 2]'...). El
    código '[E-XXX]' es justo la parte más corrupta; la ubicación antes del
    corchete ('km 90, vía Cuenca-Molleturo-Naranjal') es la parte estable.
    Generamos una clave normalizada SOLO para agrupar esas variantes como el
    mismo tramo; el texto original más completo se conserva para mostrar."""
    if not s or not isinstance(s, str):
        return s
    key = s.split("[")[0]  # descarta el código de vía entero, ahí se concentra el ruido
    key = re.sub(r"\s+", " ", key.strip())
    key = re.sub(r"\bkm\.?\s*", "km ", key, flags=re.IGNORECASE)
    key = key.rstrip(".,;:- ").lower()
    return _strip_accents(key)


def build_roads(road_rows):
    if not road_rows:
        return pd.DataFrame()
    df = pd.DataFrame(road_rows)
    usable = df.dropna(subset=["province", "road_sector"]).copy()
    usable = usable[usable["road_sector"].str.strip() != ""]
    usable["road_sector_key"] = usable["road_sector"].apply(normalize_road_sector)

    # Clave de evento: mismo tramo (normalizado) + tipo de evento + fecha de
    # evento (si la hay). Nos quedamos con el estado (cerrada/parcial) más
    # reciente reportado.
    key_cols = ["province", "canton", "road_sector_key", "adverse_event", "event_date"]
    usable = usable.sort_values("report_last_update")
    counts = usable.groupby(key_cols, dropna=False).size().rename("n_reportes").reset_index()
    dedup = usable.drop_duplicates(subset=key_cols, keep="last").merge(counts, on=key_cols, how="left")

    # Para mostrar, preferimos dentro de cada grupo: 1) la variante cuyo código
    # de vía viene limpio ('[E-582]', sin texto de columnas vecinas colado), y
    # 2) entre esas, la más repetida (más probable que sea la correcta) y más
    # corta (menos ruido pegado).
    freq = (usable.groupby(key_cols + ["road_sector"]).size().rename("_freq").reset_index())
    freq["_clean"] = freq["road_sector"].str.contains(r"\[E-\s*\d+\s*\]\s*$", regex=True).astype(int)
    freq["_len"] = freq["road_sector"].str.len()
    # Prioridad: código limpio > más repetida > más corta. Encadenamos sorts
    # estables de menor a mayor prioridad para que la última gane los empates.
    canonical = (freq.sort_values("_len", kind="stable")
                 .sort_values("_freq", ascending=False, kind="stable")
                 .sort_values("_clean", ascending=False, kind="stable")
                 .drop_duplicates(subset=key_cols, keep="first")[key_cols + ["road_sector"]]
                 .rename(columns={"road_sector": "road_sector_display"}))
    dedup = dedup.merge(canonical, on=key_cols, how="left")
    dedup["road_sector"] = dedup["road_sector_display"]
    dedup = dedup.drop(columns=["road_sector_key", "road_sector_display"])

    return _stringify_object_cols(dedup)


def main():
    files = sorted(glob.glob(str(DATA_DIR / "*.json")))
    print(f"Archivos encontrados: {len(files)}")

    rows = []
    volc_rows, fire_rows, water_rows, road_rows = [], [], [], []
    seismic_rows, hydromet_rows = [], []
    bad_files = []
    for fp in files:
        try:
            with open(fp, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception as e:
            bad_files.append((fp, str(e)))
            continue

        meta = d.get("metadata", {}) or {}
        report_name = meta.get("report_name")
        report_start = parse_dt(meta.get("start"))
        report_end = parse_dt(meta.get("end"))
        last_update = parse_dt(meta.get("last_update")) or report_end or report_start

        s2 = d.get("section_2", {}) or {}
        zones = s2.get("zones", {}) or {}
        for zone_key, zdata in zones.items():
            events = (zdata or {}).get("events", []) or []
            for ev in events:
                loc = ev.get("location", {}) or {}
                event_type = ev.get("event_type")
                province = loc.get("province")
                canton = loc.get("canton")
                parish = loc.get("parish")
                raw_start = ev.get("event_start_date")
                start_norm, year, month, start_dt = parse_event_start(raw_start)

                sectors = loc.get("sectors") or []
                sectors_str = "; ".join(sectors) if sectors else None
                location_raw = loc.get("original_narrative")
                location_key = sanitize_location(location_raw)

                rows.append({
                    "source_file": Path(fp).name,
                    "report_name": report_name,
                    "report_last_update": last_update,
                    "zone": clean_zone(zone_key),
                    "event_type": event_type,
                    "province": province,
                    "canton": canton,
                    "parish": parish,
                    "sectors": sectors_str,
                    "location_raw": location_raw,
                    "location_key": location_key,
                    "event_start_raw": raw_start,
                    "event_start_date": start_norm,
                    "year": year,
                    "month": month,
                    "start_dt": start_dt,
                    "background": (ev.get("background") or {}).get("original_narrative"),
                    "current_situation": (ev.get("current_situation") or {}).get("original_narrative"),
                    "impacts": (ev.get("impacts") or {}).get("original_narrative"),
                    "response_actions": (ev.get("response_actions") or {}).get("original_narrative"),
                    "information_sources": (ev.get("information_sources") or {}).get("original_narrative"),
                })

        extract_section1_section3(d, fp, report_name, last_update,
                                   volc_rows, fire_rows, water_rows, road_rows,
                                   seismic_rows, hydromet_rows)

    volcanoes_df = build_volcanoes(volc_rows)
    fires_df = build_fires(fire_rows)
    water_df = build_water(water_rows)
    roads_df = build_roads(road_rows)
    seismic_df = build_seismic(seismic_rows)
    hydromet_df = build_hydromet(hydromet_rows)

    print(f"Volcanes — lecturas únicas (volcán × día de reporte): {len(volcanoes_df)}")
    print(f"Incendios activos — eventos únicos: {len(fires_df)}")
    print(f"Cuerpos de agua — reportes únicos: {len(water_df)}")
    print(f"Vías — eventos únicos: {len(roads_df)}")
    print(f"Sismos — eventos únicos: {len(seismic_df)}")
    print(f"Alertas hidrometeorológicas — eventos únicos: {len(hydromet_df)}")

    volcanoes_df.to_parquet(OUT_VOLCANOES, index=False)
    fires_df.to_parquet(OUT_FIRES, index=False)
    water_df.to_parquet(OUT_WATER, index=False)
    roads_df.to_parquet(OUT_ROADS, index=False)
    seismic_df.to_parquet(OUT_SEISMIC, index=False)
    hydromet_df.to_parquet(OUT_HYDROMET, index=False)

    # Estadísticas de "filas crudas vs. deduplicadas" para los expanders de
    # metodología en app.py — los JSON fuente no están disponibles en runtime.
    stats = {
        "vias_raw": len(road_rows),
        "vias_unicas": len(roads_df),
        "volcanes_raw": len(volc_rows),
        "volcanes_lecturas": len(volcanoes_df),
        "incendios_sec1_raw": len(fire_rows),
        "incendios_sec1_unicas": len(fires_df),
        "agua_raw": len(water_rows),
        "agua_unicas": len(water_df),
        "sismos_raw": len(seismic_rows),
        "sismos_unicos": len(seismic_df),
        "hidromet_raw": len(hydromet_rows),
        "hidromet_unicas": len(hydromet_df),
    }
    with open(OUTPUT_DIR / "pipeline_stats.json", "w", encoding="utf-8") as fh:
        json.dump(stats, fh, indent=2, ensure_ascii=False)

    if bad_files:
        print(f"Archivos con error de parseo: {len(bad_files)}")
        for fp, e in bad_files[:10]:
            print("  ", fp, e)

    raw_df = pd.DataFrame(rows)
    print(f"Filas crudas (todas las apariciones en todos los reportes): {len(raw_df)}")

    raw_df["province_raw"] = raw_df["province"]
    raw_df["province"] = raw_df["province_raw"].apply(clean_province)
    n_unspecified = (raw_df["province"] == "No especificado").sum()
    print(f"Filas con provincia no reconocible tras limpieza: {n_unspecified} "
          f"(se agrupan como 'No especificado', no se descartan)")

    raw_df.to_csv(OUT_RAW_CSV, index=False)

    # Clave de "mismo evento": zona SNGR + tipo de evento + fecha de inicio +
    # location saneada (narrativa completa de provincia/cantón/parroquia/
    # sector, SIN separar en columnas — se compara como texto). La zona es
    # un campo estructurado del propio JSON (no se infiere de la narrativa)
    # y es determinante: dos eventos del mismo tipo/fecha/lugar en zonas
    # SNGR distintas nunca son el mismo evento.
    key_cols = ["zone", "event_type", "event_start_date", "location_key"]
    usable = raw_df.dropna(subset=["event_type", "zone", "event_start_date", "location_key"]).copy()
    dropped = len(raw_df) - len(usable)
    if dropped:
        print(f"Filas descartadas por falta de zona/tipo/fecha/location: {dropped}")

    # Nos quedamos con la última actualización de cada evento único
    usable = usable.sort_values("report_last_update")
    dedup = usable.drop_duplicates(subset=key_cols, keep="last").copy()

    # Cuántas veces fue reportado cada evento (para saber cuáles estuvieron más activos)
    counts = usable.groupby(key_cols, dropna=False).size().rename("n_reportes").reset_index()
    dedup = dedup.merge(counts, on=key_cols, how="left")

    dedup = dedup.sort_values(["year", "month", "event_start_date"], na_position="last")

    print(f"Eventos únicos tras deduplicar: {len(dedup)}")
    print(dedup["event_type"].value_counts())

    dedup.to_parquet(OUT_PARQUET, index=False)
    dedup.to_csv(OUT_CSV, index=False)
    print(f"Guardado: {OUT_PARQUET} y {OUT_CSV}")


if __name__ == "__main__":
    main()
