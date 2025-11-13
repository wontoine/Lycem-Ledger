from mongoengine import Document, StringField, EmailField, IntField, BooleanField, ReferenceField
from django.contrib.auth.hashers import make_password, check_password as django_check_password



class Role(Document):
    """
    Role document matching your MongoDB Roles collection
    """
    roleID = IntField(required=True, unique=True)
    RoleName = StringField(required=True, max_length=50)

    meta = {
        'collection': 'Roles',
        'indexes': ['roleID']
    }

    def __str__(self):
        return f"{self.RoleName} (ID: {self.roleID})"


class Customer(Document):
    """
    Customer record used to validate policy number/email combos.
    """
    CustomerID = IntField(required=True, unique=True, db_field="customerID")
    UserID = IntField(required=True, unique=True, db_field="userID")
    Email = StringField(required=True, max_length=255, db_field="email")

    meta = {
        'collection': 'customers',
        # Avoid auto-creating indexes to prevent conflicts with existing DB state.
        'auto_create_index': False,
        'strict': False,  # allow extra fields (address, phones, etc.) present in documents
    }

    def __str__(self):
        return f"{self.Email} ({self.CustomerID})"


class CustomerPlan(Document):
    """
    Minimal CustomerPlans document used during registration to map a
    customerPlanID to the owning CustomerID.
    """
    CustomerPlanID = IntField(required=True, unique=True, db_field="CustomerPlanID")
    CustomerID = IntField(required=True, db_field="CustomerID")

    meta = {
        'collection': 'customerPlans',
        'auto_create_index': False,
        'strict': False,  # tolerate extra plan fields such as StartDate, Status, etc.
    }

    def __str__(self):
        return f"Plan {self.CustomerPlanID} -> Customer {self.CustomerID}"


class User(Document):
    """
    User document matching your MongoDB users collection
    """
    userid = IntField(required=True, unique=True)
    username = StringField(required=True, max_length=100, unique=True)
    
    email = StringField(required=False, max_length=255)
    roleID = IntField(required=True)
    passwordHash = StringField(required=True, max_length=255)
    isEnabled = BooleanField(default=True)

    meta = {
        'collection': 'users',
        # Use default MongoDB index names (e.g., userid_1) to avoid name conflicts
        'indexes': [
            {'fields': ['userid'], 'unique': True},
            {'fields': ['username'], 'unique': True},
            {'fields': ['email'], 'unique': True, 'sparse': True},
        ],
    }

    def __str__(self):
        return f"{self.username} ({self.email})"

    @classmethod
    def hash_password(cls, password):
        """
        Hash password using Argon2 (via Django's make_password).
        """
        return make_password(password)

    def check_password(self, password):
        """
        Check if provided password matches the stored hash.

        Behavior (in priority order):
        1. If passwordHash is Argon2/Django format -> verify with django_check_password
        2. If passwordHash is plaintext and matches -> AUTO-MIGRATE to Argon2 and return True
        3. Otherwise -> return False

        This allows testing with plaintext passwords that get automatically upgraded
        to Argon2 on first successful login.
        """
        try:
            ph = self.passwordHash or ''
            
            # Check if it's already a Django-hashed password (Argon2, PBKDF2, bcrypt, etc.)
            if ph.startswith(('argon2', 'pbkdf2_', 'bcrypt', 'scrypt')):
                is_valid = django_check_password(password, ph)
                return is_valid
            
            # If it's plaintext and matches, automatically migrate to Argon2
            if ph == password:
                print(f"Migrating plaintext password to Argon2 for user: {self.username}")
                try:
                    self.passwordHash = make_password(password)
                    self.passwordHash = make_password(password)
                    self.save()
                    print(f"Password migrated successfully for: {self.username}")
                except Exception as e:
                    print(f"Migration failed for {self.username}: {e}")
                    # Even if migration fails, allow this login once
                return True
            
            # Password doesn't match
            return False
            
        except Exception as e:
            print(f"Error checking password for {self.username}: {e}")
            return False

    def set_password(self, password):
        """
        Set password hash using Argon2.
        Use this when creating new users or updating passwords.
        """
        self.passwordHash = self.hash_password(password)

    @property
    def role_name(self):
        """
        Get role name from roleID
        """
        try:
            role = Role.objects(roleID=self.roleID).first()
            return role.RoleName if role else 'unknown'
        except:
            return 'unknown'
