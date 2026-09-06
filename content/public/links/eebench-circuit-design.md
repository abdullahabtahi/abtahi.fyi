---
id: eebench-circuit-design
type: link
title: "EEBench: Physics-Backed Electrical Engineering Benchmark by atopile"
date: '2026-09-04T10:00:00Z'
canonical_url: https://eebench.org/
domain: eebench.org
summary: A physics-backed benchmark evaluating frontier AI models on electrical engineering tasks and real circuit synthesis using SPICE simulation and component tolerance analysis.
commentary: Unlike subjective LLM-as-a-judge evaluations, EEBench grounds agentic evaluation in physical reality. By expressing hardware as code (atopile), AI agents iteratively modify netlists and run SPICE simulations to verify physical constraints.
tags:
  - hardware
  - circuit-design
  - benchmarking
  - atopile
edges:
  - target: declarative-attention
    type: supports
    reason: Demonstrates code-native declarative hardware representation and physics-based validation
---
> "A physics-backed benchmark for frontier-model electrical-engineering performance."

EEBench tests whether frontier AI models can perform electrical engineering design using code-native representations (atopile). Rather than grading textual explanations or visual schematics, it compiles designs to SPICE simulations and verifies component tolerance and thermal constraints against real physics.
