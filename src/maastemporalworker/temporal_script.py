# Copyright 2024 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import asyncio
from logging import getLogger
import signal

from maasapiserver.settings import read_config
from maasserver.workflow.worker import Worker as TemporalWorker
from maasservicelayer.db import Database
from maastemporalworker.workflow.commission import CommissionNWorkflow
from maastemporalworker.workflow.configure import (
    ConfigureAgentActivity,
    ConfigureAgentWorkflow,
)
from maastemporalworker.workflow.deploy import (
    DeployActivity,
    DeployNWorkflow,
    DeployWorkflow,
)
from maastemporalworker.workflow.dhcp import (
    ConfigureDHCPForAgentWorkflow,
    ConfigureDHCPWorkflow,
    DHCPConfigActivity,
)
from maastemporalworker.workflow.msm import (
    MSMConnectorActivity,
    MSMEnrolSiteWorkflow,
    MSMHeartbeatWorkflow,
    MSMTokenRefreshWorkflow,
    MSMWithdrawWorkflow,
)
from maastemporalworker.workflow.tag_evaluation import (
    TagEvaluationActivity,
    TagEvaluationWorkflow,
)

log = getLogger()


async def _start_temporal_workers(workers: list[TemporalWorker]) -> None:
    futures = []
    for w in workers:
        futures.append(w.run())
    await asyncio.wait(futures)


async def _stop_temporal_workers(workers: list[TemporalWorker]) -> None:
    futures = []
    for w in workers:
        futures.append(w.stop())
    await asyncio.wait(futures)


async def main() -> None:
    # TODO check that Temporal is active
    log.info("starting region temporal-worker process")
    config = await read_config()
    log.debug("connecting to MAAS DB")
    db = Database(config.db, echo=config.debug_queries)
    log.debug("connecting to Temporal server")

    configure_activity = ConfigureAgentActivity(db)
    msm_activity = MSMConnectorActivity(db)
    tag_evaluation_activity = TagEvaluationActivity(db)
    deploy_activity = DeployActivity(db)
    dhcp_activity = DHCPConfigActivity(db)

    temporal_workers = [
        # All regions listen to a shared task queue. The first to pick up a task will execute it.
        TemporalWorker(
            task_queue="region",
            workflows=[
                # Configuration workflows
                ConfigureAgentWorkflow,
                ConfigureDHCPWorkflow,
                ConfigureDHCPForAgentWorkflow,
                # Lifecycle workflows
                DeployNWorkflow,
                DeployWorkflow,
                CommissionNWorkflow,
                # MSM Connector service
                MSMEnrolSiteWorkflow,
                MSMWithdrawWorkflow,
                MSMHeartbeatWorkflow,
                MSMTokenRefreshWorkflow,
                # Tag Evaluation workflows
                TagEvaluationWorkflow,
            ],
            activities=[
                # Configuration activities
                configure_activity.get_rack_controller_vlans,
                configure_activity.get_region_controller_endpoints,
                # Deploy activities
                deploy_activity.set_node_status,
                deploy_activity.get_boot_order,
                # DHCP activities
                dhcp_activity.find_agents_for_updates,
                dhcp_activity.fetch_hosts_for_update,
                dhcp_activity.get_omapi_key,
                # MSM connector activities,
                msm_activity.check_enrol,
                msm_activity.get_enrol,
                msm_activity.get_heartbeat_data,
                msm_activity.refresh_token,
                msm_activity.send_enrol,
                msm_activity.send_heartbeat,
                msm_activity.set_enrol,
                msm_activity.verify_token,
                # Tag evaluation activities
                tag_evaluation_activity.evaluate_tag,
            ],
        ),
    ]

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.ensure_future(
                _stop_temporal_workers(temporal_workers)
            ),
        )

    log.info("temporal-worker started")
    await _start_temporal_workers(temporal_workers)


def run():
    asyncio.run(main())
