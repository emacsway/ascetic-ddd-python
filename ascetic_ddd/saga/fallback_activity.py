"""Fallback activity - tries alternative RoutingSlips until one succeeds."""

from ascetic_ddd.saga.activity import Activity
from ascetic_ddd.saga.routing_slip import RoutingSlip
from ascetic_ddd.saga.work_item import WorkItem
from ascetic_ddd.saga.work_log import WorkLog
from ascetic_ddd.saga.work_result import WorkResult


__all__ = (
    'FallbackActivity',
)


class FallbackActivity(Activity):
    """Activity that tries alternative RoutingSlips until one succeeds.

    Based on Section 6 "Recovery Blocks" of Garcia-Molina & Salem's "Sagas" (1987).

    Each alternative is a full RoutingSlip with its own forward/backward paths.

    Behavior:
    - Tries each alternative RoutingSlip in order
    - Stops on first success
    - If alternative fails, it compensates itself before trying next
    - Only the successful alternative needs compensation

    Usage:
        WorkItem(FallbackActivity, WorkItemArguments({
            "alternatives": [
                RoutingSlip([
                    WorkItem(PrimaryPaymentActivity, args),
                    WorkItem(ConfirmPaymentActivity, args),
                ]),
                RoutingSlip([
                    WorkItem(BackupPaymentActivity, args),
                ]),
            ]
        }))
    """

    async def do_work(self, work_item: WorkItem) -> WorkLog | None:
        """Try alternative RoutingSlips until one succeeds.

        Args:
            work_item: Must contain "alternatives" - list of RoutingSlip.

        Returns:
            WorkLog with successful alternative, or None if all failed.
        """
        alternatives: list[RoutingSlip] = work_item.arguments["alternatives"]

        for alternative in alternatives:
            # Set parent for coordination when using message bus
            alternative.parent = work_item

            success = await self._execute_alternative(alternative)

            if success:
                # Store which alternative succeeded for future compensation
                return WorkLog(self, WorkResult({"_succeeded": alternative}))

        # All alternatives failed
        return None

    async def _execute_alternative(self, alternative: RoutingSlip) -> bool:
        """Execute an alternative RoutingSlip to completion."""
        while not alternative.is_completed:
            if not await alternative.process_next():
                # Alternative failed - compensate and return False
                while alternative.is_in_progress:
                    await alternative.undo_last()
                return False
        return True

    async def compensate(self, work_log: WorkLog, routing_slip: RoutingSlip) -> bool:
        """Compensate the successful alternative.

        Returns:
            True to continue backward path.
        """
        succeeded: RoutingSlip = work_log.result["_succeeded"]

        while succeeded.is_in_progress:
            await succeeded.undo_last()

        return True

    @property
    def work_item_queue_address(self) -> str:
        return "sb://./fallback"

    @property
    def compensation_queue_address(self) -> str:
        return "sb://./fallbackCompensation"
