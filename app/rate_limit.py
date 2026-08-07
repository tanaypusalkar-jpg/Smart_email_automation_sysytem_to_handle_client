"""
One Limiter instance, shared everywhere. slowapi needs a single instance
registered on app.state.limiter (see main.py) - creating separate Limiter()
objects per router would track limits independently instead of together.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
