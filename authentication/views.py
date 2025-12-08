from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ParseError
from rest_framework.parsers import MultiPartParser, FormParser
from django.conf import settings
from django.core.mail import send_mail
import json
from urllib.parse import parse_qs
import os
import re
import uuid
from pathlib import Path

from users.models import User, Role, Customer, CustomerPlan, InsurancePlan, Item, ClaimRecord, Agent, \
    ClaimWorkflowHistory
from django.utils import timezone
from decimal import Decimal
from datetime import datetime
from .serializers import (
    LoginSerializer,
    CreateAccountSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
)


def _classify_account(email) -> str:
    """Helper to classify account type based on email domain."""
    try:
        domain = settings.COMPANY_EMAIL_DOMAIN.lower()
        if isinstance(email, str) and "@" in email and email.lower().endswith(f"@{domain}"):
            return "employee"
        if isinstance(email, str) and "@" in email:
            return "customer"
        return "unknown"
    except Exception:
        return "unknown"


def _role_name_for(role_id: int) -> str:
    """Helper to resolve role ID to role name."""
    try:
        role = Role.objects(roleID=role_id).first()
        return role.RoleName if role else "unknown"
    except Exception:
        return "unknown"


def _default_customer_role_id() -> int:
    """Resolve the default role ID for new customers."""
    try:
        role = Role.objects(RoleName__iexact="customer").first()
        if role:
            return role.roleID
    except Exception:
        pass
    try:
        fallback = Role.objects(roleID=1).first()
        if fallback:
            return fallback.roleID
    except Exception:
        pass
    return 1


