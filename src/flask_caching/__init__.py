"""
flask_caching
~~~~~~~~~~~~~

Adds cache support to your application.

:copyright: (c) 2010 by Thadeus Burgess.
:license: BSD, see LICENSE for more details.
"""

from ._memoization import VERSION_TIMEOUT
from .cache import Cache
from .core import SUPPORTED_HASH_FUNCTIONS
from .responses import CachedResponse
from .signals import cache_memoize_hit
from .signals import cache_memoize_miss
from .signals import cache_view_hit
from .signals import cache_view_miss
from .utils import function_namespace
from .utils import make_template_fragment_key

__all__ = (
    "Cache",
    "CachedResponse",
    "SUPPORTED_HASH_FUNCTIONS",
    "VERSION_TIMEOUT",
    "cache_memoize_hit",
    "cache_memoize_miss",
    "cache_view_hit",
    "cache_view_miss",
    "function_namespace",
    "make_template_fragment_key",
)
