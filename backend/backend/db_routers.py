class TesfaReadOnlyRouter:
    """Keeps Django's migrations off Tesfa AI's database; it is only read with raw SQL."""

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if db == 'tesfa':
            return False
        return None
