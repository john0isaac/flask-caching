"""
flask_caching._typing
~~~~~~~~~~~~~~~~~~~~~~

Typing helpers shared by :mod:`flask_caching.core` and the view-caching
and memoization mixins it is built from.

:copyright: (c) 2010 by Thadeus Burgess.
:license: BSD, see LICENSE for more details.
"""

from collections.abc import Callable
from typing import Any
from typing import Concatenate
from typing import overload
from typing import ParamSpec
from typing import Protocol
from typing import TypeAlias
from typing import TypeVar

from .utils import _Timeout

P = ParamSpec("P")
# The parameters left over after ``__get__`` binds the instance.
P2 = ParamSpec("P2")
R = TypeVar("R")
T = TypeVar("T")
# ``uncached`` is read-only on the bound protocols, so their instance and
# return types are contravariant and covariant respectively.
T_co = TypeVar("T_co", covariant=True)
T_contra = TypeVar("T_contra", contravariant=True)


class _BoundCachedFunction(Protocol[T_contra, P, T_co]):
    """The type of a :meth:`Cache.cached` method accessed on an instance."""

    cache_timeout: _Timeout | None
    make_cache_key: Callable[..., str]

    @property
    def uncached(self) -> Callable[Concatenate[T_contra, P], T_co]: ...

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T_co: ...


class _CachedFunction(Protocol[P, R]):
    """The type of the callable returned by :meth:`Cache.cached`."""

    uncached: Callable[P, R]
    cache_timeout: _Timeout | None
    make_cache_key: Callable[..., str]

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R: ...

    # The decorator returns a function, so decorating a method keeps working
    # at runtime. Without ``__get__`` type checkers see a plain attribute
    # instead of a descriptor and never bind ``self``.
    @overload
    def __get__(
        self, instance: None, owner: type | None = None, /
    ) -> "_CachedFunction[P, R]": ...
    @overload
    def __get__(
        self: "_CachedFunction[Concatenate[T, P2], R]",
        instance: T,
        owner: type | None = None,
        /,
    ) -> _BoundCachedFunction[T, P2, R]: ...
    def __get__(self, instance: Any, owner: type | None = None, /) -> Any: ...


class _BoundMemoizedFunction(Protocol[T_contra, P, T_co]):
    """The type of a :meth:`Cache.memoize` method accessed on an instance."""

    cache_timeout: _Timeout | None
    make_cache_key: Callable[..., str]
    delete_memoized: Callable[[], None]

    @property
    def uncached(self) -> Callable[Concatenate[T_contra, P], T_co]: ...

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T_co: ...


class _MemoizedFunction(Protocol[P, R]):
    """The type of the callable returned by :meth:`Cache.memoize`."""

    uncached: Callable[P, R]
    cache_timeout: _Timeout | None
    make_cache_key: Callable[..., str]
    delete_memoized: Callable[[], None]

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R: ...

    @overload
    def __get__(
        self, instance: None, owner: type | None = None, /
    ) -> "_MemoizedFunction[P, R]": ...
    @overload
    def __get__(
        self: "_MemoizedFunction[Concatenate[T, P2], R]",
        instance: T,
        owner: type | None = None,
        /,
    ) -> _BoundMemoizedFunction[T, P2, R]: ...
    def __get__(self, instance: Any, owner: type | None = None, /) -> Any: ...


# A memoized function, however it was reached: a plain function, a method
# accessed on the class, or a method accessed on an instance.
_AnyMemoizedFunction: TypeAlias = (
    "_MemoizedFunction[..., Any] | _BoundMemoizedFunction[Any, ..., Any]"
)

_AnyCachedFunction: TypeAlias = (
    "_CachedFunction[..., Any] | _BoundCachedFunction[Any, ..., Any]"
)
