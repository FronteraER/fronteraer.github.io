# Pasos fronterizos Entre Ríos → Uruguay · Demoras en vivo

Dashboard público con la demora estimada para cruzar a Uruguay por:

- Gualeguaychú – Fray Bentos (Puente General San Martín)
- Colón – Paysandú (Puente General Artigas)
- Concordia – Salto (Represa Salto Grande)

Cada hora, GitHub Actions consulta el tráfico en TomTom (Routing API, gratis),
calcula demora, largo de la cola y autos estimados, guarda el resultado en
`datos.json` / `pasos.csv` y vuelve a publicar la página en GitHub Pages.

> Página: https://fronteraer.github.io

> Son estimaciones a partir del tráfico de TomTom, no conteos oficiales. Datos de tráfico © TomTom.

## Archivos

| Archivo | Qué es |
|---|---|
| `index.html` | El dashboard (lee `datos.json` cada 30 s) |
| `monitor_pasos.py` | Hace las mediciones |
| `.github/workflows/medir.yml` | Lo corre cada 10 min y publica |
| `datos.json` | Últimas 24 h (lo genera el script) |
| `pasos.csv` | Historial completo (lo genera el script) |

## Correrlo en tu compu

```
python3 monitor_pasos.py --demo              # datos simulados
TOMTOM_API_KEY=... python3 monitor_pasos.py --cada 10
```

Y abrir http://localhost:8000
