"""
Seed FashionStore with coherent demo data (~10 records per table).

Usage:
    python manage.py seed_demo
    python manage.py seed_demo --flush
    python manage.py seed_demo --force
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import (
    User, CustomerProfile, EmployeeProfile, Role, Position, Gender,
)
from ai.models import BrowsingEvent, ChatSession, ChatMessage, MessageRole, EventType, ProductEmbedding
from branches.models import City, Branch
from catalog.models import (
    Category, Brand, SizeGroup, Size, Color, Season, Collection,
    Product, ProductVariant, ProductImage, ARAsset,
)
from core.ar import default_anchor_config
from core.seed.demo_data import (
    DEMO_DOMAIN, DEMO_PASSWORD, CITIES, BRANCHES, CATEGORIES, BRANDS,
    COLORS, SEASONS, PRODUCTS, SUPPLIERS, placeholder_file, demo_email,
    random_embedding,
)
from inventory.models import BranchStock, InventoryMovement, MovementType, ReferenceType
from inventory.services import apply_movements
from notifications.models import Notification, NotificationType
from orders.models import (
    Cart, CartItem, Order, OrderItem, OrderChannel, OrderStatus,
)
from payments.models import (
    Payment, PaymentMethod, PaymentProvider, PaymentStatus,
    Receipt, StripeWebhookEvent,
)
from promotions.models import Promotion, DiscountType
from reports.models import ReportRequest, ReportStatus
from reservations.models import Reservation, ReservationItem, ReservationStatus, ItemStatus
from suppliers.models import (
    Supplier, PurchaseReceipt, PurchaseReceiptItem, PurchaseReceiptStatus,
)
from suppliers.services import confirm_receipt

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Carga datos de demostración coherentes para FashionStore (~10 por tabla)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Elimina datos demo (@fashionstore.demo) antes de sembrar',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-sembrar aunque ya existan datos demo',
        )

    def handle(self, *args, **options):
        if options['flush']:
            self._flush()
            self.stdout.write(self.style.WARNING('Datos demo eliminados.'))

        if User.objects.filter(email__endswith=f'@{DEMO_DOMAIN}').exists() and not options['force']:
            self.stdout.write(self.style.WARNING(
                'Demo ya existe. Usa --flush o --force para volver a sembrar.'
            ))
            self._print_credentials()
            return

        with transaction.atomic():
            ctx = {}
            self._seed_geography(ctx)
            self._seed_catalog(ctx)
            self._seed_suppliers(ctx)
            self._seed_users(ctx)
            self._seed_stock(ctx)
            self._seed_promotions(ctx)
            self._seed_commerce(ctx)
            self._seed_analytics(ctx)

        self.stdout.write(self.style.SUCCESS('seed_demo completado correctamente.'))
        self._print_summary(ctx)
        self._print_credentials()

    def _flush(self):
        """Remove demo-scoped data in safe FK order."""
        demo_users = User.objects.filter(email__endswith=f'@{DEMO_DOMAIN}')
        demo_customers = CustomerProfile.objects.filter(user__in=demo_users)
        demo_suppliers = Supplier.objects.filter(tax_id__startswith='1000000')

        ChatMessage.objects.filter(session__customer__in=demo_customers).delete()
        ChatSession.objects.filter(customer__in=demo_customers).delete()
        BrowsingEvent.objects.filter(customer__in=demo_customers).delete()
        ProductEmbedding.objects.filter(product__name__in=[p[0] for p in PRODUCTS]).delete()
        Notification.objects.filter(user__in=demo_users).delete()
        ReportRequest.objects.filter(user__in=demo_users).delete()

        Receipt.objects.filter(order__customer__in=demo_customers).delete()
        Payment.objects.filter(order__customer__in=demo_customers).delete()
        OrderItem.objects.filter(order__customer__in=demo_customers).delete()
        Order.objects.filter(customer__in=demo_customers).delete()
        CartItem.objects.filter(cart__customer__in=demo_customers).delete()
        Cart.objects.filter(customer__in=demo_customers).delete()

        ReservationItem.objects.filter(reservation__customer__in=demo_customers).delete()
        Reservation.objects.filter(customer__in=demo_customers).delete()

        InventoryMovement.objects.filter(branch__code__in=[b[0] for b in BRANCHES]).delete()
        BranchStock.objects.filter(branch__code__in=[b[0] for b in BRANCHES]).delete()

        PurchaseReceiptItem.objects.filter(receipt__supplier__in=demo_suppliers).delete()
        PurchaseReceipt.objects.filter(supplier__in=demo_suppliers).delete()
        demo_suppliers.delete()

        Promotion.objects.filter(code__startswith='DEMO').delete()

        ProductImage.objects.filter(product__name__in=[p[0] for p in PRODUCTS]).delete()
        ARAsset.objects.filter(product__name__in=[p[0] for p in PRODUCTS]).delete()
        ProductVariant.objects.filter(product__name__in=[p[0] for p in PRODUCTS]).delete()
        Product.objects.filter(name__in=[p[0] for p in PRODUCTS]).delete()
        Collection.objects.filter(slug__startswith='demo-').delete()
        Season.objects.filter(code__in=[s[1] for s in SEASONS]).delete()
        Color.objects.filter(name__in=[c[0] for c in COLORS]).delete()
        Size.objects.filter(code__in=['XS', 'S', 'M', 'L', 'XL', '28', '30', '32', '38', '40']).delete()
        Category.objects.filter(name__in=[c[0] for c in CATEGORIES]).delete()
        Brand.objects.filter(name__in=BRANDS).delete()

        EmployeeProfile.objects.filter(user__in=demo_users).delete()
        CustomerProfile.objects.filter(user__in=demo_users).delete()
        demo_users.delete()

        Branch.objects.filter(code__in=[b[0] for b in BRANCHES]).delete()
        City.objects.filter(name__in=[c[0] for c in CITIES]).delete()

        StripeWebhookEvent.objects.filter(event_id__startswith='evt_demo_').delete()

    def _seed_geography(self, ctx: dict) -> None:
        ctx['cities'] = []
        for name, dept in CITIES:
            city, _ = City.objects.get_or_create(
                name=name, department=dept, defaults={'is_active': True},
            )
            ctx['cities'].append(city)

        ctx['branches'] = []
        for code, name, city_idx, address in BRANCHES:
            branch, _ = Branch.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'city': ctx['cities'][city_idx],
                    'address': address,
                    'phone': f'+5917{random_phone()}',
                    'opens_at': timezone.datetime.strptime('09:00', '%H:%M').time(),
                    'closes_at': timezone.datetime.strptime('21:00', '%H:%M').time(),
                    'fitting_rooms': 4,
                    'is_active': True,
                },
            )
            ctx['branches'].append(branch)
        self.stdout.write(f'  Ciudades: {len(ctx["cities"])}, Sucursales: {len(ctx["branches"])}')

    def _seed_catalog(self, ctx: dict) -> None:
        ctx['size_groups'] = {
            'top': SizeGroup.objects.get_or_create(name='ALPHA_TOP', defaults={'description': 'Tallas superiores'})[0],
            'bottom': SizeGroup.objects.get_or_create(name='ALPHA_BOTTOM', defaults={'description': 'Tallas inferiores'})[0],
            'waist': SizeGroup.objects.get_or_create(name='WAIST_NUM', defaults={'description': 'Cintura numérica'})[0],
            'shoe': SizeGroup.objects.get_or_create(name='SHOE_EU', defaults={'description': 'Calzado EU'})[0],
        }
        size_defs = [
            ('top', 'XS', 1), ('top', 'S', 2), ('top', 'M', 3), ('top', 'L', 4), ('top', 'XL', 5),
            ('waist', '28', 1), ('waist', '30', 2), ('waist', '32', 3),
            ('shoe', '38', 1), ('shoe', '40', 2),
        ]
        ctx['sizes'] = []
        for group_key, code, order in size_defs:
            size, _ = Size.objects.get_or_create(
                group=ctx['size_groups'][group_key], code=code,
                defaults={'display_order': order},
            )
            ctx['sizes'].append(size)

        ctx['categories'] = []
        for name, _parent in CATEGORIES:
            cat, _ = Category.objects.get_or_create(
                slug=name.lower().replace(' ', '-'),
                defaults={
                    'name': name,
                    'size_group': ctx['size_groups']['top'],
                    'display_order': len(ctx['categories']),
                    'is_active': True,
                },
            )
            ctx['categories'].append(cat)

        ctx['brands'] = []
        for name in BRANDS:
            brand, _ = Brand.objects.get_or_create(
                slug=name.lower().replace(' ', '-'),
                defaults={'name': name},
            )
            ctx['brands'].append(brand)

        ctx['colors'] = []
        for name, hex_code in COLORS:
            color, _ = Color.objects.get_or_create(
                slug=name.lower().replace(' ', '-'),
                defaults={'name': name, 'hex_code': hex_code},
            )
            ctx['colors'].append(color)

        ctx['seasons'] = []
        for name, code, kind, starts, ends in SEASONS:
            season, _ = Season.objects.get_or_create(
                code=code,
                defaults={
                    'name': name, 'kind': kind,
                    'starts_on': starts, 'ends_on': ends, 'is_active': True,
                },
            )
            ctx['seasons'].append(season)

        ctx['collections'] = []
        for i in range(10):
            season = ctx['seasons'][i]
            coll, _ = Collection.objects.get_or_create(
                slug=f'demo-col-{season.code.lower()}',
                defaults={
                    'name': f'Colección Demo {season.code}',
                    'season': season,
                    'launch_date': season.starts_on,
                    'is_active': True,
                },
            )
            ctx['collections'].append(coll)

        ctx['products'] = []
        ctx['variants'] = []
        for i, (pname, gender, price, cat_idx, brand_idx) in enumerate(PRODUCTS):
            product, _ = Product.objects.get_or_create(
                slug=f'demo-{pname.lower().replace(" ", "-")[:40]}',
                defaults={
                    'name': pname,
                    'description': f'{pname} — prenda demo FashionStore temporada actual.',
                    'category': ctx['categories'][cat_idx],
                    'brand': ctx['brands'][brand_idx],
                    'collection': ctx['collections'][i],
                    'gender': gender,
                    'base_price': price,
                    'material': 'Algodón / Poliéster',
                    'care_instructions': 'Lavado a máquina 30°C',
                    'is_active': True,
                },
            )
            ctx['products'].append(product)

            size = ctx['sizes'][2] if cat_idx != 7 else ctx['sizes'][8]
            color = ctx['colors'][i]
            variant, _ = ProductVariant.objects.get_or_create(
                product=product, size=size, color=color,
                defaults={'is_active': True},
            )
            ctx['variants'].append(variant)

            ProductImage.objects.get_or_create(
                product=product, color=color,
                defaults={
                    'image': placeholder_file(f'product-{i}'),
                    'alt_text': pname,
                    'is_primary': True,
                    'display_order': 0,
                },
            )

            ARAsset.objects.get_or_create(
                product=product, color=color, kind=ARAsset.OVERLAY_2D,
                defaults={
                    'file': placeholder_file(f'ar-{i}'),
                    'anchor_config': default_anchor_config(auto_calibrated=True),
                    'status': ARAsset.READY,
                    'width': 1024,
                    'height': 1180,
                    'is_active': True,
                },
            )

        self.stdout.write(
            f'  Catálogo: {len(ctx["products"])} productos, '
            f'{len(ctx["variants"])} variantes'
        )

    def _seed_suppliers(self, ctx: dict) -> None:
        ctx['suppliers'] = []
        for i, (legal, trade, tax_id) in enumerate(SUPPLIERS):
            supplier, _ = Supplier.objects.get_or_create(
                tax_id=tax_id,
                defaults={
                    'legal_name': legal,
                    'trade_name': trade,
                    'email': f'proveedor{i + 1}@{DEMO_DOMAIN}',
                    'phone': f'+5917{random_phone()}',
                    'address': f'Zona industrial #{i + 1}',
                    'is_active': True,
                },
            )
            ctx['suppliers'].append(supplier)
        self.stdout.write(f'  Proveedores: {len(ctx["suppliers"])}')

    def _seed_users(self, ctx: dict) -> None:
        ctx['admin'] = self._create_user(
            demo_email('admin'), Role.ADMIN, 'Admin', 'FashionStore', is_staff=True,
        )
        ctx['managers'] = []
        ctx['cashiers'] = []
        for i in range(2):
            mgr = self._create_user(
                demo_email(f'manager{i + 1}'), Role.BRANCH_MANAGER,
                f'Encargado{i + 1}', 'Demo', is_staff=True,
            )
            EmployeeProfile.objects.get_or_create(
                user=mgr,
                defaults={
                    'branch': ctx['branches'][i],
                    'position': Position.MANAGER,
                    'employee_code': f'MGR-DEMO-{i + 1:02d}',
                    'hire_date': timezone.now().date() - timedelta(days=365),
                },
            )
            ctx['managers'].append(mgr)

        for i in range(2):
            cashier = self._create_user(
                demo_email(f'cajero{i + 1}'), Role.CASHIER,
                f'Cajero{i + 1}', 'Demo', is_staff=True,
            )
            EmployeeProfile.objects.get_or_create(
                user=cashier,
                defaults={
                    'branch': ctx['branches'][i],
                    'position': Position.CASHIER,
                    'employee_code': f'CAJ-DEMO-{i + 1:02d}',
                    'hire_date': timezone.now().date() - timedelta(days=180),
                },
            )
            ctx['cashiers'].append(cashier)

        supplier_user = self._create_user(
            demo_email('proveedor'), Role.SUPPLIER, 'Portal', 'Proveedor',
        )
        ctx['suppliers'][0].user = supplier_user
        ctx['suppliers'][0].save(update_fields=['user'])

        ctx['customers'] = []
        genders = [Gender.FEMALE, Gender.MALE, Gender.FEMALE, Gender.UNISEX, Gender.MALE]
        for i in range(5):
            user = self._create_user(
                demo_email(f'cliente{i + 1}'), Role.CUSTOMER,
                f'Cliente{i + 1}', 'Demo',
            )
            profile, _ = CustomerProfile.objects.get_or_create(
                user=user,
                defaults={
                    'gender_preference': genders[i],
                    'preferred_branch': ctx['branches'][i % len(ctx['branches'])],
                    'accepts_marketing': True,
                },
            )
            ctx['customers'].append(profile)

        self.stdout.write(
            f'  Usuarios: 1 admin, 2 encargados, 2 cajeros, 5 clientes, 1 proveedor'
        )

    def _create_user(self, email, role, first_name, last_name, is_staff=False):
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'first_name': first_name,
                'last_name': last_name,
                'role': role,
                'is_staff': is_staff,
                'is_active': True,
            },
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
        return user

    def _seed_stock(self, ctx: dict) -> None:
        ctx['receipts'] = []
        admin = ctx['admin']
        for i in range(10):
            supplier = ctx['suppliers'][i]
            branch = ctx['branches'][i]
            variant = ctx['variants'][i]
            receipt, created = PurchaseReceipt.objects.get_or_create(
                supplier=supplier,
                branch=branch,
                invoice_number=f'DEMO-INV-{i + 1:03d}',
                defaults={
                    'status': PurchaseReceiptStatus.DRAFT,
                    'notes': '[demo] Recepción de mercadería demo',
                },
            )
            if created:
                PurchaseReceiptItem.objects.create(
                    receipt=receipt, variant=variant,
                    quantity=20 + i * 5, unit_cost=Decimal('80.00') + i * 10,
                )
                confirm_receipt(receipt_id=receipt.id, user=admin)
            ctx['receipts'].append(receipt)

        stock_count = BranchStock.objects.filter(branch__in=ctx['branches']).count()
        movement_count = InventoryMovement.objects.filter(note__startswith='[demo]').count()
        self.stdout.write(f'  Inventario: {stock_count} stocks, {movement_count}+ movimientos')

    def _seed_promotions(self, ctx: dict) -> None:
        now = timezone.now()
        ctx['promotions'] = []
        for i in range(10):
            promo, _ = Promotion.objects.get_or_create(
                code=f'DEMO{i + 1:02d}',
                defaults={
                    'name': f'Promoción Demo {i + 1}',
                    'discount_type': DiscountType.PERCENT if i % 2 == 0 else DiscountType.FIXED,
                    'value': Decimal('10') if i % 2 == 0 else Decimal('50'),
                    'starts_at': now - timedelta(days=30),
                    'ends_at': now + timedelta(days=60),
                    'min_order_amount': Decimal('100') * i,
                    'max_uses': 100,
                    'used_count': i,
                    'is_active': True,
                },
            )
            ctx['promotions'].append(promo)
        self.stdout.write(f'  Promociones: {len(ctx["promotions"])}')

    def _seed_commerce(self, ctx: dict) -> None:
        now = timezone.now()
        ctx['reservations'] = []
        ctx['orders'] = []

        for i in range(10):
            customer = ctx['customers'][i % 5]
            branch = ctx['branches'][i]
            variant = ctx['variants'][i]
            scheduled = now + timedelta(days=i + 1, hours=10 + i)

            reservation, created = Reservation.objects.get_or_create(
                customer=customer,
                branch=branch,
                scheduled_for=scheduled,
                defaults={
                    'expires_at': scheduled + timedelta(hours=24),
                    'status': [
                        ReservationStatus.PENDING, ReservationStatus.PREPARING,
                        ReservationStatus.READY, ReservationStatus.COMPLETED,
                        ReservationStatus.CANCELLED,
                    ][i % 5],
                    'notes': '[demo] Reserva probador físico',
                },
            )
            if created:
                ReservationItem.objects.create(
                    reservation=reservation, variant=variant, quantity=1,
                )
                if reservation.status == ReservationStatus.PENDING:
                    apply_movements(
                        branch=branch,
                        lines=[(variant.id, 1)],
                        movement_type=MovementType.RESERVE_HOLD,
                        reference_type=ReferenceType.RESERVATION,
                        reference_id=reservation.id,
                        user=ctx['admin'],
                        note='[demo] Reserva probador',
                    )
            ctx['reservations'].append(reservation)

            unit_price = variant.effective_price
            qty = 1 + (i % 3)
            subtotal = unit_price * qty
            tax = (subtotal * Decimal('0.13')).quantize(Decimal('0.01'))
            grand = subtotal + tax

            order, created = Order.objects.get_or_create(
                branch=branch,
                customer=customer,
                channel=[OrderChannel.WEB, OrderChannel.MOBILE, OrderChannel.POS][i % 3],
                defaults={
                    'status': [OrderStatus.PAID, OrderStatus.DELIVERED, OrderStatus.PENDING_PAYMENT][i % 3],
                    'subtotal': subtotal,
                    'tax_total': tax,
                    'discount_total': Decimal('0'),
                    'grand_total': grand,
                    'promotion': ctx['promotions'][i] if i < 3 else None,
                    'created_by': ctx['cashiers'][i % 2] if i % 3 == 2 else None,
                    'paid_at': now - timedelta(days=i) if i % 3 != 2 else None,
                },
            )
            if created:
                OrderItem.objects.create(
                    order=order, variant=variant,
                    quantity=qty, unit_price=unit_price,
                )
                if order.status in (OrderStatus.PAID, OrderStatus.DELIVERED):
                    apply_movements(
                        branch=branch,
                        lines=[(variant.id, qty)],
                        movement_type=MovementType.OUT_SALE,
                        reference_type=ReferenceType.ORDER,
                        reference_id=order.id,
                        user=ctx['cashiers'][i % 2],
                        note='[demo] Venta demo',
                    )
                    Payment.objects.create(
                        order=order,
                        method=[PaymentMethod.CARD_ONLINE, PaymentMethod.CASH, PaymentMethod.CARD_POS][i % 3],
                        provider=PaymentProvider.STRIPE if i % 3 == 0 else PaymentProvider.NONE,
                        status=PaymentStatus.SUCCEEDED,
                        amount=grand,
                        paid_at=now - timedelta(days=i),
                    )
                    Receipt.objects.get_or_create(
                        order=order,
                        defaults={'branch': branch, 'number': 1000 + i},
                    )
            ctx['orders'].append(order)

            cart, _ = Cart.objects.get_or_create(customer=customer)
            CartItem.objects.get_or_create(
                cart=cart, variant=ctx['variants'][(i + 1) % 10],
                defaults={'quantity': 1 + (i % 2)},
            )

        for i in range(10):
            StripeWebhookEvent.objects.get_or_create(
                event_id=f'evt_demo_{i + 1:04d}',
                defaults={
                    'event_type': 'payment_intent.succeeded',
                    'payload': {'demo': True, 'index': i},
                    'processed_at': now - timedelta(hours=i),
                },
            )

        self.stdout.write(
            f'  Comercio: {len(ctx["reservations"])} reservas, '
            f'{len(ctx["orders"])} órdenes, 10 carritos'
        )

    def _seed_analytics(self, ctx: dict) -> None:
        now = timezone.now()
        event_types = [
            EventType.VIEW, EventType.SEARCH, EventType.ADD_CART,
            EventType.AR_TRY, EventType.RESERVE,
        ]
        for i in range(10):
            customer = ctx['customers'][i % 5]
            product = ctx['products'][i]
            BrowsingEvent.objects.get_or_create(
                customer=customer,
                product=product,
                event_type=event_types[i % 5],
                occurred_at=now - timedelta(hours=i * 3),
                defaults={'query': 'camisa verano' if event_types[i % 5] == EventType.SEARCH else ''},
            )

            session, _ = ChatSession.objects.get_or_create(
                customer=customer,
                defaults={'context': {'demo': True}},
            )
            ChatMessage.objects.get_or_create(
                session=session, role=MessageRole.USER,
                content=f'¿Tienen talla M en {product.name}?',
            )
            ChatMessage.objects.get_or_create(
                session=session, role=MessageRole.ASSISTANT,
                content=f'Sí, {product.name} está disponible en varias sucursales.',
            )

            ProductEmbedding.objects.get_or_create(
                product=product,
                defaults={'embedding': random_embedding(), 'model_name': 'demo-model'},
            )

            Notification.objects.get_or_create(
                user=customer.user,
                notification_type=[
                    NotificationType.RESERVATION_CREATED,
                    NotificationType.ORDER_CONFIRMED,
                    NotificationType.LOW_STOCK_ALERT,
                ][i % 3],
                title=f'Notificación demo {i + 1}',
                defaults={
                    'message': 'Mensaje de demostración FashionStore.',
                    'reference_type': 'demo',
                    'reference_id': i + 1,
                },
            )

            ReportRequest.objects.get_or_create(
                user=ctx['admin'],
                prompt_text=f'Ventas por sucursal últimos {i + 1} días',
                defaults={
                    'interpreted_spec': {'metric': 'sales', 'days': i + 1},
                    'result': {'total': 1000 * (i + 1), 'currency': 'BOB'},
                    'status': ReportStatus.COMPLETED,
                },
            )

        self.stdout.write('  Analytics: eventos, chat, embeddings, notificaciones, reportes')

    def _print_summary(self, ctx: dict) -> None:
        self.stdout.write('')
        self.stdout.write('Resumen de datos demo:')
        self.stdout.write(f'  Sucursales: {Branch.objects.filter(code__in=[b[0] for b in BRANCHES]).count()}')
        self.stdout.write(f'  Productos:  {Product.objects.filter(name__in=[p[0] for p in PRODUCTS]).count()}')
        self.stdout.write(f'  Variantes:  {ProductVariant.objects.filter(product__in=ctx.get("products", [])).count()}')
        self.stdout.write(f'  Stock:      {BranchStock.objects.count()} registros')
        self.stdout.write(f'  Reservas:   {Reservation.objects.filter(notes__startswith="[demo]").count()}')
        self.stdout.write(f'  Órdenes:    {Order.objects.filter(customer__user__email__endswith=f"@{DEMO_DOMAIN}").count()}')

    def _print_credentials(self) -> None:
        self.stdout.write('')
        self.stdout.write(self.style.NOTICE('Credenciales demo (password para todos):'))
        self.stdout.write(f'  Password: {DEMO_PASSWORD}')
        self.stdout.write(f'  Admin:    {demo_email("admin")}')
        self.stdout.write(f'  Encargado:{demo_email("manager1")}')
        self.stdout.write(f'  Cajero:   {demo_email("cajero1")}')
        self.stdout.write(f'  Cliente:  {demo_email("cliente1")}')
        self.stdout.write(f'  Proveedor:{demo_email("proveedor")}')


def random_phone() -> str:
    import random
    return ''.join(str(random.randint(0, 9)) for _ in range(7))
