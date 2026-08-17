# Trazabilidad — de PDF a JSON (reportes SNGR 2022–2026)

Esta carpeta documenta **de dónde salen los JSON** que usan las dos apps de
`docker_app/` (`dashboard/data/` y `pdf_review/data/json/`), para que quede
registro de todo el pipeline aunque solo se comparta el resultado final.

No es una app que se ejecute: es evidencia/documentación. La mayoría de los
`.py` mencionados abajo **no se copiaron aquí** (viven en la máquina donde
se hizo el procesamiento) — se referencian por su ruta original, así que
esas rutas solo son válidas en esa máquina, no en la de quien reciba esta
carpeta. La excepción es `codigo/`: ahí sí hay una **muestra** (un script de
cada tipo, no todos) copiada tal cual, para que quede al menos un ejemplo
concreto del código sin depender de esas rutas — ver sección 0.

## 0. Web SNGR → PDF (scraping)

Antes del primer paso de los pipelines de abajo, los PDF se descargaron del
sitio de la SNGR con scraping (`requests` + `BeautifulSoup`/`lxml`): se
extraen los enlaces `.pdf` de la página de listado de reportes y se
descargan los que todavía no están en disco, guardando metadata (nombre,
url, año, fecha del reporte) en un CSV incremental.

**4 URL de listado en total** — una por año, salvo 2025/2026 que comparten
la misma página:

| Año(s) | URL |
|---|---|
| 2022 | `gestionderiesgos.gob.ec/reportes-de-monitoreo-de-amenazas-y-eventos-peligrosos-2022/` |
| 2023 | `gestionderiesgos.gob.ec/reportes-de-monitoreo-de-amenazas-y-eventos-peligrosos-2023/` |
| 2024 | `gestionderiesgos.gob.ec/reportes-de-monitoreo-de-amenazas-y-eventos-peligrosos/` (sin sufijo de año) |
| 2025 y 2026 (misma página) | `gestionderiesgos.gob.ec/reportes-de-monitoreo-de-amenazas-y-eventos-peligrosos-2025/` |

Muestra copiada en `codigo/01_scraping_muestra.py` (desde `scraper.py`, sin
modificar). Hay variantes por año con el mismo enfoque
(`spider_2022.py` … `spider_2026.py` + `downloader.py`) en la ruta original
(no copiadas, solo esta muestra):

`/home/tomagochito/Documentos/ESPOL/semestre8/metodologia de la investigacion en computacion/proyecto/`
*(ruta original, solo válida en esta máquina — es del proyecto de la materia
de ESPOL, no de `MIC/datos/`)*

## Dos pipelines

Hay **dos pipelines distintos**, según si el PDF de origen tiene texto
seleccionable o no.

### A. PDF con texto seleccionable (2023–2026)

```
PDF (texto seleccionable)
   │  pdftotext -layout                 ← texto plano, preserva columnas/tablas
   │  + PyMuPDF (fitz)                  ← detecta los iconos de color de la
   │                                       columna de valoración y los reemplaza
   │                                       por [ROJO]/[AMARILLO]/[VERDE]/...
   │                                       según su color RGB (ver COLOR_MAP en
   │                                       los scripts de la sección 1)
   ▼
TXT  ──────────────────► txt/20XX/reportes_20XX_txt.zip   (incluido aquí)
   │  procesado por ChatGPT (Project "MIC Procesamiento")
   │  usando el prompt de PROMPT.txt (incluido aquí)
   ▼
JSON (un JSON por TXT, mismo nombre base)
   │  el JSON se vuelve a meter al mismo Project para que ChatGPT
   │  detecte inconsistencias/errores sobre el propio JSON ya
   │  generado y los corrija (empaquetado en SNGR_extracted_json*.zip
   │  → correcciones → 1875.zip)
   ▼
dashboard/data/*.parquet  +  pdf_review/data/json/*.json
```

### B. PDF con texto NO seleccionable / escaneado (2022, y 365 PDF de 2023)

