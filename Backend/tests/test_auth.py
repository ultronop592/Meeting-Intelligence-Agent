import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_register_user_success(async_client):
    payload = {
        "email": "newuser@example.com",
        "password": "SecretPassword123!",
        "full_name": "New User",
    }
    resp = await async_client.post("/auth/register", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "newuser@example.com"
    assert data["user"]["full_name"] == "New User"


@pytest.mark.asyncio
async def test_register_user_duplicate_email(async_client, seeded_user):
    payload = {
        "email": seeded_user.email,
        "password": "SecretPassword123!",
        "full_name": "Duplicate User",
    }
    resp = await async_client.post("/auth/register", json=payload)
    assert resp.status_code == 400
    assert "already exists" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_login_user_success(async_client, seeded_user):
    payload = {
        "email": "testuser@example.com",
        "password": "Password123!",
    }
    resp = await async_client.post("/auth/login", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == "testuser@example.com"


@pytest.mark.asyncio
async def test_login_user_invalid_password(async_client, seeded_user):
    payload = {
        "email": "testuser@example.com",
        "password": "WrongPassword!",
    }
    resp = await async_client.post("/auth/login", json=payload)
    assert resp.status_code == 401
    assert "Invalid email or password" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_me_success(authenticated_client, seeded_user):
    resp = await authenticated_client.get("/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == seeded_user.id
    assert data["email"] == seeded_user.email


@pytest.mark.asyncio
async def test_get_me_unauthorized(async_client):
    resp = await async_client.get("/auth/me")
    assert resp.status_code == 401
