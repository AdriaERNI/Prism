"""Emy vision helper — sends screenshots to the vLLM model for visual analysis.

This module provides a callable that Prism's test suite uses to verify
GUI appearance by asking the vision model to describe what it sees.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

import httpx

EMY_URL = os.environ.get(
    "EMY_VISION_URL", "http://192.168.6.185:8001/v1/chat/completions"
)
EMY_API_KEY = os.environ.get("EMY_API_KEY", "sk-emy-vllm-vl-72b")
EMY_MODEL = os.environ.get("EMY_MODEL", "emy")


def analyze_screenshot(
    image_path: str | Path, question: str, timeout: float = 60
) -> str:
    """Send a screenshot to emy and return the description.

    Args:
        image_path: Path to a PNG/JPEG image file.
        question: What to ask about the image.
        timeout: HTTP timeout in seconds.

    Returns:
        The model's text response.
    """
    image_data = Path(image_path).read_bytes()
    img_b64 = base64.b64encode(image_data).decode()

    payload = {
        "model": EMY_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                    },
                ],
            }
        ],
        "max_tokens": 500,
    }

    resp = httpx.post(
        EMY_URL,
        json=payload,
        headers={"Authorization": f"Bearer {EMY_API_KEY}"},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def assert_contains(response: str, *keywords: str) -> None:
    """Assert that the vision response contains all keywords (case-insensitive)."""
    lower = response.lower()
    for kw in keywords:
        assert kw.lower() in lower, f"Expected '{kw}' in vision response: {response}"


def assert_not_contains(response: str, *keywords: str) -> None:
    """Assert that the vision response does NOT contain any of the keywords."""
    lower = response.lower()
    for kw in keywords:
        assert kw.lower() not in lower, (
            f"Did not expect '{kw}' in vision response: {response}"
        )
