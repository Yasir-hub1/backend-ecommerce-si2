# FashionStore Backend - Plataforma E-Commerce Multi-Sucursal

Backend Django para plataforma de e-commerce de ropa con sucursales múltiples, probador virtual AR, y sistema de reservas.

## Estado Actual del Proyecto

### ✅ Completado

#### 1. Configuración del Proyecto
- ✅ Django 5.1 + Django REST Framework
- ✅ Settings organizados (base/dev/prod) con django-environ
- ✅ Celery configurado para tareas asíncronas
- ✅ JWT authentication con SimpleJWT
- ✅ CORS configurado
- ✅ OpenAPI/Swagger con drf-spectacular
- ✅ Estructura de 14 apps Django

#### 2. Modelos Implementados (100%)

**Core & Auth:**
- ✅ `User` - Usuario personalizado con roles (CUSTOMER, ADMIN, BRANCH_MANAGER, CASHIER, SUPPLIER)
- ✅ `CustomerProfile` - Perfil extendido de clientes
- ✅ `EmployeeProfile` - Perfil de empleados vinculado a sucursal

**Geografía:**
- ✅ `City` - Ciudades
- ✅ `Branch` - Sucursales con horarios y capacidad de probadores

**Catálogo:**
- ✅ `Category` - Categorías jerárquicas
- ✅ `Brand` - Marcas
- ✅ `SizeGroup` & `Size` - Sistema de tallas agrupado
- ✅ `Color` - Colores con código hex
- ✅ `Season` & `Collection` - Temporadas y colecciones
- ✅ `Product` - Productos maestros
- ✅ `ProductVariant` - Variantes (Product × Size × Color) = SKU
- ✅ `ProductImage` - Imágenes de productos
- ✅ `ARAsset` - Assets para probador virtual

**Proveedores:**
- ✅ `Supplier` - Proveedores
- ✅ `PurchaseReceipt` & `PurchaseReceiptItem` - Recepción de mercadería

**Inventario:**
- ✅ `BranchStock` - Stock por sucursal (caché transaccional)
- ✅ `InventoryMovement` - Libro mayor append-only (fuente de verdad)
- ✅ Restricciones de integridad: `on_hand >= 0`, `reserved >= 0`, `reserved <= on_hand`

**Reservas:**
- ✅ `Reservation` & `ReservationItem` - Sistema de reservas para probador
- ✅ Estados: PENDING → PREPARING → READY → IN_FITTING → COMPLETED

**Órdenes:**
- ✅ `Cart` & `CartItem` - Carrito de compras
- ✅ `Order` & `OrderItem` - Órdenes unificadas (WEB, MOBILE, POS)
- ✅ Decisión crítica: UN SOLO modelo Order para todos los canales

**Pagos:**
- ✅ `Payment` - Pagos con soporte multi-método
- ✅ `StripeWebhookEvent` - Log de webhooks para idempotencia
- ✅ `Receipt` - Comprobantes de venta

**Complementarios:**
- ✅ `Promotion` - Promociones y descuentos
- ✅ `Notification` - Notificaciones a usuarios y sucursales
- ✅ `ReportRequest` - Solicitudes de reportes IA
- ✅ `BrowsingEvent` - Eventos de navegación para recomendaciones
- ✅ `ProductEmbedding` - Embeddings para búsqueda por similitud
- ✅ `ChatSession` & `ChatMessage` - Chatbot

#### 3. Servicios Transaccionales

**Inventario (CRÍTICO):**
- ✅ `apply_movements()` - Función atómica para modificar inventario
  - ✅ Bloqueo determinista (`select_for_update` con orden fijo)
  - ✅ Prevención de deadlocks
  - ✅ Validación de invariantes
  - ✅ Todo o nada (transaccional)
- ✅ `check_availability()` - Verificar disponibilidad
- ✅ `get_stock_levels()` - Consultar niveles de stock
- ✅ `get_total_stock()` - Stock consolidado por variante

#### 4. Migraciones
- ✅ Migraciones iniciales creadas para todas las apps
- ✅ Índices optimizados para consultas frecuentes
- ✅ Restricciones de integridad en base de datos

**Reservas:**
- ✅ `reservations/services.py`
  - ✅ `create_reservation()` - Crear reserva con validación de stock
  - ✅ `transition_reservation()` - Cambiar estado de reserva con máquina de estados
  - ✅ `cancel_reservation()` - Cancelar reserva y liberar stock
  - ✅ `expire_due_reservations()` - Tarea Celery para expirar reservas

