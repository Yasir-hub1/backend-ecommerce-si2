# Deploy — FashionStore Backend

Guía de despliegue del API Django en un VPS Linux (sin Docker), apuntando a:

**https://ws.ecommercefashion.shop**

Stack: Python 3.12 · Django 5.1 · Gunicorn · Nginx · PostgreSQL **17** (+ `pg_trgm`, `pgvector`) · Redis · Celery.

Requisitos del VPS (mínimo): Ubuntu 24.04 LTS, 2 vCPU, 4 GB RAM, 40 GB SSD.

---

## Topología

```
Internet ── HTTPS ──▶ Nginx (443)  ws.ecommercefashion.shop
                       ├─ /api/     → Gunicorn (Unix socket) → Django
                       ├─ /admin/   → Gunicorn
                       ├─ /static/  → collectstatic
                       └─ /media/   → imágenes catálogo / AR
                      Servicios locales:
                        PostgreSQL 17 · Redis · Celery worker · Celery beat
```

DNS: crea un registro **A** (o AAAA) de `ws.ecommercefashion.shop` → IP pública del VPS.

---

## 1. Preparación del servidor

```bash
sudo apt update && sudo apt upgrade -y
sudo timedatectl set-timezone America/La_Paz

sudo apt install -y \
  curl ca-certificates gnupg lsb-release \
  python3.12 python3.12-venv python3-pip \
  redis-server nginx git build-essential \
  libpq-dev pkg-config \
  libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi-dev \
  libjpeg-dev zlib1g-dev libpng-dev
```

Firewall (solo SSH + HTTP/HTTPS):

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

---

## 2. PostgreSQL 17 (+ pgvector)

Ubuntu 24.04 trae PostgreSQL 16 por defecto. Para la **17** usa el repositorio oficial PGDG.

### 2.1 Repositorio PGDG

```bash
sudo apt install -y curl ca-certificates
sudo install -d /usr/share/postgresql-common/pgdg
sudo curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
  --fail https://www.postgresql.org/media/keys/ACCC4CF8.asc

sudo sh -c 'echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
  https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
  > /etc/apt/sources.list.d/pgdg.list'

sudo apt update
```

### 2.2 Instalar servidor y extensiones

```bash
sudo apt install -y \
  postgresql-17 \
  postgresql-client-17 \
  postgresql-contrib-17 \
  postgresql-17-pgvector

sudo systemctl enable --now postgresql
psql --version   # debe mostrar 17.x
```

### 2.3 Base de datos y usuario de aplicación

```bash
sudo -u postgres psql
```

```sql
CREATE USER fashion_app WITH PASSWORD 'CAMBIA_ESTA_CLAVE_FUERTE';
CREATE DATABASE fashionstore OWNER fashion_app;
\c fashionstore
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;
GRANT ALL ON SCHEMA public TO fashion_app;
\q
```

### 2.4 Escuchar solo en localhost

Edita `/etc/postgresql/17/main/postgresql.conf` y confirma:

```conf
listen_addresses = 'localhost'
```

En `/etc/postgresql/17/main/pg_hba.conf` deja auth local por `scram-sha-256` (o `peer` para el usuario del sistema `postgres`). Reinicia:

```bash
sudo systemctl restart postgresql
```

Prueba:

```bash
psql -h 127.0.0.1 -U fashion_app -d fashionstore -c '\dx'
# Debe listar pg_trgm y vector
```

---

## 3. Redis

```bash
sudo systemctl enable --now redis-server
redis-cli ping   # PONG
```

Deja Redis escuchando en `127.0.0.1:6379` (default). No abras el puerto al exterior.

---

## 4. Código y entorno Python

```bash
sudo adduser --system --group --home /srv/fashionstore fashion
sudo mkdir -p /srv/fashionstore
sudo chown fashion:fashion /srv/fashionstore

# Clona el repo (ajusta la URL)
sudo -u fashion git clone <URL_DEL_REPO_BACKEND> /srv/fashionstore/backend
# Si el backend vive dentro de un monorepo, apunta al subdirectorio correcto.
cd /srv/fashionstore/backend

sudo -u fashion python3.12 -m venv .venv
sudo -u fashion .venv/bin/pip install --upgrade pip
sudo -u fashion .venv/bin/pip install -r requirements/prod.txt
# Pipeline AR (rembg / YOLO-pose). Opcional si no usas cutout en este VPS:
sudo -u fashion .venv/bin/pip install -r requirements/ar.txt

sudo -u fashion mkdir -p logs media staticfiles
```

---

## 5. Variables de entorno (`.env`)

