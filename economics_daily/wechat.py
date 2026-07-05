from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from .io import read_json, read_text, write_json

API = "https://api.weixin.qq.com/cgi-bin"
MAX_TITLE_BYTES = 32
MAX_DIGEST_BYTES = 54
MAX_AUTHOR_BYTES = 8


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


def _json_payload(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _fit_bytes(value: str, limit: int) -> str:
    value = value.strip()
    if len(value.encode("utf-8")) <= limit:
        return value
    out = ""
    for char in value:
        if len((out + char + "...").encode("utf-8")) > limit:
            return out.rstrip("，。！？；：、 ") + "..."
        out += char
    return out


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
    digest = _fit_bytes(str(topic.get("economic_question") or topic.get("reason") or ""), MAX_DIGEST_BYTES)
    article = {
        "title": _fit_bytes(str(topic["title"]), MAX_TITLE_BYTES),
        "thumb_media_id": thumb_media_id,
        "digest": digest,
        "show_cover_pic": 1,
        "content": content,
        "content_source_url": sources[0].get("link", "") if sources else "",
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }
    author = os.environ.get("WECHAT_AUTHOR", "")
    if author and len(author.encode("utf-8")) <= MAX_AUTHOR_BYTES:
        article["author"] = author
    return article


def add_draft(candidate_dir: Path) -> Path:
    article = build_draft_article(candidate_dir, "pending")
    access_token = get_access_token()
    thumb_media_id = upload_cover(access_token, candidate_dir / "cover.png")
    article["thumb_media_id"] = thumb_media_id
    data = _json(
        requests.post(
            f"{API}/draft/add",
            params={"access_token": access_token},
            data=_json_payload({"articles": [article]}),
            headers={"Content-Type": "application/json; charset=utf-8"},
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
