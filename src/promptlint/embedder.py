"""Stage 3: MiniLM sentence embedding for instruction chunks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from sentence_transformers import SentenceTransformer

if TYPE_CHECKING:
    from promptlint.config import Config
    from promptlint.models import ClassifiedChunk


class InstructionEmbedder:
    """Generate dense vector representations of instruction chunks."""

    def __init__(self, config: Config):
        self.model = SentenceTransformer(config.embedder_model, device=config.device)

    def embed(self, instructions: list[ClassifiedChunk]) -> np.ndarray:
        if not instructions:
            return np.empty((0, 384), dtype=np.float32)

        texts = [inst.text for inst in instructions]
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            batch_size=max(len(texts), 1),
            show_progress_bar=False,
        )
        return np.array(embeddings, dtype=np.float32)
