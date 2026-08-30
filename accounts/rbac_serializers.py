"""
Serializers for RBAC (roles and permissions).
"""
from rest_framework import serializers

from accounts.models import AppPermission, RoleDefinition, Role


class AppPermissionSerializer(serializers.ModelSerializer):
    """CRUD serializer for application permissions."""

    class Meta:
        model = AppPermission
        fields = [
            'id',
            'code',
            'name',
            'description',
            'module',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_code(self, value):
        code = value.strip().lower()
        if ' ' in code:
            raise serializers.ValidationError(
                'El código no puede contener espacios. Use formato modulo.recurso.accion'
            )
        return code


class AppPermissionMinimalSerializer(serializers.ModelSerializer):
    """Lightweight permission representation nested in roles."""

    class Meta:
        model = AppPermission
        fields = ['id', 'code', 'name', 'module']


class RoleDefinitionSerializer(serializers.ModelSerializer):
    """Read serializer with nested permission details."""

    permissions = AppPermissionMinimalSerializer(many=True, read_only=True)
    permission_count = serializers.IntegerField(source='permissions.count', read_only=True)
    user_count = serializers.SerializerMethodField()

    class Meta:
        model = RoleDefinition
        fields = [
            'id',
            'code',
            'name',
            'description',
            'permissions',
            'permission_count',
            'user_count',
            'is_system',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_user_count(self, obj):
        from accounts.models import User
        return User.objects.filter(role=obj.code).count()


class RoleDefinitionWriteSerializer(serializers.ModelSerializer):
    """Create/update serializer with permission assignment by ID."""

    permission_ids = serializers.PrimaryKeyRelatedField(
        queryset=AppPermission.objects.filter(is_active=True),
        many=True,
        source='permissions',
        required=False,
    )

    class Meta:
        model = RoleDefinition
        fields = [
            'id',
            'code',
            'name',
            'description',
            'permission_ids',
            'is_active',
        ]
        read_only_fields = ['id']

    def validate_code(self, value):
        code = value.strip().upper()
        if ' ' in code:
            raise serializers.ValidationError('El código no puede contener espacios')
        return code

    def validate(self, attrs):
        if self.instance and self.instance.is_system:
            if 'code' in attrs and attrs['code'] != self.instance.code:
                raise serializers.ValidationError({
                    'code': 'No se puede cambiar el código de un rol del sistema',
                })
        return attrs

    def create(self, validated_data):
        permissions = validated_data.pop('permissions', [])
        role = RoleDefinition.objects.create(is_system=False, **validated_data)
        if permissions:
            role.permissions.set(permissions)
        return role

    def update(self, instance, validated_data):
        permissions = validated_data.pop('permissions', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if permissions is not None:
            instance.permissions.set(permissions)
        return instance


class RolePermissionAssignSerializer(serializers.Serializer):
    """Bulk assign permissions to a role (replaces current set)."""

    permission_ids = serializers.PrimaryKeyRelatedField(
        queryset=AppPermission.objects.filter(is_active=True),
        many=True,
    )


class UserPermissionsSerializer(serializers.Serializer):
    """Current user permission payload for the frontend."""

    role = serializers.CharField()
    role_name = serializers.CharField()
    permissions = AppPermissionMinimalSerializer(many=True)
    permission_codes = serializers.ListField(child=serializers.CharField())
