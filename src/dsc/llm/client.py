"""Thin wrapper around the Anthropic Claude SDK.

Provides structured output via tool_use and handles retries.
"""

from __future__ import annotations

import json
import time
from typing import Any

import anthropic


class LLMClient:
    """Client for Claude API interactions.

    Uses tool_use to enforce structured JSON output from the LLM.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        max_retries: int = 3,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.max_retries = max_retries
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def structured_request(
        self,
        system: str,
        messages: list[dict[str, str]],
        tool_name: str,
        tool_schema: dict[str, Any],
        tool_description: str = "Provide structured output",
        max_tokens: int = 8192,
    ) -> dict[str, Any]:
        """Send a request that forces structured output via tool_use.

        The LLM is forced to call the specified tool, producing validated
        JSON output matching the schema.

        Returns the parsed tool input as a dict.
        """
        tool = {
            "name": tool_name,
            "description": tool_description,
            "input_schema": tool_schema,
        }

        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=messages,
                    tools=[tool],
                    tool_choice={"type": "tool", "name": tool_name},
                )
                # Extract tool use block
                for block in response.content:
                    if block.type == "tool_use" and block.name == tool_name:
                        return block.input

                raise ValueError(f"No tool_use block found in response for {tool_name}")

            except anthropic.RateLimitError:
                last_error = "Rate limited"
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                continue
            except anthropic.APIError as e:
                last_error = str(e)
                if attempt < self.max_retries - 1:
                    time.sleep(1)
                continue

        raise RuntimeError(f"LLM request failed after {self.max_retries} attempts: {last_error}")

    def text_request(
        self,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int = 4096,
    ) -> str:
        """Send a simple text request and return the text response."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        parts = []
        for block in response.content:
            if block.type == "text":
                parts.append(block.text)
        return "\n".join(parts)
