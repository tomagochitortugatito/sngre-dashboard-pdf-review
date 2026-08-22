# Monitoreo de Eventos Adversos del SNGRE — Ecuador

Este repositorio contiene un conjunto de herramientas para el procesamiento, exploración, validación y análisis predictivo de los reportes de eventos adversos publicados por el **Servicio Nacional de Gestión de Riesgos y Emergencias (SNGRE) del Ecuador** para el período **2022–2026**.

La solución está compuesta por tres aplicaciones desarrolladas con **Streamlit** y desplegadas mediante **Docker**:

- **`dashboard/`** — Dashboard interactivo para la exploración y visualización de eventos adversos.
- **`pdf_review/`** — Visor comparativo entre los documentos PDF originales y los archivos JSON obtenidos a partir de ellos.
- **`prediccion/`** — Aplicación de análisis predictivo para estimar el tipo de evento en función del mes, la provincia y la zona.

Adicionalmente, el directorio **`trazabilidad/`** documenta el flujo de procesamiento mediante el cual se generaron los archivos JSON utilizados por las aplicaciones:

**Web → PDF → TXT → JSON**

Los servicios utilizan rutas relativas al repositorio y a sus respectivos contenedores, por lo que el proyecto puede copiarse o trasladarse a otro equipo sin modificar la configuración, siempre que el sistema de destino disponga de Docker.

La única excepción corresponde a `trazabilidad/README.md`, donde se conservan determinadas rutas absolutas de la máquina utilizada durante el procesamiento original con fines exclusivamente documentales. Estas rutas no intervienen en la ejecución de los servicios mediante Docker Compose.

