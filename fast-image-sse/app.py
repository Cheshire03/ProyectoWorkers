from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import StreamingResponse
import boto3
from pydantic import BaseModel
import pathlib
from uuid import uuid4
import asyncio
import redis.asyncio as aioredis
import json


FOLDER = 'images/'


class File(BaseModel):
    file_name: str
    file_type: str


app = FastAPI()

# archivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")

# templates HTML
templates = Jinja2Templates(directory="templates")


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )


@app.post("/api/presigned-post")
def upload_start(file: File):
    file_name = file_generate_name(file.file_name)
    file_path = f'{FOLDER}/{file_name}'
    presigned_data = s3_generate_presigned_post(file_path=file_path,
                                                file_type=file.file_type)
    print(file_name, presigned_data)
    return {
        "file_name": file_name,
        "presigned": presigned_data
    }


def s3_generate_presigned_post(*, file_path: str, file_type: str):
    s3_client = boto3.client(service_name="s3")

    acl = 'public-read'  # 'private'
    expires_in = 1000

    presigned_data = s3_client.generate_presigned_post(
        'yeidi-objects',
        file_path,
        Fields={
            "acl": acl,
            "Content-Type": file_type
        },
        Conditions=[
            {"acl": acl},
            {"Content-Type": file_type},
        ],
        ExpiresIn=expires_in,
    )
    return presigned_data


def file_generate_name(original_file_name):
    name = pathlib.Path(original_file_name)
    extension = name.suffix
    file_name = name.stem
    return f"{file_name}-{uuid4().hex}{extension}"


async def event_generator(filename: str):
    redis = aioredis.from_url(
       'redis://localhost:6379', encoding="utf-8", decode_responses=True
    )
    # Assuming you have some mechanism to get data for a specific user
    while True:
        # data = await get_data_for_user(user_id)  # Your function to get data
        # Redis client bound to single connection (no auto reconnection).
        async with redis.client() as conn:
            val = await conn.get(filename)
        print(filename, val)
        if val == "ok":
            data = json.dumps({'content': filename})
            yield f"data: {data}\n\n"
            break
        else:
            data = json.dumps({'content': 'not-found'})
            yield f"data: {data}\n\n"
        await asyncio.sleep(1)  # Interval between messages


@app.get("/events/{filename}")
async def events(request: Request, filename: str):
    event_stream = event_generator(filename)
    return StreamingResponse(event_stream, media_type="text/event-stream")
