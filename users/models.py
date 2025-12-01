from mongoengine import (
    Document,
    StringField,
    IntField,
    BooleanField,
    ReferenceField,
    DateTimeField,
    ListField,
    FloatField,
    DictField,
)
import hashlib
from django.contrib.auth.hashers import make_password, check_password as django_check_password
from datetime import datetime, timedelta
from django.utils import timezone
import secrets


class Role(Document):
    """
    Defines user roles. This collection maps a numeric roleID to a name.

    Current lookup table:
    - 1 -> Customer
    - 2 -> Agent  (note: Agent is treated the same as Manager in access control)
    - 3 -> Supervisor
    - 4 -> Admin
    """
    roleID = IntField(required=True, unique=True)
    RoleName = StringField(required=True, max_length=50)

    meta = {
        'collection': 'roles',
        'indexes': ['roleID']
    }

    def __str__(self):
        return f"{self.RoleName} (ID: {self.roleID})"


class Agent(Document):
    """
    Minimal agent document used for lookups (assignment -> agent name).
    """
    agentID = IntField(required=True, unique=True, db_field="agentID")
    firstname = StringField(required=False, db_field="firstname")
    lastName = StringField(required=False, db_field="lastName")
    email = StringField(required=False, db_field="email")
    phone = StringField(required=False, db_field="phone")
    userID = IntField(required=False, db_field="userID")
    TeamID = IntField(required=False, db_field="TeamID")

    meta = {
        'collection': 'agents',
        'auto_create_index': False,
        'strict': False,
    }

    def __str__(self):
        return f"{self.firstname or ''} {self.lastName or ''}".strip() or f"Agent {self.agentID}"


class Customer(Document):
    """
    Stores core customer data.
    This links a unique CustomerID to the main UserID (from the 'users' collection)
    and their email. The 'strict: False' setting allows other data
    (like addresses) to exist in the document without causing errors.

    Example document:
    { "customerID": 1001, "userID": 50, "email": "customer@example.com", "address": "..." }
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
    Maps a specific insurance plan (CustomerPlanID) to its owner (CustomerID).
    This is mainly used to verify ownership during registration or other checks.

    Example document:
    { "CustomerPlanID": 9001, "CustomerID": 1001, "Status": "active" }
    """
    CustomerPlanID = IntField(required=True, unique=True, db_field="CustomerPlanID")
    CustomerID = IntField(required=True, db_field="CustomerID")

    meta = {
        'collection': 'customerPlans',
        'auto_create_index': False,
        'strict': False,  # tolerate extra plan fields (e.g., assignmentID)
    }

    def __str__(self):
        return f"Plan {self.CustomerPlanID} -> Customer {self.CustomerID}"


class InsurancePlan(Document):
    """
    Lightweight model for insurance plans catalog.
    We keep it flexible (strict=False) to match existing DB documents.

    Example document:
    { "planID": 1, "PlanName": "Basic Home", "Description": "...", "BasePrice": 500 }
    """
    planID = IntField(required=True, unique=True, db_field="planID")
    PlanName = StringField(required=False, max_length=255, db_field="PlanName")
    Description = StringField(required=False, db_field="Description")
    CoverageLim = FloatField(required=False, db_field="CoverageLim")
    BasePrice = FloatField(required=False, db_field="BasePrice")

    meta = {
        'collection': 'insurancePlans',
        'auto_create_index': False,
        'strict': False,
        'indexes': [
            {'fields': ['planID'], 'unique': True},
        ],
    }

    def __str__(self):
        return f"{getattr(self, 'PlanName', None) or 'Plan'} (ID: {self.planID})"


class Supervisor(Document):
    """
    Lightweight model for supervisors (managers) metadata stored in MongoDB
    collection 'supervisors'. We primarily need TeamID to determine which
    customers (and thus customer plans) fall under a manager's responsibility.

    Example document (flexible):
    { "UserID": 3, "TeamID": 42, "Name": "Jane Manager", ... }
    """
    UserID = IntField(required=True, db_field="UserID")
    TeamID = IntField(required=False, null=True, db_field="TeamID")

    meta = {
        'collection': 'supervisors',
        'auto_create_index': False,
        'strict': False,
        'indexes': [
            {'fields': ['UserID']},
            {'fields': ['TeamID']},
        ],
    }

    def __str__(self):
        return f"Supervisor UserID={self.UserID} TeamID={getattr(self, 'TeamID', None)}"


