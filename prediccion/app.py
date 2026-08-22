"""
Modelo predictivo — Eventos Adversos (Sección 2, SNGR Ecuador)

1. Datos y pipeline   — qué entra, cómo se deduplica/extrae, qué sale.
2. Arquitectura        — diagrama de las etapas del pipeline.
3. Modelo predictivo   — Random Forest: predice la probabilidad de cada
                          tipo de evento dado mes/provincia/zona.

Ejecutar con:
    ./venv/bin/streamlit run app.py
"""
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import model as m
from build_dataset import IMPACT_WEIGHTS

CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
               "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
OTHER_GRAY = "#898781"
TEXT_PRIMARY = "#0b0b0b"
GRID = "#e1e0d9"

st.set_page_config(page_title="Modelo Predictivo — Eventos Adversos SNGR", layout="wide")

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent / "data"))
FEATURES_PATH = DATA_DIR / "eventos_features.parquet"
STATS_PATH = DATA_DIR / "pipeline_stats.json"

MONTH_NAMES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
               "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


@st.cache_data
def load_features():
    if not FEATURES_PATH.exists():
        return pd.DataFrame()
    df = pd.read_parquet(FEATURES_PATH)
    df["event_start_date"] = pd.to_datetime(df["event_start_date"], errors="coerce")
    return df


