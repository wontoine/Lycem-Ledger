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

from users.models import User, Role, Customer, CustomerPlan, InsurancePlan, Item, ClaimRecord, Agent, ClaimWorkflowHistory
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
    try:
        domain = settings.COMPANY_EMAIL_DOMAIN.lower()
        if isinstance(email, str) and "@" in email and email.lower().endswith(f"@{domain}"):
            return "employee"
        # If an email-like string is provided but not company domain, treat as customer.
        if isinstance(email, str) and "@" in email:
            return "customer"
        return "unknown"
    except Exception:
        return "unknown"


def _role_name_for(role_id: int) -> str:
    try:
        role = Role.objects(roleID=role_id).first()
        return role.RoleName if role else "unknown"
    except Exception:
        return "unknown"


def _default_customer_role_id() -> int:
    """
    Resolve the role ID used for newly created customer accounts.
    """
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
    Prototype login endpoint.
    - Accepts JSON: {"username", "password"}
    - Looks up user in MongoDB (MongoEngine)
    - Checks password (supports current plaintext or PBKDF2-hash form)
    - Classifies account type based on company email domain
    - Returns approval result (no session/JWT yet)
    """

    def get(self, request):
        """
        Provide usage information for this endpoint when accessed via GET.
        This avoids a 405 response in browsers and gives quick guidance.
        """
        return Response(
            {
                "endpoint": "/api/auth/login/",
                "methods": ["POST"],
                "usage": "POST JSON with 'username' and 'password'. If username is not found, the system will try the same value as a customer email; lastly it will try an explicit 'email' field if provided.",
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
        # Read only the keys we care about; ignore any extras
        try:
            data = request.data if isinstance(request.data, dict) else {}
        except ParseError:
            data = {}

        username = data.get("username")
        email = data.get("email")
        password = data.get("password")

        # Require password and at least one identifier
        if not password or not (username or email):
            return Response(
                {"approved": False, "error": {"detail": "Provide 'password' and either 'username' or 'email'"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Username-first lookup; then try the username value as an email in customers;
        # only then fall back to explicit email field if provided
        try:
            user = None
            if username:
                user = User.objects(username=username).first()
            # If no user by username, treat the provided username as an email and
            # try to resolve via customers collection
            if not user and username:
                try:
                    cust = Customer.objects(__raw__={"email": {"$regex": f"^{username}$", "$options": "i"}}).first()
                except Exception:
                    cust = None
                if cust:
                    user = User.objects(userid=getattr(cust, "UserID", None)).first()
            # Finally, if still not found and a separate email field was provided, try that
            if not user and email:
                try:
                    # Resolve user via customers collection using authoritative email
                    cust = Customer.objects(__raw__={"email": {"$regex": f"^{email}$", "$options": "i"}}).first()
                except Exception:
                    cust = None
                if cust:
                    user = User.objects(userid=getattr(cust, "UserID", None)).first()
        except Exception as e:
            return Response({"approved": False, "error": "Database connection error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not user:
            return Response({"approved": False, "error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.isEnabled:
            return Response({"approved": False, "error": "Account is disabled"}, status=status.HTTP_401_UNAUTHORIZED)

        # Check password (supports transitional plaintext hashes in DB)
        if not user.check_password(password):
            return Response({"approved": False, "error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

        role_name = user.role_name or _role_name_for(user.roleID)
        # Fetch email from customers collection using userID
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
    Register a new account after validating policy and email ownership.
    """

    def get(self, request):
        """Describe how to create an account."""
        return Response(
            {
                "endpoint": "/api/auth/create-account/",
                "methods": ["POST"],
                "usage": "POST JSON with 'email', 'username', 'customerPlanID', and 'password'. Email is validated against the customers record for that policy.",
                "required": ["email", "username", "customerPlanID", "password"],
                "example": {"email": "customer@example.com", "username": "newuser", "customerPlanID": 123, "password": "ChooseAStrongPassword"},
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = CreateAccountSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"created": False, "error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        # Normalize inputs
        raw_email = serializer.validated_data["email"]
        email = (raw_email or "").strip()
        email_lower = email.lower()
        username = serializer.validated_data["username"].strip()
        plan_id = int(serializer.validated_data["customerPlanID"])  # ensure int
        password = serializer.validated_data["password"]

        # Step 1: find plan -> resolve owning customerID
        try:
            # Primary path: field exactly as modeled (CustomerPlanID)
            plan = CustomerPlan.objects(CustomerPlanID=plan_id).first()
            # Fallbacks: handle inconsistent field casing or string-typed ids in the DB
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

        # Step 2: fetch customer by CustomerID from plan
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
        # Compare emails case-insensitively
        try:
            cust_email = (getattr(customer, "Email", None) or "").strip()
            if cust_email.lower() != email_lower:
                return Response(
                    {"created": False, "error": "Email does not match our records"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        except Exception as e:
            print(f"CreateAccountView: error validating customer email: {e}")
            return Response({"created": False, "error": "Database connection error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        if not isinstance(getattr(customer, "UserID", None), int):
            return Response(
                {"created": False, "error": "Customer record is missing a userID"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Uniqueness checks
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
            # Do not check User.email; authoritative email lives in customers

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
    Request a password reset token. Always returns 200 to avoid user enumeration.
    Accepts JSON: { "identifier" | "email" | "username" }
    Sends an email with a reset link or token if the user exists and has an email.
    """

    def _extract_identifier(self, request) -> str | None:
        """Try hard to extract an identifier (email or username) from various body formats.

        Supports:
        - Proper JSON (Content-Type: application/json)
        - Malformed JSON bodies that trip DRF's JSON parser (fallback to raw parse)
        - application/x-www-form-urlencoded (identifier=..., email=..., username=...)
        - Plain text body containing just the email/username
        - Query string ?identifier=... (last resort)
        """
        # 1) Try DRF-parsed data first
        try:
            data = request.data  # may raise ParseError if Content-Type says JSON but it's malformed
            if isinstance(data, dict):
                ident = data.get("identifier") or data.get("email") or data.get("username")
                if ident:
                    return ident
        except ParseError:
            # We'll try raw parsing below
            pass

        # 2) Try raw body
        try:
            raw = request.body or b""
            if not raw:
                raw = getattr(request, "_request", None)
                raw = getattr(raw, "body", b"") if raw is not None else b""
            if isinstance(raw, bytes):
                raw_text = raw.decode("utf-8", errors="ignore").strip()
            else:
                raw_text = str(raw).strip()

            # If it looks like JSON, try to parse
            if raw_text.startswith("{") and raw_text.endswith("}"):
                try:
                    obj = json.loads(raw_text)
                    if isinstance(obj, dict):
                        ident = obj.get("identifier") or obj.get("email") or obj.get("username")
                        if ident:
                            return ident
                except Exception:
                    pass

            # If it looks like form-encoded (a=b&c=d)
            if "=" in raw_text and "&" in raw_text or raw_text.startswith("identifier=") or raw_text.startswith("email=") or raw_text.startswith("username="):
                try:
                    q = parse_qs(raw_text, keep_blank_values=True)
                    # parse_qs returns lists
                    for key in ("identifier", "email", "username"):
                        vals = q.get(key)
                        if vals and vals[0]:
                            return vals[0]
                except Exception:
                    pass

            # As a last resort, if body is just the identifier itself
            if raw_text:
                return raw_text
        except Exception:
            pass

        # 3) Try query params
        try:
            qp = request.query_params  # type: ignore[attr-defined]
            ident = qp.get("identifier") or qp.get("email") or qp.get("username")
            if ident:
                return ident
        except Exception:
            pass

        return None

    def get(self, request):
        """Describe how to request a password reset token."""
        return Response(
            {
                "endpoint": "/api/auth/forgot-password/",
                "methods": ["POST"],
                "usage": "POST JSON with one of 'identifier', 'email', or 'username'. A reset token will be issued if the account exists.",
                "identifiers": ["identifier", "email", "username"],
                "example": {"identifier": "john.doe"},
                "note": "For development, the reset token and link are printed to the server console.",
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        # First, try to use the serializer with whatever data we can extract
        payload = {}
        ident = self._extract_identifier(request)
        if ident:
            payload = {"identifier": ident}
        else:
            # If we truly cannot parse anything, return generic 200 to avoid enumeration
            return Response({"message": "If an account exists, an email has been sent."}, status=status.HTTP_200_OK)

        serializer = ForgotPasswordSerializer(data=payload)
        if not serializer.is_valid():
            # Still return 200 to avoid enumeration; include generic message
            return Response({"message": "If an account exists, an email has been sent."}, status=status.HTTP_200_OK)

        ident = serializer.validated_data["identifier"]
        try:
            # Attempt by email first using customers collection, else by username
            user = None
            customer = None
            if isinstance(ident, str) and "@" in ident:
                # Find customer by email (case-insensitive)
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
            # Do not reveal errors here; return generic response
            return Response({"message": "If an account exists, an email has been sent."}, status=status.HTTP_200_OK)

        # If user exists, issue a token regardless of email setup and print it to console for development convenience
        if user:
            try:
                token = user.issue_reset_token(ttl_minutes=60)
            except Exception:
                token = None

            # Build a reset link. Prefer PASSWORD_RESET_BASE_URL if configured; otherwise fall back to a fully-qualified URL using the current host.
            try:
                link = None
                base = getattr(settings, "PASSWORD_RESET_BASE_URL", "") or ""
                if token:
                    if base:
                        base = str(base).strip()
                        # If developer provided a template with {token}, honor it directly
                        if "{token}" in base:
                            link = base.format(token=token)
                        else:
                            # If base already contains a query string, append using &token=
                            if "?" in base:
                                sep = "&" if not base.endswith(("&", "?")) else ""
                                link = f"{base}{sep}token={token}"
                            else:
                                # Normalize trailing slash then add ?token=
                                base_norm = base.rstrip("/")
                                link = f"{base_norm}?token={token}"
                    else:
                        # Fallback: build absolute URL from the incoming request
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

            # Always print token (and link if available) to server console so you can copy it without email set up
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

            # Send reset email to the customer's email if available
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
                        getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(settings, "EMAIL_HOST_USER", None) or "no-reply@localhost",
                        [getattr(customer, "Email")],
                        fail_silently=True,
                    )
                except Exception:
                    # Swallow errors to avoid exposing user info
                    pass

        return Response({"message": "If an account exists, an email has been sent."}, status=status.HTTP_200_OK)


class CustomerPlansView(APIView):
    """
    Return all plans for the customer associated with a given userID.
    """

    def get(self, request):
        user_id_raw = request.query_params.get("userID")
        if not user_id_raw:
            return Response({"error": "userID is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user_id = int(user_id_raw)
        except ValueError:
            return Response({"error": "userID must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        # Resolve customer by userID
        try:
            customer = Customer.objects(UserID=user_id).first()
        except Exception as e:
            msg = "Database connection error"
            if settings.DEBUG:
                msg = f"Database error: {e}"
            return Response({"error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not customer:
            return Response({"error": "Customer not found"}, status=status.HTTP_404_NOT_FOUND)

        # Fetch plans for this customer
        try:
            plans = CustomerPlan.objects(CustomerID=customer.CustomerID)
        except Exception as e:
            msg = "Database connection error"
            if settings.DEBUG:
                msg = f"Database error: {e}"
            return Response({"error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        def _get(plan, *keys):
            """
            Safely pull a value from a MongoEngine document that may have
            varying field names/casing or be present only in _data because
            the model doesn't declare the field.
            """
            for k in keys:
                # direct attribute
                val = getattr(plan, k, None)
                if val is not None:
                    return val
                # raw data fallback when strict=False
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

        # Enrich with plan names from insurancePlans
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
    Customer claim submission.
    - Validates that the userID maps to a customer.
    - Validates that the policy (customerPlanID) belongs to that customer.
    - Validates that the item belongs to that customer.
    - Creates a claim in claimedItems with status = Filed (CurrentStatusID = 1).
    - Marks the item as in-progress (sets ClaimStatus = 'In Progress').
    """

    def _validate_client_path(self, path_value):
        """
        Very basic validation to ensure client-provided paths are relative and safe.
        """
        if not path_value or not isinstance(path_value, str):
            return None
        path_value = path_value.strip()
        # Reject absolute paths or traversal attempts
        if path_value.startswith(("/", "\\")) or ".." in path_value:
            return None
        return path_value or None

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        required = ["userID", "policyID", "amount", "reason"]
        missing = [f for f in required if f not in data or data[f] in (None, "")]
        if missing:
            return Response({"error": {"missing": missing}}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user_id = int(data.get("userID"))
            policy_id = int(data.get("policyID"))
        except (ValueError, TypeError):
            return Response({"error": "userID and policyID must be integers"}, status=status.HTTP_400_BAD_REQUEST)

        item_id = data.get("itemID")
        if item_id not in (None, ""):
            try:
                item_id = int(item_id)
            except (ValueError, TypeError):
                return Response({"error": "itemID must be an integer if provided"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            item_id = None

        try:
            amount = Decimal(str(data.get("amount")))
        except Exception:
            return Response({"error": "amount must be numeric"}, status=status.HTTP_400_BAD_REQUEST)

        reason = str(data.get("reason", "")).strip()
        loss_date = data.get("lossDate")  # optional; accept ISO string

        # Resolve customer by userID
        try:
            customer = Customer.objects(UserID=user_id).first()
        except Exception as e:
            msg = "Database connection error"
            if settings.DEBUG:
                msg = f"Database error: {e}"
            return Response({"error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not customer:
            return Response({"error": "Customer not found"}, status=status.HTTP_404_NOT_FOUND)

        # Validate policy belongs to this customer
        try:
            policy = CustomerPlan.objects(CustomerID=customer.CustomerID, CustomerPlanID=policy_id).first()
            if not policy:
                # fallback for mixed casing
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
            # Validate item belongs to this customer
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

            # Prevent duplicate open claims on the same item (status Filed=1, In Review=2)
            try:
                open_claim = ClaimRecord.objects(__raw__={
                    "ItemID": item_id,
                    "CurrentStatusID": {"$in": [1, 2]}
                }).first()
            except Exception:
                open_claim = None

            if open_claim:
                return Response({"error": "An open claim already exists for this item"}, status=status.HTTP_409_CONFLICT)

        # Generate next ClaimID (simple max+1)
        try:
            last = ClaimRecord.objects.order_by("-ClaimID").first()
            next_id = (last.ClaimID + 1) if last and getattr(last, "ClaimID", None) else 1
        except Exception:
            next_id = 1

        now = timezone.now()
        # Normalize loss_date if provided
        loss_dt = None
        if loss_date:
            try:
                loss_dt = datetime.fromisoformat(loss_date)
            except Exception:
                loss_dt = None

        # Create claim record
        try:
            claim = ClaimRecord(
                ClaimID=next_id,
                ItemID=item_id,
                CurrentStatusID=1,  # Filed
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

        # Mark item as in-progress (add a field without strict schema enforcement)
        if item is not None:
            try:
                setattr(item, "ClaimStatus", "In Progress")
                item.save()
            except Exception:
                # best effort; do not fail claim creation if item update fails
                pass

        # Log workflow history (Filed) with agent/employee name resolved from assignment
        try:
            agent_name = None
            agent_id = getattr(customer, "assignment", None) or getattr(customer, "Assignment", None)
            if agent_id is not None:
                ag = Agent.objects(__raw__={"$or": [{"agentID": agent_id}, {"AgentID": agent_id}]}).first()
                if ag:
                    fn = getattr(ag, "firstname", None) or getattr(ag, "firstName", None)
                    ln = getattr(ag, "lastName", None) or getattr(ag, "lastname", None)
                    agent_name = " ".join(filter(None, [fn, ln])) or getattr(ag, "email", None)
            # Generate next HistoryID
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
            # best effort; do not fail claim creation if history logging fails
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
    Add an item (for a given customerPlanID) with up to two images.
    - Uses customerPlanID and customerID to ensure ownership.
    - Accepts multipart/form-data with fields:
      name (required), estimatedValue (required), customerPlanID (required),
      description (optional), Category (optional), purchaseDate (optional ISO),
      image1 (optional), image2 (optional)
    - Allowed image types: jpeg, png; max size: 10 MB each.
    - Stores two image paths on the item document (ImagePath1, ImagePath2).
    """

    parser_classes = [MultiPartParser, FormParser]
    MAX_SIZE = 10 * 1024 * 1024  # 10 MB
    ALLOWED_EXT = {".jpg", ".jpeg", ".png"}

    def _slug(self, text):
        text = text.strip().lower()
        text = re.sub(r"[^a-z0-9-_]+", "-", text)
        return text or "file"

    def _save_file(self, file_obj, customer_id, plan_id, item_name_slug, idx):
        upload_root = os.environ.get("UPLOAD_ROOT") or getattr(settings, "UPLOAD_ROOT", None)
        if not upload_root:
            raise RuntimeError("UPLOAD_ROOT is not configured")

        # Validate size
        if hasattr(file_obj, "size") and file_obj.size > self.MAX_SIZE:
            raise ValueError("File too large")

        # Validate extension
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

        return rel_path  # relative to upload_root

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}

        # Required fields (note: userID drives ownership; we resolve customerID from it)
        for field in ["name", "estimatedValue", "customerPlanID", "userID"]:
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
            user_id = int(data.get("userID"))
        except Exception:
            return Response({"error": {"userID": "Must be an integer"}}, status=status.HTTP_400_BAD_REQUEST)

        try:
            estimated_value = Decimal(str(data.get("estimatedValue")))
        except Exception:
            return Response({"error": {"estimatedValue": "Must be numeric"}}, status=status.HTTP_400_BAD_REQUEST)

        # Optional purchase date
        purchase_date_raw = data.get("purchaseDate")
        purchase_date = None
        if purchase_date_raw:
            try:
                purchase_date = datetime.fromisoformat(purchase_date_raw)
            except Exception:
                return Response({"error": {"purchaseDate": "Invalid date format"}}, status=status.HTTP_400_BAD_REQUEST)
        purchase_date_str = purchase_date.isoformat() if purchase_date else None

        # Resolve customer by userID
        try:
            customer = Customer.objects(UserID=user_id).first()
        except Exception as e:
            msg = "Database connection error"
            if settings.DEBUG:
                msg = f"Database error: {e}"
            return Response({"error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not customer:
            return Response({"error": "Customer not found for this userID"}, status=status.HTTP_404_NOT_FOUND)

        customer_id = getattr(customer, "CustomerID", None)
        try:
            customer_id = int(customer_id) if customer_id is not None else None
        except Exception:
            customer_id = None

        if customer_id is None:
            return Response({"error": "Customer record missing CustomerID"}, status=status.HTTP_400_BAD_REQUEST)

        # Validate policy exists (by plan_id) and matches this customer's CustomerID
        def _get_customer_id(doc):
            """
            Resolve CustomerID from the document. Do NOT fall back to userID.
            """
            for k in ("CustomerID", "customerID"):
                v = getattr(doc, k, None)
                if v is None and hasattr(doc, "_data"):
                    v = doc._data.get(k)
                if v is not None:
                    return v
            return None

        try:
            policy = CustomerPlan.objects(__raw__={
                "$or": [
                    {"CustomerPlanID": plan_id},
                    {"customerPlanID": plan_id},
                    {"planID": plan_id},
                    {"CustomerPlanID": str(plan_id)},
                    {"customerPlanID": str(plan_id)},
                    {"planID": str(plan_id)},
                ]
            }).first()
        except Exception as e:
            msg = "Database connection error"
            if settings.DEBUG:
                msg = f"Database error: {e}"
            return Response({"error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not policy:
            return Response({"error": "customerPlanID not found"}, status=status.HTTP_404_NOT_FOUND)

        owner = _get_customer_id(policy)
        try:
            owner_int = int(owner) if owner is not None else None
        except Exception:
            owner_int = None

        if owner_int is None or owner_int != customer_id:
            return Response({"error": "customerID does not match plan ownership"}, status=status.HTTP_400_BAD_REQUEST)

        # Generate next ItemID (max+1)
        try:
            last = Item.objects.order_by("-ItemID").first()
            next_id = (last.ItemID + 1) if last and getattr(last, "ItemID", None) else 1
        except Exception:
            next_id = 1

        # Prepare image paths (either uploaded files or client-provided relative paths)
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
                # Allow optional client-provided path in JSON (already stored somewhere else)
                client_path = self._validate_client_path(data.get(f"imagePath{idx}"))
                if not client_path:
                    return Response({"error": {field: "Image is required"}}, status=status.HTTP_400_BAD_REQUEST)
                image_paths.append(client_path)

        # Create item (strict=False allows extra fields)
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
                # two slots: ImagePath1, ImagePath2
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
    Get a specific policy (customerPlan) and all items linked to it.
    URL: /api/auth/policies/<int:customerPlanID>/
    """

    def get(self, request, customerPlanID):
        plan_id = customerPlanID
        # Fetch the policy (customerPlan)
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

        # Enrich with insurance plan info
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

        # Fetch items linked to this plan
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
    Reset the password using a valid token. Expects JSON: { "token", "new_password" }
    """

    def get(self, request):
        """Describe how to reset a password with a token."""
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