class Agent(Document):
    """
    Lightweight model to access the 'agents' collection.
    We only need TeamID linkage and a way to correlate to Users (via UserID) for
    manager-facing features like assignments.

    Example document (flexible):
    { "AgentID": 7, "UserID": 77, "TeamID": 1, "firstname": "Bob", ... }
    """
    AgentID = IntField(required=False, null=True, db_field="AgentID")
    UserID = IntField(required=False, null=True, db_field="userID")
    TeamID = IntField(required=False, null=True, db_field="TeamID")

    meta = {
        'collection': 'agents',
        'auto_create_index': False,
        'strict': False,
        'indexes': [
            {'fields': ['AgentID'], 'sparse': True},
            # Use the MongoEngine attribute name 'UserID' (db_field maps to 'userID')
            {'fields': ['UserID'], 'sparse': True},
            {'fields': ['TeamID'], 'sparse': True},
        ],
    }

    def __str__(self):
        aid = getattr(self, 'AgentID', None)
        uid = getattr(self, 'UserID', None)
        tid = getattr(self, 'TeamID', None)
        return f"Agent AgentID={aid} UserID={uid} TeamID={tid}"


class PlanAgentAssignment(Document):
    """
    Represents the assignment registry. Per requirements, this collection only
    stores the generated AssignmentID values.

    Example document:
    { "AssignmentID": 1001 }
    """
    AssignmentID = IntField(required=True, unique=True, db_field="AssignmentID")

    meta = {
        'collection': 'Plan_agent_Assignment',
        'auto_create_index': False,
        'strict': False,
        'indexes': [
            {'fields': ['AssignmentID'], 'unique': True},
        ],
    }


