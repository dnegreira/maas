# Copyright 2024 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from maasservicelayer.models.base import MaasTimestampedBaseModel


class DNSPublication(MaasTimestampedBaseModel):
    serial: int
    source: str
    update: str
