import json
from unittest.mock import MagicMock, patch

from django.test import Client, SimpleTestCase
from django.urls import reverse


class HealthCheckViewTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    @patch("backend.views.Role.objects")
    @patch("backend.views.User.objects")
    def test_health_check_reports_connected(self, mock_user_objects, mock_role_objects):
        mock_user_objects.count.return_value = 5
        mock_role_objects.count.return_value = 2

        response = self.client.get(reverse("health"))
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["mongodb"], "connected")
        self.assertEqual(payload["users_count"], 5)
        self.assertEqual(payload["roles_count"], 2)

    @patch("backend.views.Role.objects")
    @patch("backend.views.User.objects")
    def test_health_check_reports_failure(self, mock_user_objects, mock_role_objects):
        mock_user_objects.count.side_effect = RuntimeError("boom")

        response = self.client.get(reverse("health"))
        payload = response.json()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(payload["mongodb"], "disconnected")


class LoginViewTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    @patch("authentication.views.User.objects")
    def test_login_success(self, mock_user_objects):
        user = MagicMock()
        user.userid = 77
        user.username = "swiftuser"
        user.email = "swift@example.com"
        user.roleID = 1
        user.role_name = "customer"
        user.isEnabled = True
        user.check_password.return_value = True

        mock_query = MagicMock()
        mock_query.first.return_value = user
        mock_user_objects.return_value = mock_query

        body = {"identifier": "swiftuser", "password": "Secret123"}
        response = self.client.post(
            reverse("auth-login"),
            data=json.dumps(body),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["approved"])
        self.assertEqual(payload["user"]["username"], "swiftuser")

    @patch("authentication.views.User.objects")
    def test_login_invalid_credentials(self, mock_user_objects):
        mock_query = MagicMock()
        mock_query.first.return_value = None
        mock_user_objects.return_value = mock_query

        body = {"identifier": "missing", "password": "bad"}
        response = self.client.post(
            reverse("auth-login"),
            data=json.dumps(body),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)


class CreateAccountViewTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    @patch("authentication.views.Customer.objects")
    @patch("authentication.views.CustomerPlan.objects")
    @patch("authentication.views.User")
    def test_create_account_uses_customer_userid(self, mock_user_cls, mock_plan_objects, mock_customer_objects):
        customer = MagicMock()
        customer.CustomerID = 5001
        customer.UserID = 6001
        customer.Email = "policy@example.com"
        plan = MagicMock()
        plan.CustomerPlanID = 9001
        plan.CustomerID = customer.CustomerID
        mock_customer_query = MagicMock()
        mock_customer_query.first.return_value = customer
        mock_customer_objects.return_value = mock_customer_query
        mock_plan_query = MagicMock()
        mock_plan_query.first.return_value = plan
        mock_plan_objects.return_value = mock_plan_query

        def fake_user_query(**kwargs):
            query = MagicMock()
            query.first.return_value = None
            return query

        mock_user_cls.objects = MagicMock(side_effect=fake_user_query)

        new_user = MagicMock()
        new_user.userid = customer.UserID
        new_user.username = "policyuser"
        new_user.email = customer.Email
        new_user.roleID = 1
        mock_user_cls.return_value = new_user

        body = {
            "email": "policy@example.com",
            "username": "policyuser",
            "customerPlanID": 9001,
            "password": "Secret123!",
        }
        response = self.client.post(
            reverse("auth-create-account"),
            data=json.dumps(body),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["created"])
        self.assertEqual(payload["user"]["userid"], customer.UserID)
        new_user.set_password.assert_called_once_with("Secret123!")
        new_user.save.assert_called_once()

    @patch("authentication.views.CustomerPlan.objects")
    def test_create_account_rejects_missing_plan(self, mock_plan_objects):
        mock_plan_query = MagicMock()
        mock_plan_query.first.return_value = None
        mock_plan_objects.return_value = mock_plan_query

        body = {
            "email": "missing@example.com",
            "username": "nouser",
            "customerPlanID": 1,
            "password": "Secret123!",
        }
        response = self.client.post(
            reverse("auth-create-account"),
            data=json.dumps(body),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
