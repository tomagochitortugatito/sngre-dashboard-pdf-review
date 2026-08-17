"""
Visor comparativo PDF ↔ JSON
============================

App de Streamlit para revisar, lado a lado, un reporte en PDF y las tablas
extraídas del JSON correspondiente (mismo nombre de archivo, distinta
extensión).

Ejecutar con:
    streamlit run app.py
"""

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

# --------------------------------------------------------------------------
# Configuración por defecto (ajustable desde la barra lateral)
# --------------------------------------------------------------------------
DEFAULT_JSON_DIR = os.environ.get(
    "JSON_DIR", "/home/tomagochito/Documentos/outputchatgptplus/mixed_2"
)
DEFAULT_PDF_ROOT = os.environ.get("PDF_ROOT", "/home/tomagochito/Documentos/pdfs")

st.set_page_config(page_title="Visor PDF ↔ JSON", layout="wide")


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def find_pdf_for_json(json_path: str, pdf_root: str) -> str | None:
    """Busca (recursivamente bajo pdf_root) un PDF con el mismo nombre base que el JSON."""
    target = Path(json_path).stem.lower() + ".pdf"
    root = Path(pdf_root)
    if not root.exists():
        return None
    for p in root.rglob("*.pdf"):
        if p.name.lower() == target:
            return str(p)
    return None


@st.cache_data(show_spinner=False)
def load_json_file(path_or_bytes, is_bytes: bool = False):
    if is_bytes:
        return json.loads(path_or_bytes.decode("utf-8"))
    with open(path_or_bytes, "r", encoding="utf-8") as f:
        return json.load(f)


def render_pdf(pdf_path: str, height: int = 900):
    """Muestra un PDF con el visor nativo de Streamlit (st.pdf), que sirve el
    archivo en vez de embeberlo como base64 en el HTML (esto último fallaba
    en silencio con reportes de varios MB por el límite de payload de
    st.markdown/postMessage)."""
    try:
        with open(pdf_path, "rb") as f:
            data = f.read()
    except OSError as e:
        st.error(f"No se pudo abrir el PDF: {e}")
        return
    st.pdf(data, height=height)
    st.download_button(
        "Descargar PDF",
        data=data,
        file_name=Path(pdf_path).name,
        mime="application/pdf",
        use_container_width=True,
    )


def narrative_or_value(v):
    """Reduce dicts tipo {'original_narrative': '...'} a su texto; deja lo demás igual."""
    if isinstance(v, dict):
        if "original_narrative" in v and len(v) == 1:
            return v["original_narrative"]
        # dict con varias claves: intenta narrativa + resto compactado
        if "original_narrative" in v:
            extra = {k: val for k, val in v.items() if k != "original_narrative"}
            return v["original_narrative"] + (f"\n[{extra}]" if extra else "")
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    return v


def render_columns_rows_table(name: str, table: dict, table_registry: list):
    """Renderiza una tabla {columns:[...], rows:[[...]]} y la registra para el panel de revisión."""
    cols = table.get("columns", [])
    rows = table.get("rows", [])
    st.markdown(f"**{name}** &nbsp;·&nbsp; {len(rows)} filas")
    if rows:
        df = pd.DataFrame(rows, columns=cols)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.caption("_(sin filas)_")
    table_registry.append(name)


def render_events_as_table(zone_id: str, events: list, table_registry: list):
    """Aplana la lista de eventos de una zona (section_2) en una tabla comparable."""
    name = f"Adverse Event Monitoring · Zona {zone_id}"
    records = []
    for ev in events:
        loc = ev.get("location", {}) if isinstance(ev.get("location"), dict) else {}
        records.append(
            {
                "event_type": ev.get("event_type"),
                "event_start_date": ev.get("event_start_date"),
                "province": loc.get("province"),
                "canton": loc.get("canton"),
                "parish": loc.get("parish"),
                "sectors": "; ".join(loc.get("sectors", []) or []),
                "background": narrative_or_value(ev.get("background")),
                "current_situation": narrative_or_value(ev.get("current_situation")),
                "impacts": narrative_or_value(ev.get("impacts")),
                "response_actions": narrative_or_value(ev.get("response_actions")),
                "information_sources": narrative_or_value(ev.get("information_sources")),
            }
        )
    st.markdown(f"**{name}** &nbsp;·&nbsp; {len(records)} eventos")
    if records:
        df = pd.DataFrame(records)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.caption("_(sin eventos)_")
    table_registry.append(name)


