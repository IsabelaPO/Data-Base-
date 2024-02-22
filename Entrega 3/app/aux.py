def has_digits(name):
    for char in name:
        if char.isdigit():
            return True
    return False