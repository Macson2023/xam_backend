from fastapi.testclient import TestClient

from tests.conftest import auth_headers, register


def test_search_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/users/search", params={"q": "a"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_search_validates_query(client: TestClient) -> None:
    alice = register(client, username="alice")

    for query in ("", "a" * 33):
        response = client.get(
            "/api/v1/users/search", params={"q": query}, headers=auth_headers(alice)
        )

        assert response.status_code == 422
        assert isinstance(response.json()["detail"], str)


def test_search_validates_limit(client: TestClient) -> None:
    alice = register(client, username="alice")
    register(client, username="bob")

    for limit in (-1, 0, 51):
        response = client.get(
            "/api/v1/users/search",
            params={"q": "bob", "limit": limit},
            headers=auth_headers(alice),
        )

        assert response.status_code == 422

    response = client.get(
        "/api/v1/users/search",
        params={"q": "bob", "limit": 1},
        headers=auth_headers(alice),
    )
    assert response.status_code == 200


def test_search_is_case_insensitive_and_trims_query(client: TestClient) -> None:
    alice = register(client, username="alice")
    register(client, username="bobby")

    response = client.get(
        "/api/v1/users/search", params={"q": "  BOB  "}, headers=auth_headers(alice)
    )

    assert response.status_code == 200
    assert [item["username"] for item in response.json()] == ["bobby"]


def test_search_escapes_sql_wildcards(client: TestClient) -> None:
    alice = register(client, username="alice")
    register(client, username="a_b")
    register(client, username="axb")

    underscore = client.get(
        "/api/v1/users/search", params={"q": "_"}, headers=auth_headers(alice)
    ).json()
    percent = client.get(
        "/api/v1/users/search", params={"q": "%"}, headers=auth_headers(alice)
    ).json()

    assert [item["username"] for item in underscore] == ["a_b"]
    assert percent == []


def test_search_respects_limit_and_orders_by_username(client: TestClient) -> None:
    alice = register(client, username="alice")
    for username in ("bob3", "bob1", "bob2"):
        register(client, username=username)

    response = client.get(
        "/api/v1/users/search",
        params={"q": "bob", "limit": 2},
        headers=auth_headers(alice),
    )

    assert response.status_code == 200
    assert [item["username"] for item in response.json()] == ["bob1", "bob2"]


def test_search_blank_query_returns_empty_list(client: TestClient) -> None:
    alice = register(client, username="alice")
    register(client, username="bob")

    response = client.get("/api/v1/users/search", params={"q": "   "}, headers=auth_headers(alice))

    assert response.status_code == 200
    assert response.json() == []


def test_search_without_matches_returns_empty_list(client: TestClient) -> None:
    alice = register(client, username="alice")

    response = client.get("/api/v1/users/search", params={"q": "zzz"}, headers=auth_headers(alice))

    assert response.status_code == 200
    assert response.json() == []
