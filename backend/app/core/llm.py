"""
Amber Universal LLM Gateway — The Lego Brain Socket.

Any OpenAI-compatible local model (Ollama, vLLM, TGI, LM Studio, custom GPU cluster)
or cloud provider (Anthropic via Amber proxy, OpenAI, Gemini) can be plugged in here.

Client just sets 3 env vars:
  LLM_PROVIDER=local
  LOCAL_LLM_ENDPOINT=http://ollama:11434/v1   (or http://gpu-cluster.internal:8000/v1)
  LOCAL_LLM_MODEL=qwen2.5-coder:14b           (any model name — qwen4, deepseek-r1, llama3.3:70b, etc.)

To swap model: change LOCAL_LLM_MODEL in .env and restart. Nothing else changes.

Safety guarantees:
- AIR_GAPPED=true hard-blocks ALL cloud provider calls at code level.
- If LLM is down/missing: returns None so deterministic heuristics take over (no crash).
- Auto-strips <think> tokens from reasoning models (DeepSeek-R1, QwQ, etc).
- JSON extraction with auto-repair: handles markdown wrappers, trailing text, etc.
- context_length=16384 set on local calls to prevent silent log truncation.
- 1 auto-retry on malformed JSON with explicit error feedback to model.
"""

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, Optional

import httpx

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Model Certification Registry
# Trust levels gate what actions Amber will auto-propose.
# LEVEL_1: Observe only — root cause diagnosis, no dangerous tool proposals.
# LEVEL_2: High trust — full proposals, human approval still required.
# LEVEL_3: Enterprise — full proposals + auto-fix eligible (if client enables it).
# ──────────────────────────────────────────────
MODEL_TRUST_REGISTRY: Dict[str, int] = {
    # Certified — Level 2 (Standard Production)
    "qwen2.5-coder:14b": 2,
    "qwen2.5-coder:7b": 2,
    "phi4:14b": 2,
    "phi-4:14b": 2,
    "mistral-small:24b": 2,
    "mistral-small3.2:24b": 2,
    "qwen2.5-coder:32b": 2,
    # Certified — Level 3 (Enterprise)
    "qwen2.5:72b": 3,
    "llama3.1:70b": 3,
    "llama3.3:70b-instruct-q4_K_M": 3,
    "llama3.3:70b": 3,
    "qwen2.5:72b-instruct": 3,
    # Cloud — Level 3 (Enterprise, via Amber Proxy)
    "claude-3-5-sonnet-20241022": 3,
    "claude-3-7-sonnet-20250219": 3,
    "gpt-4o": 3,
    "gemini-2.5-flash": 3,
    "gemini-2.5-pro": 3,
}

# Any model NOT in this registry gets LEVEL_1 (observe only, no dangerous proposals)
DEFAULT_TRUST_LEVEL = 1


def get_model_trust_level() -> int:
    """Returns the trust level for the currently configured model."""
    provider = settings.LLM_PROVIDER.lower()
    if provider == "local":
        model = settings.LOCAL_LLM_MODEL.lower()
    elif provider == "anthropic":
        model = settings.ANTHROPIC_MODEL.lower()
    elif provider == "openai":
        model = settings.OPENAI_MODEL.lower()
    elif provider == "gemini":
        model = settings.GEMINI_MODEL.lower()
    else:
        return DEFAULT_TRUST_LEVEL

    # Exact match first
    if model in MODEL_TRUST_REGISTRY:
        return MODEL_TRUST_REGISTRY[model]
    # Prefix match (e.g. "qwen2.5-coder:14b-instruct-q4" matches "qwen2.5-coder:14b")
    for known_model, level in MODEL_TRUST_REGISTRY.items():
        if model.startswith(known_model.split(":")[0]):
            return level
    return DEFAULT_TRUST_LEVEL


