from django.db import migrations, models
import django.db.models.deletion
class Migration(migrations.Migration):
    dependencies = [
        ('surat', '0011_notification'),
    ]
    operations = [
        migrations.AddField(
            model_name='suratrequest',
            name='chat_thread',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='surat_requests',
                to='surat.chatthread',
            ),
        ),
        migrations.AddField(
            model_name='suratrequest',
            name='signer_nama_override',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='suratrequest',
            name='signer_nip_override',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='suratrequest',
            name='manual_signature_data_uri',
            field=models.TextField(blank=True, null=True),
        ),
    ]
