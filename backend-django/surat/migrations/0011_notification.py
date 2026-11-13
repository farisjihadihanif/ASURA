from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0002_user_email'),
        ('surat', '0010_fix_chatmessage_sender_type'),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(choices=[
                    ('APPROVAL_REQUIRED', 'Approval required'),
                    ('REVISION_REQUIRED', 'Revision required'),
                    ('REJECTED', 'Rejected'),
                    ('APPROVED', 'Approved'),
                    ('SENT', 'Sent'),
                    ('DIRECT_DELIVERY', 'Direct delivery'),
                ], max_length=40)),
                ('title', models.CharField(max_length=255)),
                ('body', models.TextField()),
                ('is_read', models.BooleanField(db_index=True, default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('surat_request', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notifications', to='surat.suratrequest')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='accounts.user')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['user', 'is_read', '-created_at'], name='surat_notif_user_id_6c0a3b_idx'),
        ),
    ]
