# FashionStore — API CRUD Backoffice

Documentación de todos los endpoints REST para el panel administrativo (Angular) y consumo móvil/web.

**Base URL:** `/api/v1/`  
**Autenticación:** JWT Bearer (`Authorization: Bearer <token>`)  
**Paginación:** `?page=1&page_size=20` (máx. 100)

Documentación RBAC detallada: [`rbac-api.md`](./rbac-api.md)

---

## Mapa de requisitos del examen

| RF | Módulo | Endpoints |
|----|--------|-----------|
| RF01 | Registro cliente | `POST /auth/register/` |
| RF02 | Usuarios y roles | `/users/`, `/roles/`, `/permissions/` |
| RF03 | Ciudades y sucursales | `/cities/`, `/branches/` |
| RF04–05 | Catálogo | `/categories/`, `/products/`, `/variants/`, `/sizes/`, `/colors/` |
| RF06 | Proveedores | `/suppliers/`, `/purchase-receipts/` |
| RF07–08 | Consulta catálogo + stock | `/products/`, `/products/{id}/availability/` |
| RF21–22 | Inventario | `/stock/`, `/movements/` |
| RF23 | Temporadas y colecciones | `/seasons/`, `/collections/` |

---

## 1. Autenticación y usuarios (RF01, RF02)

### Auth

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| POST | `/auth/login/` | Login JWT (incluye `role`, `permissions`) | Público |
| POST | `/auth/refresh/` | Renovar token | Refresh token |
| POST | `/auth/register/` | Registro cliente | Público |
| GET | `/auth/me/permissions/` | Permisos del usuario logueado | JWT |

### Usuarios

| Método | Ruta | Permiso escritura | Descripción |
|--------|------|-------------------|-------------|
| GET | `/users/` | `accounts.users.view` | Listar usuarios |
| POST | `/users/` | `accounts.users.manage` | Crear usuario |
| GET | `/users/{id}/` | `accounts.users.view` | Detalle |
| PUT/PATCH | `/users/{id}/` | `accounts.users.manage` | Editar (incl. `role`) |
| DELETE | `/users/{id}/` | `accounts.users.manage` | Eliminar |
| GET | `/users/me/` | — | Perfil propio |
| POST | `/users/change_password/` | — | Cambiar contraseña |

**Filtros:** `?role=ADMIN&is_active=true&search=email`

### Empleados

| Método | Ruta | Permiso | Descripción |
|--------|------|---------|-------------|
| GET | `/employees/` | JWT | Listar perfiles empleado |
| GET | `/employees/me/` | JWT | Perfil empleado propio |
| POST | `/employees/create/` | `accounts.users.manage` | Crear empleado + perfil |

**Body crear empleado:**
```json
{
  "email": "cajero@fashionstore.com",
  "password": "SecurePass123!",
  "first_name": "Juan",
  "last_name": "Pérez",
  "role": "CASHIER",
  "position": "CASHIER",
  "branch": 1,
  "hire_date": "2026-08-01"
}
```

