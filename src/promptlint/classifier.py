"""Stage 2: DeBERTa zero-shot NLI instruction classification."""

from __future__ import annotations

import logging

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer  # noqa: TC002

from promptlint.config import INSTRUCTION_HYPOTHESES, Config
from promptlint.models import Chunk, ClassifiedChunk

logger = logging.getLogger("promptlint.pipeline")


class InstructionClassifier:
    """Classify chunks as instruction or non-instruction using zero-shot NLI."""

    def __init__(self, config: Config, model: AutoModelForSequenceClassification, tokenizer: AutoTokenizer):
        self.config = config
        self.model = model
        self.tokenizer = tokenizer
        self.device = config.device
        model_cfg = getattr(model, "config", None)
        label2id: dict[str, int] = getattr(model_cfg, "label2id", {}) if model_cfg else {}
        self._entailment_idx: int = label2id.get("entailment", label2id.get("ENTAILMENT", 2))

    def classify(self, chunks: list[Chunk]) -> list[ClassifiedChunk]:
        if not chunks:
            return []

        # Build premise-hypothesis pairs: 3 hypotheses per chunk
        premises = []
        hypotheses = []
        for c in chunks:
            for hyp in INSTRUCTION_HYPOTHESES:
                premises.append(c.text)
                hypotheses.append(hyp)

        # Batch inference
        scores = self._run_nli_batch(premises, hypotheses)

        # Group scores per chunk (3 per chunk), take max entailment score
        results: list[ClassifiedChunk] = []
        for i, c in enumerate(chunks):
            chunk_scores = scores[i * 3 : (i + 1) * 3]
            max_score = max(chunk_scores)
            label = "instruction" if max_score > self.config.classification_threshold else "non_instruction"
            results.append(
                ClassifiedChunk(
                    text=c.text,
                    source_section=c.source_section,
                    start_offset=c.start_offset,
                    end_offset=c.end_offset,
                    structural_type=c.structural_type,
                    label=label,
                    confidence=max_score,
                )
            )

        return results

    def _run_nli_batch(self, premises: list[str], hypotheses: list[str], batch_size: int = 30) -> list[float]:
        """Run NLI on premise-hypothesis pairs in mini-batches, return entailment probabilities."""
        if not premises:
            return []

        all_scores: list[float] = []
        total = len(premises)
        n_chunks = total // 3  # 3 hypotheses per chunk

        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            inputs = self.tokenizer(  # type: ignore[operator]
                premises[start:end],
                hypotheses[start:end],
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            ).to(self.device)

            with torch.no_grad():
                outputs = self.model(**inputs)  # type: ignore[operator]
                probs = torch.softmax(outputs.logits, dim=-1)
            all_scores.extend(probs[:, self._entailment_idx].cpu().tolist())

            chunks_done = min(end // 3, n_chunks)
            logger.info("  [classifier]     %d/%d chunks classified...", chunks_done, n_chunks)

        return all_scores
