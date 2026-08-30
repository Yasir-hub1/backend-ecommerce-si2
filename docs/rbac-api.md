# RBAC — Roles y Permisos (API)

Documentación de los endpoints para gestionar el sistema de **Role-Based Access Control (RBAC)** de FashionStore.

Base URL: `/api/v1/`

Autenticación: **JWT Bearer** en todas las rutas excepto login/registro.

```
Authorization: Bearer <access_token>
```

---

## Conceptos

| Entidad | Tabla | Descripción |
|---------|-------|-------------|
| **AppPermission** | `app_permissions` | Permiso granular (`catalog.products.view`). Se crea/edita desde el front. |
| **RoleDefinition** | `role_definitions` | Rol configurable con un conjunto de permisos (M2M). |
| **User.role** | `users.role` | Código del rol asignado al usuario (`RoleDefinition.code`). |

### Flujo en el frontend

1. **Login** → el token JWT incluye `role` y `permissions` (lista de códigos).
2. **Menú/rutas** → consultar `GET /auth/me/permissions/` o usar los códigos del token.
3. **Backoffice RBAC** → CRUD de permisos y roles (requiere permisos `rbac.*`).
4. **Guard de ruta** → verificar que el usuario tenga el código requerido, ej. `catalog.products.manage`.

### Convención de códigos

Formato: `modulo.recurso.accion`

Ejemplos:
- `rbac.roles.manage`
- `catalog.products.view`
- `pos.sales`

---

## Permisos del sistema (semilla)

Migración `0004_seed_rbac` crea estos permisos y roles:

| Módulo | Permisos |
|--------|----------|
| `rbac` | `permissions.view`, `permissions.manage`, `roles.view`, `roles.manage` |
| `accounts` | `users.view`, `users.manage` |
| `catalog` | `products.view`, `products.manage` |
| `inventory` | `stock.view`, `stock.manage` |
| `reservations` | `view`, `manage` |
| `orders` | `view`, `manage` |
| `pos` | `sales` |
| `payments` | `view`, `manage` |
| `reports` | `view` |
| `branches` | `view`, `manage` |

Roles del sistema (`is_system: true`, no eliminables):

| Código | Nombre | Permisos por defecto |
|--------|--------|----------------------|
| `ADMIN` | Administrador | Todos |
| `BRANCH_MANAGER` | Encargado de Sucursal | Catálogo, inventario, reservas, órdenes, POS, reportes |
| `CASHIER` | Cajero | Catálogo (lectura), reservas (lectura), órdenes, POS |
| `CUSTOMER` | Cliente | Catálogo, reservas, órdenes propias |
| `SUPPLIER` | Proveedor | Catálogo e inventario (lectura) |

---

## Autenticación — permisos del usuario actual

### `GET /api/v1/auth/me/permissions/`

Devuelve el rol y los permisos del usuario autenticado. **No requiere permiso RBAC** (cualquier usuario logueado).

**Respuesta 200:**

```json
{
  "role": "BRANCH_MANAGER",
  "role_name": "Encargado de Sucursal",
  "permission_codes": [
    "catalog.products.view",
    "inventory.stock.manage",
    "inventory.stock.view",
    "orders.manage",
    "orders.view",
    "payments.view",
    "pos.sales",
    "reports.view",
    "reservations.manage",
    "reservations.view"
  ],
  "permissions": [
    {
      "id": 7,
      "code": "catalog.products.view",
      "name": "Ver catálogo",
      "module": "catalog"
    }
  ]
}
```

### Login — claims JWT adicionales

`POST /api/v1/auth/login/` incluye en el token y en `user`:

```json
{
  "access": "...",
  "user": {
    "id": 1,
    "email": "admin@fashionstore.com",
    "role": "ADMIN",
    "permissions": ["rbac.roles.manage", "catalog.products.view", "..."]
  }
}
```

Claim JWT: `permissions` (array de strings).

---

## CRUD — Permisos (`AppPermission`)

Requiere autenticación + permiso RBAC según acción.

