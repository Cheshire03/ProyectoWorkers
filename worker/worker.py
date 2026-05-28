import boto3
import redis
import json
import os
import time
import uuid
import logging
import pandas as pd
from io import StringIO

from tasks import statistics, validate, filter, sort, summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WORKER-%(process)d] %(levelname)s: %(message)s"
)
log = logging.getLogger(__name__)

# ── Configuración ────────────────────────────────────────────────────────────
AWS_REGION    = os.getenv("AWS_REGION", "us-east-1")
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL") 
S3_BUCKET     = os.getenv("S3_BUCKET", "yeidi-objects")
REDIS_HOST    = os.getenv("REDIS_HOST", "redis")
REDIS_PORT    = int(os.getenv("REDIS_PORT", 6379))
WORKER_ID     = os.getenv("WORKER_ID", str(uuid.uuid4())[:8])

# ── Clientes AWS / Redis ─────────────────────────────────────────────────────
sqs = boto3.client("sqs", region_name=AWS_REGION)
s3  = boto3.client("s3",  region_name=AWS_REGION)
r   = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

# ── Operaciones soportadas ───────────────────────────────────────────────────
OPERATIONS = {
    "statistics": lambda df, p: statistics.run(df),
    "validate":   lambda df, p: validate.run(df),
    "filter":     lambda df, p: filter.run(df, p),
    "sort":       lambda df, p: sort.run(df, p),
    "summary":    lambda df, p: summary.run(df),
}


def set_status(task_id: str, status: str, extra: dict = {}):
    """Guarda el estado de la tarea en Redis y publica evento SSE."""
    payload = {
        "task_id":   task_id,
        "status":    status,
        "worker_id": WORKER_ID,
        **extra,
    }
    # Hash con el estado actual
    r.hset(f"task:{task_id}", mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in payload.items()})
    r.expire(f"task:{task_id}", 3600)  # expira en 1 hora

    # Canal pub/sub para SSE
    r.publish("task_updates", json.dumps(payload))
    log.info(f"[{task_id}] status={status}")


def process_message(msg: dict):
    body    = json.loads(msg["Body"])
    task_id = body.get("task_id", str(uuid.uuid4()))
    s3_key  = body.get("s3_key")        # ej: "uploads/archivo.csv"
    op      = body.get("operation")     # statistics | validate | filter | sort | summary
    params  = body.get("params", {})    # parámetros extra para filter/sort

    log.info(f"[{task_id}] Iniciando operación '{op}' sobre '{s3_key}'")

    if op not in OPERATIONS:
        set_status(task_id, "error", {"mensaje": f"Operación '{op}' no soportada."})
        return

    # 1. Marcar como en proceso
    set_status(task_id, "en_proceso", {"operacion": op, "s3_key": s3_key})

    try:
        # 2. Descargar CSV desde S3
        obj      = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
        csv_body = obj["Body"].read().decode("utf-8")
        df       = pd.read_csv(StringIO(csv_body))
        log.info(f"[{task_id}] CSV cargado: {len(df)} filas, {len(df.columns)} columnas")

        # 3. Ejecutar operación
        resultado = OPERATIONS[op](df, params)

        # 4. Guardar resultado en S3
        result_key = f"results/{task_id}_{op}.json"
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=result_key,
            Body=json.dumps(resultado, ensure_ascii=False, default=str),
            ContentType="application/json",
        )
        log.info(f"[{task_id}] Resultado guardado en s3://{S3_BUCKET}/{result_key}")

        # 5. Marcar como completada
        set_status(task_id, "completada", {
            "operacion":  op,
            "result_key": result_key,
            "resumen":    str(resultado)[:200],  # preview en Redis
        })

    except Exception as e:
        log.error(f"[{task_id}] Error: {e}", exc_info=True)
        set_status(task_id, "error", {"mensaje": str(e)})


def main():
    log.info(f"Worker {WORKER_ID} iniciado. Escuchando en SQS...")
    r.set(f"worker:{WORKER_ID}:status", "idle")

    while True:
        try:
            # Heartbeat del worker
            r.set(f"worker:{WORKER_ID}:heartbeat", int(time.time()), ex=30)

            response = sqs.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=10,      # long polling
                VisibilityTimeout=300,   # 5 min para procesar
            )

            messages = response.get("Messages", [])
            if not messages:
                continue

            msg = messages[0]
            r.set(f"worker:{WORKER_ID}:status", "busy")

            try:
                process_message(msg)
                # Borrar mensaje de la cola si se procesó bien
                sqs.delete_message(
                    QueueUrl=SQS_QUEUE_URL,
                    ReceiptHandle=msg["ReceiptHandle"],
                )
            except Exception as e:
                log.error(f"Error procesando mensaje: {e}", exc_info=True)
            finally:
                r.set(f"worker:{WORKER_ID}:status", "idle")

        except Exception as e:
            log.error(f"Error en el loop principal: {e}", exc_info=True)
            time.sleep(5)


if __name__ == "__main__":
    main()