#!/usr/bin/env python3
"""
Verifica si TomTom tiene datos de tráfico (históricos) en cada zona.

Para cada ruta pide a TomTom el viaje para varios horarios futuros y compara:
  - tiempo "habitual" (historial de tráfico para ese día y hora)
  - tiempo "sin tráfico"
Si en horas pico el habitual es igual al sin tráfico, TomTom no tiene
historial de tráfico en esa zona. Incluye controles: Buenos Aires (debería
tener datos) y Tokio (ya vimos que no tiene).

Uso: TOMTOM_API_KEY=... python3 verificar_cobertura.py
"""
import json, os, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

KEY = os.environ.get("TOMTOM_API_KEY") or sys.exit("Falta TOMTOM_API_KEY")
URL = "https://api.tomtom.com/routing/1/calculateRoute/{p}/json"

RUTAS = {
    "Colón – Paysandú":            ((-32.2234, -58.1440), (-32.3171, -58.0807)),
    "Gualeguaychú – Fray Bentos":  ((-33.0094, -58.5172), (-33.1165, -58.3107)),
    "Concordia – Salto":           ((-31.3929, -58.0209), (-31.3833, -57.9667)),
    "Paraná centro → Santa Fe":    ((-31.7413, -60.5115), (-31.6333, -60.7000)),
    "Colón centro → acceso puente": ((-32.2234, -58.1440), (-32.2600, -58.1150)),
    "CONTROL Buenos Aires: Obelisco → San Isidro": ((-34.6037, -58.3816), (-34.4708, -58.5286)),
    "CONTROL Tokio: Haneda → Est. Tokio": ((35.5494, 139.7798), (35.6812, 139.7671)),
}

def horarios():
    """Viernes 6 y sábado 7 en hora pico (hora local de cada zona)."""
    return [("vie 08:00", "2026-11-06T08:00:00"), ("vie 18:00", "2026-11-06T18:00:00"),
            ("sáb 06:00", "2026-11-07T06:00:00"), ("sáb 13:00", "2026-11-07T13:00:00")]

def consultar(puntos, depart):
    ruta = ":".join(f"{a},{b}" for a, b in puntos)
    q = urllib.parse.urlencode({"key": KEY, "traffic": "true", "travelMode": "car",
                                "computeTravelTimeFor": "all", "departAt": depart})
    with urllib.request.urlopen(URL.format(p=ruta) + "?" + q, timeout=30) as r:
        return json.load(r)["routes"][0]["summary"]

print(f"{'Ruta':46} {'Horario':10} {'sin tráf.':>9} {'habitual':>9} {'dif.':>7}")
resumen = {}
for nombre, pts in RUTAS.items():
    difs = []
    for etiqueta, t in horarios():
        # Tokio: mismo horario local
        try:
            sm = consultar(pts, t)
        except Exception as e:
            print(f"{nombre:46} {etiqueta:10} error: {e}")
            continue
        libre = sm.get("noTrafficTravelTimeInSeconds", 0) / 60
        hist = sm.get("historicTrafficTravelTimeInSeconds", 0) / 60
        difs.append(hist - libre)
        print(f"{nombre:46} {etiqueta:10} {libre:8.1f}m {hist:8.1f}m {hist - libre:+6.1f}m")
    resumen[nombre] = max(difs) if difs else None
print()
print("RESUMEN (máxima diferencia habitual - sin tráfico en hora pico):")
for n, d in resumen.items():
    estado = "sin datos" if d is None else ("CON historial de tráfico" if d >= 0.5 else "SIN historial (habitual = sin tráfico)")
    print(f"  {n:46} {('%+.1f min' % d) if d is not None else '':>10}  {estado}")
