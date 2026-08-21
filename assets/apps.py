from django.apps import AppConfig
from django.db.backends.signals import connection_created


def configure_sqlite_connection(sender, connection, **kwargs):
    if connection.vendor == 'sqlite':
        cursor = connection.cursor()
        cursor.execute('PRAGMA journal_mode = WAL;')
        cursor.execute('PRAGMA busy_timeout = 15000;')


class AssetsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'assets'

    def ready(self):
        connection_created.connect(configure_sqlite_connection)
