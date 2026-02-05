
__all__ = ("hashable", "freeze", "is_subset", "deepmerge",)


def hashable(o):
    if isinstance(o, dict):
        return tuple(sorted((k, hashable(v)) for k, v in o.items()))
    if isinstance(o, list):
        return tuple([hashable(v) for v in sorted(o)])
    return o


def freeze(o):
    if isinstance(o, dict):
        return frozenset(sorted((k, freeze(v)) for k, v in o.items()))
    if isinstance(o, list):
        return frozenset([freeze(v) for v in sorted(o)])
    return o


def is_subset(sub, master):
    """
    Recursively checks if 'sub' is a subset of 'master'.
    Works with nested dicts and lists of dicts.
    """
    # 1. Handle Dictionaries
    if isinstance(sub, dict):
        if not isinstance(master, dict):
            return False
        # Every key in the subset must exist in the master and match the subset's criteria
        return all(k in master and is_subset(sub[k], master[k]) for k in sub)

    # 2. Handle Lists (Subset logic: every item in 'sub' must exist in 'master')
    elif isinstance(sub, list):
        if not isinstance(master, list):
            return False
        # Each item in the subset list must have at least one match in the master list
        return all(any(is_subset(sub_item, master_item) for master_item in master) for sub_item in sub)

    # 3. Handle Primitive Values (Strings, Ints, etc.)
    else:
        return sub == master


def deepmerge(destination, source):
    """
    >>> a = { 'first' : { 'all_rows' : { 'pass' : 'dog', 'number' : '1' } } }
    >>> b = { 'first' : { 'all_rows' : { 'fail' : 'cat', 'number' : '5' } } }
    >>> deepmerge(b, a) == { 'first' : { 'all_rows' : { 'pass' : 'dog', 'fail' : 'cat', 'number' : '5' } } }
    True
    """

    if isinstance(source, dict):
        assert isinstance(destination, dict)
        for key, value in source.items():
            if key in destination:
                deepmerge(destination[key], value)
            else:
                destination[key] = value

    elif isinstance(source, list):
        assert isinstance(destination, list)
        for index, value in enumerate(source):
            if isinstance(value, dict) and index < len(destination):
                deepmerge(destination[index], value)
            elif value not in destination:
                destination.append(value)

    return destination
