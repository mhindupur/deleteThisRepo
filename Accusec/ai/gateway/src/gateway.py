"""Deterministic path: no model call. Gateway still records that the model was not used."""


class AiGateway:
    def complete(self, *, context_id: str, prompt: str) -> dict:
        return {
            "blocked": False,
            "used_model": False,
            "context_id": context_id,
            "note": "Deterministic runtime — LLM not required for this task.",
            "prompt_chars": len(prompt),
        }
