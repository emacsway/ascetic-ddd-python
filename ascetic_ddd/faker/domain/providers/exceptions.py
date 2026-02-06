import typing

__all__ = ('DiamondUpdateConflict',)


class DiamondUpdateConflict(Exception):
    """
    Conflict when trying to set different values to the same provider.

    Occurs in diamond dependency graphs where multiple paths lead to the same provider
    with conflicting values.

    Example:
        Provider A references Provider C with value 5
        Provider B references Provider C with value 7
        When both paths merge at C -> DiamondUpdateConflict
    """

    def __init__(
        self,
        existing_value: typing.Any,
        new_value: typing.Any,
        provider_name: str | None = None
    ):
        self.existing_value = existing_value
        self.new_value = new_value
        self.provider_name = provider_name
        super().__init__(
            f"Diamond update conflict in '{provider_name}': "
            f"cannot merge {existing_value!r} with {new_value!r}"
        )
