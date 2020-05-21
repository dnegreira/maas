# Copyright 2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__all__ = ["get_deprecations", "log_deprecations"]

from provisioningserver.logger import LegacyLogger
from provisioningserver.utils import snappy

DEPRECATION_URL = "https://maas.io/deprecations/{id}"


class Deprecation:
    """A deprecation notice."""

    def __init__(self, id, since, description, link_text=""):
        self.id = id
        self.since = since
        self.description = description
        self.link_text = link_text

    @property
    def url(self):
        return DEPRECATION_URL.format(id=self.id)

    @property
    def message(self):
        return "Deprecation {id} ({url}): {description}".format(
            id=self.id, url=self.url, description=self.description
        )


# all known deprecation notices
DEPRECATIONS = {
    "NO_ALL_MODE": Deprecation(
        id="MD1",
        since="2.8",
        description=(
            "The setup for this MAAS is deprecated and not suitable for production "
            "environments, as the database is running inside the snap."
        ),
        link_text="How to migrate the database out of the snap",
    )
}


def get_deprecations():
    """Return a list of currently active deprecation notices."""
    deprecations = []
    if snappy.running_in_snap() and snappy.get_snap_mode() == "all":
        deprecations.append(DEPRECATIONS["NO_ALL_MODE"])
    return deprecations


def log_deprecations(logger=None):
    """Log active deprecations."""
    if logger is None:
        logger = LegacyLogger()
    for d in get_deprecations():
        logger.msg(d.message)


def sync_deprecation_notifications():
    from maasserver.models import Notification

    notifications = set(
        Notification.objects.filter(
            ident__startswith="deprecation_"
        ).values_list("ident", flat=True)
    )
    for deprecation in get_deprecations():
        for kind in ("users", "admins"):
            dep_ident = f"deprecation_{deprecation.id}_{kind}"
            if dep_ident in notifications:
                notifications.remove(dep_ident)
                continue
            message = deprecation.description
            if kind == "users":
                message += "<br>Please contact your MAAS administrator."
            message += (
                f"<br><a class='p-link--external' href='{deprecation.url}'>"
                f"{deprecation.link_text}...</a>"
            )
            Notification(
                ident=dep_ident,
                category="warning",
                message=message,
                dismissable=False,
                **{kind: True},
            ).save()

    # delete other deprecation notifications
    if notifications:
        Notification.objects.filter(ident__in=notifications).delete()