def _strip_thinking_tokens(text: str) -> str:
    """Remove <think>...</think> blocks from reasoning models (DeepSeek-R1, QwQ, etc)."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_json(raw: str) -> Optional[Dict[str, Any]]:
    """
    Robust JSON extractor. Handles:
    - Pure JSON
    - ```json ... ``` markdown wrappers
    - JSON embedded in surrounding prose
    Returns None if no valid JSON found.
    """
    # Strip thinking tokens first
    text = _strip_thinking_tokens(raw)

    # Try pure parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown code block wrappers
    text_clean = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text_clean = re.sub(r"\s*```$", "", text_clean.strip())
    try:
        return json.loads(text_clean)
    except json.JSONDecodeError:
        pass

    # Find first JSON object in text using brace matching
    brace_depth = 0
    start_idx = None
    for i, ch in enumerate(text):
        if ch == "{":
            if start_idx is None:
                start_idx = i
            brace_depth += 1
        elif ch == "}":
            brace_depth -= 1
            if brace_depth == 0 and start_idx is not None:
                candidate = text[start_idx : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    start_idx = None
    return None


class LLMGateway:
    """
    Universal Lego Brain Socket for Amber SRE Engine.

    One generate_json() call. Works with any provider or model.
    If provider is misconfigured or model is down: returns None gracefully.
    """

    async def generate_json(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float = 0.2,
        timeout: float = 45.0,
        _retry: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Send a prompt to the configured LLM and return a parsed JSON dict.

        Returns None if:
        - LLM is unreachable / not running
        - AIR_GAPPED=True and provider is cloud
        - JSON cannot be parsed after 1 retry
        """
        provider = settings.LLM_PROVIDER.lower()

        # Hard-block cloud providers in air-gapped mode
        if settings.AIR_GAPPED and provider in ("anthropic", "openai", "gemini"):
            logger.error(
                f"[AIR-GAPPED] Blocked outbound call to cloud provider '{provider}'. "
                "Set LLM_PROVIDER=local to use a local model."
            )
            return None

        try:
            if provider == "local":
                raw = await self._call_local(prompt, system_prompt, temperature, timeout)
            elif provider == "anthropic":
                raw = await self._call_anthropic(prompt, system_prompt, temperature, timeout)
            elif provider == "openai":
                raw = await self._call_openai(prompt, system_prompt, temperature, timeout)
            elif provider == "gemini":
                raw = await self._call_gemini(prompt, system_prompt, temperature, timeout)
            else:
                logger.error(f"Unknown LLM_PROVIDER: '{provider}'. Valid: local, anthropic, openai, gemini.")
                return None
        except Exception as e:
            logger.warning(f"[LLMGateway] Provider '{provider}' call failed: {e}")
            return None

        if raw is None:
            return None

        result = _extract_json(raw)
        if result is not None:
            return result

        # 1 auto-retry: tell model its JSON was broken
        if _retry:
            logger.warning("[LLMGateway] JSON parse failed. Retrying with repair hint...")
            retry_prompt = (
                f"{prompt}\n\n"
                "CRITICAL: Your previous response could not be parsed as JSON. "
                "Return ONLY a raw valid JSON object. No markdown, no ```json, no preamble."
            )
            return await self.generate_json(
                retry_prompt, system_prompt, temperature, timeout, _retry=False
            )

        logger.error(f"[LLMGateway] JSON extraction failed after retry. Raw response: {raw[:300]}")
        return None

    # ──────────────────────────────────────────────
    # Provider Implementations
    # ──────────────────────────────────────────────

    async def _call_local(
        self, prompt: str, system_prompt: str, temperature: float, timeout: float
    ) -> Optional[str]:
        """
        Calls any OpenAI-compatible local endpoint (Ollama, vLLM, TGI, LM Studio, etc.).
        Model name comes from LOCAL_LLM_MODEL — any model the user has pulled.
        context_length=16384 prevents silent truncation of long log dumps.
        """
        endpoint = settings.LOCAL_LLM_ENDPOINT.rstrip("/")
        model = settings.LOCAL_LLM_MODEL
        url = f"{endpoint}/chat/completions"

        payload = {
            "model": model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},  # Native JSON mode (Ollama ≥0.1.14 / vLLM)
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "options": {
                "num_ctx": settings.LOCAL_LLM_CONTEXT_LENGTH,  # Prevent silent log truncation
            },
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except httpx.ConnectError:
                logger.warning(
                    f"[LLMGateway/local] Cannot connect to local LLM at '{endpoint}'. "
                    "Is Ollama/vLLM running? Falling back to heuristics."
                )
                return None
            except httpx.HTTPStatusError as e:
                logger.warning(f"[LLMGateway/local] HTTP {e.response.status_code}: {e.response.text[:200]}")
                return None

    async def _call_anthropic(
        self, prompt: str, system_prompt: str, temperature: float, timeout: float
    ) -> Optional[str]:
        """
        Calls Claude via Amber AI Proxy (client license key auth) or direct BYOK.
        Client's .env NEVER holds our Anthropic master key — proxy handles that.
        """
        # Use Amber proxy if configured (enterprise managed), else direct BYOK
        proxy_url = getattr(settings, "AMBER_AI_PROXY_URL", None)
        if proxy_url:
            endpoint = proxy_url.rstrip("/")
            headers = {
                "Authorization": f"Bearer {settings.AMBER_LICENSE_KEY}",
                "Content-Type": "application/json",
            }
        else:
            # Direct BYOK — client provides their own Anthropic key
            if not settings.ANTHROPIC_API_KEY:
                logger.error("[LLMGateway/anthropic] No ANTHROPIC_API_KEY or AMBER_AI_PROXY_URL configured.")
                return None
            endpoint = "https://api.anthropic.com"
            headers = {
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }

        payload = {
            "model": settings.ANTHROPIC_MODEL,
            "max_tokens": 2048,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}],
        }

        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            resp = await client.post(f"{endpoint}/v1/messages", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]

    async def _call_openai(
        self, prompt: str, system_prompt: str, temperature: float, timeout: float
    ) -> Optional[str]:
        """Calls OpenAI GPT-4o (or compatible) endpoint."""
        if not settings.OPENAI_API_KEY:
            logger.error("[LLMGateway/openai] No OPENAI_API_KEY configured.")
            return None

        payload = {
            "model": settings.OPENAI_MODEL,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        }

        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            resp = await client.post("https://api.openai.com/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def _call_gemini(
        self, prompt: str, system_prompt: str, temperature: float, timeout: float
    ) -> Optional[str]:
        """Calls Google Gemini via REST (no SDK import needed)."""
        if not settings.GEMINI_API_KEY:
            logger.error("[LLMGateway/gemini] No GEMINI_API_KEY configured.")
            return None

        model = settings.GEMINI_MODEL
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
            f":generateContent?key={settings.GEMINI_API_KEY}"
        )

        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
            },
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

    async def health_check(self) -> Dict[str, Any]:
        """
        Checks if the configured LLM brain is reachable and returns model info.
        Used at startup and by the /health endpoint.
        """
        provider = settings.LLM_PROVIDER.lower()
        trust_level = get_model_trust_level()

        if provider == "local":
            endpoint = settings.LOCAL_LLM_ENDPOINT.rstrip("/")
            model = settings.LOCAL_LLM_MODEL
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(f"{endpoint}/models")
                    resp.raise_for_status()
                return {
                    "status": "connected",
                    "provider": "local",
                    "model": model,
                    "endpoint": endpoint,
                    "trust_level": trust_level,
                    "context_length": settings.LOCAL_LLM_CONTEXT_LENGTH,
                }
            except Exception as e:
                return {
                    "status": "disconnected",
                    "provider": "local",
                    "model": model,
                    "endpoint": endpoint,
                    "error": str(e),
                    "trust_level": 0,
                    "message": "Local LLM not running. Amber core is still active. Heuristics will handle triage.",
                }
        else:
            return {
                "status": "cloud",
                "provider": provider,
                "model": {
                    "anthropic": settings.ANTHROPIC_MODEL,
                    "openai": settings.OPENAI_MODEL,
                    "gemini": settings.GEMINI_MODEL,
                }.get(provider, "unknown"),
                "trust_level": trust_level,
                "air_gapped_blocked": settings.AIR_GAPPED,
            }


# Global singleton Lego Brain Socket
llm_gateway = LLMGateway()
