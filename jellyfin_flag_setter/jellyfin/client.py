import base64

import httpx

from jellyfin_flag_setter.config import settings
from jellyfin_flag_setter.jellyfin.models import MovieItem, RecentItemsResponse


class JellyfinClient:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(
            base_url=settings.jellyfin_url,
            headers={
                "X-Emby-Authorization": f"MediaBrowser "
                f'Token="{settings.jellyfin_api_key}"'
            },
            timeout=30.0,
        )
        self._user_id: str | None = None

    async def _get_user_id(self) -> str:
        if self._user_id is None:
            response = await self._http.get("/Users")
            response.raise_for_status()
            users = response.json()
            self._user_id = users[0]["Id"]
        return self._user_id

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_all_movies(self) -> list[MovieItem]:
        user_id = await self._get_user_id()
        response = await self._http.get(
            "/Items",
            params={
                "userId": user_id,
                "IncludeItemTypes": "Movie",
                "SortBy": "SortName",
                "SortOrder": "Ascending",
                "Recursive": "true",
                "Fields": "MediaStreams",
            },
        )
        response.raise_for_status()
        data = RecentItemsResponse.model_validate_json(
            response.content,
            strict=False,
        )
        return data.items

    async def get_movie(self, item_id: str) -> MovieItem:
        user_id = await self._get_user_id()
        response = await self._http.get(
            f"/Items/{item_id}",
            params={"userId": user_id, "Fields": "MediaStreams"},
        )
        response.raise_for_status()
        return MovieItem.model_validate_json(response.content, strict=False)

    async def get_poster(self, item_id: str) -> bytes:
        response = await self._http.get(f"/Items/{item_id}/Images/Primary")
        response.raise_for_status()
        return response.content

    async def upload_poster(
        self, item_id: str, image_data: bytes, content_type: str = "image/jpeg"
    ) -> None:
        response = await self._http.post(
            f"/Items/{item_id}/Images/Primary",
            content=base64.b64encode(image_data),
            headers={"Content-Type": content_type},
        )
        response.raise_for_status()