| Acción | Permiso requerido |
|--------|-------------------|
| Listar / detalle | `rbac.permissions.view` |
| Crear / editar / eliminar | `rbac.permissions.manage` |

### `GET /api/v1/permissions/`

Lista paginada de permisos.

**Query params:**

| Param | Tipo | Descripción |
|-------|------|-------------|
| `module` | string | Filtrar por módulo (`catalog`, `orders`, …) |
| `is_active` | boolean | Solo activos/inactivos |
| `search` | string | Busca en `code`, `name`, `description` |
| `ordering` | string | `module`, `code`, `name`, `created_at` |
| `page` | int | Página (paginación estándar, 20 ítems) |

**Respuesta 200:**

```json
{
  "count": 20,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "code": "rbac.permissions.view",
      "name": "Ver permisos",
      "description": "Consultar permisos del sistema",
      "module": "rbac",
      "is_active": true,
      "created_at": "2026-08-28T18:00:00Z",
      "updated_at": "2026-08-28T18:00:00Z"
    }
  ]
}
```

### `GET /api/v1/permissions/{id}/`

Detalle de un permiso. Misma estructura que un ítem de la lista.

### `POST /api/v1/permissions/`

Crea un permiso.

**Body:**

```json
{
  "code": "promotions.manage",
  "name": "Gestionar promociones",
  "description": "Crear y editar campañas promocionales",
  "module": "promotions",
  "is_active": true
}
```

**Respuesta 201:** objeto permiso creado.

**Errores:**
- `400` — código duplicado o formato inválido (sin espacios).

### `PUT /api/v1/permissions/{id}/`

Reemplaza todos los campos editables.

### `PATCH /api/v1/permissions/{id}/`

Actualización parcial.

### `DELETE /api/v1/permissions/{id}/`

Elimina el permiso. Se desvincula automáticamente de los roles (M2M).

---

## CRUD — Roles (`RoleDefinition`)

| Acción | Permiso requerido |
|--------|-------------------|
| Listar / detalle | `rbac.roles.view` |
| Crear / editar / eliminar / asignar permisos | `rbac.roles.manage` |

### `GET /api/v1/roles/`

Lista paginada de roles.

**Query params:**

| Param | Tipo | Descripción |
|-------|------|-------------|
| `is_active` | boolean | Filtrar activos |
| `is_system` | boolean | Filtrar roles del sistema |
| `search` | string | Busca en `code`, `name`, `description` |
| `ordering` | string | `name`, `code`, `created_at` |

**Respuesta 200:**

```json
{
  "count": 5,
  "results": [
    {
      "id": 2,
      "code": "BRANCH_MANAGER",
      "name": "Encargado de Sucursal",
      "description": "Gestión de sucursal, reservas e inventario",
      "permissions": [
        {"id": 7, "code": "catalog.products.view", "name": "Ver catálogo", "module": "catalog"}
      ],
      "permission_count": 11,
      "user_count": 3,
      "is_system": true,
      "is_active": true,
      "created_at": "2026-08-28T18:00:00Z",
      "updated_at": "2026-08-28T18:00:00Z"
    }
  ]
}
```

### `GET /api/v1/roles/{id}/`

Detalle de un rol con permisos anidados.

### `POST /api/v1/roles/`

Crea un rol **personalizado** (`is_system` siempre `false`).

**Body:**

```json
{
  "code": "WAREHOUSE",
  "name": "Almacén central",
  "description": "Gestiona stock de depósito",
  "permission_ids": [7, 8, 9],
  "is_active": true
}
```

**Respuesta 201:** rol creado (serializer de escritura).

**Notas:**
- `code` se normaliza a MAYÚSCULAS.
- `permission_ids` es opcional; asigna permisos en la creación.

### `PUT /api/v1/roles/{id}/`

Actualiza rol. En roles del sistema **no se puede cambiar** `code`.

**Body (escritura):**

```json
{
  "code": "WAREHOUSE",
  "name": "Almacén central",
  "description": "Actualizado",
  "permission_ids": [7, 8],
  "is_active": true
}
```

### `PATCH /api/v1/roles/{id}/`

Actualización parcial.