class User(Document):
    """
    Represents any user in the system (customers, agents, managers, etc.).
    This collection stores login credentials (username, passwordHash),
    their role (roleID), and their status (isEnabled).

    Example document:
    {
      "userid": 77,
      "username": "agent_bob",
      "email": "agent@example.com",
      "roleID": 2,  # Agent (equivalent to Manager for permissions)
      "managerID": 5,
      "isEnabled": true,
      "passwordHash": "argon2$..."
    }
    """
    userid = IntField(required=True, unique=True)
    username = StringField(required=True, max_length=100, unique=True)

    # Note: email is stored in the customers collection, not here.
    # Field retained for backward compatibility but should not be relied upon.
    email = StringField(required=False, max_length=255)
    roleID = IntField(required=True)
    passwordHash = StringField(required=True, max_length=255)
    isEnabled = BooleanField(default=True)
    managerID = IntField(required=False, null=True)
    # Password reset support
    resetToken = StringField(required=False, max_length=200, null=True)
    resetTokenExpiresAt = DateTimeField(required=False, null=True)

    meta = {
        'collection': 'users',
        # Use default MongoDB index names (e.g., userid_1) to avoid name conflicts
        'indexes': [
            {'fields': ['userid'], 'unique': True},
            {'fields': ['username'], 'unique': True},
            # Do not index email here; authoritative email lives in customers
            # {'fields': ['email'], 'unique': True, 'sparse': True},
            {'fields': ['managerID'], 'sparse': True},
        ],
    }

    def __str__(self):
        return f"{self.username}"

    # ---- Role linking helpers ----
    @property
    def role(self):
        """
        Returns the Role document linked to this user via roleID.
        If no matching role is found, returns None.
        """
        try:
            return Role.objects(roleID=self.roleID).first()
        except Exception:
            return None

    def set_role(self, role_or_id):
        """
        Convenience setter to assign role by Role document or numeric ID.

        Examples:
        - user.set_role(3)
        - user.set_role(Role.objects(roleID=3).first())
        """
        if role_or_id is None:
            self.roleID = None
            return
        if isinstance(role_or_id, Role):
            self.roleID = role_or_id.roleID
        else:
            # Assume it's an int-like ID
            self.roleID = int(role_or_id)

    @classmethod
    def hash_password(cls, password):
        """
        Hash password using Argon2 (via Django's make_password).
        """
        return make_password(password)

    def check_password(self, password):
        """
        Checks a given password against the stored hash.

        This method handles multiple password formats for legacy compatibility:
        1. Django hashes (argon2, pbkdf2, etc.): Verifies using Django's built-in checker.
        2. Legacy "salt:hash" format: Manually hashes and compares.
        3. Plaintext: Directly compares (for very old, unmigrated passwords).

        If a legacy or plaintext password matches, it automatically
        upgrades the hash to the modern Django format.
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
        # Invalidate any existing reset token once password is changed
        self.resetToken = None
        self.resetTokenExpiresAt = None

    # ---- Password reset helpers ----
    def issue_reset_token(self, ttl_minutes: int = 60) -> str:
        """
        Generate a secure token and set an expiry time.
        Returns the token.
        """
        token = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timedelta(minutes=ttl_minutes)
        self.resetToken = token
        # Store as naive UTC to be safe with MongoEngine; convert to naive UTC if timezone-aware
        if timezone.is_aware(expires_at):
            expires_at = expires_at.replace(tzinfo=None)
        self.resetTokenExpiresAt = expires_at
        self.save()
        return token

    def clear_reset_token(self):
        self.resetToken = None
        self.resetTokenExpiresAt = None
        self.save()

    def is_reset_token_valid(self, token: str) -> bool:
        if not token or not self.resetToken or token != self.resetToken:
            return False
        try:
            expires = self.resetTokenExpiresAt
            if expires is None:
                return False
            # Compare with current UTC naive time
            now = timezone.now()
            if timezone.is_aware(now):
                now = now.replace(tzinfo=None)
            return now <= expires
        except Exception:
            return False

    @property
    def role_name(self):
        """
        A helper property to get the user's role name (e.g., "admin")
        by looking up their roleID in the Roles collection.
        """
        try:
            role = self.role
            return role.RoleName if role else 'unknown'
        except Exception:
            return 'unknown'

    @property
    def role_dict(self):
        """
        Small dict useful for serialization.
        Provides both the legacy "RoleName" field and the preferred
        lowercase "role" for the role's name.
        Example: {"roleID": 3, "role": "agent", "RoleName": "agent"}
        """
        r = self.role
        return {
            "roleID": self.roleID,
            # Preferred key for JSON responses
            "role": getattr(r, "RoleName", None) if r else None,
            # Legacy key kept for backward compatibility
            "RoleName": getattr(r, "RoleName", None) if r else None,
        }


class Item(Document):
    """
    Represents an item that can be insured or part of a claim.
    Items can be generic catalog entries or, if CustomerID is set,
    can belong to a specific customer.

    Example document:
    {
      "ItemID": 10,
      "Name": "MacBook Pro 16in",
      "Description": "Silver, M3 Pro",
      "Value": 2500.00,
      "CustomerID": 1001
    }
    """
    ItemID = IntField(required=True, unique=True)
    Name = StringField(required=True, max_length=255)
    Description = StringField(required=False)
    CustomerID = IntField(required=False, null=True)
    Value = FloatField(required=False)
    CustomerPlanID = IntField(required=False, null=True)
    Category = StringField(required=False)
    EstimatedValue = StringField(required=False)
    PurchaseDate = StringField(required=False)  # stored as ISO string
    ImagePath1 = StringField(required=False)
    ImagePath2 = StringField(required=False)

    meta = {
        'collection': 'items',
        'indexes': [
            {'fields': ['ItemID'], 'unique': True},
            {'fields': ['CustomerID'], 'sparse': True},
            {'fields': ['CustomerPlanID'], 'sparse': True},
        ],
        'strict': False,
    }


class Policy(Document):
    """
    Represents an insurance policy.
    Tracks the policy's status (e.g., 'pending', 'approved', 'rejected')
    and links it to a customer.

    Example document:
    {
      "PolicyID": 901,
      "CustomerID": 1001,
      "Status": "pending",
      "CreatedAt": "2025-11-13T10:00:00Z",
      "UpdatedAt": "2025-11-13T10:00:00Z"
    }
    """
    PolicyID = IntField(required=True, unique=True)
    CustomerID = IntField(required=True)
    Status = StringField(required=True, choices=(
        'pending', 'approved', 'rejected'
    ), default='pending')
    CreatedAt = DateTimeField(default=datetime.utcnow)
    UpdatedAt = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'policies',
        'indexes': [
            {'fields': ['PolicyID'], 'unique': True},
            {'fields': ['CustomerID']},
            {'fields': ['Status']},
        ],
        'strict': False,
    }


class Claim(Document):
    """
    A claim submitted by a customer, typically assigned to an agent for review.
    Tracks the claim's status, amount, and which items are involved.

    Example document:
    {
      "ClaimID": 123,
      "CustomerID": 1001,
      "PolicyID": 901,
      "AssignedToUserID": 77,
      "Status": "submitted",
      "Reason": "Water damage to laptop",
      "Amount": 1500.00,
      "ItemIDs": [10],
      "CreatedAt": "2025-11-13T14:30:00Z",
      "UpdatedAt": "2025-11-13T14:30:00Z"
    }
    """
    ClaimID = IntField(required=True, unique=True)
    CustomerID = IntField(required=True)
    PolicyID = IntField(required=False, null=True)
    AssignedToUserID = IntField(required=False, null=True)
    Status = StringField(required=True, choices=(
        'submitted', 'in_review', 'accepted', 'rejected'
    ), default='submitted')
    Reason = StringField(required=False)
    Amount = FloatField(required=False)
    ItemIDs = ListField(IntField(), default=list)
    CreatedAt = DateTimeField(default=datetime.utcnow)
    UpdatedAt = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'claims',
        'indexes': [
            {'fields': ['ClaimID'], 'unique': True},
            {'fields': ['CustomerID']},
            {'fields': ['AssignedToUserID'], 'sparse': True},
            {'fields': ['Status']},
        ],
        'strict': False,
    }


class ClaimRecord(Document):
    """
    Represents a claim entry in the legacy claimedItems collection.
    Only core fields declared; strict=False allows extra fields to live in the document.
    """
    ClaimID = IntField(required=True, unique=True, db_field="ClaimID")
    ItemID = IntField(required=True, db_field="ItemID")
    CurrentStatusID = IntField(required=True, db_field="CurrentStatusID")
    LossDate = DateTimeField(required=False, db_field="LossDate")
    ClaimedValueAtTime = StringField(required=False, db_field="ClaimedValueAtTime")
    descriptionOfLoss = StringField(required=False, db_field="descriptionOfLoss")
    DateFiled = DateTimeField(required=False, db_field="DateFiled")

    meta = {
        'collection': 'claimedItems',
        'indexes': [
            {'fields': ['ClaimID'], 'unique': True},
            {'fields': ['ItemID']},
            {'fields': ['CurrentStatusID']},
        ],
        'strict': False,
        'auto_create_index': False,
    }


class ClaimWorkflowHistory(Document):
    """
    Logs actions taken on a claim.
    """
    HistoryID = IntField(required=True, unique=True, db_field="HistoryID")
    ClaimID = IntField(required=True, db_field="ClaimID")
    status = StringField(required=True, db_field="status")
    EmployeeName = StringField(required=False, db_field="EmployeeName")
    Timestamp = DateTimeField(required=False, db_field="Timestamp")
    Note = StringField(required=False, db_field="Note")

    meta = {
        'collection': 'claimWorkflowHistory',
        'indexes': [
            {'fields': ['HistoryID'], 'unique': True},
            {'fields': ['ClaimID']},
            {'fields': ['status']},
        ],
        'strict': False,
        'auto_create_index': False,
    }

    def __str__(self):
        return f"{self.ClaimID} - {self.status}"


class AuditLog(Document):
    """
    Logs sensitive actions performed by users for auditing purposes.
    Records who (ActorUserID) did what (Action) to what (TargetType/TargetID).

    Example document:
    {
      "LogID": 1678886400123,
      "ActorUserID": 5,
      "Action": "claim_approve",
      "TargetType": "claim",
      "TargetID": "123",
      "Details": { "newStatus": "approved", "reason": "Valid." },
      "CreatedAt": "2025-11-13T15:00:00Z"
    }
    """
    LogID = IntField(required=True, unique=True)
    ActorUserID = IntField(required=True)
    Action = StringField(required=True)
    TargetType = StringField(required=True)
    TargetID = StringField(required=True)
    Details = DictField(required=False)
    CreatedAt = DateTimeField(default=datetime.utcnow)

    meta = {
        'collection': 'audit_logs',
        'indexes': [
            {'fields': ['LogID'], 'unique': True},
            {'fields': ['ActorUserID']},
            {'fields': ['TargetType']},
            {'fields': ['CreatedAt']},
        ],
        'strict': False,
    }
