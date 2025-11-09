from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings

from users.models import User, Role, Customer, CustomerPlan
from .serializers import LoginSerializer, CreateAccountSerializer


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
    - Accepts JSON: {"email", "password"}
    - Looks up user in MongoDB (MongoEngine)
    - Checks password (supports current plaintext or PBKDF2-hash form)
    - Classifies account type based on company email domain
    - Returns approval result (no session/JWT yet)
    """

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"approved": False, "error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        identifier = serializer.validated_data["identifier"]
        password = serializer.validated_data["password"]

        # TEMP: Treat every identifier as a username while the
        # database stabilizes and email is introduced later.
        # When ready, restore email lookup with "@" detection.
        try:
            user = User.objects(username=identifier).first()
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
        account_type = _classify_account(getattr(user, "email", None))
        is_admin = (role_name.lower() == "admin")

        return Response(
            {
                "approved": True,
                "user": {
                    "userid": user.userid,
                    "username": user.username,
                    "email": getattr(user, 'email', None),
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
            if email and User.objects(email=email).first():
                return Response(
                    {"created": False, "error": "An account already exists for this email"},
                    status=status.HTTP_409_CONFLICT,
                )

            new_user = User(
                userid=customer.UserID,
                username=username,
                email=email or None,
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
                    "email": new_user.email,
                    "roleID": new_user.roleID,
                },
            },
            status=status.HTTP_201_CREATED,
        )
