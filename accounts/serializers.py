"""
Serializers for accounts app.
"""
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from accounts.models import User, CustomerProfile, EmployeeProfile, Role, RoleDefinition, Gender, Position
from branches.models import Branch


class UserSerializer(serializers.ModelSerializer):
    """Base user serializer."""

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'first_name',
            'last_name',
            'role',
            'phone',
            'is_active',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_role(self, value):
        code = value.strip().upper()
        if not RoleDefinition.objects.filter(code=code, is_active=True).exists():
            raise serializers.ValidationError('El rol especificado no existe o está inactivo')
        return code


class CustomerProfileSerializer(serializers.ModelSerializer):
    """Customer profile serializer."""
    user = UserSerializer(read_only=True)
    preferred_branch_name = serializers.CharField(source='preferred_branch.name', read_only=True)

    class Meta:
        model = CustomerProfile
        fields = [
            'user',
            'birth_date',
            'gender_preference',
            'default_size_top',
            'default_size_bottom',
            'preferred_branch',
            'preferred_branch_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['user', 'created_at', 'updated_at']


class EmployeeProfileSerializer(serializers.ModelSerializer):
    """Employee profile serializer."""
    user = UserSerializer(read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model = EmployeeProfile
        fields = [
            'user',
            'branch',
            'branch_name',
            'position',
            'hire_date',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['user', 'created_at', 'updated_at']


class CustomerRegistrationSerializer(serializers.Serializer):
    """Customer registration serializer."""
    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        style={'input_type': 'password'},
        help_text='Mínimo 8 caracteres. No uses contraseñas comunes ni solo números.',
    )
    password_confirm = serializers.CharField(write_only=True, style={'input_type': 'password'})
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    birth_date = serializers.DateField(required=False, allow_null=True)
    gender_preference = serializers.ChoiceField(choices=Gender.CHOICES, required=False)

    def validate_email(self, value):
        """Normalize and reject duplicates case-insensitively."""
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError('Este email ya está registrado')
        return email

    def validate_phone(self, value):
        """Blank phone must be NULL — empty string breaks the unique constraint."""
        phone = (value or '').strip()
        return phone or None

    def validate(self, attrs):
        """Validate passwords match and meet Django strength rules."""
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({
                'password_confirm': 'Las contraseñas no coinciden',
            })

        try:
            # Pass a temporary user so AttributeSimilarity can check name/email.
            provisional = User(
                email=attrs['email'],
                first_name=attrs.get('first_name', ''),
                last_name=attrs.get('last_name', ''),
            )
            validate_password(attrs['password'], user=provisional)
        except DjangoValidationError as e:
            raise serializers.ValidationError({'password': list(e.messages)})

        return attrs

    def create(self, validated_data):
        """Create user and customer profile."""
        # Remove password_confirm
        validated_data.pop('password_confirm')

        # Extract profile data
        birth_date = validated_data.pop('birth_date', None)
        # CharField is NOT NULL — omit the key so the model default applies.
        gender_preference = validated_data.pop('gender_preference', Gender.UNISEX)
        phone = validated_data.pop('phone', None) or None

        # Create user
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            phone=phone,
            role=Role.CUSTOMER,
        )

        # Create customer profile
        CustomerProfile.objects.create(
            user=user,
            birth_date=birth_date,
            gender_preference=gender_preference or Gender.UNISEX,
        )

        return user


class EmployeeCreateSerializer(serializers.Serializer):
    """Create employee user."""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    role = serializers.CharField(max_length=50)
    position = serializers.ChoiceField(choices=Position.CHOICES)
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all())
    hire_date = serializers.DateField()

    def validate_role(self, value):
        code = value.strip().upper()
        if not RoleDefinition.objects.filter(code=code, is_active=True).exists():
            raise serializers.ValidationError('El rol especificado no existe o está inactivo')
        blocked = {Role.CUSTOMER, Role.ADMIN, Role.SUPPLIER}
        if code in blocked:
            raise serializers.ValidationError(
                'Usa otro flujo para crear clientes, administradores o proveedores'
            )
        return code

    def validate_email(self, value):
        """Check if email is already in use."""
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError('Este email ya está registrado')
        return email

    def validate_phone(self, value):
        phone = (value or '').strip()
        return phone or None

    def validate(self, attrs):
        """Validate role matches position."""
        role = attrs['role']
        position = attrs['position']

        # Validate role-position mapping
        if role == Role.BRANCH_MANAGER and position != Position.MANAGER:
            raise serializers.ValidationError({
                'position': "El rol de encargado requiere posición de gerente"
            })
        if role == Role.CASHIER and position not in (Position.CASHIER, Position.STAFF):
            raise serializers.ValidationError({
                'position': "El rol de cajero requiere posición de cajero"
            })

        return attrs

    def create(self, validated_data):
        """Create user and employee profile."""
        # Extract profile data
        branch = validated_data.pop('branch')
        position = validated_data.pop('position')
        hire_date = validated_data.pop('hire_date')
        phone = validated_data.pop('phone', None) or None

        # Create user
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            phone=phone,
            role=validated_data['role'],
        )

        # Create employee profile
        import uuid

        EmployeeProfile.objects.create(
            user=user,
            branch=branch,
            position=position,
            hire_date=hire_date,
            employee_code=f'EMP-{uuid.uuid4().hex[:8].upper()}',
        )

        return user


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom JWT token serializer that includes role and branch_id in token claims.

    This allows the frontend to immediately show the correct menu/options
    without an extra API call.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Add custom claims
        token['role'] = user.role
        token['email'] = user.email
        token['full_name'] = user.get_full_name()
        token['permissions'] = user.get_permission_codes()

        # Add branch_id for staff users
        if user.role in [Role.BRANCH_MANAGER, Role.CASHIER]:
            try:
                token['branch_id'] = user.employee_profile.branch_id
            except EmployeeProfile.DoesNotExist:
                pass

        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        # Add user info to response
        data['user'] = {
            'id': self.user.id,
            'email': self.user.email,
            'first_name': self.user.first_name,
            'last_name': self.user.last_name,
            'role': self.user.role,
            'permissions': self.user.get_permission_codes(),
        }

        # Add branch info for staff
        if self.user.role in [Role.BRANCH_MANAGER, Role.CASHIER]:
            try:
                data['user']['branch_id'] = self.user.employee_profile.branch_id
            except EmployeeProfile.DoesNotExist:
                pass

        return data


class ChangePasswordSerializer(serializers.Serializer):
    """Change password serializer."""
    old_password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    new_password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    new_password_confirm = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate_old_password(self, value):
        """Check old password is correct."""
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Contraseña actual incorrecta")
        return value

    def validate(self, attrs):
        """Validate new passwords match."""
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({
                'new_password_confirm': "Las contraseñas no coinciden"
            })

        # Validate password strength
        try:
            validate_password(attrs['new_password'])
        except DjangoValidationError as e:
            raise serializers.ValidationError({'new_password': list(e.messages)})

        return attrs

    def save(self, **kwargs):
        """Change user password."""
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save(update_fields=['password'])
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    password_confirm = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({
                'password_confirm': 'Las contraseñas no coinciden',
            })
        return attrs
