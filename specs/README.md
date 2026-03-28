# promptlint specs

## Implementation sequence

| Priority | Spec | Rationale |
|----------|------|-----------|
| 01 | [Core Pipeline](01-core-pipeline.md) | **Done.** Foundation everything else builds on. |
| 02 | [Pipeline DSL](02-pipeline-dsl.md) | Must come first — defines the YAML building-block language that all other specs plug into. Without composable pipelines, backends/gateways/orchestrators have nothing to attach to. |
| 03 | [Storage Backends](03-storage-backends.md) | Pipelines need somewhere to write. Enables observability before we tackle live traffic. |
| 04 | [Gateway Integration](04-gateway-integration.md) | Depends on 02+03: intercepts live LLM traffic, runs a pipeline, writes to a backend. Replaces the hard-coded proxy from 01. |
| 05 | [Orchestrator Support (Passive)](05-orchestrator-support.md) | Depends on 02+03+04: parse orchestrator conventions from wire traffic. No orchestrator modification. |
| 06 | [Configuration Language](06-configuration.md) | Glue layer — references pipelines, backends, gateways, and orchestrators. Must know the surface area of everything it wires together. |
| 07 | [Benchmarks](07-benchmarks.md) | Requires full round-trip integration (orchestrator → gateway → pipeline → backend) before real-world benchmarks are meaningful. Extracted from 01. |
| 08 | [Orchestrator Plugins (Active)](08-orchestrator-plugins.md) | Install hooks/skills in orchestrators for explicit tagging, version reporting, and in-orchestrator feedback. Enriches passive observation from 05. |
