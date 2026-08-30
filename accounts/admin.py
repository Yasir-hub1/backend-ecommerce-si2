from django.contrib import admin

from accounts.models import AppPermission, RoleDefinition


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
