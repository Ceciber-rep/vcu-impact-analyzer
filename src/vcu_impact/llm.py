"""Provider-agnostic LLM client with validated structured output.

All hosted providers are called through their OpenAI-compatible endpoint, so a
provider is only configuration (base URL, model, key). Ollama is called through
its native API because that is the only way to set the context window.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from openai import BadRequestError, OpenAI
from pydantic import BaseModel, ValidationError

# Base URL and the environment variable holding the key, per provider.
PROVIDERS: dict[str, dict[str, str | None]] = {
    "github": {"base_url": "https://models.github.ai/inference", "key_env": "GITHUB_TOKEN"},
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_env": "GEMINI_API_KEY",
    },
    "groq": {"base_url": "https://api.groq.com/openai/v1", "key_env": "GROQ_API_KEY"},
    "cerebras": {"base_url": "https://api.cerebras.ai/v1", "key_env": "CEREBRAS_API_KEY"},
    "mistral": {"base_url": "https://api.mistral.ai/v1", "key_env": "MISTRAL_API_KEY"},
    "ollama": {"base_url": "http://localhost:11434", "key_env": None},
    "openai_compatible": {"base_url": None, "key_env": "LLM_API_KEY"},
}


class LLMError(RuntimeError):
    pass


@dataclass
class LLMConfig:
    provider: str
    model: str
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.0
    timeout_s: float = 600.0
    max_retries: int = 2  # SDK-level retries (rate limits, transient errors)
    # Output budget, including hidden reasoning tokens. Some providers apply a low
    # default cap that truncates reasoning models, so it is always set explicitly.
    max_tokens: int = 16384
    max_tokens_ceiling: int = 32768
    ollama_num_ctx: int = 16384
    ollama_think: bool | None = None  # None = model default

    @classmethod
    def from_env(cls, provider: str | None = None, model: str | None = None, prefix: str = "LLM_") -> LLMConfig:
        """Build the config from ``<prefix>*`` variables (LLM_ for the primary model,
        LLM_FALLBACK_ for the fallback). The provider-specific key variable
        (e.g. GROQ_API_KEY) is used when ``<prefix>API_KEY`` is empty."""
        provider = (provider or os.getenv(f"{prefix}PROVIDER") or "").strip().lower()
        if provider not in PROVIDERS:
            raise LLMError(f"Unknown or missing {prefix}PROVIDER {provider!r}; expected one of {sorted(PROVIDERS)}")
        preset = PROVIDERS[provider]
        key_env = preset["key_env"]
        api_key = os.getenv(f"{prefix}API_KEY") or (os.getenv(key_env) if key_env else None)
        model = model or os.getenv(f"{prefix}MODEL")
        if not model:
            raise LLMError(f"{prefix}MODEL is not set")
        base_url = os.getenv(f"{prefix}BASE_URL") or preset["base_url"]
        if provider != "ollama" and not api_key:
            raise LLMError(f"No API key: set {prefix}API_KEY or {key_env}")
        return cls(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout_s=float(os.getenv("LLM_TIMEOUT_S") or 600),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS") or 16384),
        )

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass
class LLMCallResult:
    parsed: BaseModel
    raw_text: str
    latency_s: float
    attempts: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    structured_mode: str = "json_schema"
    notes: list[str] = field(default_factory=list)


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema with $refs inlined (portable across providers)."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(defs[node["$ref"].split("/")[-1]])
            out = {k: resolve(v) for k, v in node.items() if k != "title"}
            if out.get("type") == "object":
                out["additionalProperties"] = False
                out["required"] = list(out.get("properties", {}))
            return out
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def extract_json(text: str) -> str:
    """The JSON object in a model reply (drops <think> blocks and code fences)."""
    text = _THINK_RE.sub("", text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end > start else text


def _is_provider_rejection(msg: str) -> bool:
    """The provider validated the generated JSON server-side and rejected it."""
    return bool(
        re.search(
            r"failed to generate json|json_validate_failed|does not match the expected schema|failed_generation", msg
        )
    )


def _is_truncation(msg: str) -> bool:
    return bool(re.search(r"max[_ ]?(completion[_ ])?tokens|truncat|length limit", msg))


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config
        if config.provider != "ollama":
            self._client = OpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
                timeout=config.timeout_s,
                max_retries=config.max_retries,
            )

    # -- public ------------------------------------------------------------

    def structured(self, system: str, user: str, schema_model: type[BaseModel], max_attempts: int = 2) -> LLMCallResult:
        """Call the model and return output validated against ``schema_model``.

        On invalid output the validation error is sent back once for repair.
        """
        schema = strict_schema(schema_model)
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        notes: list[str] = []
        total_latency, prompt_tokens, completion_tokens = 0.0, 0, 0
        mode = "json_schema"
        last_error = ""
        for attempt in range(1, max_attempts + 1):
            t0 = time.perf_counter()
            text, usage, mode = self._call(messages, schema, schema_model.__name__, mode, notes)
            total_latency += time.perf_counter() - t0
            prompt_tokens += usage[0] or 0
            completion_tokens += usage[1] or 0
            try:
                parsed = schema_model.model_validate_json(extract_json(text))
                return LLMCallResult(
                    parsed=parsed,
                    raw_text=text,
                    latency_s=total_latency,
                    attempts=attempt,
                    prompt_tokens=prompt_tokens or None,
                    completion_tokens=completion_tokens or None,
                    structured_mode=mode,
                    notes=notes,
                )
            except (ValidationError, ValueError) as exc:
                last_error = str(exc)[:1500]
                notes.append(f"attempt {attempt}: invalid output ({last_error[:200]})")
                messages += [
                    {"role": "assistant", "content": text[:6000]},
                    {
                        "role": "user",
                        "content": "Your previous answer did not match the required JSON schema. "
                        f"Validation errors:\n{last_error}\nReturn the complete corrected JSON object only.",
                    },
                ]
        raise LLMError(f"No valid structured output after {max_attempts} attempts: {last_error[:300]}")

    # -- providers ---------------------------------------------------------

    def _call(self, messages, schema, name, mode, notes):
        if self.config.provider == "ollama":
            return (*self._call_ollama(messages, schema), "ollama_format_schema")
        return self._call_openai(messages, schema, name, mode, notes)

    def _call_openai(self, messages, schema, name, mode, notes):
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": self.config.max_tokens,
        }
        if self.config.temperature is not None:
            kwargs["temperature"] = self.config.temperature
        while True:
            if mode == "json_schema":
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": name, "schema": schema, "strict": True},
                }
            else:  # fallback: JSON mode with the schema in the prompt
                kwargs["response_format"] = {"type": "json_object"}
                kwargs["messages"] = [
                    *messages[:-1],
                    {
                        "role": messages[-1]["role"],
                        "content": messages[-1]["content"]
                        + "\n\nReturn only a JSON object matching this JSON schema:\n"
                        + json.dumps(schema),
                    },
                ]
            try:
                resp = self._client.chat.completions.create(**kwargs)
                if resp.choices[0].finish_reason == "length" and self._grow_budget(kwargs, notes):
                    continue
                break
            except BadRequestError as exc:
                msg = str(exc).lower()
                if _is_truncation(msg):
                    if self._grow_budget(kwargs, notes):
                        continue
                    raise LLMError(f"Output truncated even with {kwargs['max_tokens']} tokens") from exc
                if _is_provider_rejection(msg):
                    # The provider validated the output server-side and rejected it. Hand the
                    # rejected text to the normal validation/repair path instead of failing.
                    body = exc.body if isinstance(exc.body, dict) else {}
                    failed = (body.get("error", body) or {}).get("failed_generation") or ""
                    notes.append("provider rejected the generated JSON (server-side schema check)")
                    return failed, (None, None), mode
                if "temperature" in msg and "temperature" in kwargs:
                    notes.append("provider rejected temperature; retried with default")
                    kwargs.pop("temperature")
                elif mode == "json_schema" and ("json_schema" in msg or "response_format" in msg or "schema" in msg):
                    notes.append(f"json_schema not accepted ({str(exc)[:160]}); fell back to json_object")
                    mode = "json_object"
                else:
                    raise
        usage = resp.usage
        text = resp.choices[0].message.content or ""
        return text, (getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None)), mode

    def _grow_budget(self, kwargs: dict, notes: list[str]) -> bool:
        if kwargs["max_tokens"] >= self.config.max_tokens_ceiling:
            return False
        kwargs["max_tokens"] = min(kwargs["max_tokens"] * 2, self.config.max_tokens_ceiling)
        notes.append(f"output truncated; retried with max_tokens={kwargs['max_tokens']}")
        return True

    def _call_ollama(self, messages, schema):
        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "format": schema,
            "options": {"temperature": self.config.temperature, "num_ctx": self.config.ollama_num_ctx},
        }
        if self.config.ollama_think is not None:
            body["think"] = self.config.ollama_think
        url = (self.config.base_url or "http://localhost:11434").rstrip("/") + "/api/chat"
        try:
            r = httpx.post(url, json=body, timeout=self.config.timeout_s)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama request failed: {exc}") from exc
        data = r.json()
        return data["message"]["content"], (data.get("prompt_eval_count"), data.get("eval_count"))
