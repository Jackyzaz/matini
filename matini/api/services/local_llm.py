"""Thin client for talking to a local LLM served by Ollama.

Used for two roles in the NIST AI RMF Ethical Assessment POC:
  1. "subject" — the AI system under assessment (probe_subject)
  2. "judge"   — scores each assessment criterion against the evidence collected (judge)

Both roles hit the same Ollama-compatible /api/chat endpoint; they can point at
different models (and, once you move Ollama to another machine, the same
OLLAMA_BASE_URL for both — see docs/nist-rmf-poc-guide.md).

IMPORTANT METHODOLOGICAL NOTE for the write-up: using the *same* model as both
subject and judge risks self-evaluation bias (a model may be lenient — or
inconsistent — when scoring its own outputs). For the POC this is acceptable to
prove the pipeline works end-to-end, but for the actual study, prefer a
different (ideally stronger/independently-validated) model as the judge.
"""
import json
from typing import Dict, List, Optional

import requests

from matini.api.core.config import settings


class OllamaUnavailableError(RuntimeError):
    """Raised whenever the configured Ollama endpoint can't be reached or returns
    something the caller can't use (connection refused, timeout, malformed body)."""


def _chat(
    model: str,
    messages: List[Dict[str, str]],
    *,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
    json_mode: bool = False,
) -> str:
    url = f"{(base_url or settings.ollama_base_url).rstrip('/')}/api/chat"
    payload = {"model": model, "messages": messages, "stream": False}
    if json_mode:
        payload["format"] = "json"

    try:
        resp = requests.post(url, json=payload, timeout=timeout or settings.ollama_timeout_s)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise OllamaUnavailableError(
            f"เชื่อมต่อ Ollama ไม่สำเร็จที่ {url} ({exc.__class__.__name__}: {exc}). "
            "ตรวจสอบว่า Ollama กำลังรันอยู่ (`ollama serve`), รัน `ollama pull "
            f"{model}` แล้ว และ OLLAMA_BASE_URL ตั้งค่าถูกต้อง (ดู docs/nist-rmf-poc-guide.md)"
        ) from exc

    try:
        data = resp.json()
    except ValueError as exc:
        raise OllamaUnavailableError(f"Ollama ตอบกลับที่ {url} ไม่ใช่ JSON: {resp.text[:300]!r}") from exc

    content = (data.get("message") or {}).get("content")
    if not content:
        raise OllamaUnavailableError(f"Ollama ตอบกลับไม่มี message.content ที่ใช้ได้: {data}")
    return content


def probe_subject(
    prompt: str,
    *,
    model: str,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> str:
    """Send one test prompt to the AI system under assessment and return its raw reply."""
    return _chat(model, [{"role": "user", "content": prompt}], base_url=base_url, timeout=timeout)


def judge(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> dict:
    """Call the judge LLM and parse a strict-JSON verdict.

    Retries once with an extra "JSON only" reminder if the first reply isn't valid
    JSON — small/local models sometimes wrap JSON in prose even when asked not to.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    raw = _chat(model, messages, base_url=base_url, timeout=timeout, json_mode=True)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        messages.append({"role": "assistant", "content": raw})
        messages.append(
            {
                "role": "user",
                "content": (
                    "กรุณาตอบเป็น JSON ล้วน ๆ เท่านั้น ห้ามมีข้อความอื่นนอกเหนือจาก JSON object ตาม schema ที่กำหนด"
                ),
            }
        )
        raw2 = _chat(model, messages, base_url=base_url, timeout=timeout, json_mode=True)
        try:
            return json.loads(raw2)
        except json.JSONDecodeError as exc:
            raise OllamaUnavailableError(
                f"ผลลัพธ์จาก judge model ('{model}') ไม่ใช่ JSON ที่แปลงได้: {raw2!r}"
            ) from exc
