# Copyright 2024 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from fastapi import Depends, Response

from maasapiserver.common.api.base import Handler, handler
from maasapiserver.common.api.models.responses.errors import (
    ConflictBodyResponse,
    NotFoundBodyResponse,
    NotFoundResponse,
    UnauthorizedBodyResponse,
    ValidationErrorBodyResponse,
)
from maasapiserver.v3.api import services
from maasapiserver.v3.api.public.models.requests.query import (
    TokenPaginationParams,
)
from maasapiserver.v3.api.public.models.requests.users import UserRequest
from maasapiserver.v3.api.public.models.responses.users import (
    SshKeyResponse,
    SshKeysListResponse,
    UserInfoResponse,
    UserResponse,
    UsersListResponse,
)
from maasapiserver.v3.auth.base import (
    check_permissions,
    get_authenticated_user,
)
from maasapiserver.v3.constants import V3_API_PREFIX
from maasservicelayer.auth.jwt import UserRole
from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.sshkeys import SshKeyClauseFactory
from maasservicelayer.db.repositories.users import UserClauseFactory
from maasservicelayer.exceptions.catalog import (
    BaseExceptionDetail,
    UnauthorizedException,
)
from maasservicelayer.exceptions.constants import (
    UNEXISTING_USER_OR_INVALID_CREDENTIALS_VIOLATION_TYPE,
)
from maasservicelayer.models.auth import AuthenticatedUser
from maasservicelayer.services import ServiceCollectionV3
from maasservicelayer.utils.date import utcnow