### Clientes

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/customers/` | Listar (admin) |
| GET | `/customers/me/` | Perfil cliente propio |
| PATCH | `/customers/{id}/` | Actualizar preferencias |

### RBAC (roles y permisos)

Ver [`rbac-api.md`](./rbac-api.md) — `/permissions/`, `/roles/`, acciones de asignación.

---

## 2. Sucursales (RF03)

### Ciudades

| Método | Ruta | Escritura | Descripción |
|--------|------|-----------|-------------|
| GET | `/cities/` | — | Listar ciudades activas |
| POST | `/cities/` | `branches.manage` | Crear ciudad |
| GET | `/cities/{id}/` | — | Detalle |
| PUT/PATCH | `/cities/{id}/` | `branches.manage` | Editar |
| DELETE | `/cities/{id}/` | `branches.manage` | Eliminar |

**Body:**
```json
{
  "name": "Santa Cruz de la Sierra",
  "department": "Santa Cruz",
  "is_active": true
}
```

### Sucursales

| Método | Ruta | Escritura | Descripción |
|--------|------|-----------|-------------|
| GET | `/branches/` | — | Listar sucursales |
| POST | `/branches/` | `branches.manage` | Crear sucursal |
| GET | `/branches/{id}/` | — | Detalle con horarios y probadores |
| PUT/PATCH | `/branches/{id}/` | `branches.manage` | Editar |
| DELETE | `/branches/{id}/` | `branches.manage` | Eliminar |

**Body:**
```json
{
  "code": "SCZ-01",
  "name": "FashionStore Equipetrol",
  "city": 1,
  "address": "Av. San Martín 123",
  "phone": "+59170000001",
  "opens_at": "09:00:00",
  "closes_at": "21:00:00",
  "fitting_rooms": 4,
  "is_active": true
}
```

**Filtros:** `?city=1&search=Equipetrol`

---

## 3. Catálogo (RF04, RF05, RF07, RF23)

Lectura pública/autenticada. Escritura requiere `catalog.products.manage`.

### Categorías

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | `/categories/` | CRUD jerárquico de categorías |
| GET/PUT/PATCH/DELETE | `/categories/{id}/` | Detalle / editar |

**Body:** `{ "name", "slug", "parent", "size_group", "display_order", "is_active" }`

### Marcas

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | `/brands/` | CRUD marcas |
| GET/PUT/PATCH/DELETE | `/brands/{id}/` | |

### Tallas (grupos y tallas)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | `/size-groups/` | Grupos: ALPHA_TOP, WAIST_NUM, SHOE_EU… |
| GET/POST | `/sizes/` | Tallas por grupo (`?group=1`) |

**Flujo FashionStore:** la categoría referencia un `size_group`; las variantes combinan producto + talla + color.

### Colores

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | `/colors/` | CRUD colores |
| GET/PUT/PATCH/DELETE | `/colors/{id}/` | `{ "name", "slug", "hex_code": "#FF5733" }` |

### Temporadas (RF23)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | `/seasons/` | PV26, OI26, escolar, promos… |
| GET/PUT/PATCH/DELETE | `/seasons/{id}/` | |

**Body:**
```json
{
  "name": "Primavera-Verano 2026",
  "code": "PV26",
  "kind": "SPRING_SUMMER",
  "starts_on": "2026-09-01",
  "ends_on": "2027-02-28",
  "is_active": true
}
```

**Tipos `kind`:** `SPRING_SUMMER`, `AUTUMN_WINTER`, `SCHOOL`, `PROMO`, `NEW_COLLECTION`

### Colecciones (RF23 — por temporada)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | `/collections/` | Colecciones ligadas a temporada |
| GET/PUT/PATCH/DELETE | `/collections/{id}/` | |

**Filtro clave:** `?season=1` — listar colecciones de una temporada.

**Body:**
```json
{
  "name": "Colección Urban Summer",
  "slug": "urban-summer",
  "season": 1,
  "supplier": 2,
  "launch_date": "2026-09-15",
  "is_active": true
}
```

> **Regla del dominio:** `Product → Collection → Season`. La temporada no se duplica en el producto.

### Productos (RF04, RF07)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | `/products/` | CRUD productos |
| GET/PUT/PATCH/DELETE | `/products/{id}/` | |
| GET | `/products/{id}/availability/` | Stock por variante y sucursal (RF08) |

**Filtros listado:**
- `?category=1&brand=2&collection=3&gender=UNISEX`
- `?base_price__gte=50&base_price__lte=200`
- `?branch=1` — solo productos con stock disponible en esa sucursal
- `?search=camisa&ordering=-created_at`

**Body producto:**
```json
{
  "name": "Camisa Oxford",
  "description": "Camisa formal algodón",
  "category_id": 1,
  "brand_id": 2,
  "collection_id": 3,
  "gender": "MALE",
  "base_price": "299.00",
  "material": "Algodón 100%",
  "is_active": true
}
```

### Variantes (SKU = producto × talla × color)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | `/variants/` | CRUD variantes |
| GET/PUT/PATCH/DELETE | `/variants/{id}/` | |

**Filtros:** `?product=1&size=3&color=2`

**Body:**
```json
{
  "product": 1,
  "size": 3,
  "color": 2,
  "price_override": null,
  "barcode": "7700123456789",
  "is_active": true
}
```

### Imágenes de producto

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | `/product-images/` | Subir/gestionar imágenes |
| GET/PUT/PATCH/DELETE | `/product-images/{id}/` | |

**Filtros:** `?product=1&color=2&is_primary=true`  
**Upload:** `multipart/form-data` con campo `image`.

### Assets AR (RF13)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | `/ar-assets/` | Assets por producto + color |
| GET/PUT/PATCH/DELETE | `/ar-assets/{id}/` | |

**Filtros:** `?product=1&kind=MODEL_3D`

---

## 4. Inventario (RF08, RF21, RF22)

Permiso lectura: `inventory.stock.view`  
Permiso escritura: `inventory.stock.manage`  
Encargados de sucursal solo ven **su** sucursal.

### Stock por sucursal

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/stock/` | Listar niveles de stock |
| GET | `/stock/{id}/` | Detalle |
| GET | `/stock/low_stock/` | Alertas bajo umbral (`?branch=1`) |
| POST | `/stock/adjust/` | Ajuste manual +/- |
| POST | `/stock/transfer/` | Transferencia entre sucursales |
| PATCH | `/stock/{id}/threshold/` | Actualizar umbral mínimo |

