import easyocr
import sys
import json
import re
import warnings
import cv2
import numpy as np
from PIL import Image
import os
from typing import Dict, List, Optional, Tuple

# Suprimir advertencias
warnings.filterwarnings('ignore')


class OCRProcessor:
    def __init__(self):
        print("Iniciando EasyOCR...", file=sys.stderr)
        self.reader = easyocr.Reader(['es', 'en'], gpu=False, verbose=False)

    def procesar_imagen(self, image_path, tipo):
        """Procesa imagen con varias estrategias OCR para mejorar precisión."""
        temp_paths: List[str] = []

        try:
            print(f"\n=== Procesando {tipo} ===", file=sys.stderr)

            # 1. Cargar imagen y ajustar tamaño base
            pil_img = Image.open(image_path).convert('RGB')
            if pil_img.width > 2200:
                ratio = 2200 / pil_img.width
                new_height = int(pil_img.height * ratio)
                pil_img = pil_img.resize((2200, new_height), Image.Resampling.LANCZOS)
                print(f"Redimensionado a {2200}x{new_height}", file=sys.stderr)

            img_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

            # 2. Construir variantes para OCR (ayuda con diferentes iluminaciones/contrastes)
            variantes = self._crear_variantes(img_bgr)
            textos, resultados = self._extraer_texto_multivariante(variantes, image_path, temp_paths)

            if not textos:
                raise RuntimeError("No se pudo extraer texto utilizable de la imagen")

            texto_completo = ' '.join(textos)
            print(f"Texto extraído (preview): {texto_completo[:250]}", file=sys.stderr)

            # 3. Limpieza normalizada (menos agresiva)
            texto_limpio = self._normalizar_texto(texto_completo)

            # 4. Procesar por tipo
            if tipo == 'propiedad':
                datos = self.procesar_tarjeta_propiedad(texto_limpio, resultados)
            else:
                datos = {
                    "texto": texto_limpio,
                    "lineas": self._lineas_unicas(resultados)
                }

            # 5. Señal de calidad
            datos["_ocr_confianza_promedio"] = self._confianza_promedio(resultados)
            print(json.dumps(datos, ensure_ascii=False))

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            # Fallback: devolver estructura vacía pero útil
            datos_fallback = self._get_datos_fallback(tipo)
            datos_fallback["_error"] = str(e)
            print(json.dumps(datos_fallback, ensure_ascii=False))

        finally:
            for path in temp_paths:
                try:
                    os.remove(path)
                except OSError:
                    pass

    def _crear_variantes(self, img_bgr: np.ndarray) -> Dict[str, np.ndarray]:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

        # Mejora de contraste
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)

        # Filtros
        blur = cv2.GaussianBlur(clahe, (3, 3), 0)

        # Umbrales
        otsu = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        adaptive = cv2.adaptiveThreshold(
            clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 8
        )

        # Escalado (OCR suele mejorar con texto más grande)
        upscaled = cv2.resize(gray, None, fx=1.6, fy=1.6, interpolation=cv2.INTER_CUBIC)

        return {
            "gray": gray,
            "clahe": clahe,
            "otsu": otsu,
            "adaptive": adaptive,
            "upscaled": upscaled,
        }

    def _extraer_texto_multivariante(
        self,
        variantes: Dict[str, np.ndarray],
        base_path: str,
        temp_paths: List[str],
    ) -> Tuple[List[str], List[Tuple[str, float]]]:
        candidatos: Dict[str, float] = {}

        for nombre, img in variantes.items():
            temp_path = f"{base_path}_{nombre}.jpg"
            temp_paths.append(temp_path)
            cv2.imwrite(temp_path, img, [cv2.IMWRITE_JPEG_QUALITY, 96])

            resultados = self.reader.readtext(temp_path)
            print(f"Variante {nombre}: {len(resultados)} detecciones", file=sys.stderr)

            for _, text, conf in resultados:
                txt = self._normalizar_texto(text)
                if len(txt) < 2:
                    continue
                prev = candidatos.get(txt, 0.0)
                if conf > prev:
                    candidatos[txt] = conf

        # Ordenar por confianza descendente
        ordenados = sorted(candidatos.items(), key=lambda x: x[1], reverse=True)
        textos = [t for t, c in ordenados if c >= 0.25 or len(t) > 6]

        return textos, ordenados

    def _normalizar_texto(self, texto: str) -> str:
        texto = texto.upper()

        # Correcciones comunes OCR
        reemplazos = {
            'Ó': 'O',
            'Í': 'I',
            'Á': 'A',
            'É': 'E',
            'Ú': 'U',
            'Ñ': 'N',
            '|': 'I',
            '“': ' ',
            '”': ' ',
            '—': '-',
        }
        for k, v in reemplazos.items():
            texto = texto.replace(k, v)

        # Mantener caracteres útiles en documentos
        texto = re.sub(r'[^A-Z0-9\s\-\/:\.\,]', ' ', texto)
        texto = re.sub(r'\s+', ' ', texto).strip()
        return texto

    def _lineas_unicas(self, resultados: List[Tuple[str, float]]) -> List[str]:
        vistos = set()
        lineas = []
        for txt, conf in resultados:
            if conf < 0.35:
                continue
            if txt in vistos:
                continue
            vistos.add(txt)
            lineas.append(txt)
        return lineas[:120]

    def _confianza_promedio(self, resultados: List[Tuple[str, float]]) -> float:
        if not resultados:
            return 0.0
        return round(float(sum(conf for _, conf in resultados) / len(resultados)), 4)

    def procesar_tarjeta_propiedad(self, texto: str, resultados: List[Tuple[str, float]]):
        """Extrae datos de tarjeta de propiedad con patrones flexibles y etiquetas."""
        datos = {
            "placa": "",
            "marca": "",
            "linea": "",
            "clase": "",
            "servicio": "",
            "numero_licencia": "",
            "cilindraje": "",
            "modelo": "",
            "numero_vin": "",
            "numero_motor": "",
            "no_ejes": "",
            "combustible": "",
            "chasis": "",
            "ref_llanta": "",
            "pais": "COLOMBIA",
            "departamento": "",
            "ciudad": "",
            "tipo_vehiculo": "",
            "matricula": "",
            "color_primario": "",
            "kilometraje": "",
            "potencia": "",
            "tipo_motor": "",
            "tipo_carroceria": "",
            "no_pax": "",
            "blindado": "NO"
        }

        lineas = [txt for txt, conf in resultados if conf >= 0.25]
        texto_join = " ".join(lineas) if lineas else texto
        texto_upper = self._normalizar_texto(texto_join)

        # Patrones flexibles
        self._asignar_match(datos, "placa", texto_upper, [
            r'\b([A-Z]{3}\s?[0-9]{3})\b',
            r'\b([A-Z]{3}[0-9]{2}[A-Z])\b'
        ], lambda x: x.replace(' ', ''))

        self._asignar_match(datos, "modelo", texto_upper, [
            r'\b(19[8-9][0-9]|20[0-3][0-9])\b'
        ])

        self._asignar_match(datos, "cilindraje", texto_upper, [
            r'\b(\d{2,5})\s*(?:CC|C\.C\.|CM3)?\b'
        ], condicion=lambda v: 40 <= int(v) <= 9000)

        self._asignar_match(datos, "numero_vin", texto_upper, [
            r'\b([A-HJ-NPR-Z0-9]{17})\b'
        ])

        self._asignar_match(datos, "numero_motor", texto_upper, [
            r'(?:MOTOR|NO\.?\s*MOTOR|NRO\.?\s*MOTOR)\s*[:\-]?\s*([A-Z0-9\-]{5,25})'
        ])

        self._asignar_match(datos, "numero_licencia", texto_upper, [
            r'(?:LICENCIA|LICENCI\w*)\s*(?:DE\s*TRANSITO)?\s*[:\-]?\s*([A-Z0-9\-]{6,20})'
        ])

        self._asignar_match(datos, "matricula", texto_upper, [
            r'(\d{1,2}[\/-]\d{1,2}[\/-]\d{2,4})'
        ])

        self._asignar_match(datos, "no_ejes", texto_upper, [
            r'(?:NO\.?\s*EJES|NUMERO\s*EJES)\s*[:\-]?\s*(\d{1,2})'
        ])

        marcas = [
            'HONDA', 'YAMAHA', 'SUZUKI', 'KAWASAKI', 'AKT', 'VICTORY',
            'CHEVROLET', 'RENAULT', 'MAZDA', 'TOYOTA', 'HYUNDAI', 'KIA',
            'FORD', 'VOLKSWAGEN', 'NISSAN', 'BMW', 'AUDI', 'MERCEDES',
            'DUCATI', 'BAJAJ', 'FIAT', 'JEEP', 'PEUGEOT'
        ]
        for marca in marcas:
            if re.search(rf'\b{marca}\b', texto_upper):
                datos["marca"] = marca
                break

        colores = [
            'BLANCO', 'NEGRO', 'ROJO', 'AZUL', 'GRIS', 'PLATA', 'DORADO',
            'VERDE', 'AMARILLO', 'NARANJA', 'BEIGE', 'MARRON'
        ]
        for color in colores:
            if re.search(rf'\b{color}\b', texto_upper):
                datos["color_primario"] = color
                break

        clases = ['MOTOCICLETA', 'AUTOMOVIL', 'CAMIONETA', 'CAMPERO', 'BUS', 'MOTOCARRO']
        for clase in clases:
            if re.search(rf'\b{clase}\b', texto_upper):
                datos["clase"] = clase
                break

        if 'PARTICULAR' in texto_upper:
            datos["servicio"] = 'PARTICULAR'
        elif 'PUBLICO' in texto_upper or 'PUBLICO' in texto_upper.replace('Ú', 'U'):
            datos["servicio"] = 'PUBLICO'

        combustibles = ['GASOLINA', 'DIESEL', 'ELECTRICO', 'HIBRIDO', 'GNV', 'GAS']
        for comb in combustibles:
            if re.search(rf'\b{comb}\b', texto_upper):
                datos["combustible"] = comb
                break

        return datos

    def _asignar_match(
        self,
        datos: Dict[str, str],
        key: str,
        texto: str,
        patrones: List[str],
        transform=None,
        condicion=None
    ):
        for patron in patrones:
            match = re.search(patron, texto)
            if not match:
                continue
            valor = match.group(1).strip()
            if transform:
                valor = transform(valor)
            if condicion and not condicion(valor):
                continue
            datos[key] = valor
            return

    def _get_datos_fallback(self, tipo):
        """Fallback en caso de error: estructura vacía consistente."""
        if tipo == 'propiedad':
            return {
                "placa": "",
                "marca": "",
                "linea": "",
                "clase": "",
                "servicio": "",
                "numero_licencia": "",
                "cilindraje": "",
                "modelo": "",
                "numero_vin": "",
                "numero_motor": "",
                "no_ejes": "",
                "combustible": "",
                "chasis": "",
                "ref_llanta": "",
                "pais": "COLOMBIA",
                "departamento": "",
                "ciudad": "",
                "tipo_vehiculo": "",
                "matricula": "",
                "color_primario": "",
                "kilometraje": "",
                "potencia": "",
                "tipo_motor": "",
                "tipo_carroceria": "",
                "no_pax": "",
                "blindado": "NO"
            }
        return {"texto": ""}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Se requieren argumentos"}))
        sys.exit(1)

    image_path = sys.argv[1]
    tipo = sys.argv[2]

    processor = OCRProcessor()
    processor.procesar_imagen(image_path, tipo)