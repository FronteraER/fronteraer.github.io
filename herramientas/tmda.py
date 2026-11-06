#!/usr/bin/env python3
"""
Busca el TMDA (tránsito medio diario anual, Vialidad Nacional) de los tramos
de ruta que recorre cada una de nuestras rutas, usando la geometría de geo.json.
Uso: python3 herramientas/tmda.py tmda_vialidad.geojson  -> escribe tmda.json
"""
import json, math, re, sys

src = json.load(open(sys.argv[1], encoding="utf-8"))
geo = json.load(open("geo.json", encoding="utf-8"))["rutas"]
feats = src["features"]
print("features:", len(feats))
print("ejemplo de propiedades:", json.dumps(feats[0]["properties"], ensure_ascii=False)[:600])

props = feats[0]["properties"]
k_tmda = next((k for k in props if "tmda" in k.lower()), None)
k_ruta = next((k for k in props if k.lower() in ("ruta", "rn", "nro_ruta", "ruta_nro", "numero_ruta", "route")), None) \
    or next((k for k in props if "ruta" in k.lower()), None)
print("campos usados:", k_tmda, k_ruta)

def dist(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))

def coords(g):
    t = g["type"]; c = g["coordinates"]
    if t == "LineString": return [(y, x) for x, y, *_ in c]
    if t == "MultiLineString": return [(y, x) for l in c for x, y, *_ in l]
    if t == "Point": return [(c[1], c[0])]
    return []

tramos = []
for f in feats:
    pts = coords(f["geometry"]) if f.get("geometry") else []
    if not pts: continue
    try: v = float(f["properties"].get(k_tmda))
    except (TypeError, ValueError): continue
    tramos.append((f["properties"], pts[::max(1, len(pts) // 60)], v))

# Qué ruta de Vialidad corresponde a cada una nuestra, y en qué punto del
# recorrido tomar el dato (fracción: 0 = origen, 1 = destino). Se evita el
# final porque ahí las rutas se mezclan en accesos y circunvalaciones.
MAPEO = {
    "Colón – Paysandú": ("0135", 0.3),
    "Gualeguaychú – Fray Bentos": ("0136", 0.4),
    "Concordia – Salto": ("A015", 0.4),
    "RN 9 sur · desde Oncativo": ("0009", 0.5),
    "RN 19 · desde Río Primero": ("0019", 0.5),
    "RN 9 norte · desde Jesús María": ("0009", 0.5),
    "RN 20 · desde Villa Carlos Paz": ("0020", 0.5),
    "RN 36 · desde Almafuerte": ("0036", 0.5),
    "Acceso Oeste · desde Liniers": ("0007", 0.5),
    "RN 8 / RP 6 · desde Pilar": ("0008", 0.2),
    "RN 5 · desde Mercedes": ("0005", 0.5),
    "RN 7 · desde San Andrés de Giles": ("0007", 0.5),
    "RP 6 · desde Cañuelas": (None, 0.5),   # ruta provincial: no está en el dataset nacional
}
salida = {}
for clave, g in geo.items():
    nombre, sentido = clave.split("|")
    if sentido not in ("ida", "AR->UY") or nombre not in MAPEO:
        continue
    cod, frac = MAPEO[nombre]
    if not cod:
        print(f"{nombre:40} ruta provincial: sin dato nacional"); continue
    pts = g["pts"]
    ref = pts[int((len(pts) - 1) * frac)]
    best = None
    for p, tp, v in tramos:
        if str(p.get(k_ruta)) != cod: continue
        d = min(dist(ref, b) for b in tp)
        if best is None or d < best[0]:
            best = (d, v, p)
    if best and best[0] <= 2500:
        d, v, p = best
        salida[nombre] = {"tmda": v, "cod_ruta": cod, "dist_ref_m": round(d), "anio": 2017}
        print(f"{nombre:40} TMDA {v:>8.0f}  (ruta {cod}, a {d:.0f} m del punto de referencia)")
    else:
        print(f"{nombre:40} sin tramo cercano de la ruta {cod} ({best[0]:.0f} m)" if best else f"{nombre:40} sin ruta {cod}")
json.dump(salida, open("tmda.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