def render_tables_block(tables: dict, table_registry: list):
    """Recorre el dict 'tables' de una sección; algunas entradas son tablas directas,
    otras (p. ej. water_body_overflow) agrupan varias sub-tablas."""
    for tname, tval in tables.items():
        if isinstance(tval, dict) and "columns" in tval and "rows" in tval:
            render_columns_rows_table(tname, tval, table_registry)
        elif isinstance(tval, dict) and any(
            isinstance(v, dict) and "columns" in v and "rows" in v for v in tval.values()
        ):
            # grupo de sub-tablas, p. ej. water_body_overflow
            st.markdown(f"##### {tname}")
            for subname, subval in tval.items():
                if isinstance(subval, dict) and "columns" in subval:
                    render_columns_rows_table(f"{tname} · {subname}", subval, table_registry)
        elif isinstance(tval, list):
            if tval:
                st.markdown(f"**{tname}**")
                st.dataframe(pd.DataFrame(tval), use_container_width=True, hide_index=True)
                table_registry.append(tname)
            else:
                st.markdown(f"**{tname}**")
                st.caption("_(sin datos)_")
        elif isinstance(tval, dict):
            # ficha de un solo registro (p. ej. hydrometeorological_situation):
            # sin columns/rows ni sub-tablas, se aplana a una tabla de una fila.
            record = {k: narrative_or_value(v) for k, v in tval.items()}
            st.markdown(f"**{tname}**")
            st.dataframe(pd.DataFrame([record]), use_container_width=True, hide_index=True)
            table_registry.append(tname)
        st.divider()


def render_json_tables(data: dict) -> list:
    """Renderiza todo el JSON como tablas comparables y devuelve la lista de nombres de tabla."""
    table_registry = []

    meta = data.get("metadata")
    if meta:
        st.markdown("### Metadata")
        st.dataframe(pd.DataFrame([meta]), use_container_width=True, hide_index=True)
        st.divider()

    for key, section in data.items():
        if key == "metadata" or not isinstance(section, dict):
            continue
        title = section.get("section", key)
        st.markdown(f"### {title}")

        if "tables" in section and isinstance(section["tables"], dict):
            render_tables_block(section["tables"], table_registry)

        if "zones" in section and isinstance(section["zones"], dict):
            for zone_id, zone in section["zones"].items():
                events = zone.get("events", []) if isinstance(zone, dict) else []
                render_events_as_table(zone_id, events, table_registry)
                st.divider()

    return table_registry


# --------------------------------------------------------------------------
# Fuente de datos: sección superior colapsable (en vez de barra lateral) para
# no restarle ancho horizontal a la comparación PDF/tablas.
# --------------------------------------------------------------------------
st.title("Visor comparativo: PDF vs. Tablas JSON")

with st.expander("Fuente de datos", expanded=True):
    cfg1, cfg2, cfg3 = st.columns([2, 2, 1.4])
    with cfg1:
        json_dir = st.text_input("Carpeta local de JSON", value=DEFAULT_JSON_DIR)
    with cfg2:
        pdf_root = st.text_input("Carpeta raíz de PDFs", value=DEFAULT_PDF_ROOT)
    with cfg3:
        mode = st.radio("Origen del JSON", ["Carpeta local", "Subir archivo"])

    json_data = None
    json_source_path = None  # ruta a mostrar/loguear
    uploaded_file = None

    if mode == "Carpeta local":
        dirp = Path(json_dir)
        if dirp.exists() and dirp.is_dir():
            json_files = sorted(p.name for p in dirp.glob("*.json"))
            if json_files:
                chosen = st.selectbox(
                    f"Archivo JSON ({len(json_files)} encontrados)", json_files
                )
                json_source_path = str(dirp / chosen)
                json_data = load_json_file(json_source_path)
            else:
                st.warning("No hay archivos .json en esa carpeta.")
        else:
            st.error("La carpeta indicada no existe.")
    else:
        uploaded_file = st.file_uploader("Sube un archivo JSON", type=["json"])
        if uploaded_file is not None:
            json_source_path = uploaded_file.name  # solo nombre, no hay ruta local real
            json_data = load_json_file(uploaded_file.getvalue(), is_bytes=True)

if json_data is None:
    st.info("Selecciona o sube un archivo JSON arriba para comenzar.")
    st.stop()

# localizar PDF correspondiente
pdf_path = find_pdf_for_json(json_source_path, pdf_root)

# --------------------------------------------------------------------------
# Cuerpo principal: dos columnas (PDF | Tablas). El PDF recibe más ancho
# relativo porque el visor nativo necesita espacio horizontal para leerse bien.
# Ambas columnas tienen su propio scroll interno (misma altura fija) para
# poder bajar el PDF y las tablas de forma independiente.
# --------------------------------------------------------------------------
PANEL_HEIGHT = 1100

col_pdf, col_tables = st.columns([1.3, 1], gap="medium")

with col_pdf:
    st.subheader("PDF original")
    st.caption(json_source_path)
    if pdf_path:
        st.caption(f"{pdf_path}")
        render_pdf(pdf_path, height=PANEL_HEIGHT)
    else:
        st.warning(
            "No se encontró un PDF con el mismo nombre en la carpeta configurada. "
            "Puedes subirlo manualmente."
        )
        manual_pdf = st.file_uploader("Subir PDF manualmente", type=["pdf"], key="manual_pdf")
        if manual_pdf is not None:
            tmp_path = Path(__file__).parent / f"_tmp_{manual_pdf.name}"
            tmp_path.write_bytes(manual_pdf.getvalue())
            pdf_path = str(tmp_path)
            render_pdf(pdf_path, height=PANEL_HEIGHT)

with col_tables:
    st.subheader("Tablas del JSON")
    # container con altura fija: el scroll de las tablas queda contenido aquí
    # y no arrastra a la columna del PDF (ni viceversa).
    with st.container(height=PANEL_HEIGHT, border=True):
        render_json_tables(json_data)
