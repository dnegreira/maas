#  Copyright 2024 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

from maascommon.enums.service import ServiceName, ServiceStatusEnum
from maasservicelayer.models.base import MaasTimestampedBaseModel


class ServiceStatus(MaasTimestampedBaseModel):
    name: ServiceName
    status: ServiceStatusEnum
    status_info: str
    node_id: int