```bash
sudo -u fashion cp .env.example .env
sudo chmod 600 /srv/fashionstore/backend/.env
sudo chown fashion:fashion /srv/fashionstore/backend/.env
```

Contenido sugerido para producción (`/srv/fashionstore/backend/.env`):

```env
# Django
DJANGO_SETTINGS_MODULE=config.settings.prod
SECRET_KEY=GENERA_UNA_CLAVE_LARGA_ALEATORIA
DEBUG=False
ALLOWED_HOSTS=ws.ecommercefashion.shop
CSRF_TRUSTED_ORIGINS=https://ws.ecommercefashion.shop

# Si el front Angular vive en otro host, agrégalo:
# CORS_ALLOWED_ORIGINS=https://ecommercefashion.shop,https://www.ecommercefashion.shop
CORS_ALLOWED_ORIGINS=https://ws.ecommercefashion.shop
FRONTEND_URL=https://ws.ecommercefashion.shop

# PostgreSQL 17
DB_NAME=fashionstore
DB_USER=fashion_app
DB_PASSWORD=CAMBIA_ESTA_CLAVE_FUERTE
DB_HOST=127.0.0.1
DB_PORT=5432

# Celery / Redis
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0

# Stripe (test o live)
STRIPE_SECRET_KEY=sk_...
STRIPE_PUBLISHABLE_KEY=pk_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Email (opcional)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=noreply@ecommercefashion.shop

# AR
AR_AUTO_CUTOUT=True
AR_REMBG_MODEL=u2net
```

Genera `SECRET_KEY`:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'
```

### Ajustes recomendados en `config/settings/prod.py`

Asegúrate de tener (además de lo ya existente):

```python
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])
```

Sin `SECURE_PROXY_SSL_HEADER`, con Nginx delante, `SECURE_SSL_REDIRECT` puede provocar bucles de redirección.

---

## 6. Migraciones y estáticos

```bash
cd /srv/fashionstore/backend
export DJANGO_SETTINGS_MODULE=config.settings.prod

sudo -u fashion env DJANGO_SETTINGS_MODULE=config.settings.prod \
  .venv/bin/python manage.py migrate

sudo -u fashion env DJANGO_SETTINGS_MODULE=config.settings.prod \
  .venv/bin/python manage.py collectstatic --noinput

sudo -u fashion env DJANGO_SETTINGS_MODULE=config.settings.prod \
  .venv/bin/python manage.py createsuperuser

# Datos demo (opcional)
sudo -u fashion env DJANGO_SETTINGS_MODULE=config.settings.prod \
  .venv/bin/python manage.py seed_demo

# Chequeo de despliegue
sudo -u fashion env DJANGO_SETTINGS_MODULE=config.settings.prod \
  .venv/bin/python manage.py check --deploy
```

---

## 7. systemd — Gunicorn + Celery

### 7.1 API — `/etc/systemd/system/fashionstore.service`

```ini
[Unit]
Description=FashionStore API (Gunicorn)
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
User=fashion
Group=fashion
WorkingDirectory=/srv/fashionstore/backend
EnvironmentFile=/srv/fashionstore/backend/.env
Environment=DJANGO_SETTINGS_MODULE=config.settings.prod
RuntimeDirectory=fashionstore
ExecStart=/srv/fashionstore/backend/.venv/bin/gunicorn config.wsgi:application \
  --workers 3 \
  --bind unix:/run/fashionstore/gunicorn.sock \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 7.2 Worker — `/etc/systemd/system/fashionstore-worker.service`

```ini
[Unit]
Description=FashionStore Celery Worker
After=network.target redis-server.service postgresql.service

[Service]
User=fashion
Group=fashion
WorkingDirectory=/srv/fashionstore/backend
EnvironmentFile=/srv/fashionstore/backend/.env
Environment=DJANGO_SETTINGS_MODULE=config.settings.prod
ExecStart=/srv/fashionstore/backend/.venv/bin/celery -A config worker -l info --concurrency=2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 7.3 Beat — `/etc/systemd/system/fashionstore-beat.service`

```ini
[Unit]
Description=FashionStore Celery Beat
After=network.target redis-server.service

[Service]
User=fashion
Group=fashion
WorkingDirectory=/srv/fashionstore/backend
EnvironmentFile=/srv/fashionstore/backend/.env
Environment=DJANGO_SETTINGS_MODULE=config.settings.prod
ExecStart=/srv/fashionstore/backend/.venv/bin/celery -A config beat -l info
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Activar:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now fashionstore fashionstore-worker fashionstore-beat
sudo systemctl status fashionstore fashionstore-worker fashionstore-beat
```

Logs:

```bash
journalctl -u fashionstore -f
journalctl -u fashionstore-worker -f
```

---

## 8. Nginx + TLS (Let's Encrypt)

### 8.1 Sitio HTTP temporal (para Certbot)

`/etc/nginx/sites-available/fashionstore`:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name ws.ecommercefashion.shop;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}
```

