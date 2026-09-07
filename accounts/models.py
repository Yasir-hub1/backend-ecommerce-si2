"""
User models and profiles for FashionStore.
"""
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.contrib.auth.base_user import BaseUserManager
from django.utils import timezone
from django.core.validators import RegexValidator

from core.models import TimeStampedModel


class Role:
    """User role constants."""
    CUSTOMER = 'CUSTOMER'
    ADMIN = 'ADMIN'
    BRANCH_MANAGER = 'BRANCH_MANAGER'
    CASHIER = 'CASHIER'
    SUPPLIER = 'SUPPLIER'

    CHOICES = [
        (CUSTOMER, 'Cliente'),
        (ADMIN, 'Administrador'),
        (BRANCH_MANAGER, 'Encargado de Sucursal'),
        (CASHIER, 'Cajero'),
        (SUPPLIER, 'Proveedor'),
    ]


class UserManager(BaseUserManager):
    """Custom manager for User model."""

    def create_user(self, email, password=None, **extra_fields):
        """Create and save a regular user."""
        if not email:
            raise ValueError('El email es obligatorio')

        email = self.normalize_email(email)
        extra_fields.setdefault('role', Role.CUSTOMER)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_staff', False)
        # phone is unique + nullable: empty string collides with other blank phones.
        if not extra_fields.get('phone'):
            extra_fields['phone'] = None

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Create and save a superuser."""
        extra_fields.setdefault('role', Role.ADMIN)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True')

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    """
    Custom User model with email as username field.

    Roles:
    - CUSTOMER: Regular customer
    - ADMIN: Full system access
    - BRANCH_MANAGER: Manages a specific branch
    - CASHIER: Point of sale operations
    - SUPPLIER: Supplier portal access (optional)
    """
    email = models.EmailField(
        'Correo electrónico',
        unique=True,
        error_messages={
            'unique': 'Ya existe un usuario con este correo electrónico',
        }
    )
    first_name = models.CharField('Nombre', max_length=80)
    last_name = models.CharField('Apellido', max_length=80)

    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{8,15}$',
        message="El teléfono debe estar en formato: '+999999999'. Hasta 15 dígitos."
    )
    phone = models.CharField(
        'Teléfono',
        validators=[phone_regex],
        max_length=20,
        blank=True,
        null=True,
        unique=True,
    )

    role = models.CharField(
        'Rol',
        max_length=50,
        default=Role.CUSTOMER,
        db_index=True,
        help_text='Código del rol asignado (RoleDefinition.code)',
    )

    is_active = models.BooleanField('Activo', default=True)
    is_staff = models.BooleanField('Es staff', default=False)
    date_joined = models.DateTimeField('Fecha de registro', default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        db_table = 'users'
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
        ordering = ['-date_joined']

    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"

    def get_full_name(self):
        """Return the first_name plus the last_name, with a space in between."""
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        """Return the short name for the user."""
        return self.first_name

    def get_permission_codes(self) -> list[str]:
        """Return sorted list of active permission codes for this user's role."""
        from accounts.services.permissions import get_user_permission_codes

        return sorted(get_user_permission_codes(self))

    def has_app_permission(self, code: str) -> bool:
        """Check if user has a specific application permission."""
        from accounts.services.permissions import user_has_permission

        return user_has_permission(self, code)


class AppPermission(TimeStampedModel):
    """
    Granular permission for frontend menu and API access control.

    Use dotted codes: ``module.resource.action`` (e.g. ``catalog.products.view``).
    """

    code = models.CharField(
        'Código',
        max_length=100,
        unique=True,
        help_text='Identificador único, ej: catalog.products.view',
    )
    name = models.CharField('Nombre', max_length=150)
    description = models.TextField('Descripción', blank=True)
    module = models.CharField(
        'Módulo',
        max_length=50,
        blank=True,
        help_text='Agrupación para el front, ej: catalog, orders',
    )
    is_active = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'app_permissions'
        verbose_name = 'Permiso'
        verbose_name_plural = 'Permisos'
        ordering = ['module', 'code']
        indexes = [
            models.Index(fields=['module', 'is_active']),
        ]

    def __str__(self):
        return f"{self.code} ({self.name})"


