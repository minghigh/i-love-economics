from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


@dataclass
class ChatClient:
    base_url: str
    model: str
    api_key: str = ""

    def complete(self, prompt: str, temperature: float = 0.2) -> str:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=180)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def local_client() -> ChatClient:
    return ChatClient(
        os.environ.get("LOCAL_LLM_BASE_URL", "http://10.88.255.251:8008/v1"),
        os.environ.get("LOCAL_LLM_MODEL", "deepseek-chat"),
        os.environ.get("LOCAL_LLM_API_KEY", ""),
    )


def deepseek_client() -> ChatClient:
    return ChatClient(
        os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        os.environ.get("DEEPSEEK_API_KEY", ""),
    )


def prompt(name: str, **values: object) -> str:
    text = Path("prompts", name).read_text(encoding="utf-8")
    for key, value in values.items():
        replacement = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
        text = text.replace("{{" + key + "}}", replacement)
    return text


def parse_json_response(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:]
    start = min([i for i in [stripped.find("{"), stripped.find("[")] if i >= 0], default=0)
    end_obj = stripped.rfind("}")
    end_arr = stripped.rfind("]")
    end = max(end_obj, end_arr)
    return json.loads(stripped[start : end + 1] if end >= start else stripped)
