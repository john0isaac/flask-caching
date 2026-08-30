"""
flask_caching._memoization
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The :meth:`~flask_caching.Cache.memoize` decorator and its supporting
:class:`_MemoizationMixin`.

:copyright: (c) 2010 by Thadeus Burgess.
:license: BSD, see LICENSE for more details.
"""

import base64
import functools
import inspect
import logging
import uuid
from collections import OrderedDict
from collections.abc import Callable
from typing import Any
from typing import cast

from ._typing import _AnyMemoizedFunction
from ._typing import _MemoizedFunction
from ._typing import P
from ._typing import R
from .core import _CacheCore
from .signals import cache_memoize_hit as cache_memoize_hit
from .signals import cache_memoize_miss as cache_memoize_miss
from .utils import _Timeout
from .utils import function_namespace
from .utils import get_arg_default
from .utils import get_arg_names
from .utils import get_id
from .utils import join_generator
from .utils import normalize_timeout

logger = logging.getLogger(__name__)

# The initial version timeout of a memoize version key. Will be overwritten on the first
# write with the memoize value timeout
VERSION_TIMEOUT = 0


class _MemoizationMixin(_CacheCore):
    """Adds :meth:`memoize` function memoization to
    :class:`~flask_caching.Cache`.
    """

    def _memvname(self, funcname: str) -> str:
        return funcname + "_memver"

    def _memoize_make_version_hash(self) -> str:
        return base64.b64encode(uuid.uuid4().bytes)[:6].decode("utf-8")

    def _memoize_version(
        self,
        f: Callable[..., Any],
        args: Any | None = None,
        kwargs: dict[str, Any] | None = None,
        reset: bool = False,
        delete: bool = False,
        refresh: bool = False,
        timeout: int | None = VERSION_TIMEOUT,
        args_to_ignore: list[str] | None = None,
    ) -> tuple[str, str] | tuple[str, None]:
        """Updates the hash version associated with a memoized function or
        method.
        """
        fname, instance_fname = function_namespace(f, args=args)
        version_key = self._memvname(fname)
        fetch_keys = [version_key]

        args_to_ignore = args_to_ignore or []
        if "self" in args_to_ignore:
            instance_fname = None

        if instance_fname:
            instance_version_key = self._memvname(instance_fname)
            fetch_keys.append(instance_version_key)

        # Only delete the per-instance version key or per-function version
        # key but not both.
        if delete:
            self.delete_many(fetch_keys[-1])
            return fname, None

        version_data_list = list(self.get_many(*fetch_keys))
        dirty = refresh

        if version_data_list[0] is None:
            version_data_list[0] = self._memoize_make_version_hash()
            dirty = True

        if instance_fname and version_data_list[1] is None:
            version_data_list[1] = self._memoize_make_version_hash()
            dirty = True

        # Only reset the per-instance version or the per-function version
        # but not both.
        if reset:
            fetch_keys = fetch_keys[-1:]
            version_data_list = [self._memoize_make_version_hash()]
            dirty = True

        if dirty:
            self.set_many(
                dict(zip(fetch_keys, version_data_list, strict=False)),
                timeout=timeout,
            )

        return fname, "".join(version_data_list)

    def _memoize_make_cache_key(
        self,
        make_name: Callable[..., str] | None = None,
        hash_method: Callable[..., Any] | None = None,
        source_check: bool | None = None,
        args_to_ignore: list[str] | None = None,
    ) -> Callable[..., str]:
        """Function used to create the cache_key for memoized functions."""

        def make_cache_key(f: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
            fname, version_data = self._memoize_version(
                f,
                args=args,
                kwargs=kwargs,
                args_to_ignore=args_to_ignore,
            )

            #: this should have to be after version_data, so that it
            #: does not break the delete_memoized functionality.
            altfname = make_name(fname) if callable(make_name) else fname

            if callable(f):
                keyargs, keykwargs = self._memoize_kwargs_to_args(
                    f, *args, **kwargs, args_to_ignore=args_to_ignore
                )
            else:
                keyargs, keykwargs = args, kwargs

            updated = f"{altfname}{keyargs}{keykwargs}"

            cache_hash = self._get_hash_method(hash_method)()
            cache_hash.update(updated.encode("utf-8"))

            # Use the source code if source_check is True and update the
            # cache_key with the function's source.
            if self._get_source_check(source_check) and callable(f):
                func_source_code = inspect.getsource(f)
                cache_hash.update(func_source_code.encode("utf-8"))

            cache_key = base64.b64encode(cache_hash.digest())[:16].decode("utf-8")
            cache_key += version_data or ""

            return cache_key

        return make_cache_key

    def _memoize_kwargs_to_args(
        self, f: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        #: Inspect the arguments to the function
        #: This allows the memoization to be the same
        #: whether the function was called with
        #: 1, b=2 is equivalent to a=1, b=2, etc.
        new_args = []
        arg_num = 0
        args_to_ignore = kwargs.pop("args_to_ignore", None) or []

        # If the function uses VAR_KEYWORD type of parameters,
        # we need to pass these further
        kw_keys_remaining = [key for key in kwargs if key not in args_to_ignore]
        arg_names = get_arg_names(f)
        args_len = len(arg_names)

        for i in range(args_len):
            arg_default = get_arg_default(f, i)
            if arg_names[i] in args_to_ignore:
                arg = None
                arg_num += 1
            elif i == 0 and arg_names[i] in ("self", "cls"):
                #: use the id func of the class instance
                #: this supports instance methods for
                #: the memoized functions, giving more
                #: flexibility to developers
                if not args:
                    raise ValueError(
                        "When using `delete_memoized` on a "
                        f"`{'classmethod' if arg_names[i] == 'cls' else 'method'}` "
                        f"you must provide the `{arg_names[i]}` argument "
                        "as the first positional argument."
                    )
                arg = get_id(args[0])
                arg_num += 1
            elif arg_names[i] in kwargs:
                arg = kwargs[arg_names[i]]
                kw_keys_remaining.pop(kw_keys_remaining.index(arg_names[i]))
            elif arg_num < len(args):
                arg = args[arg_num]
                arg_num += 1
            elif arg_default is not None:
                arg = arg_default
                arg_num += 1
            else:
                arg = None
                arg_num += 1

            #: Attempt to convert all arguments to a
            #: hash/id or a representation?
            #: Not sure if this is necessary, since
            #: using objects as keys gets tricky quickly.
            # if hasattr(arg, '__class__'):
            #     try:
            #         arg = hash(arg)
            #     except:
            #         arg = get_id(arg)

            #: Or what about a special __cacherepr__ function
            #: on an object, this allows objects to act normal
            #: upon inspection, yet they can define a representation
            #: that can be used to make the object unique in the
            #: cache key. Given that a case comes across that
            #: an object "must" be used as a cache key
            # if hasattr(arg, '__cacherepr__'):
            #     arg = arg.__cacherepr__

            new_args.append(arg)

        new_args.extend(args[len(arg_names) :])
        return (
            tuple(new_args),
            OrderedDict(
                sorted((k, v) for k, v in kwargs.items() if k in kw_keys_remaining)
            ),
        )

    def memoize(
        self,
        timeout: _Timeout | None = None,
        make_name: Callable[..., str] | None = None,
        unless: Callable[..., bool] | None = None,
        forced_update: Callable[..., bool] | None = None,
        is_stale: Callable[..., bool] | None = None,
        response_filter: Callable[..., Any] | None = None,
        hash_method: Callable[..., Any] | None = None,
        cache_none: bool = False,
        source_check: bool | None = None,
        args_to_ignore: list[str] | None = None,
    ) -> Callable[[Callable[P, R]], _MemoizedFunction[P, R]]:
        """Use this to cache the result of a function, taking its arguments
        into account in the cache key.

        Information on
        `Memoization <http://en.wikipedia.org/wiki/Memoization>`_.

        Example::

            @cache.memoize(timeout=50)
            def big_foo(a, b):
                return a + b + random.randrange(0, 1000)

        .. code-block:: pycon

            >>> big_foo(5, 2)
            753
            >>> big_foo(5, 3)
            234
            >>> big_foo(5, 2)
            753

        .. versionadded:: 0.4
            The returned decorated function now has three function attributes
            assigned to it.

                **uncached**
                    The original undecorated function. readable only

                **cache_timeout**
                    The cache timeout value for this function.
                    For a custom value to take affect, this must be
                    set before the function is called.

                    readable and writable

                **make_cache_key**
                    A function used in generating the cache_key used.

                    readable and writable


        :param timeout: Default None. If set to an integer, will cache for that
                        amount of time. Unit of time is in seconds. A
                        ``datetime.timedelta`` is also accepted and is rounded
                        up to whole seconds.

        :param make_name: Default None. If set this is a function that accepts
                          a single argument, the function name, and returns a
                          new string to be used as the function name.
                          If not set then the function name is used.

        :param unless: Default None. Cache will *always* execute the caching
                       facilities unless this callable is true.
                       This will bypass the caching entirely.

        :param forced_update: Default None. If this callable is true,
                              cache value will be updated regardless cache
                              is expired or not. Useful for background
                              renewal of cached functions.

        :param is_stale: Default None. Called on a cache hit with the cached
                         value as its first argument. If it is true the cached
                         value will be recomputed. If the callable accepts more
                         than one argument, the calls own arguments are passed
                         after the cached value.

        :param response_filter: Default None. If not None, the callable is
                                invoked after the cached funtion evaluation,
                                and is given one arguement, the response
                                content. If the callable returns False, the
                                content will not be cached. Useful to prevent
                                caching of code 500 responses.
        :param hash_method: Default None. If ``None``, the value is set by
                            ``CACHE_HASH_METHOD``, which itself defaults to
                            ``hashlib.sha256``. The hash method used to
                            generate the keys for cached results.

        :param cache_none: Default False. If set to True, add a key exists
                           check when cache.get returns None. This will likely
                           lead to wrongly returned None values in concurrent
                           situations and is not recommended to use.

        :param source_check: Default None. If None will use the value set by
                             CACHE_SOURCE_CHECK.
                             If True, include the function's source code in the
                             hash to avoid using cached values when the source
                             code has changed and the input values remain the
                             same. This ensures that the cache_key will be
                             formed with the function's source code hash in
                             addition to other parameters that may be included
                             in the formation of the key.

        :param args_to_ignore: List of arguments that will be ignored while
                               generating the cache key. Default to None.
                               This means that those arguments may change
                               without affecting the cache value that will be
                               returned.

        .. versionadded:: 0.5
            params ``make_name``, ``unless``

        .. versionadded:: 1.10
            params ``args_to_ignore``
        """

        def memoize(f: Callable[P, R]) -> _MemoizedFunction[P, R]:
            @functools.wraps(f)
            def decorated_function(*args: Any, **kwargs: Any) -> Any:
                #: bypass cache
                if self._bypass_cache(unless, f, *args, **kwargs):
                    return self._call_fn(f, *args, **kwargs)

                try:
                    forced_update_result = self._forced_update(
                        forced_update, *args, **kwargs
                    )

                    cache_key = self._memoize_make_cache_key(
                        make_name=make_name,
                        hash_method=hash_method,
                        source_check=source_check,
                        args_to_ignore=args_to_ignore,
                    )(f, *args, **kwargs)

                    if forced_update_result:
                        rv = None
                        found = False
                    else:
                        rv = self.get(cache_key)
                        found = True

                        # If the value returned by cache.get() is None, it
                        # might be because the key is not found in the cache
                        # or because the cached value is actually None
                        if rv is None:
                            # If we're sure we don't need to cache None values
                            # (cache_none=False), don't bother checking for
                            # key existence, as it can lead to false positives
                            # if a concurrent call already cached the
                            # key between steps. This would cause us to
                            # return None when we shouldn't
                            if not cache_none:
                                found = False
                            else:
                                found = self.has(cache_key)

                        if found and self._is_stale(is_stale, rv, *args, **kwargs):
                            rv = None
                            found = False
                except Exception:
                    if self.app.debug:
                        raise
                    logger.exception("Exception possibly due to cache backend.")
                    return self._call_fn(f, *args, **kwargs)

                if self.enable_signals:
                    signal = cache_memoize_hit if found else cache_memoize_miss
                    signal.send(
                        cache=self, cache_key=cache_key, f=f, args=args, kwargs=kwargs
                    )

                if not found:
                    rv = self._call_fn(f, *args, **kwargs)
                    if inspect.isgenerator(rv):
                        rv = join_generator(rv)

                    if response_filter is None or response_filter(rv):
                        cache_timeout = normalize_timeout(memoized_fn.cache_timeout)

                        try:
                            self.set(
                                cache_key,
                                rv,
                                timeout=cache_timeout,
                            )
                            # update the memoize version with the new cache_timeout
                            self._memoize_version(
                                f,
                                args=args,
                                kwargs=kwargs,
                                refresh=True,
                                timeout=cache_timeout,
                                args_to_ignore=args_to_ignore,
                            )
                        except Exception:
                            if self.app.debug:
                                raise
                            logger.exception("Exception possibly due to cache backend.")
                return rv

            memoized_fn = cast("_MemoizedFunction[P, R]", decorated_function)
            memoized_fn.uncached = f
            memoized_fn.cache_timeout = timeout
            memoized_fn.make_cache_key = self._memoize_make_cache_key(
                make_name=make_name,
                hash_method=hash_method,
                source_check=source_check,
                args_to_ignore=args_to_ignore,
            )
            # Equivalent to passing ``f``: ``function_namespace`` reads only
            # dunders copied by ``functools.wraps`` and a signature that
            # follows ``__wrapped__``.
            memoized_fn.delete_memoized = lambda: self.delete_memoized(memoized_fn)
            return memoized_fn

        return memoize

    def delete_memoized(
        self, f: _AnyMemoizedFunction, *args: Any, **kwargs: Any
    ) -> None:
        """Deletes the specified functions caches, based by given parameters.
        If parameters are given, only the functions that were memoized
        with them will be erased. Otherwise all versions of the caches
        will be forgotten.

        Example::

            @cache.memoize(50)
            def random_func():
                return random.randrange(1, 50)

            @cache.memoize()
            def param_func(a, b):
                return a+b+random.randrange(1, 50)

        .. code-block:: pycon

            >>> random_func()
            43
            >>> random_func()
            43
            >>> cache.delete_memoized(random_func)
            >>> random_func()
            16
            >>> param_func(1, 2)
            32
            >>> param_func(1, 2)
            32
            >>> param_func(2, 2)
            47
            >>> cache.delete_memoized(param_func, 1, 2)
            >>> param_func(1, 2)
            13
            >>> param_func(2, 2)
            47

        Delete memoized is also smart about instance methods vs class methods.

        When passing a instancemethod, it will only clear the cache related
        to that instance of that object. (object uniqueness can be overridden
        by defining the __repr__ method, such as user id).

        When passing a classmethod, it will clear all caches related across
        all instances of that class.

        Example::

            class Adder(object):
                @cache.memoize()
                def add(self, b):
                    return b + random.random()

        .. code-block:: pycon

            >>> adder1 = Adder()
            >>> adder2 = Adder()
            >>> adder1.add(3)
            3.23214234
            >>> adder2.add(3)
            3.60898509
            >>> cache.delete_memoized(adder1.add)
            >>> adder1.add(3)
            3.01348673
            >>> adder2.add(3)
            3.60898509
            >>> cache.delete_memoized(Adder.add)
            >>> adder1.add(3)
            3.53235667
            >>> adder2.add(3)
            3.72341788

        Arguments narrow the deletion down to a single call. A bound method
        supplies its own instance, so only the remaining arguments are given:

        .. code-block:: pycon

            >>> cache.delete_memoized(adder1.add, 3)

        When the function is reached through the class instead, the instance
        has to be passed explicitly, the same way a class is passed for a
        ``@classmethod``:

        .. code-block:: pycon

            >>> cache.delete_memoized(Adder.add, adder1, 3)

        .. versionchanged:: 2.5.0

            A bound method no longer needs to be given its own instance as the
            first argument. Passing it explicitly keeps working.

        :param fname: The memoized function.
        :param \\*args: A list of positional parameters used with
                       memoized function.
        :param \\**kwargs: A dict of named parameters used with
                          memoized function.

        .. note::

            Flask-Caching uses inspect to order kwargs into positional args when
            the function is memoized. If you pass a function reference into
            ``fname``, Flask-Caching will be able to place the args/kwargs in
            the proper order, and delete the positional cache.

            However, if ``delete_memoized`` is just called with the name of the
            function, be sure to pass in potential arguments in the same order
            as defined in your function as args only, otherwise Flask-Caching
            will not be able to compute the same cache key and delete all
            memoized versions of it.

        .. note::

            Flask-Caching maintains an internal random version hash for
            the function. Using delete_memoized will only swap out
            the version hash, causing the memoize function to recompute
            results and put them into another key.

            This leaves any computed caches for this memoized function within
            the caching backend.

            It is recommended to use a very high timeout with memoize if using
            this function, so that when the version hash is swapped, the old
            cached results would eventually be reclaimed by the caching
            backend.
        """
        if not callable(f):
            raise TypeError(
                "Deleting messages by relative name is not supported, please "
                "use a function reference."
            )

        if not (args or kwargs):
            self._memoize_version(f, reset=True)
        else:
            args = self._ensure_self_arg(f, args)
            cache_key = f.make_cache_key(f.uncached, *args, **kwargs)
            self.delete(cache_key)

    @staticmethod
    def _ensure_self_arg(
        f: _AnyMemoizedFunction, args: tuple[Any, ...]
    ) -> tuple[Any, ...]:
        """Supply the ``self`` argument when a bound method is passed.

        ``make_cache_key`` works on the undecorated function, so the instance
        has to be part of ``args`` to compute the same key that was used when
        the value was cached. A bound method already carries it, so passing it
        again is redundant::

            cache.delete_memoized(adder.add, 3)

        Passing it explicitly keeps working, so that the form previously
        required for instance methods is not broken.
        """
        instance = getattr(f, "__self__", None)

        if instance is None or inspect.isclass(instance):
            return args

        arg_names = get_arg_names(f.uncached)

        if not arg_names or arg_names[0] != "self" or (args and args[0] is instance):
            return args

        return (instance, *args)

    def delete_memoized_verhash(self, f: _AnyMemoizedFunction, *args: Any) -> None:
        """Delete the version hash associated with the function.

        .. warning::

            Performing this operation could leave keys behind that have
            been created with this version hash. It is up to the application
            to make sure that all keys that may have been created with this
            version hash at least have timeouts so they will not sit orphaned
            in the cache backend.
        """
        if not callable(f):
            raise TypeError(
                "Deleting messages by relative name is not supported, please"
                "use a function reference."
            )

        self._memoize_version(f, delete=True)
