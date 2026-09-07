# Probador virtual AR — librerías y ajustes por capa

Alcance de este documento: qué instalar y qué configurar en **backend (Django)**, **web (Angular)**, **móvil (React Native)** y **worker GPU** para el flujo "subo una imagen desde Angular → el usuario se prueba el producto desde la app móvil".

Antes de instalar nada, lee la sección **Decisión de arquitectura**. Instalar las librerías equivocadas aquí cuesta una semana.

---

## 0. Decisión de arquitectura (léela primero)

Hay **dos productos distintos** bajo el nombre "probador virtual", y necesitan pilas de librerías diferentes:

| | Vía A — Overlay 2D con pose | Vía B — Try-on generativo | Vía C — 3D/AR real |
|---|---|---|---|
| Qué hace | Superpone un PNG de la prenda sobre el cuerpo en la cámara | Genera una foto del usuario vistiendo la prenda | Coloca un modelo 3D en el mundo real |
| Tiempo real | Sí (30–60 fps) | No (~35 s por imagen) | Sí |
| Necesita GPU | No | Sí (≥8 GB VRAM) | Solo para generar el modelo, una vez |
| Sirve para ropa | Sí (prendas superiores) | Sí (la mejor calidad) | **No** — genera mallas rígidas, no prendas |
| Sirve para accesorios | Regular | Regular | Sí (gafas, zapatos, bolsos) |

**Plan recomendado**: A como base (RF13 cubierto sin GPU), B como diferenciador si consigues GPU, C solo para accesorios y con GLB pre-generado offline.

**Lo que NO vas a hacer**: generar un 3D al vuelo desde la imagen subida en Angular y que eso sea una prenda ponible. Ese flujo, tal como lo pediste literalmente, no existe hoy en producción. Ver `#riesgos`.

---

## 1. Backend — Django

### Dependencias

```bash
# Núcleo (ya deberías tenerlo)
pip install "Django~=5.1" djangorestframework django-cors-headers \
            psycopg[binary] python-decouple djangorestframework-simplejwt

# Procesamiento de imágenes del asset AR
pip install Pillow                 # validación, resize, verificación de canal alfa
pip install rembg[cpu]             # recorte automático de fondo del PNG de la prenda
pip install numpy opencv-python-headless

# Cola asíncrona (obligatoria si haces la Vía B o C)
pip install celery redis django-celery-results

# Solo si haces la Vía C (3D para accesorios) — post-proceso de malla
pip install trimesh pygltflib xatlas
```

**Lo que NO instalas en el servidor web**: `torch`, `diffusers`, `pymeshlab`, `pytorch3d`, `open3d`. Eso vive en el worker GPU, que es otra máquina. Meter PyTorch en el VPS de Django infla la imagen ~3 GB y no te sirve de nada sin CUDA.

`rembg[cpu]` sí puede vivir en el backend: usa ONNX Runtime en CPU, tarda 1–3 s por imagen y solo corre cuando el admin sube un producto. Aun así, encólalo en Celery, no lo hagas en el request.

### Modelo (ya definido en el proyecto)

`ARAsset`: `product` (FK), `color` (FK null), `kind` (`OVERLAY_2D` | `MODEL_3D`), `file`, `anchor_config` (JSON), `is_active`. Único `(product, color, kind)`.

Añade para el pipeline asíncrono:

```python
class ARAsset(models.Model):
    ...
    status = models.CharField(max_length=12, choices=[
        ("PENDING", "Pendiente"),
        ("PROCESSING", "Procesando"),
        ("READY", "Listo"),
        ("FAILED", "Falló"),
    ], default="PENDING")
    source_image = models.ImageField(upload_to="ar/source/")   # lo que subió el admin
    file = models.FileField(upload_to="ar/assets/", null=True) # PNG recortado o GLB
    error_message = models.TextField(blank=True)
```

**Por qué `status` y no solo `file`**: el procesamiento tarda segundos o minutos. Sin estado, Angular no sabe si el asset está fallado o todavía en cola, y termina haciendo polling ciego.

### `anchor_config` — la pieza que evita recompilar la app

```json
{
  "widthFactor": 1.85,
  "offsetY": -0.08,
  "assetWidth": 1024,
  "assetHeight": 1280,
  "sizeScale": { "XS": 0.90, "S": 0.95, "M": 1.00, "L": 1.06, "XL": 1.12 }
}
```

Calibrar una prenda mal ajustada debe ser editar este JSON en el admin, nunca tocar código de React Native. Si te descubres hardcodeando factores en el móvil, vuelve aquí.

### Ajustes de `settings.py`

```python
# Archivos servidos desde disco local (sin S3, según la restricción del proyecto)
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"

# Límite de subida: un PNG de prenda no debería pasar de 8 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 8 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 8 * 1024 * 1024

# Celery
CELERY_BROKER_URL = "redis://localhost:6379/0"
CELERY_RESULT_BACKEND = "django-db"
CELERY_TASK_ACKS_LATE = True            # no perder el job si el worker muere
CELERY_WORKER_PREFETCH_MULTIPLIER = 1   # crítico con GPU: un job por worker
CELERY_TASK_TIME_LIMIT = 600
```

