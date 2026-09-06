import pytest
from app.services.curriculum import CurriculumIngestionService, slugify


SAMPLE_LESSON_TEXT = """MODULE 2 | LESSON 1
Network Effects, Platforms, and Systemic Fragility
Reading Time	60 minutes
Keywords	network effects, platforms, feedback loops, fragile architecture, two-sided markets

Every platform creates an invisible coordination layer.

1.1 Direct Network Effects
Direct network effects occur when a product becomes more valuable as more people use it.
Telephone networks and messaging apps are classic examples.

1.2 Two-Sided Platform Vulnerability: When Balance Breaks
In two-sided platforms, buyers and sellers depend mutually on market liquidity.
When a shock arrives, the feedback loop can run in reverse.
"""


def test_slugify_clean_titles():
    assert slugify("The Invisible Infrastructure") == "the-invisible-infrastructure"
    assert slugify("1.2 Single Points of Failure") == "single-points-of-failure"
    assert slugify("Case: Automated Floodgate Failure") == "case-automated-floodgate-failure"
    assert slugify("Just-in-Time Efficiency Versus Resilience: A Design Tradeoff") == "just-in-time-efficiency-versus-resilience"


def test_parse_curriculum_text():
    module, concepts = CurriculumIngestionService.parse_curriculum_text(SAMPLE_LESSON_TEXT)

    assert module.module_id == "M2L1"
    assert module.title == "Network Effects, Platforms, and Systemic Fragility"
    assert len(concepts) == 2

    # Concept 1
    c1 = concepts[0]
    assert c1.slug == "direct-network-effects"
    assert c1.module == "M2L1"
    assert c1.order == 1
    assert "Direct network effects occur" in c1.summary
    assert "network effects" in c1.keywords

    # Concept 2
    c2 = concepts[1]
    assert c2.slug == "two-sided-platform-vulnerability"
    assert c2.module == "M2L1"
    assert c2.order == 2
    assert "two-sided platforms" in c2.summary.lower()


def test_parse_markdown_header_fallback():
    md_text = """# Foundations of Distributed Systems

## Consensus Protocols
Raft and Paxos guarantee state machine replication across nodes.

## Split-Brain Hazard
Partitioning can lead to split-brain if quorum is not enforced.
"""
    module, concepts = CurriculumIngestionService.parse_curriculum_text(md_text, fallback_module="M3L1")
    assert module.module_id == "M3L1"
    assert len(concepts) == 2
    assert concepts[0].slug == "consensus-protocols"
    assert concepts[1].slug == "split-brain-hazard"