**Órdenes:**
- ✅ `orders/services.py`
  - ✅ `checkout_from_cart()` - Convertir carrito a orden (PENDING_PAYMENT, sin descontar stock)
  - ✅ `mark_order_as_paid()` - Marcar orden como pagada y descontar stock (llamado desde webhook)
  - ✅ `cancel_order()` - Cancelar orden pendiente
  - ✅ `refund_order()` - Procesar reembolso y devolver stock
  - ✅ `create_pos_sale()` - Venta POS (ya pagada, descuenta inmediatamente)

**Pagos:**
- ✅ `payments/services.py`
  - ✅ `create_stripe_payment_intent()` - Crear intención de pago en Stripe
  - ✅ `handle_stripe_webhook()` - Procesar webhooks con idempotencia
  - ✅ `process_stripe_refund()` - Procesar reembolsos
  - ✅ `generate_receipt()` - Generar comprobante PDF con WeasyPrint

**Proveedores:**
- ✅ `suppliers/services.py`
  - ✅ `confirm_receipt()` - Confirmar recepción de mercadería
  - ✅ `cancel_receipt()` - Cancelar recibo borrador

#### 4. API REST (Endpoints DRF)

**Autenticación:**
- ✅ `POST /api/v1/auth/login/` - Login JWT con claims custom (role, branch_id)
- ✅ `POST /api/v1/auth/refresh/` - Refresh token
- ✅ `POST /api/v1/auth/register/` - Registro de clientes
- ✅ `GET/POST /api/v1/users/` - Gestión de usuarios (admin)
- ✅ `GET /api/v1/users/me/` - Perfil del usuario actual
- ✅ `POST /api/v1/users/change_password/` - Cambiar contraseña
- ✅ `GET/POST /api/v1/customers/` - Perfiles de clientes
- ✅ `GET /api/v1/customers/me/` - Mi perfil de cliente
- ✅ `GET/POST /api/v1/employees/` - Perfiles de empleados
- ✅ `POST /api/v1/employees/create/` - Crear empleado (admin)

**Geografía:**
- ✅ `GET/POST /api/v1/cities/` - Ciudades (public read, admin write)
- ✅ `GET/POST /api/v1/branches/` - Sucursales (public read, admin write)

**Catálogo:**
- ✅ `GET/POST /api/v1/categories/` - Categorías
- ✅ `GET/POST /api/v1/brands/` - Marcas
- ✅ `GET/POST /api/v1/size-groups/` - Grupos de tallas
- ✅ `GET/POST /api/v1/sizes/` - Tallas
- ✅ `GET/POST /api/v1/colors/` - Colores
- ✅ `GET/POST /api/v1/seasons/` - Temporadas
- ✅ `GET/POST /api/v1/collections/` - Colecciones
- ✅ `GET/POST /api/v1/products/` - Productos con filtros
  - ✅ Filtros: category, brand, collection, gender, price range, branch
  - ✅ Búsqueda: name, description, material
  - ✅ Ordenamiento: created_at, price, name
- ✅ `GET /api/v1/products/{id}/availability/` - Disponibilidad por sucursal
- ✅ `GET/POST /api/v1/variants/` - Variantes de productos
- ✅ `GET/POST /api/v1/ar-assets/` - Assets de realidad aumentada

**Carrito:**
- ✅ `GET /api/v1/cart/` - Ver carrito actual
- ✅ `POST /api/v1/cart/add_item/` - Agregar item al carrito
- ✅ `PATCH /api/v1/cart/items/{id}/` - Actualizar cantidad
- ✅ `DELETE /api/v1/cart/items/{id}/` - Eliminar item
- ✅ `DELETE /api/v1/cart/clear/` - Vaciar carrito
- ✅ `POST /api/v1/cart/checkout/` - Convertir carrito a orden

**Órdenes:**
- ✅ `GET /api/v1/orders/` - Listar órdenes (filtradas por rol)
- ✅ `GET /api/v1/orders/{id}/` - Detalle de orden
- ✅ `POST /api/v1/orders/{id}/cancel/` - Cancelar orden
- ✅ `POST /api/v1/orders/{id}/refund/` - Reembolsar orden (admin/manager)
- ✅ `POST /api/v1/pos/sales/` - Crear venta POS (branch staff)

