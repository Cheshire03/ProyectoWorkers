import sys
import os
import time
import signal
import json
import redis
import boto3
from botocore.exceptions import ClientError
import s3image

SQS_URL = os.environ.get('SQS_URL')
SQS_URL = 'https://sqs.us-east-1.amazonaws.com/197659111769/MyQueue'

REDIS_HOST = os.environ.get('REDIS_HOST')
if not REDIS_HOST:
    print("Error: La variable de entorno REDIS_HOST no está definida", flush=True)
    sys.exit(1)

r = redis.Redis(host=REDIS_HOST, decode_responses=True)

redis_ready = False
while not redis_ready:
    try:
        if r.ping():
            print("Redis is connected", flush=True)
            redis_ready = True
    except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
        print(f"Redis connection error: {e}", flush=True)
        print("Waiting for redis", flush=True)
        time.sleep(3)
    except Exception as e:
        print(f"Waiting for redis: {e}", flush=True)
        time.sleep(3)

print("Redis is active", flush=True)
if not SQS_URL:
    print("Error: La variable de entorno SQS_URL no está definida", flush=True)
    sys.exit(1)

client = boto3.client('sqs', region_name='us-east-1')


run = True
stop_after_next = len(sys.argv) > 1 and sys.argv[1] == 'stop'


def handle_signal(signum, frame):
    global run
    print(f"\nSeñal {signum} recibida, deteniendo worker...", flush=True)
    run = False


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

while run:
    if stop_after_next:
        run = False

    try:
        message = client.receive_message(QueueUrl=SQS_URL, WaitTimeSeconds=2)
    except ClientError as e:
        if e.response['Error']['Code'] == 'QueueDoesNotExist':
            print("The queue does not exist.")
        else:
            raise e
            time.sleep(3)
        continue

    if message and 'Messages' in message and message['Messages']:
        try:
            receipt_handle = message['Messages'][0]['ReceiptHandle']
            body = json.loads(message['Messages'][0]['Body'])
            bucket_name = body['Records'][0]['s3']['bucket']['name']
            key = body['Records'][0]['s3']['object']['key']
            filename = key.split('/')[-1]
            message_id = message['Messages'][0]['MessageId']
            print(message_id, bucket_name, key, receipt_handle)
            s3image.download_file(bucket_name, key, 'image.jpg')
            print('imagen recibida')
            s3image.resize_image('image.jpg','new.jpg')
            print('imagen transformada') 
            s3image.upload_file('new.jpg', bucket_name,
                     f'small/{filename}',  extra_args={'ACL': 'public-read'}) 
            print('imagen almacenada')
            client.delete_message(QueueUrl=SQS_URL, ReceiptHandle=receipt_handle)
            print('mensaje eliminado')
            ok = r.set(filename, "ok")
            #ok = r.set(filename, "ok", ex=2000)
            assert ok
        except Exception as e:
            print(e)
            client.delete_message(QueueUrl=SQS_URL, ReceiptHandle=receipt_handle)

print("Worker detenido.", flush=True)
