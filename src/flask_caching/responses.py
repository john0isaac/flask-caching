"""
flask_caching.responses
~~~~~~~~~~~~~~~~~~~~~~~~

:copyright: (c) 2010 by Thadeus Burgess.
:license: BSD, see LICENSE for more details.
"""

from flask import Response

from .utils import _Timeout
from .utils import normalize_timeout


class CachedResponse(Response):
    """
    views wraped by @cached can return this (which inherits from flask.Response)
    to override the cache TTL dynamically
    """

    timeout: int | None = None

    def __init__(self, response: Response, timeout: _Timeout | None) -> None:
        # ``CachedResponse`` adopts the state of an existing Response in
        # place rather than calling ``Response.__init__``; copying
        # ``__dict__`` preserves headers, status and body without having
        # to round-trip the response through Werkzeug's constructor.
        self.__dict__ = response.__dict__
        self.timeout = normalize_timeout(timeout)
