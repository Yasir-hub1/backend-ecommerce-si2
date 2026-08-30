"""
Seed default permissions and system roles for FashionStore RBAC.
"""
from django.db import migrations


PERMISSIONS = [
    ('rbac.permissions.view', 'Ver permisos', 'Consultar permisos del sistema', 'rbac'),
    ('rbac.permissions.manage', 'Gestionar permisos', 'Crear, editar y eliminar permisos', 'rbac'),
    ('rbac.roles.view', 'Ver roles', 'Consultar roles y sus permisos', 'rbac'),
    ('rbac.roles.manage', 'Gestionar roles', 'Crear, editar y asignar permisos a roles', 'rbac'),
    ('accounts.users.view', 'Ver usuarios', 'Listar y consultar usuarios', 'accounts'),
    ('accounts.users.manage', 'Gestionar usuarios', 'Crear, editar y desactivar usuarios', 'accounts'),
    ('catalog.products.view', 'Ver catálogo', 'Consultar productos y variantes', 'catalog'),
    ('catalog.products.manage', 'Gestionar catálogo', 'Administrar productos, marcas y categorías', 'catalog'),
    ('inventory.stock.view', 'Ver inventario', 'Consultar stock por sucursal', 'inventory'),
    ('inventory.stock.manage', 'Gestionar inventario', 'Ajustes y movimientos de inventario', 'inventory'),
    ('reservations.view', 'Ver reservas', 'Consultar reservas de probador', 'reservations'),
    ('reservations.manage', 'Gestionar reservas', 'Confirmar, cancelar y atender reservas', 'reservations'),
    ('orders.view', 'Ver pedidos', 'Consultar órdenes y carritos', 'orders'),
    ('orders.manage', 'Gestionar pedidos', 'Procesar y cancelar órdenes', 'orders'),
    ('pos.sales', 'Ventas POS', 'Registrar ventas en caja', 'pos'),
    ('payments.view', 'Ver pagos', 'Consultar pagos y transacciones', 'payments'),
    ('payments.manage', 'Gestionar pagos', 'Procesar reembolsos y conciliación', 'payments'),
    ('reports.view', 'Ver reportes', 'Acceder a dashboards y reportes', 'reports'),
    ('branches.view', 'Ver sucursales', 'Consultar sucursales', 'branches'),
    ('branches.manage', 'Gestionar sucursales', 'Administrar sucursales y horarios', 'branches'),
]

ROLES = [
    ('ADMIN', 'Administrador', 'Acceso total al sistema', True),
    ('BRANCH_MANAGER', 'Encargado de Sucursal', 'Gestión de sucursal, reservas e inventario', True),
    ('CASHIER', 'Cajero', 'Operaciones de caja y ventas presenciales', True),
    ('CUSTOMER', 'Cliente', 'Compras en línea y reservas', True),
    ('SUPPLIER', 'Proveedor', 'Portal de proveedor', True),
]

ROLE_PERMISSION_MAP = {
    'ADMIN': '__all__',
    'BRANCH_MANAGER': [
        'catalog.products.view',
        'inventory.stock.view',
        'inventory.stock.manage',
        'reservations.view',
        'reservations.manage',
        'orders.view',
        'orders.manage',
        'pos.sales',
        'payments.view',
        'reports.view',
        'branches.view',
    ],
    'CASHIER': [
        'catalog.products.view',
        'inventory.stock.view',
        'reservations.view',
        'orders.view',
        'pos.sales',
        'payments.view',
    ],
    'CUSTOMER': [
        'catalog.products.view',
        'reservations.view',
        'orders.view',
        'orders.manage',
    ],
    'SUPPLIER': [
        'catalog.products.view',
        'inventory.stock.view',
    ],
}


def seed_rbac(apps, schema_editor):
    AppPermission = apps.get_model('accounts', 'AppPermission')
    RoleDefinition = apps.get_model('accounts', 'RoleDefinition')

    permission_objects = {}
    for code, name, description, module in PERMISSIONS:
        permission_objects[code] = AppPermission.objects.create(
            code=code,
            name=name,
            description=description,
            module=module,
            is_active=True,
        )

    all_permissions = list(permission_objects.values())

    for code, name, description, is_system in ROLES:
        role = RoleDefinition.objects.create(
            code=code,
            name=name,
            description=description,
            is_system=is_system,
            is_active=True,
        )
        assigned = ROLE_PERMISSION_MAP[code]
        if assigned == '__all__':
            role.permissions.set(all_permissions)
        else:
            role.permissions.set(
                [permission_objects[c] for c in assigned if c in permission_objects]
            )


def unseed_rbac(apps, schema_editor):
    AppPermission = apps.get_model('accounts', 'AppPermission')
    RoleDefinition = apps.get_model('accounts', 'RoleDefinition')
    RoleDefinition.objects.all().delete()
    AppPermission.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_rbac'),
    ]

    operations = [
        migrations.RunPython(seed_rbac, unseed_rbac),
    ]