> [!IMPORTANT]
> Los documentos PDF originales **no se incluyen en este repositorio** debido a su tamaño aproximado de **6,3 GB**.  
> Deben descargarse por separado desde Google Drive antes de utilizar el visor `pdf_review`. Consulte la sección [Descarga de los PDF originales](#descarga-de-los-pdf-originales).

---

## Estructura del repositorio

```text
sngre-dashboard-pdf-review/
├── docker-compose.yml
│
├── dashboard/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py
│   ├── build_dataset.py
│   └── data/
│       └── archivos .parquet y .csv preprocesados
│
├── prediccion/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py
│   ├── build_dataset.py
│   ├── model.py
│   ├── README.md
│   └── data/
│       └── eventos_features.parquet
│
├── pdf_review/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py
│   └── data/
│       ├── json/
│       │   └── 2865 reportes JSON (2022–2026)
│       └── pdfs/
│           ├── reportes_2022_pdf/
│           ├── reportes_2023_pdf/
│           ├── reportes_2024_pdf/
│           ├── reportes_2025_pdf/
│           └── reportes_2026_pdf/
│
└── trazabilidad/
    ├── README.md
    ├── PROMPT.txt
    ├── codigo/
    ├── txt/
    └── markdown/
```

### Componentes principales

#### Dashboard de Eventos Adversos

El directorio `dashboard/` contiene la aplicación principal de exploración de datos, desarrollada con **Streamlit** y **Plotly**.

Los conjuntos de datos procesados se encuentran en `dashboard/data/` y se incluyen preparados para su utilización, por lo que no es necesario ejecutar nuevamente el proceso de construcción del conjunto de datos para iniciar la aplicación.

#### Visor comparativo PDF ↔ JSON

El directorio `pdf_review/` contiene una aplicación destinada a verificar visualmente la correspondencia entre los reportes PDF originales y los archivos JSON estructurados derivados de ellos.

Los archivos JSON se incluyen en el repositorio. Los PDF, debido a su tamaño, deben descargarse por separado.

#### Modelo predictivo

El directorio `prediccion/` contiene la aplicación de análisis predictivo y su correspondiente proceso de preparación de características.

El modelo utiliza información derivada de los eventos adversos procesados por el dashboard y permite estimar el tipo de evento según variables temporales y geográficas.

Para información detallada sobre el procesamiento y entrenamiento de los modelos, consulte [`prediccion/README.md`](prediccion/README.md).

#### Trazabilidad de los datos

El directorio `trazabilidad/` documenta el procedimiento utilizado para transformar los reportes originales en los archivos estructurados utilizados por las aplicaciones.

Incluye:

- código empleado durante distintas etapas del procesamiento;
- archivos TXT y Markdown intermedios;
- el prompt utilizado para estructurar información mediante ChatGPT;
- documentación sobre el origen y transformación de los datos.

---

## Descarga de los PDF originales

Los **2865 documentos PDF correspondientes al período 2022–2026**, con un tamaño total aproximado de **6,3 GB**, no forman parte de este repositorio.

Los archivos pueden descargarse desde Google Drive:

**[Descargar PDF originales desde Google Drive](https://drive.google.com/drive/folders/11IKLl6i6clk2uvVzKr3WMJwiSbQyzdUV?usp=sharing)**

### Configuración de `pdf_review`

Para habilitar la comparación entre PDF y JSON:

1. Descargue las cinco carpetas disponibles en Google Drive:

   ```text
   reportes_2022_pdf
   reportes_2023_pdf
   reportes_2024_pdf
   reportes_2025_pdf
   reportes_2026_pdf
   ```

2. Copie las carpetas dentro de:

   ```text
   pdf_review/data/pdfs/
   ```

   La estructura resultante debe ser:

   ```text
   pdf_review/data/pdfs/
   ├── reportes_2022_pdf/
   ├── reportes_2023_pdf/
   ├── reportes_2024_pdf/
   ├── reportes_2025_pdf/
   └── reportes_2026_pdf/
   ```

3. Verifique que el nombre de cada archivo PDF coincida con el archivo JSON correspondiente ubicado en `pdf_review/data/json/`.

   Ambos archivos deben compartir el mismo identificador y diferenciarse únicamente por la extensión:

   ```text
   reporte_<año>_<n>.json
   reporte_<año>_<n>.pdf
   ```

   Esta correspondencia permite que el visor empareje automáticamente cada documento PDF con su representación JSON.

4. Inicie los servicios normalmente mediante Docker Compose. No es necesario reconstruir las imágenes después de copiar los PDF, ya que el directorio `pdf_review/` se monta como volumen dentro del contenedor.

---

## Requisitos

Para ejecutar el proyecto se requiere:

- **Docker Engine**.
- **Docker Compose v2**, disponible mediante el comando `docker compose`.
- Aproximadamente **500 MB de espacio disponible** para los archivos incluidos en el repositorio.
- Aproximadamente **6,3 GB adicionales** si se descargan todos los documentos PDF.
- Disponibilidad de los siguientes puertos:

| Puerto | Servicio |
|---:|---|
| `8502` | Dashboard de Eventos Adversos |
| `8503` | Visor comparativo PDF ↔ JSON |
| `8504` | Modelo Predictivo |

Docker Desktop para Windows y macOS incluye Docker Compose. En distribuciones Linux puede ser necesario instalar el complemento correspondiente, por ejemplo:

```bash
sudo apt install docker-compose-plugin
```

---

## Ejecución con Docker

Desde el directorio raíz del repositorio, ejecute:

```bash
docker compose up -d --build
```

El comando construye las imágenes de los tres servicios e inicia los contenedores en segundo plano.

Para comprobar su estado:

```bash
docker compose ps
```

---

## Acceso a las aplicaciones

Una vez iniciados los contenedores, las aplicaciones estarán disponibles en las siguientes direcciones:

| Aplicación | Dirección |
|---|---|
| Dashboard de Eventos Adversos | [http://localhost:8502](http://localhost:8502) |
| Visor comparativo PDF ↔ JSON | [http://localhost:8503](http://localhost:8503) |
| Modelo Predictivo — Eventos Adversos | [http://localhost:8504](http://localhost:8504) |

Para acceder desde otro equipo conectado a la misma red, sustituya `localhost` por la dirección IP del equipo donde se ejecuta Docker.

Por ejemplo:

```text
http://192.168.1.100:8502
```

---

## Administración de los servicios

### Detener los contenedores

```bash
docker compose down
```

Este comando detiene y elimina los contenedores, pero no modifica los datos almacenados en los directorios del repositorio.

### Iniciar nuevamente los servicios

```bash
docker compose up -d
```

### Consultar los registros

```bash
docker compose logs -f
```

El comando muestra en tiempo real los registros generados por los servicios.

---

## Datos y procesamiento

### Dashboard

El directorio `dashboard/data/` contiene los archivos `.parquet` y `.csv` previamente procesados a partir de los **2865 archivos JSON** disponibles en `pdf_review/data/json/`.

Estos archivos se incluyen preparados para su utilización, por lo que **no es necesario regenerarlos para ejecutar el dashboard**.

El script responsable de construir estos conjuntos de datos es:

```text
dashboard/build_dataset.py
```

Por defecto, el script utiliza como fuente:

```text
pdf_review/data/json/
```

y escribe los archivos generados en:

```text
dashboard/data/
```

Las rutas pueden modificarse mediante las siguientes variables de entorno:

- `SOURCE_JSON_DIR` — directorio que contiene los archivos JSON de origen.
- `OUTPUT_DIR` — directorio donde se almacenarán los conjuntos de datos generados.

> [!NOTE]
> La configuración actual de `docker-compose.yml` no monta `pdf_review/data/json/` dentro del contenedor `dashboard`. Por este motivo, la regeneración mediante `docker compose exec dashboard python build_dataset.py` requiere añadir previamente el volumen correspondiente al servicio `dashboard` o ejecutar el script desde un entorno Python local con acceso a la estructura completa del repositorio.

### Visor PDF ↔ JSON

El servicio `pdf_review` utiliza las siguientes variables de entorno, definidas en `docker-compose.yml`:

```text
JSON_DIR=/app/data/json
PDF_ROOT=/app/data/pdfs
```

Estas rutas corresponden respectivamente a:

```text
pdf_review/data/json/
pdf_review/data/pdfs/
```

en el sistema anfitrión.

### Modelo predictivo

El servicio `prediccion` utiliza como fuente:

```text
dashboard/data/eventos_raw.csv
```

El directorio `dashboard/data/` se monta dentro del contenedor del modelo en modo de solo lectura.

El repositorio ya incluye:

```text
prediccion/data/eventos_features.parquet
```

por lo que no es necesario reconstruir inicialmente el conjunto de características.

Para obtener información sobre la preparación de datos y el entrenamiento de los modelos, consulte [`prediccion/README.md`](prediccion/README.md).

---

## Ejecución sin Docker

Las aplicaciones también pueden ejecutarse directamente con Python.

Cada directorio contiene su propio archivo `requirements.txt`.

Por ejemplo:

```bash
cd dashboard

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

El procedimiento equivalente puede aplicarse a:

```text
dashboard/
pdf_review/
prediccion/
```

En Windows PowerShell, el entorno virtual puede activarse mediante:

```powershell
.\.venv\Scripts\Activate.ps1
```

### `pdf_review` sin Docker

Al ejecutar `pdf_review` directamente desde Python, pueden definirse explícitamente las rutas de los archivos JSON y PDF:

```bash
JSON_DIR=./data/json \
PDF_ROOT=./data/pdfs \
streamlit run app.py
```

---

## Solución de problemas

### Puerto en uso

Si alguno de los puertos `8502`, `8503` o `8504` está ocupado, modifique el puerto publicado en `docker-compose.yml`.

Por ejemplo:

```yaml
ports:
  - "8602:8501"
```

En este caso, la aplicación estará disponible mediante:

```text
http://localhost:8602
```

El segundo puerto (`8501`) corresponde al puerto interno utilizado por Streamlit y, en condiciones normales, no necesita modificarse.

### `docker compose` no está disponible

Las versiones actuales de Docker utilizan:

```bash
docker compose
```

En instalaciones antiguas puede estar disponible únicamente el comando:

```bash
docker-compose
```

Se recomienda utilizar Docker Compose v2 cuando sea posible.

### El visor no encuentra los PDF

Compruebe que:

1. los documentos se encuentren dentro de `pdf_review/data/pdfs/`;
2. estén organizados en la carpeta correspondiente a su año;
3. el nombre base del PDF coincida exactamente con el archivo JSON asociado.

---

## Fuente de los datos

Los reportes originales utilizados por este proyecto provienen del **Servicio Nacional de Gestión de Riesgos y Emergencias (SNGRE) del Ecuador**.

Los documentos PDF y los archivos JSON, TXT y Markdown derivados de ellos se utilizan con fines de procesamiento, análisis, validación y visualización de información pública.

Este proyecto constituye un procesamiento independiente de dicha información y **no reemplaza, representa ni sustituye a las fuentes oficiales del SNGRE**.

---

## Autores

Proyecto desarrollado por:

- **Enrique Rosado** — egrosado@espol.edu.ec
- **Valeria Gutiérrez** — vaniguti@espol.edu.ec
- **Adrián Salamea** — asalamea@espol.edu.ec
- **Tomás Bolaños** — tbolanos@espol.edu.ec
- **Steven Barzola** — starbarz@espol.edu.ec

**Escuela Superior Politécnica del Litoral (ESPOL)**  
Guayaquil, Ecuador