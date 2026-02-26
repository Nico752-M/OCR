import cv2
import numpy as np
import easyocr
import re
from fastapi import FastAPI, UploadFile, File

app = FastAPI()
reader = easyocr.Reader(['es'], gpu=False)

# =========================
# UTILIDADES DE IMAGEN
# =========================

def bytes_a_imagen(img_bytes):
    img_np = np.frombuffer(img_bytes, np.uint8)
    return cv2.imdecode(img_np, cv2.IMREAD_COLOR)

def preprocesar(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5,5), 0)
    return cv2.adaptiveThreshold(
        blur, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11, 2
    )
def procesar_documento_bytes(lista_bytes):
    """
    Intenta OCR por regiones.
    Si falla o extrae muy poco texto, usa OCR simple (fallback).
    Retorna OCR ordenado (lista de dicts con x,y,texto)
    """

    resultados = []

    for img_bytes in lista_bytes:
        img = bytes_a_imagen(img_bytes)

        # 1️⃣ OCR por regiones
        ocr_regiones = ocr_por_regiones(img)

        # 2️⃣ Si regiones fallan → fallback simple
        if len(ocr_regiones) < 5:
            print("⚠️ OCR por regiones insuficiente → fallback OCR simple")
            ocr_regiones = ocr_simple(img)

        resultados.extend(ocr_regiones)

    return ordenar_ocr(resultados)
# =========================
# OCR SIMPLE (FALLBACK)
# =========================

def ocr_simple(img):
    resultado = reader.readtext(img, detail=1)
    data = []
    for r in resultado:
        x = r[0][0][0]
        y = r[0][0][1]
        data.append({
            "x": x,
            "y": y,
            "texto": r[1].upper()
        })
    return data

# =========================
# OCR POR REGIONES
# =========================

def detectar_regiones(binaria):
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15,5))
    dilatada = cv2.dilate(binaria, kernel, 2)
    contornos, _ = cv2.findContours(
        dilatada, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    regiones = []
    for c in contornos:
        x,y,w,h = cv2.boundingRect(c)
        if w > 120 and h > 25:
            regiones.append((x,y,w,h))
    return regiones

def ocr_por_regiones(img):
    binaria = preprocesar(img)
    regiones = detectar_regiones(binaria)

    resultados = []
    for x,y,w,h in regiones:
        roi = img[y:y+h, x:x+w]
        ocr = reader.readtext(roi, detail=1)
        for r in ocr:
            resultados.append({
                "x": x + r[0][0][0],
                "y": y + r[0][0][1],
                "texto": r[1].upper()
            })
    return resultados

# =========================
# ORDEN Y UTILIDADES
# =========================

def ordenar_ocr(data):
    return sorted(data, key=lambda r: (r["y"], r["x"]))

def buscar_valor(ocr, etiqueta):
    etiqueta = etiqueta.upper()

    for i, r in enumerate(ocr):
        if etiqueta in r["texto"]:
            y_base = r["y"]

            candidatos = []
            for j in range(i+1, len(ocr)):
                if abs(ocr[j]["y"] - y_base) < 80:
                    candidatos.append(ocr[j]["texto"])
                elif ocr[j]["y"] > y_base + 120:
                    break

            return " ".join(candidatos).strip()

    return ""

# =========================
# EXTRACCIÓN DOCUMENTOS
# =========================

def extraer_tarjeta(ocr):
    return {
        "identificacion": buscar_valor(ocr, "IDENTIFICACION"),
        "numero": buscar_valor(ocr, "LICENCIA"),
        "placa": buscar_valor(ocr, "PLACA"),
        "marca": buscar_valor(ocr, "MARCA"),
        "linea": buscar_valor(ocr, "LINEA"),
        "modelo": buscar_valor(ocr, "MODELO"),
        "cilindraje": buscar_valor(ocr, "CILINDR"),
        "color": buscar_valor(ocr, "COLOR"),
        "servicio": buscar_valor(ocr, "SERVICIO"),
        "clase": buscar_valor(ocr, "CLASE"),
        "capacidad": buscar_valor(ocr, "CAPACIDAD"),
        "motor": buscar_valor(ocr, "MOTOR"),
        "vin": buscar_valor(ocr, "VIN"),
        "chasis": buscar_valor(ocr, "CHASIS"),
        "serie": buscar_valor(ocr, "SERIE")
    }

def extraer_cedula(ocr):
    return {
        "tipo_documento": "CÉDULA",
        "numero": buscar_valor(ocr, "NUMERO"),
        "nombres": buscar_valor(ocr, "NOMBRES"),
        "apellidos": buscar_valor(ocr, "APELLIDOS"),
        "fecha_nacimiento": buscar_valor(ocr, "FECHA DE NACIMIENTO"),
        "lugar_nacimiento": buscar_valor(ocr, "LUGAR DE NACIMIENTO"),
        "fecha_expedicion": buscar_valor(ocr, "FECHA Y LUGAR DE EXPEDICION"),
        "lugar_expedicion": buscar_valor(ocr, "EXPEDICION")
    }

# =========================
# ENDPOINT
# =========================

@app.post("/ocr")
async def ocr(
    cedula_frontal: UploadFile | None = File(None),
    cedula_reverso: UploadFile | None = File(None),
    tarjeta_frontal: UploadFile | None = File(None),
):

    # ---------- CÉDULA ----------
    ocr_cedula = []
    if cedula_frontal and cedula_reverso:
        ocr_cedula = procesar_documento_bytes([
            await cedula_frontal.read(),
            await cedula_reverso.read()
        ])

    cedula_data = extraer_cedula(ocr_cedula)

    print("\n===== TEXTO CÉDULA OCR =====")
    print(ocr_cedula)
    print("============================")

    # ---------- TARJETA ----------
    ocr_tarjeta = []
    if tarjeta_frontal:
        ocr_tarjeta = procesar_documento_bytes([
            await tarjeta_frontal.read()
        ])

    print("\n===== OCR TARJETA =====")
    for r in ocr_tarjeta:
        print(r)
    print("======================")

    tarjeta_data = extraer_tarjeta(ocr_tarjeta)

    print("\n===== TARJETA EXTRAÍDA =====")
    print(tarjeta_data)
    print("============================")

    return {
    "cedula": cedula_data,
    "tarjeta": tarjeta_data
}