class ValidationError(ValueError):
    pass

def require_rows(rows):
    if type(rows) is not list:
        raise ValidationError("rows must be a list")
    if len(rows) > 5000:
        raise ValidationError("too many rows")
    for ordinal, row in enumerate(rows, 1):
        if type(row) is not dict:
            raise ValidationError("each row must be an object")
        if not 1 <= len(row) <= 64:
            raise ValidationError(f"row {ordinal} must contain 1..64 fields")
        for field, value in row.items():
            require_field(field)
            if type(value) not in (str, int, bool, type(None)):
                raise ValidationError(f"row {ordinal} field {field!r} must be a string, integer, boolean or null; represent exact decimals as strings")
    return rows


def require_field(field):
    if (type(field) is not str or not 1 <= len(field) <= 256
            or any(ord(char) < 32 or ord(char) == 127 for char in field)):
        raise ValidationError("field names must contain 1..256 characters without controls")
    return field


def require_fields(fields, name, limit):
    if type(fields) is not list or not 1 <= len(fields) <= limit:
        raise ValidationError(f"{name} must contain 1..{limit} field names")
    for field in fields:
        require_field(field)
    if len(fields) != len(set(fields)):
        raise ValidationError(f"{name} contains duplicate field names")
    return fields
