"""Async wrapper around the OpenAI-compatible vLLM endpoint for Cosmos Reason 2."""

from __future__ import annotations

import base64
import logging
import re
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI

from app import config

log = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)


def _image_to_data_url(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(suffix, "image/png")
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


def _parse_reasoning(text: str) -> tuple[str, str]:
    """Return (reasoning_trace, final_answer) from model output."""
    m = _THINK_RE.search(text)
    if m:
        reasoning = m.group(1).strip()
        answer = text[m.end():].strip()
        return reasoning, answer
    return "", text.strip()


class CosmosClient:
    """Speaks to the local vLLM Cosmos Reason 2 server."""

    def __init__(
        self,
        base_url: str = config.VLLM_BASE_URL,
        model: str = config.COSMOS_MODEL,
        max_tokens: int = config.MAX_TOKENS,
        timeout: float = config.REQUEST_TIMEOUT,
    ):
        self._client = AsyncOpenAI(base_url=base_url, api_key="not-needed")
        self._model = model
        self._max_tokens = max_tokens
        self._timeout = timeout

    async def analyze_image(
        self,
        image_path: Path,
        prompt: str,
        system_prompt: str = "You are a lunar terrain analysis expert.",
    ) -> dict:
        """Send a single image + prompt; return parsed reasoning + answer."""
        data_url = _image_to_data_url(image_path)
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt},
                ],
            },
        ]
        return await self._call(messages)

    async def compare_images(
        self,
        image_paths: list[Path],
        prompt: str,
        system_prompt: str = "You are a lunar terrain analysis expert.",
    ) -> dict:
        """Send multiple images for side-by-side comparison."""
        content: list[dict] = []
        for i, p in enumerate(image_paths, 1):
            content.append({"type": "text", "text": f"Image {i}:"})
            content.append({"type": "image_url", "image_url": {"url": _image_to_data_url(p)}})
        content.append({"type": "text", "text": prompt})

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ]
        return await self._call(messages)

    async def _call(self, messages: list[dict]) -> dict:
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=self._max_tokens,
                temperature=0.05,
                timeout=self._timeout,
            )
            raw = resp.choices[0].message.content or ""
            reasoning, answer = _parse_reasoning(raw)
            return {"raw": raw, "reasoning": reasoning, "answer": answer}
        except Exception:
            log.exception("Cosmos R2 API call failed")
            raise

    async def health_check(self) -> bool:
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False
