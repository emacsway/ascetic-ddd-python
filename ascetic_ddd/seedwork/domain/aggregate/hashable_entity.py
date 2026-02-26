from abc import ABCMeta, abstractmethod
from collections.abc import Hashable

from ascetic_ddd.specification.domain.interfaces import IEqualOperand

__all__ = ("HashableEntity",)


class HashableEntity(Hashable, metaclass=ABCMeta):
    @property
    @abstractmethod
    def id(self) -> IEqualOperand:  # noqa: A003 # id shadowing Python builtin
        """
        See also IsTransient
        https://github.com/dotnet-architecture/eShopOnContainers/blob/dev/src/Services/Ordering/Ordering.Domain/SeedWork/Entity.cs#L42.
        """
        raise NotImplementedError

    def __hash__(self):
        id_ = self.id
        assert id_ is not None, "Model instances without primary key value are unhashable"
        return hash(id_)

    def __eq__(self, other: IEqualOperand):
        assert isinstance(other, HashableEntity)
        return self.id == other.id
