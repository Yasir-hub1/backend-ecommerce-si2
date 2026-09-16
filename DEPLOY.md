# Deploy — FashionStore Backend

Guía de despliegue del API Django en un VPS Linux (sin Docker), como **root**, apuntando a:

**https://ws.ecommercefashion.shop**

Ruta del proyecto en el servidor:

```
/var/www/ecommercefashion/backend
```

Stack: Python 3.12 · Django 5.1 · Gunicorn · Nginx · PostgreSQL **17** (+ `pg_trgm`, `pgvector`) · Redis · Celery.

VPS de referencia: Ubuntu 24.04, 1 vCPU, 2 GB RAM (ajusta workers de Gunicorn/Celery si subes recursos).

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

DNS: registro **A** de `ws.ecommercefashion.shop` → IP pública del VPS.

Todo se ejecuta como **root** (usuario del sistema `root`). No se crea un usuario de aplicación aparte.

---

## 1. Preparación del servidor

```bash
apt update && apt upgrade -y
timedatectl set-timezone America/La_Paz

apt install -y \
  curl ca-certificates gnupg lsb-release \
  python3.12 python3.12-venv python3-pip \
  redis-server nginx git build-essential \
  libpq-dev pkg-config \
  libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi-dev \
  libjpeg-dev zlib1g-dev libpng-dev
```

Firewall (solo SSH + HTTP/HTTPS):

```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
ufw status
```

---

## 2. PostgreSQL 17 (+ pgvector)

Ubuntu 24.04 trae PostgreSQL 16 por defecto. Para la **17** usa el repositorio oficial PGDG.

### 2.1 Repositorio PGDG

```bash
apt install -y curl ca-certificates
install -d /usr/share/postgresql-common/pgdg
curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
  --fail https://www.postgresql.org/media/keys/ACCC4CF8.asc

sh -c 'echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
  https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
  > /etc/apt/sources.list.d/pgdg.list'

apt update
```

### 2.2 Instalar servidor y extensiones

```bash
apt install -y \
  postgresql-17 \
  postgresql-client-17 \
  postgresql-contrib-17 \
  postgresql-17-pgvector

systemctl enable --now postgresql
psql --version   # debe mostrar 17.x
```

### 2.3 Usuario `postgres` (el por defecto) + base de datos

Solo se usa el rol **`postgres`**. Cambia su contraseña y crea la base:

```bash
sudo -u postgres psql
```

```sql
ALTER USER postgres WITH PASSWORD '12345678';
CREATE DATABASE fashionstore OWNER postgres;
\c fashionstore
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;
\q
```

### 2.4 Escuchar en localhost + auth por contraseña (TCP)

Edita `/etc/postgresql/17/main/postgresql.conf`:

```conf
listen_addresses = 'localhost'
```

En `/etc/postgresql/17/main/pg_hba.conf`, asegúrate de tener auth por contraseña para conexiones locales TCP (Django usa `127.0.0.1`):

```conf
# TYPE  DATABASE        USER            ADDRESS                 METHOD
local   all             postgres                                peer
host    all             postgres        127.0.0.1/32            scram-sha-256
host    all             postgres        ::1/128                 scram-sha-256
```

```bash
systemctl restart postgresql
```

Prueba (te pedirá la contraseña de `postgres`):

```bash
psql -h 127.0.0.1 -U postgres -d fashionstore -c '\dx'
# Debe listar pg_trgm y vector
```

---

## 3. Redis

```bash
systemctl enable --now redis-server
redis-cli ping   # PONG
```

Redis solo en `127.0.0.1:6379`. No abras el puerto al exterior.

---

## 4. Código y entorno Python

El código vive en `/var/www/ecommercefashion/backend` (ya como root):

```bash
cd /var/www/ecommercefashion/backend

# Si aún no está el código:
# mkdir -p /var/www/ecommercefashion
# git clone <URL_DEL_REPO> /var/www/ecommercefashion
# (o sube el backend a /var/www/ecommercefashion/backend)

python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements/prod.txt
# Pipeline AR (rembg / YOLO-pose):
.venv/bin/pip install -r requirements/ar.txt

mkdir -p logs media staticfiles
```

---

## 5. Variables de entorno (`.env`)

```bash
cd /var/www/ecommercefashion/backend
cp .env.example .env
chmod 600 .env
```

Contenido sugerido (`/var/www/ecommercefashion/backend/.env`):

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

# PostgreSQL 17 — usuario por defecto
DB_NAME=fashionstore
DB_USER=postgres
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

```python
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])
```

Sin `SECURE_PROXY_SSL_HEADER`, con Nginx delante, `SECURE_SSL_REDIRECT` puede provocar bucles de redirección.

---

## 6. Migraciones y estáticos

```bash
cd /var/www/ecommercefashion/backend
export DJANGO_SETTINGS_MODULE=config.settings.prod

.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py createsuperuser

# Datos demo (opcional)
.venv/bin/python manage.py seed_demo

# Chequeo de despliegue
.venv/bin/python manage.py check --deploy
```

