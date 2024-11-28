#  Copyright 2024 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

from unittest.mock import Mock

from fastapi.exceptions import RequestValidationError
from httpx import AsyncClient
import pytest

from maasapiserver.common.api.models.responses.errors import ErrorBodyResponse
from maasapiserver.v3.api.public.models.requests.query import (
    TokenPaginationParams,
)
from maasapiserver.v3.api.public.models.responses.reservedips import (
    ReservedIPsListResponse,
)
from maasapiserver.v3.constants import V3_API_PREFIX
from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.reservedips import (
    ReservedIPsClauseFactory,
)
from maasservicelayer.models.base import ListResult
from maasservicelayer.models.reservedips import ReservedIP
from maasservicelayer.services import ReservedIPsService, ServiceCollectionV3
from maasservicelayer.utils.date import utcnow
from tests.maasapiserver.v3.api.public.handlers.base import (
    ApiCommonTests,
    Endpoint,
)

TEST_RESERVEDIP = ReservedIP(
    id=1,
    created=utcnow(),
    updated=utcnow(),
    ip="10.0.0.1",
    mac_address="01:02:03:04:05:06",
    comment="test_comment",
    subnet_id=1,
)

TEST_RESERVEDIP_2 = ReservedIP(
    id=2,
    created=utcnow(),
    updated=utcnow(),
    ip="10.0.0.2",
    mac_address="02:02:03:04:05:06",
    comment="test_comment_2",
    subnet_id=1,
)


class TestReservedIPsApi(ApiCommonTests):
    BASE_PATH = f"{V3_API_PREFIX}/fabrics/1/vlans/1/subnets/1/reserved_ips"

    @pytest.fixture
    def user_endpoints(self) -> list[Endpoint]:
        return [
            Endpoint(method="GET", path=self.BASE_PATH),
            Endpoint(method="GET", path=f"{self.BASE_PATH}/1"),
        ]

    @pytest.fixture
    def admin_endpoints(self) -> list[Endpoint]:
        return []

    async def test_list_no_other_page(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_user: AsyncClient,
    ) -> None:
        services_mock.reservedips = Mock(ReservedIPsService)
        services_mock.reservedips.list.return_value = ListResult[ReservedIP](
            items=[TEST_RESERVEDIP], next_token=None
        )
        response = await mocked_api_client_user.get(f"{self.BASE_PATH}?size=1")
        assert response.status_code == 200
        reservedips_response = ReservedIPsListResponse(**response.json())
        assert len(reservedips_response.items) == 1
        assert reservedips_response.next is None
        services_mock.reservedips.list.assert_called_once_with(
            token=None,
            size=1,
            query=QuerySpec(
                where=ReservedIPsClauseFactory.and_clauses(
                    [
                        ReservedIPsClauseFactory.with_fabric_id(1),
                        ReservedIPsClauseFactory.with_subnet_id(1),
                        ReservedIPsClauseFactory.with_vlan_id(1),
                    ]
                )
            ),
        )

    async def test_list_other_page(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_user: AsyncClient,
    ) -> None:
        services_mock.reservedips = Mock(ReservedIPsService)
        services_mock.reservedips.list.return_value = ListResult[ReservedIP](
            items=[TEST_RESERVEDIP_2], next_token=str(TEST_RESERVEDIP.id)
        )
        response = await mocked_api_client_user.get(f"{self.BASE_PATH}?size=1")
        assert response.status_code == 200
        reservedips_response = ReservedIPsListResponse(**response.json())
        assert len(reservedips_response.items) == 1
        assert (
            reservedips_response.next
            == f"{self.BASE_PATH}?{TokenPaginationParams.to_href_format(token=str(TEST_RESERVEDIP.id), size='1')}"
        )
        services_mock.reservedips.list.assert_called_once_with(
            token=None,
            size=1,
            query=QuerySpec(
                where=ReservedIPsClauseFactory.and_clauses(
                    [
                        ReservedIPsClauseFactory.with_fabric_id(1),
                        ReservedIPsClauseFactory.with_subnet_id(1),
                        ReservedIPsClauseFactory.with_vlan_id(1),
                    ]
                )
            ),
        )

    async def test_get_200(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_user: AsyncClient,
    ) -> None:
        services_mock.reservedips = Mock(ReservedIPsService)
        services_mock.reservedips.get_one.return_value = TEST_RESERVEDIP
        response = await mocked_api_client_user.get(
            f"{self.BASE_PATH}/{TEST_RESERVEDIP.id}"
        )
        assert response.status_code == 200
        assert len(response.headers["ETag"]) > 0
        assert response.json() == {
            "kind": "ReservedIP",
            "id": TEST_RESERVEDIP.id,
            "ip": "10.0.0.1",
            "mac_address": "01:02:03:04:05:06",
            "comment": "test_comment",
            "subnet_id": 1,
            # TODO: FastAPI response_model_exclude_none not working. We need to fix this before making the api public
            "_embedded": None,
            "_links": {
                "self": {"href": f"{self.BASE_PATH}/{TEST_RESERVEDIP.id}"}
            },
        }
        services_mock.reservedips.get_one.assert_called_once_with(
            query=QuerySpec(
                ReservedIPsClauseFactory.and_clauses(
                    [
                        ReservedIPsClauseFactory.with_id(TEST_RESERVEDIP.id),
                        ReservedIPsClauseFactory.with_fabric_id(1),
                        ReservedIPsClauseFactory.with_subnet_id(1),
                        ReservedIPsClauseFactory.with_vlan_id(1),
                    ]
                )
            )
        )

    async def test_get_404(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_user: AsyncClient,
    ) -> None:
        services_mock.reservedips = Mock(ReservedIPsService)
        services_mock.reservedips.get_one.return_value = None
        response = await mocked_api_client_user.get(f"{self.BASE_PATH}/100")
        assert response.status_code == 404
        assert "ETag" not in response.headers

        error_response = ErrorBodyResponse(**response.json())
        assert error_response.kind == "Error"
        assert error_response.code == 404

    async def test_get_422(
        self,
        services_mock: ServiceCollectionV3,
        mocked_api_client_user: AsyncClient,
    ) -> None:
        services_mock.reservedips = Mock(ReservedIPsService)
        services_mock.reservedips.get_one.return_value = (
            RequestValidationError(errors=[])
        )
        response = await mocked_api_client_user.get(f"{self.BASE_PATH}/xyz")
        assert response.status_code == 422
        assert "ETag" not in response.headers

        error_response = ErrorBodyResponse(**response.json())
        assert error_response.kind == "Error"
        assert error_response.code == 422