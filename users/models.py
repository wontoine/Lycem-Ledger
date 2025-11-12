from mongoengine import Document, StringField, IntField, BooleanField, ReferenceField
import hashlib
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
        Hash password using Django's password hasher (Argon2 preferred via settings).
        """
        return make_password(password)
    
    def check_password(self, password):
        """
        Check if provided password matches the stored hash.

        Behavior (priority order):
        1) If `passwordHash` looks like a Django hash (argon2, pbkdf2_*, bcrypt, scrypt) -> verify with Django.
        2) If `passwordHash` contains a colon -> treat it as legacy "salt:hexhash" (PBKDF2-SHA256) and compare.
        3) If `passwordHash` appears to be plaintext and matches -> migrate to Django hasher and return True.
        4) Otherwise -> False.
        """
        try:
            ph = self.passwordHash or ''

            # 1) Django-managed hashes (argon2/pbkdf2_/bcrypt/scrypt)
            if ph.startswith(('argon2', 'pbkdf2_', 'bcrypt', 'scrypt')):
                return django_check_password(password, ph)

            # 2) Legacy custom format: salt:hexhash (PBKDF2-SHA256)
            if ':' in ph:
                salt, stored_hash = ph.split(':', 1)
                hash_obj = hashlib.pbkdf2_hmac(
                    'sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000
                )
                if hash_obj.hex() == stored_hash:
                    # On successful legacy match, migrate to Django hasher for future logins
                    try:
                        self.passwordHash = make_password(password)
                        self.save()
                    except Exception:
                        pass
                    return True
                return False

            # 3) Plaintext stored: migrate on successful match
            if ph == password:
                try:
                    self.passwordHash = make_password(password)
                    self.save()
                except Exception:
                    # Even if migration fails, allow this login once
                    pass
                return True

            # 4) No match
            return False
        except Exception:
            return False
    
    def set_password(self, password):
        """
        Set password hash
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
