"""Configuration and thresholds for promptlint."""

from __future__ import annotations

from dataclasses import dataclass, field

INSTRUCTION_HYPOTHESES = [
    "This is a behavioral instruction or constraint for an AI assistant.",
    "This is a rule or directive that must be followed.",
    "This text tells the AI what to do or not do.",
]

NON_INSTRUCTION_HYPOTHESIS = "This is background context, a definition, or an example."

# Minimal English stopword set for keyword overlap pre-filtering.
STOPWORDS: frozenset[str] = frozenset(
    "a an the is are was were be been being have has had do does did will would shall "
    "should can could may might must need to of in on at by for with from as into through "
    "during before after above below between out off over under again further then once "
    "here there when where why how all each every both few more most other some such no "
    "nor not only own same so than too very just about also back even still already always "
    "never now often sometimes usually i me my we us our you your he him his she her it its "
    "they them their this that these those what which who whom if or and but because since "
    "while although though however therefore thus hence instead unless until yet".split()
)


@dataclass
class Config:
    # Model names
    classifier_model: str = "microsoft/deberta-v3-base-mnli"
    embedder_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    device: str = "cpu"

    # Stage 2: Classification
    classification_threshold: float = 0.65

    # Stage 4: Redundancy
    redundancy_similarity: float = 0.80
    hdbscan_min_cluster_size: int = 2
    hdbscan_min_samples: int = 1
    hdbscan_epsilon: float = 0.20
    small_dataset_threshold: int = 20

    # Stage 5: Contradiction
    contradiction_threshold: float = 0.7
    contradiction_min_reverse: float = 0.4
    similarity_prefilter: float = 0.3

    # Stage 1: Chunker
    min_chunk_words: int = 2

    # Stage 6: Severity thresholds
    warn_instructions: int = 80
    critical_instructions: int = 150
    warn_density: float = 60.0
    critical_density: float = 90.0
    warn_contradictions: int = 1
    critical_contradictions: int = 3
