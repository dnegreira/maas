# Copyright 2014 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""RPC helpers relating to nodes."""

from __future__ import (
    absolute_import,
    print_function,
    unicode_literals,
    )

str = None

__metaclass__ = type
__all__ = [
    "mark_node_failed",
    "update_node_power_state",
    "create_node",
]


from django.core.exceptions import ValidationError
from maasserver.api.utils import get_overridden_query_dict
from maasserver.forms import AdminNodeWithMACAddressesForm
from maasserver.models import (
    Node,
    NodeGroup,
    )
from maasserver.utils.async import transactional
from provisioningserver.rpc.exceptions import (
    NoSuchCluster,
    NoSuchNode,
    )
from provisioningserver.utils.twisted import synchronous


@synchronous
@transactional
def mark_node_failed(system_id, error_description):
    """Mark a node as failed.

    for :py:class:`~provisioningserver.rpc.region.MarkBroken`.
    """
    try:
        node = Node.objects.get(system_id=system_id)
    except Node.DoesNotExist:
        raise NoSuchNode.from_system_id(system_id)
    node.mark_failed(error_description)


@synchronous
@transactional
def list_cluster_nodes_power_parameters(uuid):
    """Query a cluster controller and return all of its nodes
    power parameters

    for :py:class:`~provisioningserver.rpc.region.ListNodePowerParameters`.
    """
    try:
        nodegroup = NodeGroup.objects.get_by_natural_key(uuid)
    except NodeGroup.DoesNotExist:
        raise NoSuchCluster.from_uuid(uuid)
    else:
        power_info_by_node = (
            (node, node.get_effective_power_info())
            for node in nodegroup.node_set.all()
        )
        return [
            {
                'system_id': node.system_id,
                'hostname': node.hostname,
                'power_state': node.power_state,
                'power_type': power_info.power_type,
                'context': power_info.power_parameters,
            }
            for node, power_info in power_info_by_node
            if power_info.power_type is not None
        ]


@synchronous
@transactional
def update_node_power_state(system_id, power_state):
    """Update a node power state.

    for :py:class:`~provisioningserver.rpc.region.UpdateNodePowerState.
    """
    try:
        node = Node.objects.get(system_id=system_id)
    except Node.DoesNotExist:
        raise NoSuchNode.from_system_id(system_id)
    node.update_power_state(power_state)


@transactional
def create_node(cluster_uuid, architecture, power_type,
                power_parameters, mac_addresses):
    """Create a new `Node` and return it.

    :param cluster_uuid: The UUID of the cluster upon which the node
        should be created.
    :param architecture: The architecture of the new node.
    :param power_type: The power type of the new node.
    :param power_parameters: A JSON-encoded string of power parameters
        for the new node.
    :param mac_addresses: An iterable of MAC addresses that belong to
        the node.
    """
    cluster = NodeGroup.objects.get_by_natural_key(cluster_uuid)
    data = {
        'power_type': power_type,
        'power_parameters': power_parameters,
        'architecture': architecture,
        'nodegroup': cluster,
        'mac_addresses': mac_addresses,
    }
    data_query_dict = get_overridden_query_dict(
        {}, data, AdminNodeWithMACAddressesForm.Meta.fields)
    form = AdminNodeWithMACAddressesForm(data_query_dict)
    if form.is_valid():
        node = form.save()
        return node
    else:
        raise ValidationError(form.errors)
