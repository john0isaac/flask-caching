"""
flask_caching.core
~~~~~~~~~~~~~~~~~~~

The base :class:`_CacheCore` class: application wiring and the plain
backend proxy methods that :class:`~flask_caching.Cache` is built from.

:copyright: (c) 2010 by Thadeus Burgess.
:license: BSD, see LICENSE for more details.
"""

import hashlib
import warnings
from collections.abc import Callable
from typing import Any
from typing import cast

from cachelib.serializers import BaseSerializer
from flask import current_app
from flask import Flask
from werkzeug.exceptions import HTTPException
from werkzeug.utils import import_string

from .backends.base import BaseCache
from .backends.simplecache import SimpleCache
from .utils import normalize_timeout
from .utils import wants_args
from .utils import wants_extra_args

SUPPORTED_HASH_FUNCTIONS = [
    hashlib.sha1,
    hashlib.sha224,
    hashlib.sha256,
    hashlib.sha384,
    hashlib.sha512,
    hashlib.md5,
]


class _CacheCore:
    """Application wiring and the plain backend proxy methods shared by
    :class:`~flask_caching.Cache`.
    """

    def __init__(
        self,
        app: Flask | None = None,
        with_jinja2_ext: bool = True,
        config: dict[str, Any] | None = None,
    ) -> None:
        if not (config is None or isinstance(config, dict)):
            raise ValueError("`config` must be an instance of dict or None")

        self.with_jinja2_ext = with_jinja2_ext
        self.config = config

        self.source_check = None
        self.hash_method: Callable[..., Any] | None = None
        self.serializer: BaseSerializer | None = None
        self.enable_signals = False

        if app is not None:
            self.init_app(app, config)

    def init_app(self, app: Flask, config: dict[str, Any] | None = None) -> None:
        """This is used to initialize cache with your app object"""
        if not (config is None or isinstance(config, dict)):
            raise ValueError("`config` must be an instance of dict or None")

        #: Ref PR #44.
        #: Do not set self.app in the case a single instance of the Cache
        #: object is being used for multiple app instances.
        #: Example use case would be Cache shipped as part of a blueprint
        #: or utility library.

        base_config = app.config.copy()
        if self.config:
            base_config.update(self.config)
        if config:
            base_config.update(config)
        config = base_config

        config.setdefault("CACHE_DEFAULT_TIMEOUT", 300)
        config.setdefault("CACHE_IGNORE_ERRORS", False)
        config.setdefault("CACHE_THRESHOLD", 500)
        config.setdefault("CACHE_KEY_PREFIX", "flask_cache_")
        config.setdefault("CACHE_MEMCACHED_SERVERS", None)
        config.setdefault("CACHE_DIR", None)
        config.setdefault("CACHE_FILE_HASH_METHOD", hashlib.sha256)
        config.setdefault("CACHE_HASH_METHOD", hashlib.sha256)
        config.setdefault("CACHE_OPTIONS", None)
        config.setdefault("CACHE_ARGS", [])
        config.setdefault("CACHE_TYPE", "NullCache")
        config.setdefault("CACHE_NO_NULL_WARNING", False)
        config.setdefault("CACHE_SOURCE_CHECK", False)
        config.setdefault("CACHE_ENABLE_SIGNALS", False)
        config.setdefault("CACHE_SERIALIZER", None)

        if config["CACHE_TYPE"] == "NullCache" and not config["CACHE_NO_NULL_WARNING"]:
            warnings.warn(
                "Flask-Caching: CACHE_TYPE is set to NullCache, "
                "caching is effectively disabled.",
                stacklevel=2,
            )

        if config["CACHE_TYPE"] == "FileSystemCache" and config["CACHE_DIR"] is None:
            warnings.warn(
                f"Flask-Caching: CACHE_TYPE is set to {config['CACHE_TYPE']} but no "
                "CACHE_DIR is set.",
                stacklevel=2,
            )

        self.source_check = config["CACHE_SOURCE_CHECK"]
        self.enable_signals = config["CACHE_ENABLE_SIGNALS"]
        # Validated here rather than lazily so that a bad hash method is
        # reported at startup instead of on the first cached call.
        if not callable(config["CACHE_HASH_METHOD"]):
            raise ValueError(
                "`CACHE_HASH_METHOD` must be a hash constructor, for example "
                f"`hashlib.sha256`, not {config['CACHE_HASH_METHOD']!r}"
            )
        self.hash_method = config["CACHE_HASH_METHOD"]
        self.serializer = self._get_serializer(config["CACHE_SERIALIZER"])

        if self.with_jinja2_ext:
            from .jinja2ext import CacheExtension
            from .jinja2ext import JINJA_CACHE_ATTR_NAME

            setattr(app.jinja_env, JINJA_CACHE_ATTR_NAME, self)
            app.jinja_env.add_extension(CacheExtension)

        self._set_cache(app, config)

    def _set_cache(self, app: Flask, config: dict[str, Any]) -> None:
        import_me = config["CACHE_TYPE"]
        if "." not in import_me:
            import_me = "flask_caching.backends." + import_me

        cache_factory = import_string(import_me)
        cache_args = config["CACHE_ARGS"][:]
        cache_options = {
            "default_timeout": config["CACHE_DEFAULT_TIMEOUT"],
            "ignore_delete_many_errors": config["CACHE_IGNORE_ERRORS"],
        }

        if isinstance(cache_factory, type) and issubclass(cache_factory, BaseCache):
            cache_factory = cache_factory.factory

        if config["CACHE_OPTIONS"]:
            cache_options.update(config["CACHE_OPTIONS"])

        cache_options["default_timeout"] = normalize_timeout(
            cache_options["default_timeout"]
        )

        # Backends that are not created from cachelib read the timeout from
        # config instead of cache_options.
        config["CACHE_DEFAULT_TIMEOUT"] = cache_options["default_timeout"]

        if not hasattr(app, "extensions"):
            app.extensions = {}

        app.extensions.setdefault("cache", {})
        if import_me.find("cachelib") > -1:
            cache = cache_factory(*cache_args, **cache_options)
        else:
            cache = cache_factory(app, config, cache_args, cache_options)

        if self.serializer is not None:
            if hasattr(cache, "serializer"):
                cache.serializer = self.serializer  # pyright: ignore[reportAttributeAccessIssue]
            else:
                warnings.warn(
                    f"CACHE_SERIALIZER is set but {type(cache).__name__} does not use"
                    "a serializer.",
                    stacklevel=2,
                )

        app.extensions["cache"][self] = cache
        self.app = app

    def _get_serializer(self, serializer: Any) -> BaseSerializer | None:
        """Returns the serializer instance for the caching backend.
        If None, it will use the default one.
        """
        if serializer is None:
            return None

        if isinstance(serializer, type) and issubclass(serializer, BaseSerializer):
            try:
                return serializer()
            except TypeError as e:
                raise ValueError(
                    f"Couldn't instantiate serializer: {serializer!r}!"
                ) from e

        if not isinstance(serializer, BaseSerializer):
            raise ValueError(
                "`CACHE_SERIALIZER` must be a `cachelib.serializers.BaseSerializer` "
                "subclass or instance!"
            )

        return serializer

    def _get_hash_method(
        self, hash_method: Callable[..., Any] | None
    ) -> Callable[..., Any]:
        """Returns the hash method for the cache keys. Defaults to hashlib.sha256"""
        if hash_method is not None:
            return hash_method
        return self.hash_method or hashlib.sha256

    def _get_source_check(self, source_check: bool | None) -> bool | None:
        """Resolve whether the function's source belongs in the cache key."""
        if source_check is not None:
            return source_check
        return self.source_check

    def _call_fn(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        ensure_sync = getattr(self.app, "ensure_sync", None)
        if ensure_sync is not None:
            return ensure_sync(fn)(*args, **kwargs)
        return fn(*args, **kwargs)

    def _call_fn_or_exception(
        self, fn: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        """Returns an ``HTTPException`` instead of propagating it."""
        try:
            return self._call_fn(fn, *args, **kwargs)
        except HTTPException as e:
            return e

    def _bypass_cache(
        self,
        unless: Callable[..., Any] | None,
        f: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        """Determines whether or not to bypass the cache by calling unless().
        Supports both unless() that takes in arguments and unless()
        that doesn't.
        """
        bypass_cache = False

        if callable(unless):
            # If unless() takes args, pass them in.
            if wants_args(unless):
                if unless(f, *args, **kwargs) is True:
                    bypass_cache = True
            elif unless() is True:
                bypass_cache = True

        return bypass_cache

    def _forced_update(
        self,
        forced_update: Callable[..., Any] | None,
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        if not callable(forced_update):
            return False

        # If forced_update() takes args, pass them in.
        if wants_args(forced_update):
            return forced_update(*args, **kwargs) is True

        return forced_update() is True

    def _is_stale(
        self,
        is_stale: Callable[..., Any] | None,
        rv: Any,
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        if not callable(is_stale):
            return False

        # If is_stale() takes args besides the cached value, pass them in.
        if wants_extra_args(is_stale):
            return is_stale(rv, *args, **kwargs) is True

        return is_stale(rv) is True

    @property
    def cache(self) -> SimpleCache:
        """The backend instance the proxy methods delegate to. Use this to
        reach backend specific functionality that ``Cache`` does not proxy.
        Requires an application context.
        """
        app = current_app or self.app
        return cast("SimpleCache", app.extensions["cache"][self])

    def get(self, *args: Any, **kwargs: Any) -> Any:
        """Proxy function for internal cache object."""
        return self.cache.get(*args, **kwargs)

    def has(self, *args: Any, **kwargs: Any) -> bool:
        """Proxy function for internal cache object."""
        return self.cache.has(*args, **kwargs)

    def set(self, *args: Any, **kwargs: Any) -> bool | None:
        """Proxy function for internal cache object."""
        return self.cache.set(*args, **kwargs)

    def add(self, *args: Any, **kwargs: Any) -> bool:
        """Proxy function for internal cache object."""
        return self.cache.add(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> bool:
        """Proxy function for internal cache object."""
        return self.cache.delete(*args, **kwargs)

    def delete_many(self, *args: Any, **kwargs: Any) -> list[str]:
        """Proxy function for internal cache object."""
        return self.cache.delete_many(*args, **kwargs)

    def clear(self) -> bool:
        """Proxy function for internal cache object."""
        return self.cache.clear()

    def get_many(self, *args: Any, **kwargs: Any) -> list[Any]:
        """Proxy function for internal cache object."""
        return self.cache.get_many(*args, **kwargs)

    def set_many(self, *args: Any, **kwargs: Any) -> list[Any]:
        """Proxy function for internal cache object."""
        return self.cache.set_many(*args, **kwargs)

    def get_dict(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Proxy function for internal cache object."""
        return self.cache.get_dict(*args, **kwargs)

    def unlink(self, *args: Any, **kwargs: Any) -> list[str]:
        """Proxy function for internal cache object
        only support Redis
        """
        unlink = getattr(self.cache, "unlink", None)
        if unlink is not None and callable(unlink):
            return cast("list[str]", unlink(*args, **kwargs))
        return self.delete_many(*args, **kwargs)
