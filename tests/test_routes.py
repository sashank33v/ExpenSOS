import pytest


@pytest.mark.parametrize("path", ["/login", "/register"])
def test_public_routes(client, path):
    response = client.get(path)
    assert response.status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/expenses",
        "/budgets",
        "/recurring",
        "/reminders",
        "/settings",
        "/monthly-data",
        "/api/insights",
        "/api/budget-progress",
    ],
)
def test_authenticated_routes(client, path):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "testuser"

    response = client.get(path)
    assert response.status_code == 200