```bash
sudo mkdir -p /var/www/certbot
sudo ln -sf /etc/nginx/sites-available/fashionstore /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### 8.2 Certificado

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d ws.ecommercefashion.shop
```

### 8.3 Configuración HTTPS final

Reemplaza el archivo por:

```nginx
upstream fashionstore_app {
    server unix:/run/fashionstore/gunicorn.sock fail_timeout=0;
}

server {
    listen 80;
    listen [::]:80;
    server_name ws.ecommercefashion.shop;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ws.ecommercefashion.shop;

    ssl_certificate     /etc/letsencrypt/live/ws.ecommercefashion.shop/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ws.ecommercefashion.shop/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    client_max_body_size 20M;

    # API
    location /api/ {
        proxy_pass http://fashionstore_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    # Admin Django
    location /admin/ {
        proxy_pass http://fashionstore_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # OpenAPI / schema (si se expone en prod)
    location /api/schema/ {
        proxy_pass http://fashionstore_app;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /srv/fashionstore/backend/staticfiles/;
        expires 30d;
        access_log off;
    }

    location /media/ {
        alias /srv/fashionstore/backend/media/;
        expires 7d;
    }
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## 9. Stripe webhook

En el dashboard de Stripe → Webhooks → endpoint:

```
https://ws.ecommercefashion.shop/api/v1/payments/webhook/stripe/
```

Copia el `whsec_...` a `STRIPE_WEBHOOK_SECRET` en `.env` y reinicia:

```bash
sudo systemctl restart fashionstore
```

---

## 10. Verificación

```bash
curl -I https://ws.ecommercefashion.shop/api/v1/
curl -I https://ws.ecommercefashion.shop/admin/
```

Clientes:

| Cliente | Base URL |
|---------|----------|
| Angular / móvil | `https://ws.ecommercefashion.shop/api/v1/` |
| Admin | `https://ws.ecommercefashion.shop/admin/` |
| Media | `https://ws.ecommercefashion.shop/media/...` |

---

## 11. Actualización (deploy recurrente)

```bash
cd /srv/fashionstore/backend
sudo -u fashion git pull
sudo -u fashion .venv/bin/pip install -r requirements/prod.txt
# si usas AR:
# sudo -u fashion .venv/bin/pip install -r requirements/ar.txt
sudo -u fashion env DJANGO_SETTINGS_MODULE=config.settings.prod \
  .venv/bin/python manage.py migrate
sudo -u fashion env DJANGO_SETTINGS_MODULE=config.settings.prod \
  .venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart fashionstore fashionstore-worker fashionstore-beat
```

Script opcional `deploy.sh` en el servidor con esos mismos pasos.

---

## 12. Respaldos

Cron diario (como root):

```bash
sudo mkdir -p /var/backups/fashionstore
sudo crontab -e
```

```cron
0 3 * * * pg_dump -h 127.0.0.1 -U fashion_app fashionstore | gzip > /var/backups/fashionstore/db-$(date +\%F).sql.gz
0 3 * * * rsync -a /srv/fashionstore/backend/media/ /var/backups/fashionstore/media/
# Rotación: borrar dumps > 7 días
0 4 * * * find /var/backups/fashionstore -name 'db-*.sql.gz' -mtime +7 -delete
```

Guarda la contraseña de `fashion_app` en `~/.pgpass` del usuario que ejecuta el dump (`chmod 600`).

---

## 13. Checklist rápido

- [ ] DNS `ws.ecommercefashion.shop` → IP del VPS
- [ ] PostgreSQL 17 + extensiones `pg_trgm` y `vector`
- [ ] Redis activo solo en localhost
- [ ] `.env` con `DEBUG=False`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`
- [ ] `migrate` + `collectstatic` + superusuario
- [ ] systemd: API, worker, beat
- [ ] Nginx + Certbot HTTPS
- [ ] `SECURE_PROXY_SSL_HEADER` en prod
- [ ] Webhook Stripe apuntando al dominio
- [ ] `manage.py check --deploy` sin warnings críticos
- [ ] Backup `pg_dump` + `media/`

---

*Dominio de producción del API: `https://ws.ecommercefashion.shop`.*
