# Tecnologías del Backend — FashionStore

Stack tecnológico usado en el backend de la plataforma e-commerce multi-sucursal FashionStore (examen SI2).

---

## Resumen del stack

| Capa | Tecnología | Rol |
|------|------------|-----|
| Lenguaje | **Python 3.12+** (dev local puede usar 3.14) | Runtime |
| Framework web | **Django 5.1** | App monolítica, ORM, admin |
| API REST | **Django REST Framework 3.15** | Endpoints JSON |
| Base de datos | **PostgreSQL** + **pgvector** | Persistencia + embeddings |
| Caché / broker | **Redis** | Cola Celery y resultados |
| Tareas async | **Celery 5.4** + **django-celery-beat** | rembg, reportes, jobs |
| Auth | **SimpleJWT** + **Argon2** | JWT Bearer + hash de passwords |
| Pagos | **Stripe** | Checkout web / webhooks |
| Media / imágenes | **Pillow**, **rembg**, **OpenCV**, **YOLO-pose** | Catálogo + AR |
| Docs API | **drf-spectacular** | OpenAPI / Swagger |
| PDF | **WeasyPrint** | Comprobantes / reportes |
| Servidor prod | **Gunicorn** | WSGI |

---

## 1. Núcleo de la aplicación

### Django 5.1
- Framework principal.
- Settings por entorno: `config/settings/base.py`, `dev.py`, `prod.py`.
- Variables de entorno con **django-environ**.
- Usuario custom (`accounts.User`) con roles: CUSTOMER, ADMIN, BRANCH_MANAGER, CASHIER, SUPPLIER.

### Django REST Framework (DRF) 3.15
- ViewSets, serializers, permisos RBAC.
- Paginación, filtros y validación de payloads.
- Parsers multipart para subida de imágenes.

### Apps del proyecto
`core`, `accounts`, `branches`, `catalog`, `suppliers`, `inventory`, `reservations`, `orders`, `payments`, `pos`, `promotions`, `reports`, `ai`, `notifications`.

---

## 2. Base de datos e infraestructura de datos

### PostgreSQL
- Motor relacional principal.
- Driver: **psycopg 3.2** (`psycopg[binary]`).
- Transacciones atómicas para inventario (`select_for_update`).

### pgvector 0.3
- Extensión de PostgreSQL para vectores.
- Usada en embeddings de productos (`ProductEmbedding`) para recomendaciones / similitud.

### Redis 5
- Broker de mensajes para Celery (`redis://localhost:6379/0`).
- Backend de resultados de tareas.

---

## 3. Autenticación y seguridad

| Librería | Uso |
|----------|-----|
| **djangorestframework-simplejwt** | Access / refresh tokens (Bearer) |
| **argon2-cffi** | Hasher de contraseñas (Argon2) |
| **django-cors-headers** | CORS para Angular y app móvil |
| Validadores Django | Longitud, similitud, comunes, numéricos |

---

## 4. API y documentación

| Librería | Uso |
|----------|-----|
| **django-filter** | Filtros por query params (`?product=`, `?color=`, etc.) |
| **drf-spectacular** | Esquema OpenAPI 3 + UI Swagger / Redoc |
| **python-slugify** | Slugs ASCII para URLs y nombres de archivo |

---

## 5. Tareas asíncronas

### Celery 5.4
- Worker aparte del `runserver`.
- Tareas: `build_ar_asset` (recorte AR), reportes, jobs periódicos.

### django-celery-beat 2.7
- Schedules persistidos en DB (tareas periódicas).

### Configuración relevante
- `CELERY_TASK_ACKS_LATE = True`
- `CELERY_WORKER_PREFETCH_MULTIPLIER = 1`
- `CELERY_TASK_TIME_LIMIT = 600` (10 min)

---

## 6. Pagos

### Stripe SDK (stripe 10)
- Intentos de pago, Checkout, webhooks.
- Idempotencia vía `StripeWebhookEvent`.
- Canales: WEB, MOBILE, POS.

---

## 7. Media, imágenes y probador AR

Dependencias en `requirements/ar.txt` (además de `base.txt`):

| Librería | Uso |
|----------|-----|
| **Pillow** | Validar, recortar, redimensionar, PNG con alfa |
| **NumPy** | Cálculo de máscaras / anclas sobre silueta |
| **rembg** + **onnxruntime** | Recorte automático de fondo (modelo `u2net`) |
| **opencv-python-headless** | Procesamiento de imagen sin GUI |
| **ultralytics (YOLO11-pose)** | Detección de hombros/caderas en fotos de catálogo para calibrar `anchor_config` |

Flujo AR:
1. Admin sube imagen (front Angular) → `source_image`
2. Celery corre rembg (+ opcional YOLO-pose)
3. Guarda PNG procesado + `anchor_config`
4. App móvil consume el overlay con MoveNet

---

## 8. Reportes y documentos

| Librería | Uso |
|----------|-----|
| **WeasyPrint** | Generación de PDF (comprobantes, reportes) |

---

## 9. Producción y desarrollo

### Producción (`requirements/prod.txt`)
- **Gunicorn** — servidor WSGI
- Media servida por nginx (no por Django) en despliegue real

### Desarrollo / calidad (`requirements/dev.txt`)
| Herramienta | Uso |
|-------------|-----|
| **pytest** + **pytest-django** + **pytest-cov** | Tests |
| **model-bakery** | Fixtures de modelos |
| **ruff** | Linter / formato |
| **mypy** + **django-stubs** + **djangorestframework-stubs** | Tipado estático |
| **django-extensions** | Utilidades de desarrollo |

---

## 10. Cómo se instalan

```bash
# Núcleo
pip install -r requirements/base.txt

# + pipeline AR (rembg, YOLO-pose, OpenCV)
pip install -r requirements/ar.txt

# Desarrollo
pip install -r requirements/dev.txt

# Producción
pip install -r requirements/prod.txt
```

Servicios locales típicos:

```bash
# PostgreSQL y Redis deben estar corriendo
python manage.py runserver 0.0.0.0:8000
celery -A config worker -l info
```

---

## 11. Diagrama rápido del stack

```
Cliente (Angular / React Native)
        │  HTTPS / JWT
        ▼
   Django + DRF  ──────► PostgreSQL (+ pgvector)
        │
        ├── Stripe (pagos)
        │
        └── Celery worker ◄── Redis
                 │
                 ├── rembg / ONNX (cutout AR)
                 ├── YOLO-pose (anclas corporales)
                 └── WeasyPrint (PDF)
```

---

## 12. Versiones fijadas (referencia)

Fuente: `requirements/base.txt`, `ar.txt`, `dev.txt`, `prod.txt`.

- Django `5.1.*`
- djangorestframework `3.15.*`
- psycopg `3.2.*`
- Celery `5.4.*`
- Redis client `5.0.*`
- Stripe `10.*`
- Pillow `10.4.*`
- rembg `2.0.*`
- ultralytics `>=8.3,<9`
- Gunicorn `22.*`

---

*Documento generado para el backend FashionStore (SI2). Actualizar si se agregan dependencias nuevas a `requirements/`.*
