class RoutingError(Exception):
    pass


def resolve_department(category):
    """Department responsible for `category`, read from the Category -> Department mapping.

    Nothing is hardcoded: remapping a category in the database changes routing.
    """
    if not category.is_active:
        raise RoutingError("Category is not active.")
    department = category.department
    if not department.is_active:
        raise RoutingError("Department is not active.")
    return department
