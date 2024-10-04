from typing import Any

from maasservicelayer.models.configurations import Configuration
from tests.maasapiserver.fixtures.db import Fixture


async def create_test_configuration(
    fixture: Fixture, **extra_details: Any
) -> Configuration:
    configuration = {
        "name": "test",
        "value": "test",
    }
    configuration.update(extra_details)

    [created_configuration] = await fixture.create(
        "maasserver_config",
        [configuration],
    )
    return Configuration(**created_configuration)
