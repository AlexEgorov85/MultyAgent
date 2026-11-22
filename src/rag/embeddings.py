"""Эмбеддинги для RAG."""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

from .. import telemetry

TOKEN_RE = re.compile(r"[0-9a-zA-Zа-яА-ЯёЁ]+")


class EmbeddingClient(Protocol):
    """Контракт клиента эмбеддингов: текст → векторы."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbeddings:
    """Эмбеддинги через OpenAI-совместимый endpoint."""

    def __init__(self, model: str | None = None, client=None) -> None:
        import os

        if client is None:
            from openai import OpenAI

            client = OpenAI(
                api_key=os.getenv("OPENAI_API_KEY"),
                base_url=os.getenv("OPENAI_BASE_URL") or None,
            )
        self.client = client
        self.model = model or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

    @telemetry.timed_embedding("embed_query")
    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self.client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in response.data]


class HashEmbeddings:
    """Детерминированные офлайн-эмбеддинги для тестов и демо без ключа."""

    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim

    @telemetry.timed_embedding("embed_hash")
    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dim
            for token in TOKEN_RE.findall(text.lower()):
                index = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % self.dim
                vector[index] += 1.0
            norm = sum(value * value for value in vector) ** 0.5 or 1.0
            vectors.append([value / norm for value in vector])
        return vectors
