from typing import Optional

_FAKE_DB = {
    1: {"name": "  Alice  ", "email": "alice@example.com "},
    2: {"name": None, "email": "bob@example.com"},
    # 3 is missing to simulate absent user
}

def load_user(user_id: Optional[int]):
    """
    Bug #3: returns {} for unknown user instead of a safe shape.
    """
    if user_id not in _FAKE_DB:
        return {}  # BUG: callers expect keys to exist or a safe default object
    return _FAKE_DB[user_id]
