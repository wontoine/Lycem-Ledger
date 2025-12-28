curl.exe -i -X POST "http://127.0.0.1:8000/api/auth/forgot-password/" -H "Content-Type: application/json" -d "{\"identifier\": \"john.doe\"}"
from users.models import User
u = User.objects(username="john.doe").first()
print(f"Reset Token: {u.resetToken}")

curl.exe -i -X POST "http://127.0.0.1:8000/api/auth/reset-password/" -H "Content-Type: application/json" -d "{\"token\": \"<YOUR_TOKEN>\", \"new_password\": \"NewSecurePassword123!\"}"