"""Parallel activity - executes multiple RoutingSlips concurrently."""

import asyncio

from ascetic_ddd.saga.activity import Activity
from ascetic_ddd.saga.routing_slip import RoutingSlip
from ascetic_ddd.saga.work_item import WorkItem
from ascetic_ddd.saga.work_log import WorkLog
from ascetic_ddd.saga.work_result import WorkResult


__all__ = (
    'ParallelActivity',
)


class ParallelActivity(Activity):
    """Activity that executes multiple RoutingSlips in parallel (fork/join).

    Based on Section 8 of Garcia-Molina & Salem's "Sagas" (1987).

    Each branch is a full RoutingSlip with its own forward/backward paths.

    Behavior:
    - Executes all branch RoutingSlips concurrently
    - Fail-fast: on first failure, compensates completed branches
    - Compensation: all branches compensated in parallel

    Usage:
        WorkItem(ParallelActivity, WorkItemArguments({
            "branches": [
                RoutingSlip([
                    WorkItem(ReserveHotelActivity, args),
                    WorkItem(ConfirmHotelActivity, args),
                ]),
                RoutingSlip([
                    WorkItem(ReserveCarActivity, args),
                ]),
            ]
        }))
    """

    async def do_work(self, work_item: WorkItem) -> WorkLog | None:
        """Execute all branch RoutingSlips in parallel.

        Args:
            work_item: Must contain "branches" - list of RoutingSlip.

        Returns:
            WorkLog with branch references, or None if any branch failed.
        """
        branches: list[RoutingSlip] = work_item.arguments["branches"]

        # Execute all branches in parallel
        tasks = [self._execute_branch(branch) for branch in branches]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for failures
        for i, result in enumerate(results):
            if isinstance(result, Exception) or result is False:
                # Fail-fast: compensate all branches (completed and partial)
                await self._compensate_branches(branches)
                return None

        # All succeeded - store branches for future compensation
        return WorkLog(self, WorkResult({"_branches": branches}))

    async def _execute_branch(self, branch: RoutingSlip) -> bool:
        """Execute a single branch RoutingSlip to completion."""
        while not branch.is_completed:
            if not await branch.process_next():
                # Branch failed - compensate this branch
                while branch.is_in_progress:
                    await branch.undo_last()
                return False
        return True

    async def _compensate_branches(self, branches: list[RoutingSlip]) -> None:
        """Compensate all branches in parallel."""
        tasks = [self._compensate_branch(branch) for branch in branches]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _compensate_branch(self, branch: RoutingSlip) -> None:
        """Compensate a single branch."""
        while branch.is_in_progress:
            await branch.undo_last()

    async def compensate(self, work_log: WorkLog, routing_slip: RoutingSlip) -> bool:
        """Compensate all branches in parallel.

        Returns:
            True to continue backward path.
        """
        branches: list[RoutingSlip] = work_log.result["_branches"]
        await self._compensate_branches(branches)
        return True

    @property
    def work_item_queue_address(self) -> str:
        return "sb://./parallel"

    @property
    def compensation_queue_address(self) -> str:
        return "sb://./parallelCompensation"
