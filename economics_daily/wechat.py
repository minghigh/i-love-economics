from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from .io import read_json, read_text, write_json

API = "https://api.weixin.qq.com/cgi-bin"


class WeChatAPIError(RuntimeError):
    pass


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise WeChatAPIError(f"missing {name}")
    return value


def _json(response: requests.Response) -> dict[str, Any]:
    data = response.json()
    if data.get("errcode", 0) != 0:
        raise WeChatAPIError(str(data))
    return data


def get_access_token() -> str:
    data = _json(
        requests.get(
            f"{API}/token",
            params={
                "grant_type": "client_credential",
                "appid": _required_env("WECHAT_APPID"),
                "secret": _required_env("WECHAT_APPSECRET"),
            },
            timeout=20,
        )
    )
    return str(data["access_token"])


def upload_cover(access_token: str, path: Path) -> str:
    with path.open("rb") as file:
        data = _json(
            requests.post(
                f"{API}/material/add_material",
                params={"access_token": access_token, "type": "image"},
                files={"media": file},
                timeout=60,
            )
        )
    return str(data["media_id"])


def build_draft_article(candidate_dir: Path, thumb_media_id: str) -> dict[str, Any]:
    for name in ["topic.json", "article.html", "cover.png"]:
        if not (candidate_dir / name).exists():
            raise WeChatAPIError(f"missing {candidate_dir / name}")
    topic = read_json(candidate_dir / "topic.json")
    sources = read_json(candidate_dir / "sources.json") if (candidate_dir / "sources.json").exists() else []
    content = read_text(candidate_dir / "article.html").replace('<meta charset="utf-8">', "").strip()
    digest = str(topic.get("economic_question") or topic.get("reason") or "")[:120]
    return {
        "title": str(topic["title"]),
        "thumb_media_id": thumb_media_id,
        "author": os.environ.get("WECHAT_AUTHOR", "用经济学看昨天"),
        "digest": digest,
        "show_cover_pic": 1,
        "content": content,
        "content_source_url": sources[0].get("link", "") if sources else "",
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }


def add_draft(candidate_dir: Path) -> Path:
    article = build_draft_article(candidate_dir, "pending")
    access_token = get_access_token()
    thumb_media_id = upload_cover(access_token, candidate_dir / "cover.png")
    article["thumb_media_id"] = thumb_media_id
    data = _json(
        requests.post(
            f"{API}/draft/add",
            params={"access_token": access_token},
            json={"articles": [article]},
            timeout=60,
        )
    )
    out = candidate_dir / "wechat-draft.json"
    write_json(
        out,
        {
            "media_id": data["media_id"],
            "thumb_media_id": thumb_media_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return out
