#!/usr/bin/env python3
"""
Monitor de demoras en los pasos Entre Ríos -> Uruguay (solo sentido AR->UY),
usando la API de rutas de TomTom (gratis, sin tarjeta), con dashboard web en tiempo real.

Estima, para cada paso:
  - demora actual (min) = duración con tráfico - duración sin tráfico
  - largo de la cola (m) = tramo contiguo más largo en SLOW / TRAFFIC_JAM
  - autos en cola (estimado) = largo / metros_por_auto * carriles
  - flujo (autos/h, estimado) = autos en cola / demora   (ley de Little)

Uso:
  export TOMTOM_API_KEY="tu_clave"
  python3 monitor_pasos.py --cada 10          # mide cada 10 min y sirve el dashboard
  python3 monitor_pasos.py --demo             # datos simulados, sin clave (para probar)
  python3 monitor_pasos.py --una-vez          # una medición y salir (GitHub Actions)

Abrí http://localhost:8000 en el navegador. Otras personas de tu misma red
pueden entrar con http://<IP-de-tu-compu>:8000.

Archivos: pasos.csv (historial completo), datos.json (lo que lee el dashboard).
Necesita index.html en la misma carpeta. Sin dependencias externas.
"""

import argparse
import csv
import functools
import http.server
import json
import math
import os
import random
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

AR = timezone(timedelta(hours=-3))   # hora de Argentina (sin horario de verano)


def ahora():
    return datetime.now(AR)

API_URL = "https://api.tomtom.com/routing/1/calculateRoute/{o}:{d}/json"

# Origen (lado argentino) y destino (lado uruguayo) como (lat, lng).
# TomTom traza la ruta que cruza el puente. Para más precisión, mové el origen
# a unos km antes del control y el destino a la salida del puente.
PASOS = {
    "Colón – Paysandú":           ((-32.2234, -58.1440), (-32.3171, -58.0807)),
    "Gualeguaychú – Fray Bentos": ((-33.0094, -58.5172), (-33.1165, -58.3107)),
    "Concordia – Salto":          ((-31.3929, -58.0209), (-31.3833, -57.9667)),
}

METROS_POR_AUTO = 7.0   # largo promedio auto + espacio en fila
CARRILES = 1            # carriles de fila (ajustar según el paso)
CSV_PATH = "pasos.csv"
JSON_PATH = "datos.json"
HORAS_EN_DASHBOARD = 24
CARPETA = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- TomTom API

def distancia_m(a, b):
    R = 6371000
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def consultar(origen, destino, api_key):
    fmt = lambda p: f"{p[0]},{p[1]}"
    url = API_URL.format(o=fmt(origen), d=fmt(destino)) + "?" + urllib.parse.urlencode({
        "key": api_key,
        "traffic": "true",
        "travelMode": "car",
        "routeType": "fastest",
        "computeTravelTimeFor": "all",   # incluye el tiempo sin tráfico
        "sectionType": "traffic",        # tramos con embotellamiento
    })
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def analizar(resp):
    ruta = resp["routes"][0]
    sm = ruta["summary"]
    demora_min = max(0.0, sm.get("trafficDelayInSeconds", 0) / 60)

    # Puntos de la ruta, para medir el largo de cada tramo con tráfico
    pts = [(p["latitude"], p["longitude"])
           for leg in ruta.get("legs", []) for p in leg.get("points", [])]

    # Tramo congestionado contiguo más largo (la fila)
    tramos = sorted((s["startPointIndex"], s["endPointIndex"])
                    for s in ruta.get("sections", [])
                    if s.get("sectionType") == "TRAFFIC")
    cola_max, ini_act, fin_act = 0.0, None, None

    def largo(i, f):
        return sum(distancia_m(pts[k], pts[k + 1]) for k in range(i, min(f, len(pts) - 1)))

    for i, f in tramos:
        if fin_act is not None and i <= fin_act + 1:
            fin_act = max(fin_act, f)
        else:
            if ini_act is not None:
                cola_max = max(cola_max, largo(ini_act, fin_act))
            ini_act, fin_act = i, f
    if ini_act is not None:
        cola_max = max(cola_max, largo(ini_act, fin_act))

    if not pts:  # sin geometría: usar el total que informa TomTom
        cola_max = sm.get("trafficLengthInMeters", 0)

    return resultado(demora_min, cola_max,
                     viaje_s=sm.get("travelTimeInSeconds"),
                     habitual_s=sm.get("historicTrafficTravelTimeInSeconds"),
                     libre_s=sm.get("noTrafficTravelTimeInSeconds"))


