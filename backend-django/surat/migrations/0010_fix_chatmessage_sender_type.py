from django.db import migrations


def fix_sender_type(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'surat_chatmessage' AND column_name = 'sender_type'
                ) THEN
                    ALTER TABLE surat_chatmessage ALTER COLUMN sender_type DROP NOT NULL;
                    ALTER TABLE surat_chatmessage ALTER COLUMN sender_type SET DEFAULT 'user';
                END IF;
            END $$;
        """)

class Migration(migrations.Migration):

    dependencies = [
        ('surat', '0009_remove_suratrequest_target_email_destination_and_more'),
    ]

    operations = [
        migrations.RunPython(fix_sender_type, migrations.RunPython.noop),
    ]
