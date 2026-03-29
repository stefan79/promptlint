"""Two-phase pipeline runner (spec 02)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

from promptlint.chunker import chunk
from promptlint.classifier import InstructionClassifier
from promptlint.config import Config
from promptlint.contradiction import ContradictionDetector
from promptlint.embedder import InstructionEmbedder
from promptlint.models import AnalysisResult, ClassifiedChunk
from promptlint.pipeline_config import (
    BUILT_IN_METRICS,
    PipelineConfig,
    PipelineDefinition,
)
from promptlint.redundancy import RedundancyDetector
from promptlint.scorer import score


@dataclass
class PreprocessedContext:
    """Output of phase 1: shared context for all metric stages."""

    original_text: str
    classified: list[ClassifiedChunk] = field(default_factory=list)
    instructions: list[ClassifiedChunk] = field(default_factory=list)
    non_instructions: list[ClassifiedChunk] = field(default_factory=list)
    embeddings: np.ndarray | None = None
    config: Config = field(default_factory=Config)


class PipelineRunner:
    """Runs named pipelines from a PipelineConfig."""

    def __init__(self, pipeline_config: PipelineConfig) -> None:
        self._config = pipeline_config
        self._analyzers: dict[str, _PipelineAnalyzer] = {}

    def run(self, pipeline_name: str, text: str) -> AnalysisResult:
        """Run a named pipeline on input text."""
        if pipeline_name not in self._config.pipelines:
            msg = f"Unknown pipeline '{pipeline_name}'. Available: {list(self._config.pipelines)}"
            raise ValueError(msg)

        analyzer = self._get_analyzer(pipeline_name)
        return analyzer.analyze(text)

    def _get_analyzer(self, pipeline_name: str) -> _PipelineAnalyzer:
        if pipeline_name not in self._analyzers:
            pipeline_def = self._config.pipelines[pipeline_name]
            self._analyzers[pipeline_name] = _PipelineAnalyzer(pipeline_def, self._config)
        return self._analyzers[pipeline_name]


class _PipelineAnalyzer:
    """Internal: runs a single pipeline definition."""

    def __init__(self, pipeline_def: PipelineDefinition, pipeline_config: PipelineConfig) -> None:
        self._pipeline_def = pipeline_def
        self._pipeline_config = pipeline_config

        # Build config with preprocessing overrides
        self._config = self._build_config()

        # Load models once
        self._load_models()

    def _build_config(self) -> Config:
        """Build a Config with stage variant overrides applied."""
        config_overrides: dict[str, Any] = {}

        # Apply preprocessing stage variant configs
        for _slot, variant_name in self._pipeline_def.preprocessing.items():
            if variant_name in self._pipeline_config.stages:
                variant = self._pipeline_config.stages[variant_name]
                config_overrides.update(variant.config)

        # Apply metric stage variant configs
        for metric_name in self._pipeline_def.metrics:
            if metric_name in self._pipeline_config.stages:
                variant = self._pipeline_config.stages[metric_name]
                config_overrides.update(variant.config)

        return Config(**{k: v for k, v in config_overrides.items() if hasattr(Config, k)})

    def _load_models(self) -> None:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._nli_tokenizer = AutoTokenizer.from_pretrained(self._config.classifier_model)
        self._nli_model = AutoModelForSequenceClassification.from_pretrained(self._config.classifier_model)
        self._nli_model.to(self._config.device)
        self._nli_model.eval()

        self._classifier = InstructionClassifier(self._config, self._nli_model, self._nli_tokenizer)
        self._embedder = InstructionEmbedder(self._config)
        self._redundancy_detector = RedundancyDetector(self._config)
        self._contradiction_detector = ContradictionDetector(self._config, self._nli_model, self._nli_tokenizer)

    def analyze(self, text: str) -> AnalysisResult:
        """Run the two-phase pipeline."""
        # Phase 1: Preprocessing (always runs)
        ctx = self._preprocess(text)

        if not ctx.instructions:
            return score(ctx.instructions, ctx.non_instructions, [], [], ctx.classified, ctx.original_text, ctx.config)

        # Phase 2: Metric stages (parallel)
        return self._run_metrics(ctx)

    def _preprocess(self, text: str) -> PreprocessedContext:
        chunks = chunk(text, config=self._config)
        if not chunks:
            return PreprocessedContext(original_text=text, config=self._config)

        classified = self._classifier.classify(chunks)
        instructions = [c for c in classified if c.label == "instruction"]
        non_instructions = [c for c in classified if c.label == "non_instruction"]

        embeddings = self._embedder.embed(instructions) if instructions else None

        return PreprocessedContext(
            original_text=text,
            classified=classified,
            instructions=instructions,
            non_instructions=non_instructions,
            embeddings=embeddings,
            config=self._config,
        )

    def _run_metrics(self, ctx: PreprocessedContext) -> AnalysisResult:
        metrics = self._pipeline_def.metrics
        active_metrics = {m if m in BUILT_IN_METRICS else self._pipeline_config.stages[m].base for m in metrics}
        assert ctx.embeddings is not None

        redundancy_groups: list = []
        contradictions: list = []

        def run_redundancy() -> None:
            nonlocal redundancy_groups
            assert ctx.embeddings is not None
            redundancy_groups = self._redundancy_detector.detect(ctx.instructions, ctx.embeddings)

        def run_contradiction() -> None:
            nonlocal contradictions
            assert ctx.embeddings is not None
            # Contradiction needs redundancy groups for exclusion filtering.
            # If redundancy is also active, wait for it; otherwise pass empty.
            groups = redundancy_groups if "redundancy" in active_metrics else []
            contradictions = self._contradiction_detector.detect(ctx.instructions, ctx.embeddings, groups)

        # Run metric stages. Contradiction depends on redundancy, so order matters.
        if "redundancy" in active_metrics:
            run_redundancy()
        if "contradiction" in active_metrics:
            run_contradiction()

        # Scorer always runs if requested — it's the aggregator
        if "scorer" in active_metrics:
            return score(
                ctx.instructions,
                ctx.non_instructions,
                redundancy_groups,
                contradictions,
                ctx.classified,
                ctx.original_text,
                ctx.config,
            )

        # If no scorer, build a minimal result with just the metric keys present
        return AnalysisResult(
            instruction_count=len(ctx.instructions),
            non_instruction_count=len(ctx.non_instructions),
            total_chunks=len(ctx.classified),
            instructions=ctx.instructions,
            non_instructions=ctx.non_instructions,
            redundant_groups=redundancy_groups,
            contradictions=contradictions,
        )
