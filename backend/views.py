# Simple API views for testing and basic authentication

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.hashers import check_password
from users.models import User, Role, Customer


class HelloWorldView(APIView):
    """
    Explanation: Basic connectivity endpoint to verify the API is reachable and DRF is configured.
    Expected Input: GET request (no parameters).
    Expected Output: JSON object with status message (HTTP 200).
    """

    def get(self, request):
        return Response({
            'message': 'Hello World!',
            'status': 'Django REST Framework is working!',
            'server': 'Lycem-Ledger Authentication Backend'
        }, status=status.HTTP_200_OK)


class LoginView(APIView):
    """
    Explanation: Authenticates a user. Supports login via 'username' or 'email'.
                 Checks against MongoEngine User documents and validates passwords.
    Expected Input: JSON Body { "username": str (optional), "email": str (optional), "password": str }.
    Expected Output: JSON object containing user details and role info (HTTP 200), or error (HTTP 400/401).
    """

    def post(self, request):
        username = request.data.get('username')
        email = request.data.get('email')
        password = request.data.get('password')

        # Validation: Ensure password and at least one identifier are present
        if not (username or email):
            return Response({
                'error': 'Username or email is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        if not password:
            return Response({
                'error': 'Password is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = None
            cust_email = None

            # Strategy 1: Look up by username directly in User collection
            if username:
                user = User.objects(username=username).first()
                if user:
                    try:
                        # Fetch associated email from Customer record
                        cust = Customer.objects(UserID=user.userid).first()
                        if cust:
                            cust_email = getattr(cust, 'Email', None)
                    except Exception:
                        cust_email = None

            # Strategy 2: If not found or only email provided, look up in Customer collection
            else:
                try:
                    # Regex used for case-insensitive email match
                    cust = Customer.objects(__raw__={"email": {"$regex": f"^{email}$", "$options": "i"}}).first()
                except Exception:
                    cust = None

                if cust:
                    cust_email = getattr(cust, 'Email', None)
                    # Resolve back to User via UserID
                    user = User.objects(userid=getattr(cust, 'UserID', None)).first()

        except Exception as e:
            return Response({
                'error': 'Database connection error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not user:
            return Response({
                'error': 'Invalid credentials'
            }, status=status.HTTP_401_UNAUTHORIZED)

        if not user.isEnabled:
            return Response({
                'error': 'Account is disabled'
            }, status=status.HTTP_401_UNAUTHORIZED)

        # Uses the model's check_password method (supports legacy hashes and Argon2)
        if not user.check_password(password):
            return Response({
                'error': 'Invalid credentials'
            }, status=status.HTTP_401_UNAUTHORIZED)

        return Response({
            'message': 'Login successful',
            'user': {
                'userid': user.userid,
                'username': user.username,
                'email': cust_email,
                # Returns both readable role name and numeric ID for frontend logic
                'role': user.role_name,
                'accountType': user.role_name,
                'roleID': getattr(user, 'roleID', None),
                'isEnabled': user.isEnabled
            }
        }, status=status.HTTP_200_OK)


class HealthCheckView(APIView):
    """
    Explanation: Diagnostics endpoint to verify the backend can connect to the MongoDB database.
    Expected Input: GET request.
    Expected Output: JSON object with database connection status and document counts (HTTP 200) or error (HTTP 500).
    """

    def get(self, request):
        try:
            # Perform a simple read operation to verify DB connectivity
            user_count = User.objects.count()
            role_count = Role.objects.count()

            return Response({
                'status': 'healthy',
                'mongodb': 'connected',
                'users_count': user_count,
                'roles_count': role_count
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'status': 'unhealthy',
                'mongodb': 'disconnected',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)