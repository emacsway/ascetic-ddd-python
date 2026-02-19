import asyncio
import inspect
import math
import os
import typing
import operator
from hypothesis import strategies

from ascetic_ddd.faker.domain.generators.interfaces import IInputGenerator
from ascetic_ddd.faker.domain.query.operators import IQueryOperator, EqOperator
from ascetic_ddd.session.interfaces import ISession


__all__ = (
    "IterableGenerator",
    "HypothesisStrategyGenerator",
    "CallableGenerator",
    "CountableGenerator",
    "SequenceGenerator",
    "RangeGenerator",
    "TemplateGenerator",
    "RequiredGenerator",
    "prepare_input_generator",
)

T = typing.TypeVar("T")


class _SupportsRangeOps(typing.Protocol):
    def __sub__(self, __other: typing.Any) -> typing.Any: ...
    def __add__(self, __other: typing.Any) -> typing.Any: ...
    def __le__(self, __other: typing.Any) -> bool: ...
    def __lt__(self, __other: typing.Any) -> bool: ...


_RangeT = typing.TypeVar("_RangeT", bound=_SupportsRangeOps)


def prepare_input_generator(input_generator):
    if input_generator is not None:
        if isinstance(input_generator, strategies.SearchStrategy):
            input_generator = HypothesisStrategyGenerator(input_generator)
        elif isinstance(input_generator, typing.Iterable) and not isinstance(input_generator, (str, bytes)):
            input_generator = IterableGenerator(input_generator)
        elif callable(input_generator):
            # Check if already wrapped
            if not isinstance(input_generator, CallableGenerator):
                input_generator = CallableGenerator(input_generator)
        input_generator = RequiredGenerator(input_generator)
    return input_generator


class IterableGenerator(typing.Generic[T]):

    def __init__(self, values: typing.Iterable[T]):
        self._source = values
        self._values = iter(self._source)

    async def __call__(self, session: ISession, query: IQueryOperator | None = None, position: typing.Optional[int] = None) -> T:
        try:
            return next(self._values)
        except StopIteration as e:
            self._values = iter(self._source)
            return self.__call__(session=session, query=query, position=position)


class HypothesisStrategyGenerator(typing.Generic[T]):
    """
    Do we actually need it?
    self._strategy.example() is a regular function.
    CallableGenerator can be used instead.
    """

    def __init__(self, strategy: strategies.SearchStrategy[T]):
        self._strategy = strategy

    async def __call__(self, session: ISession, query: IQueryOperator | None = None, position: typing.Optional[int] = None) -> T:
        return self._strategy.example()


class CallableGenerator(typing.Generic[T]):
    """
    Wrapper for a callable with any number of parameters (0, 1, or 2).
    Automatically detects signature and async.
    """

    def __init__(self, callable_: typing.Callable):
        self._callable = callable_
        signature = inspect.signature(callable_)
        self._num_params = len(signature.parameters)
        self._is_async = (
            asyncio.iscoroutinefunction(callable_) or
            asyncio.iscoroutinefunction(getattr(callable_, '__call__', None))
        )

    async def __call__(self, session: ISession, query: IQueryOperator | None = None, position: typing.Optional[int] = None) -> T:
        if self._num_params == 0:
            result = self._callable()
        elif self._num_params == 1:
            result = self._callable(session)
        elif self._num_params == 2:
            result = self._callable(session, query)
        else:
            result = self._callable(session, query, position)
        if self._is_async or asyncio.iscoroutine(result):
            result = await result
        return result


class CountableGenerator(typing.Generic[T]):

    def __init__(self, base: str):
        self._count = 0
        self._pid = os.getpid()
        self._base = base

    async def __call__(self, session: ISession, query: IQueryOperator | None = None, position: typing.Optional[int] = None) -> T:
        result = "%s_%s_%s" % (self._base, os.getpid(), ++self._count)
        self._count += 1
        return result


class SequenceGenerator(typing.Generic[T]):

    def __init__(self, lower: T, delta: typing.Any):
        self._lower = lower
        self._delta = delta
        self._op = operator.add

    async def __call__(self, session: ISession, query: IQueryOperator | None = None, position: typing.Optional[int] = None) -> T:
        return self._op(self._lower, self._delta * position)


class RangeGenerator(typing.Generic[_RangeT]):

    def __init__(self, lower: _RangeT, upper: _RangeT):
        self._lower = lower
        self._upper = upper
        self._range = upper - lower

    async def __call__(self, session: ISession, query: IQueryOperator | None = None, position: typing.Optional[int] = None) -> _RangeT:
        assert position is not None
        degree = 1 if position < 2 else math.ceil(math.log2(position))
        base = 2 ** degree
        value = self._lower + self._range * (position % base) / base
        assert self._lower <= value < self._upper
        return value


class RequiredGenerator(typing.Generic[T]):

    def __init__(self, delegate: IInputGenerator[T]):
        self._delegate = delegate

    async def __call__(self, session: ISession, query: IQueryOperator | None = None, position: typing.Optional[int] = None) -> T:
        if isinstance(query, EqOperator):
            return query.value
        return await self._delegate(session, query, position)


class TemplateGenerator:

    def __init__(self, delegate: IInputGenerator[typing.Any], template: str):
        assert "%s" in template
        self._template = template
        self._delegate = delegate

    async def __call__(self, session: ISession, query: IQueryOperator | None = None, position: typing.Optional[int] = None) -> str:
        return self._template % (await self._delegate(session, query, position),)
