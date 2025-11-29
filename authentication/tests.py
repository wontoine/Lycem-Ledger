import os
from decimal import Decimal
from django.test import SimpleTestCase, Client, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import MagicMock, patch


@override_settings(DEBUG=False)
class AddItemWithImagesTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()
        os.environ["UPLOAD_ROOT"] = "./uploads"  # ensure view sees a path

    @patch("authentication.views.Item")
    @patch("authentication.views.CustomerPlan.objects")
    @patch("authentication.views.AddItemWithImagesView._save_file")
    def test_add_item_with_required_images_succeeds(self, mock_save_file, mock_plan_objects, mock_item_cls):
        # Fake plan lookup returns a policy with matching CustomerID
        policy = MagicMock()
        policy.CustomerID = 10
        mock_plan_objects.__raw__.return_value.first.return_value = policy
        mock_plan_objects.return_value.first.return_value = policy

        # Fake next ItemID
        mock_item = MagicMock()
        mock_item.ItemID = 99
        mock_item_cls.objects.order_by.return_value.first.return_value = mock_item
        mock_item_cls.return_value = mock_item

        # Pretend saved file paths
        mock_save_file.side_effect = ["path/to/img1.jpg", "path/to/img2.jpg"]

        img_bytes = b"\x89PNG\r\n\x1a\n"
        image1 = SimpleUploadedFile("img1.png", img_bytes, content_type="image/png")
        image2 = SimpleUploadedFile("img2.png", img_bytes, content_type="image/png")

        resp = self.client.post(
            "/api/auth/items/add/",
            data={
                "name": "Laptop",
                "estimatedValue": "1200",
                "customerPlanID": "1",
                "customerID": "10",
                "image1": image1,
                "image2": image2,
            },
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["name"], "Laptop")
        self.assertEqual(body["customerID"], 10)
        self.assertIsNotNone(body["imagePath1"])
        self.assertIsNotNone(body["imagePath2"])

    def test_add_item_without_images_returns_400(self):
        resp = self.client.post(
            "/api/auth/items/add/",
            data={
                "name": "Laptop",
                "estimatedValue": "1200",
                "customerPlanID": "1",
                "customerID": "10",
            },
        )
        self.assertEqual(resp.status_code, 400)


@override_settings(DEBUG=False)
class SubmitClaimViewTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    @patch("authentication.views.ClaimWorkflowHistory")
    @patch("authentication.views.Agent.objects")
    @patch("authentication.views.ClaimRecord")
    @patch("authentication.views.Item.objects")
    @patch("authentication.views.CustomerPlan.objects")
    @patch("authentication.views.Customer.objects")
    def test_submit_claim_happy_path(self, mock_cust, mock_plan, mock_item, mock_claim, mock_agent, mock_hist):
        # Customer resolved by userID
        customer = MagicMock()
        customer.CustomerID = 1
        customer.assignment = 1
        mock_cust.return_value.first.return_value = customer

        # Policy belongs to customer
        policy = MagicMock()
        policy.CustomerID = 1
        mock_plan.return_value.first.return_value = policy
        mock_plan.__raw__.return_value.first.return_value = policy

        # Item belongs to customer
        item_obj = MagicMock()
        item_obj.CustomerID = 1
        mock_item.return_value.first.return_value = item_obj
        mock_item.__raw__.return_value.first.return_value = item_obj

        # No open claim
        mock_claim.objects.__raw__.return_value.first.return_value = None
        # Next ClaimID
        mock_claim.objects.order_by.return_value.first.return_value = MagicMock(ClaimID=5)

        resp = self.client.post(
            "/api/auth/claims/submit/",
            data={
                "userID": 1,
                "policyID": 1,
                "itemID": 1,
                "amount": "500.00",
                "reason": "Broken screen",
            },
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        payload = resp.json()
        self.assertEqual(payload["status"], "Filed")
        self.assertEqual(payload["itemID"], 1)

    def test_submit_claim_missing_field(self):
        resp = self.client.post(
            "/api/auth/claims/submit/",
            data={"userID": 1},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)


@override_settings(DEBUG=False)
class PolicyDetailViewTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()

    @patch("authentication.views.Item.objects")
    @patch("authentication.views.InsurancePlan.objects")
    @patch("authentication.views.CustomerPlan.objects")
    def test_policy_detail_returns_items(self, mock_plan, mock_ins, mock_items):
        # Policy
        policy = MagicMock()
        policy.CustomerPlanID = 1
        policy.CustomerID = 1
        policy.planID = 2
        policy.Status = "Active"
        mock_plan.__raw__.return_value.first.return_value = policy

        # Insurance plan
        ins = MagicMock()
        ins.PlanName = "Basic Home"
        ins.Description = "desc"
        ins.CoverageLim = 100000
        ins.BasePrice = 500
        mock_ins.__raw__.return_value.first.return_value = ins

        # Items
        item = MagicMock()
        item.ItemID = 1
        item.Name = "Laptop"
        mock_items.__raw__.return_value = [item]

        resp = self.client.get("/api/auth/policies/1/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["policy"]["planName"], "Basic Home")
        self.assertEqual(body["count"], 1)

    @patch("authentication.views.CustomerPlan.objects")
    def test_policy_detail_not_found(self, mock_plan):
        mock_plan.__raw__.return_value.first.return_value = None
        resp = self.client.get("/api/auth/policies/999/")
        self.assertEqual(resp.status_code, 404)
