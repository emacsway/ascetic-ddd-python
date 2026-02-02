from ascetic_ddd.utils.json import JSONEncoder as _JSONEncoder
from ascetic_ddd.faker.domain.values.json import Json

__all__ = ("JSONEncoder",)


class JSONEncoder(_JSONEncoder):
    def default(self, o):
        if isinstance(o, Json):
            return o.obj
        return super().default(o)
