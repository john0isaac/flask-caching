"""
flask_caching.cache
~~~~~~~~~~~~~~~~~~~~

The concrete :class:`Cache` class, composed from :class:`_ViewCachingMixin`
and :class:`_MemoizationMixin`.

:copyright: (c) 2010 by Thadeus Burgess.
:license: BSD, see LICENSE for more details.
"""

from ._memoization import _MemoizationMixin
from ._view_caching import _ViewCachingMixin


class Cache(_ViewCachingMixin, _MemoizationMixin):
    """This class is used to control the cache objects."""