@st.cache_data
def load_stats():
    if not STATS_PATH.exists():
        return {}
    with open(STATS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def base_layout(fig, height=420):
    fig.update_layout(
        height=height, plot_bgcolor="#fcfcfb", paper_bgcolor="rgba(0,0,0,0)",
        font_color=TEXT_PRIMARY, margin=dict(l=10, r=10, t=50, b=10), legend_title_text="",
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False)
    return fig


df = load_features()
stats = load_stats()

st.title("Modelo Predictivo — Eventos Adversos (Sección 2)")

if df.empty:
    st.error(
        f"No se encontró `{FEATURES_PATH}`. Ejecuta primero:\n\n"
        "```\ncd dashboard && python build_dataset.py\n"
        "cd ../prediccion && python build_dataset.py\n```"
    )
    st.stop()

section = st.sidebar.radio(
    "Sección",
    ["Datos y pipeline", "Arquitectura", "Modelo predictivo"],
)

# ===========================================================================
# SECCIÓN 1 — Datos y pipeline
# ===========================================================================
if section == "Datos y pipeline":
    st.header("Datos y pipeline de construcción")
    st.markdown(
        "Cada evento de la Sección 2 aparece repetido en decenas de boletines mientras "
        "sigue activo; se deduplica (exacta + difusa) y se extraen cifras de impacto del "
        "texto libre hasta llegar a un dataset de eventos únicos, uno por fila."
    )

    if stats:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Apariciones crudas", f"{stats['n_raw_apariciones']:,}")
        c2.metric("Eventos exactos", f"{stats['n_eventos_exactos']:,}")
        c3.metric("Fusiones difusas", f"{stats['n_fusiones_difusas']:,}")
        c4.metric("Eventos únicos", f"{stats['n_eventos_unicos']:,}")
        c5.metric("Tasa de escalamiento", f"{stats['tasa_escalamiento']:.1%}")

    st.subheader("Distribución por tipo de evento")
    order = df["event_type"].value_counts().index.tolist()
    cmap = {et: (CATEGORICAL[i] if i < len(CATEGORICAL) else OTHER_GRAY) for i, et in enumerate(order)}
    fig = px.bar(df["event_type"].value_counts().reset_index(), x="event_type", y="count",
                 color="event_type", color_discrete_map=cmap)
    fig.update_layout(showlegend=False)
    st.plotly_chart(base_layout(fig, 380), use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Índice de impacto pico (escala log)")
        fig = px.histogram(df, x=np.log1p(df["peak_impact_score"]), nbins=40,
                            color_discrete_sequence=[CATEGORICAL[0]])
        fig.update_layout(xaxis_title="log(1 + índice de impacto)", yaxis_title="Eventos")
        st.plotly_chart(base_layout(fig, 360), use_container_width=True)
    with col2:
        st.subheader("Escalamiento por tipo de evento (top 8)")
        top8 = order[:8]
        rate = df[df["event_type"].isin(top8)].groupby("event_type")["escalamiento"].mean().reindex(top8)
        fig = px.bar(rate.reset_index(), x="event_type", y="escalamiento",
                     color="event_type", color_discrete_map=cmap)
        fig.update_layout(showlegend=False, yaxis_tickformat=".0%", yaxis_title="% que escala")
        st.plotly_chart(base_layout(fig, 360), use_container_width=True)

    with st.expander("Pesos del índice de impacto (ilustrativo, no oficial del SNGR)"):
        w = pd.DataFrame(sorted(IMPACT_WEIGHTS.items(), key=lambda x: -x[1]),
                          columns=["categoría", "peso"])
        st.dataframe(w, hide_index=True, use_container_width=True)

    st.subheader("Muestra del dataset de eventos únicos")
    show_cols = ["event_type", "province", "zone", "event_start_date", "n_exact_variants",
                 "n_snapshots_total", "initial_impact_score", "peak_impact_score", "escalamiento"]
    st.dataframe(df[show_cols].sort_values("event_start_date", ascending=False).head(200),
                 use_container_width=True, hide_index=True)

# ===========================================================================
# SECCIÓN 2 — Arquitectura
# ===========================================================================
elif section == "Arquitectura":
    st.header("Arquitectura del pipeline y del modelo")
    st.markdown(
        "De los 2 865 JSON fuente a la predicción: extracción + dedup exacta → dedup "
        "difusa → extracción de impactos → dataset de eventos únicos → tabla de "
        "probabilidad por mes/provincia/zona."
    )

    st.markdown(
        """
<style>
.flow-box{border:1px solid #d8d6cf;border-radius:10px;padding:12px 16px;margin:5px 0;
  background:#fafaf8;}
.flow-box b{color:#0b0b0b;}
.flow-box span{color:#52514e;font-size:0.9em;}
.flow-arrow{text-align:center;color:#898781;font-size:1.2em;margin:-2px 0;}
.flow-stage-label{font-size:0.76em;text-transform:uppercase;letter-spacing:.04em;
  color:#2a78d6;font-weight:600;margin-bottom:2px;}
</style>

<div class="flow-box">
<div class="flow-stage-label">Fuente</div>
<b>2 865 JSON de reportes SNGR</b> <span>— Sección 2, eventos adversos por zona</span>
</div>
<div class="flow-arrow">↓</div>

<div class="flow-box">
<div class="flow-stage-label">dashboard/build_dataset.py</div>
<b>eventos_raw.csv — 42 628 apariciones</b> <span>(evento × boletín)</span>
</div>
<div class="flow-arrow">↓</div>

<div class="flow-box">
<div class="flow-stage-label">Etapa 1 — dedup exacta</div>
<b>zona + tipo + fecha + location idénticos → 2 956 eventos exactos</b>
</div>
<div class="flow-arrow">↓</div>

<div class="flow-box">
<div class="flow-stage-label">Etapa 2 — dedup difusa (union-find)</div>
<b>fechas ≤5 días + similitud de texto ≥0.85 → 2 406 eventos únicos</b>
</div>
<div class="flow-arrow">↓</div>

<div class="flow-box">
<div class="flow-stage-label">Etapa 3 — extracción de impactos (regex)</div>
<b>índice de impacto compuesto + flags de `background`</b>
</div>
<div class="flow-arrow">↓</div>

<div class="flow-box">
<div class="flow-stage-label">eventos_features.parquet</div>
<b>2 406 filas — un evento único por fila, con su mes/provincia/zona/tipo</b>
</div>
<div class="flow-arrow">↓</div>

<div class="flow-box">
<div class="flow-stage-label">model.py — train_event_type_classifier</div>
<b>Random Forest (estación del año + provincia + zona → 20 tipos de evento)</b>
</div>
<div class="flow-arrow">↓</div>

<div class="flow-box">
<div class="flow-stage-label">Modelo</div>
<b>Accuracy≈0.65 (top-1) · 0.81 (top-3) — vs. 0.39 de línea base</b>
</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        "Se entrena con `scikit-learn` (`RandomForestClassifier`, 600 árboles, one-hot "
        "sobre estación/provincia/zona) y se evalúa contra una línea base ('siempre "
        "predecir el tipo más frecuente'). El mes se agrupa en 4 estaciones (DEF/MAM/"
        "JJA/SON) porque mes crudo + Random Forest daba menos accuracy (muy pocos "
        "eventos por combinación mes×provincia); con regresión logística en vez de "
        "Random Forest, accuracy≈0.62 en vez de 0.65."
    )

# ===========================================================================
# SECCIÓN 3 — Modelo predictivo
# ===========================================================================
else:
    st.header("Probabilidad de eventos por mes, provincia y zona")
    st.markdown(
        "Random Forest entrenado con scikit-learn: a partir de (mes, provincia, zona) "
        "predice la probabilidad de cada uno de los 20 tipos de evento. Entrenado y "
        "evaluado con split temporal (80% eventos más antiguos "
        "para entrenar, 20% más recientes para evaluar)."
    )

    @st.cache_resource
    def get_event_type_model(_df):
        return m.train_event_type_classifier(_df)

    res = get_event_type_model(df)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Accuracy (top-1)", f"{res.accuracy:.1%}")
    c2.metric("Accuracy (top-3)", f"{res.top3_accuracy:.1%}",
              help="El tipo real está entre los 3 más probables que predice el modelo")
    c3.metric("Log loss", f"{res.log_loss:.3f}",
              help="Más bajo es mejor")
    c4.metric("Línea base", f"{res.baseline_accuracy:.1%}",
              help="Accuracy de predecir siempre el tipo más frecuente (Inundación)")

    st.divider()
    st.subheader("Probar una combinación")
    c1, c2, c3 = st.columns(3)
    month_opt = c1.selectbox("Mes", list(range(1, 13)), format_func=lambda x: MONTH_NAMES[x])
    province_opt = c2.selectbox("Provincia", sorted(df["province"].dropna().unique()))
    zone_opt = c3.selectbox("Zona SNGR", sorted(df["zone"].dropna().unique()))

    tbl = m.predict_event_type_probabilities(res.pipeline, res.classes, month_opt, province_opt, zone_opt)
    order = tbl["event_type"].tolist()
    cmap = {et: (CATEGORICAL[i] if i < len(CATEGORICAL) else OTHER_GRAY) for i, et in enumerate(order)}
    fig = px.bar(tbl.head(10), x="event_type", y="probability", color="event_type",
                 color_discrete_map=cmap, text=tbl.head(10)["probability"].map(lambda p: f"{p:.0%}"))
    fig.update_layout(showlegend=False, yaxis_tickformat=".0%",
                       xaxis_title="", yaxis_title="Probabilidad predicha")
    st.plotly_chart(base_layout(fig, 400), use_container_width=True)

    show = tbl.rename(columns={"event_type": "Tipo de evento", "probability": "Probabilidad"})
    show["Probabilidad"] = show["Probabilidad"].map(lambda p: f"{p:.1%}")
    st.dataframe(show, hide_index=True, use_container_width=True)
