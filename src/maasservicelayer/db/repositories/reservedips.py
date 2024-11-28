# Copyright 2024 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from typing import Type

from sqlalchemy import join, Table
from sqlalchemy.sql.operators import eq

from maasservicelayer.db.filters import Clause, ClauseFactory
from maasservicelayer.db.repositories.base import BaseRepository
from maasservicelayer.db.tables import ReservedIPTable, SubnetTable, VlanTable
from maasservicelayer.models.reservedips import ReservedIP


class ReservedIPsClauseFactory(ClauseFactory):
    @classmethod
    def with_subnet_id(cls, subnet_id: int) -> Clause:
        return Clause(condition=eq(ReservedIPTable.c.subnet_id, subnet_id))

    @classmethod
    def with_vlan_id(cls, vlan_id: int) -> Clause:
        return Clause(
            condition=eq(SubnetTable.c.vlan_id, vlan_id),
            joins=[
                join(
                    ReservedIPTable,
                    SubnetTable,
                    eq(ReservedIPTable.c.subnet_id, SubnetTable.c.id),
                )
            ],
        )

    @classmethod
    def with_fabric_id(cls, fabric_id: int) -> Clause:
        return Clause(
            condition=eq(VlanTable.c.fabric_id, fabric_id),
            joins=[
                join(
                    ReservedIPTable,
                    SubnetTable,
                    eq(ReservedIPTable.c.subnet_id, SubnetTable.c.id),
                ),
                join(
                    VlanTable,
                    SubnetTable,
                    eq(VlanTable.c.id, SubnetTable.c.vlan_id),
                ),
            ],
        )


class ReservedIPsRepository(BaseRepository[ReservedIP]):
    def get_repository_table(self) -> Table:
        return ReservedIPTable

    def get_model_factory(self) -> Type[ReservedIP]:
        return ReservedIP
