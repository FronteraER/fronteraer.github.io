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

salida = {}
for clave, g in geo.items():
    nombre, sentido = clave.split("|")
    if sentido not in ("ida", "AR->UY"): continue
    pts = g["pts"]
    num = re.findall(r"RN\s*(\d+)", nombre)
    # punto de referencia: acceso a la ciudad destino (80% del recorrido)
    ref = pts[int(len(pts) * 0.8)]
    cands = []
    for p, tp, v in tramos:
        d_ruta = min(dist(a, b) for a in pts[::5] for b in tp)
        if d_ruta > 400: continue
        rn = str(p.get(k_ruta, ""))
        coincide = (not num) or any(n == re.sub(r"\D", "", rn) for n in num)
        d_ref = min(dist(ref, b) for b in tp)
        cands.append((not coincide, d_ref, v, p))
    cands.sort(key=lambda x: (x[0], x[1]))
    if cands:
        _, d_ref, v, p = cands[0]
        salida[nombre] = {"tmda": v, "ruta": p.get(k_ruta), "dist_ref_m": round(d_ref),
                          "props": {k: p[k] for k in list(p)[:12]}}
        print(f"{nombre:40} TMDA {v:>8.0f}  ({p.get(k_ruta)}, a {d_ref:.0f} m del acceso)")
    else:
        print(f"{nombre:40} sin tramo de Vialidad cercano")
json.dump(salida, open("tmda.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
