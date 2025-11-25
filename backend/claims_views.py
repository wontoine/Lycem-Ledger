from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from users.models import User, Claim, Item, Policy, AuditLog, Customer
from datetime import datetime


def _now_utc():
    """
    Just a helper to get the current time in UTC so we don't have timezone headaches.

    Output: datetime object (UTC)
    """
    return datetime.utcnow()


def _new_log_id() -> int:
    """
    Creates a unique ID number based on the current time (milliseconds).
    Used for logs or ID generation so we don't get duplicates.

    Output: int (e.g., 1678886400123)
    """
    return int(datetime.utcnow().timestamp() * 1000)


def _current_user(request):
    """
    Tries to figure out who is making the request by looking at the headers.
    It checks 'userid' first, but also looks for 'X-User-ID' just in case we are using old code.

    Input: request object
    Output: User object (if found) OR None (if they don't exist or header is missing)
    """
    try:
        # Check the new header style first, then fallback to legacy
        uid = (
                request.headers.get("userid")
                or request.META.get("HTTP_USERID")
                or request.headers.get("X-User-ID")
                or request.META.get("HTTP_X_USER_ID")
        )
        if not uid:
            return None
        # Grab the user from the database
        user = User.objects(userid=int(uid)).first()
        return user
    except Exception:
        return None


def _require_user(request):
    """
    The bouncer function. It checks if the user is logged in AND if their account is actually enabled.

    Input: request object

    Output (Success): (User object, None)
    Output (Failure - Not logged in): (None, Response 401)
       -> {"error": "Unauthorized: missing or invalid userid"}
    Output (Failure - Account disabled): (None, Response 403)
       -> {"error": "Account disabled"}
    """
    user = _current_user(request)
    if not user:
        return None, Response({"error": "Unauthorized: missing or invalid userid"},
                              status=status.HTTP_401_UNAUTHORIZED)
    if not user.isEnabled:
        return None, Response({"error": "Account disabled"}, status=status.HTTP_403_FORBIDDEN)
    return user, None


def _is_admin(user: User) -> bool:
    """
    Checks if the user is a superuser or admin.
    Input: User object
    Output: True/False
    """
    return (user.role_name or "").lower() in ("admin", "superuser")


def _is_manager(user: User) -> bool:
    """
    Checks if the user has manager privileges (includes admins).
    Input: User object
    Output: True/False
    """
    # Accept either by resolved role name OR by numeric roleID == 3
    try:
        role_id = int(getattr(user, "roleID", 0))
    except Exception:
        role_id = 0
    # Only Supervisors (3) are managers; Agents (2) are not
    if role_id == 3:
        return True

    role = (user.role_name or "").lower()
    # Recognize supervisor and admin roles by name. Do NOT treat agent as manager.
    # Role names in the DB are: customer, agent, supervisor, admin
    return role in ("supervisor", "admin", "superuser")


def _is_agent(user: User) -> bool:
    """
    Checks if the user is staff (agent, employee, manager, etc.).
    Input: User object
    Output: True/False
    """
    role = (user.role_name or "").lower()
    # Treat supervisor as staff as well (but not as manager unless roleID==3)
    return role in ("agent", "employee", "manager", "supervisor", "admin", "superuser")


# ---- RoleID-based helpers (These look at the numeric ID instead of the string name) ----

def _has_full_access(user: User) -> bool:
    """RoleID 3 and 4 allow reading everything."""
    try:
        return int(getattr(user, "roleID", 0)) in (3, 4)
    except Exception:
        return False


def _is_assigned_clients_only(user: User) -> bool:
    """RoleID 2 limits the user to only seeing their assigned clients."""
    try:
        return int(getattr(user, "roleID", 0)) == 2
    except Exception:
        return False


def _is_self_only(user: User) -> bool:
    """RoleID 1 is for regular customers. They can only see their own stuff."""
    try:
        return int(getattr(user, "roleID", 0)) == 1
    except Exception:
        return False


def _own_customer_ids(user: User):
    """
    Finds the CustomerID associated with this User account.
    Useful for customers seeing their own data.

    Output: Set of CustomerIDs (e.g., {456})
    """
    try:
        custs = Customer.objects(UserID=user.userid)
        return {c.CustomerID for c in custs}
    except Exception:
        return set()


def _assigned_customer_ids(user: User):
    """
    Finds which customers are assigned to this agent based on claims they are working on.

    Output: Set of CustomerIDs
    """
    try:
        claims = Claim.objects(AssignedToUserID=user.userid)
        return {c.CustomerID for c in claims}
    except Exception:
        return set()


