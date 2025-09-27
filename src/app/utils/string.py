def sanitize_string(s):
    """
    Sanitize string by trimming whitespace and handling None values.
    """
    if s is None:
        return ""
    return str(s).strip()