```
PDF (escaneado, sin capa de texto)
   │  MinerU (https://mineru.net), subido por la web en lotes de 20 PDF
   │  (límite de carga de la interfaz web) — hace OCR + estructura tablas
   ▼
Markdown (descargable de MinerU, uno por PDF)
   │  se pide a ChatGPT Plus (uso directo, no el Project) que extraiga
   │  la valoración (columna de color VERDE/AMARILLO/ROJO) y corrija
   │  columnas con errores de OCR — mismo criterio de color que en A
   ▼
Markdown "valorado"
   │  se manda de nuevo a ChatGPT (mismo Project "MIC Procesamiento")
   │  para que extraiga el JSON final
   ▼
JSON
```

**Diferencia clave:** al pipeline B **no se le hace ninguna revisión/corrección
extra después de generado el JSON** — no pasa por el paso de "volver a meter
el JSON al Project para detectar y arreglar errores nuevos" que sí tiene el
pipeline A.

Ver sección 3 (2022) y sección 5 (365 PDF de 2023) para el detalle de cómo se
aplicó el pipeline B en cada caso.

## Contenido

```
trazabilidad/
├── README.md                                        ← este archivo
├── PROMPT.txt                                       ← prompt exacto usado en ChatGPT para generar los JSON
├── txt/                                              ← TXT fuente (pipeline A), un subcarpeta por año
│   ├── 2023/  (341 .txt) + reportes_2023_txt.zip
│   ├── 2024/  (603 .txt) + reportes_2024_txt.zip
│   ├── 2025/  (659 .txt) + reportes_2025_txt.zip
│   └── 2026/  (272 .txt) + reportes_2026_txt.zip
├── markdown/                                         ← Markdown "valorado" (pipeline B), un subcarpeta por año
│   ├── 2022/  (625 .md) + markdown_2022.zip          ← ver sección 3, ya integrado a JSON
│   └── 2023/  (365 .md) + markdown_2023.zip          ← ver sección 5, ya integrado a JSON
└── codigo/                                           ← muestras de código (ver sección 0), no todo el pipeline
    ├── 01_scraping_muestra.py                        ← Web SNGR → PDF
    └── 02_pdf_a_txt_valorado_muestra.py              ← PDF → TXT valorado (pipeline A)
```

**Ya no quedan PDF sin JSON**: los 1875 JSON de 2023–2026 más los 625 de 2022
y los 365 pendientes de 2023 ya están en `pdf_review/data/json/`.

## 1. Cómo se generaron los TXT (PDF → TXT, pipeline A)

Código usado, **en su ruta original** (no incluido en esta carpeta, salvo la
muestra de 2025 copiada en `codigo/02_pdf_a_txt_valorado_muestra.py`). Todos
siguen el mismo patrón: `pdftotext -layout` para el texto plano +
**PyMuPDF (`fitz`)** para detectar los iconos de color de la tabla de
valoración (mapeados por su color RGB a `[ROJO]`/`[AMARILLO]`/`[VERDE]`/...
vía un `COLOR_MAP` en el propio script) y reemplazarlos en el texto en el
orden en que aparecen:

| Año | Script | Notas |
|---|---|---|
| 2022 | `/home/tomagochito/Documentos/MIC/datos/scripts/procesar_2022.py` | **Intento abandonado**: usa el mismo enfoque (`pdftotext -layout` + PyMuPDF) pero nunca llegó a generar salida (`reportes_2022_txt/` no existe) — los PDF de 2022 resultaron no tener texto seleccionable, así que 2022 terminó yendo por el pipeline B (MinerU, ver sección 3) |
| 2023 | `/home/tomagochito/Documentos/MIC/datos/2023/extraer_texto_con_iconos.py`, `/home/tomagochito/Documentos/MIC/datos/2023/procesar_solo_texto.py` | Si `pdftotext` falla o produce muy poco texto, usa como respaldo el texto extraído directamente con PyMuPDF |
| 2024 | (mismo enfoque que 2023; ver `/home/tomagochito/Documentos/MIC/datos/2024/`) | No se identificó un script propio por año en esa carpeta |
| 2025 | `/home/tomagochito/Documentos/MIC/datos/2025/extraer_texto_con_iconos_2025.py`, `/home/tomagochito/Documentos/MIC/datos/2025/extraer_docx_con_iconos.py` | Incluye variante para reportes en `.docx` |
| 2026 | `/home/tomagochito/Documentos/MIC/datos/2026/extraer_texto_con_iconos.py` | — |

