from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings

from users.models import User, Role
from .serializers import LoginSerializer


def _classify_account(email: str) -> str:
    domain = settings.COMPANY_EMAIL_DOMAIN.lower()
    return "employee" if email.lower().endswith(f"@{domain}") else "customer"


def _role_name_for(role_id: int) -> str:
    try:
        role = Role.objects(roleID=role_id).first()
        return role.RoleName if role else "unknown"
    except Exception:
        return "unknown"


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

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        # Find user by email
        try:
            user = User.objects(email=email).first()
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
        account_type = _classify_account(user.email)
        is_admin = (role_name.lower() == "admin")

        return Response(
            {
                "approved": True,
                "user": {
                    "userid": user.userid,
                    "username": user.username,
                    "email": user.email,
                    "role": role_name,
                    "isEnabled": user.isEnabled,
                    "accountType": account_type,
                    "isAdmin": is_admin,
                },
            },
            status=status.HTTP_200_OK,
        )
