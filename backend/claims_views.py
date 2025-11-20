from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from users.models import User, Claim, Item, Policy, AuditLog, Customer
from datetime import datetime


def _now_utc():
    """Returns the current datetime in UTC."""
    return datetime.utcnow()


def _new_log_id() -> int:
    """Generates a unique integer ID based on the current millisecond epoch."""
    return int(datetime.utcnow().timestamp() * 1000)


def _current_user(request):
    """
    Identifies the current user from the 'userid' header.
    Returns a User object or None if not found or on error.

    Backward compatibility: still accepts legacy 'X-User-ID' if present.
    """
    try:
        # Preferred new header name
        uid = (
            request.headers.get("userid")
            or request.META.get("HTTP_USERID")
            # Legacy support
            or request.headers.get("X-User-ID")
            or request.META.get("HTTP_X_USER_ID")
        )
        if not uid:
            return None
        user = User.objects(userid=int(uid)).first()
        return user
    except Exception:
        return None


def _require_user(request):
    """
    Ensures a valid and enabled user is authenticated via the 'userid' header.
    Returns (user, None) on success.
    Returns (None, Response) on failure.

    Failure JSON Output (401 Unauthorized):
    {"error": "Unauthorized: missing or invalid userid"}

    Failure JSON Output (403 Forbidden):
    {"error": "Account disabled"}
    """
    user = _current_user(request)
    if not user:
        return None, Response({"error": "Unauthorized: missing or invalid userid"},
                              status=status.HTTP_401_UNAUTHORIZED)
    if not user.isEnabled:
        return None, Response({"error": "Account disabled"}, status=status.HTTP_403_FORBIDDEN)
    return user, None


def _is_admin(user: User) -> bool:
    """Checks if the user has an 'admin' or 'superuser' role."""
    return (user.role_name or "").lower() in ("admin", "superuser")


def _is_manager(user: User) -> bool:
    """Checks if the user has a 'manager', 'admin', or 'superuser' role."""
    role = (user.role_name or "").lower()
    return role in ("manager", "admin", "superuser")


def _is_agent(user: User) -> bool:
    """Checks if the user has an 'agent', 'employee', 'manager', 'admin', or 'superuser' role."""
    role = (user.role_name or "").lower()
    return role in ("agent", "employee", "manager", "admin", "superuser")


# ---- RoleID-based access helpers (authoritative) ----
def _has_full_access(user: User) -> bool:
    """RoleIDs 3 and 4 can access all information (read)."""
    try:
        return int(getattr(user, "roleID", 0)) in (3, 4)
    except Exception:
        return False


def _is_assigned_clients_only(user: User) -> bool:
    """RoleID 2 can access information of their assigned clients (read)."""
    try:
        return int(getattr(user, "roleID", 0)) == 2
    except Exception:
        return False


def _is_self_only(user: User) -> bool:
    """RoleID 1 can access only their own policies and information (read)."""
    try:
        return int(getattr(user, "roleID", 0)) == 1
    except Exception:
        return False


def _own_customer_ids(user: User):
    """Return a set of CustomerID(s) owned by this user (via customers.UserID == user.userid)."""
    try:
        custs = Customer.objects(UserID=user.userid)
        return {c.CustomerID for c in custs}
    except Exception:
        return set()


def _assigned_customer_ids(user: User):
    """
    Return a set of CustomerID(s) assigned to this user. We infer assignment via
    Claim.AssignedToUserID == user.userid.
    """
    try:
        claims = Claim.objects(AssignedToUserID=user.userid)
        return {c.CustomerID for c in claims}
    except Exception:
        return set()


