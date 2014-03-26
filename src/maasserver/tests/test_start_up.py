# Copyright 2012-2014 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the start up utility."""

from __future__ import (
    absolute_import,
    print_function,
    unicode_literals,
    )

str = None

__metaclass__ = type
__all__ = []

from maasserver import (
    eventloop,
    locks,
    start_up,
    )
from maasserver.components import (
    discard_persistent_error,
    register_persistent_error,
    )
from maasserver.enum import COMPONENT
from maasserver.models import (
    BootImage,
    NodeGroup,
    )
from maasserver.testing.factory import factory
from maasserver.testing.testcase import MAASServerTestCase
from maastesting.celery import CeleryFixture
from maastesting.fakemethod import FakeMethod
from maastesting.matchers import MockCalledOnceWith
from mock import Mock
from provisioningserver import tasks
from testresources import FixtureResource


class LockChecker:
    """Callable.  Records calls, and whether the startup lock was held."""

    def __init__(self, lock_file=None):
        self.call_count = 0
        self.lock_was_held = None

    def __call__(self):
        self.call_count += 1
        self.lock_was_held = locks.startup.is_locked()


class TestStartUp(MAASServerTestCase):
    """Testing for the method `start_up`."""

    resources = (
        ('celery', FixtureResource(CeleryFixture())),
        )

    def tearDown(self):
        super(TestStartUp, self).tearDown()
        eventloop.stop().wait(5)

    def test_start_up_calls_write_full_dns_config(self):
        recorder = FakeMethod()
        self.patch(start_up, 'write_full_dns_config', recorder)
        start_up.start_up()
        self.assertEqual(
            (1, [()]),
            (recorder.call_count, recorder.extract_args()))

    def test_start_up_creates_master_nodegroup(self):
        start_up.start_up()
        self.assertEqual(1, NodeGroup.objects.all().count())

    def test_start_up_refreshes_workers(self):
        patched_handlers = tasks.refresh_functions.copy()
        patched_handlers['nodegroup_uuid'] = Mock()
        self.patch(tasks, 'refresh_functions', patched_handlers)
        start_up.start_up()
        self.assertThat(
            patched_handlers['nodegroup_uuid'],
            MockCalledOnceWith(NodeGroup.objects.ensure_master().uuid))

    def test_start_up_refreshes_workers_outside_lock(self):
        lock_checker = LockChecker()
        self.patch(NodeGroup.objects, 'refresh_workers', lock_checker)
        start_up.start_up()
        self.assertEquals(False, lock_checker.lock_was_held)

    def test_start_up_runs_in_exclusion(self):
        lock_checker = LockChecker()
        self.patch(start_up, 'inner_start_up', lock_checker)
        start_up.start_up()
        self.assertEqual(1, lock_checker.call_count)
        self.assertEqual(True, lock_checker.lock_was_held)

    def test_start_up_warns_about_missing_boot_images(self):
        # If no boot images have been registered yet, that may mean that
        # the import script has not been successfully run yet, or that
        # the master worker is having trouble reporting its images.  And
        # so start_up registers a persistent warning about this.
        BootImage.objects.all().delete()
        discard_persistent_error(COMPONENT.IMPORT_PXE_FILES)
        recorder = self.patch(start_up, 'register_persistent_error')

        start_up.start_up()

        self.assertIn(
            COMPONENT.IMPORT_PXE_FILES,
            [args[0][0] for args in recorder.call_args_list])

    def test_start_up_does_not_warn_if_boot_images_are_known(self):
        # If boot images are known, there is no warning about the import
        # script.
        factory.make_boot_image()
        recorder = self.patch(start_up, 'register_persistent_error')

        start_up.start_up()

        self.assertNotIn(
            COMPONENT.IMPORT_PXE_FILES,
            [args[0][0] for args in recorder.call_args_list])

    def test_start_up_does_not_warn_if_already_warning(self):
        # If there already is a warning about missing boot images, it is
        # based on more precise knowledge of whether we ever heard from
        # the region worker at all.  It will not be replaced by a less
        # knowledgeable warning.
        BootImage.objects.all().delete()
        register_persistent_error(
            COMPONENT.IMPORT_PXE_FILES, factory.getRandomString())
        recorder = self.patch(start_up, 'register_persistent_error')

        start_up.start_up()

        self.assertNotIn(
            COMPONENT.IMPORT_PXE_FILES,
            [args[0][0] for args in recorder.call_args_list])
