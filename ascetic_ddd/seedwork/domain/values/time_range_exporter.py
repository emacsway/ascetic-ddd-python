import datetime

from ascetic_ddd.seedwork.domain.values.time_range import ITimeRangeExporter

__all__ = ("TimeRangeExporter",)


class TimeRangeExporter(ITimeRangeExporter):
    data: dict[str, datetime.datetime | None]

    def __init__(self) -> None:
        self.data = {}

    def set_lower(self, value: datetime.datetime | None) -> None:
        self.data["lower"] = value

    def set_upper(self, value: datetime.datetime | None) -> None:
        self.data["upper"] = value
