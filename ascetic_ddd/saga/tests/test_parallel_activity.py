"""Tests for ParallelActivity."""

import unittest

from ascetic_ddd.saga.activity import Activity
from ascetic_ddd.saga.parallel_activity import ParallelActivity
from ascetic_ddd.saga.routing_slip import RoutingSlip
from ascetic_ddd.saga.work_item import WorkItem
from ascetic_ddd.saga.work_item_arguments import WorkItemArguments
from ascetic_ddd.saga.work_log import WorkLog
from ascetic_ddd.saga.work_result import WorkResult


class BranchAActivity(Activity):
    """Test activity for branch A."""

    call_count = 0
    compensate_count = 0

    async def do_work(self, work_item: WorkItem) -> WorkLog:
        BranchAActivity.call_count += 1
        return WorkLog(self, WorkResult({
            "branch": "A",
            "value": work_item.arguments.get("value", "default"),
        }))

    async def compensate(self, work_log: WorkLog, routing_slip: RoutingSlip) -> bool:
        BranchAActivity.compensate_count += 1
        return True

    @property
    def work_item_queue_address(self) -> str:
        return "sb://./branchA"

    @property
    def compensation_queue_address(self) -> str:
        return "sb://./branchACompensation"


class BranchBActivity(Activity):
    """Test activity for branch B."""

    call_count = 0
    compensate_count = 0

    async def do_work(self, work_item: WorkItem) -> WorkLog:
        BranchBActivity.call_count += 1
        return WorkLog(self, WorkResult({
            "branch": "B",
            "value": work_item.arguments.get("value", "default"),
        }))

    async def compensate(self, work_log: WorkLog, routing_slip: RoutingSlip) -> bool:
        BranchBActivity.compensate_count += 1
        return True

    @property
    def work_item_queue_address(self) -> str:
        return "sb://./branchB"

    @property
    def compensation_queue_address(self) -> str:
        return "sb://./branchBCompensation"


class FailingBranchActivity(Activity):
    """Test activity that always fails."""

    call_count = 0

    async def do_work(self, work_item: WorkItem) -> WorkLog | None:
        FailingBranchActivity.call_count += 1
        return None

    async def compensate(self, work_log: WorkLog, routing_slip: RoutingSlip) -> bool:
        return True

    @property
    def work_item_queue_address(self) -> str:
        return "sb://./failing"

    @property
    def compensation_queue_address(self) -> str:
        return "sb://./failingCompensation"


class ParallelActivityDoWorkTestCase(unittest.IsolatedAsyncioTestCase):
    """Test cases for ParallelActivity.do_work()."""

    def setUp(self):
        BranchAActivity.call_count = 0
        BranchAActivity.compensate_count = 0
        BranchBActivity.call_count = 0
        BranchBActivity.compensate_count = 0
        FailingBranchActivity.call_count = 0

    async def test_all_branches_succeed(self):
        """All branches execute successfully."""
        activity = ParallelActivity()
        work_item = WorkItem(ParallelActivity, WorkItemArguments({
            "branches": [
                RoutingSlip([WorkItem(BranchAActivity, WorkItemArguments({"value": "a1"}))]),
                RoutingSlip([WorkItem(BranchBActivity, WorkItemArguments({"value": "b1"}))]),
            ]
        }))

        result = await activity.do_work(work_item)

        self.assertIsNotNone(result)
        self.assertEqual(BranchAActivity.call_count, 1)
        self.assertEqual(BranchBActivity.call_count, 1)

    async def test_multi_step_branches_succeed(self):
        """Multi-step branches execute all steps."""
        activity = ParallelActivity()
        work_item = WorkItem(ParallelActivity, WorkItemArguments({
            "branches": [
                RoutingSlip([
                    WorkItem(BranchAActivity, WorkItemArguments({"value": "a1"})),
                    WorkItem(BranchAActivity, WorkItemArguments({"value": "a2"})),
                ]),
                RoutingSlip([
                    WorkItem(BranchBActivity, WorkItemArguments({"value": "b1"})),
                ]),
            ]
        }))

        result = await activity.do_work(work_item)

        self.assertIsNotNone(result)
        self.assertEqual(BranchAActivity.call_count, 2)  # Two steps in first branch
        self.assertEqual(BranchBActivity.call_count, 1)

    async def test_one_branch_fails_compensates_all(self):
        """When one branch fails, all branches are compensated."""
        activity = ParallelActivity()
        work_item = WorkItem(ParallelActivity, WorkItemArguments({
            "branches": [
                RoutingSlip([
                    WorkItem(BranchAActivity, WorkItemArguments({"value": "a1"})),
                    WorkItem(FailingBranchActivity, WorkItemArguments({})),
                ]),
                RoutingSlip([
                    WorkItem(BranchBActivity, WorkItemArguments({"value": "b1"})),
                ]),
            ]
        }))

        result = await activity.do_work(work_item)

        self.assertIsNone(result)
        # BranchA was completed before failure, should be compensated
        self.assertEqual(BranchAActivity.call_count, 1)
        self.assertEqual(BranchAActivity.compensate_count, 1)


