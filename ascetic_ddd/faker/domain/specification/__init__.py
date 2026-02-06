"""
Specification patterns for faker domain.
"""

from ascetic_ddd.faker.domain.specification.query_specification import QuerySpecification
from ascetic_ddd.faker.domain.specification.query_resolvable_specification import QueryResolvableSpecification
from ascetic_ddd.faker.domain.specification.query_lookup_specification import QueryLookupSpecification

__all__ = (
    'QuerySpecification',
    'QueryResolvableSpecification',
    'QueryLookupSpecification',
)
