# Test MongoDB connection and create sample data
# Run this with: py manage.py shell
# Then copy-paste this code

from users.models import User, Role

# Test connection
print("Testing MongoDB connection...")

# Create sample roles if they don't exist
try:
    role1 = Role.objects(roleID=1).first()
    if not role1:
        role1 = Role(roleID=1, RoleName='user').save()
        print("Created role: user")
    
    role2 = Role.objects(roleID=2).first()
    if not role2:
        role2 = Role(roleID=2, RoleName='admin').save()
        print("Created role: admin")
    
    print("Roles created successfully")
except Exception as e:
    print(f"Error creating roles: {e}")

# Create a test user
try:
    test_user = User.objects(email='test@example.com').first()
    if not test_user:
        test_user = User(
            userid=999,
            username='testuser',
            email='test@example.com',
            roleID=1,
            isEnabled=True
        )
        test_user.set_password('testpassword123')
        test_user.save()
        print("Created test user: test@example.com / testpassword123")
    else:
        print("Test user already exists")
except Exception as e:
    print(f"Error creating test user: {e}")

# Test login
try:
    user = User.objects(email='test@example.com').first()
    if user and user.check_password('testpassword123'):
        print(f"Login test successful! User: {user.username}, Role: {user.role_name}")
    else:
        print("Login test failed")
except Exception as e:
    print(f"Error testing login: {e}")

print("MongoDB setup complete!")