class AgentClaimsDashboard(APIView):
    """
    Provides an agent-specific view to list all claims assigned to the current user.

    GET:
    - Requires: Agent-level permissions ('agent', 'employee', 'manager', 'admin', 'superuser').
    - Success JSON Output (200 OK):
      {
        "claims": [
          {
            "ClaimID": 123,
            "CustomerID": 456,
            "PolicyID": 789,
            "Status": "submitted",
            "Amount": 1500.00,
            "Reason": "Water damage",
            "ItemIDs": [10, 11],
            "CreatedAt": "2025-11-13T14:30:00Z",
            "UpdatedAt": "2025-11-13T14:30:00Z"
          }
        ]
      }
    - Failure JSON Output (403 Forbidden):
      {"error": "Forbidden"}
    - Failure JSON Output (500 Internal Server Error):
      {"error": "database error description"}
    """

    def get(self, request):
        user, err = _require_user(request)
        if err:
            return err
        if not _is_agent(user):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        try:
            claims = Claim.objects(AssignedToUserID=user.userid)
            data = [
                {
                    "ClaimID": c.ClaimID,
                    "CustomerID": c.CustomerID,
                    "PolicyID": c.PolicyID,
                    "Status": c.Status,
                    "Amount": c.Amount,
                    "Reason": c.Reason,
                    "ItemIDs": list(c.ItemIDs or []),
                    "CreatedAt": c.CreatedAt,
                    "UpdatedAt": c.UpdatedAt,
                }
                for c in claims
            ]
            return Response({"claims": data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ClaimDetailView(APIView):
    """
    Handles CRUD operations for a single claim (identified by claim_id).

    GET:
    - Retrieves claim details, plus the customer's previous claims and items.
    - Permissions: Admin/Manager (any) or the assigned Agent.
    - Success JSON Output (200 OK):
      {
        "claim": {
          "ClaimID": 123,
          "CustomerID": 456,
          "PolicyID": 789,
          "AssignedToUserID": 77,
          "Status": "submitted",
          "Amount": 1500.00,
          "Reason": "Water damage",
          "ItemIDs": [10, 11],
          "CreatedAt": "2025-11-13T14:30:00Z",
          "UpdatedAt": "2025-11-13T14:30:00Z"
        },
        "previousClaims": [
          {
            "ClaimID": 101,
            "Status": "accepted",
            "Amount": 250.00,
            "CreatedAt": "2024-05-10T10:00:00Z"
          }
        ],
        "customerItems": [
          {
            "ItemID": 10,
            "Name": "Laptop",
            "Description": "15in MacBook Pro",
            "Value": 2000.00
          }
        ]
      }
    - Failure JSON Output (404 Not Found):
      {"error": "Claim not found"}
    - Failure JSON Output (403 Forbidden):
      {"error": "Forbidden"}

    PUT / PATCH:
    - Updates a claim using the provided JSON body.
    - Permissions: Admin/Manager (any) or the assigned Agent.
    - Success JSON Output (200 OK):
      {"ok": true}
    - Failure JSON Output (404 Not Found):
      {"error": "Claim not found"}
    - Failure JSON Output (403 Forbidden):
      {"error": "Forbidden"}
    - Failure JSON Output (400 Bad Request):
      {"error": "Invalid value for {field}"}

    DELETE:
    - Deletes a claim.
    - Permissions: Admin only.
    - Success JSON Output (200 OK):
      {"ok": true}
    - Failure JSON Output (404 Not Found):
      {"error": "Claim not found"}
    - Failure JSON Output (403 Forbidden):
      {"error": "Forbidden"}
    """

    def get(self, request, claim_id: int):
        user, err = _require_user(request)
        if err:
            return err
        try:
            claim = Claim.objects(ClaimID=int(claim_id)).first()
            if not claim:
                return Response({"error": "Claim not found"}, status=status.HTTP_404_NOT_FOUND)

            if not (_is_manager(user) or _is_admin(user) or (claim.AssignedToUserID == user.userid)):
                return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

            previous_claims = Claim.objects(CustomerID=claim.CustomerID, ClaimID__ne=claim.ClaimID)
            customer_items = Item.objects(CustomerID=claim.CustomerID)

            result = {
                "claim": {
                    "ClaimID": claim.ClaimID,
                    "CustomerID": claim.CustomerID,
                    "PolicyID": claim.PolicyID,
                    "AssignedToUserID": claim.AssignedToUserID,
                    "Status": claim.Status,
                    "Amount": claim.Amount,
                    "Reason": claim.Reason,
                    "ItemIDs": list(claim.ItemIDs or []),
                    "CreatedAt": claim.CreatedAt,
                    "UpdatedAt": claim.UpdatedAt,
                },
                "previousClaims": [
                    {
                        "ClaimID": c.ClaimID,
                        "Status": c.Status,
                        "Amount": c.Amount,
                        "CreatedAt": c.CreatedAt,
                    }
                    for c in previous_claims
                ],
                "customerItems": [
                    {
                        "ItemID": i.ItemID,
                        "Name": i.Name,
                        "Description": getattr(i, "Description", None),
                        "Value": getattr(i, "Value", None),
                    }
                    for i in customer_items
                ],
            }
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, claim_id: int):
        user, err = _require_user(request)
        if err:
            return err
        try:
            claim = Claim.objects(ClaimID=int(claim_id)).first()
            if not claim:
                return Response({"error": "Claim not found"}, status=status.HTTP_404_NOT_FOUND)
            if not (_is_manager(user) or _is_admin(user) or (claim.AssignedToUserID == user.userid)):
                return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

            updatable = {
                "CustomerID": int,
                "PolicyID": (lambda v: int(v) if v is not None else None),
                "AssignedToUserID": (lambda v: int(v) if v is not None else None),
                "Status": str,
                "Reason": (lambda v: v),
                "Amount": (lambda v: float(v) if v is not None else None),
                "ItemIDs": (lambda v: list(v) if isinstance(v, (list, tuple)) else []),
            }
            payload = request.data or {}
            for field, caster in updatable.items():
                if field in payload:
                    val = payload.get(field)
                    try:
                        val = caster(val)
                    except Exception:
                        return Response({"error": f"Invalid value for {field}"}, status=status.HTTP_400_BAD_REQUEST)
                    setattr(claim, field, val)
            claim.UpdatedAt = _now_utc()
            claim.save()

            AuditLog(
                LogID=_new_log_id(),
                ActorUserID=user.userid,
                Action="claim_update",
                TargetType="claim",
                TargetID=str(claim.ClaimID),
                Details=None,
                CreatedAt=_now_utc(),
            ).save()

            return Response({"ok": True}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def patch(self, request, claim_id: int):
        return self.put(request, claim_id)

    def delete(self, request, claim_id: int):
        user, err = _require_user(request)
        if err:
            return err
        if not _is_admin(user):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            claim = Claim.objects(ClaimID=int(claim_id)).first()
            if not claim:
                return Response({"error": "Claim not found"}, status=status.HTTP_404_NOT_FOUND)
            cid = claim.ClaimID
            claim.delete()
            AuditLog(
                LogID=_new_log_id(),
                ActorUserID=user.userid,
                Action="claim_delete",
                TargetType="claim",
                TargetID=str(cid),
                Details=None,
                CreatedAt=_now_utc(),
            ).save()
            return Response({"ok": True}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ClaimDecisionView(APIView):
    """
    Handles the action of accepting or rejecting a specific claim.

    POST:
    - Requires: Agent-level permissions. Agents can only decide on their
      assigned claims; Managers/Admins can decide on any.
    - Input JSON Body:
      {"decision": "accept"|"reject", "reason": "Optional reason text"}
    - Success JSON Output (200 OK):
      {"ok": true, "newStatus": "accepted"}
    - Failure JSON Output (400 Bad Request):
      {"error": "Invalid decision"}
    - Failure JSON Output (404 Not Found):
      {"error": "Claim not found"}
    - Failure JSON Output (403 Forbidden):
      {"error": "Forbidden"}
    """

    def post(self, request, claim_id: int):
        user, err = _require_user(request)
        if err:
            return err
        if not _is_agent(user):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        decision = (request.data.get("decision") or "").strip().lower()
        reason = request.data.get("reason")
        if decision not in ("accept", "reject"):
            return Response({"error": "Invalid decision"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            claim = Claim.objects(ClaimID=int(claim_id)).first()
            if not claim:
                return Response({"error": "Claim not found"}, status=status.HTTP_404_NOT_FOUND)
            if claim.AssignedToUserID not in (None, user.userid) and not _is_manager(user) and not _is_admin(user):
                return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

            claim.Status = "accepted" if decision == "accept" else "rejected"
            claim.Reason = reason or claim.Reason
            claim.UpdatedAt = _now_utc()
            claim.save()

            AuditLog(
                LogID=_new_log_id(),
                ActorUserID=user.userid,
                Action=f"claim_{decision}",
                TargetType="claim",
                TargetID=str(claim.ClaimID),
                Details={"reason": reason} if reason else None,
                CreatedAt=_now_utc(),
            ).save()

            return Response({"ok": True, "newStatus": claim.Status}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ManagerEmployeesView(APIView):
    """
    Provides a manager-specific view to list their direct employees.

    GET:
    - Requires: Manager-level permissions ('manager', 'admin', 'superuser').
    - Success JSON Output (200 OK):
      {
        "employees": [
          {
            "userid": 77,
            "username": "agent_bob",
            "email": "bob@example.com",
            "role": "agent",
            "isEnabled": true
          }
        ]
      }
    - Failure JSON Output (403 Forbidden):
      {"error": "Forbidden"}
    """

    def get(self, request):
        user, err = _require_user(request)
        if err:
            return err
        if not _is_manager(user):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        try:
            employees = User.objects(managerID=user.userid)
            data = [
                {
                    "userid": u.userid,
                    "username": u.username,
                    "email": getattr(u, "email", None),
                    "role": u.role_name,
                    "isEnabled": u.isEnabled,
                }
                for u in employees
            ]
            return Response({"employees": data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ManagerPendingPoliciesView(APIView):
    """
    Provides a manager-specific view to list all policies awaiting approval.

    GET:
    - Requires: Manager-level permissions ('manager', 'admin', 'superuser').
    - Success JSON Output (200 OK):
      {
        "policies": [
          {
            "PolicyID": 901,
            "CustomerID": 456,
            "Status": "pending",
            "CreatedAt": "2025-11-13T14:30:00Z"
          }
        ]
      }
    - Failure JSON Output (403 Forbidden):
      {"error": "Forbidden"}
    """

    def get(self, request):
        user, err = _require_user(request)
        if err:
            return err
        if not _is_manager(user):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        try:
            policies = Policy.objects(Status="pending")
            data = [
                {
                    "PolicyID": p.PolicyID,
                    "CustomerID": p.CustomerID,
                    "Status": p.Status,
                    "CreatedAt": p.CreatedAt,
                }
                for p in policies
            ]
            return Response({"policies": data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ManagerPolicyDecisionView(APIView):
    """
    Handles the action of approving or rejecting a specific pending policy.

    POST:
    - Requires: Manager-level permissions.
    - Input JSON Body:
      {"decision": "approve"|"reject"}
    - Success JSON Output (200 OK):
      {"ok": true, "newStatus": "approved"}
    - Failure JSON Output (400 Bad Request):
      {"error": "Invalid decision"}
    - Failure JSON Output (404 Not Found):
      {"error": "Policy not found"}
    - Failure JSON Output (400 Bad Request):
      {"error": "Policy is not pending"}
    """

    def post(self, request, policy_id: int):
        user, err = _require_user(request)
        if err:
            return err
        if not _is_manager(user):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        decision = (request.data.get("decision") or "").strip().lower()
        if decision not in ("approve", "reject"):
            return Response({"error": "Invalid decision"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            policy = Policy.objects(PolicyID=int(policy_id)).first()
            if not policy:
                return Response({"error": "Policy not found"}, status=status.HTTP_404_NOT_FOUND)
            if policy.Status != "pending":
                return Response({"error": "Policy is not pending"}, status=status.HTTP_400_BAD_REQUEST)

            policy.Status = "approved" if decision == "approve" else "rejected"
            policy.UpdatedAt = _now_utc()
            policy.save()

            AuditLog(
                LogID=_new_log_id(),
                ActorUserID=user.userid,
                Action=f"policy_{decision}",
                TargetType="policy",
                TargetID=str(policy.PolicyID),
                Details=None,
                CreatedAt=_now_utc(),
            ).save()

            return Response({"ok": True, "newStatus": policy.Status}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminAuditLogView(APIView):
    """
    Provides an admin-only view to list the 500 most recent audit log entries.

    GET:
    - Requires: Admin-level permissions ('admin', 'superuser').
    - Success JSON Output (200 OK):
      {
        "logs": [
          {
            "LogID": 1678886400123,
            "ActorUserID": 1,
            "Action": "claim_update",
            "TargetType": "claim",
            "TargetID": "123",
            "Details": {"reason": "Updated amount"},
            "CreatedAt": "2025-11-13T14:30:00Z"
          }
        ]
      }
    - Failure JSON Output (403 Forbidden):
      {"error": "Forbidden"}
    """

    def get(self, request):
        user, err = _require_user(request)
        if err:
            return err
        if not _is_admin(user):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            logs = AuditLog.objects.order_by('-CreatedAt')[:500]
            data = [
                {
                    "LogID": l.LogID,
                    "ActorUserID": l.ActorUserID,
                    "Action": l.Action,
                    "TargetType": l.TargetType,
                    "TargetID": l.TargetID,
                    "Details": getattr(l, 'Details', None),
                    "CreatedAt": l.CreatedAt,
                }
                for l in logs
            ]
            return Response({"logs": data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ClaimListCreateView(APIView):
    """
    Handles listing and creation of claims.

    GET:
    - Lists claims. Admin/Manager users see all claims.
    - Agents see only claims assigned to them.
    - Success JSON Output (200 OK):
      {
        "claims": [
          {
            "ClaimID": 123,
            "CustomerID": 456,
            "PolicyID": 789,
            "AssignedToUserID": 77,
            "Status": "submitted",
            "Amount": 1500.00,
            "Reason": "Water damage",
            "ItemIDs": [10, 11],
            "CreatedAt": "2025-11-13T14:30:00Z",
            "UpdatedAt": "2025-11-13T14:30:00Z"
          }
        ]
      }

    POST:
    - Creates a new claim.
    - Requires: Agent-level permissions.
    - Input JSON Body (ClaimID and CustomerID are required):
      {
        "ClaimID": 124,
        "CustomerID": 456,
        "PolicyID": 789,
        "AssignedToUserID": 77,
        "Status": "submitted",
        "Reason": "New claim",
        "Amount": 500.00,
        "ItemIDs": [12]
      }
    - Success JSON Output (201 Created):
      {"created": true, "ClaimID": 124}
    - Failure JSON Output (400 Bad Request):
      {"error": "Missing field: ClaimID"}
    - Failure JSON Output (409 Conflict):
      {"error": "ClaimID already exists"}
    - Failure JSON Output (403 Forbidden):
      {"error": "Forbidden"}
    """

    def get(self, request):
        user, err = _require_user(request)
        if err:
            return err
        try:
            q = {}
            if _is_manager(user) or _is_admin(user):
                pass
            else:
                q["AssignedToUserID"] = user.userid
            claims = Claim.objects(**q)
            data = [
                {
                    "ClaimID": c.ClaimID,
                    "CustomerID": c.CustomerID,
                    "PolicyID": c.PolicyID,
                    "AssignedToUserID": c.AssignedToUserID,
                    "Status": c.Status,
                    "Amount": c.Amount,
                    "Reason": c.Reason,
                    "ItemIDs": list(c.ItemIDs or []),
                    "CreatedAt": c.CreatedAt,
                    "UpdatedAt": c.UpdatedAt,
                }
                for c in claims
            ]
            return Response({"claims": data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        user, err = _require_user(request)
        if err:
            return err
        if not _is_agent(user):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            payload = request.data or {}
            required = ["ClaimID", "CustomerID"]
            for r in required:
                if r not in payload:
                    return Response({"error": f"Missing field: {r}"}, status=status.HTTP_400_BAD_REQUEST)
            claim = Claim(
                ClaimID=int(payload["ClaimID"]),
                CustomerID=int(payload["CustomerID"]),
                PolicyID=int(payload["PolicyID"]) if payload.get("PolicyID") is not None else None,
                AssignedToUserID=int(payload.get("AssignedToUserID") or user.userid),
                Status=str(payload.get("Status") or "submitted"),
                Reason=payload.get("Reason"),
                Amount=float(payload.get("Amount")) if payload.get("Amount") is not None else None,
                ItemIDs=list(payload.get("ItemIDs") or []),
                CreatedAt=_now_utc(),
                UpdatedAt=_now_utc(),
            )
            if Claim.objects(ClaimID=claim.ClaimID).first():
                return Response({"error": "ClaimID already exists"}, status=status.HTTP_409_CONFLICT)
            claim.save()
            AuditLog(
                LogID=_new_log_id(),
                ActorUserID=user.userid,
                Action="claim_create",
                TargetType="claim",
                TargetID=str(claim.ClaimID),
                Details=None,
                CreatedAt=_now_utc(),
            ).save()
            return Response({"created": True, "ClaimID": claim.ClaimID}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ItemListCreateView(APIView):
    """
    Handles listing all items and creating new items.

    GET:
    - Lists all items.
    - Requires: Any authenticated user.
    - Success JSON Output (200 OK):
      {
        "items": [
          {
            "ItemID": 10,
            "Name": "Laptop",
            "Description": "15in MacBook Pro",
            "CustomerID": 456,
            "Value": 2000.00
          }
        ]
      }

    POST:
    - Creates a new item.
    - Requires: Manager-level permissions.
    - Input JSON Body (ItemID and Name are required):
      {
        "ItemID": 11,
        "Name": "Camera",
        "Description": "DSLR Camera",
        "CustomerID": 456,
        "Value": 800.00
      }
    - Success JSON Output (201 Created):
      {"created": true, "ItemID": 11}
    - Failure JSON Output (403 Forbidden):
      {"error": "Forbidden"}
    - Failure JSON Output (400 Bad Request):
      {"error": "Missing field: ItemID"}
    - Failure JSON Output (409 Conflict):
      {"error": "ItemID already exists"}
    """

    def get(self, request):
        user, err = _require_user(request)
        if err:
            return err
        try:
            items = Item.objects
            data = [
                {
                    "ItemID": i.ItemID,
                    "Name": i.Name,
                    "Description": getattr(i, "Description", None),
                    "CustomerID": getattr(i, "CustomerID", None),
                    "Value": getattr(i, "Value", None),
                }
                for i in items
            ]
            return Response({"items": data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        user, err = _require_user(request)
        if err:
            return err
        if not (_is_manager(user) or _is_admin(user)):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            payload = request.data or {}
            required = ["ItemID", "Name"]
            for r in required:
                if r not in payload:
                    return Response({"error": f"Missing field: {r}"}, status=status.HTTP_400_BAD_REQUEST)
            item = Item(
                ItemID=int(payload["ItemID"]),
                Name=str(payload["Name"]),
                Description=payload.get("Description"),
                CustomerID=int(payload["CustomerID"]) if payload.get("CustomerID") is not None else None,
                Value=float(payload.get("Value")) if payload.get("Value") is not None else None,
            )
            if Item.objects(ItemID=item.ItemID).first():
                return Response({"error": "ItemID already exists"}, status=status.HTTP_409_CONFLICT)
            item.save()
            AuditLog(
                LogID=_new_log_id(),
                ActorUserID=user.userid,
                Action="item_create",
                TargetType="item",
                TargetID=str(item.ItemID),
                Details=None,
                CreatedAt=_now_utc(),
            ).save()
            return Response({"created": True, "ItemID": item.ItemID}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ItemDetailView(APIView):
    """
    Handles CRUD operations for a single item (identified by item_id).

    GET:
    - Retrieves details for a specific item.
    - Permissions: Any authenticated user.
    - Success JSON Output (200 OK):
      {
        "ItemID": 10,
        "Name": "Laptop",
        "Description": "15in MacBook Pro",
        "CustomerID": 456,
        "Value": 2000.00
      }
    - Failure JSON Output (404 Not Found):
      {"error": "Item not found"}

    PUT / PATCH:
    - Updates an item using the provided JSON body.
    - Permissions: Manager-level.
    - Success JSON Output (200 OK):
      {"ok": true}
    - Failure JSON Output (404 Not Found):
      {"error": "Item not found"}
    - Failure JSON Output (403 Forbidden):
      {"error": "Forbidden"}

    DELETE:
    - Deletes an item.
    - Permissions: Manager-level.
    - Success JSON Output (200 OK):
      {"ok": true}
    - Failure JSON Output (404 Not Found):
      {"error": "Item not found"}
    - Failure JSON Output (403 Forbidden):
      {"error": "Forbidden"}
    """

    def get(self, request, item_id: int):
        user, err = _require_user(request)
        if err:
            return err
        try:
            i = Item.objects(ItemID=int(item_id)).first()
            if not i:
                return Response({"error": "Item not found"}, status=status.HTTP_404_NOT_FOUND)
            data = {
                "ItemID": i.ItemID,
                "Name": i.Name,
                "Description": getattr(i, "Description", None),
                "CustomerID": getattr(i, "CustomerID", None),
                "Value": getattr(i, "Value", None),
            }
            return Response(data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, item_id: int):
        user, err = _require_user(request)
        if err:
            return err
        if not (_is_manager(user) or _is_admin(user)):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            i = Item.objects(ItemID=int(item_id)).first()
            if not i:
                return Response({"error": "Item not found"}, status=status.HTTP_404_NOT_FOUND)
            payload = request.data or {}
            if "Name" in payload:
                i.Name = str(payload["Name"]) if payload["Name"] is not None else i.Name
            if "Description" in payload:
                i.Description = payload.get("Description")
            if "CustomerID" in payload:
                i.CustomerID = int(payload["CustomerID"]) if payload["CustomerID"] is not None else None
            if "Value" in payload:
                i.Value = float(payload["Value"]) if payload["Value"] is not None else None
            i.save()
            AuditLog(
                LogID=_new_log_id(),
                ActorUserID=user.userid,
                Action="item_update",
                TargetType="item",
                TargetID=str(i.ItemID),
                Details=None,
                CreatedAt=_now_utc(),
            ).save()
            return Response({"ok": True}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def patch(self, request, item_id: int):
        return self.put(request, item_id)

    def delete(self, request, item_id: int):
        user, err = _require_user(request)
        if err:
            return err
        if not (_is_manager(user) or _is_admin(user)):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            i = Item.objects(ItemID=int(item_id)).first()
            if not i:
                return Response({"error": "Item not found"}, status=status.HTTP_404_NOT_FOUND)
            iid = i.ItemID
            i.delete()
            AuditLog(
                LogID=_new_log_id(),
                ActorUserID=user.userid,
                Action="item_delete",
                TargetType="item",
                TargetID=str(iid),
                Details=None,
                CreatedAt=_now_utc(),
            ).save()
            return Response({"ok": True}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PolicyListCreateView(APIView):
    """
    Handles listing and creation of policies.

    GET:
    - Lists all policies.
    - Requires: Manager-level permissions.
    - Success JSON Output (200 OK):
      {
        "policies": [
          {
            "PolicyID": 901,
            "CustomerID": 456,
            "Status": "pending",
            "CreatedAt": "2025-11-13T14:30:00Z",
            "UpdatedAt": "2025-11-13T14:30:00Z"
          }
        ]
      }

    POST:
    - Creates a new policy.
    - Requires: Manager-level permissions.
    - Input JSON Body (PolicyID and CustomerID are required):
      {
        "PolicyID": 902,
        "CustomerID": 457,
        "Status": "pending"
      }
    - Success JSON Output (201 Created):
      {"created": true, "PolicyID": 902}
    - Failure JSON Output (403 Forbidden):
      {"error": "Forbidden"}
    - Failure JSON Output (400 Bad Request):
      {"error": "Missing field: PolicyID"}
    - Failure JSON Output (409 Conflict):
      {"error": "PolicyID already exists"}
    """

    def get(self, request):
        user, err = _require_user(request)
        if err:
            return err
        if not (_is_manager(user) or _is_admin(user)):
            return Response({"error": "Forbidden"}, status=status.HTTP_4D03_FORBIDDEN)
        try:
            policies = Policy.objects
            data = [
                {
                    "PolicyID": p.PolicyID,
                    "CustomerID": p.CustomerID,
                    "Status": p.Status,
                    "CreatedAt": p.CreatedAt,
                    "UpdatedAt": p.UpdatedAt,
                }
                for p in policies
            ]
            return Response({"policies": data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        user, err = _require_user(request)
        if err:
            return err
        if not (_is_manager(user) or _is_admin(user)):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            payload = request.data or {}
            required = ["PolicyID", "CustomerID"]
            for r in required:
                if r not in payload:
                    return Response({"error": f"Missing field: {r}"}, status=status.HTTP_400_BAD_REQUEST)
            policy = Policy(
                PolicyID=int(payload["PolicyID"]),
                CustomerID=int(payload["CustomerID"]),
                Status=str(payload.get("Status") or "pending"),
                CreatedAt=_now_utc(),
                UpdatedAt=_now_utc(),
            )
            if Policy.objects(PolicyID=policy.PolicyID).first():
                return Response({"error": "PolicyID already exists"}, status=status.HTTP_409_CONFLICT)
            policy.save()
            AuditLog(
                LogID=_new_log_id(),
                ActorUserID=user.userid,
                Action="policy_create",
                TargetType="policy",
                TargetID=str(policy.PolicyID),
                Details=None,
                CreatedAt=_now_utc(),
            ).save()
            return Response({"created": True, "PolicyID": policy.PolicyID}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PolicyDetailView(APIView):
    """
    Handles CRUD operations for a single policy (identified by policy_id).

    GET:
    - Retrieves details for a specific policy.
    - Permissions: Manager-level.
    - Success JSON Output (200 OK):
      {
        "PolicyID": 901,
        "CustomerID": 456,
        "Status": "pending",
        "CreatedAt": "2025-11-13T14:30:00Z",
        "UpdatedAt": "2025-11-13T14:30:00Z"
      }
    - Failure JSON Output (404 Not Found):
      {"error": "Policy not found"}
    - Failure JSON Output (403 Forbidden):
      {"error": "Forbidden"}

    PUT / PATCH:
    - Updates a policy using the provided JSON body.
    - Permissions: Manager-level.
    - Success JSON Output (200 OK):
      {"ok": true}
    - Failure JSON Output (404 Not Found):
      {"error": "Policy not found"}
    - Failure JSON Output (403 Forbidden):
      {"error": "Forbidden"}

    DELETE:
    - Deletes a policy.
    - Permissions: Admin only.
    - Success JSON Output (200 OK):
      {"ok": true}
    - Failure JSON Output (404 Not Found):
      {"error": "Policy not found"}
    - Failure JSON Output (403 Forbidden):
      {"error": "Forbidden"}
    """

    def get(self, request, policy_id: int):
        user, err = _require_user(request)
        if err:
            return err
        if not (_is_manager(user) or _is_admin(user)):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            p = Policy.objects(PolicyID=int(policy_id)).first()
            if not p:
                return Response({"error": "Policy not found"}, status=status.HTTP_404_NOT_FOUND)
            data = {
                "PolicyID": p.PolicyID,
                "CustomerID": p.CustomerID,
                "Status": p.Status,
                "CreatedAt": p.CreatedAt,
                "UpdatedAt": p.UpdatedAt,
            }
            return Response(data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, policy_id: int):
        user, err = _require_user(request)
        if err:
            return err
        if not (_is_manager(user) or _is_admin(user)):
            return Response({"error": "Forbidden"}, status=status.HTTP_4D03_FORBIDDEN)
        try:
            p = Policy.objects(PolicyID=int(policy_id)).first()
            if not p:
                return Response({"error": "Policy not found"}, status=status.HTTP_404_NOT_FOUND)
            payload = request.data or {}
            if "CustomerID" in payload:
                p.CustomerID = int(payload["CustomerID"]) if payload["CustomerID"] is not None else p.CustomerID
            if "Status" in payload:
                p.Status = str(payload["Status"]) if payload["Status"] is not None else p.Status
            p.UpdatedAt = _now_utc()
            p.save()
            AuditLog(
                LogID=_new_log_id(),
                ActorUserID=user.userid,
                Action="policy_update",
                TargetType="policy",
                TargetID=str(p.PolicyID),
                Details=None,
                CreatedAt=_now_utc(),
            ).save()
            return Response({"ok": True}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def patch(self, request, policy_id: int):
        return self.put(request, policy_id)

    def delete(self, request, policy_id: int):
        user, err = _require_user(request)
        if err:
            return err
        if not _is_admin(user):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            p = Policy.objects(PolicyID=int(policy_id)).first()
            if not p:
                return Response({"error": "Policy not found"}, status=status.HTTP_404_NOT_FOUND)
            pid = p.PolicyID
            p.delete()
            AuditLog(
                LogID=_new_log_id(),
                ActorUserID=user.userid,
                Action="policy_delete",
                TargetType="policy",
                TargetID=str(pid),
                Details=None,
                CreatedAt=_now_utc(),
            ).save()
            return Response({"ok": True}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)