"""Extend RBAC seed with suppliers and promotions permissions."""
from django.db import migrations


NEW_PERMISSIONS = [
    ('suppliers.view', 'Ver proveedores', 'Consultar proveedores y recepciones', 'suppliers'),
    ('suppliers.manage', 'Gestionar proveedores', 'Administrar proveedores y recepciones de compra', 'suppliers'),
    ('promotions.view', 'Ver promociones', 'Consultar promociones y cupones', 'promotions'),
    ('promotions.manage', 'Gestionar promociones', 'Crear y editar promociones', 'promotions'),
]

ROLE_ADDITIONS = {
    'ADMIN': '__all_new__',
    'BRANCH_MANAGER': ['suppliers.view'],
    'SUPPLIER': ['suppliers.view', 'suppliers.manage'],
}


def extend_permissions(apps, schema_editor):
    AppPermission = apps.get_model('accounts', 'AppPermission')
    RoleDefinition = apps.get_model('accounts', 'RoleDefinition')

    created = {}
    for code, name, description, module in NEW_PERMISSIONS:
        perm, _ = AppPermission.objects.get_or_create(
            code=code,
            defaults={'name': name, 'description': description, 'module': module, 'is_active': True},
        )
        created[code] = perm

    admin = RoleDefinition.objects.filter(code='ADMIN').first()
    if admin:
        admin.permissions.add(*created.values())

    for role_code, codes in ROLE_ADDITIONS.items():
        if role_code == 'ADMIN':
            continue
        role = RoleDefinition.objects.filter(code=role_code).first()
        if role:
            role.permissions.add(*[created[c] for c in codes if c in created])


def reverse_extend(apps, schema_editor):
    AppPermission = apps.get_model('accounts', 'AppPermission')
    AppPermission.objects.filter(
        code__in=[p[0] for p in NEW_PERMISSIONS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_seed_rbac'),
    ]

    operations = [
        migrations.RunPython(extend_permissions, reverse_extend),
    ]
