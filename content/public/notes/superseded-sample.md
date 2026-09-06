---
id: superseded-sample
type: riff
title: Early Heuristic on Vector Indexing
date: '2026-08-01T09:00:00Z'
superseded_by: declarative-attention
summary: Initial draft on static vector partitioning before adopting dynamic query spaces.
tags:
  - draft
  - deprecated
edges:
  - target: declarative-attention
    type: superseded_by
    reason: Obsolete static vector partitioning replaced by declarative query spaces
---
This initial note proposed pre-partitioning all embedding vectors by static token clusters prior to indexing.

Subsequent benchmarks demonstrated that static clustering produces high boundary miss rates during multi-hop graph traversals. This approach has been completely superseded by dynamic query spaces.
