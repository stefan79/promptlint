"""Stage 2: DeBERTa zero-shot NLI instruction classification."""

from __future__ import annotations

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer  # noqa: TC002

from promptlint.config import INSTRUCTION_HYPOTHESES, Config
from promptlint.models import Chunk, ClassifiedChunk


class InstructionClassifier:
    """Classify chunks as instruction or non-instruction using zero-shot NLI."""

    def __init__(self, config: Config, model: AutoModelForSequenceClassification, tokenizer: AutoTokenizer):
        self.config = config
        self.model = model
        self.tokenizer = tokenizer
        self.device = config.device

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

    def _run_nli_batch(self, premises: list[str], hypotheses: list[str]) -> list[float]:
        """Run NLI on premise-hypothesis pairs, return entailment probabilities."""
        if not premises:
            return []

        inputs = self.tokenizer(  # type: ignore[operator]
            premises,
            hypotheses,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)  # type: ignore[operator]
            # DeBERTa MNLI: [contradiction, neutral, entailment]
            probs = torch.softmax(outputs.logits, dim=-1)
        return probs[:, 2].cpu().tolist()
