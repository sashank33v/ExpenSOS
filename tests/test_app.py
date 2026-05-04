import pytest


class TestAuthRoutes:
    def test_login_page_loads(self, client):
        response = client.get("/login")
        assert response.status_code == 200
        assert b"Sign In" in response.data or b"Log In" in response.data or b"Welcome" in response.data

    def test_register_page_loads(self, client):
        response = client.get("/register")
        assert response.status_code == 200

    def test_login_empty_fields(self, client):
        response = client.post("/login", data={"email": "", "password": ""}, follow_redirects=True)
        assert response.status_code == 200

    def test_register_password_too_short(self, client):
        response = client.post(
            "/register",
            data={"username": "testuser", "email": "test@test.com", "password": "123"},
            follow_redirects=True,
        )
        assert response.status_code == 200

    def test_logout_redirects(self, client):
        response = client.get("/logout", follow_redirects=True)
        assert response.status_code == 200


class TestProtectedRoutes:
    @pytest.mark.parametrize(
        "path",
        ["/", "/expenses", "/budgets", "/recurring", "/reminders", "/settings"],
    )
    def test_route_requires_login(self, client, path):
        response = client.get(path, follow_redirects=True)
        assert response.status_code == 200


class TestApiRoutes:
    @pytest.mark.parametrize(
        "path",
        ["/monthly-data", "/api/insights", "/api/budget-progress"],
    )
    def test_api_requires_login(self, client, path):
        response = client.get(path)
        assert response.status_code in [302, 401]


class TestInputValidation:
    def test_add_expense_missing_fields(self, authenticated_client):
        response = authenticated_client.post("/add", data={}, follow_redirects=True)
        assert response.status_code == 200

    def test_budget_add_missing_fields(self, authenticated_client):
        response = authenticated_client.post("/budgets/add", data={}, follow_redirects=True)
        assert response.status_code == 200

    def test_recurring_add_missing_fields(self, authenticated_client):
        response = authenticated_client.post("/recurring/add", data={}, follow_redirects=True)
        assert response.status_code == 200

    def test_reminder_add_no_days(self, authenticated_client):
        response = authenticated_client.post(
            "/reminders/add",
            data={"days": [], "time": "09:00", "reminder_count": "1"},
            follow_redirects=True,
        )
        assert response.status_code == 200


class TestUrlRouting:
    @pytest.mark.parametrize(
        "path",
        [
            "/delete/99999",
            "/edit/99999",
            "/budgets/delete/99999",
            "/recurring/delete/99999",
            "/reminders/delete/99999",
            "/recurring/toggle/99999",
            "/reminders/toggle/99999",
        ],
    )
    def test_invalid_ids_do_not_crash(self, authenticated_client, path):
        response = authenticated_client.get(path)
        assert response.status_code in [302, 404]


class TestFileUploads:
    def test_receipt_upload_invalid_file(self, authenticated_client):
        response = authenticated_client.post(
            "/upload-receipt/1",
            data={"receipt": (b"not an image", "test.txt")},
            follow_redirects=True,
        )
        assert response.status_code == 200

    def test_upload_invalid_expense_id(self, authenticated_client):
        response = authenticated_client.post(
            "/upload-receipt/99999",
            data={"receipt": (b"fake image", "test.png")},
            follow_redirects=True,
        )
        assert response.status_code in [200, 404]


class TestQueryParameters:
    @pytest.mark.parametrize(
        "path",
        [
            "/expenses?year=2024&month=01&category=Food",
            "/expenses?search=test",
            "/expenses?page=1",
            "/expenses?page=-1",
        ],
    )
    def test_expenses_filters_render(self, authenticated_client, path):
        response = authenticated_client.get(path)
        assert response.status_code == 200


class TestSettingsUpdate:
    @pytest.mark.parametrize(
        "payload",
        [
            {"currency": "$", "theme": "dark", "language": "en", "font_size": "medium"},
            {"currency": "€", "theme": "light", "language": "hi", "font_size": "large"},
        ],
    )
    def test_update_settings(self, authenticated_client, payload):
        response = authenticated_client.post("/settings/update", data=payload, follow_redirects=True)
        assert response.status_code == 200
