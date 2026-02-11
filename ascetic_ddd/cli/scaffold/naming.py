import re

from ascetic_ddd.cli.scaffold.model import CollectionKind, PRIMITIVE_TYPES


def camel_to_snake(name):
    # Handle sequences like "UserId" -> "User_Id" -> "user_id"
    # First pass: insert _ before uppercase letters that follow lowercase/digits
    s1 = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)
    # Second pass: insert _ between consecutive uppercase letters followed by lowercase
    s2 = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', s1)
    return s2.lower()


def strip_underscore_prefix(name):
    if name.startswith('_'):
        return name[1:]
    return name


def is_collection_type(type_str):
    return type_str.startswith('list[') or type_str.startswith('tuple[')


def extract_inner_type(type_str):
    # "list[SpecializationId]" -> "SpecializationId"
    # "tuple[EmploymentType, ...]" -> "EmploymentType"
    match = re.match(r'(?:list|tuple)\[([A-Za-z_]\w*)', type_str)
    if match:
        return match.group(1)
    return type_str


def collection_kind(type_str):
    if type_str.startswith('list['):
        return CollectionKind.LIST
    if type_str.startswith('tuple['):
        return CollectionKind.TUPLE
    return CollectionKind.NONE


def is_primitive_type(type_str):
    return type_str in PRIMITIVE_TYPES
