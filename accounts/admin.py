from django.contrib import admin

from accounts.models import AppPermission, Bitacora, RoleDefinition


@admin.register(AppPermission)
class AppPermissionAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'module', 'is_active', 'created_at')
    list_filter = ('module', 'is_active')
    search_fields = ('code', 'name')
    ordering = ('module', 'code')


@admin.register(RoleDefinition)
class RoleDefinitionAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_system', 'is_active', 'created_at')
    list_filter = ('is_system', 'is_active')
    search_fields = ('code', 'name')
    filter_horizontal = ('permissions',)
    ordering = ('name',)


@admin.register(Bitacora)
class BitacoraAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user_email', 'action', 'module', 'resource', 'description')
    list_filter = ('action', 'module')
    search_fields = ('user_email', 'user_full_name', 'description', 'path')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    readonly_fields = (
        'user',
        'user_email',
        'user_full_name',
        'action',
        'module',
        'resource',
        'object_id',
        'description',
        'method',
        'path',
        'ip_address',
        'metadata',
        'created_at',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