**Reservas:**
- ✅ `GET /api/v1/reservations/` - Listar reservas (filtradas por rol)
- ✅ `POST /api/v1/reservations/` - Crear reserva (customers)
- ✅ `GET /api/v1/reservations/{id}/` - Detalle de reserva
- ✅ `GET /api/v1/reservations/{code}/` - Detalle por código (ej: RSV-XXXXX)
- ✅ `POST /api/v1/reservations/{id}/transition/` - Cambiar estado (branch staff)
- ✅ `POST /api/v1/reservations/{id}/cancel/` - Cancelar reserva
- ✅ `GET /api/v1/reservations/my_reservations/` - Mis reservas (customer)
- ✅ `GET /api/v1/reservations/upcoming/` - Próximas reservas (branch staff)

**Pagos:**
- ✅ `POST /api/v1/payment-intent/` - Crear payment intent de Stripe
- ✅ `POST /api/v1/webhook/stripe/` - Webhook de Stripe (CRÍTICO, public, idempotente)
- ✅ `GET /api/v1/payment-intent/{id}/status/` - Estado del payment intent

**OpenAPI:**
- ✅ `GET /api/schema/` - Schema OpenAPI JSON
- ✅ `GET /api/schema/swagger/` - Swagger UI
- ✅ `GET /api/schema/redoc/` - ReDoc UI

### 📋 Por Implementar (Orden de Prioridad)

#### 1. Django Admin (Crítico para testing)
- ⏳ Configurar `admin.py` para todos los modelos
  - Acciones personalizadas (confirmar recibo, cambiar estado de reserva)
  - Filtros y búsquedas optimizadas
  - Inline para items de órdenes y reservas

#### 2. Datos de Demostración
- ⏳ Management command `python manage.py seed_demo`
  - 3 ciudades, 5 sucursales
  - 2 temporadas, 4 colecciones
  - ~40 productos con variantes
  - Stock distribuido entre sucursales
  - 5 usuarios (1 por rol)
  - Reservas y ventas históricas para dashboards

#### 3. Tests Críticos
- ⏳ `inventory/tests.py`
  - Test de concurrencia: dos reservas de la última unidad
  - Test transaccional: reserva parcialmente imposible (all-or-nothing)
  - Test de reconciliación de stock
- ⏳ `reservations/tests.py`
  - Test de expiración automática
  - Test de venta desde reserva
- ⏳ `payments/tests.py`
  - Test de webhook duplicado (idempotencia)
  - Test de monto manipulado
- ⏳ `core/tests.py`
  - Test de aislamiento por sucursal (404 no 403)

#### 4. APIs Secundarias
- ⏳ Inventory management endpoints (admin)
- ⏳ Reports endpoints  (dashboards)
- ⏳ AI endpoints (recomendaciones, chat)

#### 5. Tareas Celery
- ⏳ Configurar celery beat
- ⏳ Task: `expire_due_reservations` (cada 10 min)
- ⏳ Task: `low_stock_alerts` (diaria)
- ⏳ Task: `refresh_dashboard_cache` (cada 15 min)

#### 6. Documentación
- ⏳ Guía de instalación completa
- ⏳ Ejemplos de uso de API (curl/httpie)
- ⏳ Diagrams UML (casos de uso, secuencia, clases, estados)

### Fuera de Alcance (No implementar)
- ❌ Delivery y ruteo
- ❌ Multi-moneda
- ❌ Facturación fiscal SIN/SIAT
- ❌ Devoluciones parciales
- ❌ Transferencias entre sucursales con aprobación
- ❌ Programa de fidelización
- ❌ Reseñas de producto
- ❌ Notificaciones push nativas
- ❌ Pruebas de carga

## Reglas Anti-Redundancia Implementadas

✅ **La variante es la unidad de inventario** - No hay stock, tallas ni colores como texto
✅ **`available` no se almacena** - Es `on_hand - reserved` (calculado)
✅ **La temporada viene de collection** - `Product → Collection → Season`
✅ **Un solo Order para todos los canales** - WEB, MOBILE, POS usan el mismo modelo
✅ **Precio congelado en OrderItem** - `unit_price` se guarda, `line_total` se calcula
✅ **Stock es caché del ledger** - `InventoryMovement` es la verdad, `BranchStock` es derivado

## Stack Tecnológico

- **Framework**: Django 5.1 + Django REST Framework 3.15
- **Base de Datos**: PostgreSQL 16 (con extensiones pg_trgm y pgvector)
- **Autenticación**: JWT con djangorestframework-simplejwt
- **Tareas Asíncronas**: Celery + Redis
- **Pagos**: Stripe (modo test)
- **PDF**: WeasyPrint
- **Hashing**: Argon2

