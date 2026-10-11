from django.apps import AppConfig


class ConsultationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sessions'
    label = 'consultations'
    verbose_name = 'Consultation sessions'
