from mongoengine import Document, StringField, IntField, BooleanField, ReferenceField
import hashlib
import secrets


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
        Hash password using a simple method (you can upgrade to bcrypt/argon2 later)
        """
        salt = secrets.token_hex(16)
        hash_obj = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
        return f"{salt}:{hash_obj.hex()}"
    
    def check_password(self, password):
        """
        Check if provided password matches the stored hash.

        Behavior:
        - If `passwordHash` contains a colon, treat it as "salt:hexhash" (PBKDF2-SHA256) and compare.
        - If `passwordHash` appears to be plaintext and matches the provided password,
          automatically migrate this user to a hashed password and return True.
        """
        try:
            ph = self.passwordHash or ''
            if ':' in ph:
                salt, stored_hash = ph.split(':', 1)
                hash_obj = hashlib.pbkdf2_hmac(
                    'sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000
                )
                return hash_obj.hex() == stored_hash
            # Plaintext stored: migrate on successful match
            if ph == password:
                try:
                    self.set_password(password)
                    # Avoid triggering full validation; save only the changed field
                    self.save()
                except Exception:
                    # Even if migration fails, allow this login once
                    pass
                return True
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
