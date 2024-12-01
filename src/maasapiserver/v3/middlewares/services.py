from typing import Awaitable, Callable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp
from temporalio.client import Client

from maasapiserver.v3.constants import V3_API_PREFIX
from maasservicelayer.services import CacheForServices, ServiceCollectionV3


async def services(
    request: Request,
) -> ServiceCollectionV3:
    """Dependency to return the services collection."""
    return request.state.services


class ServicesMiddleware(BaseHTTPMiddleware):
    """Injects the V3 services in the request context if the request targets a v3 endpoint."""

    def __init__(
        self,
        app: ASGIApp,
        cache: CacheForServices,
        temporal: Optional[Client] = None,
    ):
        super().__init__(app)
        self.temporal = temporal
        self.services_cache = cache

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Just pass through the request if it's not a V3 endpoint. The other V2 endpoints have another authentication
        # architecture/mechanism.
        if not request.url.path.startswith(V3_API_PREFIX):
            return await call_next(request)

        services = await ServiceCollectionV3.produce(
            request.state.context.get_connection(),
            cache=self.services_cache,
            temporal=self.temporal,
        )
        request.state.services = services
        return await call_next(request)
