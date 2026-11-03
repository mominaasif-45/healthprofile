from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        from . import openapi  # noqa: F401  (registers the Swagger auth scheme for member cookies)
