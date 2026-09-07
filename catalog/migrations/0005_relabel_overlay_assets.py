from io import BytesIO

from django.db import migrations


def relabel_image_overlays(apps, schema_editor):
    ARAsset = apps.get_model('catalog', 'ARAsset')
    from core.ar import default_anchor_config

    for asset in ARAsset.objects.all():
        name = (asset.file.name if asset.file else '') or ''
        ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
        is_image = ext in {'png', 'jpg', 'jpeg', 'webp'}
        if not is_image:
            continue

        updates = []
        if asset.kind != 'OVERLAY_2D':
            asset.kind = 'OVERLAY_2D'
            updates.append('kind')
        if not asset.anchor_config:
            asset.anchor_config = default_anchor_config(auto_calibrated=True)
            updates.append('anchor_config')
        if asset.status != 'READY' and asset.file:
            asset.status = 'READY'
            updates.append('status')
        if (not asset.width or not asset.height) and asset.file:
            try:
                from PIL import Image

                asset.file.open('rb')
                img = Image.open(BytesIO(asset.file.read()))
                asset.file.close()
                asset.width = img.width
                asset.height = img.height
                updates.extend(['width', 'height'])
            except Exception:
                pass
        if updates:
            asset.save(update_fields=[*updates, 'updated_at'])


def noop(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0004_arasset_async_pipeline'),
    ]

    operations = [
        migrations.RunPython(relabel_image_overlays, noop),
    ]
