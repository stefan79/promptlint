# Spec 11 — Orchestrator Adapter: Codex CLI

Status: Draft

## Motivation

OpenAI's Codex CLI is an open-source coding agent that assembles prompts with
system instructions, tool definitions, and multi-turn conversation. Supporting
Codex CLI as an orchestrator adapter enables promptlint to analyze prompts from
OpenAI-ecosystem coding agents.

## Goals

1. Detect Codex CLI traffic passively via wire format heuristics
2. Extract system prompt, tool definitions, and conversation structure
3. Attribute prompt sections to Codex CLI components
4. Map to the generic `OrchestratorEnvelope` from spec 05

## Research needed

- Codex CLI wire format analysis (OpenAI chat completions API shape)
- System prompt conventions and injection patterns
- Tool definition format and how tools are registered
- Multi-turn conversation structure
- Version detection heuristics (User-Agent, prompt patterns)

## Dependencies

- Spec 04 (gateway integration) — request interception
- Spec 05 (orchestrator support) — adapter protocol and envelope type
