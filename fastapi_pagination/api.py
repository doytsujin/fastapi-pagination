import inspect
from contextvars import ContextVar
from typing import Awaitable, Callable, Optional, Sequence, Type, TypeVar, cast

from fastapi import Depends, FastAPI, Response
from fastapi.dependencies.utils import (
    get_parameterless_sub_dependant,
    lenient_issubclass,
)
from fastapi.routing import APIRoute, APIRouter

from .bases import AbstractPage, AbstractParams
from .default import Page

T = TypeVar("T")
TAbstractParams = TypeVar("TAbstractParams", covariant=True, bound=AbstractParams)

params_value: ContextVar[AbstractParams] = ContextVar("pagination_value")
response_value: ContextVar[Optional[Response]] = ContextVar("response_value", default=None)
page_type: ContextVar[Type[AbstractPage]] = ContextVar("page_type", default=Page)


def resolve_params(params: Optional[AbstractParams] = None) -> AbstractParams:
    if params is None:
        try:
            return params_value.get()
        except LookupError:
            raise RuntimeError("Use params or add_pagination")

    return params


def create_page(items: Sequence[T], total: int, params: AbstractParams) -> AbstractPage[T]:
    return page_type.get().create(items, total, params)


def response() -> Optional[Response]:
    return response_value.get()


def set_page(page: Type[AbstractPage]) -> None:
    page_type.set(page)


def _create_page_dependency(page: Type[AbstractPage]) -> Callable[[], Awaitable[None]]:
    async def _set_page_type() -> None:
        page_type.set(page)

    return _set_page_type


def _create_params_dependency(
    params: Type[TAbstractParams],
) -> Callable[[TAbstractParams], Awaitable[TAbstractParams]]:
    async def _pagination_params(*args, **kwargs) -> params:  # type: ignore
        val = params(*args, **kwargs)  # type: ignore
        params_value.set(val)

    _pagination_params.__signature__ = inspect.signature(params)  # type: ignore

    return _pagination_params


async def _set_response(res: Response) -> None:
    response_value.set(res)


async def _marker() -> None:
    pass


ParentT = TypeVar("ParentT", APIRouter, FastAPI)


def _update_route(route: APIRoute) -> None:
    if all(
        (
            not any(d.call is _marker for d in route.dependant.dependencies),
            lenient_issubclass(route.response_model, AbstractPage),
        )
    ):
        cls = cast(Type[AbstractPage], route.response_model)

        dependencies = [
            Depends(_marker),
            Depends(_set_response),
            Depends(_create_params_dependency(cls.__params_type__)),
            Depends(_create_page_dependency(cls)),
        ]

        route.dependencies.extend(dependencies)
        route.dependant.dependencies.extend(
            get_parameterless_sub_dependant(
                depends=d,
                path=route.path_format,
            )
            for d in dependencies
        )


def add_pagination(parent: ParentT) -> ParentT:
    for route in parent.routes:
        if isinstance(route, APIRoute):
            _update_route(route)

    return parent


__all__ = [
    "add_pagination",
    "create_page",
    "resolve_params",
    "response",
    "set_page",
]
