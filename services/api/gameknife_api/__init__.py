from __future__ import annotations


__all__ = ["create_community_app"]


def create_community_app(*args, **kwargs):
    # Package initialization cannot import app and routes eagerly because services/workflows reuses API job executors.
    # Delay imports until application creation so workflow tests do not trigger a route-workflow import cycle.
    from .app import create_community_app as factory

    return factory(*args, **kwargs)
