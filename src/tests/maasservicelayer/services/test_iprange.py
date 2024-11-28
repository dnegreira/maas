from ipaddress import IPv4Address
from unittest.mock import Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from maascommon.enums.ipaddress import IpAddressType
from maascommon.enums.ipranges import IPRangeType
from maascommon.workflows.dhcp import (
    CONFIGURE_DHCP_WORKFLOW_NAME,
    merge_configure_dhcp_param,
)
from maasservicelayer.context import Context
from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.dhcpsnippets import (
    DhcpSnippetsClauseFactory,
)
from maasservicelayer.db.repositories.ipranges import (
    IPRangeResourceBuilder,
    IPRangesRepository,
)
from maasservicelayer.models.ipranges import IPRange
from maasservicelayer.models.staticipaddress import StaticIPAddress
from maasservicelayer.models.subnets import Subnet
from maasservicelayer.services.dhcpsnippets import DhcpSnippetsService
from maasservicelayer.services.ipranges import IPRangesService
from maasservicelayer.services.temporal import TemporalService
from maasservicelayer.utils.date import utcnow
from maastemporalworker.workflow.dhcp import ConfigureDHCPParam


@pytest.mark.asyncio
class TestIPRangesService:
    async def test_get_dynamic_range_for_ip(self) -> None:
        subnet = Subnet(
            id=1,
            cidr="10.0.0.0/24",
            created=utcnow(),
            updated=utcnow(),
            rdns_mode=1,
            allow_dns=True,
            allow_proxy=True,
            active_discovery=True,
            managed=True,
            vlan_id=1,
            disabled_boot_architectures=[],
        )
        sip = StaticIPAddress(
            id=2,
            ip="10.0.0.1",
            subnet_id=subnet.id,
            lease_time=600,
            created=utcnow(),
            updated=utcnow(),
            alloc_type=IpAddressType.DISCOVERED,
        )

        mock_ipranges_repository = Mock(IPRangesRepository)

        ipranges_service = IPRangesService(
            Mock(AsyncConnection),
            Mock(TemporalService),
            Mock(DhcpSnippetsService),
            ipranges_repository=mock_ipranges_repository,
        )

        await ipranges_service.get_dynamic_range_for_ip(subnet, sip.ip)

        mock_ipranges_repository.get_dynamic_range_for_ip.assert_called_once_with(
            subnet, IPv4Address("10.0.0.1")
        )

    async def test_create(self):
        iprange = IPRange(
            id=1,
            type=IPRangeType.DYNAMIC,
            start_ip="10.0.0.1",
            end_ip="10.0.0.20",
            subnet_id=2,
            created=utcnow(),
            updated=utcnow(),
        )

        mock_ipranges_repository = Mock(IPRangesRepository)
        mock_ipranges_repository.create.return_value = iprange

        mock_temporal = Mock(TemporalService)

        ipranges_service = IPRangesService(
            context=Context(),
            temporal_service=mock_temporal,
            dhcpsnippets_service=Mock(DhcpSnippetsService),
            ipranges_repository=mock_ipranges_repository,
        )

        resource = (
            IPRangeResourceBuilder()
            .with_type(iprange.type)
            .with_start_ip(iprange.start_ip)
            .with_end_ip(iprange.end_ip)
            .with_created(iprange.created)
            .with_updated(iprange.updated)
            .build()
        )

        await ipranges_service.create(resource)

        mock_ipranges_repository.create.assert_called_once_with(resource)
        mock_temporal.register_or_update_workflow_call.assert_called_once_with(
            CONFIGURE_DHCP_WORKFLOW_NAME,
            ConfigureDHCPParam(ip_range_ids=[iprange.id]),
            parameter_merge_func=merge_configure_dhcp_param,
            wait=False,
        )

    async def test_update(self):
        iprange = IPRange(
            id=1,
            type=IPRangeType.DYNAMIC,
            start_ip="10.0.0.1",
            end_ip="10.0.0.20",
            subnet_id=2,
            created=utcnow(),
            updated=utcnow(),
        )

        mock_ipranges_repository = Mock(IPRangesRepository)
        mock_ipranges_repository.update_by_id.return_value = iprange

        mock_temporal = Mock(TemporalService)

        ipranges_service = IPRangesService(
            context=Context(),
            temporal_service=mock_temporal,
            dhcpsnippets_service=Mock(DhcpSnippetsService),
            ipranges_repository=mock_ipranges_repository,
        )

        resource = (
            IPRangeResourceBuilder()
            .with_type(iprange.type)
            .with_start_ip(iprange.start_ip)
            .with_end_ip(iprange.end_ip)
            .with_created(iprange.created)
            .with_updated(iprange.updated)
            .build()
        )

        await ipranges_service.update_by_id(iprange.id, resource)

        mock_ipranges_repository.update_by_id.assert_called_once_with(
            iprange.id, resource
        )

        mock_temporal.register_or_update_workflow_call.assert_called_once_with(
            CONFIGURE_DHCP_WORKFLOW_NAME,
            ConfigureDHCPParam(ip_range_ids=[iprange.id]),
            parameter_merge_func=merge_configure_dhcp_param,
            wait=False,
        )

    async def test_delete(self):
        iprange = IPRange(
            id=1,
            type=IPRangeType.DYNAMIC,
            start_ip="10.0.0.1",
            end_ip="10.0.0.20",
            subnet_id=2,
            created=utcnow(),
            updated=utcnow(),
        )

        mock_ipranges_repository = Mock(IPRangesRepository)
        mock_ipranges_repository.delete_by_id.return_value = iprange

        mock_temporal = Mock(TemporalService)
        dhcpsnippets_service_mock = Mock(DhcpSnippetsService)

        ipranges_service = IPRangesService(
            context=Context(),
            temporal_service=mock_temporal,
            dhcpsnippets_service=dhcpsnippets_service_mock,
            ipranges_repository=mock_ipranges_repository,
        )

        await ipranges_service.delete_by_id(iprange.id)

        mock_ipranges_repository.delete_by_id.assert_called_once_with(
            iprange.id
        )
        dhcpsnippets_service_mock.delete.assert_called_once_with(
            QuerySpec(
                where=DhcpSnippetsClauseFactory.with_iprange_id(iprange.id)
            )
        )
        mock_temporal.register_or_update_workflow_call.assert_called_once_with(
            CONFIGURE_DHCP_WORKFLOW_NAME,
            ConfigureDHCPParam(subnet_ids=[iprange.subnet_id]),
            parameter_merge_func=merge_configure_dhcp_param,
            wait=False,
        )