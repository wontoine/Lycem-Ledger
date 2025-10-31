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


class User(Document):
    """
    User document matching your MongoDB users collection
    """
    userid = IntField(required=True, unique=True)
    username = StringField(required=True, max_length=100)
    # Temporarily make email optional and non-unique so the DB can
    # contain users without emails while we finish wiring things up.
    # We'll reintroduce uniqueness (likely sparse) when emails are present.
    email = StringField(required=False, max_length=255)
    roleID = IntField(required=True)
    passwordHash = StringField(required=True, max_length=255)
    isEnabled = BooleanField(default=True)
    
    meta = {
        'collection': 'users',
        'indexes': ['userid', 'email', 'username']
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
