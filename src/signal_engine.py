import json
import re

from anthropic import Anthropic

_PROMPT_TEMPLATE = """You are a calibrated sports forecasting assistant. Given a Polymarket \
prediction market question, estimate the true probability that it resolves YES.

Market question: {question}
Market description: {description}
Current market-implied probability (YES price): {yes_price:.3f}

Respond with ONLY a JSON object, no other text:
{{"probability": <float between 0 and 1>, "reasoning": "<one sentence>"}}
"""


class SignalEngine:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5"):
        self._client = Anthropic(api_key=api_key)
        self._model = model

    def estimate_probability(self, question: str, description: str, yes_price: float) -> float:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": _PROMPT_TEMPLATE.format(
                        question=question, description=description, yes_price=yes_price
                    ),
                }
            ],
        )
        text = "".join(block.text for block in message.content if hasattr(block, "text"))
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"Could not parse a JSON probability from model output: {text!r}")
        parsed = json.loads(match.group(0))
        prob = float(parsed["probability"])
        if not 0.0 <= prob <= 1.0:
            raise ValueError(f"Model returned an out-of-range probability: {prob}")
        return prob
