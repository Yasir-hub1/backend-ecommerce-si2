from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0003_arasset_processing'),
    ]

    operations = [
        migrations.AddField(
            model_name='arasset',
            name='source_image',
            field=models.ImageField(
                blank=True,
                help_text='Archivo que subió el administrador, antes de rembg.',
                upload_to='ar/source/',
                verbose_name='Imagen origen',
            ),
        ),
        migrations.AlterField(
            model_name='arasset',
            name='file',
            field=models.FileField(
                blank=True,
                null=True,
                upload_to='ar_assets/',
                verbose_name='Archivo procesado',
            ),
        ),
        migrations.AlterField(
            model_name='arasset',
            name='process_error',
            field=models.TextField(blank=True, verbose_name='Error de proceso'),
        ),
        migrations.AlterField(
            model_name='arasset',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Pendiente'),
                    ('PROCESSING', 'Procesando'),
                    ('READY', 'Listo'),
                    ('FAILED', 'Falló'),
                ],
                db_index=True,
                default='PENDING',
                max_length=20,
                verbose_name='Estado',
            ),
        ),
    ]
