"""
MUESTRA de código de scraping — descarga los PDF de reportes de monitoreo
desde el sitio de la SNGR (Secretaría Nacional de Gestión de Riesgos).

Copiado sin modificar desde (ruta original en esta máquina, solo válida
donde se corrió):
  /home/tomagochito/Documentos/ESPOL/semestre8/metodologia de la
  investigacion en computacion/proyecto/codigo fuente/scraper.py

Es UNA muestra representativa, no todo el código de scraping que existe:
en esa misma carpeta hay variantes por año (spider_2022.py … spider_2026.py
+ downloader.py, en .../try2/dataset/code/scrapper/) con el mismo enfoque
(requests + parseo de HTML) pero adaptadas a como cambió el sitio de la
SNGR entre años.

Qué hace, en dos pasos:
  1. extract_pdf_links(): pide la página de listado de reportes (URL abajo)
     y con BeautifulSoup junta todos los <a href> que terminen en .pdf y
     que sean del año que corresponde.
  2. download_pdf(): descarga cada PDF nuevo (evita re-descargar los que ya
     están en disco) y guarda metadata (nombre, url, año, fecha del
     reporte, fecha de descarga) en un CSV que se actualiza incrementalmente.

Las 4 URL de listado usadas en total (una por spider_20XX.py, salvo
2025/2026 que comparten la misma página — por eso el filtro de abajo busca
"/2025/" O "/2026/" en el href):
  2022: https://www.gestionderiesgos.gob.ec/reportes-de-monitoreo-de-amenazas-y-eventos-peligrosos-2022/
  2023: https://www.gestionderiesgos.gob.ec/reportes-de-monitoreo-de-amenazas-y-eventos-peligrosos-2023/
  2024: https://www.gestionderiesgos.gob.ec/reportes-de-monitoreo-de-amenazas-y-eventos-peligrosos/  (sin sufijo de año)
  2025 y 2026 (misma página): https://www.gestionderiesgos.gob.ec/reportes-de-monitoreo-de-amenazas-y-eventos-peligrosos-2025/
"""
import os
import re
import csv
import sys
import time
from datetime import datetime
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

URL = "https://www.gestionderiesgos.gob.ec/reportes-de-monitoreo-de-amenazas-y-eventos-peligrosos-2025/"
DATA_DIR = "sgre data"
CSV_FILE = os.path.join(DATA_DIR, "metadatos.csv")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def extract_pdf_links(url):
    print("Extrayendo enlaces PDF del sitio...", flush=True)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.lower().endswith(".pdf"):
            continue
        if "/2025/" in href or "/2026/" in href:
            links.add(href)
    return sorted(links)


def extract_metadata(url):
    parsed = urlparse(url)
    filename = os.path.basename(parsed.path)
    if "/2025/" in url:
        year = "2025"
    elif "/2026/" in url:
        year = "2026"
    else:
        year = "desconocido"
    match = re.search(r"(\d{8})", filename)
    date_str = ""
    if match:
        raw = match.group(1)
        try:
            dt = datetime.strptime(raw, "%d%m%Y")
            date_str = dt.strftime("%Y-%m-%d")
        except ValueError:
            date_str = raw
    numero_match = re.search(r"_(\d{4})_", filename)
    numero = numero_match.group(1) if numero_match else ""
    return {
        "nombre_archivo": filename,
        "url": url,
        "anio": year,
        "fecha_reporte": date_str,
        "numero_reporte": numero,
        "fecha_descarga": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def download_pdf(url, dest_dir):
    parsed = urlparse(url)
    filename = os.path.basename(parsed.path)
    path = os.path.join(dest_dir, filename)
    if os.path.exists(path):
        return path, True
    try:
        resp = requests.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        with open(path, "wb") as f:
            f.write(resp.content)
        return path, False
    except Exception as e:
        print(f"  Error: {e}", flush=True)
        return None, False


def save_csv(metadata_list):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "nombre_archivo", "url", "anio", "fecha_reporte",
            "numero_reporte", "fecha_descarga", "ruta_local"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(metadata_list)
    print(f"CSV guardado: {CSV_FILE}", flush=True)


def load_existing_metadata():
    if not os.path.exists(CSV_FILE):
        return {}
    existing = {}
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            existing[row["url"]] = row
    print(f"Cargados {len(existing)} registros existentes del CSV", flush=True)
    return existing


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    # Load already-downloaded metadata if CSV exists
    existing_meta = load_existing_metadata()

    pdf_links = extract_pdf_links(URL)
    total = len(pdf_links)
    c2025 = sum(1 for l in pdf_links if "/2025/" in l)
    c2026 = sum(1 for l in pdf_links if "/2026/" in l)
    print(f"Encontrados {total} PDFs únicos ({c2025} de 2025, {c2026} de 2026)", flush=True)

    metadata_list = list(existing_meta.values())
    downloaded = 0
    skipped = 0
    errors = 0

    for i, link in enumerate(pdf_links, 1):
        fname = os.path.basename(urlparse(link).path)

        # Skip if already in CSV
        if link in existing_meta:
            skipped += 1
            continue

        print(f"[{i}/{total}] {fname}", flush=True)
        meta = extract_metadata(link)
        path, was_cached = download_pdf(link, DATA_DIR)
        if path:
            downloaded += 1
            meta["ruta_local"] = path
        else:
            errors += 1
            meta["ruta_local"] = ""
        metadata_list.append(meta)

        # Save CSV every 25 new downloads
        if downloaded % 25 == 0:
            save_csv(metadata_list)

    save_csv(metadata_list)

    print(f"\nResumen:", flush=True)
    print(f"  Descargados nuevos: {downloaded}", flush=True)
    print(f"  Ya en CSV:          {skipped}", flush=True)
    print(f"  Errores:            {errors}", flush=True)
    print(f"  Total en CSV:       {len(metadata_list)}", flush=True)


if __name__ == "__main__":
    main()
