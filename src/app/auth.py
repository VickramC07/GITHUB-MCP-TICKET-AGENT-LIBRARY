from typing import Union, Optional
from .user_repo import load_user
from .utils.string import sanitize_string

def get_user_profile(user_id: Optional[int]):
    """
    Get user profile with proper error handling.
    """
    # Handle None user_id
    if user_id is None:
        return {}
    
    user = load_user(user_id)  # may return {} or None-ish fields
    
    # Handle missing user or missing fields
    if not user:
        return {}
    
    # Safely get name and email with defaults
    name = sanitize_string(user.get("name", ""))
    email = sanitize_string(user.get("email", ""))
    
    return {"id": user_id, "name": name, "email": email}
