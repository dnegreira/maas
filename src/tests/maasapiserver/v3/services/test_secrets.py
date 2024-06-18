import abc
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from maasapiserver.common.vault.api.apiclient import AsyncVaultApiClient
from maasapiserver.common.vault.api.models.exceptions import (
    VaultNotFoundException,
)
from maasapiserver.common.vault.manager import AsyncVaultManager
from maasapiserver.v3.services import ConfigurationsService
from maasapiserver.v3.services.secrets import (
    LocalSecretsStorageService,
    SecretNotFound,
    SecretsService,
    SecretsServiceFactory,
    VaultSecretsService,
)
from tests.maasapiserver.fixtures.db import Fixture


@pytest.fixture(autouse=True)
def prepare():
    # Always reset the SecretsServiceFactory cache
    SecretsServiceFactory.clear()
    yield
    SecretsServiceFactory.clear()


@pytest.mark.usefixtures("ensuremaasdb")
@pytest.mark.asyncio
class SecretsServiceTestSuite:
    DEFAULT_SECRET = "secret"
    DEFAULT_COMPOSITE_SECRET = {"data": {"drivers": [1, 2, 3], "maps": True}}
    DEFAULT_PATH = "mypath"

    @abc.abstractmethod
    def get_vault_service(self, connection) -> SecretsService:
        pass

    # simple secrets
    async def test_get_not_path_not_found(self, db_connection):
        vault_service = self.get_vault_service(db_connection)
        with pytest.raises(SecretNotFound):
            await vault_service.get_simple_secret(self.DEFAULT_PATH)

    async def test_get_returns_default_if_path_not_found(self, db_connection):
        vault_service = self.get_vault_service(db_connection)
        retrieved_secret = await vault_service.get_simple_secret(
            self.DEFAULT_PATH, default=self.DEFAULT_SECRET
        )
        assert retrieved_secret == self.DEFAULT_SECRET

    async def test_set_and_get_simple_secret(self, db_connection):
        vault_service = self.get_vault_service(db_connection)
        await vault_service.set_simple_secret(
            self.DEFAULT_PATH, self.DEFAULT_SECRET
        )
        retrieved_secret = await vault_service.get_simple_secret(
            self.DEFAULT_PATH
        )
        assert retrieved_secret == self.DEFAULT_SECRET

    async def test_set_updates_simple_secret(self, db_connection):
        updated_secret = "supersecret"
        vault_service = self.get_vault_service(db_connection)
        await vault_service.set_simple_secret(
            self.DEFAULT_PATH, self.DEFAULT_SECRET
        )
        await vault_service.set_simple_secret(
            self.DEFAULT_PATH, updated_secret
        )
        retrieved_secret = await vault_service.get_simple_secret(
            self.DEFAULT_PATH
        )
        assert retrieved_secret == updated_secret

    # composite secrets
    async def test_get_composite_secret_path_not_found(self, db_connection):
        vault_service = self.get_vault_service(db_connection)
        with pytest.raises(SecretNotFound):
            await vault_service.get_composite_secret(self.DEFAULT_PATH)

    async def test_get_composite_secret_returns_default_if_path_not_found(
        self, db_connection
    ):
        vault_service = self.get_vault_service(db_connection)
        retrieved_secret = await vault_service.get_composite_secret(
            self.DEFAULT_PATH, default=self.DEFAULT_COMPOSITE_SECRET
        )
        assert retrieved_secret == self.DEFAULT_COMPOSITE_SECRET

    async def test_set_and_get_composite_secret(self, db_connection):
        vault_service = self.get_vault_service(db_connection)
        await vault_service.set_composite_secret(
            self.DEFAULT_PATH, self.DEFAULT_COMPOSITE_SECRET
        )
        retrieved_secret = await vault_service.get_composite_secret(
            self.DEFAULT_PATH
        )
        assert retrieved_secret == self.DEFAULT_COMPOSITE_SECRET

    async def test_set_updates_composite_secret(self, db_connection):
        updated_secret = {"mynewdata": [1, 2, 3, 4]}
        vault_service = self.get_vault_service(db_connection)
        await vault_service.set_composite_secret(
            self.DEFAULT_PATH, self.DEFAULT_COMPOSITE_SECRET
        )
        await vault_service.set_composite_secret(
            self.DEFAULT_PATH, updated_secret
        )
        retrieved_secret = await vault_service.get_composite_secret(
            self.DEFAULT_PATH
        )
        assert retrieved_secret == updated_secret

    # delete
    async def test_delete(self, db_connection):
        vault_service = self.get_vault_service(db_connection)
        await vault_service.set_composite_secret(
            self.DEFAULT_PATH, self.DEFAULT_COMPOSITE_SECRET
        )
        retrieved_secret = await vault_service.get_composite_secret(
            self.DEFAULT_PATH
        )
        assert retrieved_secret is not None
        await vault_service.delete(self.DEFAULT_PATH)
        with pytest.raises(SecretNotFound):
            await vault_service.get_composite_secret(self.DEFAULT_PATH)


