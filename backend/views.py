# Simple API views for testing

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.hashers import check_password
from users.models import User, Role, Customer


class HelloWorldView(APIView):
    """
    Simple test endpoint to make sure Django REST Framework is working
    """
    
    def get(self, request):
        return Response({
            'message': 'Hello World!',
            'status': 'Django REST Framework is working!',
            'server': 'Lycem-Ledger Authentication Backend'
        }, status=status.HTTP_200_OK)


class LoginView(APIView):
    """
    Login endpoint using MongoEngine User documents.
    Accepts either username or email for login.
    """

    def post(self, request):
        # Accept either 'username' or 'email' field
        username = request.data.get('username')
        email = request.data.get('email')
        password = request.data.get('password')
        
        # User must provide either username or email
        if not (username or email):
            return Response({
                'error': 'Username or email is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not password:
            return Response({
                'error': 'Password is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Find user by username or by customer email (authoritative)
        try:
            user = None
            cust_email = None
            if username:
                user = User.objects(username=username).first()
                if user:
                    try:
                        cust = Customer.objects(UserID=user.userid).first()
                        if cust:
                            cust_email = getattr(cust, 'Email', None)
                    except Exception:
                        cust_email = None
            else:
                # Look up customer by email, then map to user via UserID
                try:
                    cust = Customer.objects(__raw__={"email": {"$regex": f"^{email}$", "$options": "i"}}).first()
                except Exception:
                    cust = None
                if cust:
                    cust_email = getattr(cust, 'Email', None)
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
        
        # Check password
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
                'role': user.role_name,
                'isEnabled': user.isEnabled
            }
        }, status=status.HTTP_200_OK)


class HealthCheckView(APIView):
    """
    Health check endpoint to verify MongoDB connection
    """
    
    def get(self, request):
        try:
            # Test MongoDB connection
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
