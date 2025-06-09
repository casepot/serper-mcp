import pytest
from src.serper_mcp_server import _resolve_entities_with_splink as _resolve_entities

def test_resolve_entities_simple_clustering():
    """
    Tests that simple variations of the same entity are clustered correctly.
    """
    extracted_relationships = [
        {"source": "ARPANET", "target": "Computers", "relationship": "used", "strength": 0.9},
        {"source": "Arpanet", "target": "Networking", "relationship": "pioneered", "strength": 0.8},
        {"source": "The ARPANET", "target": "US Military", "relationship": "funded by", "strength": 0.9},
        {"source": "Tim Berners-Lee", "target": "World Wide Web", "relationship": "invented", "strength": 1.0},
        {"source": "Sir Tim Berners-Lee", "target": "MIT", "relationship": "works at", "strength": 0.7},
    ]

    canonical_map = _resolve_entities(extracted_relationships)

    # Check that variations of ARPANET map to the same canonical name
    arpanet_canonical = canonical_map["ARPANET"]
    assert canonical_map["Arpanet"] == arpanet_canonical
    assert canonical_map["The ARPANET"] == arpanet_canonical
    assert "arpanet" in arpanet_canonical.lower()

    # Check that variations of Tim Berners-Lee map to the same canonical name
    tbl_canonical = canonical_map["Tim Berners-Lee"]
    assert canonical_map["Sir Tim Berners-Lee"] == tbl_canonical
    assert "tim berners-lee" in tbl_canonical.lower()

    # Check that unrelated entities are not clustered
    assert canonical_map["Computers"] == "Computers"
    assert canonical_map["World Wide Web"] == "World Wide Web"

def test_resolve_entities_no_matches():
    """
    Tests that entities with no similarity are not clustered.
    """
    extracted_relationships = [
        {"source": "Apple Inc.", "target": "iPhone", "relationship": "produces", "strength": 1.0},
        {"source": "Google", "target": "Android", "relationship": "develops", "strength": 1.0},
        {"source": "Microsoft", "target": "Windows", "relationship": "develops", "strength": 1.0},
    ]

    canonical_map = _resolve_entities(extracted_relationships)

    assert canonical_map["Apple Inc."] == "Apple Inc."
    assert canonical_map["Google"] == "Google"
    assert canonical_map["Microsoft"] == "Microsoft"

def test_resolve_entities_empty_input():
    """
    Tests that the function handles empty input gracefully.
    """
    extracted_relationships = []
    canonical_map = _resolve_entities(extracted_relationships)
    assert canonical_map == {}