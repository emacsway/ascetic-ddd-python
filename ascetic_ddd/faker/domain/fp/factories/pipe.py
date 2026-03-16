import typing
import dataclasses

from ascetic_ddd.faker.domain.fp.factories.interfaces import IFactory
from ascetic_ddd.session.interfaces import ISession

__all__ = ('Pipe', 'PipeStep')

T = typing.TypeVar('T')


@dataclasses.dataclass
class PipeStep:
    """A named step in the pipeline.

    Args:
        name: Key for this step's output in the context.
        factory: Factory to invoke.
        require_fn: Receives read-only context of previous steps' results,
            returns criteria dict for this step. None means no criteria.
    """

    name: str
    factory: IFactory[typing.Any]
    require_fn: typing.Callable[[dict[str, typing.Any]], dict[str, typing.Any] | None] | None = None


class Pipe(typing.Generic[T]):
    """Stateless pipeline for top-down aggregate generation.

    Steps execute sequentially. Each step sees results of all previous steps
    as read-only context. Data flows one direction only.

    Example::

        pipe = Pipe(
            PipeStep('tenant', tenant_factory),
            PipeStep('order', order_factory,
                require_fn=lambda ctx: {'tenant_id': {'$eq': ctx['tenant'].id}}),
            result='order',
        )
        order = await pipe.create(session)
    """

    def __init__(self, *steps: PipeStep, result: str | None = None) -> None:
        self._steps = list(steps)
        self._result = result or (steps[-1].name if steps else '')

    async def create(
            self,
            session: ISession,
            criteria: dict[str, typing.Any] | None = None,
    ) -> T:
        ctx: dict[str, typing.Any] = {}
        for step in self._steps:
            step_criteria = step.require_fn(ctx) if step.require_fn is not None else None
            ctx[step.name] = await step.factory.create(session, step_criteria)
        return ctx[self._result]

    async def setup(self, session: ISession) -> None:
        for step in self._steps:
            await step.factory.setup(session)

    async def cleanup(self, session: ISession) -> None:
        for step in self._steps:
            await step.factory.cleanup(session)
