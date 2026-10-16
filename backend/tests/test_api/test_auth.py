"""登录与鉴权接口测试。P0-09。"""
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.services.auth_service import create_user

LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_login_success(client, db: Session) -> None:
    create_user(db, "alice", "secret123", role="teacher", display_name="Alice")

    resp = client.post(LOGIN_URL, json={"username": "alice", "password": "secret123"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and body["access_token"]
    user = body["user"]
    assert user["username"] == "alice"
    assert user["role"] == "teacher"
    assert user["display_name"] == "Alice"


def test_login_token_is_valid_jwt(client, db: Session) -> None:
    user = create_user(db, "bob", "pw", role="student")

    resp = client.post(LOGIN_URL, json={"username": "bob", "password": "pw"})

    token = resp.json()["access_token"]
    payload = decode_access_token(token)
    assert payload["sub"] == str(user.id)
    assert payload["role"] == "student"


def test_login_wrong_password(client, db: Session) -> None:
    create_user(db, "alice", "secret123", role="teacher")

    resp = client.post(LOGIN_URL, json={"username": "alice", "password": "wrong"})

    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHORIZED"


def test_login_unknown_user(client) -> None:
    resp = client.post(LOGIN_URL, json={"username": "ghost", "password": "whatever"})

    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHORIZED"


def test_login_missing_password(client, db: Session) -> None:
    resp = client.post(LOGIN_URL, json={"username": "alice"})

    assert resp.status_code == 422


def test_me_success(client, db: Session) -> None:
    create_user(db, "alice", "secret123", role="teacher")

    token = client.post(
        LOGIN_URL, json={"username": "alice", "password": "secret123"}
    ).json()["access_token"]

    resp = client.get(ME_URL, headers=_auth_headers(token))

    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"


def test_me_without_token(client) -> None:
    resp = client.get(ME_URL)

    assert resp.status_code == 401


def test_me_with_malformed_header(client) -> None:
    resp = client.get(ME_URL, headers={"Authorization": "NotBearer abc"})

    assert resp.status_code == 401


def test_me_with_invalid_token(client) -> None:
    resp = client.get(ME_URL, headers=_auth_headers("this.is.not.a.jwt"))

    assert resp.status_code == 401


def test_me_rejects_inactive_user(client, db: Session) -> None:
    user = create_user(db, "disabled", "secret123", role="teacher")
    user.is_active = False
    db.commit()

    token = client.post(
        LOGIN_URL, json={"username": "disabled", "password": "secret123"}
    ).json()["access_token"]

    resp = client.get(ME_URL, headers=_auth_headers(token))

    assert resp.status_code == 401