class UsersHandler(Handler):
    """Users API handler."""

    TAGS = ["Users"]

    def get_handlers(self):
        # The '/me' path component matches both /users/me and /users/{user_id},
        # the default dir(self) returns a handler registration order that is
        # alphabetically ordered, meaning /users/me would get handled by the
        # /users/{user_id}. Therefore we need to specify a custom registration
        # order to disambiguate these paths.
        return [
            "get_user_info",
            "list_user_sshkeys",
            "get_user_sshkey",
            "list_users",
            "get_user",
            "create_user",
            "update_user",
        ]

    @handler(
        path="/users/me",
        methods=["GET"],
        tags=TAGS,
        responses={
            200: {
                "model": UserInfoResponse,
            },
            401: {"model": UnauthorizedBodyResponse},
        },
        response_model_exclude_none=True,
        status_code=200,
        dependencies=[
            Depends(check_permissions(required_roles={UserRole.USER}))
        ],
    )
    async def get_user_info(
        self,
        authenticated_user: AuthenticatedUser | None = Depends(
            get_authenticated_user
        ),
        services: ServiceCollectionV3 = Depends(services),
    ) -> UserInfoResponse:
        assert authenticated_user is not None
        user = await services.users.get_one(
            QuerySpec(
                UserClauseFactory.with_username(authenticated_user.username)
            )
        )
        if user is None:
            raise UnauthorizedException(
                details=[
                    BaseExceptionDetail(
                        type=UNEXISTING_USER_OR_INVALID_CREDENTIALS_VIOLATION_TYPE,
                        message="The user does not exist",
                    )
                ]
            )
        return UserInfoResponse(
            id=user.id, username=user.username, is_superuser=user.is_superuser
        )

    @handler(
        path="/users",
        methods=["GET"],
        tags=TAGS,
        responses={
            200: {
                "model": UsersListResponse,
            },
            422: {"model": ValidationErrorBodyResponse},
        },
        response_model_exclude_none=True,
        status_code=200,
        dependencies=[
            Depends(check_permissions(required_roles={UserRole.USER}))
        ],
    )
    async def list_users(
        self,
        token_pagination_params: TokenPaginationParams = Depends(),
        services: ServiceCollectionV3 = Depends(services),
    ) -> UsersListResponse:
        users = await services.users.list(
            token=token_pagination_params.token,
            size=token_pagination_params.size,
        )
        return UsersListResponse(
            items=[
                UserResponse.from_model(
                    user=user,
                    self_base_hyperlink=f"{V3_API_PREFIX}/users",
                )
                for user in users.items
            ],
            next=(
                f"{V3_API_PREFIX}/users?"
                f"{TokenPaginationParams.to_href_format(users.next_token, token_pagination_params.size)}"
                if users.next_token
                else None
            ),
        )

    @handler(
        path="/users/{user_id}",
        methods=["GET"],
        tags=TAGS,
        responses={
            200: {
                "model": UserResponse,
                "headers": {
                    "ETag": {"description": "The ETag for the resource"}
                },
            },
            404: {"model": NotFoundBodyResponse},
            422: {"model": ValidationErrorBodyResponse},
        },
        response_model_exclude_none=True,
        status_code=200,
        dependencies=[
            Depends(check_permissions(required_roles={UserRole.USER}))
        ],
    )
    async def get_user(
        self,
        user_id: int,
        response: Response,
        services: ServiceCollectionV3 = Depends(services),
    ) -> UserResponse:
        user = await services.users.get_by_id(user_id)
        if not user:
            return NotFoundResponse()

        response.headers["ETag"] = user.etag()
        return UserResponse.from_model(
            user=user,
            self_base_hyperlink=f"{V3_API_PREFIX}/users",
        )

    @handler(
        path="/users",
        methods=["POST"],
        tags=TAGS,
        responses={
            201: {
                "model": UserResponse,
                "headers": {
                    "ETag": {"description": "The ETag for the resource"}
                },
            },
            409: {"model": ConflictBodyResponse},
            422: {"model": ValidationErrorBodyResponse},
        },
        status_code=201,
        response_model_exclude_none=True,
        dependencies=[
            Depends(check_permissions(required_roles={UserRole.ADMIN}))
        ],
    )
    async def create_user(
        self,
        user_request: UserRequest,
        response: Response,
        services: ServiceCollectionV3 = Depends(services),
    ) -> UserResponse:
        new_user = await services.users.create(
            user_request.to_builder().with_date_joined(utcnow()).build()
        )

        response.headers["ETag"] = new_user.etag()
        return UserResponse.from_model(
            user=new_user, self_base_hyperlink=f"{V3_API_PREFIX}/users"
        )

    @handler(
        path="/users/{user_id}",
        methods=["PUT"],
        tags=TAGS,
        responses={
            200: {
                "model": UserResponse,
                "headers": {
                    "ETag": {"description": "The ETag for the resource"}
                },
            },
            404: {"model": NotFoundBodyResponse},
            422: {"model": ValidationErrorBodyResponse},
        },
        status_code=200,
        response_model_exclude_none=True,
        dependencies=[
            Depends(check_permissions(required_roles={UserRole.ADMIN}))
        ],
    )
    async def update_user(
        self,
        user_id: int,
        user_request: UserRequest,
        response: Response,
        services: ServiceCollectionV3 = Depends(services),
    ) -> UserResponse:
        resource = user_request.to_builder().build()
        user = await services.users.update_by_id(user_id, resource)
        if not user:
            return NotFoundResponse()

        response.headers["ETag"] = user.etag()
        return UserResponse.from_model(
            user=user,
            self_base_hyperlink=f"{V3_API_PREFIX}/users",
        )

    @handler(
        path="/users/me/sshkeys",
        methods=["GET"],
        tags=TAGS,
        responses={
            200: {
                "model": SshKeysListResponse,
            },
            401: {"model": UnauthorizedBodyResponse},
        },
        response_model_exclude_none=True,
        status_code=200,
        dependencies=[
            Depends(check_permissions(required_roles={UserRole.USER}))
        ],
    )
    async def list_user_sshkeys(
        self,
        token_pagination_params: TokenPaginationParams = Depends(),
        authenticated_user: AuthenticatedUser | None = Depends(
            get_authenticated_user
        ),
        services: ServiceCollectionV3 = Depends(services),
    ) -> Response:
        assert authenticated_user is not None
        ssh_keys = await services.sshkeys.list(
            token=token_pagination_params.token,
            size=token_pagination_params.size,
            query=QuerySpec(
                where=SshKeyClauseFactory.with_user_id(authenticated_user.id)
            ),
        )

        return SshKeysListResponse(
            items=[
                SshKeyResponse.from_model(
                    ssh_key,
                    self_base_hyperlink=f"{V3_API_PREFIX}/users/me/sshkeys",
                )
                for ssh_key in ssh_keys.items
            ],
            next=(
                f"{V3_API_PREFIX}/users/me/sshkeys?"
                f"{TokenPaginationParams.to_href_format(ssh_keys.next_token, token_pagination_params.size)}"
                if ssh_keys.next_token
                else None
            ),
        )

    @handler(
        path="/users/me/sshkeys/{sshkey_id}",
        methods=["GET"],
        tags=TAGS,
        responses={
            200: {
                "model": SshKeyResponse,
            },
            401: {"model": UnauthorizedBodyResponse},
        },
        response_model_exclude_none=True,
        status_code=200,
        dependencies=[
            Depends(check_permissions(required_roles={UserRole.USER}))
        ],
    )
    async def get_user_sshkey(
        self,
        sshkey_id: int,
        response: Response,
        authenticated_user: AuthenticatedUser | None = Depends(
            get_authenticated_user
        ),
        services: ServiceCollectionV3 = Depends(services),
    ) -> Response:
        assert authenticated_user is not None
        ssh_key = await services.sshkeys.get_one(
            query=QuerySpec(
                where=SshKeyClauseFactory.and_clauses(
                    [
                        SshKeyClauseFactory.with_id(sshkey_id),
                        SshKeyClauseFactory.with_user_id(
                            authenticated_user.id
                        ),
                    ]
                )
            ),
        )

        if not ssh_key:
            return NotFoundResponse()

        response.headers["ETag"] = ssh_key.etag()

        return SshKeyResponse.from_model(
            ssh_key,
            self_base_hyperlink=f"{V3_API_PREFIX}/users/me/sshkeys",
        )
