"""Stage 5: Contradiction detection via NLI cross-encoder with dual pre-filtering."""

from __future__ import annotations

import re

import numpy as np
import torch
from sklearn.metrics.pairwise import cosine_similarity
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from promptlint.config import STOPWORDS, Config
from promptlint.models import ClassifiedChunk, Contradiction, RedundancyGroup


class ContradictionDetector:
    """Find pairs of instructions that impose conflicting behavioral requirements."""

    def __init__(self, config: Config, model: AutoModelForSequenceClassification, tokenizer: AutoTokenizer):
        self.config = config
        self.model = model
        self.tokenizer = tokenizer
        self.device = config.device

    def detect(
        self,
        instructions: list[ClassifiedChunk],
        embeddings: np.ndarray,
        redundancy_groups: list[RedundancyGroup],
    ) -> list[Contradiction]:
        n = len(instructions)
        if n < 2:
            return []

        # Build set of pairs to exclude (within same redundancy group)
        excluded = self._build_excluded_pairs(instructions, redundancy_groups)

        # Pre-filter: union of embedding similarity and keyword overlap
        candidate_pairs = self._prefilter(instructions, embeddings, excluded)

        if not candidate_pairs:
            return []

        # Run bidirectional NLI on candidate pairs
        return self._score_pairs(instructions, candidate_pairs)

    def _build_excluded_pairs(
        self, instructions: list[ClassifiedChunk], redundancy_groups: list[RedundancyGroup]
    ) -> set[tuple[int, int]]:
        """Build set of index pairs to exclude (same redundancy group)."""
        # Map instruction identity to index
        inst_to_idx: dict[int, int] = {id(inst): i for i, inst in enumerate(instructions)}
        excluded: set[tuple[int, int]] = set()

        for group in redundancy_groups:
            group_indices: list[int] = []
            if id(group.canonical) in inst_to_idx:
                group_indices.append(inst_to_idx[id(group.canonical)])
            for dup in group.duplicates:
                if id(dup) in inst_to_idx:
                    group_indices.append(inst_to_idx[id(dup)])
            for i in range(len(group_indices)):
                for j in range(i + 1, len(group_indices)):
                    a, b = min(group_indices[i], group_indices[j]), max(group_indices[i], group_indices[j])
                    excluded.add((a, b))

        return excluded

    def _prefilter(
        self,
        instructions: list[ClassifiedChunk],
        embeddings: np.ndarray,
        excluded: set[tuple[int, int]],
    ) -> list[tuple[int, int]]:
        """Pre-filter candidate pairs using embedding similarity and keyword overlap."""
        n = len(instructions)
        candidates: set[tuple[int, int]] = set()

        # Strategy 1: Embedding similarity > threshold
        sim_matrix = cosine_similarity(embeddings)
        for i in range(n):
            for j in range(i + 1, n):
                if sim_matrix[i, j] > self.config.similarity_prefilter:
                    candidates.add((i, j))

        # Strategy 2: Keyword overlap
        content_words = [self._extract_content_words(inst.text) for inst in instructions]
        for i in range(n):
            for j in range(i + 1, n):
                if content_words[i] & content_words[j]:
                    candidates.add((i, j))

        # Remove excluded pairs (same redundancy group)
        candidates -= excluded

        return sorted(candidates)

    def _extract_content_words(self, text: str) -> set[str]:
        """Extract content words (nouns/verbs) by removing stopwords."""
        words = re.findall(r"[a-zA-Z]+", text.lower())
        return {w for w in words if w not in STOPWORDS and len(w) > 2}

    def _score_pairs(self, instructions: list[ClassifiedChunk], pairs: list[tuple[int, int]]) -> list[Contradiction]:
        """Run bidirectional NLI on candidate pairs."""
        # Build forward and reverse pairs
        premises: list[str] = []
        hypotheses: list[str] = []
        for i, j in pairs:
            # Forward: A -> B
            premises.append(instructions[i].text)
            hypotheses.append(instructions[j].text)
            # Reverse: B -> A
            premises.append(instructions[j].text)
            hypotheses.append(instructions[i].text)

        # Batch NLI
        contradiction_scores = self._run_nli_batch(premises, hypotheses)

        # Aggregate: pairs of (forward, reverse) scores
        contradictions: list[Contradiction] = []
        for pair_idx, (i, j) in enumerate(pairs):
            fwd_score = contradiction_scores[pair_idx * 2]
            rev_score = contradiction_scores[pair_idx * 2 + 1]

            max_score = max(fwd_score, rev_score)
            min_score = min(fwd_score, rev_score)

            # Apply thresholds: max > contradiction_threshold AND min > min_reverse
            if max_score > self.config.contradiction_threshold and min_score > self.config.contradiction_min_reverse:
                # Determine direction
                if abs(fwd_score - rev_score) < 0.1:
                    direction = "bidirectional"
                elif fwd_score > rev_score:
                    direction = "a_contradicts_b"
                else:
                    direction = "b_contradicts_a"

                contradictions.append(
                    Contradiction(
                        instruction_a=instructions[i],
                        instruction_b=instructions[j],
                        score=max_score,
                        direction=direction,
                    )
                )

        # Sort by score descending
        contradictions.sort(key=lambda c: c.score, reverse=True)
        return contradictions

    def _run_nli_batch(self, premises: list[str], hypotheses: list[str]) -> list[float]:
        """Run NLI on premise-hypothesis pairs, return contradiction probabilities."""
        if not premises:
            return []

        inputs = self.tokenizer(
            premises,
            hypotheses,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)
            # DeBERTa MNLI: [contradiction=0, neutral=1, entailment=2]
            probs = torch.softmax(outputs.logits, dim=-1)
            contradiction_scores = probs[:, 0].cpu().tolist()

        return contradiction_scores
