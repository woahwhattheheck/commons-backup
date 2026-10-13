def exact_equal(left, right):
    return type(left) is type(right) and left == right

def row_key(row, fields):
    return tuple(row[field] for field in fields)
