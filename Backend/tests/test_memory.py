"""
tests/test_memory.py — Tests for Cross-Meeting Semantic Memory Layer (RAG)
"""

import pytest
from core.memory_service import generate_embedding, cosine_similarity, memory_service


def test_generate_embedding_dimensions():
    vec = generate_embedding("Weekly team sync meeting on software architecture and auth migration")
    assert len(vec) == 768
    assert isinstance(vec[0], float)


def test_generate_embedding_empty():
    vec = generate_embedding("")
    assert len(vec) == 768
    assert all(v == 0.0 for v in vec)


def test_cosine_similarity():
    v1 = generate_embedding("authentication security login oauth")
    v2 = generate_embedding("user login oauth authentication token")
    v3 = generate_embedding("gardening flowers soil plants")

    sim_related = cosine_similarity(v1, v2)
    sim_unrelated = cosine_similarity(v1, v3)

    assert sim_related > sim_unrelated


@pytest.mark.asyncio
async def test_memory_indexing_and_search(db_session, seeded_meeting):
    indexed = await memory_service.index_meeting(db_session, seeded_meeting.id)
    assert indexed is True

    matches = await memory_service.search_memory(db_session, query="sprint goals standup", top_k=2)
    assert len(matches) >= 1
    assert matches[0]["meeting_id"] == seeded_meeting.id
    assert matches[0]["title"] == "Weekly Standup"


@pytest.mark.asyncio
async def test_memory_search_endpoint(authenticated_client):
    resp = await authenticated_client.post("/memory/search", json={"query": "Weekly Standup", "top_k": 2})
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "Weekly Standup"
    assert "matches" in data