def resultado(demora_min, cola_m, viaje_s=None, habitual_s=None, libre_s=None):
    """
    demora_min       = viaje actual - viaje sin tráfico (ruta vacía)
    extra_habitual   = viaje actual - viaje HABITUAL para este día y hora
                       (TomTom lo calcula con su historial de tráfico)
    indice_habitual  = viaje actual / viaje habitual  (1.0 = normal, 1.5 = 50% más lento)
    """
    autos = cola_m / METROS_POR_AUTO * CARRILES
    flujo = autos / (demora_min / 60) if demora_min >= 1 else None
    r = {
        "demora_min": round(demora_min, 1),
        "cola_m": round(cola_m),
        "autos_cola_est": round(autos),
        "flujo_autos_h_est": round(flujo) if flujo else None,
        "viaje_min": None, "habitual_min": None, "libre_min": None,
        "extra_habitual_min": None, "indice_habitual": None,
    }
    if viaje_s:
        r["viaje_min"] = round(viaje_s / 60, 1)
    if libre_s:
        r["libre_min"] = round(libre_s / 60, 1)
    if viaje_s and habitual_s:
        r["habitual_min"] = round(habitual_s / 60, 1)
        r["extra_habitual_min"] = round((viaje_s - habitual_s) / 60, 1)
        r["indice_habitual"] = round(viaje_s / habitual_s, 2)
    return r


# ---------------------------------------------------------------- Modo demo

def simular(nombre, cuando):
    """Demora con forma diaria realista: picos a la mañana y fin de tarde."""
    base = {"Gualeguaychú – Fray Bentos": 18,
            "Colón – Paysandú": 9,
            "Concordia – Salto": 5}[nombre]
    h = cuando.hour + cuando.minute / 60
    curva = (math.exp(-((h - 10) ** 2) / 6) + 0.8 * math.exp(-((h - 18) ** 2) / 5))
    demora = max(0.0, base * curva + random.gauss(0, base * 0.05))
    cola = demora * 55 + random.gauss(0, 30)
    libre = {"Gualeguaychú – Fray Bentos": 40, "Colón – Paysandú": 15, "Concordia – Salto": 30}[nombre]
    habitual = libre + base * curva * 0.8
    return resultado(demora, max(0.0, cola), viaje_s=(libre + demora) * 60,
                     habitual_s=habitual * 60, libre_s=libre * 60)


# ---------------------------------------------------------------- Guardado

def guardar(filas):
    if not filas:
        return
    nuevo = not os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        if nuevo:
            w.writeheader()
        w.writerows(filas)

    # datos.json: últimas N horas, leído por el dashboard
    try:
        with open(JSON_PATH, encoding="utf-8") as f:
            datos = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        datos = {"mediciones": []}
    datos["mediciones"].extend(filas)
    corte = (ahora() - timedelta(hours=HORAS_EN_DASHBOARD)).isoformat()
    datos["mediciones"] = [m for m in datos["mediciones"] if m["fecha"] >= corte]
    datos["actualizado"] = filas[-1]["fecha"]
    datos["pasos"] = list(PASOS)
    tmp = JSON_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)
    os.replace(tmp, JSON_PATH)   # escritura atómica: el dashboard nunca lee a medias


def medir(api_key, demo=False, cuando=None, silencio=False):
    cuando = cuando or ahora()
    filas = []
    for nombre, (ar, uy) in PASOS.items():
        try:
            res = simular(nombre, cuando) if demo else analizar(consultar(ar, uy, api_key))
        except Exception as e:  # noqa: BLE001
            print(f"[error] {nombre}: {e}", file=sys.stderr)
            continue
        filas.append({"fecha": cuando.isoformat(timespec="seconds"),
                      "paso": nombre, "sentido": "AR->UY", **res})
        if not silencio:
            print(f"{cuando:%H:%M}  {nombre:28} demora {res['demora_min']:>5} min  "
                  f"cola {res['cola_m']:>5} m  ~{res['autos_cola_est']} autos")
    guardar(filas)


# ---------------------------------------------------------------- Servidor web

class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):
        pass  # silencio en consola

    def do_GET(self):
        if self.path in ("/", ""):
            self.path = "/index.html"
        super().do_GET()


def servir(puerto):
    handler = functools.partial(Handler, directory=CARPETA)
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", puerto), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"Dashboard en http://localhost:{puerto}  (Ctrl+C para cortar)\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cada", type=float, default=10, help="minutos entre mediciones (10)")
    p.add_argument("--puerto", type=int, default=8000, help="puerto del dashboard (8000)")
    p.add_argument("--demo", action="store_true", help="datos simulados, sin API key")
    p.add_argument("--una-vez", action="store_true",
                   help="una sola medición y salir (lo usa GitHub Actions)")
    a = p.parse_args()

    os.chdir(CARPETA)
    key = os.environ.get("TOMTOM_API_KEY")
    if not a.demo and not key:
        sys.exit("Falta TOMTOM_API_KEY (o usá --demo para probar)")

    if a.una_vez:
        medir(key)
        return

    if a.demo:
        # Precarga 24 h simuladas para que el gráfico tenga historia
        if os.path.exists(JSON_PATH):
            os.remove(JSON_PATH)
        fin = ahora()
        t = fin - timedelta(hours=HORAS_EN_DASHBOARD)
        while t < fin:
            medir(None, demo=True, cuando=t, silencio=True)
            t += timedelta(minutes=a.cada)

    servir(a.puerto)
    try:
        while True:
            medir(key, demo=a.demo)
            time.sleep(a.cada * 60)
    except KeyboardInterrupt:
        print("\nListo.")


if __name__ == "__main__":
    main()
