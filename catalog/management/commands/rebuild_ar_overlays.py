"""Rebuild overlay PNGs from catalog photos (seed placeholders are not garments)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from catalog.models import ARAsset
from catalog.services.ar_assets import copy_catalog_image_as_source, is_placeholder_overlay
from catalog.tasks import build_ar_asset


class Command(BaseCommand):
    help = 'Copia la foto de catálogo a source_image y corre rembg (Celery o --sync).'

    def add_arguments(self, parser):
        parser.add_argument('--product', type=int, action='append', dest='product_ids')
        parser.add_argument('--sync', action='store_true', help='Procesar en este proceso, uno a uno.')
        parser.add_argument('--force', action='store_true', help='Reprocesar aunque el PNG no sea placeholder.')

    def handle(self, *args, **options):
        qs = ARAsset.objects.select_related('product', 'color').order_by('product_id')
        product_ids = options.get('product_ids')
        if product_ids:
            qs = qs.filter(product_id__in=product_ids)

        rebuilt = 0
        skipped = 0
        for asset in qs:
            raw = b''
            if asset.file:
                asset.file.open('rb')
                raw = asset.file.read()
                asset.file.close()
            placeholder = not raw or is_placeholder_overlay(raw)
            if not placeholder and not options['force']:
                skipped += 1
                continue
            if not copy_catalog_image_as_source(asset):
                self.stderr.write(f'sin foto de catálogo: product={asset.product_id}')
                skipped += 1
                continue
            asset.status = ARAsset.PENDING
            asset.process_error = ''
            asset.save()
            if options['sync']:
                build_ar_asset(asset.id)
            else:
                build_ar_asset.delay(asset.id)
            rebuilt += 1
            self.stdout.write(f'encolado asset={asset.id} product={asset.product_id} {asset.product.name}')

        self.stdout.write(self.style.SUCCESS(f'reconstruidos={rebuilt} omitidos={skipped}'))