class TestLocalSecretStorageService(SecretsServiceTestSuite):
    def get_vault_service(self, connection) -> SecretsService:
        return LocalSecretsStorageService(connection)


class AsyncVaultManagerMock(AsyncVaultManager):
    def __init__(self):
        super().__init__(
            Mock(AsyncVaultApiClient), "role_id", "secret_id", "base_path"
        )
        self.storage = {}

    async def set(self, path: str, value: dict[str, Any]) -> None:
        self.storage[self._build_path_key(path)] = value

    async def get(self, path: str) -> dict[str, Any]:
        key = self._build_path_key(path)
        if key not in self.storage:
            raise VaultNotFoundException("Not found")
        return self.storage[key]

    async def delete(self, path: str) -> None:
        del self.storage[self._build_path_key(path)]

    def _build_path_key(self, path: str):
        return f"/v1/{self._secrets_mount}/data/{path}"


@pytest.mark.asyncio
class TestVaultSecretService(SecretsServiceTestSuite):
    def get_vault_service(self, connection) -> SecretsService:
        return VaultSecretsService(
            connection=connection, vault_manager=AsyncVaultManagerMock()
        )


@pytest.mark.asyncio
class TestSecretServiceFactory:
    async def test_with_default_settings(self, db_connection: AsyncConnection):
        assert SecretsServiceFactory.IS_VAULT_ENABLED is None
        vault_service = await SecretsServiceFactory.produce(
            db_connection, ConfigurationsService(db_connection)
        )
        assert SecretsServiceFactory.IS_VAULT_ENABLED is False
        assert isinstance(vault_service, LocalSecretsStorageService)

    async def test_with_vault_enabled(
        self, db_connection: AsyncConnection, fixture: Fixture
    ):
        configuration_service_mock = Mock(ConfigurationsService)
        configuration_service_mock.get = AsyncMock(return_value=True)
        vault_service = await SecretsServiceFactory.produce(
            db_connection, configuration_service_mock
        )
        assert SecretsServiceFactory.IS_VAULT_ENABLED is True
        assert isinstance(vault_service, VaultSecretsService)

    async def test_with_vault_disabled(
        self, db_connection: AsyncConnection, fixture: Fixture
    ):
        configuration_service_mock = Mock(ConfigurationsService)
        configuration_service_mock.get = AsyncMock(return_value=False)
        vault_service = await SecretsServiceFactory.produce(
            db_connection, configuration_service_mock
        )
        assert SecretsServiceFactory.IS_VAULT_ENABLED is False
        assert isinstance(vault_service, LocalSecretsStorageService)

    async def test_clear(self, db_connection: AsyncConnection):
        configuration_service_mock = Mock(ConfigurationsService)
        configuration_service_mock.get = AsyncMock(return_value=False)
        await SecretsServiceFactory.produce(
            db_connection, configuration_service_mock
        )
        assert SecretsServiceFactory.IS_VAULT_ENABLED is False
        SecretsServiceFactory.clear()
        assert SecretsServiceFactory.IS_VAULT_ENABLED is None
