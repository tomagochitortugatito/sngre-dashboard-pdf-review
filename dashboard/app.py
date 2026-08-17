"""
Dashboard de Monitoreo de Eventos Adversos (SNGR Ecuador)
Sección 2 de los reportes de monitoreo, deduplicada por evento único.

Ejecutar con:
    ./venv/bin/streamlit run app.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Paleta (dataviz skill) — orden categórico fijo, nunca ciclado.
# ---------------------------------------------------------------------------
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
               "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
OTHER_GRAY = "#898781"
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#184f95", "#0d366b"]
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e1e0d9"

st.set_page_config(
    page_title="Monitoreo de Eventos Adversos — SNGR",
    layout="wide",
)

# Carpeta con los .parquet/.csv generados por build_dataset.py. Por defecto
# "data/" junto a este archivo; override con la variable de entorno DATA_DIR
# (así lo usa el contenedor Docker, que monta los datos aparte del código).
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent / "data"))

DATA_PATH = DATA_DIR / "eventos_dedup.parquet"


@st.cache_data
def load_data():
    df = pd.read_parquet(DATA_PATH)
    df["year"] = df["year"].astype("Int64")
    df["month"] = df["month"].astype("Int64")
    df["event_start_date"] = pd.to_datetime(df["event_start_date"], errors="coerce", format="mixed")
    return df


@st.cache_data
def load_volcanoes():
    path = DATA_DIR / "volcanes.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce")
    return df


@st.cache_data
def load_roads():
    path = DATA_DIR / "vias.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce", format="mixed")
    df["year"] = df["year"].astype("Int64")
    return df


@st.cache_data
def load_fires():
    path = DATA_DIR / "incendios_activos.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce", format="mixed")
    df["year"] = df["year"].astype("Int64")
    return df


@st.cache_data
def load_water():
    path = DATA_DIR / "cuerpos_agua.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


@st.cache_data
def load_seismic():
    path = DATA_DIR / "sismos.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df["event_datetime"] = pd.to_datetime(df["event_datetime"], errors="coerce")
    return df


@st.cache_data
def load_hydromet():
    path = DATA_DIR / "alertas_hidromet.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df["validity_start"] = pd.to_datetime(df["validity_start"], errors="coerce", format="mixed")
    return df


def event_type_order(df):
    """Orden fijo de tipos de evento por frecuencia global, usado para asignar
    color de forma consistente en todos los gráficos (misma entidad = mismo color)."""
    return df["event_type"].value_counts().index.tolist()


def color_map_for(order):
    cmap = {}
    for i, et in enumerate(order):
        cmap[et] = CATEGORICAL[i] if i < len(CATEGORICAL) else OTHER_GRAY
    return cmap


def base_layout(fig, height=420):
    fig.update_layout(
        height=height,
        plot_bgcolor="#fcfcfb",
        paper_bgcolor="rgba(0,0,0,0)",
        font_color=TEXT_PRIMARY,
        margin=dict(l=10, r=10, t=50, b=10),
        legend_title_text="",
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


def add_stack_totals(fig, categories, totals, horizontal=False):
    """Agrega el total de cada barra apilada como texto justo encima (barras
    verticales) o a la derecha (horizontales) de la pila — no forma parte de
    ninguna traza de color, es una capa de texto aparte. También deja
    margen extra en el eje de valores para que el número no quede cortado."""
    totals = list(totals)
    if not totals:
        return
    max_total = max(totals)
    if horizontal:
        fig.add_trace(go.Scatter(
            x=totals, y=list(categories), mode="text",
            text=[f"{t:,.0f}" for t in totals],
            textposition="middle right", textfont=dict(color=TEXT_PRIMARY, size=12),
            showlegend=False, hoverinfo="skip", cliponaxis=False,
        ))
        fig.update_xaxes(range=[0, max_total * 1.18])
    else:
        fig.add_trace(go.Scatter(
            x=list(categories), y=totals, mode="text",
            text=[f"{t:,.0f}" for t in totals],
            textposition="top center", textfont=dict(color=TEXT_PRIMARY, size=12),
            showlegend=False, hoverinfo="skip", cliponaxis=False,
        ))
        fig.update_yaxes(range=[0, max_total * 1.15])


def chart_total_caption(label, total):
    st.caption(f"**Total: {total:,.0f}** {label}")


def detail_table(df, key=None):
    """Tabla exacta con los datos detrás del gráfico, colapsada por defecto —
    para los números que un segmento chico o una barra angosta no alcanzan a mostrar."""
    with st.expander("Ver el desglose exacto"):
        st.dataframe(df, width='stretch', key=key)


df_all = load_data()
TYPE_ORDER_GLOBAL = event_type_order(df_all)
CMAP = color_map_for(TYPE_ORDER_GLOBAL)

volc_all = load_volcanoes()
roads_all = load_roads()
fires_all = load_fires()
water_all = load_water()
seismic_all = load_seismic()
hydromet_all = load_hydromet()

# ---------------------------------------------------------------------------
# Sidebar — filtros
# ---------------------------------------------------------------------------
st.sidebar.title("Filtros")

years = sorted(df_all["year"].dropna().unique().tolist())
year_range = st.sidebar.select_slider(
    "Rango de años (según fecha de inicio del evento)",
    options=years,
    value=(years[0], years[-1]),
)

provinces = sorted(df_all["province"].dropna().unique().tolist())
sel_provinces = st.sidebar.multiselect("Provincia", provinces, default=[])

types = TYPE_ORDER_GLOBAL
sel_types = st.sidebar.multiselect("Tipo de evento", types, default=[])

zones = sorted([z for z in df_all["zone"].dropna().unique().tolist() if z])
sel_zones = st.sidebar.multiselect("Zona SNGR", zones, default=[])

df = df_all[(df_all["year"] >= year_range[0]) & (df_all["year"] <= year_range[1])]
if sel_provinces:
    df = df[df["province"].isin(sel_provinces)]
if sel_types:
    df = df[df["event_type"].isin(sel_types)]
if sel_zones:
    df = df[df["zone"].isin(sel_zones)]

st.sidebar.markdown("---")
st.sidebar.caption(
    f"{len(df):,} eventos únicos tras filtros, de {len(df_all):,} totales."
)

# Filtro de año/provincia aplicado también a los datasets de Sección 1 y 3
# (sus categorías propias no coinciden con "Tipo de evento" / "Zona SNGR",
# por eso esos dos filtros no les aplican).
volc = volc_all[(volc_all["report_date"].dt.year >= year_range[0]) & (volc_all["report_date"].dt.year <= year_range[1])]
roads = roads_all[(roads_all["year"] >= year_range[0]) & (roads_all["year"] <= year_range[1])]
fires = fires_all[(fires_all["year"] >= year_range[0]) & (fires_all["year"] <= year_range[1])]
water = water_all[(water_all["report_last_update"].dt.year >= year_range[0]) & (water_all["report_last_update"].dt.year <= year_range[1])]
seismic = seismic_all[(seismic_all["event_datetime"].dt.year >= year_range[0]) & (seismic_all["event_datetime"].dt.year <= year_range[1])]
hydromet = hydromet_all[(hydromet_all["validity_start"].dt.year >= year_range[0]) & (hydromet_all["validity_start"].dt.year <= year_range[1])]
if sel_provinces:
    roads = roads[roads["province"].isin(sel_provinces)]
    fires = fires[fires["province"].isin(sel_provinces)]
    water = water[water["province"].isin(sel_provinces)]
    seismic = seismic[seismic["province"].isin(sel_provinces)]

# ---------------------------------------------------------------------------
# Encabezado
# ---------------------------------------------------------------------------
st.title("Monitoreo de Eventos Adversos — SNGR Ecuador")
st.caption("Reportes de Monitoreo de Amenazas y Eventos Adversos/Peligrosos — Secciones 1, 2 y 3")

st.markdown("---")

# =============================================================================
# SECCIÓN 1 — Monitoreo de Amenazas (Threat Monitoring)
# =============================================================================
st.header("Sección 1 — Monitoreo de Amenazas")

# ---------------------------------------------------------------------------
# Volcanes
# ---------------------------------------------------------------------------
st.subheader("Volcanes: evolución de la alerta declarada y la valoración")
st.caption(
    "Cada punto es una lectura tomada de un boletín (una por volcán y día de reporte). "
    "No son 'eventos' discretos como el resto del dashboard, sino el estado declarado en el tiempo."
)

ALERT_COLOR = {"No valorado": "#d8d6cf", "BLANCA": "#cde2fb", "Sin alerta declarada": OTHER_GRAY,
               "AMARILLA": "#eda100", "NARANJA": "#eb6834", "ROJA": "#e34948"}
ALERT_ORDER = ["No valorado", "Sin alerta declarada", "BLANCA", "AMARILLA", "NARANJA", "ROJA"]
ASSESSMENT_COLOR = {"No valorado": "#d8d6cf", "AMARILLO": "#eda100", "VERDE": "#1baf7a", "ROJO": "#e34948"}
ASSESSMENT_ORDER = ["No valorado", "AMARILLO", "VERDE", "ROJO"]

# Escala numérica de severidad para el gráfico temporal por volcán: "nada"
# (sin dato/sin alerta/blanca) = 0, subiendo hasta el nivel más grave.
ALERT_SCORE = {"No valorado": 0, "Sin alerta declarada": 0, "BLANCA": 0,
               "AMARILLA": 1, "NARANJA": 2, "ROJA": 3}
ALERT_SCORE_LABELS = {0: "Ninguna / sin dato", 1: "AMARILLA", 2: "NARANJA", 3: "ROJA"}
ASSESSMENT_SCORE = {"No valorado": 0, "VERDE": 1, "AMARILLO": 2, "ROJO": 3}
ASSESSMENT_SCORE_LABELS = {0: "No valorado", 1: "VERDE", 2: "AMARILLO", 3: "ROJO"}

if not volc_all.empty:
    st.caption(
        f"Cobertura de esta tabla en los reportes: "
        f"{volc_all['report_date'].min():%b %Y} – {volc_all['report_date'].max():%b %Y}. "
        "El filtro de años del sidebar usa la fecha de inicio del evento (Sección 2), que sí "
        "arranca antes — si el rango seleccionado no toca ese período, esta sección queda vacía."
    )

if volc.empty:
    st.info("Sin datos de volcanes para el rango de años seleccionado.")
else:
    volc_order = volc["volcano"].value_counts().index.tolist()
    volc = volc.copy()
    volc["alert_level"] = volc["alert_level"].replace({"Sin dato": "No valorado"})
    volc["assessment"] = volc["assessment"].replace({"Sin dato": "No valorado"})

    METRICS = {
        "Nivel de alerta declarado": ("alert_level", ALERT_ORDER, ALERT_COLOR),
        "Valoración actual": ("assessment", ASSESSMENT_ORDER, ASSESSMENT_COLOR),
    }
    csel1, csel2 = st.columns(2)
    with csel1:
        sel_volcano = st.selectbox("Volcán", volc_order)
    with csel2:
        sel_metric = st.selectbox("Variable a graficar en el tiempo", list(METRICS.keys()))
    metric_col, metric_order, metric_color = METRICS[sel_metric]

    volc_one = volc[volc["volcano"] == sel_volcano].sort_values("report_date").reset_index(drop=True)

    # Convertimos la categoría a una escala numérica de severidad (0 = nada,
    # subiendo hasta el nivel más grave) para poder graficar un índice
    # temporal por mes en vez de puntos/franjas categóricas.
    SCORE_MAPS = {
        "Nivel de alerta declarado": (ALERT_SCORE, ALERT_SCORE_LABELS),
        "Valoración actual": (ASSESSMENT_SCORE, ASSESSMENT_SCORE_LABELS),
    }
    score_map, score_labels = SCORE_MAPS[sel_metric]
    volc_one["score"] = volc_one[metric_col].map(score_map)
    volc_month = volc_one.copy()
    volc_month["mes"] = volc_month["report_date"].dt.to_period("M").dt.to_timestamp()
    # Máximo del mes: el nivel más grave alcanzado, no un promedio diluido
    # (para monitoreo de riesgo el pico del mes es lo que importa).
    monthly_score = volc_month.groupby("mes")["score"].max().reset_index()

    fig10 = go.Figure(go.Scatter(
        x=monthly_score["mes"], y=monthly_score["score"], mode="lines+markers",
        line=dict(color=CATEGORICAL[1], width=2, shape="hv"),
        marker=dict(size=7),
        fill="tozeroy", fillcolor="rgba(235,104,52,0.15)",
        hovertemplate="%{x|%b %Y}: %{text}<extra></extra>",
        text=[score_labels.get(s, s) for s in monthly_score["score"]],
    ))
    fig10.update_layout(title=f"{sel_metric} — máximo mensual — {sel_volcano}")
    fig10.update_xaxes(title="")
    fig10.update_yaxes(
        title="", tickmode="array",
        tickvals=list(score_labels.keys()), ticktext=list(score_labels.values()),
        range=[-0.3, max(score_labels.keys()) + 0.3],
    )
    base_layout(fig10, height=340)
    st.plotly_chart(fig10, width='stretch')
    chart_total_caption(f"lecturas de {sel_volcano}", len(volc_one))
    detail_table(
        volc_one[["report_date", metric_col, "score"]]
        .rename(columns={"report_date": "fecha", metric_col: sel_metric, "score": "índice"})
        .sort_values("fecha", ascending=False),
        key="tbl_volcan_serie",
    )

    # Treemap en vez de barras apiladas/mapa de calor: cada volcán es un
    # bloque grande subdividido por nivel — el tamaño y el color codifican el
    # valor, y el número queda dentro del rectángulo salvo que sea diminuto.
    alert_pct = volc.groupby(["volcano", "alert_level"]).size().reset_index(name="n")
    alert_pivot = (alert_pct.pivot(index="volcano", columns="alert_level", values="n")
                   .reindex(index=volc_order, columns=[c for c in ALERT_ORDER if c in alert_pct["alert_level"].unique()])
                   .fillna(0).astype(int))
    fig11 = px.treemap(
        alert_pct, path=["volcano", "alert_level"], values="n",
        color="alert_level", color_discrete_map={**ALERT_COLOR, "(?)": "#eeeeea"},
    )
    fig11.update_traces(texttemplate="<b>%{label}</b><br>%{value}", textfont_size=13)
    fig11.update_layout(title="Lecturas por nivel de alerta declarado")
    base_layout(fig11, height=460)
    st.plotly_chart(fig11, width='stretch')
    chart_total_caption("lecturas de alerta (todos los volcanes)", alert_pct["n"].sum())
    detail_table(alert_pivot, key="tbl_volcan_alerta_heatmap")

    assess_pct = volc.groupby(["volcano", "assessment"]).size().reset_index(name="n")
    assess_pivot = (assess_pct.pivot(index="volcano", columns="assessment", values="n")
                     .reindex(index=volc_order, columns=[c for c in ASSESSMENT_ORDER if c in assess_pct["assessment"].unique()])
                     .fillna(0).astype(int))
    fig12 = px.treemap(
        assess_pct, path=["volcano", "assessment"], values="n",
        color="assessment", color_discrete_map={**ASSESSMENT_COLOR, "(?)": "#eeeeea"},
    )
    fig12.update_traces(texttemplate="<b>%{label}</b><br>%{value}", textfont_size=13)
    fig12.update_layout(title="Lecturas por valoración actual (current_assessment)")
    base_layout(fig12, height=460)
    st.plotly_chart(fig12, width='stretch')
    chart_total_caption("lecturas de valoración (todos los volcanes)", assess_pct["n"].sum())
    detail_table(assess_pivot, key="tbl_volcan_valoracion_heatmap")

    st.markdown("###### Alerta vs. valoración: ¿son consistentes entre sí?")
    st.caption(
        "Cruce de nivel de alerta declarado × valoración actual, sumando todas las lecturas de "
        "todos los volcanes. Si ambas fueran siempre coherentes, casi todo caería en la diagonal "
        "(alerta baja → valoración VERDE, alerta alta → valoración ROJO)."
    )
    cross = volc.groupby(["alert_level", "assessment"]).size().reset_index(name="n")
    cross_pivot = (cross.pivot(index="alert_level", columns="assessment", values="n")
                   .reindex(index=ALERT_ORDER, columns=ASSESSMENT_ORDER).fillna(0).astype(int))
    cross_pivot = cross_pivot.loc[(cross_pivot.sum(axis=1) > 0), (cross_pivot.sum(axis=0) > 0)]
    fig_cross = px.imshow(
        cross_pivot, text_auto=True, color_continuous_scale=SEQ_BLUE, aspect="auto",
        labels=dict(x="Valoración actual", y="Nivel de alerta declarado", color="N.º de lecturas"),
    )
    fig_cross.update_layout(title="Nivel de alerta declarado × valoración actual (todos los volcanes)")
    base_layout(fig_cross, height=max(280, 55 * len(cross_pivot)))
    st.plotly_chart(fig_cross, width='stretch')
    chart_total_caption("lecturas cruzadas", cross["n"].sum())
    detail_table(cross_pivot, key="tbl_volcan_alerta_vs_valoracion")

st.markdown("---")

# ---------------------------------------------------------------------------
# Sismos
# ---------------------------------------------------------------------------
st.subheader("Sismos")
st.caption(
    "Un punto por sismo detectado (deduplicado por hora + magnitud + ubicación). "
    "La magnitud y profundidad vienen a veces con ruido de OCR de columnas vecinas — "
    "los valores fuera de rango físico plausible se descartan en vez de mostrarse como si fueran reales."
)

if seismic.empty:
    st.info("Sin datos de sismos para los filtros seleccionados.")
else:
    n_no_mag = int(seismic["magnitude"].isna().sum())
    FELT_COLOR = {"Sí": CATEGORICAL[7], "No": SEQ_BLUE[3], "No especificado": OTHER_GRAY}

    seismic_plot = seismic.dropna(subset=["magnitude"]).sort_values("event_datetime")
    figS1 = px.scatter(
        seismic_plot, x="event_datetime", y="magnitude", color="felt_by_population",
        color_discrete_map=FELT_COLOR,
        hover_data={"near": True, "depth_km": True, "event_datetime": "|%d %b %Y %H:%M"},
    )
    figS1.update_traces(marker=dict(size=8))
    figS1.update_layout(title="Sismos registrados — magnitud en el tiempo")
    figS1.update_xaxes(title="")
    figS1.update_yaxes(title="Magnitud")
    base_layout(figS1, height=380)
    st.plotly_chart(figS1, width='stretch')
    chart_total_caption("sismos graficados", len(seismic_plot))
    if n_no_mag:
        st.caption(f"{n_no_mag} sismo(s) adicionales detectados sin magnitud reconocible (no graficados aquí).")
    detail_table(
        seismic_plot[["event_datetime", "magnitude", "depth_km", "near", "felt_by_population"]]
        .rename(columns={"event_datetime": "fecha", "magnitude": "magnitud", "depth_km": "profundidad_km",
                          "near": "ubicación", "felt_by_population": "sentido_por_población"})
        .sort_values("fecha", ascending=False),
        key="tbl_sismos_serie",
    )

    prov_counts_s = seismic["province"].value_counts().reset_index()
    prov_counts_s.columns = ["province", "n"]
    prov_counts_s = prov_counts_s[prov_counts_s["province"] != "No especificado"]
    prov_counts_s = prov_counts_s.sort_values("n", ascending=True).tail(12)
    figS2 = go.Figure(go.Bar(
        x=prov_counts_s["n"], y=prov_counts_s["province"], orientation="h",
        marker_color=CATEGORICAL[4],
        text=prov_counts_s["n"], textposition="outside", cliponaxis=False,
    ))
    figS2.update_layout(title="Sismos por provincia (ubicación reconocida)")
    figS2.update_xaxes(range=[0, prov_counts_s["n"].max() * 1.15])
    base_layout(figS2, height=380)
    st.plotly_chart(figS2, width='stretch')
    chart_total_caption("sismos con provincia reconocida", prov_counts_s["n"].sum())
    detail_table(
        prov_counts_s.rename(columns={"province": "provincia", "n": "sismos"}).sort_values("sismos", ascending=False),
        key="tbl_sismos_provincia",
    )

    seismic_month = seismic.dropna(subset=["event_datetime"]).copy()
    seismic_month["year_month"] = seismic_month["event_datetime"].dt.to_period("M").dt.to_timestamp()
    seismic_monthly = seismic_month.groupby("year_month").size().reset_index(name="n")
    figS3 = go.Figure(go.Scatter(
        x=seismic_monthly["year_month"], y=seismic_monthly["n"], mode="lines",
        line=dict(color=CATEGORICAL[4], width=2),
        fill="tozeroy", fillcolor="rgba(232,123,164,0.15)",
        hovertemplate="%{x|%b %Y}: %{y} sismos<extra></extra>",
    ))
    figS3.update_layout(title="Sismos detectados por mes")
    figS3.update_xaxes(title="")
    figS3.update_yaxes(title="N.º de sismos")
    base_layout(figS3, height=340)
    st.plotly_chart(figS3, width='stretch')
    chart_total_caption("sismos con fecha reconocida", seismic_monthly["n"].sum())
    detail_table(
        seismic_monthly.rename(columns={"year_month": "mes", "n": "sismos"}).sort_values("mes", ascending=False),
        key="tbl_sismos_mes",
    )

st.markdown("---")

# ---------------------------------------------------------------------------
# Situación hidrometeorológica
# ---------------------------------------------------------------------------
st.subheader("Situación hidrometeorológica")
st.caption(
    "Alertas declaradas por tipo de amenaza (lluvias/tormenta, temperatura, viento, radiación UV), "
    "deduplicadas por número de alerta + familia + ventana de vigencia (el número de alerta se reinicia cada año)."
)

FAMILY_LABELS = {
    "PRECIPITACION_TORMENTA": "Lluvias / tormenta",
    "TEMPERATURA_ALTA": "Temperatura alta",
    "TEMPERATURA_BAJA": "Temperatura baja",
    "VIENTO_FUERTE": "Viento fuerte",
    "RADIACION_UV": "Radiación UV",
}

if hydromet.empty:
    st.info("Sin datos de situación hidrometeorológica para los filtros seleccionados.")
else:
    hydromet = hydromet.copy()
    hydromet["family_label"] = hydromet["primary_family"].map(lambda f: FAMILY_LABELS.get(f, f))
    fam_order = hydromet["family_label"].value_counts().index.tolist()
    fam_color = {fam: CATEGORICAL[i % len(CATEGORICAL)] for i, fam in enumerate(fam_order)}

    figH1 = px.scatter(
        hydromet.sort_values("validity_start"), x="validity_start", y="family_label", color="family_label",
        category_orders={"family_label": fam_order},
        color_discrete_map=fam_color,
        hover_data={"validity_start": "|%d %b %Y", "family_label": False},
    )
    figH1.update_traces(marker=dict(size=8))
    figH1.update_layout(title="Alertas hidrometeorológicas declaradas en el tiempo", showlegend=False)
    figH1.update_xaxes(title="")
    figH1.update_yaxes(title="")
    base_layout(figH1, height=340)
    st.plotly_chart(figH1, width='stretch')
    chart_total_caption("alertas hidrometeorológicas", len(hydromet))
    detail_table(
        hydromet[["validity_start", "validity_end", "family_label", "warning_number"]]
        .rename(columns={"validity_start": "vigencia_desde", "validity_end": "vigencia_hasta",
                          "family_label": "tipo", "warning_number": "n_alerta"})
        .sort_values("vigencia_desde", ascending=False),
        key="tbl_hidromet_serie",
    )

    fam_counts = hydromet["family_label"].value_counts().reset_index()
    fam_counts.columns = ["family_label", "n"]
    fam_counts = fam_counts.sort_values("n", ascending=True)
    figH2 = go.Figure(go.Bar(
        x=fam_counts["n"], y=fam_counts["family_label"], orientation="h",
        marker_color=SEQ_BLUE[3],
        text=fam_counts["n"], textposition="outside", cliponaxis=False,
    ))
    figH2.update_layout(title="Total de alertas por tipo")
    figH2.update_xaxes(range=[0, fam_counts["n"].max() * 1.15])
    base_layout(figH2, height=340)
    st.plotly_chart(figH2, width='stretch')
    chart_total_caption("alertas hidrometeorológicas", fam_counts["n"].sum())
    detail_table(
        fam_counts.rename(columns={"family_label": "tipo", "n": "alertas"}).sort_values("alertas", ascending=False),
        key="tbl_hidromet_tipo",
    )

    hydromet_month = hydromet.dropna(subset=["validity_start"]).copy()
    hydromet_month["year_month"] = hydromet_month["validity_start"].dt.to_period("M").dt.to_timestamp()
    hydromet_monthly = hydromet_month.groupby(["year_month", "family_label"]).size().reset_index(name="n")
    figH3 = go.Figure()
    for fam in fam_order:
        sub = hydromet_monthly[hydromet_monthly["family_label"] == fam]
        figH3.add_trace(go.Scatter(
            x=sub["year_month"], y=sub["n"], mode="lines", name=fam,
            line=dict(color=fam_color.get(fam, OTHER_GRAY), width=2),
            hovertemplate=f"{fam}<br>" + "%{x|%b %Y}: %{y} alertas<extra></extra>",
        ))
    figH3.update_layout(title="Alertas hidrometeorológicas por mes, por tipo")
    figH3.update_xaxes(title="")
    figH3.update_yaxes(title="N.º de alertas")
    base_layout(figH3, height=380)
    st.plotly_chart(figH3, width='stretch')
    chart_total_caption("alertas con fecha de vigencia reconocida", hydromet_monthly["n"].sum())
    detail_table(
        hydromet_monthly.pivot(index="year_month", columns="family_label", values="n")
        .fillna(0).astype(int).sort_index(ascending=False),
        key="tbl_hidromet_mes",
    )

st.markdown("---")

# ---------------------------------------------------------------------------
# Otras amenazas — incendios activos y cuerpos de agua
# ---------------------------------------------------------------------------
st.subheader("Otras amenazas: incendios forestales activos y cuerpos de agua")

if fires.empty:
    st.info("Sin datos de incendios activos para los filtros seleccionados.")
else:
    fire_month = fires.dropna(subset=["start_date"]).copy()
    fire_month["year_month"] = fire_month["start_date"].dt.to_period("M").dt.to_timestamp()
    fire_monthly = fire_month.groupby("year_month").size().reset_index(name="n")
    fig16 = go.Figure(go.Scatter(
        x=fire_monthly["year_month"], y=fire_monthly["n"], mode="lines",
        line=dict(color=CATEGORICAL[1], width=2),
        fill="tozeroy", fillcolor="rgba(235,104,52,0.15)",
        hovertemplate="%{x|%b %Y}: %{y} incendios<extra></extra>",
    ))
    fig16.update_layout(title="Incendios forestales activos por mes de inicio")
    fig16.update_yaxes(title="N.º de incendios")
    base_layout(fig16, height=380)
    st.plotly_chart(fig16, width='stretch')
    chart_total_caption("incendios con fecha de inicio reconocida", fire_monthly["n"].sum())
    detail_table(
        fire_monthly.rename(columns={"year_month": "mes", "n": "incendios"}).sort_values("mes", ascending=False),
        key="tbl_incendios_mes",
    )

    fires_prov = fires["province"].value_counts().reset_index()
    fires_prov.columns = ["province", "n"]
    fires_prov = fires_prov.sort_values("n", ascending=True).tail(15)
    fig_fires_prov = go.Figure(go.Bar(
        x=fires_prov["n"], y=fires_prov["province"], orientation="h",
        marker_color=CATEGORICAL[1],
        text=fires_prov["n"], textposition="outside", cliponaxis=False,
    ))
    fig_fires_prov.update_layout(title="Top 15 provincias por N.º de incendios activos")
    fig_fires_prov.update_xaxes(range=[0, fires_prov["n"].max() * 1.15])
    base_layout(fig_fires_prov, height=420)
    st.plotly_chart(fig_fires_prov, width='stretch')
    chart_total_caption("incendios en las 15 provincias mostradas", fires_prov["n"].sum())
    detail_table(
        fires_prov.rename(columns={"province": "provincia", "n": "incendios"}).sort_values("incendios", ascending=False),
        key="tbl_incendios_provincia",
    )

    fires_ha = fires.dropna(subset=["affected_area_ha"])
    n_sin_ha = len(fires) - len(fires_ha)
    st.caption(
        f"El área quemada (`affected_area_ha`) solo viene declarada en {len(fires_ha):,} de "
        f"{len(fires):,} incendios ({n_sin_ha:,} sin dato) — es una métrica de intensidad, no de "
        "frecuencia, y su cobertura es parcial."
    )
    if not fires_ha.empty:
        fires_ha_prov = fires_ha.groupby("province")["affected_area_ha"].sum().reset_index()
        fires_ha_prov = fires_ha_prov.sort_values("affected_area_ha", ascending=True).tail(15)
        fig_fires_ha = go.Figure(go.Bar(
            x=fires_ha_prov["affected_area_ha"], y=fires_ha_prov["province"], orientation="h",
            marker_color=CATEGORICAL[7],
            text=[f"{v:,.0f}" for v in fires_ha_prov["affected_area_ha"]], textposition="outside", cliponaxis=False,
        ))
        fig_fires_ha.update_layout(title="Top 15 provincias por hectáreas quemadas (dato parcial)")
        fig_fires_ha.update_xaxes(title="Hectáreas", range=[0, fires_ha_prov["affected_area_ha"].max() * 1.15])
        base_layout(fig_fires_ha, height=420)
        st.plotly_chart(fig_fires_ha, width='stretch')
        chart_total_caption("hectáreas quemadas (incendios con dato)", fires_ha_prov["affected_area_ha"].sum())
        detail_table(
            fires_ha_prov.rename(columns={"province": "provincia", "affected_area_ha": "hectáreas"})
            .round({"hectáreas": 1}).sort_values("hectáreas", ascending=False),
            key="tbl_incendios_hectareas",
        )

if water.empty:
    st.info("Sin datos de cuerpos de agua para los filtros seleccionados.")
else:
    water_prov = water.groupby(["province", "status"]).size().reset_index(name="n")
    top_prov_water = water["province"].value_counts().head(12).index.tolist()
    water_prov = water_prov[water_prov["province"].isin(top_prov_water)]
    fig17 = px.bar(
        water_prov, x="n", y="province", color="status", orientation="h",
        category_orders={"province": top_prov_water[::-1]},
        color_discrete_map={"Desbordado": CATEGORICAL[7], "Creciendo": CATEGORICAL[3]},
    )
    fig17.update_traces(texttemplate="%{x}", textposition="inside", textangle=0, textfont_size=11)
    fig17.update_layout(title="Cuerpos de agua reportados por provincia", barmode="stack",
                         xaxis_title="N.º de reportes únicos", yaxis_title="")
    water_totals = water_prov.groupby("province")["n"].sum().reindex(top_prov_water)
    add_stack_totals(fig17, water_totals.index, water_totals.values, horizontal=True)
    base_layout(fig17, height=420)
    st.plotly_chart(fig17, width='stretch')
    chart_total_caption("reportes únicos de cuerpos de agua", water_prov["n"].sum())
    detail_table(
        water_prov.pivot(index="province", columns="status", values="n")
        .reindex(top_prov_water).fillna(0).astype(int),
        key="tbl_agua_provincia",
    )

st.markdown("---")

# ---------------------------------------------------------------------------
# Índice compuesto de amenazas por provincia
# ---------------------------------------------------------------------------
st.subheader("Índice compuesto de amenazas por provincia")
st.caption(
    "Suma simple de registros de sismos + incendios activos + cuerpos de agua + tramos de vía "
    "afectados, por provincia — no es un índice de riesgo ponderado ni normalizado, solo cuánta "
    "actividad reportada de estas 4 fuentes se concentra en cada provincia. Los volcanes quedan "
    "fuera porque esa tabla no trae provincia como campo propio."
)

composite_sources = {
    "Sismos": seismic[seismic["province"] != "No especificado"]["province"].value_counts(),
    "Incendios": fires["province"].value_counts(),
    "Cuerpos de agua": water["province"].value_counts(),
    "Vías afectadas": roads["province"].value_counts(),
}
composite = pd.DataFrame(composite_sources).fillna(0).astype(int)
composite = composite[composite.sum(axis=1) > 0]

if composite.empty:
    st.info("Sin datos suficientes para el índice compuesto con los filtros seleccionados.")
else:
    composite["total"] = composite.sum(axis=1)
    composite = composite.sort_values("total", ascending=False).head(15)
    top_provs_composite = composite.index.tolist()
    composite_long = (composite.drop(columns="total").reset_index()
                       .rename(columns={"index": "province"})
                       .melt(id_vars="province", var_name="fuente", value_name="n"))

    fig_composite = px.bar(
        composite_long, x="n", y="province", color="fuente", orientation="h",
        category_orders={"province": top_provs_composite[::-1],
                          "fuente": ["Sismos", "Incendios", "Cuerpos de agua", "Vías afectadas"]},
        color_discrete_map={"Sismos": CATEGORICAL[4], "Incendios": CATEGORICAL[1],
                             "Cuerpos de agua": CATEGORICAL[3], "Vías afectadas": SEQ_BLUE[4]},
    )
    fig_composite.update_traces(texttemplate="%{x}", textposition="inside", textangle=0, textfont_size=10)
    fig_composite.update_layout(title="Índice compuesto de amenazas por provincia (top 15)", barmode="stack",
                                 xaxis_title="N.º de registros combinados", yaxis_title="")
    composite_totals = composite["total"]
    add_stack_totals(fig_composite, composite_totals.index, composite_totals.values, horizontal=True)
    base_layout(fig_composite, height=480)
    st.plotly_chart(fig_composite, width='stretch')
    chart_total_caption("registros combinados en las 15 provincias mostradas", composite["total"].sum())
    detail_table(composite, key="tbl_indice_compuesto")

st.markdown("---")

# =============================================================================
# SECCIÓN 2 — Eventos Adversos (deduplicados)
# =============================================================================
st.header("Sección 2 — Eventos Adversos (deduplicados)")
st.caption("Sección 2 de los Reportes de Monitoreo de Amenazas y Eventos Adversos/Peligrosos")


if df.empty:
    st.warning("No hay eventos con los filtros seleccionados.")
else:
    # -------------------------------------------------------------------
    # KPIs
    # -------------------------------------------------------------------
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Eventos únicos", f"{len(df):,}")
    c2.metric("Provincias afectadas", df["province"].nunique())
    top_type = df["event_type"].value_counts().idxmax()
    c3.metric("Tipo más frecuente", top_type, f"{df['event_type'].value_counts().max()} eventos")
    top_prov = df["province"].value_counts().idxmax()
    c4.metric("Provincia más afectada", top_prov, f"{df['province'].value_counts().max()} eventos")

    st.markdown("---")

    # -------------------------------------------------------------------
    # 1. Proporción por tipo de evento
    # -------------------------------------------------------------------
    st.subheader("¿Qué tipos de evento ocurren con más frecuencia?")
    type_counts = df["event_type"].value_counts().reset_index()
    type_counts.columns = ["event_type", "n"]
    type_counts["pct"] = 100 * type_counts["n"] / type_counts["n"].sum()
    type_counts["event_type"] = pd.Categorical(type_counts["event_type"], categories=TYPE_ORDER_GLOBAL, ordered=True)
    type_counts = type_counts.sort_values("n", ascending=True)

    fig = go.Figure(go.Bar(
        x=type_counts["n"], y=type_counts["event_type"], orientation="h",
        marker_color=[CMAP.get(t, OTHER_GRAY) for t in type_counts["event_type"]],
        text=[f"{n} ({p:.0f}%)" for n, p in zip(type_counts["n"], type_counts["pct"])],
        textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: %{x} eventos (%{customdata:.1f}%)<extra></extra>",
        customdata=type_counts["pct"],
    ))
    fig.update_layout(title="Eventos únicos por tipo (todas las provincias/años filtrados)")
    fig.update_xaxes(title="N.º de eventos")
    base_layout(fig, height=max(380, 26 * len(type_counts)))
    st.plotly_chart(fig, width='stretch')
    chart_total_caption("eventos únicos filtrados", type_counts["n"].sum())
    detail_table(
        type_counts[["event_type", "n", "pct"]].rename(columns={"event_type": "tipo", "n": "eventos", "pct": "%"})
        .round({"%": 1}).sort_values("eventos", ascending=False),
        key="tbl_tipo_evento",
    )

    top8 = type_counts.sort_values("n", ascending=False).head(8).copy()
    others = type_counts.sort_values("n", ascending=False).iloc[8:]["n"].sum()
    if others > 0:
        top8 = pd.concat([top8, pd.DataFrame([{"event_type": "Otros", "n": others, "pct": 100 * others / type_counts["n"].sum()}])])
    fig2 = px.pie(
        top8, names="event_type", values="n",
        color="event_type",
        color_discrete_map={**CMAP, "Otros": OTHER_GRAY},
        hole=0.5,
    )
    fig2.update_traces(textinfo="percent+label", textfont_color=TEXT_PRIMARY)
    fig2.update_layout(title="Proporción (top 8 + Otros)", showlegend=False)
    base_layout(fig2, height=max(380, 26 * len(type_counts)))
    st.plotly_chart(fig2, width='stretch')
    chart_total_caption("eventos únicos filtrados", top8["n"].sum())
    detail_table(
        top8[["event_type", "n", "pct"]].rename(columns={"event_type": "tipo", "n": "eventos", "pct": "%"})
        .round({"%": 1}).sort_values("eventos", ascending=False),
        key="tbl_tipo_evento_pie",
    )

    st.markdown("---")

    # -------------------------------------------------------------------
    # 2. Evolución por año
    # -------------------------------------------------------------------
    st.subheader("¿En qué años ocurrieron más eventos?")

    top_n_types = st.slider("Tipos de evento a distinguir por color (el resto se agrupa en 'Otros')", 3, 8, 6)
    keep_types = TYPE_ORDER_GLOBAL[:top_n_types]

    df_year = df.dropna(subset=["year"]).copy()
    df_year["type_grouped"] = df_year["event_type"].where(df_year["event_type"].isin(keep_types), "Otros")
    year_type = df_year.groupby(["year", "type_grouped"]).size().reset_index(name="n")

    order_grouped = [t for t in keep_types] + (["Otros"] if (df_year["type_grouped"] == "Otros").any() else [])
    cmap_grouped = {**{t: CMAP.get(t, OTHER_GRAY) for t in keep_types}, "Otros": OTHER_GRAY}

    fig3 = px.bar(
        year_type, x="n", y="year", color="type_grouped", orientation="h",
        category_orders={"type_grouped": order_grouped},
        color_discrete_map=cmap_grouped,
    )
    fig3.update_traces(texttemplate="%{x}", textposition="inside", textangle=0, textfont_size=11)
    fig3.update_layout(title="Eventos únicos por año, apilados por tipo", barmode="stack",
                        xaxis_title="N.º de eventos", yaxis_title="Año (fecha de inicio del evento)")
    fig3.update_yaxes(type="category")
    year_totals = year_type.groupby("year")["n"].sum()
    add_stack_totals(fig3, year_totals.index.astype(str), year_totals.values, horizontal=True)
    base_layout(fig3, height=440)
    st.plotly_chart(fig3, width='stretch')
    chart_total_caption("eventos únicos en el período filtrado", year_type["n"].sum())
    detail_table(
        year_type.pivot(index="year", columns="type_grouped", values="n")
        .fillna(0).astype(int).sort_index(ascending=False),
        key="tbl_evolucion_anio",
    )

    st.markdown("---")

    # -------------------------------------------------------------------
    # 3. Por provincia
    # -------------------------------------------------------------------
    st.subheader("¿En qué provincias ocurrieron más eventos?")
    prov_counts = df["province"].value_counts().reset_index()
    prov_counts.columns = ["province", "n"]
    prov_counts = prov_counts.sort_values("n", ascending=True).tail(20)

    fig4 = go.Figure(go.Bar(
        x=prov_counts["n"], y=prov_counts["province"], orientation="h",
        marker_color=SEQ_BLUE[3],
        text=prov_counts["n"], textposition="outside", cliponaxis=False,
    ))
    fig4.update_layout(title="Top 20 provincias por N.º de eventos únicos")
    fig4.update_xaxes(title="N.º de eventos", range=[0, prov_counts["n"].max() * 1.15])
    base_layout(fig4, height=560)
    st.plotly_chart(fig4, width='stretch')
    chart_total_caption("eventos en las 20 provincias mostradas", prov_counts["n"].sum())
    detail_table(
        prov_counts.rename(columns={"province": "provincia", "n": "eventos"}).sort_values("eventos", ascending=False),
        key="tbl_top_provincias",
    )

    top_provs = df["province"].value_counts().head(6).index.tolist()
    df_prov_type = df[df["province"].isin(top_provs)]
    prov_type_pct = (
        df_prov_type.groupby(["province", "event_type"]).size().reset_index(name="n")
    )
    prov_type_pct["province"] = pd.Categorical(prov_type_pct["province"], categories=top_provs, ordered=True)
    prov_type_pct["event_type_g"] = prov_type_pct["event_type"].where(
        prov_type_pct["event_type"].isin(TYPE_ORDER_GLOBAL[:8]), "Otros"
    )
    fig5 = px.bar(
        prov_type_pct, x="n", y="province", color="event_type_g", orientation="h",
        category_orders={"province": top_provs[::-1], "event_type_g": TYPE_ORDER_GLOBAL[:8] + ["Otros"]},
        color_discrete_map={**CMAP, "Otros": OTHER_GRAY},
    )
    # texttemplate solo en el eje de valores (%{x}); textangle=0 evita que Plotly
    # rote a 90° los números de segmentos angostos — si un segmento es demasiado
    # chico para el número horizontal, Plotly directamente lo oculta (más legible
    # que un número apretado y girado).
    fig5.update_traces(texttemplate="%{x}", textposition="inside", textangle=0, textfont_size=11)
    fig5.update_layout(title="Composición por tipo — top 6 provincias", barmode="stack",
                        xaxis_title="N.º de eventos", yaxis_title="")
    prov_totals = prov_type_pct.groupby("province")["n"].sum().reindex(top_provs)
    add_stack_totals(fig5, prov_totals.index, prov_totals.values, horizontal=True)
    base_layout(fig5, height=380)
    st.plotly_chart(fig5, width='stretch')
    chart_total_caption("eventos en las 6 provincias mostradas", prov_type_pct["n"].sum())
    detail_table(
        prov_type_pct.pivot_table(index="province", columns="event_type_g", values="n", aggfunc="sum", observed=True)
        .reindex(top_provs).fillna(0).astype(int),
        key="tbl_composicion_provincia",
    )

    st.markdown("---")

    # -------------------------------------------------------------------
    # 4. Evolución mensual — top 5 tipos de evento
    # -------------------------------------------------------------------
    st.subheader("Evolución mensual de los 5 tipos de evento más frecuentes")

    top5_types = df["event_type"].value_counts().head(5).index.tolist()

    df_month = df[df["event_type"].isin(top5_types)].dropna(subset=["event_start_date"]).copy()
    df_month["year_month"] = df_month["event_start_date"].dt.to_period("M").dt.to_timestamp()
    monthly_type = df_month.groupby(["year_month", "event_type"]).size().reset_index(name="n")

    fig7 = go.Figure()
    for t in top5_types:
        sub = monthly_type[monthly_type["event_type"] == t]
        fig7.add_trace(go.Scatter(
            x=sub["year_month"], y=sub["n"], mode="lines", name=t,
            line=dict(color=CMAP.get(t, OTHER_GRAY), width=2),
            hovertemplate=f"{t}<br>" + "%{x|%b %Y}: %{y} eventos<extra></extra>",
        ))
    fig7.update_layout(title="N.º de eventos por mes — top 5 tipos (fecha de inicio del evento)")
    fig7.update_xaxes(title="")
    fig7.update_yaxes(title="N.º de eventos")
    base_layout(fig7, height=440)
    st.plotly_chart(fig7, width='stretch')
    chart_total_caption("eventos de los 5 tipos más frecuentes con fecha reconocida", monthly_type["n"].sum())
    detail_table(
        monthly_type.pivot(index="year_month", columns="event_type", values="n")
        .fillna(0).astype(int).sort_index(ascending=False),
        key="tbl_evolucion_mensual_top5",
    )

    st.markdown("---")

    # -------------------------------------------------------------------
    # 4b. Estacionalidad por tipo de evento
    # -------------------------------------------------------------------
    st.subheader("¿Hay estacionalidad? Eventos por mes del año, sumando todos los años")
    st.caption(
        "A diferencia del gráfico anterior (que sigue el calendario real, año por año), aquí se "
        "suman todas las ocurrencias de cada mes (enero de 2020 + enero de 2021 + ...) para ver si "
        "un tipo de evento tiende a repetirse en la misma época del año."
    )
    MONTH_NAMES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    season_types = TYPE_ORDER_GLOBAL[:10]
    season = df[df["event_type"].isin(season_types) & df["month"].notna()].copy()
    season_counts = season.groupby(["event_type", "month"]).size().reset_index(name="n")
    season_pivot = (season_counts.pivot(index="event_type", columns="month", values="n")
                     .reindex(index=season_types, columns=range(1, 13)).fillna(0).astype(int))
    season_pivot.columns = [MONTH_NAMES[m - 1] for m in season_pivot.columns]
    fig_season = px.imshow(
        season_pivot, text_auto=True, color_continuous_scale=SEQ_BLUE, aspect="auto",
        labels=dict(color="N.º de eventos"),
    )
    fig_season.update_layout(title="Eventos por mes del año — top 10 tipos (todos los años sumados)")
    fig_season.update_xaxes(title="")
    fig_season.update_yaxes(title="")
    base_layout(fig_season, height=max(320, 40 * len(season_pivot)))
    st.plotly_chart(fig_season, width='stretch')
    chart_total_caption("eventos con mes reconocido (top 10 tipos)", season_counts["n"].sum())
    detail_table(season_pivot, key="tbl_estacionalidad")

    st.markdown("---")

    # -------------------------------------------------------------------
    # 4c. Duración típica por tipo de evento
    # -------------------------------------------------------------------
    st.subheader("¿Qué tipos de evento quedan activos más tiempo?")
    st.caption(
        "`n_reportes` (en cuántos boletines apareció cada evento) como proxy de duración — no es "
        "tiempo real en días, pero sí indica qué tipos siguen apareciendo boletín tras boletín."
    )
    duration_stats = df.groupby("event_type")["n_reportes"].agg(mediana="median", promedio="mean", n="size")
    duration_stats = duration_stats[duration_stats["n"] >= 3].sort_values("mediana", ascending=True)
    fig_duration = go.Figure(go.Bar(
        x=duration_stats["mediana"], y=duration_stats.index, orientation="h",
        marker_color=CATEGORICAL[5],
        text=[f"{v:.1f}" for v in duration_stats["mediana"]], textposition="outside", cliponaxis=False,
    ))
    fig_duration.update_layout(title="Mediana de boletines por evento, por tipo (tipos con ≥3 eventos)")
    fig_duration.update_xaxes(title="Mediana de n.º de boletines", range=[0, duration_stats["mediana"].max() * 1.2])
    base_layout(fig_duration, height=max(320, 26 * len(duration_stats)))
    st.plotly_chart(fig_duration, width='stretch')
    chart_total_caption("tipos de evento comparados", len(duration_stats))
    detail_table(
        duration_stats.reset_index().rename(columns={"event_type": "tipo", "n": "n_eventos"})
        .round({"mediana": 1, "promedio": 1}).sort_values("mediana", ascending=False),
        key="tbl_duracion_tipo",
    )

    st.markdown("---")

    # -------------------------------------------------------------------
    # 4d. Eventos por Zona SNGR
    # -------------------------------------------------------------------
    st.subheader("Eventos por Zona SNGR")
    zone_counts = df[df["zone"].notna() & (df["zone"].str.strip() != "")]["zone"].value_counts().reset_index()
    zone_counts.columns = ["zone", "n"]
    zone_counts["zone_label"] = "Zona " + zone_counts["zone"].astype(str)
    zone_counts = zone_counts.sort_values("n", ascending=True)
    fig_zone = go.Figure(go.Bar(
        x=zone_counts["n"], y=zone_counts["zone_label"], orientation="h",
        marker_color=CATEGORICAL[6],
        text=zone_counts["n"], textposition="outside", cliponaxis=False,
    ))
    fig_zone.update_layout(title="Eventos únicos por Zona SNGR")
    fig_zone.update_xaxes(range=[0, zone_counts["n"].max() * 1.15])
    base_layout(fig_zone, height=max(280, 36 * len(zone_counts)))
    st.plotly_chart(fig_zone, width='stretch')
    chart_total_caption("eventos con zona reconocida", zone_counts["n"].sum())
    detail_table(
        zone_counts[["zone_label", "n"]].rename(columns={"zone_label": "zona", "n": "eventos"})
        .sort_values("eventos", ascending=False),
        key="tbl_zona_sngr",
    )

    st.markdown("---")

    # -------------------------------------------------------------------
    # 5. Ranking cantón / parroquia
    # -------------------------------------------------------------------
    st.subheader("Cantones y parroquias más afectados")
    canton_counts = df.dropna(subset=["canton"]).groupby(["province", "canton"]).size()
    canton_counts = canton_counts.reset_index(name="n").sort_values("n", ascending=False).head(15)
    canton_counts["label"] = canton_counts["canton"] + " (" + canton_counts["province"] + ")"
    fig8 = go.Figure(go.Bar(
        x=canton_counts["n"][::-1], y=canton_counts["label"][::-1], orientation="h",
        marker_color=CATEGORICAL[1],
        text=canton_counts["n"][::-1], textposition="outside", cliponaxis=False,
    ))
    fig8.update_layout(title="Top 15 cantones")
    fig8.update_xaxes(range=[0, canton_counts["n"].max() * 1.15])
    base_layout(fig8, height=440)
    st.plotly_chart(fig8, width='stretch')
    chart_total_caption("eventos en los 15 cantones mostrados", canton_counts["n"].sum())
    detail_table(
        canton_counts[["province", "canton", "n"]].rename(columns={"province": "provincia", "canton": "cantón", "n": "eventos"})
        .sort_values("eventos", ascending=False),
        key="tbl_top_cantones",
    )

    n_reportes_top = df.sort_values("n_reportes", ascending=False).head(15).copy()
    n_reportes_top["label"] = n_reportes_top["event_type"] + " — " + n_reportes_top["canton"].fillna(n_reportes_top["province"])
    fig9 = go.Figure(go.Bar(
        x=n_reportes_top["n_reportes"][::-1], y=n_reportes_top["label"][::-1], orientation="h",
        marker_color=CATEGORICAL[2],
        text=n_reportes_top["n_reportes"][::-1], textposition="outside", cliponaxis=False,
    ))
    fig9.update_layout(title="Eventos más prolongados (más boletines en los que aparecieron)")
    fig9.update_xaxes(title="N.º de reportes en los que apareció", range=[0, n_reportes_top["n_reportes"].max() * 1.15])
    base_layout(fig9, height=440)
    st.plotly_chart(fig9, width='stretch')
    chart_total_caption("boletines acumulados entre los 15 eventos mostrados", n_reportes_top["n_reportes"].sum())
    detail_table(
        n_reportes_top[["event_type", "province", "canton", "n_reportes"]]
        .rename(columns={"event_type": "tipo", "province": "provincia", "canton": "cantón", "n_reportes": "n_boletines"})
        .sort_values("n_boletines", ascending=False),
        key="tbl_eventos_prolongados",
    )

    st.markdown("---")

    # -------------------------------------------------------------------
    # Tabla y descarga
    # -------------------------------------------------------------------
    st.subheader("Datos filtrados")
    show_cols = ["event_type", "province", "canton", "parish", "event_start_date",
                 "year", "zone", "n_reportes", "sectors"]
    st.dataframe(df[show_cols].sort_values("event_start_date", ascending=False), width='stretch', height=350)
    st.download_button(
        "Descargar CSV filtrado",
        df.to_csv(index=False).encode("utf-8"),
        file_name="eventos_adversos_filtrados.csv",
        mime="text/csv",
    )

st.markdown("---")

# =============================================================================
# SECCIÓN 3 — Estado de Vías (Road Status Monitoring)
# =============================================================================
st.header("Sección 3 — Estado de Vías")
st.subheader("Vías afectadas por eventos adversos")
st.caption(
    "Tramos de vía de 1º, 2º y 3º orden reportados cerrados o parcialmente habilitados, "
    "deduplicados por tramo + tipo de evento + fecha del evento (se conserva el último estado reportado)."
)

if roads.empty:
    st.info("Sin datos de vías para los filtros seleccionados.")
else:
    road_month = roads.dropna(subset=["event_date"]).copy()
    road_month["year_month"] = road_month["event_date"].dt.to_period("M").dt.to_timestamp()
    road_monthly = road_month.groupby(["year_month", "road_status"]).size().reset_index(name="n")
    fig13 = px.bar(
        road_monthly, x="year_month", y="n", color="road_status",
        color_discrete_map={"Cerrada": CATEGORICAL[7], "Parcialmente habilitada": CATEGORICAL[3]},
    )
    # Solo 2 colores por barra, así que el número adentro de cada segmento
    # todavía es legible; textangle=0 oculta el que de verdad no quepa en vez
    # de mostrarlo girado. El total del mes va arriba de la pila.
    fig13.update_traces(texttemplate="%{y}", textposition="inside", textangle=0, textfont_size=10)
    fig13.update_layout(title="Vías afectadas por mes (fecha del evento)", barmode="stack",
                         xaxis_title="", yaxis_title="N.º de tramos")
    road_month_totals = road_monthly.groupby("year_month")["n"].sum()
    add_stack_totals(fig13, road_month_totals.index, road_month_totals.values)
    base_layout(fig13, height=420)
    st.plotly_chart(fig13, width='stretch')
    chart_total_caption("tramos con fecha de evento reconocida", road_monthly["n"].sum())
    detail_table(
        road_monthly.pivot(index="year_month", columns="road_status", values="n")
        .fillna(0).astype(int).sort_index(ascending=False),
        key="tbl_vias_mes",
    )

    road_types = roads["adverse_event"].value_counts().reset_index()
    road_types.columns = ["adverse_event", "n"]
    road_types = road_types.sort_values("n", ascending=True).tail(10)
    fig14 = go.Figure(go.Bar(
        x=road_types["n"], y=road_types["adverse_event"], orientation="h",
        marker_color=SEQ_BLUE[3],
        text=road_types["n"], textposition="outside", cliponaxis=False,
    ))
    fig14.update_layout(title="Tramos afectados por tipo de evento causante")
    fig14.update_xaxes(range=[0, road_types["n"].max() * 1.15])
    base_layout(fig14, height=420)
    st.plotly_chart(fig14, width='stretch')
    chart_total_caption("tramos afectados (top 10 tipos)", road_types["n"].sum())
    detail_table(
        road_types.rename(columns={"adverse_event": "tipo_de_evento", "n": "tramos"}).sort_values("tramos", ascending=False),
        key="tbl_vias_tipo",
    )

    road_prov = roads.groupby(["province", "road_order"]).size().reset_index(name="n")
    top_prov_roads = roads["province"].value_counts().head(15).index.tolist()
    road_prov = road_prov[road_prov["province"].isin(top_prov_roads)]
    fig15 = px.bar(
        road_prov, x="n", y="province", color="road_order", orientation="h",
        category_orders={"province": top_prov_roads[::-1], "road_order": ["Primer orden", "Segundo orden", "Tercer orden"]},
        color_discrete_map={"Primer orden": CATEGORICAL[0], "Segundo orden": CATEGORICAL[3], "Tercer orden": CATEGORICAL[5]},
    )
    fig15.update_traces(texttemplate="%{x}", textposition="inside", textangle=0, textfont_size=11)
    fig15.update_layout(title="Top 15 provincias por tramos afectados, por orden de vía", barmode="stack",
                         xaxis_title="N.º de tramos", yaxis_title="")
    road_prov_totals = road_prov.groupby("province")["n"].sum().reindex(top_prov_roads)
    add_stack_totals(fig15, road_prov_totals.index, road_prov_totals.values, horizontal=True)
    base_layout(fig15, height=480)
    st.plotly_chart(fig15, width='stretch')
    chart_total_caption("tramos en las 15 provincias mostradas", road_prov["n"].sum())
    detail_table(
        road_prov.pivot(index="province", columns="road_order", values="n")
        .reindex(top_prov_roads).fillna(0).astype(int),
        key="tbl_vias_provincia",
    )

    st.markdown("---")

    # -------------------------------------------------------------------
    # Metros lineales afectados
    # -------------------------------------------------------------------
    st.subheader("Metros lineales afectados por provincia")
    roads_m = roads.dropna(subset=["affected_linear_meters"])
    n_sin_m = len(roads) - len(roads_m)
    st.caption(
        f"`affected_linear_meters` solo viene declarado en {len(roads_m):,} de {len(roads):,} "
        f"tramos ({n_sin_m:,} sin dato) — mide la extensión del daño, no cuántos tramos hay."
    )
    if roads_m.empty:
        st.info("Sin datos de metros lineales para los filtros seleccionados.")
    else:
        meters_prov = roads_m.groupby("province")["affected_linear_meters"].sum().reset_index()
        meters_prov = meters_prov.sort_values("affected_linear_meters", ascending=True).tail(15)
        fig_meters = go.Figure(go.Bar(
            x=meters_prov["affected_linear_meters"], y=meters_prov["province"], orientation="h",
            marker_color=SEQ_BLUE[4],
            text=[f"{v:,.0f}" for v in meters_prov["affected_linear_meters"]],
            textposition="outside", cliponaxis=False,
        ))
        fig_meters.update_layout(title="Top 15 provincias por metros lineales de vía afectados")
        fig_meters.update_xaxes(title="Metros", range=[0, meters_prov["affected_linear_meters"].max() * 1.15])
        base_layout(fig_meters, height=480)
        st.plotly_chart(fig_meters, width='stretch')
        chart_total_caption("metros afectados (tramos con dato)", meters_prov["affected_linear_meters"].sum())
        detail_table(
            meters_prov.rename(columns={"province": "provincia", "affected_linear_meters": "metros"})
            .round({"metros": 0}).sort_values("metros", ascending=False),
            key="tbl_vias_metros",
        )

    st.markdown("---")

    # -------------------------------------------------------------------
    # Top tramos más recurrentes
    # -------------------------------------------------------------------
    st.subheader("Tramos de vía más recurrentes")
    st.caption(
        "Los tramos que aparecieron en más boletines consecutivos — proxy de cuánto tiempo "
        "permanecieron afectados, igual que 'Eventos más prolongados' en Sección 2."
    )
    top_roads = roads.sort_values("n_reportes", ascending=False).head(15).copy()
    top_roads["label"] = top_roads["road_sector"].str.slice(0, 50) + " (" + top_roads["province"] + ")"
    fig_top_roads = go.Figure(go.Bar(
        x=top_roads["n_reportes"][::-1], y=top_roads["label"][::-1], orientation="h",
        marker_color=CATEGORICAL[0],
        text=top_roads["n_reportes"][::-1], textposition="outside", cliponaxis=False,
    ))
    fig_top_roads.update_layout(title="Top 15 tramos por N.º de boletines en los que aparecieron")
    fig_top_roads.update_xaxes(title="N.º de boletines", range=[0, top_roads["n_reportes"].max() * 1.15])
    base_layout(fig_top_roads, height=480)
    st.plotly_chart(fig_top_roads, width='stretch')
    chart_total_caption("boletines acumulados entre los 15 tramos mostrados", top_roads["n_reportes"].sum())
    detail_table(
        top_roads[["province", "road_sector", "road_status", "adverse_event", "n_reportes"]]
        .rename(columns={"province": "provincia", "road_sector": "tramo", "road_status": "estado",
                          "adverse_event": "tipo_de_evento", "n_reportes": "n_boletines"})
        .sort_values("n_boletines", ascending=False),
        key="tbl_vias_recurrentes",
    )

    st.markdown("---")

    # -------------------------------------------------------------------
    # Duración de cierres (proxy)
    # -------------------------------------------------------------------
    st.subheader("¿Las vías cerradas tardan más en resolverse que las parcialmente habilitadas?")
    st.caption(
        "`n_reportes` del ÚLTIMO estado conocido de cada tramo como proxy de duración — no es el "
        "historial completo de transiciones (esta tabla no lo conserva), así que es una "
        "aproximación: cuántos boletines pasó cada tramo en el estado en que quedó."
    )
    duration_status = roads.groupby("road_status")["n_reportes"].agg(mediana="median", promedio="mean", n="size").reset_index()
    fig_road_duration = go.Figure(go.Bar(
        x=duration_status["mediana"], y=duration_status["road_status"], orientation="h",
        marker_color=[CATEGORICAL[7] if s == "Cerrada" else CATEGORICAL[3] for s in duration_status["road_status"]],
        text=[f"{v:.1f}" for v in duration_status["mediana"]], textposition="outside", cliponaxis=False,
    ))
    fig_road_duration.update_layout(title="Mediana de boletines por tramo, según su último estado")
    fig_road_duration.update_xaxes(title="Mediana de n.º de boletines",
                                    range=[0, duration_status["mediana"].max() * 1.3])
    base_layout(fig_road_duration, height=260)
    st.plotly_chart(fig_road_duration, width='stretch')
    chart_total_caption("tramos comparados", duration_status["n"].sum())
    detail_table(
        duration_status.rename(columns={"road_status": "estado", "n": "n_tramos"})
        .round({"mediana": 1, "promedio": 1}),
        key="tbl_vias_duracion",
    )
