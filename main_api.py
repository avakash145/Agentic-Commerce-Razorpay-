import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Expose 'app' and 'application' for Uvicorn / ASGI servers
application = get_asgi_application()
app = application
