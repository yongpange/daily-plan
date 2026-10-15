"""每日必做四则运算挑战题生成。"""

from __future__ import annotations

import random

from app.core.database import ROUTINE_SYMBOLS
from app.core.errors import AppError


def generate_routine_questions(count: int = 3) -> list[dict]:
    rng = random.SystemRandom()
    questions: list[dict] = []
    prompts: set[str] = set()
    attempts = 0
    while len(questions) < count:
        attempts += 1
        if attempts > 40:
            raise AppError("暂时无法生成题目，请再试一次")
        question = _routine_question(rng)
        if question["prompt"] in prompts:
            continue
        if any(symbol not in question["prompt"] for symbol in ROUTINE_SYMBOLS):
            continue
        prompts.add(question["prompt"])
        questions.append(question)
    return questions


def _routine_question(rng: random.SystemRandom) -> dict:
    divisor = rng.randint(2, 9)
    factor = rng.randint(2, 8)
    inner = rng.randint(2, 12)
    while (inner * factor) % divisor != 0:
        inner += 1
    subtrahend = rng.randint(1, 12)
    total = inner + subtrahend
    left = rng.randint(2, max(2, total - 1))
    right = total - left
    answer = (inner * factor) // divisor
    prompt = f"(({left} + {right}) − {subtrahend}) × {factor} ÷ {divisor}"
    return {"prompt": prompt, "answer": answer}
