"""Stage 4: Redundancy detection via HDBSCAN clustering or pairwise similarity."""

from __future__ import annotations

from collections import defaultdict

import hdbscan
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from promptlint.config import Config
from promptlint.models import ClassifiedChunk, RedundancyGroup


class RedundancyDetector:
    """Group semantically equivalent instructions to identify redundancy."""

    def __init__(self, config: Config):
        self.config = config

    def detect(self, instructions: list[ClassifiedChunk], embeddings: np.ndarray) -> list[RedundancyGroup]:
        n = len(instructions)
        if n < 2:
            return []

        if n < self.config.small_dataset_threshold:
            return self._pairwise_grouping(instructions, embeddings)
        return self._hdbscan_grouping(instructions, embeddings)

    def _hdbscan_grouping(self, instructions: list[ClassifiedChunk], embeddings: np.ndarray) -> list[RedundancyGroup]:
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=self.config.hdbscan_min_cluster_size,
            min_samples=self.config.hdbscan_min_samples,
            metric="cosine",
            cluster_selection_epsilon=self.config.hdbscan_epsilon,
        )
        labels = clusterer.fit_predict(embeddings)

        # Group by cluster label (skip noise = -1)
        clusters: dict[int, list[int]] = defaultdict(list)
        for i, label in enumerate(labels):
            if label >= 0:
                clusters[label].append(i)

        sim_matrix = cosine_similarity(embeddings)
        return self._build_groups(instructions, clusters, sim_matrix)

    def _pairwise_grouping(self, instructions: list[ClassifiedChunk], embeddings: np.ndarray) -> list[RedundancyGroup]:
        sim_matrix = cosine_similarity(embeddings)
        n = len(instructions)

        # Union-find for single-linkage clustering
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        # Link pairs above similarity threshold
        for i in range(n):
            for j in range(i + 1, n):
                if sim_matrix[i, j] >= self.config.redundancy_similarity:
                    union(i, j)

        # Group by root
        clusters: dict[int, list[int]] = defaultdict(list)
        for i in range(n):
            root = find(i)
            clusters[root].append(i)

        # Only keep groups with 2+ members
        clusters = {k: v for k, v in clusters.items() if len(v) >= 2}

        return self._build_groups(instructions, clusters, sim_matrix)

    def _build_groups(
        self,
        instructions: list[ClassifiedChunk],
        clusters: dict[int, list[int]],
        sim_matrix: np.ndarray,
    ) -> list[RedundancyGroup]:
        groups: list[RedundancyGroup] = []
        for indices in clusters.values():
            if len(indices) < 2:
                continue

            # Pick canonical as highest confidence
            members = [(idx, instructions[idx]) for idx in indices]
            members.sort(key=lambda x: x[1].confidence, reverse=True)
            canonical = members[0][1]
            duplicates = [m[1] for m in members[1:]]

            # Mean pairwise similarity within group
            group_indices = [m[0] for m in members]
            sims = []
            for i_idx in range(len(group_indices)):
                for j_idx in range(i_idx + 1, len(group_indices)):
                    sims.append(sim_matrix[group_indices[i_idx], group_indices[j_idx]])
            mean_sim = float(np.mean(sims)) if sims else 0.0

            groups.append(
                RedundancyGroup(
                    canonical=canonical,
                    duplicates=duplicates,
                    similarity=mean_sim,
                )
            )

        # Sort by group size descending
        groups.sort(key=lambda g: len(g.duplicates), reverse=True)
        return groups
