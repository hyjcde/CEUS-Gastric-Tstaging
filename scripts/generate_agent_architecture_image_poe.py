#!/usr/bin/env python3
"""Generate gastric US Agent architecture diagrams through Poe's image API.

Supports a compact overview diagram and a detailed methodology diagram (GPT-Image-2).

Set POE_API_KEY before real generation, or use --dry-run to write the prompt only.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS = PROJECT_ROOT / "docs" / "mainline"

# Load POE_API_KEY from repo-root `.env` when present.
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from repo_env import load_repo_env  # noqa: E402

load_repo_env()

PROMPT_OVERVIEW = DOCS / "gastric_us_agent_architecture_poe_prompt.txt"
PROMPT_DETAILED = DOCS / "gastric_us_agent_methodology_architecture_poe_prompt_detailed.txt"

DEFAULT_OUT = {
    "overview": DOCS / "gastric_us_agent_architecture_poe.png",
    "detailed": DOCS / "gastric_us_agent_methodology_architecture_poe.png",
}

DEFAULT_MODEL = {
    "overview": "GPT-Image-1",
    "detailed": "GPT-Image-2",
}

POE_IMAGES_URL = "https://api.poe.com/v1/images"
POE_CHAT_URL = "https://api.poe.com/v1/chat/completions"
_IMAGE_URL_RE = re.compile(r"https://[^\s\)\]>\"']+")

# Fallback if prompt files missing (overview only).
_OVERVIEW_FALLBACK = PROMPT_OVERVIEW.read_text(encoding="utf-8") if PROMPT_OVERVIEW.exists() else ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate gastric US Agent architecture diagram(s) via Poe image API.",
    )
    parser.add_argument(
        "--variant",
        choices=["overview", "detailed"],
        default="detailed",
        help="overview = compact 4-layer diagram; detailed = full methodology swimlanes.",
    )
    parser.add_argument("--out", type=Path, default=None, help="Output PNG path.")
    parser.add_argument("--prompt-file", type=Path, default=None, help="Override prompt text file.")
    parser.add_argument("--prompt-out", type=Path, default=None, help="Copy prompt to this path.")
    parser.add_argument(
        "--model",
        default=None,
        help="Poe image model (default: GPT-Image-1 overview, GPT-Image-2 detailed).",
    )
    parser.add_argument("--api-key-env", default="POE_API_KEY")
    parser.add_argument("--quality", default="high", choices=["low", "medium", "high", "auto"])
    parser.add_argument("--aspect-ratio", default="16:9")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--backend",
        choices=["auto", "chat", "images"],
        default="auto",
        help="auto: chat (Poe Images API often 404/403); chat: GPT-Image via /v1/chat/completions.",
    )
    return parser.parse_args()


def _resolve_prompt(variant: str, prompt_file: Path | None) -> str:
    if prompt_file is not None:
        return prompt_file.read_text(encoding="utf-8")
    path = PROMPT_OVERVIEW if variant == "overview" else PROMPT_DETAILED
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def _extract_image_url_from_text(text: str) -> str:
    for url in _IMAGE_URL_RE.findall(text or ""):
        if any(token in url for token in ("poecdn", "/image/", ".png", ".jpg", ".jpeg", ".webp")):
            return url.rstrip(")")
    raise RuntimeError("No image URL found in Poe chat response")


def _generate_via_chat(api_key: str, model: str, prompt: str) -> bytes:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
    }
    request = urllib.request.Request(
        POE_CHAT_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Poe chat request failed: HTTP {exc.code}: {detail}") from exc

    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError(f"Poe chat returned no choices: {payload}")
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    image_url = _extract_image_url_from_text(content)
    download_req = urllib.request.Request(
        image_url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; GastricTstaging/1.0)"},
    )
    with urllib.request.urlopen(download_req, timeout=120) as response:
        return response.read()


def _generate_via_images(api_key: str, request_body: dict[str, Any]) -> bytes:
    request = urllib.request.Request(
        POE_IMAGES_URL,
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Poe image request failed: HTTP {exc.code}: {detail}") from exc
    return _extract_image_bytes(payload)


def _extract_image_bytes(payload: dict[str, Any]) -> bytes:
    data = payload.get("data")
    if isinstance(data, list) and data:
        item = data[0]
        if isinstance(item, dict):
            b64 = item.get("b64_json") or item.get("base64")
            if isinstance(b64, str) and b64:
                return base64.b64decode(b64)
            url = item.get("url")
            if isinstance(url, str) and url:
                download_req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; GastricTstaging/1.0)"},
                )
                with urllib.request.urlopen(download_req, timeout=120) as response:
                    return response.read()
    image = payload.get("image")
    if isinstance(image, str) and image:
        return base64.b64decode(image)
    raise RuntimeError(f"Could not find image data in Poe response keys: {sorted(payload.keys())}")


def main() -> None:
    args = parse_args()
    prompt = _resolve_prompt(args.variant, args.prompt_file)
    out_path = args.out or DEFAULT_OUT[args.variant]
    model = args.model or os.getenv("POE_IMAGE_MODEL") or DEFAULT_MODEL[args.variant]
    prompt_out = args.prompt_out or (
        PROMPT_OVERVIEW if args.variant == "overview" else PROMPT_DETAILED
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_out.parent.mkdir(parents=True, exist_ok=True)
    prompt_out.write_text(prompt, encoding="utf-8")

    request_body = {
        "model": model,
        "prompt": prompt,
        "quality": args.quality,
        "aspect_ratio": args.aspect_ratio,
    }

    backend = args.backend
    if backend == "auto":
        backend = "chat"

    if args.dry_run:
        print(json.dumps({
            "status": "dry_run",
            "variant": args.variant,
            "backend": backend,
            "endpoint": POE_CHAT_URL if backend == "chat" else POE_IMAGES_URL,
            "model": model,
            "prompt_chars": len(prompt),
            "prompt_path": str(prompt_out),
            "output_path": str(out_path),
            "request": request_body,
        }, indent=2, ensure_ascii=False))
        return

    load_repo_env()
    api_key = os.getenv(args.api_key_env)
    if not api_key:
        raise RuntimeError(
            f"Missing {args.api_key_env}. Copy .env.example to .env or export in shell.\n"
            f"  python {Path(__file__).name} --variant detailed"
        )

    if backend == "chat":
        image_bytes = _generate_via_chat(api_key, model, prompt)
        used_backend = "chat"
    else:
        try:
            image_bytes = _generate_via_images(api_key, request_body)
            used_backend = "images"
        except RuntimeError as exc:
            if args.backend != "images":
                image_bytes = _generate_via_chat(api_key, model, prompt)
                used_backend = "chat"
            else:
                raise exc

    out_path.write_bytes(image_bytes)
    print(json.dumps({
        "status": "ok",
        "variant": args.variant,
        "backend": used_backend,
        "model": model,
        "output_path": str(out_path),
        "prompt_path": str(prompt_out),
        "bytes": len(image_bytes),
    }, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
