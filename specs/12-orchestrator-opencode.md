# Spec 12 — Orchestrator Adapter: OpenCode

Status: Draft

## Motivation

OpenCode is an open-source terminal-based AI coding assistant that supports
multiple LLM providers. Supporting OpenCode as an orchestrator adapter enables
promptlint to analyze prompts from this growing ecosystem.

## Goals

1. Detect OpenCode traffic passively via wire format heuristics
2. Extract system prompt, tool definitions, and conversation structure
3. Attribute prompt sections to OpenCode components
4. Map to the generic `OrchestratorEnvelope` from spec 05

## Research needed

- OpenCode wire format analysis (which LLM APIs does it call?)
- System prompt conventions and injection patterns
- Tool/skill registration and how they appear in requests
- Multi-turn conversation structure
- Version detection heuristics (User-Agent, prompt markers)

## Dependencies

- Spec 04 (gateway integration) — request interception
- Spec 05 (orchestrator support) — adapter protocol and envelope type
