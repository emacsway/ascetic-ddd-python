"""Tests for FallbackActivity."""

import unittest

from ascetic_ddd.saga.activity import Activity
from ascetic_ddd.saga.fallback_activity import FallbackActivity
from ascetic_ddd.saga.routing_slip import RoutingSlip
from ascetic_ddd.saga.work_item import WorkItem
from ascetic_ddd.saga.work_item_arguments import WorkItemArguments
from ascetic_ddd.saga.work_log import WorkLog
from ascetic_ddd.saga.work_result import WorkResult


class PrimaryActivity(Activity):
    """Primary test activity."""

    call_count = 0
    compensate_count = 0
    should_fail = False

    async def do_work(self, work_item: WorkItem) -> WorkLog | None:
        PrimaryActivity.call_count += 1
        if PrimaryActivity.should_fail:
            return None
        return WorkLog(self, WorkResult({
            "provider": "primary",
            "value": work_item.arguments.get("value", "default"),
        }))

    async def compensate(self, work_log: WorkLog, routing_slip: RoutingSlip) -> bool:
        PrimaryActivity.compensate_count += 1
        return True

    @property
    def work_item_queue_address(self) -> str:
        return "sb://./primary"

    @property
    def compensation_queue_address(self) -> str:
        return "sb://./primaryCompensation"


class BackupActivity(Activity):
    """Backup test activity."""

    call_count = 0
    compensate_count = 0
    should_fail = False

    async def do_work(self, work_item: WorkItem) -> WorkLog | None:
        BackupActivity.call_count += 1
        if BackupActivity.should_fail:
            return None
        return WorkLog(self, WorkResult({
            "provider": "backup",
            "value": work_item.arguments.get("value", "default"),
        }))

    async def compensate(self, work_log: WorkLog, routing_slip: RoutingSlip) -> bool:
        BackupActivity.compensate_count += 1
        return True

    @property
    def work_item_queue_address(self) -> str:
        return "sb://./backup"

    @property
    def compensation_queue_address(self) -> str:
        return "sb://./backupCompensation"


class ThirdActivity(Activity):
    """Third fallback option."""

    call_count = 0
    compensate_count = 0

    async def do_work(self, work_item: WorkItem) -> WorkLog:
        ThirdActivity.call_count += 1
        return WorkLog(self, WorkResult({"provider": "third"}))

    async def compensate(self, work_log: WorkLog, routing_slip: RoutingSlip) -> bool:
        ThirdActivity.compensate_count += 1
        return True

    @property
    def work_item_queue_address(self) -> str:
        return "sb://./third"

    @property
    def compensation_queue_address(self) -> str:
        return "sb://./thirdCompensation"


class ConfirmActivity(Activity):
    """Confirmation step activity."""

    call_count = 0
    compensate_count = 0

    async def do_work(self, work_item: WorkItem) -> WorkLog:
        ConfirmActivity.call_count += 1
        return WorkLog(self, WorkResult({"confirmed": True}))

    async def compensate(self, work_log: WorkLog, routing_slip: RoutingSlip) -> bool:
        ConfirmActivity.compensate_count += 1
        return True

    @property
    def work_item_queue_address(self) -> str:
        return "sb://./confirm"

    @property
    def compensation_queue_address(self) -> str:
        return "sb://./confirmCompensation"


