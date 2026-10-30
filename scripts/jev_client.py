"""Minimal TypeSafe System One client for the Jev experiments (docs/assets/53+).

Stdlib only: nothing in the package depends on TypeSafe until a rung passes.
Every call is appended to ~/.ytk/logs/jev_calls.jsonl with its latency and
token usage, so a section's spend and speed are counted, not estimated.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
LEDGER = Path.home() / ".ytk" / "logs" / "jev_calls.jsonl"
# Pinned by id: `jev-latest` is an alias that moves, and a moved alias would
# change answers under a figure that still carries the old stamp.
MODEL = "jev-1.14.0"


def api_key() -> str:
    key = os.environ.get("TYPESAFE_JEV_KEY")
    if not key:
        for line in (Path(__file__).resolve().parents[1] / ".env").read_text().splitlines():
            if line.startswith("TYPESAFE_JEV_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
    if not key:
        raise SystemExit("TYPESAFE_JEV_KEY is not set (env or .env)")
    return key


@dataclass
class Reply:
    answers: dict
    model: str
    input_tokens: int
    output_tokens: int
    latency_s: float


def noul(instructions: str, true: str | None = None, false: str | None = None) -> dict:
    q: dict = {"type": "noul", "instructions": instructions}
    if true or false:
        q["criteria"] = {"true": true, "false": false}
    return q


def choice(instructions: str, criteria: dict[str, str]) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def system_one(
    state: object, questions: dict[str, dict], *, tag: str, model: str = MODEL, retries: int = 4
) -> Reply:
    body = json.dumps({"model": model, "state": state, "questions": questions}).encode()
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"},
    )
    for attempt in range(retries + 1):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries:
                time.sleep(float(e.headers.get("retry-after", 2**attempt)))
                continue
            raise SystemExit(f"HTTP {e.code}: {e.read()[:400]!r}")
    latency = time.perf_counter() - t0
    usage = data.get("usage", {})
    reply = Reply(
        answers=data["answers"],
        model=data.get("model", model),
        input_tokens=int(usage.get("input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
        latency_s=latency,
    )
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "tag": tag,
                    "model": reply.model,
                    "questions": len(questions),
                    "bytes": len(body),
                    "input_tokens": reply.input_tokens,
                    "output_tokens": reply.output_tokens,
                    "latency_s": round(latency, 4),
                }
            )
            + "\n"
        )
    return reply