**Ajuste:**
```json
{
  "branch_id": 1,
  "variant_id": 10,
  "quantity": 5,
  "direction": "in",
  "note": "Conteo físico"
}
```

**Transferencia:**
```json
{
  "from_branch_id": 1,
  "to_branch_id": 2,
  "variant_id": 10,
  "quantity": 3,
  "note": "Reposición LPZ"
}
```

### Movimientos (ledger append-only)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/movements/` | Historial de movimientos |
| GET | `/movements/{id}/` | Detalle |

**Filtros:** `?branch=1&variant=10&movement_type=OUT_SALE`

---

## 5. Proveedores (RF06, RF12)

| Permiso | Código |
|---------|--------|
| Ver | `suppliers.view` |
| Gestionar | `suppliers.manage` |

### Proveedores

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | `/suppliers/` | CRUD proveedores |
| GET/PUT/PATCH/DELETE | `/suppliers/{id}/` | |

**Body:**
```json
{
  "legal_name": "Textiles del Sur SRL",
  "trade_name": "Textiles del Sur",
  "tax_id": "123456789",
  "email": "ventas@textiles.com",
  "phone": "+59170000099",
  "address": "Zona industrial",
  "is_active": true
}
```

### Recepciones de compra (ingreso de mercadería → stock)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | `/purchase-receipts/` | CRUD recepciones (borrador) |
| GET/PUT/PATCH/DELETE | `/purchase-receipts/{id}/` | Solo editable en DRAFT |
| POST | `/purchase-receipts/{id}/confirm/` | Confirma → movimiento IN_RECEIPT |
| POST | `/purchase-receipts/{id}/cancel/` | Cancela borrador |

**Body crear recepción:**
```json
{
  "supplier": 1,
  "branch": 1,
  "invoice_number": "FAC-2026-001",
  "notes": "Ingreso colección PV26",
  "items": [
    { "variant": 10, "quantity": 50, "unit_cost": "120.00" },
    { "variant": 11, "quantity": 30, "unit_cost": "95.00" }
  ]
}
```

---

## 6. Promociones

| Permiso escritura | `promotions.manage` |

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | `/promotions/` | CRUD promociones/cupones |
| GET/PUT/PATCH/DELETE | `/promotions/{id}/` | |
| POST | `/promotions/validate/` | Validar cupón (público) |

**Validar cupón:**
```json
{ "code": "VERANO20", "order_amount": "500.00" }
```

---

## 7. Reservas, pedidos y pagos (referencia)

| Módulo | Rutas principales |
|--------|-------------------|
| Reservas RF09–12 | `/reservations/`, `/reservations/{id}/transition/`, `/cancel/` |
| Carrito RF14 | `/cart/`, `/cart/add_item/`, `/cart/checkout/` |
| Órdenes RF15–17 | `/orders/`, `/pos/sales/` |
| Pagos RF19 | `/payment-intent/`, `/webhook/stripe/` |

---

## Permisos por rol (semilla)

| Rol | Puede gestionar |
|-----|-----------------|
| ADMIN | Todo |
| BRANCH_MANAGER | Catálogo (lectura), inventario, reservas, órdenes, POS, reportes |
| CASHIER | Catálogo (lectura), reservas (lectura), órdenes, POS |
| CUSTOMER | Catálogo, reservas propias, carrito |
| SUPPLIER | Proveedores y recepciones |

---

## Uso en Angular (front)

```typescript
// Guard de ruta
canActivate(): boolean {
  return this.auth.hasPermission('catalog.products.manage');
}

// Menú dinámico tras login
this.http.get('/api/v1/auth/me/permissions/').subscribe(data => {
  this.menu = buildMenu(data.permission_codes);
});
```

---

## Swagger / OpenAPI

- UI: `GET /api/schema/swagger/`
- Schema: `GET /api/schema/`

---

## Comandos útiles

```bash
python manage.py migrate          # aplicar migraciones RBAC + modelos
python manage.py seed_demo        # datos demo (~10 registros por tabla)
python manage.py seed_demo --flush --force   # reiniciar demo desde cero
python manage.py runserver        # servidor dev
```

### Credenciales demo (`seed_demo`)

| Rol | Email | Password |
|-----|-------|----------|
| Admin | `admin@fashionstore.demo` | `Demo1234!` |
| Encargado | `manager1@fashionstore.demo` | `Demo1234!` |
| Cajero | `cajero1@fashionstore.demo` | `Demo1234!` |
| Cliente | `cliente1@fashionstore.demo` | `Demo1234!` |
| Proveedor | `proveedor@fashionstore.demo` | `Demo1234!` |
