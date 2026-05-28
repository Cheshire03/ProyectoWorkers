import boto3
import redis
import json
import uuid
import os
import asyncio
import logging
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [API] %(levelname)s: %(message)s"
)
log = logging.getLogger(__name__)

# ── Configuración ─────────────────────────────────────────────────────────────
AWS_REGION    = os.getenv("AWS_REGION", "us-east-1")
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL")
S3_BUCKET     = os.getenv("S3_BUCKET", "yeidi-objects")
REDIS_HOST    = os.getenv("REDIS_HOST", "redis")
REDIS_PORT    = int(os.getenv("REDIS_PORT", 6379))

# ── Clientes ──────────────────────────────────────────────────────────────────
sqs = boto3.client("sqs", region_name=AWS_REGION)
s3  = boto3.client("s3",  region_name=AWS_REGION)
r   = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="CSV Worker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

VALID_OPERATIONS = ["statistics", "validate", "filter", "sort", "summary"]


# ── POST /tasks — subir CSV y encolar tarea ───────────────────────────────────
@app.post("/tasks")
async def create_task(
    file:      UploadFile = File(...),
    operation: str        = Form(...),
    params:    str        = Form("{}"),   # JSON string con params opcionales
):
    # Validar operación
    if operation not in VALID_OPERATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Operación inválida. Usa: {VALID_OPERATIONS}"
        )

    # Validar que sea CSV
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos .csv")

    # Parsear params
    try:
        params_dict = json.loads(params)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="'params' debe ser un JSON válido")

    task_id = str(uuid.uuid4())
    s3_key  = f"uploads/{task_id}_{file.filename}"

    # 1. Subir CSV a S3
    try:
        content = await file.read()
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=content,
            ContentType="text/csv",
        )
        log.info(f"[{task_id}] CSV subido a s3://{S3_BUCKET}/{s3_key}")
    except Exception as e:
        log.error(f"Error subiendo a S3: {e}")
        raise HTTPException(status_code=500, detail=f"Error subiendo archivo: {str(e)}")

    # 2. Guardar estado inicial en Redis
    r.hset(f"task:{task_id}", mapping={
        "task_id":   task_id,
        "status":    "pendiente",
        "operation": operation,
        "filename":  file.filename,
        "s3_key":    s3_key,
    })
    r.expire(f"task:{task_id}", 3600)

    # 3. Encolar en SQS
    try:
        sqs.send_message(
            QueueUrl=SQS_QUEUE_URL,
            MessageBody=json.dumps({
                "task_id":   task_id,
                "s3_key":    s3_key,
                "operation": operation,
                "params":    params_dict,
            }),
        )
        log.info(f"[{task_id}] Tarea encolada en SQS — operación: {operation}")
    except Exception as e:
        log.error(f"Error enviando a SQS: {e}")
        raise HTTPException(status_code=500, detail=f"Error encolando tarea: {str(e)}")

    return JSONResponse({
        "task_id":   task_id,
        "status":    "pendiente",
        "operation": operation,
        "filename":  file.filename,
    })


# ── GET /tasks/{task_id} — estado de una tarea ────────────────────────────────
@app.get("/tasks/{task_id}")
def get_task(task_id: str):
    data = r.hgetall(f"task:{task_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return data


# ── GET /tasks/{task_id}/result — descargar resultado desde S3 ────────────────
@app.get("/tasks/{task_id}/result")
def get_result(task_id: str):
    data = r.hgetall(f"task:{task_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    if data.get("status") != "completada":
        raise HTTPException(status_code=400, detail="La tarea aún no está completada")

    result_key = data.get("result_key")
    if not result_key:
        raise HTTPException(status_code=404, detail="Resultado no disponible")

    try:
        obj  = s3.get_object(Bucket=S3_BUCKET, Key=result_key)
        body = obj["Body"].read()
        return JSONResponse(json.loads(body))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo resultado: {str(e)}")


# ── GET /workers — estado de los workers ──────────────────────────────────────
@app.get("/workers")
def get_workers():
    import time
    workers = []
    keys = r.keys("worker:*:heartbeat")
    for key in keys:
        worker_id  = key.split(":")[1]
        heartbeat  = r.get(key)
        status     = r.get(f"worker:{worker_id}:status") or "unknown"
        last_seen  = int(time.time()) - int(heartbeat) if heartbeat else None
        workers.append({
            "worker_id": worker_id,
            "status":    status,
            "last_seen": f"{last_seen}s ago" if last_seen is not None else "unknown",
            "active":    last_seen is not None and last_seen < 30,
        })
    return {"workers": workers, "total": len(workers)}


# ── GET /sse/tasks — stream de eventos en tiempo real ─────────────────────────
@app.get("/sse/tasks")
async def sse_tasks():
    async def event_stream():
        pubsub = r.pubsub()
        pubsub.subscribe("task_updates")
        log.info("SSE client conectado")
        try:
            while True:
                msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    yield f"data: {msg['data']}\n\n"
                else:
                    # Heartbeat para mantener la conexión abierta
                    yield ": heartbeat\n\n"
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pubsub.unsubscribe("task_updates")
            log.info("SSE client desconectado")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ── GET /health ───────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    try:
        r.ping()
        redis_ok = True
    except Exception:
        redis_ok = False
    return {
        "status":  "ok" if redis_ok else "degraded",
        "redis":   "ok" if redis_ok else "error",
    }


# ── Servir frontend estático ──────────────────────────────────────────────────
app.mount("/", StaticFiles(directory="static", html=True), name="static")