# Modelo Predictivo — Eventos Adversos (Sección 2, SNGR Ecuador)

App de Streamlit que entrena modelos sobre los eventos adversos deduplicados
del dashboard (Sección 2 de los reportes SNGR) y expone 3 secciones: datos y
pipeline, arquitectura, y el modelo predictivo (Random Forest: probabilidad
de tipo de evento según mes, provincia y zona).

Depende de `dashboard/data/eventos_raw.csv` — hay que tener generado el
dashboard al menos una vez antes de levantar esta app (ver
`../README.md`).

## Contenido

```
prediccion/
├── Dockerfile
├── requirements.txt
├── build_dataset.py   ← pipeline: dedup exacta + difusa + extracción de impactos
├── model.py            ← preprocesamiento + entrenamiento de los modelos
├── app.py               ← la app Streamlit
└── data/                ← eventos_features.parquet + pipeline_stats.json (ya generados)
```

## Con Docker (recomendado)

Desde la raíz del repo (`docker_app/`), junto con las otras dos apps:

```bash
docker compose up -d --build
```

La app queda en **http://localhost:8504**. El contenedor monta
`dashboard/data` en modo solo-lectura para leer `eventos_raw.csv`
(`EVENTOS_RAW_CSV`, definido en `docker-compose.yml`).

Si aún no generaste los datos del dashboard, hazlo primero:

```bash
docker compose exec dashboard python build_dataset.py
```

## Sin Docker

```bash
cd prediccion
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/streamlit run app.py
```

Abre **http://localhost:8501**.

## Regenerar los datos (`eventos_features.parquet`)

Los `.parquet` en `data/` ya vienen generados y listos para usar. Si
cambiaste algo en el pipeline o en los JSON fuente, regenera en este orden
(el segundo paso depende del primero):

```bash
cd dashboard && python build_dataset.py    # regenera eventos_raw.csv
cd ../prediccion && python build_dataset.py # regenera eventos_features.parquet
```

Rutas configurables por variable de entorno si no usas la estructura por
defecto del repo:

- `EVENTOS_RAW_CSV` — por defecto `../dashboard/data/eventos_raw.csv`
- `OUTPUT_DIR` — por defecto `./data`

## Troubleshooting

- **"No se encontró eventos_features.parquet"** al abrir la app: corre
  `python build_dataset.py` dentro de `prediccion/` (ver arriba).
- **"No se encontró eventos_raw.csv"** al correr `prediccion/build_dataset.py`:
  corre primero `dashboard/build_dataset.py` (necesita los JSON fuente en
  `pdf_review/data/json/`, ver `../README.md`).
- **Puerto 8504 ocupado:** edita `docker-compose.yml`, servicio
  `prediccion`, y cambia el primer número de `ports: "8504:8501"`.
