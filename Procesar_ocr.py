import easyocr
import cv2
import numpy as np

idioma = easyocr.Reader(['es'],gpu=False)

imagen = cv2.imread('Nicolas.jpeg')
resultado = idioma.readtext(imagen)


for i in resultado:
    print("resultado:", i)

    pt0 = i[0][0]
    pt1 = i[0][1]
    pt2 = i[0][2]
    pt3 = i[0][3]

    # Dibujar rectángulo alrededor del texto detectado
    cv2.rectangle(imagen, pt0, pt2, (0, 255, 0), 2)

cv2.imshow('imagen', imagen)
cv2.waitKey(0)
cv2.destroyAllWindows()