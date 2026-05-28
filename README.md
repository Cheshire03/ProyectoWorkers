# CSV Worker — Procesamiento Distribuido Cloud Native

Aplicación web para procesar archivos CSV mediante workers distribuidos en contenedores Docker, usando AWS SQS como cola de mensajes, S3 para almacenamiento y Redis para estado en tiempo real.

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

### Ejemplos de parámetros para `filter` y `sort`

```json
// filter: filas donde precio > 100
{ "columna": "precio", "operador": ">", "valor": 100 }

// sort: ordenar por fecha descendente
{ "columna": "fecha", "ascendente": false }
```

## Requisitos previos

- EC2 con IAM Role que tenga permisos sobre SQS y S3
- Docker y Docker Compose instalados
- Puerto `8000` abierto en el Security Group

Verificar Docker Compose:
```bash
docker compose version
```

Verificar acceso a AWS:
```bash
aws sts get-caller-identity
aws s3 ls s3://yeidi-objects
aws sqs get-queue-attributes \
  --queue-url https://sqs.us-east-1.amazonaws.com/197659111769/MyQueue \
  --attribute-names All
```

## Instalación y uso

### 1. Clonar el repositorio

```bash
git clone <tu-repo>
cd proyecto
```

### 2. Primera vez — construir y levantar

```bash
docker compose up --build -d
```

Esto levanta:
- `redis` — base de datos de estado
- `api` — FastAPI en el puerto 8000
- `worker` — 3 instancias procesando tareas

### 3. Verificar que todo está corriendo

```bash
docker compose ps
```

Deberías ver:
```
NAME        STATUS
redis       running
api         running
worker-1    running
worker-2    running
worker-3    running
```

### 4. Abrir la aplicación

```
http://TU_IP_ELASTICA:8000
```

La documentación interactiva de la API está en:
```
http://TU_IP_ELASTICA:8000/docs
```

## Comandos del día a día

| Situación | Comando |
|---|---|
| Primera vez o cambié código | `docker compose up --build -d` |
| Reiniciar sin cambios | `docker compose restart` |
| Ver logs en vivo | `docker compose logs -f` |
| Ver logs solo de workers | `docker compose logs -f worker` |
| Ver logs solo de la API | `docker compose logs -f api` |
| Ver contenedores activos | `docker compose ps` |
| Apagar todo | `docker compose down` |
| Apagar y eliminar imágenes | `docker compose down --rmi all` |

## Endpoints de la API

| Método | Endpoint | Descripción |
|---|---|---|
| `POST` | `/tasks` | Sube CSV y encola tarea |
| `GET` | `/tasks/{task_id}` | Estado de una tarea |
| `GET` | `/tasks/{task_id}/result` | Resultado de una tarea completada |
| `GET` | `/workers` | Estado de los workers activos |
| `GET` | `/sse/tasks` | Stream de eventos en tiempo real (SSE) |
| `GET` | `/health` | Salud del sistema |

## Estados de una tarea

```
pendiente ──▶ en_proceso ──▶ completada
                    └──────▶ error
```

| Estado | Descripción |
|---|---|
| `pendiente` | Tarea encolada en SQS, esperando worker |
| `en_proceso` | Un worker tomó la tarea y está procesando |
| `completada` | Procesamiento exitoso, resultado en S3 |
| `error` | Ocurrió un error durante el procesamiento |

## Flujo de una tarea

1. Usuario sube un CSV y elige una operación desde el frontend
2. FastAPI guarda el CSV en **S3** (`uploads/`)
3. FastAPI encola un mensaje en **SQS** con el `task_id`, `s3_key` y `operation`
4. Un worker libre toma el mensaje de SQS
5. El worker descarga el CSV desde S3 y actualiza el estado en Redis a `en_proceso`
6. El worker procesa el CSV y guarda el resultado en S3 (`results/`)
7. El worker actualiza el estado en Redis a `completada`
8. El frontend recibe el update via **SSE** y muestra el resultado