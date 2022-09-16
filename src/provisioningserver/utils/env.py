# Copyright 2014-2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Environment-related utilities."""


from contextlib import contextmanager, suppress
import os
from pathlib import Path
import threading
from typing import Optional

from provisioningserver.path import get_maas_data_path
from provisioningserver.utils.fs import atomic_delete, atomic_write


@contextmanager
def environment_variables(variables):
    """Context manager: temporarily set the given environment variables.

    The variables are reset to their original settings afterwards.

    :param variables: A dict mapping environment variables to their temporary
        values.
    """
    prior_environ = os.environ.copy()
    os.environ.update(variables)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(prior_environ)


class FileBackedID:
    """An ID read and written to file.

    The content is written to the specified file under the MAAS data path, and
    access is done through a LockFile.

    """

    def __init__(self, name):
        self.name = name
        self.path = Path(get_maas_data_path(self.name))
        self._value = None
        self._lock = threading.Lock()

    def get(self) -> Optional[str]:
        """Return the value of the ID, if set, else None"""
        with self._lock:
            if not self._value:
                if not self.path.exists():
                    return None

                value = self._normalise_value(
                    self.path.read_text(encoding="ascii")
                )
                self._value = value
            return self._value

    def set(self, value: Optional[str]):
        """Set the value for the ID."""
        value = self._normalise_value(value)
        with self._lock:
            if value is None:
                with suppress(FileNotFoundError):
                    atomic_delete(self.path)
                self._value = None
            else:
                # ensure the parent dirs exist
                self.path.parent.mkdir(exist_ok=True)
                atomic_write(value.encode("ascii"), self.path)
                self._value = value

    def _normalise_value(self, value: Optional[str]) -> Optional[str]:
        if value:
            value = value.strip()
        return value if value else None


MAAS_ID = FileBackedID("maas_id")
MAAS_UUID = FileBackedID("maas_uuid")
