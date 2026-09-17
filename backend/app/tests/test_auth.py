def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_register_and_login(client):
    resp = client.post("/api/v1/auth/register", json={
        "email": "test@example.com", "password": "SecurePass123!",
        "full_name": "Test User", "role": "analyst",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert "access_token" in body
    assert body["user"]["email"] == "test@example.com"

    resp2 = client.post("/api/v1/auth/login", json={
        "email": "test@example.com", "password": "SecurePass123!",
    })
    assert resp2.status_code == 200
    assert "access_token" in resp2.json()


def test_login_wrong_password_rejected(client):
    client.post("/api/v1/auth/register", json={
        "email": "user2@example.com", "password": "CorrectPass1!",
        "full_name": "User Two", "role": "viewer",
    })
    resp = client.post("/api/v1/auth/login", json={
        "email": "user2@example.com", "password": "WrongPass!",
    })
    assert resp.status_code == 401


def test_duplicate_registration_rejected(client):
    payload = {"email": "dupe@example.com", "password": "Password123!",
               "full_name": "Dupe User", "role": "analyst"}
    r1 = client.post("/api/v1/auth/register", json=payload)
    assert r1.status_code == 201
    r2 = client.post("/api/v1/auth/register", json=payload)
    assert r2.status_code == 400


def test_me_requires_auth(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_me_with_valid_token(client):
    reg = client.post("/api/v1/auth/register", json={
        "email": "me@example.com", "password": "Password123!",
        "full_name": "Me User", "role": "admin",
    })
    token = reg.json()["access_token"]
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@example.com"
