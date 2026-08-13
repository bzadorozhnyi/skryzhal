import templates.endpoints.v1.routes.create_template  # noqa: F401
import templates.endpoints.v1.routes.create_upload_url  # noqa: F401
from templates.endpoints.v1.routes.router import router as template_v1_router

__all__ = ["template_v1_router"]
