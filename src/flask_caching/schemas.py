"""
flask_caching.schemas
~~~~~~~~~~~~~~~~~~~~~~

Per-backend cache configuration dataclasses. ``cache_type`` acts as a
discriminator: each dataclass only exposes the fields relevant to that
backend. The :func:`CacheConfig` factory function is ``@overload``-ed per
``cache_type`` literal so editors only offer completions for the fields
that apply to the chosen backend.

:copyright: (c) 2010 by Thadeus Burgess.
:license: BSD, see LICENSE for more details.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import cast
from typing import Literal
from typing import overload

from cachelib.serializers import BaseSerializer


@dataclass
class _CommonCacheConfig:
    """Fields shared by every cache backend."""

    default_timeout: int = 300
    ignore_delete_many_errors: bool = False
    key_prefix: str = "flask_cache_"
    hash_method: Callable[..., Any] = hashlib.sha256
    no_null_warning: bool = False
    source_check: bool = False
    enable_signals: bool = False
    serializer: BaseSerializer | None = None


@dataclass
class NullCacheConfig(_CommonCacheConfig):
    """Configuration for :class:`~flask_caching.backends.nullcache.NullCache`."""

    cache_type: Literal["NullCache"] = "NullCache"


@dataclass
class SimpleCacheConfig(_CommonCacheConfig):
    """Configuration for :class:`~flask_caching.backends.simplecache.SimpleCache`."""

    cache_type: Literal["SimpleCache"] = "SimpleCache"
    threshold: int = 500


@dataclass
class FileSystemCacheConfig(_CommonCacheConfig):
    """Configuration for
    :class:`~flask_caching.backends.filesystemcache.FileSystemCache`.
    """

    cache_type: Literal["FileSystemCache"] = "FileSystemCache"
    cache_dir: Any = None
    threshold: int = 500
    file_hash_method: Callable[..., Any] = hashlib.sha256


@dataclass
class RedisCacheConfig(_CommonCacheConfig):
    """Configuration for :class:`~flask_caching.backends.rediscache.RedisCache`."""

    cache_type: Literal["RedisCache"] = "RedisCache"
    host: Any = "localhost"
    port: int = 6379
    password: str | None = None
    db: int = 0
    redis_url: str | None = None
    options: dict[str, Any] | None = None


@dataclass
class MemcachedCacheConfig(_CommonCacheConfig):
    """Configuration for :class:`~flask_caching.backends.memcache.MemcachedCache`."""

    cache_type: Literal["MemcachedCache"] = "MemcachedCache"
    memcached_servers: Any = None
    pool_size: int = 1
    pool_blocking: bool = True


@dataclass
class UWSGICacheConfig(_CommonCacheConfig):
    """Configuration for
    :class:`~flask_caching.contrib.uwsgicache.UWSGICache`.
    """

    cache_type: Literal["UWSGICache"] = "UWSGICache"
    args: list[Any] = field(default_factory=list)


AnyCacheConfig = (
    NullCacheConfig
    | SimpleCacheConfig
    | FileSystemCacheConfig
    | RedisCacheConfig
    | MemcachedCacheConfig
    | UWSGICacheConfig
)
"""Union of every backend config, for annotating "accepts any config" spots."""

_CACHE_TYPE_TO_CONFIG: dict[str, type[AnyCacheConfig]] = {
    "NullCache": NullCacheConfig,
    "SimpleCache": SimpleCacheConfig,
    "FileSystemCache": FileSystemCacheConfig,
    "RedisCache": RedisCacheConfig,
    "MemcachedCache": MemcachedCacheConfig,
    "UWSGICache": UWSGICacheConfig,
}


@overload
def CacheConfig(
    *,
    cache_type: Literal["NullCache"] = "NullCache",
    default_timeout: int = 300,
    ignore_delete_many_errors: bool = False,
    key_prefix: str = "flask_cache_",
    hash_method: Callable[..., Any] = hashlib.sha256,
    no_null_warning: bool = False,
    source_check: bool = False,
    enable_signals: bool = False,
    serializer: BaseSerializer | None = None,
) -> NullCacheConfig: ...
@overload
def CacheConfig(
    *,
    cache_type: Literal["SimpleCache"],
    default_timeout: int = 300,
    ignore_delete_many_errors: bool = False,
    key_prefix: str = "flask_cache_",
    hash_method: Callable[..., Any] = hashlib.sha256,
    no_null_warning: bool = False,
    source_check: bool = False,
    enable_signals: bool = False,
    serializer: BaseSerializer | None = None,
    threshold: int = 500,
) -> SimpleCacheConfig: ...
@overload
def CacheConfig(
    *,
    cache_type: Literal["FileSystemCache"],
    default_timeout: int = 300,
    ignore_delete_many_errors: bool = False,
    key_prefix: str = "flask_cache_",
    hash_method: Callable[..., Any] = hashlib.sha256,
    no_null_warning: bool = False,
    source_check: bool = False,
    enable_signals: bool = False,
    serializer: BaseSerializer | None = None,
    cache_dir: Any = None,
    threshold: int = 500,
    file_hash_method: Callable[..., Any] = hashlib.sha256,
) -> FileSystemCacheConfig: ...
@overload
def CacheConfig(
    *,
    cache_type: Literal["RedisCache"],
    default_timeout: int = 300,
    ignore_delete_many_errors: bool = False,
    key_prefix: str = "flask_cache_",
    hash_method: Callable[..., Any] = hashlib.sha256,
    no_null_warning: bool = False,
    source_check: bool = False,
    enable_signals: bool = False,
    serializer: BaseSerializer | None = None,
    host: Any = "localhost",
    port: int = 6379,
    password: str | None = None,
    db: int = 0,
    redis_url: str | None = None,
    options: dict[str, Any] | None = None,
) -> RedisCacheConfig: ...
@overload
def CacheConfig(
    *,
    cache_type: Literal["MemcachedCache"],
    default_timeout: int = 300,
    ignore_delete_many_errors: bool = False,
    key_prefix: str = "flask_cache_",
    hash_method: Callable[..., Any] = hashlib.sha256,
    no_null_warning: bool = False,
    source_check: bool = False,
    enable_signals: bool = False,
    serializer: BaseSerializer | None = None,
    memcached_servers: Any = None,
    pool_size: int = 1,
    pool_blocking: bool = True,
) -> MemcachedCacheConfig: ...
@overload
def CacheConfig(
    *,
    cache_type: Literal["UWSGICache"],
    default_timeout: int = 300,
    ignore_delete_many_errors: bool = False,
    key_prefix: str = "flask_cache_",
    hash_method: Callable[..., Any] = hashlib.sha256,
    no_null_warning: bool = False,
    source_check: bool = False,
    enable_signals: bool = False,
    serializer: BaseSerializer | None = None,
    args: list[Any] | None = None,
) -> UWSGICacheConfig: ...
def CacheConfig(*, cache_type: str = "NullCache", **kwargs: Any) -> AnyCacheConfig:
    """Build the config dataclass matching ``cache_type``.

    A single, discoverable entry point: pass ``cache_type="RedisCache"`` (etc.)
    and get completion for only that backend's fields, via the ``@overload``
    signatures above.
    """
    try:
        config_cls = _CACHE_TYPE_TO_CONFIG[cache_type]
    except KeyError:
        raise ValueError(f"Unknown cache_type: {cache_type!r}") from None
    # The overloads above are what give call sites their precise typing;
    # the implementation itself only needs to satisfy the return type.
    return cast("Any", config_cls)(cache_type=cache_type, **kwargs)
