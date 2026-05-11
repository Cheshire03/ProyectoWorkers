# Instrucciones de prueba local

## Estructura del proyecto

```
.
├── worker/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── worker.py
├── images/
│   ├── a.y.-jackson_wilderness-deese-bay.jpg
│   ├── caravaggio_boy-with-a-basket-of-fruit.jpg
│   └── ... (98 imágenes más)
├── enqueue_images.py
├── s3image.py
└── instrucciones.md
```

---

# Parte 1: Docker manual (entender los pasos)

## 1. Construir la imagen del worker

```bash
docker build -t my-worker worker/
```

## 2. Lanzar Redis

```bash
docker run -d --name redis -p 6379:6379 redis:alpine
```

## 3. Lanzar uno o varios workers

```bash
# Worker 1
## En caso de utilizar Docker Desktop
docker run -d --name worker1 -e REDIS_HOST=host.docker.internal my-worker
## En caso de utilizar Linux (o instancia de AWS)
docker run -d --name worker1 -e REDIS_HOST=<IP-PRIVADA>

# Worker 2 (opcional, para probar concurrencia)
docker run -d --name worker2 -e REDIS_HOST=host.docker.internal my-worker
```

Ver logs:
```bash
docker logs -f worker1
docker logs -f worker2
```

## 4. Encolar imágenes de prueba a Redis

Ver el directorio con imágenes:
Si quieres cargar más imágenes esta es una muestra tomada de [Kaggle](https://www.kaggle.com/datasets/steubk/wikiart?resource=download).

```bash
ls images
```

Ejecutar el enqueuer (necesita la librería `redis` y Redis funcionando):

### Opción A: Con Python local
```bash
export REDIS_HOST=localhost
python enqueue_images.py images/
```

### Opción B: Con Docker (si no tienes Python local)
```bash
docker run --rm \
  -e REDIS_HOST=host.docker.internal \
  -v "$(pwd)/images:/images" \
  -v "$(pwd)/enqueue_images.py:/enqueue_images.py" \
  python:3.12-slim \
  bash -c "pip install redis && python /enqueue_images.py /images"
```

## 5. Verificar que los workers procesaron las mensajes

```bash
docker logs worker1
docker logs worker2
```

Deberías ver mensajes como:
```
Imagen "foto1.jpg" procesada exitosamente
Imagen "foto2.png" procesada exitosamente
```

## 6. Detener todo

```bash
docker stop worker1 worker2 redis
docker rm worker1 worker2 redis
```

## Otros comandos de Docker para detener y eliminar contenedores

Detener y remover a un contenedore en ejecución

```bash
docker rm -f nombre_contenedor
```

Crear un contenedor efímero 

```bash
docker run --rm redis
```

Eliminar todos los contenedores

```bash
docker container prune -f
```

## Notas (Docker manual)

- `host.docker.internal` permite que los contenedores se conecten a servicios en la máquina host (Redis en `localhost:6379`).
- En Linux, si `host.docker.internal` no funciona, usa la IP de la máquina host o `--network host`.
- El worker maneja `SIGTERM` correctamente, así que `docker stop` lo detiene limpiamente.





---

# Parte 2: Docker Compose (automatizar)

Después de entender los pasos manuales, usa Docker Compose para levantar todo con un solo comando.

## 1. Lanzar todo

```bash
docker compose up -d
```

Esto levanta:
- **Redis** en el puerto 6379
- **2 workers** que consumen de la cola

Ver logs:
```bash
docker compose logs -f worker
```

## 2. Encolar imágenes

Igual que en la Parte 1 (Opción A o B).

## 3. Escalar workers (opcional)

```bash
docker compose up -d --scale worker=5
```

## 4. Detener todo

```bash
docker compose down
```

## Notas (Docker Compose)

- Los workers se conectan a Redis por el nombre de servicio (`REDIS_HOST=redis`), gracias a la red interna de Docker Compose. No hace falta `host.docker.internal`.
- El `depends_on` con `condition: service_healthy` espera a que Redis esté listo antes de arrancar los workers.
- El worker sigue teniendo su loop de reconexión como respaldo.