### `DELETE /api/v1/roles/{id}/`

Elimina el rol.

**Errores:**
- `400` — rol con `is_system: true` (ADMIN, CASHIER, etc.).

---

## Asignación de permisos a roles

### `PUT /api/v1/roles/{id}/permissions/`

**Reemplaza** el conjunto completo de permisos del rol.

**Permiso:** `rbac.roles.manage`

**Body:**

```json
{
  "permission_ids": [1, 2, 3, 7, 8]
}
```

**Respuesta 200:** rol con permisos actualizados (serializer de lectura).

### `POST /api/v1/roles/{id}/permissions/add/`

**Agrega** permisos sin quitar los existentes.

**Body:**

```json
{
  "permission_ids": [15, 16]
}
```

### `POST /api/v1/roles/{id}/permissions/remove/`

**Quita** permisos específicos del rol.

**Body:**

```json
{
  "permission_ids": [15]
}
```

---

## Asignar rol a usuarios

Los usuarios usan el campo `role` (string = `RoleDefinition.code`).

### `PATCH /api/v1/users/{id}/`

Requiere permiso de admin (`IsAdmin`) o `accounts.users.manage` (según evolución del proyecto).

**Body:**

```json
{
  "role": "WAREHOUSE"
}
```

Validación: el código debe existir en `role_definitions` y estar activo.

### Crear empleado

`POST /api/v1/employees/create/` — el campo `role` debe ser un rol activo (`BRANCH_MANAGER` o `CASHIER` para empleados de sucursal).

---

## Uso en el backend (proteger endpoints)

Clase de permiso DRF en `core/permissions.py`:

```python
from core.permissions import HasAppPermission

class MiViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasAppPermission]
    permission_map = {
        'list': 'catalog.products.view',
        'create': 'catalog.products.manage',
    }

    def get_required_permission(self):
        return self.permission_map.get(self.action)
```

Helpers en modelo `User`:

```python
user.has_app_permission('orders.manage')
user.get_permission_codes()
```

---

## Códigos de error

| HTTP | Situación |
|------|-----------|
| `401` | Token ausente o inválido |
| `403` | Usuario autenticado sin el permiso requerido |
| `400` | Validación (código duplicado, rol del sistema, rol inexistente) |
| `404` | Recurso no encontrado |

Formato de error estándar del proyecto (ver `core/exceptions.py`).

---

## Resumen de endpoints

| Método | Ruta | Descripción | Permiso |
|--------|------|-------------|---------|
| GET | `/auth/me/permissions/` | Permisos del usuario logueado | Autenticado |
| GET | `/permissions/` | Listar permisos | `rbac.permissions.view` |
| POST | `/permissions/` | Crear permiso | `rbac.permissions.manage` |
| GET | `/permissions/{id}/` | Detalle permiso | `rbac.permissions.view` |
| PUT/PATCH | `/permissions/{id}/` | Editar permiso | `rbac.permissions.manage` |
| DELETE | `/permissions/{id}/` | Eliminar permiso | `rbac.permissions.manage` |
| GET | `/roles/` | Listar roles | `rbac.roles.view` |
| POST | `/roles/` | Crear rol | `rbac.roles.manage` |
| GET | `/roles/{id}/` | Detalle rol | `rbac.roles.view` |
| PUT/PATCH | `/roles/{id}/` | Editar rol | `rbac.roles.manage` |
| DELETE | `/roles/{id}/` | Eliminar rol | `rbac.roles.manage` |
| PUT | `/roles/{id}/permissions/` | Reemplazar permisos del rol | `rbac.roles.manage` |
| POST | `/roles/{id}/permissions/add/` | Agregar permisos al rol | `rbac.roles.manage` |
| POST | `/roles/{id}/permissions/remove/` | Quitar permisos del rol | `rbac.roles.manage` |

---

## Migraciones aplicadas

```bash
python manage.py migrate accounts
```

- `0003_rbac` — tablas `app_permissions`, `role_definitions`, alter `users.role`
- `0004_seed_rbac` — permisos y roles del sistema con asignaciones por defecto