## Instalación

### 1. Requisitos Previos
```bash
# Python 3.11+
python --version

# PostgreSQL 16
psql --version

# Redis
redis-cli ping
```

### 2. Configurar Entorno

```bash
# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements/dev.txt
```

### 3. Configurar Base de Datos

```bash
# Crear base de datos PostgreSQL
createdb fashionstore

# O con psql:
psql -U postgres
CREATE DATABASE fashionstore;
\q
```

### 4. Variables de Entorno

Copiar `.env.example` a `.env` y configurar:

```bash
cp .env.example .env
# Editar .env con tus credenciales
```

### 5. Ejecutar Migraciones

```bash
python manage.py migrate
```

### 6. Crear Superusuario

```bash
python manage.py createsuperuser
```

### 7. Cargar Datos de Prueba (Cuando esté implementado)

```bash
python manage.py seed_demo
```

### 8. Ejecutar Servidor

```bash
# Servidor de desarrollo
python manage.py runserver

# Celery worker (en otra terminal)
celery -A config worker -l info

# Celery beat (tareas programadas)
celery -A config beat -l info
```

## Estructura del Proyecto

```
backend/
├── manage.py
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   └── prod.txt
├── config/
│   ├── settings/
│   │   ├── base.py      # Settings base
│   │   ├── dev.py       # Settings desarrollo
│   │   └── prod.py      # Settings producción
│   ├── urls.py
│   ├── celery.py
│   └── __init__.py
├── core/                 # Clases base, permisos, excepciones
├── accounts/             # User, perfiles, auth
├── branches/             # City, Branch
├── catalog/              # Catálogo completo
├── suppliers/            # Proveedores y recepciones
├── inventory/            # Stock y movimientos
├── reservations/         # Reservas
├── orders/               # Carrito y órdenes
├── payments/             # Pagos y Stripe
├── pos/                  # Punto de venta
├── promotions/           # Promociones
├── reports/              # Reportes
├── ai/                   # IA y analytics
└── notifications/        # Notificaciones
```

## Endpoints API (Próximos)

```
/api/v1/
├── auth/
│   ├── register/
│   ├── login/
│   └── refresh/
├── products/
├── cart/
├── reservations/
├── orders/
├── payments/
├── pos/
└── admin/
```

## Arquitectura por Capas

```
View (DRF ViewSet)
    ↓
Serializer (validación de forma)
    ↓
Service (lógica de negocio + transacción)
    ↓
Model/QuerySet
```

**Regla de oro**: Las vistas NO contienen lógica de negocio. Todo va en `services.py`.

## Testing

```bash
# Ejecutar todos los tests
pytest

# Con cobertura
pytest --cov=. --cov-report=html

# Tests específicos
pytest inventory/tests/test_services.py
```

## Próximos Pasos Recomendados

1. **✅ COMPLETADO**: Servicios transaccionales (inventory, reservations, orders, payments)
2. **✅ COMPLETADO**: API REST crítica (auth, catalog, cart, orders, reservations, payments)
3. **⏳ SIGUIENTE**: Configurar Django Admin (crítico para testing manual)
4. **⏳ SIGUIENTE**: Implementar comando `seed_demo` (datos de demostración)
5. **Opcional**: Tests críticos (concurrencia de inventario, webhooks)
6. **Opcional**: APIs secundarias (inventory admin, reports, AI)

## Documentación de Referencia

Ver archivos en `/Users/dev/Documents/si2/examen1-ecommerce/files/`:
- `00-requisitos-trazabilidad.md` - Matriz RF ↔ Módulo
- `01-modelo-datos.md` - Modelo de datos completo
- `02-backend-django.md` - Arquitectura backend
- `03-pagos-stripe.md` - Integración Stripe
- `07-api-contrato.md` - Diseño de API

## Contacto y Soporte

Este proyecto es parte del examen de Sistemas de Información 2 (SI2) - E-Commerce Multi-Sucursal.

---

**Estado**: Backend 90% implementado

- ✅ Modelos y migraciones (100%)
- ✅ Servicios transaccionales (100%)
- ✅ API REST crítica (90% - faltan inventory/reports/ai)
- ⏳ Django Admin (0%)
- ⏳ Tests (0%)
- ⏳ Datos demo (0%)
