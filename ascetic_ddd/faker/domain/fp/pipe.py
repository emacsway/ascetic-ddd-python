import typing
import dataclasses

from ascetic_ddd.faker.domain.fp.providers.interfaces import IProvider
from ascetic_ddd.session.interfaces import ISession

__all__ = ('Pipe', 'PipeStep')

T = typing.TypeVar('T')


@dataclasses.dataclass
class PipeStep:
    """A named step in the pipeline.

    Args:
        name: Key for this step's output in the context.
        provider: Provider to populate.
        require_fn: Receives read-only context of previous steps' results,
            returns criteria dict to apply before populate. None means no criteria.
    """

    name: str
    provider: IProvider[typing.Any]
    require_fn: typing.Callable[[dict[str, typing.Any]], dict[str, typing.Any] | None] | None = None


class Pipe(typing.Generic[T]):
    """Pipeline for top-down aggregate generation.

    Steps execute sequentially. Each step sees results of all previous steps
    as read-only context. Data flows one direction only — downstream steps
    cannot modify upstream providers' state.

    Eliminates diamond conflicts inherent in reverse control flow
    (ReferenceProvider calling aggregate_provider.populate/require).

    Example::

        pipe = Pipe(
            PipeStep('tenant', tenant_faker),
            PipeStep('order', order_faker,
                require_fn=lambda ctx: {'tenant_id': {'$eq': ctx['tenant'].id}}),
            result='order',
        )
        await pipe.populate(session)
        order = pipe.output()  # Order with correct tenant_id
    """

    def __init__(self, *steps: PipeStep, result: str | None = None) -> None:
        self._steps = list(steps)
        self._result = result or (steps[-1].name if steps else '')
        self._context: dict[str, typing.Any] = {}

    async def populate(self, session: ISession) -> None:
        if self.is_complete():
            return
        for step in self._steps:
            if step.require_fn is not None:
                criteria = step.require_fn(self._context)
                if criteria is not None:
                    step.provider.require(criteria)
            await step.provider.populate(session)
            self._context[step.name] = step.provider.output()

    def output(self) -> T:
        return self._context[self._result]

    def require(self, criteria: dict[str, typing.Any]) -> None:
        for step in self._steps:
            if step.name == self._result:
                step.provider.require(criteria)
                return

    def state(self) -> typing.Any:
        for step in self._steps:
            if step.name == self._result:
                return step.provider.state()
        return None

    def reset(self, visited: set[int] | None = None) -> None:
        if visited is None:
            visited = set()
        if id(self) in visited:
            return
        visited.add(id(self))
        for step in self._steps:
            step.provider.reset(visited)
        self._context.clear()

    def is_complete(self) -> bool:
        return self._result in self._context

    def is_transient(self) -> bool:
        for step in self._steps:
            if step.name == self._result:
                return step.provider.is_transient()
        return False

    async def setup(self, session: ISession, visited: set[int] | None = None) -> None:
        if visited is None:
            visited = set()
        if id(self) in visited:
            return
        visited.add(id(self))
        for step in self._steps:
            await step.provider.setup(session, visited)

    async def cleanup(self, session: ISession, visited: set[int] | None = None) -> None:
        if visited is None:
            visited = set()
        if id(self) in visited:
            return
        visited.add(id(self))
        for step in self._steps:
            await step.provider.cleanup(session, visited)
