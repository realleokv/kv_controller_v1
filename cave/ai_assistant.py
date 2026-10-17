# ai_assistant.py
"""
Optional conversational AI assistant layer supporting local Ollama or OpenAI-compatible
endpoints while remaining strictly isolated from OS shell execution.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import requests

from cave.command_registry import CommandRegistry

logger = logging.getLogger("cave.ai_assistant")


class ConversationalAssistant:
    """
    Answers general questions, explains programming concepts, or generates text
    when explicitly queried. Output is never executed as OS commands.
    """

    SYSTEM_PROMPT = (
        "Você é CAVE (KV), um assistente pessoal futurista, conciso e prestativo em "
        "português do Brasil. Responda em 1 a 3 frases curtas e diretas, adequadas para "
        "leitura em voz alta. Nunca gere comandos destrutivos do sistema."
    )

    def __init__(self, registry: CommandRegistry) -> None:
        self._registry = registry

    def ask(self, prompt: str) -> str:
        if not self._registry.get_setting("ai_enabled", False):
            return (
                "O módulo conversacional de IA está desativado nas configurações. "
                "Comandos locais do computador continuam ativos."
            )

        provider = os.getenv(
            "CAVE_AI_PROVIDER",
            str(self._registry.get_setting("ai_provider", "none")),
        ).lower()
        base_url = os.getenv("CAVE_AI_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/")
        model = os.getenv("CAVE_AI_MODEL", "llama3.2")
        api_key: Optional[str] = os.getenv("CAVE_AI_API_KEY", "")

        if provider in ("none", ""):
            return "Nenhum provedor de IA está configurado no momento."

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
            "max_tokens": 220,
        }

        try:
            response = requests.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=8.0,
            )
            response.raise_for_status()
            data = response.json()
            reply = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            return reply or "Não obtive resposta do modelo de IA."
        except Exception as exc:
            logger.warning("Conversational AI request failed: %s", exc)
            return "Serviço de IA indisponível no momento. Controles locais seguem operando offline."