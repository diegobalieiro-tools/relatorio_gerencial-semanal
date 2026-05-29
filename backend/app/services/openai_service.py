from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.services.storage_service import StoredFileContext

settings = get_settings()
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


@dataclass
class OpenAIJsonResult:
    data: dict[str, Any]
    raw_text: str
    model_used: str
    tokens_input: int | None = None
    tokens_output: int | None = None


class OpenAIService:
    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY não configurada no arquivo .env.")
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    def load_prompt(self, filename: str) -> str:
        path = PROMPTS_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"Prompt não encontrado: {path}")
        return path.read_text(encoding="utf-8")

    def render_prompt(self, template: str, variables: dict[str, Any]) -> str:
        rendered = template
        for key, value in variables.items():
            if isinstance(value, (dict, list)):
                text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
            elif value is None:
                text = ""
            else:
                text = str(value)
            rendered = rendered.replace("{" + key + "}", text)
        return rendered

    def _json_from_text(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            if not match:
                raise
            parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValueError("A resposta JSON precisa ser um objeto.")
        return parsed

    def _usage(self, response: Any) -> tuple[int | None, int | None]:
        usage = getattr(response, "usage", None)
        if not usage:
            return None, None
        return getattr(usage, "prompt_tokens", None), getattr(usage, "completion_tokens", None)

    def _content_with_files(self, prompt: str, files: list[StoredFileContext] | None = None) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for file in files or []:
            if file.data_url:
                content.append({"type": "image_url", "image_url": {"url": file.data_url}})
        return content

    async def _call_chat_api(
        self,
        model: str,
        prompt: str,
        files: list[StoredFileContext] | None = None,
        force_json: bool = True,
    ) -> tuple[str, int | None, int | None]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": self._content_with_files(prompt, files),
                }
            ],
        }
        if force_json:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self.client.chat.completions.create(**kwargs)
        text = response.choices[0].message.content or ""
        tin, tout = self._usage(response)
        return text, tin, tout

    async def _repair_json(self, text: str, model: str) -> str:
        prompt = (
            "Corrija a resposta abaixo para JSON válido. "
            "Retorne somente JSON, sem Markdown e sem comentários.\n\n"
            f"RESPOSTA ORIGINAL:\n{text}"
        )
        response = await self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or "{}"


    async def run_inline_prompt_json(
        self,
        prompt: str,
        model: str | None = None,
    ) -> OpenAIJsonResult:
        """Executa um prompt dinâmico e retorna JSON válido.

        Usado em fluxos de revisão/reprocessamento, quando o prompt depende
        de instruções escritas pelo usuário em tempo real e não de um arquivo
        fixo em `app/prompts`.
        """
        primary = model or settings.openai_model_primary
        candidates = [primary]
        if settings.openai_model_fallback and settings.openai_model_fallback not in candidates:
            candidates.append(settings.openai_model_fallback)

        last_error: Exception | None = None
        for candidate in candidates:
            try:
                raw_text, tin, tout = await self._call_chat_api(candidate, prompt, files=None, force_json=True)
                try:
                    data = self._json_from_text(raw_text)
                except Exception:
                    repaired = await self._repair_json(raw_text, candidate)
                    raw_text = repaired
                    data = self._json_from_text(repaired)
                return OpenAIJsonResult(
                    data=data,
                    raw_text=raw_text,
                    model_used=candidate,
                    tokens_input=tin,
                    tokens_output=tout,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue

        raise RuntimeError(f"Falha ao obter JSON válido da OpenAI: {last_error}")

    async def run_prompt_json(
        self,
        prompt_filename: str,
        variables: dict[str, Any],
        files: list[StoredFileContext] | None = None,
        model: str | None = None,
    ) -> OpenAIJsonResult:
        prompt_template = self.load_prompt(prompt_filename)
        prompt = self.render_prompt(prompt_template, variables)
        primary = model or settings.openai_model_primary
        candidates = [primary]
        if settings.openai_model_fallback and settings.openai_model_fallback not in candidates:
            candidates.append(settings.openai_model_fallback)

        last_error: Exception | None = None
        for candidate in candidates:
            try:
                raw_text, tin, tout = await self._call_chat_api(candidate, prompt, files)
                try:
                    data = self._json_from_text(raw_text)
                except Exception:
                    repaired = await self._repair_json(raw_text, candidate)
                    raw_text = repaired
                    data = self._json_from_text(repaired)
                return OpenAIJsonResult(
                    data=data,
                    raw_text=raw_text,
                    model_used=candidate,
                    tokens_input=tin,
                    tokens_output=tout,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue

        raise RuntimeError(f"Falha ao obter JSON válido da OpenAI: {last_error}")
