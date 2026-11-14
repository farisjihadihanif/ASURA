from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Reset database lokal tanpa menghapus file SQLite, lalu migrasi dan seed.'

    def handle(self, *args, **options):
        call_command('flush', interactive=False, verbosity=0)
        call_command('migrate', verbosity=0)
        call_command('seed_master_data')
        call_command('seed_surat')
        self.stdout.write(self.style.SUCCESS('Database lokal berhasil di-reset, dimigrasi, dan di-seed.'))
