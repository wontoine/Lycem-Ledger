from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ParseError
from django.conf import settings
from django.core.mail import send_mail
import json
from urllib.parse import parse_qs

from users.models import User, Role, Customer, CustomerPlan
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