class FallbackActivityDoWorkTestCase(unittest.IsolatedAsyncioTestCase):
    """Test cases for FallbackActivity.do_work()."""

    def setUp(self):
        PrimaryActivity.call_count = 0
        PrimaryActivity.compensate_count = 0
        PrimaryActivity.should_fail = False
        BackupActivity.call_count = 0
        BackupActivity.compensate_count = 0
        BackupActivity.should_fail = False
        ThirdActivity.call_count = 0
        ThirdActivity.compensate_count = 0
        ConfirmActivity.call_count = 0
        ConfirmActivity.compensate_count = 0

    async def test_primary_succeeds(self):
        """Primary alternative succeeds, backup not called."""
        activity = FallbackActivity()
        work_item = WorkItem(FallbackActivity, WorkItemArguments({
            "alternatives": [
                RoutingSlip([WorkItem(PrimaryActivity, WorkItemArguments({"value": "test"}))]),
                RoutingSlip([WorkItem(BackupActivity, WorkItemArguments({"value": "test"}))]),
            ]
        }))

        result = await activity.do_work(work_item)

        self.assertIsNotNone(result)
        self.assertEqual(PrimaryActivity.call_count, 1)
        self.assertEqual(BackupActivity.call_count, 0)

    async def test_primary_fails_backup_succeeds(self):
        """Primary fails, backup succeeds."""
        PrimaryActivity.should_fail = True

        activity = FallbackActivity()
        work_item = WorkItem(FallbackActivity, WorkItemArguments({
            "alternatives": [
                RoutingSlip([WorkItem(PrimaryActivity, WorkItemArguments({"value": "test"}))]),
                RoutingSlip([WorkItem(BackupActivity, WorkItemArguments({"value": "test"}))]),
            ]
        }))

        result = await activity.do_work(work_item)

        self.assertIsNotNone(result)
        self.assertEqual(PrimaryActivity.call_count, 1)
        self.assertEqual(BackupActivity.call_count, 1)

    async def test_multi_step_alternative(self):
        """Multi-step alternative executes all steps."""
        activity = FallbackActivity()
        work_item = WorkItem(FallbackActivity, WorkItemArguments({
            "alternatives": [
                RoutingSlip([
                    WorkItem(PrimaryActivity, WorkItemArguments({"value": "step1"})),
                    WorkItem(ConfirmActivity, WorkItemArguments({})),
                ]),
            ]
        }))

        result = await activity.do_work(work_item)

        self.assertIsNotNone(result)
        self.assertEqual(PrimaryActivity.call_count, 1)
        self.assertEqual(ConfirmActivity.call_count, 1)

    async def test_all_alternatives_fail(self):
        """All alternatives fail, returns None."""
        PrimaryActivity.should_fail = True
        BackupActivity.should_fail = True

        activity = FallbackActivity()
        work_item = WorkItem(FallbackActivity, WorkItemArguments({
            "alternatives": [
                RoutingSlip([WorkItem(PrimaryActivity, WorkItemArguments({"value": "test"}))]),
                RoutingSlip([WorkItem(BackupActivity, WorkItemArguments({"value": "test"}))]),
            ]
        }))

        result = await activity.do_work(work_item)

        self.assertIsNone(result)
        self.assertEqual(PrimaryActivity.call_count, 1)
        self.assertEqual(BackupActivity.call_count, 1)

    async def test_third_alternative_succeeds(self):
        """First two fail, third succeeds."""
        PrimaryActivity.should_fail = True
        BackupActivity.should_fail = True

        activity = FallbackActivity()
        work_item = WorkItem(FallbackActivity, WorkItemArguments({
            "alternatives": [
                RoutingSlip([WorkItem(PrimaryActivity, WorkItemArguments({}))]),
                RoutingSlip([WorkItem(BackupActivity, WorkItemArguments({}))]),
                RoutingSlip([WorkItem(ThirdActivity, WorkItemArguments({}))]),
            ]
        }))

        result = await activity.do_work(work_item)

        self.assertIsNotNone(result)
        self.assertEqual(PrimaryActivity.call_count, 1)
        self.assertEqual(BackupActivity.call_count, 1)
        self.assertEqual(ThirdActivity.call_count, 1)


class FallbackActivityCompensateTestCase(unittest.IsolatedAsyncioTestCase):
    """Test cases for FallbackActivity.compensate()."""

    def setUp(self):
        PrimaryActivity.call_count = 0
        PrimaryActivity.compensate_count = 0
        PrimaryActivity.should_fail = False
        BackupActivity.call_count = 0
        BackupActivity.compensate_count = 0
        BackupActivity.should_fail = False
        ConfirmActivity.call_count = 0
        ConfirmActivity.compensate_count = 0

    async def test_compensate_primary(self):
        """Compensate the primary (successful) alternative."""
        activity = FallbackActivity()
        work_item = WorkItem(FallbackActivity, WorkItemArguments({
            "alternatives": [
                RoutingSlip([WorkItem(PrimaryActivity, WorkItemArguments({"value": "test"}))]),
                RoutingSlip([WorkItem(BackupActivity, WorkItemArguments({"value": "test"}))]),
            ]
        }))

        result = await activity.do_work(work_item)
        self.assertIsNotNone(result)

        compensate_result = await activity.compensate(result, RoutingSlip())

        self.assertTrue(compensate_result)
        self.assertEqual(PrimaryActivity.compensate_count, 1)
        self.assertEqual(BackupActivity.compensate_count, 0)

    async def test_compensate_backup(self):
        """Compensate the backup (successful) alternative."""
        PrimaryActivity.should_fail = True

        activity = FallbackActivity()
        work_item = WorkItem(FallbackActivity, WorkItemArguments({
            "alternatives": [
                RoutingSlip([WorkItem(PrimaryActivity, WorkItemArguments({"value": "test"}))]),
                RoutingSlip([WorkItem(BackupActivity, WorkItemArguments({"value": "test"}))]),
            ]
        }))

        result = await activity.do_work(work_item)
        self.assertIsNotNone(result)

        compensate_result = await activity.compensate(result, RoutingSlip())

        self.assertTrue(compensate_result)
        self.assertEqual(PrimaryActivity.compensate_count, 0)
        self.assertEqual(BackupActivity.compensate_count, 1)

    async def test_compensate_multi_step_alternative(self):
        """Compensate all steps of multi-step alternative."""
        activity = FallbackActivity()
        work_item = WorkItem(FallbackActivity, WorkItemArguments({
            "alternatives": [
                RoutingSlip([
                    WorkItem(PrimaryActivity, WorkItemArguments({})),
                    WorkItem(ConfirmActivity, WorkItemArguments({})),
                ]),
            ]
        }))

        result = await activity.do_work(work_item)
        self.assertIsNotNone(result)
        self.assertEqual(PrimaryActivity.call_count, 1)
        self.assertEqual(ConfirmActivity.call_count, 1)

        compensate_result = await activity.compensate(result, RoutingSlip())

        self.assertTrue(compensate_result)
        self.assertEqual(PrimaryActivity.compensate_count, 1)
        self.assertEqual(ConfirmActivity.compensate_count, 1)


