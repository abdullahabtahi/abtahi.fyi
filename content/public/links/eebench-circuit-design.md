---
id: eebench-circuit-design
type: link
title: "EEBench: Measuring Hardware Efficiency in Tensor Compilers"
date: '2026-09-04T10:00:00Z'
canonical_url: https://eebench.org/paper/circuit-design
domain: eebench.org
summary: Hardware-aware tensor scheduling reduces memory bus contention by 42% across dense attention kernels.
commentary: The critical insight here is that memory bus saturation, not raw arithmetic FLOP limits, dictates real-world token generation latency at batch size 1.
tags:
  - hardware
  - tensor-compilers
  - benchmarking
edges:
  - target: declarative-attention
    type: supports
    reason: Validates memory bus efficiency when evaluating declarative attention kernels
---
> "Hardware-aware tensor scheduling reduces memory bus contention by 42% across dense attention kernels."

The critical insight here is that memory bus saturation, not raw arithmetic FLOP limits, dictates real-world token generation latency at batch size 1. Prior benchmarking frameworks over-indexed on synthetic throughput metrics while ignoring thermal throttling and memory-bandwidth stalls.
