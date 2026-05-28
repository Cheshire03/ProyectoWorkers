from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request

import boto3
from pydantic import BaseModel
import pathlib
from uuid import uuid4


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
    presigned_data = s3_generate_presigned_post(file_path=file_name,
                                                file_type=file.file_type)
    print(file_name, presigned_data)
    return presigned_data


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
    return f"images/{file_name}-{uuid4().hex}{extension}"
