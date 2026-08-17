#!/usr/bin/env python3
"""
MUESTRA de código PDF -> TXT valorado (pipeline A, ver trazabilidad/README.md).

Copiado (con las rutas renombradas a RUTA_ORIGEN/RUTA_DESTINO para que se
entiendan sin contexto adicional) desde la ruta original en esta máquina,
solo válida donde se corrió:
  /home/tomagochito/Documentos/MIC/datos/2025/extraer_texto_con_iconos_2025.py

Es UNA muestra representativa: el mismo enfoque (pdftotext -layout + PyMuPDF
para los iconos de color) se repite con pequeñas variaciones en los scripts
de 2023, 2024 y 2026 — ver la tabla de la sección 1 de trazabilidad/README.md
para la lista completa con sus rutas.

Qué hace, en un solo paso (a diferencia del pipeline B — MinerU + ChatGPT
Plus en dos pasos separados — aquí "extraer texto" y "extraer valoración"
pasan en el mismo script):
  1. pdftotext -layout: extrae el texto plano del PDF preservando columnas/
     tablas.
  2. PyMuPDF (fitz): recorre el PDF buscando los iconos de color de la
     columna de valoración (el carácter "" en el texto de cada span) y
     guarda, en orden de aparición, a qué color RGB corresponde cada uno
     (COLOR_MAP).
  3. Reemplaza cada icono, en el mismo orden en que aparecieron, por su
     etiqueta de texto ("[ROJO]", "[AMARILLO]", "[VERDE]"...) dentro del
     TXT — este es el TXT que después se sube a ChatGPT (Project "MIC
     Procesamiento") junto con PROMPT.txt.
"""

import os, re, subprocess, glob
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── Rutas ───────────────────────────────────────────────────────────────
# Relativas a la carpeta del script (así corrió originalmente en
# /home/tomagochito/Documentos/MIC/datos/2025/).
BASE = os.path.dirname(os.path.abspath(__file__))
RUTA_ORIGEN = os.path.join(BASE, "reportes_2025_pdf")     # PDF de entrada
RUTA_DESTINO = os.path.join(BASE, "reportes__2025_txt")   # TXT de salida
os.makedirs(RUTA_DESTINO, exist_ok=True)

COLOR_MAP = {
    0xff0000: "ROJO", 0xffd966: "AMARILLO",
    0x00b050: "VERDE", 0x538135: "VERDE",
    0xffff00: "AMARILLO", 0x000000: "NEGRO",
}

PDFS_PATTERN = os.path.join(RUTA_ORIGEN, "*.pdf")


# ─── Función por PDF ─────────────────────────────────────────────────────
def procesar_pdf(pdf_path):
    import fitz
    pdf_name = os.path.basename(pdf_path)
    base = os.path.splitext(pdf_name)[0]
    txt_out = os.path.join(RUTA_DESTINO, f"{base}.txt")

    # 1. Extraer texto plano con pdftotext -layout
    resultado = subprocess.run(
        ["pdftotext", "-layout", pdf_path, "-"],
        capture_output=True, timeout=60
    )
    contenido = resultado.stdout.decode("utf-8", errors="replace")

    # 2. Obtener iconos con su color (PyMuPDF), en orden de aparición
    doc = fitz.open(pdf_path)
    iconos = []
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                texto_linea = ""
                ics = []
                for span in line["spans"]:
                    if "" in span["text"]:
                        etiqueta = COLOR_MAP.get(span["color"], f"#{span['color']:06X}")
                        ics.append({"etiqueta": etiqueta})
                    texto_linea += span["text"]
                for ic in ics:
                    ic["texto"] = texto_linea.strip()[:150]
                    iconos.append(ic)
    doc.close()

    # 3. Reemplazar cada icono por su etiqueta de color, en orden
    contador = [0]
    def reemplazar(m):
        i = contador[0]
        contador[0] += 1
        if i < len(iconos):
            return f"[{iconos[i]['etiqueta']}]"
        return "⬤"

    nuevo = re.sub("", reemplazar, contenido)
    with open(txt_out, "w", encoding="utf-8") as f:
        f.write(nuevo)

    colores = {}
    for ic in iconos:
        colores[ic["etiqueta"]] = colores.get(ic["etiqueta"], 0) + 1
    return pdf_name, len(iconos), colores


# ─── Main ─────────────────────────────────────────────────────────────────
def main():
    pdfs = sorted(glob.glob(PDFS_PATTERN))
    total = len(pdfs)
    print(f"PDFs a procesar: {total}")
    print(f"Origen: {RUTA_ORIGEN}")
    print(f"Destino: {RUTA_DESTINO}")
    print()

    ok = 0
    err = 0

    with ThreadPoolExecutor(max_workers=8) as pool:
        futuros = {pool.submit(procesar_pdf, p): p for p in pdfs}
        for futuro in as_completed(futuros):
            try:
                nombre, n_iconos, colores = futuro.result()
                col_str = ", ".join(f"{k}={v}" for k, v in sorted(colores.items()))
                print(f"  OK {nombre[:55]:55s}  {n_iconos:2d} iconos: {col_str}")
                ok += 1
            except Exception as e:
                pdf_name = os.path.basename(futuros[futuro])
                print(f"  ERROR {pdf_name[:55]:55s}  {e}")
                err += 1

    print(f"\n{'=' * 70}")
    print(f"  Procesados: {ok} OK, {err} ERRORES")
    print(f"  Salida en: {RUTA_DESTINO}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
