# RBAC — Coordinación Backend ↔ Frontend

## Modelo

| Capa | Responsabilidad |
|------|-----------------|
| **Backend** | Fuente de verdad: `RoleDefinition` + `AppPermission`, validación en API (`HasAppPermission`) |
| **Frontend** | UX: menú, guards de ruta, botones deshabilitados según permisos del usuario |

## Reglas

### 1. Admin = todos los permisos

- **Backend:** `user.role == ADMIN` o `is_superuser` → `user_has_permission()` siempre `True` y `get_permission_codes()` devuelve todos los permisos activos.
- **Frontend:** `PermissionService.has()` / `hasAny()` y `permissionGuard` devuelven `true` si `role === 'ADMIN'`.

### 2. Roles personalizados

1. Crear permisos en **Admin → Permisos** (`rbac.permissions.manage`).
2. Crear rol en **Admin → Roles** y asignar permisos (`rbac.roles.manage`).
3. Asignar rol al usuario en **Admin → Usuarios** (`accounts.users.manage`).
4. El login y `GET /api/v1/auth/me/permissions/` devuelven `permission_codes` según el rol.

El front **no** inventa permisos: usa la lista del API.

### 3. Convención de códigos

Formato: `modulo.recurso.accion`

Ejemplos usados en menú y rutas:

| Código | Uso |
|--------|-----|
| `catalog.products.view` | Ver catálogo |
| `catalog.products.manage` | CRUD catálogo |
| `pos.sales` | Punto de venta |
| `reports.view` | Reportes |
| `accounts.users.manage` | Gestionar usuarios |

Definidos en seed: `accounts/migrations/0004_seed_rbac.py`  
Menú admin: `frontend/src/app/core/config/admin-nav.config.ts`  
Guards: `frontend/src/app/app.routes.ts` → `permissionGuard('...')`

### 4. Sucursal en POS (caso Admin)

Cajeros/encargados tienen `employee_profile.branch`.  
**Admin no tiene perfil de empleado** → el POS usa:

- Query/body `branch_id` en `/api/v1/pos/*`
- Front: selector de sucursal en `PosSubnavComponent` (`PosBranchService`)

Sin sucursal, el backend usa la primera sucursal activa (solo admin).

### 5. Endpoints clave

| Endpoint | Uso front |
|----------|-----------|
| `POST /api/v1/auth/login/` | JWT + `user.permissions[]` inicial |
| `GET /api/v1/auth/me/permissions/` | Recarga permisos (`PermissionService.loadFromApi()`) |
| `GET/PUT /api/v1/roles/` | Pantalla roles |
| `GET/POST /api/v1/permissions/` | Pantalla permisos |

### 6. Checklist al añadir una feature

1. Crear permiso(s) en backend (migración o admin).
2. Asignar a roles en seed o UI.
3. Proteger vista DRF con `HasAppPermission` + `required_permission` o `permission_map`.
4. Añadir entrada en `admin-nav.config.ts` con `permissions: [...]`.
5. Añadir ruta con `permissionGuard('...')`.
6. En la página, `canManage = computed(() => permissions.has('...'))` para botones de escritura.

## Errores comunes

| Error | Causa | Solución |
|-------|-------|----------|
| `EMPLOYEE_PROFILE_MISSING` | POS exigía empleado (admin) | Usar `branch_id`; admin elige sucursal en POS |
| `403 FORBIDDEN` en API | Falta permiso en el rol | Asignar permiso al rol en Admin → Roles |
| Menú vacío | Rol sin permisos `.view` | Asignar permisos de lectura al rol |
| Admin bloqueado en ruta | Front sin bypass ADMIN | Ya corregido en `PermissionService` |
