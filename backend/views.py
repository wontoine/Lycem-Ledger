# Simple API views for testing

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from users.models import User, Role


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
    Login endpoint using MongoEngine User documents
    """
    
    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        
        if not email or not password:
            return Response({'error': 'Email and password are required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Find user by email
        try:
            user = User.objects(email=email).first()
        except Exception as e:
            return Response({'error': 'Database connection error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        if not user:
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        
        if not user.isEnabled:
            return Response({'error': 'Account is disabled'}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Check password
        if not user.check_password(password):
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
        
        return Response({
            'message': 'Login successful',
            'user': {
                'userid': user.userid,
                'username': user.username,
                'email': user.email,
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
