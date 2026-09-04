from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='arasset',
            name='height',
            field=models.PositiveIntegerField(default=0, verbose_name='Alto'),
        ),
        migrations.AddField(
            model_name='arasset',
            name='process_error',
            field=models.CharField(blank=True, max_length=300, verbose_name='Error de proceso'),
        ),
        migrations.AddField(
            model_name='arasset',
            name='status',
            field=models.CharField(
                choices=[
                    ('PROCESSING', 'Procesando'),
                    ('READY', 'Listo'),
                    ('FAILED', 'Fallido'),
                ],
                db_index=True,
                default='READY',
                max_length=20,
                verbose_name='Estado',
            ),
        ),
        migrations.AddField(
            model_name='arasset',
            name='width',
            field=models.PositiveIntegerField(default=0, verbose_name='Ancho'),
        ),
        migrations.AlterField(
            model_name='arasset',
            name='kind',
            field=models.CharField(
                choices=[('OVERLAY_2D', 'Overlay 2D'), ('MODEL_3D', 'Modelo 3D')],
                default='OVERLAY_2D',
                max_length=20,
                verbose_name='Tipo',
            ),
        ),
    ]