En producción **nginx sirve `/media/`**, no Django. `django.views.static.serve` es solo para desarrollo y es lento para archivos binarios de varios MB.

### Endpoints mínimos

```
POST   /api/v1/products/{id}/ar-assets/     → 202 + {id, status: "PENDING"}
GET    /api/v1/ar-assets/{id}/              → {status, file_url, anchor_config}
PATCH  /api/v1/ar-assets/{id}/              → editar anchor_config (calibración)
GET    /api/v1/products/{id}/ar-asset/?color={id}&kind=OVERLAY_2D
```

El `POST` **nunca** procesa en línea. Valida, guarda `source_image`, encola, devuelve 202.

### Validación en el serializer (no la saltes)

```python
def validate_source_image(self, image):
    img = Image.open(image)
    if img.width < 512:
        raise serializers.ValidationError("Mínimo 512 px de ancho.")
    if img.width > 4096 or img.height > 4096:
        raise serializers.ValidationError("Máximo 4096 px por lado.")
    return image
```

El canal alfa se verifica **después** de `rembg`, no antes: el admin va a subir JPGs de catálogo con fondo blanco y eso es normal.

---

## 2. Worker GPU (solo Vía B o C)

Máquina separada. Puede ser un worker Celery escuchando una cola dedicada, o un microservicio FastAPI que Django llama por HTTP. Prefiere el worker Celery: una pieza menos que autenticar y monitorear.

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install diffusers transformers accelerate safetensors
pip install celery redis Pillow numpy opencv-python-headless

# Vía B — try-on por difusión
# CatVTON: <8 GB VRAM a 1024x768, ~35 s por imagen. Clonar el repo oficial.