Carpetas de trabajo con los PDF/TXT/JSON intermedios de cada año (también en
la máquina original, no copiadas aquí):

- `/home/tomagochito/Documentos/MIC/datos/2022/` … `/home/tomagochito/Documentos/MIC/datos/2026/`
- `/home/tomagochito/Documentos/MIC/datos/2023-2026/` (vista consolidada)

## 2. Cómo se generaron los JSON (TXT → JSON, vía ChatGPT, pipeline A)

Los TXT de `txt/` se subieron (zipeados por año) al **Project** de
ChatGPT **"MIC Procesamiento"**, usando el prompt de `PROMPT.txt` (reglas de
extracción: estructura exacta del JSON, no inventar datos, preservar
`"--"`/`"---"` literalmente, un JSON por TXT, etc.). Es una carpeta de
proyecto (ChatGPT Projects), no una conversación suelta: agrupa todas las
conversaciones/lotes donde se fue procesando cada año.

**Project folder:** https://chatgpt.com/g/g-p-6a7fd946e4e88191b8abcfc3cbfb10cd-mic-procesamiento/project

De ahí salieron los `SNGR_extracted_json*.zip` (por año/lote). Ese JSON se
volvió a meter al mismo Project para que ChatGPT revisara el propio JSON ya
generado, detectara inconsistencias o errores nuevos y los corrigiera —
este paso de re-revisión es exclusivo del pipeline A, hasta llegar al
`1875.zip` final usado por `dashboard/` y `pdf_review/` (ver
`docker_app/README.md`, sección "Notas sobre los datos").

## 3. Año 2022 — pipeline B

A diferencia de 2023–2026, el año 2022 **no pasó por TXT**: siguió el
pipeline B (ver arriba) porque sus PDF no tienen texto seleccionable (el
intento de usar `pdftotext` para 2022, `procesar_2022.py`, no llegó a
generar salida — sección 1). El resultado intermedio son archivos
**Markdown** (uno por reporte PDF), organizados por lotes, en:

`/home/tomagochito/Documentos/MIC/datos/2022/resultados_markdown_pdf/`
*(ruta original, no copiada aquí — igual que el resto de rutas de esta
sección, solo válida en la máquina donde se hizo el procesamiento)*

```
resultados_markdown_pdf/
├── lote1markdown_corregido.zip     (160 .md)
├── lote2markdown_corregido.zip     (182 .md)
├── lote3markdown_completado.zip    (189 .md)
└── lote4markdown_corregido.zip     ( 94 .md)
```

