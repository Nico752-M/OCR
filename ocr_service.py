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

    

ETIQUETAS_TARJETA = {
    "identificacion": ["IDENTIFICACION"],
    "placa": ["PLACA"],
    "marca": ["MARCA"],
    "linea": ["LINEA"],
    "modelo": ["MODELO"],
    "cilindraje": ["CILINDRAJE", "CILINDR"],
    "color": ["COLOR"],
    "servicio": ["SERVICIO"],
    "clase": ["CLASE"],
    "capacidad": ["CAPACIDAD"],
    "motor": ["MOTOR"],
    "vin": ["VIN"],
    "chasis": ["CHASIS"],
    "serie": ["SERIE"]
}

def detectar_etiquetas(ocr, etiquetas):
    encontradas = []

    for campo, keys in etiquetas.items():
        for r in ocr:
            if any(k in r["texto"] for k in keys):
                encontradas.append({
                    "campo": campo,
                    "x": r["x"],
                    "y": r["y"],
                    "texto": r["texto"]
                })
    return encontradas

def distancia(a, b):
    return abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])

def asignar_valores(ocr, etiquetas_detectadas):
    resultado = {}

    for e in etiquetas_detectadas:
        candidatos = []

        for r in ocr:
            if r["texto"] == e["texto"]:
                continue

            # solo texto cercano
            if (
                r["y"] > e["y"] and
                r["y"] - e["y"] < 120 and
                abs(r["x"] - e["x"]) < 400
            ):
                candidatos.append(r)

        if candidatos:
            mejor = min(candidatos, key=lambda r: distancia(e, r))
            resultado[e["campo"]] = limpiar_texto(mejor["texto"])

    return resultado
def limpiar_texto(txt):
    basura = [
        "MARCA", "MODELO", "PLACA", "SERVICIO", "CLASE",
        "CAPACIDAD", "COLOR", "CILINDRAJE", "VIN",
        "CHASIS", "SERIE", "IDENTIFICACION"
    ]

    txt = txt.upper()

    for b in basura:
        txt = txt.replace(b, "")

    # quitar caracteres raros
    txt = re.sub(r"[^A-Z0-9\-\. ]", "", txt)

    # normalizar espacios
    txt = re.sub(r"\s{2,}", " ", txt).strip()

    return txt

    txt = txt.upper()
    for b in basura:
        txt = txt.replace(b, "")

    return re.sub(r"\s{2,}", " ", txt).strip()

def extraer_tarjeta_inteligente(ocr):
    ocr = ordenar_ocr(ocr)

    etiquetas_detectadas = detectar_etiquetas(ocr, ETIQUETAS_TARJETA)
    valores = asignar_valores(ocr, etiquetas_detectadas)

    # garantizar campos vacíos
    for k in ETIQUETAS_TARJETA:
        valores.setdefault(k, "")

    return valores

def normalizar_codigo(txt):
    """
    Normaliza VIN / CHASIS:
    - Mayúsculas
    - Solo A-Z y 0-9
    - Quita ruido OCR
    """
    if not txt:
        return ""

    txt = txt.upper()
    txt = re.sub(r"[^A-Z0-9]", "", txt)

    return txt

def reconciliar_vin_chasis(data):
    vin = normalizar_codigo(data.get("vin", ""))
    chasis = normalizar_codigo(data.get("chasis", ""))

    # si ambos existen
    if vin and chasis:
        # si uno es substring del otro → usar el más largo
        if vin in chasis:
            final = chasis
        elif chasis in vin:
            final = vin
        else:
            # escoger el que tenga longitud típica VIN (17)
            final = vin if len(vin) >= len(chasis) else chasis

    # si solo uno existe
    else:
        final = vin or chasis

    data["vin"] = final
    data["chasis"] = final

    return data
# =========================
# EXTRACCIÓN DOCUMENTOS
# =========================



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

    tarjeta_data = extraer_tarjeta_inteligente(ocr_tarjeta)
    tarjeta_data = reconciliar_vin_chasis(tarjeta_data)
    
    print("\n===== TARJETA EXTRAÍDA =====")
    print(tarjeta_data)
    print("============================")

    return {
    "cedula": cedula_data,
    "tarjeta": tarjeta_data
}