from abc import ABCMeta, abstractmethod

__all__ = ('IO2MDistributor',)


class IO2MDistributor(metaclass=ABCMeta):
    """
    O2M distributor interface.

    Unlike M2O (which selects a parent for each child),
    O2M determines how many children to create for each parent.

    Stateless: each distribute() call is independent.
    Suitable for multi-threaded usage.

    Example:
        dist = SkewDistributor(skew=2.0, mean=50)

        for _ in range(companies_count):
            company = create_company()
            devices_count = dist.distribute()  # mean = 50
            create_devices(company, devices_count)
    """

    @abstractmethod
    def distribute(self) -> int:
        """
        Returns the number of items for the current owner.

        Returns:
            Random number of items. Average across all calls = mean.
        """
        raise NotImplementedError
