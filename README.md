# CSV Worker — Procesamiento Distribuido Cloud Native

El proyecto consiste en una aplicación web de procesamiento distribuido que permite al usuario cargar archivos en formato CSV, elegir una operación y obtener los resultados. Funciona a través de “workers” que procesan tareas de forma síncrona, los cuales se ejecutan en contenedores Docker y son coordinados mediante una cola de mensajes en AWS SQS.

## Arquitectura

```
Frontend (HTML/CSS/JS)
        │
        │  POST /tasks (sube CSV + elige operación)
        ▼
FastAPI (API)
        │
        ├──▶ S3 (guarda el CSV)
        └──▶ SQS (encola la tarea)
                    │
                    ▼
            Workers Docker (x3)
                    │
                    ├──▶ S3 (descarga CSV, guarda resultado)
                    └──▶ Redis (actualiza estado)
                                │
                                ▼
                    FastAPI SSE ──▶ Frontend (dashboard en tiempo real)
```

## Frontend
La interfaz web está construida con HTML, CSS y JavaScript. En el sitio el usuario sube cualquier archivo CSV, elige una operación y puede ver el estado de cada tarea en tiempo real. 

## Backend
Se utilizó FastAPI, actuando como intermediario entre el frontend, AWS y los workers. Al ingresar un CSV en el frontend, el backend lo recibe, lo almacena en S3, encola la tarea en SQS y expone los endpoints necesarios para consultar estados y resultados.

## Workers
Procesos de Python que corren dentro de contenedores Docker. Los workers escuchan la cola SQS de forma independiente, toman tareas al estar disponibles, descargan el archivo CSV desde S3, ejecutan la operación con pandas y guardan el resultado de vuelta en S3. El sistema corre tres workers en paralelo.

## Redis
Base de datos de estado y canal de comunicación en tiempo real. Los workers escriben el estado de cada tarea y publican eventos que el backend reenvía al frontend via SSE.


## Tecnologías

| Capa | Tecnología |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Backend | FastAPI + Uvicorn |
| Cola de mensajes | AWS SQS |
| Almacenamiento | AWS S3 |
| Estado en tiempo real | Redis + SSE |
| Workers | Python + Pandas |
| Contenedores | Docker + Docker Compose |

## Estructura del proyecto

```
proyecto/
├── docker-compose.yml
├── README.md
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   └── static/          ← frontend servido por FastAPI
│       ├── index.html
│       ├── style.css
│       └── app.js
└── worker/
    ├── Dockerfile
    ├── requirements.txt
    ├── worker.py
    └── tasks/
        ├── __init__.py
        ├── statistics.py
        ├── validate.py
        ├── filter.py
        ├── sort.py
        └── summary.py
```


## Operaciones disponibles

| Operación | Descripción | Parámetros extra |
|---|---|---|
| `summary` | Resumen general del CSV (filas, columnas, tipos, nulos) | Ninguno |
| `statistics` | Promedio, mínimo, máximo, total por columna numérica | Ninguno |
| `validate` | Detecta filas inválidas, nulos y duplicados | Ninguno |
| `filter` | Filtra filas según condición | `columna`, `operador`, `valor` |
| `sort` | Ordena el CSV por una o varias columnas | `columna`, `ascendente` |