class FallbackActivityQueueAddressTestCase(unittest.TestCase):
    """Test cases for queue addresses."""

    def test_work_item_queue_address(self):
        """Returns correct work queue address."""
        activity = FallbackActivity()
        self.assertEqual(activity.work_item_queue_address, "sb://./fallback")

    def test_compensation_queue_address(self):
        """Returns correct compensation queue address."""
        activity = FallbackActivity()
        self.assertEqual(activity.compensation_queue_address, "sb://./fallbackCompensation")



class FallbackActivityParentTestCase(unittest.IsolatedAsyncioTestCase):
    """Test cases for parent assignment to alternatives."""

    def setUp(self):
        PrimaryActivity.call_count = 0
        PrimaryActivity.compensate_count = 0
        PrimaryActivity.should_fail = False

    async def test_successful_alternative_has_parent_set(self):
        """Successful alternative has parent WorkItem set."""
        alternative = RoutingSlip([WorkItem(PrimaryActivity, WorkItemArguments({}))])

        activity = FallbackActivity()
        work_item = WorkItem(FallbackActivity, WorkItemArguments({
            "alternatives": [alternative]
        }))

        await activity.do_work(work_item)

        self.assertIs(alternative.parent, work_item)


class FallbackActivityIntegrationTestCase(unittest.IsolatedAsyncioTestCase):
    """Integration tests with RoutingSlip."""

    def setUp(self):
        PrimaryActivity.call_count = 0
        PrimaryActivity.compensate_count = 0
        PrimaryActivity.should_fail = False
        BackupActivity.call_count = 0
        BackupActivity.compensate_count = 0
        BackupActivity.should_fail = False
        ThirdActivity.call_count = 0
        ThirdActivity.compensate_count = 0

    async def test_fallback_step_in_routing_slip(self):
        """FallbackActivity works as a step in RoutingSlip."""
        PrimaryActivity.should_fail = True

        slip = RoutingSlip([
            WorkItem(ThirdActivity, WorkItemArguments({})),
            WorkItem(FallbackActivity, WorkItemArguments({
                "alternatives": [
                    RoutingSlip([WorkItem(PrimaryActivity, WorkItemArguments({"value": "try1"}))]),
                    RoutingSlip([WorkItem(BackupActivity, WorkItemArguments({"value": "try2"}))]),
                ]
            })),
            WorkItem(ThirdActivity, WorkItemArguments({})),
        ])

        # Execute all steps
        while not slip.is_completed:
            result = await slip.process_next()
            self.assertTrue(result)

        self.assertTrue(slip.is_completed)
        self.assertEqual(ThirdActivity.call_count, 2)
        self.assertEqual(PrimaryActivity.call_count, 1)  # Tried and failed
        self.assertEqual(BackupActivity.call_count, 1)   # Succeeded

    async def test_all_fallbacks_fail_triggers_compensation(self):
        """When all alternatives fail, saga can compensate previous steps."""
        PrimaryActivity.should_fail = True
        BackupActivity.should_fail = True

        slip = RoutingSlip([
            WorkItem(ThirdActivity, WorkItemArguments({})),
            WorkItem(FallbackActivity, WorkItemArguments({
                "alternatives": [
                    RoutingSlip([WorkItem(PrimaryActivity, WorkItemArguments({}))]),
                    RoutingSlip([WorkItem(BackupActivity, WorkItemArguments({}))]),
                ]
            })),
        ])

        # First step succeeds
        result1 = await slip.process_next()
        self.assertTrue(result1)

        # Second step (fallback) fails
        result2 = await slip.process_next()
        self.assertFalse(result2)

        # Compensate first step
        while slip.is_in_progress:
            await slip.undo_last()

        self.assertEqual(ThirdActivity.compensate_count, 1)


if __name__ == '__main__':
    unittest.main()
