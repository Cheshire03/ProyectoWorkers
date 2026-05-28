import boto3
import redis
import json
import uuid
import os
import asyncio
import logging
import math
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, Response
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


# ── Helper: limpiar NaN/Inf para JSON ─────────────────────────────────────────
def sanitize(obj):
    """Reemplaza NaN e Infinity por None recursivamente."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(i) for i in obj]
    return obj


# ── POST /tasks — subir uno o varios CSVs y encolar tareas ───────────────────
@app.post("/tasks")
async def create_task(
    files:     list[UploadFile] = File(...),
    operation: str              = Form(...),
    params:    str              = Form("{}"),
):
    if operation not in VALID_OPERATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Operación inválida. Usa: {VALID_OPERATIONS}"
        )

    try:
        params_dict = json.loads(params)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="'params' debe ser un JSON válido")

    created = []

    for file in files:
        if not file.filename.endswith(".csv"):
            continue  # saltar archivos que no sean CSV

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
            log.info(f"[{task_id}] CSV subido → s3://{S3_BUCKET}/{s3_key}")
        except Exception as e:
            log.error(f"Error subiendo {file.filename} a S3: {e}")
            continue

        # 2. Estado inicial en Redis
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
            log.info(f"[{task_id}] Encolado en SQS — operación: {operation}")
        except Exception as e:
            log.error(f"Error encolando {task_id}: {e}")
            continue

        created.append({
            "task_id":   task_id,
            "status":    "pendiente",
            "operation": operation,
            "filename":  file.filename,
        })

    if not created:
        raise HTTPException(status_code=400, detail="No se pudo procesar ningún archivo CSV.")

    return JSONResponse({"tasks": created, "total": len(created)})


# ── GET /tasks/{task_id} — estado de una tarea ────────────────────────────────
@app.get("/tasks/{task_id}")
def get_task(task_id: str):
    data = r.hgetall(f"task:{task_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return data


# ── GET /tasks/{task_id}/result — ver resultado en JSON ───────────────────────
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
        obj    = s3.get_object(Bucket=S3_BUCKET, Key=result_key)
        body   = json.loads(obj["Body"].read())
        clean  = sanitize(body)   # ← limpia NaN antes de serializar
        return JSONResponse(clean)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo resultado: {str(e)}")


# ── GET /tasks/{task_id}/download — descargar resultado como archivo ──────────
@app.get("/tasks/{task_id}/download")
def download_result(task_id: str):
    data = r.hgetall(f"task:{task_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    if data.get("status") != "completada":
        raise HTTPException(status_code=400, detail="La tarea aún no está completada")

    result_key = data.get("result_key")
    if not result_key:
        raise HTTPException(status_code=404, detail="Resultado no disponible")

    try:
        obj   = s3.get_object(Bucket=S3_BUCKET, Key=result_key)
        body  = json.loads(obj["Body"].read())
        clean = sanitize(body)
        filename = f"{data.get('operation', 'result')}_{data.get('filename', 'output')}.json"
        return Response(
            content=json.dumps(clean, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error descargando resultado: {str(e)}")


# ── GET /workers — estado de los workers ──────────────────────────────────────
@app.get("/workers")
def get_workers():
    import time
    workers = []
    keys = r.keys("worker:*:heartbeat")
    for key in keys:
        worker_id = key.split(":")[1]
        heartbeat = r.get(key)
        status    = r.get(f"worker:{worker_id}:status") or "unknown"
        last_seen = int(time.time()) - int(heartbeat) if heartbeat else None
        workers.append({
            "worker_id": worker_id,
            "status":    status,
            "last_seen": f"{last_seen}s ago" if last_seen is not None else "unknown",
            "active":    last_seen is not None and last_seen < 30,
        })
    return {"workers": workers, "total": len(workers)}


# ── GET /sse/tasks — stream SSE en tiempo real ────────────────────────────────
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
    return {"status": "ok" if redis_ok else "degraded", "redis": "ok" if redis_ok else "error"}


# ── Servir frontend estático ──────────────────────────────────────────────────
app.mount("/", StaticFiles(directory="static", html=True), name="static")