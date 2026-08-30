"""Demo seed helpers for FashionStore."""
from __future__ import annotations

import random
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

DEMO_DOMAIN = 'fashionstore.demo'
DEMO_PASSWORD = 'Demo1234!'

CITIES = [
    ('Santa Cruz de la Sierra', 'Santa Cruz'),
    ('La Paz', 'La Paz'),
    ('El Alto', 'La Paz'),
    ('Cochabamba', 'Cochabamba'),
    ('Sucre', 'Chuquisaca'),
    ('Tarija', 'Tarija'),
    ('Oruro', 'Oruro'),
    ('Potosí', 'Potosí'),
    ('Trinidad', 'Beni'),
    ('Cobija', 'Pando'),
]

BRANCHES = [
    ('SCZ-01', 'FashionStore Equipetrol', 0, 'Av. San Martín 1234'),
    ('SCZ-02', 'FashionStore Las Brisas', 0, 'Av. Cristo Redentor 456'),
    ('LPZ-01', 'FashionStore Sopocachi', 1, 'Calle 6 de Agosto 789'),
    ('LPZ-02', 'FashionStore Zona Sur', 1, 'Av. Ballivián 321'),
    ('ALT-01', 'FashionStore El Alto Centro', 2, 'Av. Juan Pablo II 100'),
    ('CBB-01', 'FashionStore Queru Queru', 3, 'Av. América 555'),
    ('CBB-02', 'FashionStore Cala Cala', 3, 'Av. Pando 888'),
    ('SRE-01', 'FashionStore Centro Histórico', 4, 'Plaza 25 de Mayo 50'),
    ('TJA-01', 'FashionStore Comercial', 5, 'Av. Las Américas 200'),
    ('ORU-01', 'FashionStore Feria Barrio Lindo', 6, 'Av. 6 de Octubre 300'),
]

CATEGORIES = [
    ('Camisas', None),
    ('Pantalones', None),
    ('Vestidos', None),
    ('Faldas', None),
    ('Chaquetas', None),
    ('Poleras', None),
    ('Shorts', None),
    ('Calzado', None),
    ('Accesorios', None),
    ('Ropa Interior', None),
]

BRANDS = [
    'Zara Style BO', 'Andes Wear', 'Altiplano Fashion', 'Tropicana',
    'Urban Fit', 'Classic Man', 'Luna Rosa', 'Sportiva', 'Denim Co', 'Kids Moda',
]

COLORS = [
    ('Negro', '#000000'), ('Blanco', '#FFFFFF'), ('Azul Marino', '#1B2A4E'),
    ('Rojo', '#C0392B'), ('Verde Oliva', '#556B2F'), ('Beige', '#D2B48C'),
    ('Gris Melange', '#808080'), ('Rosa Palo', '#F4C2C2'), ('Mostaza', '#E1AD01'),
    ('Borgoña', '#800020'),
]

SEASONS = [
    ('Primavera-Verano 2025', 'PV25', 'SPRING_SUMMER', date(2025, 9, 1), date(2026, 2, 28)),
    ('Otoño-Invierno 2025', 'OI25', 'AUTUMN_WINTER', date(2025, 3, 1), date(2025, 8, 31)),
    ('Escolar 2026', 'ESC26', 'SCHOOL', date(2026, 1, 15), date(2026, 3, 15)),
    ('Promo San Valentín', 'VAL26', 'PROMO', date(2026, 2, 1), date(2026, 2, 28)),
    ('Nueva Colección Urban', 'NC26', 'NEW_COLLECTION', date(2026, 3, 1), date(2026, 8, 31)),
    ('Primavera-Verano 2026', 'PV26', 'SPRING_SUMMER', date(2026, 9, 1), date(2027, 2, 28)),
    ('Otoño-Invierno 2026', 'OI26', 'AUTUMN_WINTER', date(2026, 3, 1), date(2026, 8, 31)),
    ('Black Friday 2025', 'BF25', 'PROMO', date(2025, 11, 20), date(2025, 11, 30)),
    ('Colección Festiva', 'FES25', 'PROMO', date(2025, 12, 1), date(2025, 12, 31)),
    ('Línea Premium 2026', 'PRE26', 'NEW_COLLECTION', date(2026, 1, 1), date(2026, 12, 31)),
]

PRODUCTS = [
    ('Camisa Oxford Slim', 'MALE', Decimal('289.00'), 0, 0),
    ('Pantalón Chino Classic', 'MALE', Decimal('320.00'), 1, 1),
    ('Vestido Floral Midi', 'FEMALE', Decimal('450.00'), 2, 2),
    ('Falda Plisada Escolar', 'KIDS', Decimal('180.00'), 3, 2),
    ('Chaqueta Denim', 'UNISEX', Decimal('390.00'), 4, 3),
    ('Polera Básica Algodón', 'UNISEX', Decimal('120.00'), 5, 4),
    ('Short Deportivo', 'MALE', Decimal('150.00'), 6, 5),
    ('Zapatillas Urban Run', 'UNISEX', Decimal('520.00'), 7, 6),
    ('Cinturón Cuero', 'MALE', Decimal('95.00'), 8, 7),
    ('Pack Ropa Interior', 'MALE', Decimal('110.00'), 9, 8),
]

SUPPLIERS = [
    ('Textiles del Sur SRL', 'Textiles del Sur', '100000001'),
    ('Confecciones Altiplano SA', 'Altiplano', '100000002'),
    ('Importadora Moda Latina', 'Moda Latina', '100000003'),
    ('Denim Factory BO', 'Denim Factory', '100000004'),
    ('Calzados Paceños', 'Calzados LPZ', '100000005'),
    ('Accesorios Chic', 'Chic Acc', '100000006'),
    ('Kids Fashion Bolivia', 'Kids Fashion', '100000007'),
    ('Sport Wear Andino', 'Sport Andino', '100000008'),
    ('Premium Garments', 'Premium G', '100000009'),
    ('Eco Textil Bolivia', 'Eco Textil', '100000010'),
]


def placeholder_file(prefix: str) -> ContentFile:
    """Minimal valid PNG (1x1) when Pillow is unavailable."""
    try:
        from PIL import Image

        buffer = BytesIO()
        Image.new('RGB', (400, 400), color=(220, 220, 220)).save(buffer, format='PNG')
        return ContentFile(buffer.getvalue(), name=f'{prefix}.png')
    except ImportError:
        png = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
            b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc``\x00\x00'
            b'\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        return ContentFile(png, name=f'{prefix}.png')


def demo_email(local_part: str) -> str:
    return f'{local_part}@{DEMO_DOMAIN}'


def random_embedding(dim: int = 768) -> list[float]:
    return [round(random.uniform(-1, 1), 6) for _ in range(dim)]
