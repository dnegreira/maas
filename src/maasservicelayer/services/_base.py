#  Copyright 2023-2024 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

from abc import ABC
from dataclasses import dataclass
from typing import Generic, List, TypeVar

from maasservicelayer.context import Context
from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.base import (
    BaseRepository,
    CreateOrUpdateResource,
)
from maasservicelayer.exceptions.catalog import (
    BaseExceptionDetail,
    NotFoundException,
    PreconditionFailedException,
)
from maasservicelayer.exceptions.constants import (
    ETAG_PRECONDITION_VIOLATION_TYPE,
    UNEXISTING_RESOURCE_VIOLATION_TYPE,
)
from maasservicelayer.models.base import ListResult, MaasBaseModel


@dataclass(slots=True)
class ServiceCache(ABC):
    """Base cache for a service."""

    def clear(self):
        for field in list(self.__slots__):
            self.__setattr__(field, None)

    async def close(self):
        """Shutdown operations to be performed when destroying the cache."""


class Service(ABC):
    """Base class for services."""

    def __init__(self, context: Context, cache: ServiceCache | None = None):
        self.context = context
        self.cache = cache

    @staticmethod
    def build_cache_object() -> ServiceCache:
        """Return the cache specific to the service."""
        raise NotImplementedError(
            "build_cache_object must be overridden in the service."
        )

    @staticmethod
    def from_cache_or_execute(attr: str):
        """Decorator to search `attr` through the cache before executing the method.

        The logic is as follows:
            - you have a Service and a related ServiceCache
            - in the ServiceCache you must define all the values that you want
                to cache as an attribute with a type and that defaults to None.
            - wrap the method in the Service that is responsible to retrieve that value
            - now the ServiceCache will be checked before executing the Service method
                and if there is a value, it will return it otherwise it will execute
                the method, populate the ServiceCache and return that value.

        Note: This decorator doesn't take into account *args and **kwargs, so don't
            expect it to cache different values for different function calls.
        """

        def inner_decorator(fn):
            async def wrapped(self, *args, **kwargs):
                if self.cache is None:
                    return await fn(self, *args, **kwargs)
                if self.cache.__getattribute__(attr) is None:  # Cache miss
                    value = await fn(self, *args, **kwargs)
                    self.cache.__setattr__(attr, value)
                return self.cache.__getattribute__(attr)

            return wrapped

        return inner_decorator


T = TypeVar("T", bound=MaasBaseModel)
R = TypeVar("R", bound=BaseRepository)


class BaseService(Service, ABC, Generic[T, R]):
    """
    The base class for all the services that have a BaseRepository.
    The `get`, `get_one`, `get_by_id` and all the other methods of the BaseRepository are just pass-through methods in the Service
    most of the time. In case the service needs to put additional business logic in these methods, it needs to override them.
    """

    def __init__(
        self,
        context: Context,
        repository: R,
        cache: ServiceCache | None = None,
    ):
        super().__init__(context, cache)
        self.repository = repository

    def etag_check(self, model: T, etag_if_match: str | None = None):
        """
        Raises a PreconditionFailedException if the etag does not match.
        """
        if etag_if_match is not None and model.etag() != etag_if_match:
            raise PreconditionFailedException(
                details=[
                    BaseExceptionDetail(
                        type=ETAG_PRECONDITION_VIOLATION_TYPE,
                        message=f"The resource etag '{model.etag()}' did not match '{etag_if_match}'.",
                    )
                ]
            )

    async def get_many(self, query: QuerySpec) -> List[T]:
        return await self.repository.get_many(query=query)

    async def get_one(self, query: QuerySpec) -> T | None:
        return await self.repository.get_one(query=query)

    async def get_by_id(self, id: int) -> T | None:
        return await self.repository.get_by_id(id=id)

    async def post_create_hook(self, resource: T) -> None:
        return None

    async def create(self, resource: CreateOrUpdateResource) -> T:
        created_resource = await self.repository.create(resource=resource)
        await self.post_create_hook(created_resource)
        return created_resource

    async def list(
        self, token: str | None, size: int, query: QuerySpec | None = None
    ) -> ListResult[T]:
        return await self.repository.list(token=token, size=size, query=query)

    async def post_update_many_hook(self, resources: List[T]) -> None:
        """
        Override this function in your Service to perform post-hooks with the updated objects
        """
        return None

    async def update_many(
        self, query: QuerySpec, resource: CreateOrUpdateResource
    ) -> List[T]:
        updated_resources = await self.repository.update_many(
            query=query, resource=resource
        )
        await self.post_update_many_hook(updated_resources)
        return updated_resources

    async def post_update_hook(
        self, old_resource: T, updated_resource: T
    ) -> None:
        """
        Override this function in your Service to perform post-hooks with the updated object
        """
        return None

    async def update_one(
        self,
        query: QuerySpec,
        resource: CreateOrUpdateResource,
        etag_if_match: str | None = None,
    ) -> T:
        existing_resource = await self.get_one(query=query)
        return await self._update_resource(
            existing_resource, resource, etag_if_match
        )

    async def update_by_id(
        self,
        id: int,
        resource: CreateOrUpdateResource,
        etag_if_match: str | None = None,
    ) -> T:
        existing_resource = await self.get_by_id(id=id)
        return await self._update_resource(
            existing_resource, resource, etag_if_match
        )

    async def _update_resource(
        self,
        existing_resource: T | None,
        resource: CreateOrUpdateResource,
        etag_if_match: str | None = None,
    ) -> T:
        if not existing_resource:
            raise NotFoundException(
                details=[
                    BaseExceptionDetail(
                        type=UNEXISTING_RESOURCE_VIOLATION_TYPE,
                        message="Resource with such identifiers does not exist.",
                    )
                ]
            )

        self.etag_check(existing_resource, etag_if_match)
        updated_resource = await self.repository.update_by_id(
            id=existing_resource.id, resource=resource
        )
        await self.post_update_hook(existing_resource, updated_resource)
        return updated_resource

    async def post_delete_many_hook(self, resources: List[T]) -> None:
        """
        Override this function in your Service to perform post-hooks with the deleted objects
        """
        return None

    async def delete_many(self, query: QuerySpec) -> List[T]:
        resources = await self.repository.delete_many(query=query)
        await self.post_delete_many_hook(resources)
        return resources

    async def pre_delete_hook(self, resource_to_be_deleted: T) -> None:
        """
        Override this function in your Service to perform pre-hooks with the object to be deleted.
        This can be used for example to implement extra checks on the objects to be deleted.
        """
        return None

    async def post_delete_hook(self, resource: T) -> None:
        """
        Override this function in your Service to perform post-hooks with the deleted object.
        This is called only if the delete query matched a target, so you are sure the `resource` is not None.
        """
        return None

    async def delete_one(
        self, query: QuerySpec, etag_if_match: str | None = None
    ) -> T | None:
        resource = await self.get_one(query=query)
        return await self._delete_resource(resource, etag_if_match)

    async def delete_by_id(
        self, id: int, etag_if_match: str | None = None
    ) -> T | None:
        resource = await self.get_by_id(id=id)
        return await self._delete_resource(resource, etag_if_match)

    async def _delete_resource(
        self, resource: T | None, etag_if_match: str | None = None
    ) -> T | None:
        if not resource:
            return None

        self.etag_check(resource, etag_if_match)
        await self.pre_delete_hook(resource)

        deleted_resource = await self.repository.delete_by_id(id=resource.id)
        if deleted_resource:
            await self.post_delete_hook(deleted_resource)
        return deleted_resource