class AgentClaimsDashboard(APIView):
    """
    Dashboard for Agents to see what they need to work on.

    GET:
    - Lists all claims assigned to the logged-in agent.
    - Input: 'userid' header (must be an agent).
    - Output (Success 200):
      {
        "claims": [
          {
            "ClaimID": 123,
            "Status": "submitted",
            "Amount": 1500.00,
            ... (other claim fields)
          }
        ]
      }
    - Output (Fail 403): If you aren't an agent.
    """

    def get(self, request):
        user, err = _require_user(request)
        if err:
            return err

        # Security check: Only agents allow here
        if not _is_agent(user):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        try:
            # Grab all claims where AssignedToUserID matches the current user
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
    Main view for looking at one specific claim. Does read, update, and delete.

    GET:
    - Pulls up the claim info, PLUS the customer's history and their items (so the agent has context).
    - Input: claim_id in URL.
    - Output (200):
      {
        "claim": { ... details ... },
        "previousClaims": [ ... old claims ... ],
        "customerItems": [ ... items owned by customer ... ]
      }

    PUT:
    - Updates fields in the claim.
    - Input: JSON body with fields to change (e.g., {"Status": "reviewing"}).
    - Output (200): {"ok": true}

    DELETE:
    - Deletes the claim entirely.
    - Permission: Admin ONLY.
    - Output (200): {"ok": true}
    """

    def get(self, request, claim_id: int):
        user, err = _require_user(request)
        if err:
            return err
        try:
            claim = Claim.objects(ClaimID=int(claim_id)).first()
            if not claim:
                return Response({"error": "Claim not found"}, status=status.HTTP_404_NOT_FOUND)

            # Access Check: Must be Manager, Admin, OR the specific agent assigned to this claim
            if not (_is_manager(user) or _is_admin(user) or (claim.AssignedToUserID == user.userid)):
                return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

            # Fetch extra context for the frontend
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

            # Access Check
            if not (_is_manager(user) or _is_admin(user) or (claim.AssignedToUserID == user.userid)):
                return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

            # Map fields to their types for safe casting
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

            # Loop through payload and update if the field is valid
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

            # Create an audit log for the update
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
        # Just reuse the PUT logic for partial updates
        return self.put(request, claim_id)

    def delete(self, request, claim_id: int):
        user, err = _require_user(request)
        if err:
            return err

        # Only admins can delete claims history!
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
    Where the Agent makes the call: Accept or Reject.

    POST:
    - Input: JSON body {"decision": "accept", "reason": "Looks good"} or {"decision": "reject"}.
    - Logic: Agents can only decide on THEIR assigned claims. Managers can decide on any.
    - Output (200): {"ok": true, "newStatus": "accepted"}
    """

    def post(self, request, claim_id: int):
        user, err = _require_user(request)
        if err:
            return err
        if not _is_agent(user):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        decision = (request.data.get("decision") or "").strip().lower()
        reason = request.data.get("reason")

        # Validate input
        if decision not in ("accept", "reject"):
            return Response({"error": "Invalid decision"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            claim = Claim.objects(ClaimID=int(claim_id)).first()
            if not claim:
                return Response({"error": "Claim not found"}, status=status.HTTP_404_NOT_FOUND)

            # Access logic: If you aren't a manager, you must be the assigned agent
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


class SupervisorClaimsReviewList(APIView):
    """
    List for Managers to review claims that Agents have already 'accepted'.

    GET:
    - Only for Managers/Admins.
    - Input: None.
    - Output (200): List of claims with Status='accepted'.
      { "claims": [...] }
    """

    def get(self, request):
        user, err = _require_user(request)
        if err:
            return err
        if not (_is_manager(user) or _is_admin(user)):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            claims = Claim.objects(Status="accepted")
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


class SupervisorClaimDecisionView(APIView):
    """
    Manager's final say on a claim. They can Approve or Deny what the agent accepted.

    POST:
    - Input: {"decision": "approve"|"deny", "reason": "optional"}.
    - Constraint: Can only act on claims that are currently 'accepted'.
    - Output (200): {"ok": true, "newStatus": "approved"}
    """

    def post(self, request, claim_id: int):
        user, err = _require_user(request)
        if err:
            return err
        if not (_is_manager(user) or _is_admin(user)):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        decision = (request.data.get("decision") or "").strip().lower()
        reason = request.data.get("reason")
        if decision not in ("approve", "deny"):
            return Response({"error": "Invalid decision"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            claim = Claim.objects(ClaimID=int(claim_id)).first()
            if not claim:
                return Response({"error": "Claim not found"}, status=status.HTTP_404_NOT_FOUND)

            # Workflow check: Must be accepted first
            if (claim.Status or "").lower() != "accepted":
                return Response({"error": "Only accepted claims can be decided by supervisor"},
                                status=status.HTTP_400_BAD_REQUEST)

            claim.Status = "approved" if decision == "approve" else "denied"
            claim.Reason = reason or claim.Reason
            claim.UpdatedAt = _now_utc()
            claim.save()

            AuditLog(
                LogID=_new_log_id(),
                ActorUserID=user.userid,
                Action=f"supervisor_claim_{decision}",
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
    Shows a manager their direct reports.

    GET:
    - Input: None.
    - Output (200): List of users where managerID matches current user.
      {
        "employees": [
          {"userid": 77, "username": "agent_bob", "role": "agent", ...}
        ]
      }
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


class ManagerPoliciesView(APIView):
    """
    Shows a manager all policies they are responsible for (i.e., policies for
    customers whose claims are currently handled by the manager's direct reports).

    GET:
    - Input: None.
    - Output (200): All policies within the manager's scope.
      { "policies": [...] }
    Notes:
    - Admins see all policies.
    """

    def get(self, request):
        user, err = _require_user(request)
        if err:
            return err
        if not _is_manager(user):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        try:
            query = {}
            # Admins/superusers: see everything
            if not _is_admin(user):
                # Determine manager scope: direct reports -> their assigned claims -> customer IDs
                employee_ids = [u.userid for u in User.objects(managerID=user.userid)]
                if employee_ids:
                    cust_ids = {c.CustomerID for c in Claim.objects(AssignedToUserID__in=employee_ids)}
                else:
                    cust_ids = set()

                if not cust_ids:
                    return Response({"policies": []}, status=status.HTTP_200_OK)
                query["CustomerID__in"] = list(cust_ids)

            policies = Policy.objects(**query)
            data = [
                {
                    "PolicyID": p.PolicyID,
                    "CustomerID": p.CustomerID,
                    "Status": p.Status,
                    "CreatedAt": p.CreatedAt,
                    "UpdatedAt": getattr(p, "UpdatedAt", None),
                }
                for p in policies
            ]
            return Response({"policies": data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ManagerPendingPoliciesView(APIView):
    """
    Shows a manager all new policies that are waiting to be signed off.

    GET:
    - Input: None.
    - Output (200): Policies with Status='pending'.
      { "policies": [...] }
    """

    def get(self, request):
        user, err = _require_user(request)
        if err:
            return err
        if not _is_manager(user):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        try:
            # Admins: see all pending
            if _is_admin(user):
                policies = Policy.objects(Status="pending")
            else:
                # Scope to manager's team customers
                employee_ids = [u.userid for u in User.objects(managerID=user.userid)]
                if employee_ids:
                    cust_ids = {c.CustomerID for c in Claim.objects(AssignedToUserID__in=employee_ids)}
                else:
                    cust_ids = set()

                if not cust_ids:
                    return Response({"policies": []}, status=status.HTTP_200_OK)
                policies = Policy.objects(CustomerID__in=list(cust_ids), Status="pending")
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
    Manager approves or rejects a pending policy.

    POST:
    - Input: {"decision": "approve"|"reject"}.
    - Constraint: Policy must currently be 'pending'.
    - Output (200): {"ok": true, "newStatus": "approved"}
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
    The 'Big Brother' view. Admins can see the last 500 actions taken in the system.

    GET:
    - Input: None.
    - Output (200): List of 500 most recent logs.
      { "logs": [ { "Action": "claim_update", ... } ] }
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
    The main endpoint for getting lists of claims or creating a new one.

    GET:
    - Shows claims based on who you are:
      1. Managers/Admins -> See everything.
      2. Agents -> See only claims assigned to them.
      3. Customers -> See only their own claims.
    - Output (200): { "claims": [...] }

    POST:
    - Creates a new claim.
    - Input (JSON):
      {
        "CustomerID": 456, (Required, unless you are the customer, then we infer it)
        "Reason": "Fire",
        "Amount": 500,
        ...
      }
    - Output (201): {"created": true, "ClaimID": 124}
    """

    def get(self, request):
        user, err = _require_user(request)
        if err:
            return err
        try:
            q = {}
            if _is_manager(user) or _is_admin(user):
                # Managers/Admins see everything, so no filter needed.
                pass
            elif _is_agent(user):
                # Agents filter by their own ID.
                q["AssignedToUserID"] = user.userid
            else:
                # Customers only see their own stuff.
                own_ids = list(_own_customer_ids(user) or [])
                if not own_ids:
                    return Response({"claims": []}, status=status.HTTP_200_OK)
                q["CustomerID__in"] = own_ids

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

        # Who can create claims? Staff can, and Customers can (for themselves).
        is_staffish = _is_agent(user) or _is_manager(user) or _is_admin(user)
        is_customer = _is_self_only(user)

        if not (is_staffish or is_customer):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        try:
            payload = request.data or {}

            # Helper to grabbing fields regardless of casing (camelCase vs snake_case)
            def g(*names, default=None):
                for n in names:
                    if n in payload and payload[n] is not None:
                        return payload[n]
                return default

            claim_id = g("ClaimID", "claim_id")
            customer_id = g("CustomerID", "customer_id")
            policy_id = g("PolicyID", "policy_id")
            amount = g("Amount", "amount")
            reason = g("Reason", "reason")
            assigned_to = g("AssignedToUserID", "assigned_to_user_id")
            item_ids = g("ItemIDs", "item_ids", default=[])
            status_str = g("Status", "status", default="submitted")

            # Logic specifically for Customers creating their own claim
            if is_customer:
                own_ids = list(_own_customer_ids(user) or [])
                if not own_ids:
                    return Response({"error": "No associated customer record"}, status=status.HTTP_400_BAD_REQUEST)
                # If they didn't send an ID, use their first one.
                if customer_id is None:
                    customer_id = own_ids[0]
                # Security check: Prevent them from creating a claim for someone else
                if int(customer_id) not in own_ids:
                    return Response({"error": "Forbidden: invalid customer context"}, status=status.HTTP_403_FORBIDDEN)
                # Customers can't assign the claim, it goes to the pool (None)
                assigned_to = None

            # Validation
            if customer_id is None:
                return Response({"error": "Missing field: CustomerID"}, status=status.HTTP_400_BAD_REQUEST)

            # Generate ID if missing
            if claim_id is None:
                claim_id = _new_log_id()

            # Type conversion
            claim_id = int(claim_id)
            customer_id = int(customer_id)
            policy_id = int(policy_id) if policy_id is not None and str(policy_id) != "" else None

            # If agent creates it, they can assign it to themselves automatically
            assigned_to = int(assigned_to) if assigned_to is not None and str(assigned_to) != "" else (
                user.userid if _is_agent(user) and not is_customer else None)

            amount = float(amount) if amount is not None and str(amount) != "" else None
            item_ids = list(item_ids or [])

            # Check if this ID is already taken
            if Claim.objects(ClaimID=claim_id).first():
                return Response({"error": "ClaimID already exists"}, status=status.HTTP_409_CONFLICT)

            claim = Claim(
                ClaimID=claim_id,
                CustomerID=customer_id,
                PolicyID=policy_id,
                AssignedToUserID=assigned_to,
                Status=str(status_str or "submitted"),
                Reason=reason,
                Amount=amount,
                ItemIDs=item_ids,
                CreatedAt=_now_utc(),
                UpdatedAt=_now_utc(),
            )
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
    Standard List/Create view for Items (like cameras, laptops, etc.).

    GET:
    - Lists all items.
    - Output (200): { "items": [...] }

    POST:
    - Creates a new item.
    - Permission: Managers only.
    - Input: {"ItemID": 11, "Name": "Camera", "Value": 800}.
    - Output (201): {"created": true, "ItemID": 11}
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
    CRUD for a single Item.

    GET:
    - Get details.
    - Output (200): JSON object of the item.

    PUT:
    - Update details (Manager only).
    - Input: JSON body fields.
    - Output (200): {"ok": true}

    DELETE:
    - Delete item (Manager only).
    - Output (200): {"ok": true}
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
    List and Create Policies.

    GET:
    - List policies.
    - Managers/Admins see all. Agents see their assigned clients'. Customers see their own.
    - Output (200): { "policies": [...] }

    POST:
    - Create a policy.
    - Permission: Managers only.
    - Input: {"PolicyID": 902, "CustomerID": 457}.
    - Output (201): {"created": true, "PolicyID": 902}
    """

    def get(self, request):
        user, err = _require_user(request)
        if err:
            return err
        try:
            q = {}
            if _is_manager(user) or _is_admin(user):
                # See all
                pass
            elif _is_agent(user):
                # Only see policies for customers assigned to this agent
                assigned_ids = list(_assigned_customer_ids(user) or [])
                if not assigned_ids:
                    return Response({"policies": []}, status=status.HTTP_200_OK)
                q["CustomerID__in"] = assigned_ids
            else:
                # Customer sees only their own
                own_ids = list(_own_customer_ids(user) or [])
                if not own_ids:
                    return Response({"policies": []}, status=status.HTTP_200_OK)
                q["CustomerID__in"] = own_ids

            policies = Policy.objects(**q)
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
    CRUD for a single Policy.

    GET:
    - Get policy details.
    - Output (200): JSON object of the policy.

    PUT:
    - Update policy (Manager only).
    - Input: JSON body fields.
    - Output (200): {"ok": true}

    DELETE:
    - Delete policy (Admin only).
    - Output (200): {"ok": true}
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
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
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