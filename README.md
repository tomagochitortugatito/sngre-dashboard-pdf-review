# docker_app — Monitoreo SNGR (Ecuador)

Carpeta con dos aplicaciones Streamlit dockerizadas, más una carpeta de
trazabilidad documental. Las apps (`dashboard/`, `pdf_review/`) no dependen
de rutas absolutas de ninguna máquina: puedes copiar/mover/compartir esta
carpeta completa (por USB, red, etc.) y funcionan igual en cualquier equipo
con Docker instalado. La única excepción es `trazabilidad/README.md`, que
cita rutas absolutas de la máquina de origen a propósito (ver esa carpeta) —
son solo referencia documental, no afectan a `docker compose up`.

> **⚠️ Este repo NO incluye los PDFs originales** (pesan ~6,3 GB, no caben
> en GitHub). Se descargan aparte desde Google Drive — ver la sección
> **[PDFs (descarga aparte)](#pdfs-descarga-aparte)** más abajo antes de
> levantar `pdf_review`.

## Contenido

```
docker_app/
├── docker-compose.yml          ← levanta las dos apps de una vez
├── dashboard/                  ← "Dashboard de Eventos Adversos" (Streamlit + Plotly)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py
│   ├── build_dataset.py        ← script que regenera los datos desde los JSON fuente
│   └── data/                   ← .parquet/.csv ya generados (listos para usar)
├── pdf_review/                 ← "Visor comparativo PDF ↔ JSON"
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py
│   └── data/
│       ├── json/                ← 2865 reportes JSON fuente (SNGR, 2022–2026)
│       └── pdfs/                ← VACÍO en este repo — descargar de Drive, ver abajo
│           ├── reportes_2022_pdf/
│           ├── reportes_2023_pdf/
│           ├── reportes_2024_pdf/
│           ├── reportes_2025_pdf/
│           └── reportes_2026_pdf/
└── trazabilidad/                ← documentación: de dónde salen esos JSON (Web→PDF→TXT→JSON)
    ├── README.md                              ← detalle del pipeline y rutas del código usado
    ├── PROMPT.txt                             ← prompt usado en ChatGPT para generar los JSON
    ├── codigo/                                ← muestra de código (scraping, PDF→TXT valorado)
    ├── txt/                                   ← TXT fuente 2023–2026, por año
    └── markdown/                               ← Markdown valorado 2022 y 2023, por año
```

## PDFs (descarga aparte)

Los 2865 PDFs originales (2022–2026, ~6,3 GB) **no están en este repo**, solo
sus JSON extraídos (`pdf_review/data/json/`) y las carpetas vacías donde
deben ir. Están subidos a Google Drive:

🔗 **https://drive.google.com/drive/folders/11IKLl6i6clk2uvVzKr3WMJwiSbQyzdUV?usp=sharing**

**Pasos para dejar `pdf_review` funcional:**

1. Descarga las 5 carpetas del Drive (`reportes_2022_pdf` … `reportes_2026_pdf`).
2. Colócalas dentro de `pdf_review/data/pdfs/`, respetando el nombre exacto
   de cada carpeta, de modo que quede así:

   ```
   pdf_review/data/pdfs/
   ├── reportes_2022_pdf/   ← los .pdf de 2022 van aquí
   ├── reportes_2023_pdf/
   ├── reportes_2024_pdf/
   ├── reportes_2025_pdf/
   └── reportes_2026_pdf/
   ```

3. El nombre de cada PDF debe coincidir con el JSON correspondiente en
   `pdf_review/data/json/` (mismo `reporte_<año>_<n>`, solo cambia la
   extensión: `.json` ↔ `.pdf`) — así la app "Visor comparativo PDF ↔ JSON"
   puede emparejarlos automáticamente.
4. Levanta la app normalmente (ver [Cómo levantarlo](#cómo-levantarlo)); el
   contenedor `pdf-review` monta `./pdf_review` completo, así que apenas
   copies los PDFs ahí quedan disponibles sin rebuild.

## Requisitos

- Docker Engine + el plugin `docker compose` (Docker Desktop en Windows/Mac
  ya lo trae; en Linux: `sudo apt install docker-compose-plugin` o similar).
- ~500 MB libres de disco para este repo + ~6,3 GB adicionales si descargas
  todos los PDFs del Drive (ver sección anterior).
- Puertos **8502** y **8503** libres en el equipo donde se ejecute.

## Cómo levantarlo

Desde dentro de esta carpeta (`docker_app/`):

```bash
docker compose up -d --build
```

Esto construye ambas imágenes (solo la primera vez, o si cambias el código)
y arranca los contenedores en segundo plano.

Verifica que quedaron arriba:

```bash
docker compose ps
```

## Acceder a las apps

| App | URL |
|---|---|
| Dashboard de Eventos Adversos | http://localhost:8502 |
| Visor comparativo PDF ↔ JSON | http://localhost:8503 |

Si accedes desde otro equipo de la misma red, reemplaza `localhost` por la IP
de la máquina que corre Docker.

## Detener / reiniciar

```bash
docker compose down        # detiene y quita los contenedores (los datos en disco no se tocan)
docker compose up -d       # los vuelve a levantar
docker compose logs -f     # ver logs en vivo de ambos servicios
```

## Notas sobre los datos

- **`dashboard/data/`** ya trae los `.parquet`/`.csv` deduplicados, generados
  a partir de los 2865 JSON corregidos (los mismos que están en
  `pdf_review/data/json/`). No hace falta regenerarlos para usar el dashboard.
- Si quieres **regenerar** esos datos (por ejemplo tras corregir algún JSON
  fuente), corre dentro del contenedor:

  ```bash
  docker compose exec dashboard python build_dataset.py
  ```

  Por defecto lee de `../pdf_review/data/json` (montado dentro del
  contenedor en `/app/data/json` vía el propio `docker-compose.yml`, ya que
  `pdf_review` también se monta completo) y escribe en `dashboard/data/`.
  Ambas rutas son configurables con las variables de entorno
  `SOURCE_JSON_DIR` y `OUTPUT_DIR` si necesitas apuntarlas a otro lado.

- **`pdf_review`** usa las variables de entorno `JSON_DIR` y `PDF_ROOT`
  (definidas en `docker-compose.yml`) para saber dónde buscar los JSON y los
  PDFs; por defecto apuntan a `/app/data/json` y `/app/data/pdfs`, que dentro
  del contenedor son justo `pdf_review/data/json` y `pdf_review/data/pdfs`
  del host.

## Correr sin Docker (opcional)

Si prefieres correrlas directo con Python, cada carpeta trae su
`requirements.txt`:

```bash
cd dashboard   # o pdf_review
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/streamlit run app.py
```

En `pdf_review`, exporta `JSON_DIR`/`PDF_ROOT` antes de correrlo si quieres
que apunten a las carpetas locales en vez de a las rutas absolutas por
defecto:

```bash
JSON_DIR=./data/json PDF_ROOT=./data/pdfs ./venv/bin/streamlit run app.py
```

## Troubleshooting

- **Puerto ocupado (8502/8503):** edita `docker-compose.yml` y cambia el
  primer número de `ports: "8502:8501"` por el puerto libre que prefieras.
- **`docker compose` no reconocido:** en versiones viejas de Docker el
  comando es `docker-compose` (con guion), sin el plugin nuevo.

## Fuente de los datos

Los reportes originales (PDFs, y los JSON/TXT/Markdown derivados en
`pdf_review/` y `trazabilidad/`) provienen del **Servicio Nacional de Gestión
de Riesgos y Emergencias (SNGRE)** de Ecuador. Este proyecto reprocesa y
estructura esa información pública con fines de análisis y visualización;
no reemplaza ni sustituye las fuentes oficiales del SNGRE.

## Créditos

Proyecto realizado por:

- **Enrique Rosado** — egrosado@espol.edu.ec
- **Valeria Gutiérrez** — vaniguti@espol.edu.ec
- **Adrián Salamea** — asalamea@espol.edu.ec
- **Tomás Bolaños** — tbolanos@espol.edu.ec
- **Steven Barzola** — stabarz@espol.edu.ec

Escuela Superior Politécnica del Litoral (ESPOL), Guayaquil, Ecuador.
