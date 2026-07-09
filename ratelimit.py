from slowapi import Limiter
from slowapi.util import get_remote_address

# ponytail: in-memory store — fine for one process. For multi-worker, point storage_uri at Redis.
limiter = Limiter(key_func=get_remote_address)
