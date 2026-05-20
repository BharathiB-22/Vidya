from slowapi import Limiter
from slowapi.util import get_remote_address

# Shared limiter instance used by all routers and SlowAPIMiddleware.
# default_limits applies globally to every route when SlowAPIMiddleware is active.
# 600/minute accommodates shared NAT/proxy environments in universities where many
# users share a single egress IP.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["600/minute"],
)
