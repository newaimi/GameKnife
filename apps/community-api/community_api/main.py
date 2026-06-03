from __future__ import annotations

from gameknife_api import create_community_app
from gameknife_api.deps import CommunitySettings


def create_app(settings: CommunitySettings | None = None):
    return create_community_app(settings)


app = create_app()