# Vía C — 3D para accesorios
pip install trimesh pymeshlab xatlas
# TripoSR (MIT) o TRELLIS (MIT). Evita Hunyuan3D si el proyecto toca UE/UK/Corea.
```

Arranque del worker:

```bash
celery -A config worker -Q gpu -c 1 --loglevel=info
```

`-c 1` no es negociable con una sola GPU. Dos procesos compartiendo VRAM producen OOM intermitentes que vas a perseguir durante días.

**Revisa las licencias antes de escribir código**: SF3D y SPAR3D son gratis solo bajo 1 M USD/año de ingresos; la licencia de Hunyuan3D excluye la Unión Europea, Reino Unido y Corea del Sur; SMPL/SMPL-X es exclusivamente no comercial. Para un proyecto académico da igual, para una defensa donde te pregunten "¿y esto se puede vender?" no.

---

## 3. Web — Angular

No necesitas casi nada nuevo. Angular solo sube la imagen y calibra.

```bash
npm i ngx-image-cropper       # recorte y encuadre antes de subir
npm i @google/model-viewer    # solo si haces Vía C: previsualizar el GLB en el admin
```

`@google/model-viewer` es un web component, así que registra `CUSTOM_ELEMENTS_SCHEMA` en el componente standalone que lo use:

```ts
@Component({
  standalone: true,
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  ...
})
```

Subida con progreso real:

```ts
this.http.post(url, formData, { reportProgress: true, observe: 'events' })
```

Y polling del estado con backoff, no cada segundo:

```ts
timer(0, 3000).pipe(
  switchMap(() => this.http.get<ARAsset>(`/api/v1/ar-assets/${id}/`)),
  takeWhile(a => a.status === 'PENDING' || a.status === 'PROCESSING', true)
)
```

**Lo que sí vale la pena construir**: una pantalla de calibración que muestre el PNG recortado sobre una silueta de referencia con sliders para `widthFactor` y `offsetY`, guardando en `anchor_config`. Sin esto, cada prenda mal ajustada es un ciclo de compilar la app, probar, corregir. Con esto son treinta segundos.

---

## 4. Móvil — React Native

**Expo development build obligatorio.** Expo Go no incluye los módulos nativos de cámara con frame processors. Si intentas esto en Expo Go vas a perder medio día antes de entenderlo.

### Vía A — overlay 2D (la base)

```bash
npx expo install react-native-vision-camera react-native-worklets-core
npx expo install @shopify/react-native-skia react-native-reanimated
npm i react-native-fast-tflite
npx expo install expo-image expo-media-library expo-file-system
npm i @tanstack/react-query zustand axios
```

### Vía C — visualizar GLB de accesorios

```bash
npm i react-native-filament            # render 3D, Metal en iOS, hilo separado
# o
npm i @reactvision/react-viro          # AR real con ARKit/ARCore, MIT
# o, lo más rápido para el MVP:
npx expo install react-native-webview  # + <model-viewer> dentro
```

Criterio: `react-native-webview` + `<model-viewer>` es una tarde de trabajo y lanza AR nativo automáticamente (Scene Viewer en Android, Quick Look en iOS). `ViroReact` es AR de verdad con detección de planos y cuesta días. Para una demo académica, empieza por el WebView.

Si vas por Quick Look en iOS necesitas **USDZ, no GLB**. La conversión se hace **offline en el backend** con `usd_from_gltf` de Google, y guardas ambos archivos. Convertir en el dispositivo no es viable.

### `app.json`

```json
{
  "expo": {
    "scheme": "fashionstore",
    "plugins": [
      ["react-native-vision-camera", {
        "cameraPermissionText": "FashionStore usa la cámara para el probador virtual.",
        "enableFrameProcessors": true
      }]
    ],
    "extra": { "apiUrl": "..." }
  }
}
```

`enableFrameProcessors: true` es el flag que la gente olvida; sin él el `useFrameProcessor` compila pero no ejecuta nada.

### `babel.config.js`

```js
plugins: [
  'react-native-worklets-core/plugin',
  'react-native-reanimated/plugin',  // SIEMPRE el último
]
```

El orden importa y el error que produce equivocarse es incomprensible.

### Ajustes de rendimiento que no son opcionales

- Detección de pose a **10–15 fps**, render a 60 fps interpolando entre detecciones. Correr el modelo en cada frame quema batería y baja el framerate sin mejorar nada: el cuerpo humano no se mueve tan rápido.
- **Suavizado exponencial (EMA)** sobre los keypoints. Sin esto la prenda tiembla y la demo se ve rota aunque la matemática sea correcta.
- **Modo galería como fallback**: si el modelo no carga o el dispositivo es lento, el usuario toma una foto y ajusta la prenda con gestos. El día de la defensa el dispositivo del tribunal puede ser cualquier cosa.
- Cachea el PNG del asset con `expo-file-system`, no lo descargues en cada apertura del producto.

### Verificación de versiones

```bash
npx expo install --check
```

Córrelo después de cada instalación. La incompatibilidad entre Reanimated, Vision Camera y la versión de Expo es la causa número uno de días perdidos en este stack, y el error nunca dice cuál de las tres es.

---

## 5. Infraestructura del servidor

```bash
sudo apt install redis-server postgresql-16 nginx
sudo systemctl enable --now redis-server
```

Systemd para Celery (sin Docker, según la restricción del proyecto):

```ini
# /etc/systemd/system/fashionstore-celery.service
[Service]
User=fashionstore
WorkingDirectory=/srv/fashionstore
ExecStart=/srv/fashionstore/.venv/bin/celery -A config worker -l info -c 2
Restart=always
```

nginx para los assets:

```nginx
location /media/ {
    alias /srv/fashionstore/media/;
    expires 30d;
    add_header Cache-Control "public, immutable";
}
```

---

## 6. Riesgos y trampas {#riesgos}

**El flujo literal que pediste no es realizable como lo formulaste.** "Subir una imagen y que se construya dinámicamente en AR para probarse la prenda en tiempo real" mezcla tres cosas incompatibles: generación 3D (necesita GPU y minutos), prendas deformables (problema de investigación abierto, requiere rigging y simulación de tela) y tiempo real (necesita que todo corra en el dispositivo). Lo honesto es entregar overlay 2D con pose tracking y decir en la defensa que es *body-tracked overlay*, la misma técnica de los probadores comerciales de prendas superiores.

**Otras trampas concretas:**

- Procesar la imagen dentro del request de Django bloquea el worker de Gunicorn. Con dos admins subiendo productos a la vez, la web se cae.
- `torchmcubes` en TripoSR compila a veces solo para CPU y desactiva la GPU **sin lanzar error**. Mide el tiempo de la primera inferencia para detectarlo.
- Servir GLB por `django.views.static.serve` en producción es lentísimo. nginx.
- Un GLB de más de 15 MB tarda demasiado en cargar en móvil. Decima la malla y limita texturas a 2048².
- Registrar `BrowsingEvent(event_type="AR_TRY")` en cada uso te da la métrica del informe ("X% de quienes usaron el probador reservaron") y alimenta el recomendador. Es una línea de código y vale más en la defensa que una función extra.

---

## 7. Orden de implementación

1. Modelo `ARAsset` + estados + endpoints + admin de calibración. Sin GPU, sin cámara. **Un día.**
2. Subida desde Angular + `rembg` en Celery + pantalla de calibración. **Dos días.**
3. Cámara + MoveNet + Skia en React Native, con modo galería desde el principio. **Tres o cuatro días.**
4. Cierre del círculo: desde el probador al carrito o a la reserva en sucursal. **Medio día.**
5. Opcional, si sobra tiempo y hay GPU: try-on por difusión o 3D de accesorios.

El paso 4 es el que convierte una demo bonita en una función de negocio, y es exactamente lo que evalúa el enunciado al pedir integración del probador con catálogo y disponibilidad. No lo dejes para el final.
