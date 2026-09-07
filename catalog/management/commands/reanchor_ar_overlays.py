"""Re-estimate anchor_config from existing overlay PNGs (no rembg, instant)."""

from __future__ import annotations

from io import BytesIO

from django.core.management.base import BaseCommand
from PIL import Image

from catalog.models import ARAsset
from catalog.services.ar_assets import estimate_anchors


class Command(BaseCommand):
    help = (
        'Re-runs estimate_anchors() on every READY overlay PNG and updates '
        'anchor_config.  Does NOT call rembg – uses the already-processed file. '
        'Use --force to also update assets with auto_calibrated=False (manual overrides).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--product', type=int, action='append', dest='product_ids',
            help='Limit to specific product IDs (repeatable).',
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Overwrite even manually-calibrated anchors (auto_calibrated=False).',
        )

    def handle(self, *args, **options):
        qs = (
            ARAsset.objects
            .filter(status=ARAsset.READY, is_active=True)
            .exclude(file='')
            .select_related('product', 'color')
            .order_by('product_id')
        )
        product_ids = options.get('product_ids')
        if product_ids:
            qs = qs.filter(product_id__in=product_ids)

        updated = skipped = errors = 0
        for asset in qs:
            ac = asset.anchor_config or {}
            if not options['force'] and ac.get('auto_calibrated') is False:
                self.stderr.write(
                    f'skip {asset.id} product={asset.product_id} '
                    f'(manual override; use --force to rewrite)'
                )
                skipped += 1
                continue

            try:
                asset.file.open('rb')
                png_bytes = asset.file.read()
                asset.file.close()
            except Exception as exc:
                self.stderr.write(f'error reading file for asset {asset.id}: {exc}')
                errors += 1
                continue

            try:
                img = Image.open(BytesIO(png_bytes)).convert('RGBA')
                new_anchor = estimate_anchors(img)
            except Exception as exc:
                self.stderr.write(f'error estimating anchors for asset {asset.id}: {exc}')
                errors += 1
                continue

            # Merge: preserve manual fields (size_scale, width_factor) if present
            merged = dict(new_anchor)
            if ac.get('auto_calibrated') is False:
                for key in ('width_factor', 'size_scale'):
                    if key in ac:
                        merged[key] = ac[key]
            merged['auto_calibrated'] = True

            asset.anchor_config = merged
            asset.save(update_fields=['anchor_config'])
            updated += 1

            oy = new_anchor['offset_y']
            self.stdout.write(
                f'updated asset={asset.id} product={asset.product_id} '
                f'{asset.product.name}  offset_y={oy:+.3f}'
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Done: updated={updated}  skipped={skipped}  errors={errors}'
            )
        )
