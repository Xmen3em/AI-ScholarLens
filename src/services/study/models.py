"""Hosted-model profiles; the default is production, distinct from the frozen benchmark control."""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

InputEstimate = Literal["gpt_oss_tokenizer", "glm_tokenizer", "utf8_bytes_div_3"]
ESTIMATES = ("gpt_oss_tokenizer", "glm_tokenizer", "utf8_bytes_div_3")
# Pre-call estimation refuses above 20,000, but accepted provider usage may report 21,000.
WORST_INPUT_TOKENS = 21_000


@dataclass(frozen=True)
class ModelProfile:
    name: str
    route: str
    input_estimate: InputEstimate
    request_options: dict[str, object] = field(hash=False)
    price_in_usd_per_m: float
    price_out_usd_per_m: float
    priced_on: str


GPT_OSS_PROFILE = ModelProfile("baseline", "openai/gpt-oss-120b:cerebras", "gpt_oss_tokenizer",
                               {"reasoning_effort": "low"}, 0.35, 0.75, "2026-11-03")
# The benchmark control stayed DeepInfra; production changed only after Fireworks qualification passed.
GLM_FIREWORKS_PROFILE = ModelProfile("glm-fireworks", "zai-org/GLM-5.3:fireworks-ai", "glm_tokenizer",
                                     {"reasoning_effort": "low"}, 2.10, 6.60, "2026-11-25")
DEFAULT_PROFILE = GLM_FIREWORKS_PROFILE


def estimate_input(profile: ModelProfile, serialized: str) -> int:
    if profile.input_estimate == "gpt_oss_tokenizer":
        from src.services.hf.tokenizer import count_input_tokens

        return count_input_tokens(serialized)
    if profile.input_estimate == "glm_tokenizer":
        from src.services.study.glm_tokenizer import count_glm_tokens

        counted = count_glm_tokens(serialized)
        if counted is not None:
            return counted
    # No (verified) local tokenizer: three UTF-8 bytes per token over-counts English and Arabic alike.
    return math.ceil(len(serialized.encode()) / 3)


def call_cost_usd(profile: ModelProfile, usage: dict | None, *, estimate: int, max_tokens: int = 3000) -> float:
    if usage is None:
        # A call without usage is charged as if it used everything it could.
        tokens_in, tokens_out = estimate, max_tokens
    else:
        tokens_in, tokens_out = usage["prompt_tokens"], usage["completion_tokens"]
    token_cost = (tokens_in * profile.price_in_usd_per_m + tokens_out * profile.price_out_usd_per_m) / 1e6
    reported = None if usage is None else usage.get("cost")
    if reported is None and usage is not None and type(usage.get("cost_details")) is dict:
        reported = usage["cost_details"].get("upstream_inference_cost")
    if type(reported) in (int, float) and reported is not None and math.isfinite(reported) and reported >= 0:
        return max(token_cost, reported)
    return token_cost


def load_profiles(path: Path) -> dict[str, ModelProfile]:
    data = json.loads(path.read_text(encoding="utf-8"))
    profiles = {}
    for name, raw in data["profiles"].items():
        if raw["input_estimate"] not in ESTIMATES or type(raw["request_options"]) is not dict:
            raise ValueError("invalid_profile")
        profiles[name] = ModelProfile(name, raw["route"], raw["input_estimate"], raw["request_options"],
                                      float(raw["price_in_usd_per_m"]), float(raw["price_out_usd_per_m"]),
                                      raw["priced_on"])
    if data["judge"] not in profiles:
        raise ValueError("invalid_profile")
    return profiles
