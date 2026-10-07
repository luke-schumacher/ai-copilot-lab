"""
Claude reads the sentence; it does not decide anything.

Engineers write the way they talk: "AA's too careful into the hairpin, he's on
the brakes way before BB". The rule parser in `claim.py` misses some of
that. This translator turns the sentence into the same `ClaimSpec` the rule
parser produces, through a JSON schema whose enums are built from the loaded
session itself: the drivers in the files, the corners on the map, the
engine's list of causes. It cannot name a corner that isn't there or a cause
the judge doesn't know.

The stamp is still computed by `verdict.judge` from the telemetry. If there
is no key, no network, a timeout or a refusal, `translate` returns None and
the rule parser's reading is used: the check carries on without it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from claimcheck.check.claim import CAUSES, OWN_BEST, UNSUPPORTED, ClaimSpec

MODEL = "claude-opus-5-5"
TIMEOUT_S = 15.0

_SYSTEM = """You translate one sentence from a GT4 race engineer into a test specification for a telemetry checker. You do not judge whether the claim is true; you only say what it claims.

Fill every field from what the sentence says, and nothing more:
- driver: who the claim is about. Use "none" if no loaded driver is named.
- versus: who they are compared with, if the sentence names one ("than BB", "vs BB", "to BB"), "own-best" for their own best lap, else "none".
- corner: the corner, using the session's own names or aliases listed below. Engineers may say "turn 3", "T3", "Kurve 3", or a nickname. Use "none" if no listed corner is meant.
- effect: "loses" if the driver is said to lose time / be slower there, "gains" for the opposite, "none" if the sentence makes no claim about time.
- causes: only the causes the sentence states, from the list below. Never add a cause the sentence does not state.
- unsupported: "oversteer" for oversteer/loose rear, "line" for racing line/apex position/turn-in point/running wide, "car" for setup, tyres, pressures, dampers, anti-roll bars.
- unread: short notes on anything the sentence says that does not fit these fields.

The sentence may be English or German."""


def _schema(drivers: Sequence[str], corners: Sequence[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "driver": {"type": "string", "enum": list(drivers) + ["none"]},
            "versus": {"type": "string", "enum": list(drivers) + [OWN_BEST, "none"]},
            "corner": {"type": "string", "enum": list(corners) + ["none"]},
            "effect": {"type": "string", "enum": ["loses", "gains", "none"]},
            "causes": {"type": "array", "items": {"type": "string", "enum": list(CAUSES)}},
            "unsupported": {"type": "array", "items": {"type": "string", "enum": list(UNSUPPORTED)}},
            "unread": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["driver", "versus", "corner", "effect", "causes", "unsupported", "unread"],
        "additionalProperties": False,
    }


def _context(drivers: Sequence[str], corners, aliases: Dict[str, str]) -> str:
    lines = ["Drivers in the loaded session: " + ", ".join(drivers), "",
             "Corners, numbered by the tool from the start/finish line:"]
    for c in corners:
        names = [a for a, t in aliases.items() if t == c.name]
        extra = f" — also called {', '.join(names)}" if names else ""
        lines.append(f"- {c.name}: {c.direction}-hander, apex {c.apex_m:.0f} m after the line, "
                     f"minimum speed {c.v_min_kph:.0f} km/h{extra}")
    lines += ["", "Causes the checker can test:"]
    lines += [f"- {key}: {label}" for key, (label, _, _) in CAUSES.items()]
    return "\n".join(lines)


def load_key() -> Optional[str]:
    """ANTHROPIC_API_KEY from the environment, or a `.env` beside the repository."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    for d in (Path.cwd(), Path(__file__).resolve().parents[2]):
        env = d / ".env"
        if env.is_file():
            for line in env.read_text().splitlines():
                if line.strip().startswith("ANTHROPIC_API_KEY="):
                    value = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if value:
                        return value
    return None


class ClaudeTranslator:
    """Callable: (text, drivers, corners, aliases) -> ClaimSpec or None."""

    def __init__(self, api_key: Optional[str] = None, model: str = MODEL,
                 timeout_s: float = TIMEOUT_S):
        import anthropic  # optional dependency: pip install "claimcheck-product[llm]"

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key or load_key(),
                                          timeout=timeout_s, max_retries=1)
        self.model = model
        self.last_error: Optional[str] = None

    def __call__(self, text: str, drivers: Sequence[str], corners,
                 aliases: Dict[str, str]) -> Optional[ClaimSpec]:
        a = self._anthropic
        names = [c.name for c in corners]
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=4000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={"effort": "low",
                               "format": {"type": "json_schema",
                                          "schema": _schema(drivers, names)}},
                system=_SYSTEM + "\n\n" + _context(drivers, corners, aliases),
                messages=[{"role": "user", "content": text}],
            )
        except (a.APIConnectionError, a.APITimeoutError) as exc:
            self.last_error = f"no connection ({type(exc).__name__})"
            return None
        except a.AuthenticationError:
            self.last_error = "API key rejected"
            return None
        except a.RateLimitError:
            self.last_error = "rate limited"
            return None
        except a.APIStatusError as exc:
            message = str(getattr(exc, "message", "")).lower()
            self.last_error = ("no API credit left on this key" if "credit balance" in message
                               else f"API error {exc.status_code}")
            return None

        if response.stop_reason in ("refusal", "max_tokens"):
            self.last_error = f"stopped: {response.stop_reason}"
            return None
        text_out = next((b.text for b in response.content if b.type == "text"), None)
        if not text_out:
            self.last_error = "empty response"
            return None
        try:
            raw = json.loads(text_out)
        except json.JSONDecodeError:
            self.last_error = "unparseable response"
            return None
        return _to_spec(text, raw, drivers, names)


def _to_spec(text: str, raw: dict, drivers: Sequence[str], corners: Sequence[str]) -> ClaimSpec:
    """Validate against the session once more: the schema is the contract, not the trust."""
    def pick(value, allowed):
        return value if value in allowed else None

    return ClaimSpec(
        text=text,
        driver=pick(raw.get("driver"), drivers),
        versus=pick(raw.get("versus"), list(drivers) + [OWN_BEST]),
        corner=pick(raw.get("corner"), corners),
        effect=pick(raw.get("effect"), ("loses", "gains")),
        causes=[c for c in raw.get("causes", []) if c in CAUSES],
        unsupported=[u for u in raw.get("unsupported", []) if u in UNSUPPORTED],
        unread=[str(u) for u in raw.get("unread", [])][:3],
        parser="claude",
    )


def available() -> bool:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return load_key() is not None