---

## 7. systemd — Gunicorn + Celery (como root)

### 7.1 API — `/etc/systemd/system/fashionstore.service`

```ini
[Unit]
Description=FashionStore API (Gunicorn)
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
User=root
Group=root
WorkingDirectory=/var/www/ecommercefashion/backend
EnvironmentFile=/var/www/ecommercefashion/backend/.env
Environment=DJANGO_SETTINGS_MODULE=config.settings.prod
RuntimeDirectory=fashionstore
ExecStart=/var/www/ecommercefashion/backend/.venv/bin/gunicorn config.wsgi:application \
  --workers 2 \
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
User=root
Group=root
WorkingDirectory=/var/www/ecommercefashion/backend
EnvironmentFile=/var/www/ecommercefashion/backend/.env
Environment=DJANGO_SETTINGS_MODULE=config.settings.prod
ExecStart=/var/www/ecommercefashion/backend/.venv/bin/celery -A config worker -l info --concurrency=1
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
User=root
Group=root
WorkingDirectory=/var/www/ecommercefashion/backend
EnvironmentFile=/var/www/ecommercefashion/backend/.env
Environment=DJANGO_SETTINGS_MODULE=config.settings.prod
ExecStart=/var/www/ecommercefashion/backend/.venv/bin/celery -A config beat -l info
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Activar:

```bash
systemctl daemon-reload
systemctl enable --now fashionstore fashionstore-worker fashionstore-beat
systemctl status fashionstore fashionstore-worker fashionstore-beat
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
mkdir -p /var/www/certbot
ln -sf /etc/nginx/sites-available/ws.fashionstore /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```

### 8.2 Certificado

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d ws.ecommercefashion.shop
```

### 8.3 Configuración HTTPS final

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

    location /api/ {
        proxy_pass http://fashionstore_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    location /admin/ {
        proxy_pass http://fashionstore_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/schema/ {
        proxy_pass http://fashionstore_app;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /var/www/ecommercefashion/backend/staticfiles/;
        expires 30d;
        access_log off;
    }

    location /media/ {
        alias /var/www/ecommercefashion/backend/media/;
        expires 7d;
    }
}
```

```bash
nginx -t && systemctl reload nginx
```

---

## 9. Stripe webhook

Endpoint en Stripe:

```
https://ws.ecommercefashion.shop/api/v1/payments/webhook/stripe/
```

Copia el `whsec_...` a `STRIPE_WEBHOOK_SECRET` en `.env` y reinicia:

```bash
systemctl restart fashionstore
```

---

## 10. Verificación

```bash
curl -I https://ws.ecommercefashion.shop/api/v1/
curl -I https://ws.ecommercefashion.shop/admin/
```

| Cliente | Base URL |
|---------|----------|
| Angular / móvil | `https://ws.ecommercefashion.shop/api/v1/` |
| Admin | `https://ws.ecommercefashion.shop/admin/` |
| Media | `https://ws.ecommercefashion.shop/media/...` |

---

## 11. Actualización (deploy recurrente)

```bash
cd /var/www/ecommercefashion/backend
git pull
.venv/bin/pip install -r requirements/prod.txt
# .venv/bin/pip install -r requirements/ar.txt
export DJANGO_SETTINGS_MODULE=config.settings.prod
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
systemctl restart fashionstore fashionstore-worker fashionstore-beat
```

---

## 12. Respaldos

```bash
mkdir -p /var/backups/fashionstore
crontab -e
```

```cron
0 3 * * * PGPASSWORD='CAMBIA_ESTA_CLAVE_FUERTE' pg_dump -h 127.0.0.1 -U postgres fashionstore | gzip > /var/backups/fashionstore/db-$(date +\%F).sql.gz
0 3 * * * rsync -a /var/www/ecommercefashion/backend/media/ /var/backups/fashionstore/media/
0 4 * * * find /var/backups/fashionstore -name 'db-*.sql.gz' -mtime +7 -delete
```

Mejor: usa `~/.pgpass` (`chmod 600`) en lugar de poner la clave en el crontab.

---

## 13. Checklist rápido

- [ ] DNS `ws.ecommercefashion.shop` → IP del VPS
- [ ] Código en `/var/www/ecommercefashion/backend`
- [ ] PostgreSQL 17 + `pg_trgm` / `vector`
- [ ] Usuario DB `postgres` con contraseña nueva
- [ ] Redis solo en localhost
- [ ] `.env` con `DB_USER=postgres`, `DEBUG=False`, hosts del dominio
- [ ] `migrate` + `collectstatic` + superusuario Django
- [ ] systemd como `root`: API, worker, beat
- [ ] Nginx + Certbot HTTPS
- [ ] `SECURE_PROXY_SSL_HEADER` en prod
- [ ] Webhook Stripe
- [ ] Backup `pg_dump` + `media/`

---

*Dominio: `https://ws.ecommercefashion.shop` · Path: `/var/www/ecommercefashion/backend` · DB user: `postgres`.*
