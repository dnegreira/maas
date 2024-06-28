# Copyright 2024 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).


from sqlalchemy import desc, select
from sqlalchemy.sql.operators import le

from maasapiserver.common.db.tables import VlanTable
from maasapiserver.v3.api.models.requests.vlans import VlanRequest
from maasapiserver.v3.db.base import BaseRepository
from maasapiserver.v3.models.base import ListResult
from maasapiserver.v3.models.vlans import Vlan


class VlansRepository(BaseRepository[Vlan, VlanRequest]):
    async def create(self, request: VlanRequest) -> Vlan:
        raise NotImplementedError()

    async def find_by_id(self, id: int) -> Vlan | None:
        raise NotImplementedError()

    async def find_by_name(self, name: str) -> Vlan | None:
        raise NotImplementedError()

    async def list(self, token: str | None, size: int) -> ListResult[Vlan]:
        stmt = (
            select("*")
            .select_from(VlanTable)
            .order_by(desc(VlanTable.c.id))
            .limit(size + 1)  # Retrieve one more element to get the next token
        )
        if token is not None:
            stmt = stmt.where(le(VlanTable.c.id, int(token)))

        result = (await self.connection.execute(stmt)).all()
        next_token = None
        if len(result) > size:  # There is another page
            next_token = result.pop().id
        return ListResult[Vlan](
            items=[Vlan(**row._asdict()) for row in result],
            next_token=next_token,
        )

    async def update(self, resource: Vlan) -> Vlan:
        raise NotImplementedError()

    async def delete(self, id: int) -> None:
        raise NotImplementedError()
