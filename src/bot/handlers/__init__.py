from aiogram import Router

from ..middlewares import AccessMiddleware
from . import admin, common, fallback, print_jobs, scan, start


def setup_routers() -> Router:
    root = Router(name="root")

    root.include_router(start.router)
    root.include_router(admin.router)

    protected = [common.router, scan.router, print_jobs.router, fallback.router]
    for router in protected:
        router.message.middleware(AccessMiddleware())
        router.callback_query.middleware(AccessMiddleware())
        root.include_router(router)

    return root