class RoleDefinition(TimeStampedModel):
    """
    Configurable role with a set of AppPermission entries.

    ``code`` matches ``User.role`` (e.g. ADMIN, CASHIER) or custom roles
    created from the backoffice.
    """

    code = models.CharField(
        'Código',
        max_length=50,
        unique=True,
        help_text='Identificador del rol, ej: BRANCH_MANAGER',
    )
    name = models.CharField('Nombre', max_length=100)
    description = models.TextField('Descripción', blank=True)
    permissions = models.ManyToManyField(
        AppPermission,
        blank=True,
        related_name='roles',
        verbose_name='Permisos',
    )
    is_system = models.BooleanField(
        'Rol del sistema',
        default=False,
        help_text='Los roles del sistema no pueden eliminarse',
    )
    is_active = models.BooleanField('Activo', default=True)

    class Meta:
        db_table = 'role_definitions'
        verbose_name = 'Definición de Rol'
        verbose_name_plural = 'Definiciones de Rol'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class Gender:
    """Gender preference constants for recommendations."""
    MALE = 'MALE'
    FEMALE = 'FEMALE'
    UNISEX = 'UNISEX'
    KIDS = 'KIDS'

    CHOICES = [
        (MALE, 'Masculino'),
        (FEMALE, 'Femenino'),
        (UNISEX, 'Unisex'),
        (KIDS, 'Niños'),
    ]


class CustomerProfile(TimeStampedModel):
    """
    Extended profile for customers.

    Contains preferences for recommendations and shopping experience.
    """
    user = models.OneToOneField(
        'User',
        on_delete=models.CASCADE,
        related_name='customer_profile',
        primary_key=True,
    )

    birth_date = models.DateField('Fecha de nacimiento', null=True, blank=True)
    gender_preference = models.CharField(
        'Preferencia de género',
        max_length=10,
        choices=Gender.CHOICES,
        default=Gender.UNISEX,
    )

    # Size preferences for quick checkout
    default_size_top = models.ForeignKey(
        'catalog.Size',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customers_top',
        verbose_name='Talla superior preferida',
    )
    default_size_bottom = models.ForeignKey(
        'catalog.Size',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customers_bottom',
        verbose_name='Talla inferior preferida',
    )

    preferred_branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='preferred_customers',
        verbose_name='Sucursal preferida',
    )

    accepts_marketing = models.BooleanField('Acepta marketing', default=True)

    class Meta:
        db_table = 'customer_profiles'
        verbose_name = 'Perfil de Cliente'
        verbose_name_plural = 'Perfiles de Cliente'

    def __str__(self):
        return f"Perfil de {self.user.get_full_name()}"


class Position:
    """Employee position constants."""
    MANAGER = 'MANAGER'
    CASHIER = 'CASHIER'
    STAFF = 'STAFF'

    CHOICES = [
        (MANAGER, 'Encargado'),
        (CASHIER, 'Cajero'),
        (STAFF, 'Personal'),
    ]


class EmployeeProfile(TimeStampedModel):
    """
    Extended profile for employees (branch staff).

    Branch managers and cashiers work at a specific branch.
    """
    user = models.OneToOneField(
        'User',
        on_delete=models.CASCADE,
        related_name='employee_profile',
        primary_key=True,
    )

    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.PROTECT,
        related_name='employees',
        verbose_name='Sucursal',
    )

    position = models.CharField(
        'Cargo',
        max_length=20,
        choices=Position.CHOICES,
    )

    employee_code = models.CharField(
        'Código de empleado',
        max_length=20,
        unique=True,
    )

    hire_date = models.DateField('Fecha de contratación', default=timezone.now)

    class Meta:
        db_table = 'employee_profiles'
        verbose_name = 'Perfil de Empleado'
        verbose_name_plural = 'Perfiles de Empleado'
        indexes = [
            models.Index(fields=['branch', 'position']),
        ]

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.get_position_display()} ({self.branch.code})"

    def clean(self):
        """Validate that user role matches position."""
        from django.core.exceptions import ValidationError

        role_position_map = {
            Position.MANAGER: Role.BRANCH_MANAGER,
            Position.CASHIER: Role.CASHIER,
            Position.STAFF: Role.CASHIER,  # Staff también puede ser cajero
        }

        expected_role = role_position_map.get(self.position)
        if self.user.role == Role.ADMIN:
            return

        # Custom roles created in RBAC skip position/role coupling.
        if self.user.role not in (Role.BRANCH_MANAGER, Role.CASHIER):
            return

        if expected_role and self.user.role != expected_role:
            if not (self.user.role == Role.CASHIER and self.position == Position.STAFF):
                raise ValidationError(
                    f"El rol del usuario ({self.user.role}) "
                    f"no coincide con el cargo ({self.get_position_display()})"
                )

    def save(self, *args, **kwargs):
        """Run clean before save."""
        self.clean()
        super().save(*args, **kwargs)