class ParallelActivityCompensateTestCase(unittest.IsolatedAsyncioTestCase):
    """Test cases for ParallelActivity.compensate()."""

    def setUp(self):
        BranchAActivity.call_count = 0
        BranchAActivity.compensate_count = 0
        BranchBActivity.call_count = 0
        BranchBActivity.compensate_count = 0

    async def test_compensate_all_branches(self):
        """Compensation compensates all branch RoutingSlips."""
        activity = ParallelActivity()
        work_item = WorkItem(ParallelActivity, WorkItemArguments({
            "branches": [
                RoutingSlip([
                    WorkItem(BranchAActivity, WorkItemArguments({"value": "a"})),
                    WorkItem(BranchAActivity, WorkItemArguments({"value": "a2"})),
                ]),
                RoutingSlip([
                    WorkItem(BranchBActivity, WorkItemArguments({"value": "b"})),
                ]),
            ]
        }))

        # First execute
        result = await activity.do_work(work_item)
        self.assertIsNotNone(result)
        self.assertEqual(BranchAActivity.call_count, 2)
        self.assertEqual(BranchBActivity.call_count, 1)

        # Then compensate
        compensate_result = await activity.compensate(result, RoutingSlip())

        self.assertTrue(compensate_result)
        self.assertEqual(BranchAActivity.compensate_count, 2)  # Both steps compensated
        self.assertEqual(BranchBActivity.compensate_count, 1)


class ParallelActivityQueueAddressTestCase(unittest.TestCase):
    """Test cases for queue addresses."""

    def test_work_item_queue_address(self):
        """Returns correct work queue address."""
        activity = ParallelActivity()
        self.assertEqual(activity.work_item_queue_address, "sb://./parallel")

    def test_compensation_queue_address(self):
        """Returns correct compensation queue address."""
        activity = ParallelActivity()
        self.assertEqual(activity.compensation_queue_address, "sb://./parallelCompensation")


class ParallelActivityIntegrationTestCase(unittest.IsolatedAsyncioTestCase):
    """Integration tests with RoutingSlip."""

    def setUp(self):
        BranchAActivity.call_count = 0
        BranchAActivity.compensate_count = 0
        BranchBActivity.call_count = 0
        BranchBActivity.compensate_count = 0
        FailingBranchActivity.call_count = 0

    async def test_parallel_step_in_routing_slip(self):
        """ParallelActivity works as a step in RoutingSlip."""
        slip = RoutingSlip([
            WorkItem(BranchAActivity, WorkItemArguments({"value": "before"})),
            WorkItem(ParallelActivity, WorkItemArguments({
                "branches": [
                    RoutingSlip([
                        WorkItem(BranchAActivity, WorkItemArguments({"value": "p1"})),
                        WorkItem(BranchAActivity, WorkItemArguments({"value": "p2"})),
                    ]),
                    RoutingSlip([
                        WorkItem(BranchBActivity, WorkItemArguments({"value": "p3"})),
                    ]),
                ]
            })),
            WorkItem(BranchBActivity, WorkItemArguments({"value": "after"})),
        ])

        # Execute all steps
        while not slip.is_completed:
            result = await slip.process_next()
            self.assertTrue(result)

        self.assertTrue(slip.is_completed)
        # BranchA: 1 (before) + 2 (parallel branch) = 3
        self.assertEqual(BranchAActivity.call_count, 3)
        # BranchB: 1 (parallel branch) + 1 (after) = 2
        self.assertEqual(BranchBActivity.call_count, 2)

    async def test_parallel_failure_triggers_saga_compensation(self):
        """Failed parallel step allows saga compensation."""
        slip = RoutingSlip([
            WorkItem(BranchAActivity, WorkItemArguments({"value": "first"})),
            WorkItem(ParallelActivity, WorkItemArguments({
                "branches": [
                    RoutingSlip([
                        WorkItem(BranchBActivity, WorkItemArguments({"value": "ok"})),
                    ]),
                    RoutingSlip([
                        WorkItem(FailingBranchActivity, WorkItemArguments({})),
                    ]),
                ]
            })),
        ])

        # First step succeeds
        result1 = await slip.process_next()
        self.assertTrue(result1)
        self.assertEqual(BranchAActivity.call_count, 1)

        # Second step (parallel) fails
        result2 = await slip.process_next()
        self.assertFalse(result2)

        # Compensate first step
        while slip.is_in_progress:
            await slip.undo_last()

        self.assertEqual(BranchAActivity.compensate_count, 1)


if __name__ == '__main__':
    unittest.main()