class LoginView(APIView):
    """
    Explanation: Authenticates a user using username (or email) and password.
    Expected Input: JSON Body { "username": str, "password": str } (or "email").
    Expected Output: JSON object with user details and approval status.
    """

    def get(self, request):
        return Response(
            {
                "endpoint": "/api/auth/login/",
                "methods": ["POST"],
                "usage": "POST JSON with 'username' and 'password'.",
                "required": ["password"],
                "identifiers": ["username", "email"],
                "examples": {
                    "username_login": {"username": "john.doe", "password": "YourPassword"},
                    "email_login": {"email": "customer@example.com", "password": "YourPassword"}
                },
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        try:
            data = request.data if isinstance(request.data, dict) else {}
        except ParseError:
            data = {}

        username = data.get("username")
        email = data.get("email")
        password = data.get("password")

        if not password or not (username or email):
            return Response(
                {"approved": False, "error": {"detail": "Provide 'password' and either 'username' or 'email'"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = None
            if username:
                user = User.objects(username=username).first()

            if not user and username:
                try:
                    cust = Customer.objects(
                        __raw__={"Email": {"$regex": f"^{username}$", "$options": "i"}}
                    ).first()
                except Exception:
                    cust = None
                if cust:
                    user = User.objects(userid=getattr(cust, "UserID", None)).first()

            if not user and email:
                try:
                    cust = Customer.objects(
                        __raw__={"Email": {"$regex": f"^{email}$", "$options": "i"}}
                    ).first()
                except Exception:
                    cust = None
                if cust:
                    user = User.objects(userid=getattr(cust, "UserID", None)).first()
        except Exception as e:
            return Response({"approved": False, "error": "Database connection error"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not user:
            return Response({"approved": False, "error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.isEnabled:
            return Response({"approved": False, "error": "Account is disabled"}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.check_password(password):
            return Response({"approved": False, "error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

        role_name = user.role_name or _role_name_for(user.roleID)
        cust_email = None
        try:
            cust = Customer.objects(UserID=user.userid).first()
            if cust:
                cust_email = getattr(cust, "Email", None)
        except Exception:
            cust_email = None
        account_type = _classify_account(cust_email)
        is_admin = (role_name.lower() == "admin")

        return Response(
            {
                "approved": True,
                "user": {
                    "userid": user.userid,
                    "username": user.username,
                    "email": cust_email,
                    "roleID": getattr(user, 'roleID', None),
                    "role": role_name,
                    "isEnabled": user.isEnabled,
                    "accountType": account_type,
                    "isAdmin": is_admin,
                },
            },
            status=status.HTTP_200_OK,
        )


class CreateAccountView(APIView):
    """
    Explanation: Registers a new user account linked to an existing Customer Plan.
    Expected Input: JSON Body { "email": str, "username": str, "customerPlanID": int, "password": str }.
    Expected Output: JSON object with created user details.
    """

    def get(self, request):
        return Response(
            {
                "endpoint": "/api/auth/create-account/",
                "methods": ["POST"],
                "usage": "POST JSON with 'email', 'username', 'customerPlanID', and 'password'.",
                "required": ["email", "username", "customerPlanID", "password"],
                "example": {"email": "customer@example.com", "username": "newuser", "customerPlanID": 123,
                            "password": "ChooseAStrongPassword"},
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = CreateAccountSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"created": False, "error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        raw_email = serializer.validated_data["email"]
        email = (raw_email or "").strip()
        email_lower = email.lower()
        username = serializer.validated_data["username"].strip()
        plan_id = int(serializer.validated_data["customerPlanID"])
        password = serializer.validated_data["password"]

        try:
            plan = CustomerPlan.objects(CustomerPlanID=plan_id).first()
            if not plan:
                plan = CustomerPlan.objects(__raw__={
                    "$or": [
                        {"CustomerPlanID": plan_id},
                        {"CustomerPlanID": str(plan_id)},
                        {"customerPlanID": plan_id},
                        {"customerPlanID": str(plan_id)},
                    ]
                }).first()
        except Exception as e:
            print(f"CreateAccountView: error fetching customer plan: {e}")
            msg = "Database connection error"
            if settings.DEBUG:
                msg = f"Database error: {e}"
            return Response({"created": False, "error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not plan:
            return Response(
                {"created": False, "error": "Customer plan not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            customer = Customer.objects(CustomerID=plan.CustomerID).first()
        except Exception as e:
            print(f"CreateAccountView: error fetching customer: {e}")
            msg = "Database connection error"
            if settings.DEBUG:
                msg = f"Database error: {e}"
            return Response({"created": False, "error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not customer:
            return Response(
                {"created": False, "error": "Customer not found for plan"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            cust_email = (getattr(customer, "Email", None) or "").strip()
            if cust_email.lower() != email_lower:
                return Response(
                    {"created": False, "error": "Email does not match our records"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        except Exception as e:
            print(f"CreateAccountView: error validating customer email: {e}")
            return Response({"created": False, "error": "Database connection error"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not isinstance(getattr(customer, "UserID", None), int):
            return Response(
                {"created": False, "error": "Customer record is missing a userID"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if User.objects(userid=customer.UserID).first():
                return Response(
                    {"created": False, "error": "An account already exists for this policy"},
                    status=status.HTTP_409_CONFLICT,
                )
            if User.objects(username=username).first():
                return Response(
                    {"created": False, "error": "Username already exists"},
                    status=status.HTTP_409_CONFLICT,
                )

            new_user = User(
                userid=customer.UserID,
                username=username,
                roleID=_default_customer_role_id(),
                isEnabled=True,
            )
            new_user.set_password(password)
            new_user.save()
        except Exception as e:
            print(f"CreateAccountView: error creating user: {e}")
            msg = "Unable to create account"
            if settings.DEBUG:
                msg = f"Create failed: {e}"
            return Response({"created": False, "error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(
            {
                "created": True,
                "user": {
                    "userid": new_user.userid,
                    "username": new_user.username,
                    "email": getattr(customer, "Email", None),
                    "roleID": new_user.roleID,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class ForgotPasswordView(APIView):
    """
    Explanation: Initiates password reset process. Sends token via email if user exists.
    Expected Input: JSON Body { "identifier" | "email" | "username" }.
    Expected Output: JSON message (Always 200 OK for security).
    """

    def _extract_identifier(self, request) -> str | None:
        try:
            data = request.data
            if isinstance(data, dict):
                ident = data.get("identifier") or data.get("email") or data.get("username")
                if ident:
                    return ident
        except ParseError:
            pass

        try:
            raw = request.body or b""
            if not raw:
                raw = getattr(request, "_request", None)
                raw = getattr(raw, "body", b"") if raw is not None else b""
            if isinstance(raw, bytes):
                raw_text = raw.decode("utf-8", errors="ignore").strip()
            else:
                raw_text = str(raw).strip()

            if raw_text.startswith("{") and raw_text.endswith("}"):
                try:
                    obj = json.loads(raw_text)
                    if isinstance(obj, dict):
                        ident = obj.get("identifier") or obj.get("email") or obj.get("username")
                        if ident:
                            return ident
                except Exception:
                    pass

            if "=" in raw_text and "&" in raw_text or raw_text.startswith("identifier=") or raw_text.startswith(
                    "email=") or raw_text.startswith("username="):
                try:
                    q = parse_qs(raw_text, keep_blank_values=True)
                    for key in ("identifier", "email", "username"):
                        vals = q.get(key)
                        if vals and vals[0]:
                            return vals[0]
                except Exception:
                    pass

            if raw_text:
                return raw_text
        except Exception:
            pass

        try:
            qp = request.query_params
            ident = qp.get("identifier") or qp.get("email") or qp.get("username")
            if ident:
                return ident
        except Exception:
            pass

        return None

    def get(self, request):
        return Response(
            {
                "endpoint": "/api/auth/forgot-password/",
                "methods": ["POST"],
                "usage": "POST JSON with one of 'identifier', 'email', or 'username'.",
                "identifiers": ["identifier", "email", "username"],
                "example": {"identifier": "john.doe"},
                "note": "For development, the reset token and link are printed to the server console.",
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        payload = {}
        ident = self._extract_identifier(request)
        if ident:
            payload = {"identifier": ident}
        else:
            return Response({"message": "If an account exists, an email has been sent."}, status=status.HTTP_200_OK)

        serializer = ForgotPasswordSerializer(data=payload)
        if not serializer.is_valid():
            return Response({"message": "If an account exists, an email has been sent."}, status=status.HTTP_200_OK)

        ident = serializer.validated_data["identifier"]
        try:
            user = None
            customer = None
            if isinstance(ident, str) and "@" in ident:
                customer = Customer.objects(__raw__={"email": {"$regex": f"^{ident}$", "$options": "i"}}).first()
                if customer:
                    user = User.objects(userid=getattr(customer, "UserID", None)).first()
            if not user:
                user = User.objects(username=ident).first()
                if user:
                    try:
                        customer = Customer.objects(UserID=user.userid).first()
                    except Exception:
                        customer = None
        except Exception:
            return Response({"message": "If an account exists, an email has been sent."}, status=status.HTTP_200_OK)

        if user:
            try:
                token = user.issue_reset_token(ttl_minutes=60)
            except Exception:
                token = None

            try:
                link = None
                base = getattr(settings, "PASSWORD_RESET_BASE_URL", "") or ""
                if token:
                    if base:
                        base = str(base).strip()
                        if "{token}" in base:
                            link = base.format(token=token)
                        else:
                            if "?" in base:
                                sep = "&" if not base.endswith(("&", "?")) else ""
                                link = f"{base}{sep}token={token}"
                            else:
                                base_norm = base.rstrip("/")
                                link = f"{base_norm}?token={token}"
                    else:
                        try:
                            reset_url = request.build_absolute_uri("/api/auth/reset-password/")
                        except Exception:
                            reset_url = "/api/auth/reset-password/"
                        if "?" in reset_url:
                            link = f"{reset_url}&token={token}"
                        else:
                            link = f"{reset_url}?token={token}"
            except Exception:
                link = None

            if token:
                try:
                    uname = getattr(user, "username", "<unknown>")
                    uid = getattr(user, "userid", "<unknown>")
                    print("[ForgotPassword] Issued reset token:")
                    print(f"  user: {uname} (userid: {uid})")
                    print(f"  token: {token}")
                    if link:
                        print(f"  link:  {link}")
                    else:
                        print("  link:  <Could not build reset link>")
                except Exception:
                    pass

            if customer and getattr(customer, "Email", None) and token:
                try:
                    subject = "Password reset request"
                    if link:
                        message = (
                            "We received a request to reset your password.\n\n"
                            f"Reset link: {link}\n\n"
                            "If you did not request this, you can ignore this email."
                        )
                    else:
                        message = (
                            "We received a request to reset your password.\n\n"
                            f"Your reset token is: {token}\n\n"
                            "Use this token in the app to set a new password. If you did not request this, ignore this email."
                        )

                    send_mail(
                        subject,
                        message,
                        getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(settings, "EMAIL_HOST_USER",
                                                                                 None) or "no-reply@localhost",
                        [getattr(customer, "Email")],
                        fail_silently=True,
                    )
                except Exception:
                    pass

        return Response({"message": "If an account exists, an email has been sent."}, status=status.HTTP_200_OK)


class CustomerPlansView(APIView):
    """
    Explanation: Returns all plans for a specific customer.
    Expected Input: URL Query param 'userID'.
    Expected Output: JSON object containing list of plans.
    """

    def get(self, request):
        user_id_raw = request.query_params.get("userID")
        if not user_id_raw:
            return Response({"error": "userID is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user_id = int(user_id_raw)
        except ValueError:
            return Response({"error": "userID must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            customer = Customer.objects(UserID=user_id).first()
        except Exception as e:
            msg = "Database connection error"
            if settings.DEBUG:
                msg = f"Database error: {e}"
            return Response({"error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not customer:
            return Response({"error": "Customer not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            plans = CustomerPlan.objects(CustomerID=customer.CustomerID)
        except Exception as e:
            msg = "Database connection error"
            if settings.DEBUG:
                msg = f"Database error: {e}"
            return Response({"error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        def _get(plan, *keys):
            for k in keys:
                val = getattr(plan, k, None)
                if val is not None:
                    return val
                if hasattr(plan, "_data") and k in plan._data:
                    val = plan._data.get(k)
                    if val is not None:
                        return val
            return None

        def _plan_to_dict(plan):
            start_dt = _get(plan, "StartDate", "startDate")
            end_dt = _get(plan, "EndDate", "endDate")
            return {
                "customerPlanID": _get(plan, "CustomerPlanID", "customerPlanID"),
                "customerID": _get(plan, "CustomerID", "customerID"),
                "startDate": start_dt.isoformat() if hasattr(start_dt, "isoformat") else start_dt,
                "endDate": end_dt.isoformat() if hasattr(end_dt, "isoformat") else end_dt,
                "currentPremium": _get(plan, "CurrentPremium", "currentPremium"),
                "status": _get(plan, "Status", "status"),
                "planID": _get(plan, "planID", "PlanID"),
            }

        plans_list = [_plan_to_dict(p) for p in plans]

        plan_ids = {p.get("planID") for p in plans_list if p.get("planID") is not None}
        plan_names = {}
        if plan_ids:
            try:
                plan_docs = InsurancePlan.objects(__raw__={"planID": {"$in": list(plan_ids)}})
                for doc in plan_docs:
                    pid = _get(doc, "planID", "PlanID")
                    pname = _get(doc, "PlanName", "plan_name")
                    if pid is not None:
                        plan_names[pid] = pname
            except Exception:
                pass
        for p in plans_list:
            pid = p.get("planID")
            if pid in plan_names:
                p["planName"] = plan_names[pid]

        return Response(
            {
                "userID": user_id,
                "customerID": getattr(customer, "CustomerID", None),
                "count": len(plans_list),
                "plans": plans_list,
            },
            status=status.HTTP_200_OK,
        )


class SubmitClaimView(APIView):
    """
    Explanation: Creates a new claim submission for a policy or item.
    Expected Input: JSON Body { "userID", "policyID", "amount", "reason", "itemID" (optional) }.
    Expected Output: JSON object with created claim details.
    """

    def _validate_client_path(self, path_value):
        if not path_value or not isinstance(path_value, str):
            return None
        path_value = path_value.strip()
        if path_value.startswith(("/", "\\")) or ".." in path_value:
            return None
        return path_value or None

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}

        headers = getattr(request, "headers", {}) or {}
        meta = getattr(request, "META", {}) or {}

        def _get_first(dct, keys, default=None):
            for k in keys:
                if k in dct and dct[k] not in (None, ""):
                    return dct[k]
            return default

        raw_user = _get_first(
            data,
            ["userID", "userid", "UserID", "customer_id", "customerID"],
        )
        if raw_user in (None, ""):
            raw_user = (
                    headers.get("x-user-id")
                    or headers.get("X-User-ID")
                    or headers.get("userid")
                    or headers.get("UserID")
                    or meta.get("HTTP_X_USER_ID")
                    or meta.get("HTTP_USERID")
            )

        raw_policy = _get_first(
            data,
            [
                "policyID",
                "policyId",
                "policy_id",
                "customerPlanID",
                "customerPlanId",
                "planID",
                "planId",
            ],
        )
        raw_item = _get_first(data, ["itemID", "itemId", "ItemID"])
        raw_amount = _get_first(data, ["amount", "Amount", "claimAmount", "ClaimAmount"])
        raw_reason = _get_first(data, ["reason", "Reason", "description", "claimReason", "notes"]) or ""
        loss_date = _get_first(data, ["lossDate", "loss_date", "LossDate"])

        missing = []
        if raw_user in (None, ""): missing.append("userID")
        if raw_policy in (None, ""): missing.append("policyID")
        if raw_amount in (None, ""): missing.append("amount")
        if raw_reason in (None, ""): missing.append("reason")
        if missing:
            return Response(
                {
                    "error": {
                        "detail": "Missing required fields.",
                        "missing": missing,
                        "acceptedKeys": {
                            "userID": ["userID", "userid", "UserID", "x-user-id (header)"],
                            "policyID": ["policyID", "policyId", "customerPlanID", "customerPlanId", "planID",
                                         "planId"],
                            "itemID": ["itemID", "itemId"],
                            "amount": ["amount", "Amount", "claimAmount", "ClaimAmount"],
                            "reason": ["reason", "Reason", "description", "claimReason", "notes"],
                        },
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user_id = int(str(raw_user).strip())
            policy_id = int(str(raw_policy).strip())
        except (ValueError, TypeError):
            return Response({"error": "userID and policyID must be integers"}, status=status.HTTP_400_BAD_REQUEST)

        item_id = None
        if raw_item not in (None, ""):
            try:
                item_id = int(str(raw_item).strip())
            except (ValueError, TypeError):
                return Response({"error": "itemID must be an integer when provided"},
                                status=status.HTTP_400_BAD_REQUEST)

        from decimal import Decimal as _Dec
        try:
            amt_str = str(raw_amount).strip()
            amt_clean = amt_str.replace("$", "").replace(",", "")
            amount = _Dec(amt_clean)
        except Exception:
            return Response({"error": "amount must be numeric"}, status=status.HTTP_400_BAD_REQUEST)

        reason = str(raw_reason).strip()

        try:
            customer = Customer.objects(UserID=user_id).first()
        except Exception as e:
            msg = "Database connection error"
            if settings.DEBUG:
                msg = f"Database error: {e}"
            return Response({"error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not customer:
            return Response({"error": "Customer not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            policy = CustomerPlan.objects(CustomerID=customer.CustomerID, CustomerPlanID=policy_id).first()
            if not policy:
                policy = CustomerPlan.objects(__raw__={
                    "CustomerID": customer.CustomerID,
                    "$or": [
                        {"CustomerPlanID": policy_id},
                        {"customerPlanID": policy_id},
                        {"planID": policy_id},
                    ]
                }).first()
        except Exception as e:
            msg = "Database connection error"
            if settings.DEBUG:
                msg = f"Database error: {e}"
            return Response({"error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not policy:
            return Response({"error": "Policy not found for this customer"}, status=status.HTTP_404_NOT_FOUND)

        item = None
        if item_id is not None:
            try:
                item = Item.objects(ItemID=item_id, CustomerID=customer.CustomerID).first()
                if not item:
                    item = Item.objects(__raw__={"ItemID": item_id, "CustomerID": customer.CustomerID}).first()
            except Exception as e:
                msg = "Database connection error"
                if settings.DEBUG:
                    msg = f"Database error: {e}"
                return Response({"error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            if not item:
                return Response({"error": "Item not found for this customer"}, status=status.HTTP_404_NOT_FOUND)

        if item_id is not None:
            try:
                open_claim = ClaimRecord.objects(__raw__={
                    "ItemID": item_id,
                    "CurrentStatusID": {"$in": [1, 2]}
                }).first()
            except Exception:
                open_claim = None

            if open_claim:
                return Response({"error": "An open claim already exists for this item"},
                                status=status.HTTP_409_CONFLICT)

        try:
            last = ClaimRecord.objects.order_by("-ClaimID").first()
            next_id = (last.ClaimID + 1) if last and getattr(last, "ClaimID", None) else 1
        except Exception:
            next_id = 1

        now = timezone.now()
        loss_dt = None
        if loss_date:
            try:
                loss_dt = datetime.fromisoformat(loss_date)
            except Exception:
                loss_dt = None

        try:
            claim = ClaimRecord(
                ClaimID=next_id,
                ItemID=item_id if item_id is not None else None,
                CurrentStatusID=1,
                LossDate=loss_dt,
                ClaimedValueAtTime=str(amount),
                descriptionOfLoss=reason,
                DateFiled=now,
            )
            claim.save()
        except Exception as e:
            msg = "Unable to create claim"
            if settings.DEBUG:
                msg = f"Create failed: {e}"
            return Response({"error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if item is not None:
            try:
                setattr(item, "ClaimStatus", "In Progress")
                item.save()
            except Exception:
                pass

        try:
            agent_name = None
            agent_id = getattr(customer, "assignment", None) or getattr(customer, "Assignment", None)
            if agent_id is not None:
                ag = Agent.objects(__raw__={"$or": [{"agentID": agent_id}, {"AgentID": agent_id}]}).first()
                if ag:
                    fn = getattr(ag, "firstname", None) or getattr(ag, "firstName", None)
                    ln = getattr(ag, "lastName", None) or getattr(ag, "lastname", None)
                    agent_name = " ".join(filter(None, [fn, ln])) or getattr(ag, "email", None)
            try:
                last_hist = ClaimWorkflowHistory.objects.order_by("-HistoryID").first()
                next_hist = (last_hist.HistoryID + 1) if last_hist and getattr(last_hist, "HistoryID", None) else 1
            except Exception:
                next_hist = 1
            hist = ClaimWorkflowHistory(
                HistoryID=next_hist,
                ClaimID=claim.ClaimID,
                status="Filed",
                EmployeeName=agent_name or "customer",
                Timestamp=now,
                Note="Initial claim submission by customer.",
            )
            hist.save()
        except Exception:
            pass

        return Response(
            {
                "claimID": claim.ClaimID,
                "status": "Filed",
                "itemID": item_id,
                "policyID": policy_id,
                "customerID": getattr(customer, "CustomerID", None),
                "amount": str(amount),
                "reason": reason,
                "lossDate": loss_dt.isoformat() if loss_dt else None,
                "dateFiled": now.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )


class AddItemWithImagesView(APIView):
    """
    Explanation: Creates an Item under a specific policy, optionally handling up to 2 image uploads.
    Expected Input: Multipart/Form Data { "name", "estimatedValue", "customerPlanID", "customerID", "image1", "image2", ... }.
    Expected Output: JSON object with created item details.
    """

    parser_classes = [MultiPartParser, FormParser]
    MAX_SIZE = 10 * 1024 * 1024  # 10 MB
    ALLOWED_EXT = {".jpg", ".jpeg", ".png"}

    def _slug(self, text):
        text = text.strip().lower()
        text = re.sub(r"[^a-z0-9-_]+", "-", text)
        return text or "file"

    def _save_file(self, file_obj, customer_id, plan_id, item_name_slug, idx):
        """
        Save an uploaded file to a safe location.

        We attempt several fallbacks for the root upload directory to avoid 500s
        when a specific setting isn't provided in the environment:
        1) ENV var UPLOAD_ROOT
        2) settings.UPLOAD_ROOT
        3) settings.MEDIA_ROOT (if set and non-empty)
        4) <BASE_DIR>/uploads (created on demand)
        """
        upload_root = (
            os.environ.get("UPLOAD_ROOT")
            or getattr(settings, "UPLOAD_ROOT", None)
            or getattr(settings, "MEDIA_ROOT", None)
        )
        # If MEDIA_ROOT is empty string or None, fall back to BASE_DIR/uploads
        if not upload_root:
            base_dir = getattr(settings, "BASE_DIR", Path.cwd())
            upload_root = os.path.join(str(base_dir), "uploads")

        # Ensure the root exists (avoid failing later with obscure errors)
        os.makedirs(upload_root, exist_ok=True)

        if hasattr(file_obj, "size") and file_obj.size > self.MAX_SIZE:
            raise ValueError("File too large")

        ext = Path(file_obj.name).suffix.lower()
        if ext not in self.ALLOWED_EXT:
            raise ValueError("Unsupported file type")

        safe_base = self._slug(item_name_slug)
        filename = f"{safe_base}_img{idx}{ext}"

        item_folder = os.path.join(
            upload_root,
            "customers",
            str(customer_id),
            "plans",
            str(plan_id),
            "items",
            safe_base,
        )
        os.makedirs(item_folder, exist_ok=True)
        abs_path = os.path.join(item_folder, filename)
        rel_path = os.path.relpath(abs_path, upload_root)

        with open(abs_path, "wb") as out:
            for chunk in file_obj.chunks():
                out.write(chunk)

        return rel_path

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}

        for field in ["name", "estimatedValue", "customerPlanID", "customerID"]:
            if field not in data or data[field] in (None, ""):
                return Response({"error": {field: "This field is required"}}, status=status.HTTP_400_BAD_REQUEST)

        name = str(data.get("name")).strip()
        description = str(data.get("description", "")).strip() if data.get("description") else None
        category = str(data.get("Category", "")).strip() if data.get("Category") else None
        try:
            plan_id = int(data.get("customerPlanID"))
        except Exception:
            return Response({"error": {"customerPlanID": "Must be an integer"}}, status=status.HTTP_400_BAD_REQUEST)
        try:
            customer_id = int(data.get("customerID"))
        except Exception:
            return Response({"error": {"customerID": "Must be an integer"}}, status=status.HTTP_400_BAD_REQUEST)

        try:
            estimated_value = Decimal(str(data.get("estimatedValue")))
        except Exception:
            return Response({"error": {"estimatedValue": "Must be numeric"}}, status=status.HTTP_400_BAD_REQUEST)

        purchase_date_raw = data.get("purchaseDate")
        purchase_date = None
        if purchase_date_raw:
            try:
                purchase_date = datetime.fromisoformat(purchase_date_raw)
            except Exception:
                return Response({"error": {"purchaseDate": "Invalid date format"}}, status=status.HTTP_400_BAD_REQUEST)
        purchase_date_str = purchase_date.isoformat() if purchase_date else None

        try:
            policy = CustomerPlan.objects(__raw__={
                "$or": [
                    {"CustomerPlanID": plan_id},
                    {"customerPlanID": plan_id},
                    {"planID": plan_id},
                ]
            }).first()
        except Exception as e:
            msg = "Database connection error"
            if settings.DEBUG:
                msg = f"Database error: {e}"
            return Response({"error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not policy:
            return Response({"error": "customerPlanID not found"}, status=status.HTTP_404_NOT_FOUND)
        if getattr(policy, "CustomerID", None) != customer_id:
            return Response({"error": "customerID does not match plan ownership"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            last = Item.objects.order_by("-ItemID").first()
            next_id = (last.ItemID + 1) if last and getattr(last, "ItemID", None) else 1
        except Exception:
            next_id = 1

        image_paths = []
        for idx, field in enumerate(["image1", "image2"], start=1):
            file_obj = request.FILES.get(field)
            if file_obj:
                try:
                    rel = self._save_file(file_obj, customer_id, plan_id, self._slug(name), idx)
                    image_paths.append(rel)
                except ValueError as ve:
                    return Response({"error": {field: str(ve)}}, status=status.HTTP_400_BAD_REQUEST)
                except Exception as e:
                    msg = "File upload failed"
                    if settings.DEBUG:
                        msg = f"Upload error: {e}"
                    return Response({"error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                client_path = self._validate_client_path(data.get(f"imagePath{idx}"))
                if not client_path:
                    return Response({"error": {field: "Image is required"}}, status=status.HTTP_400_BAD_REQUEST)
                image_paths.append(client_path)

        try:
            item = Item(
                ItemID=next_id,
                Name=name,
                Description=description,
                CustomerID=customer_id,
                CustomerPlanID=plan_id,
                Category=category,
                EstimatedValue=str(estimated_value),
                PurchaseDate=purchase_date_str,
            )
            if image_paths:
                if len(image_paths) > 0:
                    setattr(item, "ImagePath1", image_paths[0])
                if len(image_paths) > 1:
                    setattr(item, "ImagePath2", image_paths[1])
            item.save()
        except Exception as e:
            msg = "Unable to create item"
            if settings.DEBUG:
                msg = f"Create failed: {e}"
            return Response({"error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(
            {
                "itemID": item.ItemID,
                "name": name,
                "description": description,
                "category": category,
                "customerPlanID": plan_id,
                "customerID": customer_id,
                "estimatedValue": str(estimated_value),
                "purchaseDate": purchase_date_str,
                "imagePath1": getattr(item, "ImagePath1", None),
                "imagePath2": getattr(item, "ImagePath2", None),
            },
            status=status.HTTP_201_CREATED,
        )


class PolicyDetailView(APIView):
    """
    Explanation: Returns a specific policy (CustomerPlan) and its associated items.
    Expected Input: URL Param 'customerPlanID'.
    Expected Output: JSON object with policy and items details.
    """

    def get(self, request, customerPlanID):
        plan_id = customerPlanID
        try:
            policy = CustomerPlan.objects(__raw__={
                "$or": [
                    {"CustomerPlanID": plan_id},
                    {"customerPlanID": plan_id},
                    {"planID": plan_id},
                ]
            }).first()
        except Exception as e:
            msg = "Database connection error"
            if settings.DEBUG:
                msg = f"Database error: {e}"
            return Response({"error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not policy:
            return Response({"error": "Policy not found"}, status=status.HTTP_404_NOT_FOUND)

        def _get(doc, *keys):
            for k in keys:
                val = getattr(doc, k, None)
                if val is not None:
                    return val
                if hasattr(doc, "_data") and k in doc._data:
                    val = doc._data.get(k)
                    if val is not None:
                        return val
            return None

        plan_id_field = _get(policy, "planID", "PlanID")
        plan_name = plan_desc = None
        coverage = base_price = None
        if plan_id_field is not None:
            try:
                ins = InsurancePlan.objects(__raw__={
                    "$or": [
                        {"planID": plan_id_field},
                        {"PlanID": plan_id_field},
                    ]
                }).first()
                if ins:
                    plan_name = _get(ins, "PlanName", "plan_name")
                    plan_desc = _get(ins, "Description", "description")
                    coverage = _get(ins, "CoverageLim", "coverage_amount")
                    base_price = _get(ins, "BasePrice", "premium")
            except Exception:
                pass

        try:
            items = Item.objects(__raw__={
                "$or": [
                    {"CustomerPlanID": plan_id},
                    {"planID": plan_id},
                ]
            })
        except Exception as e:
            msg = "Database connection error"
            if settings.DEBUG:
                msg = f"Database error: {e}"
            return Response({"error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        def _item_to_dict(it):
            return {
                "itemID": _get(it, "ItemID", "itemID"),
                "name": _get(it, "Name", "name"),
                "description": _get(it, "Description", "description"),
                "category": _get(it, "Category", "category"),
                "purchaseDate": (_get(it, "PurchaseDate") or _get(it, "purchaseDate")),
                "estimatedValue": _get(it, "EstimatedValue", "estimatedValue", "Value"),
                "imagePath1": getattr(it, "ImagePath1", None),
                "imagePath2": getattr(it, "ImagePath2", None),
                "claimStatus": getattr(it, "ClaimStatus", None),
            }

        items_list = [_item_to_dict(it) for it in items]

        policy_dict = {
            "customerPlanID": _get(policy, "CustomerPlanID", "customerPlanID"),
            "customerID": _get(policy, "CustomerID", "customerID"),
            "planID": plan_id_field,
            "startDate": _get(policy, "StartDate", "startDate"),
            "endDate": _get(policy, "EndDate", "endDate"),
            "currentPremium": _get(policy, "CurrentPremium", "currentPremium"),
            "status": _get(policy, "Status", "status"),
            "planName": plan_name,
            "planDescription": plan_desc,
            "coverageLimit": coverage,
            "basePrice": base_price,
        }

        return Response(
            {
                "policy": policy_dict,
                "items": items_list,
                "count": len(items_list),
            },
            status=status.HTTP_200_OK,
        )


class ResetPasswordView(APIView):
    """
    Explanation: Resets the user's password using a valid token.
    Expected Input: JSON Body { "token": str, "new_password": str }.
    Expected Output: JSON message (Success).
    """

    def get(self, request):
        return Response(
            {
                "endpoint": "/api/auth/reset-password/",
                "methods": ["POST"],
                "usage": "POST JSON with 'token' and 'new_password' to reset your password.",
                "required": ["token", "new_password"],
                "example": {"token": "<paste token>", "new_password": "NewStrongPassword"},
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        token = serializer.validated_data["token"]
        new_password = serializer.validated_data["new_password"]

        try:
            user = User.objects(resetToken=token).first()
        except Exception:
            user = None

        if not user or not user.is_reset_token_valid(token):
            return Response({"error": "Invalid or expired token"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user.set_password(new_password)
            user.save()
            user.clear_reset_token()
        except Exception as e:
            return Response({"error": "Failed to reset password"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"message": "Password has been reset successfully"}, status=status.HTTP_200_OK)