**Herramienta de extracción:** [MinerU](https://github.com/opendatalab/MinerU)
(OCR + estructuración de tablas para PDF → Markdown). Se confirma por las
imágenes referenciadas dentro de los `.md` (`cdn-mineru.openxlab.org.cn/...`),
que son recortes de tabla que MinerU no logró convertir a texto y dejó como
imagen embebida.

**Qué se hizo con ChatGPT Plus (no el Project, sino uso directo) sobre estos
Markdown:** extraer las **valoraciones** (columna de color VERDE/AMARILLO/ROJO)
y corregir columnas con errores de OCR en dos tablas específicas de la
Sección 1 (Threat Monitoring) — las únicas dos tablas del schema que tienen
una columna de valoración. Este paso de valoración con ChatGPT Plus es el
mismo para todo el pipeline B (2022 y, más adelante, los 365 de 2023 —
sección 5); a diferencia del pipeline A, el JSON que resulta de este flujo
**no se vuelve a revisar** en busca de errores nuevos:

- **`PELIGRO VOLCÁNICO`** (`volcanic_hazard` en el JSON — columna `current_assessment`)
- **`PELIGRO POR APERTURA Y/O COLAPSO DE PRESAS Y REPRESAS`** (`dams_and_reservoirs` en el JSON — columna `assessment`)

Los Markdown valorados de 2022 sí se pasaron al Project de ChatGPT
"MIC Procesamiento" para extraer el JSON completo (mismo paso de la sección
2). El resultado son los **625 JSON de 2022** (`manifest.json` interno:
`total_txt: 625, processed_ok: 625, failed: 0`, mismo schema que
2023–2026), ya **integrados** en `dashboard/data/` y `pdf_review/data/json/`
— confirmado 1:1 contra los 625 `.md` de `markdown/2022/`. Ese resultado
(originalmente `SNGR_extracted_json(6).zip`) ya está en
`pdf_review/data/json/`, así que no se dejó una copia aparte aquí.

## 4. PDFs de 2023 sin JSON generado (histórico — ya resuelto)

En su momento se detectaron **366 PDF de 2023** que existían en
`pdf_review/data/pdfs/reportes_2023_pdf/` (707 en total) pero que **no
tenían** un JSON correspondiente en `pdf_review/data/json/` (341 en total
para 2023, entre las dos convenciones de nombre que usa ese año:
`reporte_2023_NNN` y `Reporte-de-Monitoreo-Nacional-NNNN-DDMM2023-...`).

Se identificaron comparando el nombre base (sin extensión) de cada PDF de
2023 contra el de cada JSON de 2023; los que no tenían coincidencia exacta
se copiaron a una carpeta `pendiente/` (ya eliminada — era una copia
temporal, el original siempre estuvo intacto en `reportes_2023_pdf/`) para
poder revisarlos y mandarlos al Project de ChatGPT (TXT→JSON, sección 2).

```
707 PDF 2023  −  341 JSON 2023 (con nombre coincidente)  =  366 PDF pendientes en ese momento
```

### Lotes para MinerU

Se armaron los **366 PDF completos** repartidos en lotes de 20 para subir a
[MinerU](https://mineru.net) desde la web (que limita cuántos archivos
acepta por carga):

```
lotes_mineru_2023/
├── lote01/ … lote09/   (20 PDF cada uno — segunda mitad, PDF nº184–366)
├── lote10/              ( 3 PDF — resto de la segunda mitad)
├── lote11/ … lote19/   (20 PDF cada uno — primera mitad, PDF nº1–183)
└── lote20/              ( 3 PDF — resto de la primera mitad)
```

Se armó primero la segunda mitad (`lote01`–`lote10`, ver más abajo el
resultado ya procesado por MinerU en `../markdown/` y `../pdfs/` dentro de
`/home/tomagochito/Documentos/pendiente2023/`) y después se completó con la
primera mitad (`lote11`–`lote20`), así que entre los 20 lotes cubren los
366 PDF pendientes sin duplicar ni dejar ninguno fuera (verificado: la unión
de todos los lotes coincide 1:1, sin duplicados, con los 366 archivos de
`pendiente/`).

### Incidencias detectadas al revisar los resultados de MinerU (117, 297, 401)

Al comparar los `.md` que devolvió MinerU contra los 366 PDF pendientes,
salieron 3 sin markdown correspondiente. Revisando cada uno:

- **`reporte_2023_117.pdf`** — **no es un reporte de monitoreo** (es otro tipo
  de documento que quedó mezclado en la descarga masiva de PDFs de 2023).
  Se descartó del pipeline: se quitó de `pendiente/` y de
  `lotes_mineru_2023/lote16/` (queda intacto, sin tocar, en la colección
  maestra `pdf_review/data/pdfs/reportes_2023_pdf/`, solo ya no se procesa
  como si fuera un reporte).

- **`reporte_2023_297.pdf`** y **`reporte_2023_401.pdf`** — **su contenido no
  correspondía al reporte real** (verificado por MD5: son archivos
  distintos a los correctos, y de tamaño muy distinto — p. ej. 297 pasó de
  888 KB a 6.5 MB). Esto expone que la numeración secuencial
  `reporte_2023_NNN` (asignada al descargar el lote de PDFs) **no es un
  identificador confiable** — se desalineó del número de reporte real en
  algún punto de esa descarga (el caso de 117 es la evidencia más clara: ni
  siquiera correspondía a un reporte). El nombre confiable es el que trae el
  propio PDF/reporte: `Reporte-de-Monitoreo-Nacional-NNNN-DDMMYYYY-...`.

  Se volvieron a descargar ambos con su nombre correcto y se sincronizaron
  en todos los lugares donde vivía la versión equivocada (incluida la
  carpeta temporal `pendiente/`, ya eliminada — mismo contenido, se dejó el
  nombre `reporte_2023_NNN` para no romper las referencias ya existentes,
  pero el **contenido** quedó corregido). El PDF con su nombre real
  (`Reporte-de-Monitoreo-Nacional-...pdf`) también quedó en la colección
  maestra `pdf_review/data/pdfs/reportes_2023_pdf/` junto al anterior.

  Sus markdown (`Reporte-de-Monitoreo-Nacional-0297-29052023-09h00.md` y
  `...-0401-20072023-09h00.md`) y PDF ya están incorporados a
  `/home/tomagochito/Documentos/pendiente2023/markdown/` y `.../pdfs/`
  *(ruta original, no copiada aquí)*, que ahora tiene **185** pares
  markdown+PDF verificados 1:1 (los 183 de la segunda mitad + estos 2).

**Lección para el resto de lotes (11–20, primera mitad, aún sin procesar):**
al validar sus resultados de MinerU conviene comprobar también por
contenido/tamaño, no solo por nombre — la desalineación de numeración que
causó esto puede repetirse en otros PDF de esa lista.

*(Actualización: los 20 lotes ya se procesaron. Ver sección 5.)*

## 5. Los 365 PDF de 2023 — Markdown completo y "valorado"

Los 20 lotes de `lotes_mineru_2023/` (sección 4) se subieron completos a
MinerU y se armó el par Markdown+PDF para los **365 PDF pendientes** (366
menos el `117` descartado) en
`/home/tomagochito/Documentos/pendiente2023/markdown/` y `.../pdfs/`
*(ruta original, no copiada aquí)* — verificado 1:1, sin faltantes.

Después, igual que se hizo con 2022 (sección 3), esos 365 Markdown se
llevaron a ChatGPT Plus para que **extrajera las valoraciones y corrigiera
columnas** de las tablas con errores de OCR (mismo criterio: `PELIGRO
VOLCÁNICO` / `volcanic_hazard` y `PELIGRO POR APERTURA Y/O COLAPSO DE
PRESAS Y REPRESAS` / `dams_and_reservoirs`), repartidos en 3 ZIPs (Markdown+PDF,
~467–474 MB cada uno, bajo el límite de subida) para no pasarse del límite
de tamaño. El resultado — 365 Markdown "valorados" — se consolidó en un solo
ZIP:

Ese resultado (originalmente
`/home/tomagochito/Documentos/pendiente2023/markdown_2023_valorados_365.zip`)
es justamente `markdown/2023/` — 365 archivos `.md`, verificados uno a uno
contra la lista original de pendientes (mismo nombre, sin faltantes ni
duplicados).

Estos 365 Markdown ya se pasaron por el Project oficial "MIC Procesamiento"
(sección 2) para generar el JSON final, y ya están **integrados** en
`dashboard/data/` y `pdf_review/data/json/`.

## 6. Reportes 2024 sin recuperar — descarga original corrupta

Dos boletines de 2024 (`reporte_2024_481.pdf` y `reporte_2024_552.pdf`, sin
número/fecha de reporte real identificado) tenían el mismo problema tanto en
`pdf_review/data/pdfs/reportes_2024_pdf/` como en la copia fuente
`/home/tomagochito/Documentos/MIC/datos/2024/reportes_2024_pdfs/` (mismo
MD5): el archivo `.pdf` en realidad era una **imagen JPEG** — el banner de
fotos institucionales que la SNGR pone como cabecera de cada boletín (volcán,
inundación, sala de monitoreo, torre de sensores, personal, terremoto, sala
de control, tsunami), no el reporte con contenido. La descarga original se
cortó y solo capturó esa imagen de cabecera.

Como no aportaban ningún dato recuperable, **se eliminaron** de ambas
ubicaciones (15 ago 2026). No hay JSON para estos dos boletines ni lo habrá
hasta recuperar el PDF real desde la fuente original de la SNGR — no fue
posible identificar su número de reporte o fecha exacta a partir del archivo
corrupto.
