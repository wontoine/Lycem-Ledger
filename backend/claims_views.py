from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings

from users.models import User, Claim, Item, Policy, AuditLog, Customer, CustomerPlan, InsurancePlan, Supervisor, Agent
from datetime import datetime
import json


def _now_utc():
    """
    Just a helper to get the current time in UTC so we don't have timezone headaches.

    Output: datetime object (UTC)
    """
    return datetime.utcnow()


def _print_api_payload(label: str, payload: dict):
    """
    Debug helper: pretty-print the JSON payload a view is about to return.
    Prints to the Django runserver terminal. Safe for datetimes via default=str.
    """
    try:
        print(f"\n=== {label} RESPONSE JSON ===", flush=True)
        print(json.dumps(payload, indent=2, default=str), flush=True)
        print("=== END RESPONSE JSON ===\n", flush=True)
    except Exception as _e:
        # Never allow logging to break the API response
        print(f"[debug] Failed to print payload for {label}: {_e}", flush=True)


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
        # Attempt multiple sources for compatibility with various clients/dev tools
        headers = getattr(request, "headers", {}) or {}
        meta = getattr(request, "META", {}) or {}

        # DRF Headers is case-insensitive, but we also probe common variants + META
        uid = (
            headers.get("userid")
            or headers.get("UserID")
            or headers.get("x-user-id")
            or headers.get("X-User-ID")
            or meta.get("HTTP_USERID")
            or meta.get("HTTP_X_USER_ID")
        )

        # As a last resort (dev convenience only), allow query param
        if not uid:
            try:
                # request.query_params for DRF, fallback to GET for Django
                qp = getattr(request, "query_params", None) or getattr(request, "GET", {})
                uid = qp.get("x-user-id") or qp.get("userid")
            except Exception:
                uid = None

        if not uid:
            return None
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
    # Correct mapping:
    # - roleID 3 = Supervisor (this is the "manager")
    # - roleID 2 = Agent (NOT a manager)
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
    if role in ("supervisor", "admin", "superuser"):
        return True

    # Fallback: if this user appears in the supervisors collection, treat as manager
    # This helps in environments where the role table isn't synchronized yet.
    try:
        sup = Supervisor.objects(UserID=user.userid).first()
        if sup is not None:
            return True
    except Exception:
        pass
    return False


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
    Finds which customers are assigned to this agent. Priority is explicit
    customer assignment via Customer.AssignedAgentUserID; falls back to
    customers from claims AssignedToUserID.

    Output: Set of CustomerIDs
    """
    try:
        # Prefer explicit assignment on Customer documents
        custs = Customer.objects(__raw__={"AssignedAgentUserID": user.userid})
        cust_ids = {c.CustomerID for c in custs}
        if cust_ids:
            return cust_ids
        # Fallback: infer from claims currently assigned
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


class AgentCreatePlanView(APIView):
    """
    Agent creates a new insurance plan entry in insurancePlans.
    - planID auto-assigned as max+1
    - PlanName must be unique (case-insensitive)
    - Optional fields: Description, CoverageLim, BasePrice
    """

    def post(self, request):
        user, err = _require_user(request)
        if err:
            return err
        if not (_is_agent(user) or _is_manager(user) or _is_admin(user)):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        data = request.data if isinstance(request.data, dict) else {}
        plan_name = str(data.get("PlanName") or "").strip()
        if not plan_name:
            return Response({"error": {"PlanName": "This field is required"}}, status=status.HTTP_400_BAD_REQUEST)

        # Ensure PlanName uniqueness (case-insensitive)
        try:
            existing = InsurancePlan.objects(__raw__={
                "PlanName": {"$regex": f"^{plan_name}$", "$options": "i"}
            }).first()
            if existing:
                return Response({"error": "PlanName already exists"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            msg = "Database connection error"
            if settings.DEBUG:
                msg = f"Database error: {e}"
            return Response({"error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Generate next planID
        try:
            last = InsurancePlan.objects.order_by("-planID").first()
            last_id = getattr(last, "planID", None) or getattr(last, "PlanID", None)
            next_id = (last_id + 1) if last_id is not None else 1
        except Exception:
            next_id = 1

        # Optional fields
        desc = str(data.get("Description")).strip() if data.get("Description") else None
        coverage = data.get("CoverageLim")
        base_price = data.get("BasePrice")
        try:
            coverage_val = float(coverage) if coverage not in (None, "") else None
        except Exception:
            return Response({"error": {"CoverageLim": "Must be numeric"}}, status=status.HTTP_400_BAD_REQUEST)
        try:
            base_price_val = float(base_price) if base_price not in (None, "") else None
        except Exception:
            return Response({"error": {"BasePrice": "Must be numeric"}}, status=status.HTTP_400_BAD_REQUEST)

        try:
            plan = InsurancePlan(planID=next_id, PlanName=plan_name)
            if desc:
                plan.Description = desc
            if coverage_val is not None:
                plan.CoverageLim = coverage_val
            if base_price_val is not None:
                plan.BasePrice = base_price_val
            plan.save()
        except Exception as e:
            msg = "Unable to create plan"
            if settings.DEBUG:
                msg = f"Create failed: {e}"
            return Response({"error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(
            {
                "created": True,
                "planID": next_id,
                "PlanName": plan_name,
                "Description": desc,
                "CoverageLim": coverage_val,
                "BasePrice": base_price_val,
            },
            status=status.HTTP_201_CREATED,
        )

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

            # Workflow check: Manager may decide on claims awaiting approval.
            # Support both legacy flow ('accepted' by agent) and the simplified
            # requirement where manager acts on 'pending' claims.
            if (claim.Status or "").lower() not in ("accepted", "pending"):
                return Response({"error": "Only pending or accepted claims can be decided by supervisor"},
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
            # Determine manager's team via supervisors collection (tolerant to casing)
            sup = None
            try:
                sup = Supervisor.objects(UserID=user.userid).first()
                if not sup:
                    sup = Supervisor.objects(__raw__={"$or": [
                        {"UserID": user.userid},
                        {"userID": user.userid},
                    ]}).first()
            except Exception:
                sup = None
            team_id = getattr(sup, 'TeamID', None) if sup else None
            if team_id is None:
                return Response({"employees": []}, status=status.HTTP_200_OK)

            # Find agents that are on the same team (support TeamID/teamID in raw docs)
            try:
                team_agents = list(Agent.objects(__raw__={"$or": [
                    {"TeamID": team_id},
                    {"teamID": team_id},
                ]}))
            except Exception:
                team_agents = []

            # Helper to safely extract fields with multiple casings
            def _aget(a, *names):
                for n in names:
                    try:
                        v = getattr(a, n, None)
                        if v is not None:
                            return v
                    except Exception:
                        pass
                    try:
                        data = getattr(a, "_data", None) or {}
                        if n in data and data[n] is not None:
                            return data[n]
                    except Exception:
                        pass
                return None

            agent_user_ids = []
            for a in team_agents:
                uid = _aget(a, 'UserID', 'userID')
                if uid is not None:
                    agent_user_ids.append(uid)
            if not agent_user_ids:
                return Response({"employees": []}, status=status.HTTP_200_OK)

            users = User.objects(userid__in=agent_user_ids)
            data = [
                {
                    "userid": u.userid,
                    "username": u.username,
                    "email": getattr(u, "email", None),
                    "role": u.role_name,
                    "isEnabled": u.isEnabled,
                }
                for u in users
            ]
            return Response({"employees": data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ManagerUnassignedCustomersView(APIView):
    """
    Lists customers that do not have an AssignedAgentUserID so a manager can assign them.

    GET /api/manager/customers/unassigned/

    Permissions:
    - Managers/Admins only.

    Scope:
    - Admins: all unassigned customers.
    - Managers: all unassigned customers (global), since assignment determines team.
      This matches the requirement to surface all customers missing an agent so the
      supervisor can assign them to someone on their team.
    """

    def get(self, request):
        user, err = _require_user(request)
        if err:
            return err
        if not (_is_manager(user) or _is_admin(user)):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            # Customers missing explicit assignment
            customers = Customer.objects(__raw__={
                "$or": [
                    {"AssignedAgentUserID": {"$exists": False}},
                    {"AssignedAgentUserID": None},
                    {"AssignedAgentUserID": 0},
                ]
            })
            data = [
                {
                    "CustomerID": c.CustomerID,
                    "UserID": getattr(c, "UserID", None),
                    "Email": getattr(c, "Email", None),
                }
                for c in customers
            ]
            return Response({"customers": data}, status=status.HTTP_200_OK)
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
                # Determine manager scope via supervisors collection: TeamID -> customers
                sup = Supervisor.objects(UserID=user.userid).first()
                if not sup or getattr(sup, 'TeamID', None) is None:
                    return Response({"policies": []}, status=status.HTTP_200_OK)
                team_id = getattr(sup, 'TeamID', None)

                # Find customers on this team
                try:
                    team_customers = Customer.objects(__raw__={"TeamID": team_id})
                    cust_ids = [c.CustomerID for c in team_customers]
                except Exception:
                    cust_ids = []

                if not cust_ids:
                    return Response({"policies": []}, status=status.HTTP_200_OK)
                query["CustomerID__in"] = cust_ids

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
    Manager approvals inbox for POLICIES/PLANS.

    Returns customer plans within scope, regardless of Status (pending/approved/rejected).
    Scope:
    - Admins/Superusers: see ALL customer plans.
    - Managers: only plans for customers whose TeamID matches the manager's TeamID
      as defined in the supervisors collection (UserID -> TeamID).
    The endpoint path keeps '/pending/' for backward compatibility with the UI.

    GET:
    - Output (200): { "policies": [ { PolicyID, CustomerID, Status, CreatedAt, policy_name?, planID } ] }
    """

    def get(self, request):
        """
        Determine policies strictly by supervisor -> team -> customers mapping
        using the x-user-id provided. This endpoint intentionally does not
        require an authenticated User document; it relies on the supervisor
        record as the source of truth for team scoping, per requirements.
        """

        try:
            debug = str(request.GET.get("debug", "0")).lower() in ("1", "true", "yes")

            # 1) Read the manager's user id from headers or query params
            headers = getattr(request, "headers", {}) or {}
            meta = getattr(request, "META", {}) or {}
            uid = (
                headers.get("x-user-id")
                or headers.get("X-User-ID")
                or headers.get("userid")
                or headers.get("UserID")
                or meta.get("HTTP_X_USER_ID")
                or meta.get("HTTP_USERID")
            )
            if not uid:
                qp = getattr(request, "query_params", None) or getattr(request, "GET", {})
                uid = qp.get("x-user-id") or qp.get("userid") or qp.get("UserID")
            try:
                manager_userid = int(uid) if uid is not None else None
            except Exception:
                manager_userid = None

            if manager_userid is None:
                payload = {"policies": []}
                if debug:
                    payload["debug_info"] = {
                        "reason": "missing x-user-id",
                        "manager_userid": None,
                        "supervisor_found": False,
                        "team_id": None,
                        "team_customer_count": 0,
                        "plans_count_returned": 0,
                    }
                _print_api_payload("ManagerPendingPoliciesView", payload)
                return Response(payload, status=status.HTTP_200_OK)

            # 2) Look up supervisor by userID with flexible casing in DB fields
            sup = None
            try:
                # Try exact field first (uppercase mapping)
                sup = Supervisor.objects(UserID=manager_userid).first()
                if not sup:
                    # Fallback raw query to support collections using lowercase 'userID'
                    sup = Supervisor.objects(__raw__={"$or": [
                        {"UserID": manager_userid},
                        {"userID": manager_userid},
                    ]}).first()
            except Exception:
                sup = None

            if not sup or getattr(sup, 'TeamID', None) is None:
                payload = {"policies": []}
                if debug:
                    payload["debug_info"] = {
                        "manager_userid": manager_userid,
                        "supervisor_found": False,
                        "team_id": None,
                        "team_customer_count": 0,
                        "plans_count_returned": 0,
                    }
                _print_api_payload("ManagerPendingPoliciesView", payload)
                return Response(payload, status=status.HTTP_200_OK)

            team_id = getattr(sup, 'TeamID', None)

            # 3) Find customers with this TeamID
            try:
                team_customers = Customer.objects(__raw__={"TeamID": team_id})
                cust_ids = [c.CustomerID for c in team_customers]
            except Exception:
                cust_ids = []

            if not cust_ids:
                payload = {"policies": []}
                if debug:
                    payload["debug_info"] = {
                        "manager_userid": manager_userid,
                        "supervisor_found": True,
                        "team_id": team_id,
                        "team_customer_count": 0,
                        "plans_count_returned": 0,
                    }
                _print_api_payload("ManagerPendingPoliciesView", payload)
                return Response(payload, status=status.HTTP_200_OK)

            # 4) Fetch customer plans for these customers only
            plans = CustomerPlan.objects(CustomerID__in=cust_ids)

            # Helpers to robustly read fields with various casings and types
            def _get_field(cp, *names, default=None):
                for n in names:
                    # Try attribute
                    val = getattr(cp, n, None)
                    if val is not None:
                        return val
                    # Try underlying _data dict via mongoengine if present (handles raw field names)
                    try:
                        data = getattr(cp, "_data", None) or {}
                        if n in data and data[n] is not None:
                            return data[n]
                    except Exception:
                        pass
                return default

            def _normalize_plan_id(pid):
                if pid is None:
                    return None
                try:
                    return int(pid)
                except Exception:
                    # if it cannot be cast, return as-is to avoid losing info
                    return pid

            # 5) Build planID -> PlanName map (normalize keys to int when possible)
            raw_plan_ids = []
            for p in plans:
                raw_pid = _get_field(p, 'planID', 'PlanID', default=None)
                n_pid = _normalize_plan_id(raw_pid)
                if n_pid is not None:
                    raw_plan_ids.append(n_pid)
            plan_ids = sorted({pid for pid in raw_plan_ids if pid is not None})

            name_by_id = {}
            if plan_ids:
                try:
                    # Query with normalized integers only; if some are non-int strings, they won't match the index,
                    # but we attempt best-effort by querying unique int IDs we extracted
                    int_ids = [pid for pid in plan_ids if isinstance(pid, int)]
                    if int_ids:
                        for ip in InsurancePlan.objects(planID__in=int_ids):
                            name_by_id[_normalize_plan_id(getattr(ip, 'planID', None))] = getattr(ip, 'PlanName', None)
                except Exception:
                    name_by_id = {}

            def _policy_name_for(cp):
                pid = _normalize_plan_id(_get_field(cp, 'planID', 'PlanID'))
                # Prefer name from catalog, else fall back to any embedded name in the plan document
                return (
                    name_by_id.get(pid)
                    or _get_field(cp, 'PlanName', 'policy_name')
                )

            def _status_for(cp):
                return _get_field(cp, 'Status', 'status', default='pending')

            def _created_for(cp):
                # Try common variants; fall back to StartDate if present
                val = _get_field(cp, 'CreatedAt', 'createdAt', 'created_at', 'Created', default=None)
                if val is None:
                    val = _get_field(cp, 'StartDate', 'startDate', default=None)
                return val

            data = [
                {
                    "PolicyID": _get_field(cp, 'CustomerPlanID', 'customerPlanID', 'customerplanID'),
                    "CustomerID": _get_field(cp, 'CustomerID', 'customerID'),
                    "Status": _status_for(cp),
                    "CreatedAt": _created_for(cp),
                    "policy_name": _policy_name_for(cp),
                    "planID": _normalize_plan_id(_get_field(cp, 'planID', 'PlanID')),
                }
                for cp in plans
            ]

            payload = {"policies": data}
            if debug:
                payload["debug_info"] = {
                    "manager_userid": manager_userid,
                    "supervisor_found": True,
                    "team_id": team_id,
                    "team_customer_count": len(cust_ids),
                    "plans_count_returned": len(data),
                }
            _print_api_payload("ManagerPendingPoliciesView", payload)
            return Response(payload, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ManagerAssignablePoliciesView(APIView):
    """
    Manager Assign Policies list.
    Similar to ManagerPendingPoliciesView but returns only customer plans within
    the manager's team scope that DO NOT have an assignmentID set in the
    customerPlans document. No status filter is applied.

    GET:
    - Output: { "policies": [ ... ] }
    """

    def get(self, request):
        user, err = _require_user(request)
        if err:
            return err
        if not _is_manager(user):
            return Response({"policies": []}, status=status.HTTP_403_FORBIDDEN)

        try:
            # Be tolerant to field casing in supervisors collection, like the pending view
            sup = None
            try:
                sup = Supervisor.objects(UserID=user.userid).first()
                if not sup:
                    sup = Supervisor.objects(__raw__={"$or": [
                        {"UserID": user.userid},
                        {"userID": user.userid},
                    ]}).first()
            except Exception:
                sup = None
            team_id = getattr(sup, 'TeamID', None) if sup else None
            if team_id is None:
                return Response({"policies": []}, status=status.HTTP_200_OK)

            # Customers on this team
            team_customers = Customer.objects(__raw__={"TeamID": team_id})
            cust_ids = [c.CustomerID for c in team_customers]
            if not cust_ids:
                return Response({"policies": []}, status=status.HTTP_200_OK)

            # Customer plans for these customers that are missing assignmentID
            plans = CustomerPlan.objects(CustomerID__in=cust_ids)

            def _get(cp, *names, default=None):
                for n in names:
                    v = getattr(cp, n, None)
                    if v is not None:
                        return v
                    try:
                        data = getattr(cp, "_data", None) or {}
                        if n in data and data[n] is not None:
                            return data[n]
                    except Exception:
                        pass
                return default

            def _normalize_int(val):
                if val is None:
                    return None
                try:
                    return int(val)
                except Exception:
                    return val

            # filter missing assignmentID (support multiple possible field names)
            filtered = []
            for cp in plans:
                # Consider any of these as an assignment marker
                has_assign = _get(cp, 'assignmentID', 'AssignmentID', 'AssignedAgentID', 'assignedAgentID')
                if has_assign in (None, 0, "", "0"):
                    filtered.append(cp)

            # Build plan name map
            plan_ids = []
            for cp in filtered:
                pid = _normalize_int(_get(cp, 'planID', 'PlanID'))
                if pid is not None:
                    plan_ids.append(pid)
            name_by_id = {}
            if plan_ids:
                try:
                    int_ids = [pid for pid in set(plan_ids) if isinstance(pid, int)]
                    if int_ids:
                        for ip in InsurancePlan.objects(planID__in=int_ids):
                            name_by_id[_normalize_int(getattr(ip, 'planID', None))] = getattr(ip, 'PlanName', None)
                except Exception:
                    name_by_id = {}

            def _policy_name(cp):
                pid = _normalize_int(_get(cp, 'planID', 'PlanID'))
                return name_by_id.get(pid) or _get(cp, 'PlanName', 'policy_name')

            def _created(cp):
                return _get(cp, 'CreatedAt', 'createdAt', 'Created', 'StartDate')

            data = [
                {
                    "PolicyID": _get(cp, 'CustomerPlanID', 'customerPlanID', 'customerplanID'),
                    "CustomerID": _get(cp, 'CustomerID', 'customerID'),
                    "Status": _get(cp, 'Status', 'status', default='pending'),
                    "CreatedAt": _created(cp),
                    "policy_name": _policy_name(cp),
                    "planID": _normalize_int(_get(cp, 'planID', 'PlanID')),
                }
                for cp in filtered
            ]

            return Response({"policies": data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ManagerAssignPolicyView(APIView):
    """
    Assign a customer plan (policy) to an agent by creating a new AssignmentID.
    Steps:
    - Compute max AssignmentID from Plan_agent_Assignment, increment by 1.
    - Insert new record into Plan_agent_Assignment.
    - Update the selected agent's document (User) with assignmentID.
    - Update the corresponding customer plan with assignmentID.
    """

    def post(self, request, policy_id: int):
        from users.models import PlanAgentAssignment  # local import to avoid circulars

        user, err = _require_user(request)
        if err:
            return err
        if not _is_manager(user):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        try:
            body = {}
            try:
                body = json.loads(request.body or "{}")
            except Exception:
                body = getattr(request, 'data', {}) or {}

            agent_user_id = body.get('agentUserID') or body.get('agent_id') or body.get('agentUserId')
            try:
                agent_user_id = int(agent_user_id)
            except Exception:
                agent_user_id = None

            if not agent_user_id:
                return Response({"error": "agentUserID is required"}, status=status.HTTP_400_BAD_REQUEST)

            # Find the customer plan by CustomerPlanID == policy_id
            cp = CustomerPlan.objects(__raw__={"$or": [
                {"CustomerPlanID": policy_id},
                {"customerPlanID": policy_id},
                {"customerplanID": policy_id},
            ]}).first()
            if not cp:
                return Response({"error": "Policy not found"}, status=status.HTTP_404_NOT_FOUND)

            # Generate next AssignmentID (max + 1)
            try:
                last = PlanAgentAssignment.objects.order_by('-AssignmentID').first()
                next_id = (getattr(last, 'AssignmentID', 0) or 0) + 1
            except Exception:
                next_id = 1

            # Insert into Plan_agent_Assignment
            PlanAgentAssignment(AssignmentID=next_id).save()

            # Update Agent (User) with assignmentID (dynamic field tolerated)
            u = User.objects(userid=agent_user_id).first()
            if u:
                setattr(u, 'assignmentID', next_id)
                try:
                    # also set capitalized variant for legacy clients
                    setattr(u, 'AssignmentID', next_id)
                except Exception:
                    pass
                u.save()

            # Update Agent collection row linked by UserID
            ag = Agent.objects(__raw__={"userID": agent_user_id}).first()
            if ag:
                try:
                    setattr(ag, 'assignmentID', next_id)
                    setattr(ag, 'AssignmentID', next_id)
                except Exception:
                    pass
                ag.save()

            # Update CustomerPlan with assignmentID
            setattr(cp, 'assignmentID', next_id)
            try:
                setattr(cp, 'AssignmentID', next_id)
            except Exception:
                pass
            cp.save()

            return Response({"ok": True, "AssignmentID": next_id}, status=status.HTTP_200_OK)
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

        # Robustly parse decision from either DRF request.data or raw body JSON
        try:
            incoming = getattr(request, "data", None)
            if not incoming or (isinstance(incoming, dict) and "decision" not in incoming):
                incoming = json.loads(getattr(request, "body", b"{}") or b"{}")
        except Exception:
            incoming = {}

        decision = (str((incoming or {}).get("decision") or "")).strip().lower()
        if decision not in ("approve", "reject"):
            return Response({"error": "Invalid decision"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # First try: treat id as a classic PolicyID
            policy = Policy.objects(PolicyID=int(policy_id)).first()
            if policy:
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

            # Otherwise, this is a CustomerPlan approval (CustomerPlanID mapped to PolicyID in UI)
            cplan = CustomerPlan.objects(CustomerPlanID=int(policy_id)).first()
            if not cplan:
                return Response({"error": "Policy/CustomerPlan not found"}, status=status.HTTP_404_NOT_FOUND)

            # Read status flexibly (supports missing field -> treat as pending as in list endpoint)
            def _get(cp, *names, default=None):
                for n in names:
                    v = getattr(cp, n, None)
                    if v is not None:
                        return v
                    try:
                        data = getattr(cp, "_data", None) or {}
                        if n in data and data[n] is not None:
                            return data[n]
                    except Exception:
                        pass
                return default

            current_status = (_get(cplan, 'Status', 'status', default='pending') or 'pending').lower()
            if current_status != "pending":
                return Response({"error": "CustomerPlan is not pending"}, status=status.HTTP_400_BAD_REQUEST)

            cplan.Status = "approved" if decision == "approve" else "rejected"
            setattr(cplan, 'UpdatedAt', _now_utc())
            cplan.save()

            AuditLog(
                LogID=_new_log_id(),
                ActorUserID=user.userid,
                Action=f"customerplan_{decision}",
                TargetType="customerplan",
                TargetID=str(cplan.CustomerPlanID),
                Details=None,
                CreatedAt=_now_utc(),
            ).save()

            return Response({"ok": True, "newStatus": cplan.Status}, status=status.HTTP_200_OK)
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


class ManagerAssignCustomerView(APIView):
    """
    Allows a supervisor/manager to assign a customer to an agent on their team.

    POST /api/manager/customers/<customer_id>/assign/
    Body: { "agentUserID": 77 }

    Rules:
    - Requesting user must be a manager/supervisor (or admin).
    - agentUserID must belong to the manager's direct reports (unless admin).
    - Sets Customer.AssignedAgentUserID = agentUserID.
    - Writes an audit log.
    """

    def post(self, request, customer_id: int):
        user, err = _require_user(request)
        if err:
            return err
        if not _is_manager(user) and not _is_admin(user):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        try:
            payload = request.data or {}
            agent_user_id = payload.get("agentUserID")
            try:
                agent_user_id = int(agent_user_id)
            except Exception:
                return Response({"error": "agentUserID must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

            # Validate customer exists
            customer = Customer.objects(CustomerID=int(customer_id)).first()
            if not customer:
                return Response({"error": "Customer not found"}, status=status.HTTP_404_NOT_FOUND)

            # Validate agent exists and is a direct report (unless admin)
            agent = User.objects(userid=agent_user_id).first()
            if not agent:
                return Response({"error": "Agent not found"}, status=status.HTTP_404_NOT_FOUND)

            if not _is_admin(user):
                direct_report_ids = {u.userid for u in User.objects(managerID=user.userid)}
                if agent_user_id not in direct_report_ids:
                    return Response({"error": "Agent is not on your team"}, status=status.HTTP_403_FORBIDDEN)

            # Perform assignment (Customer has strict=False, so adding field is allowed)
            setattr(customer, "AssignedAgentUserID", agent_user_id)
            customer.save()

            # Audit
            AuditLog(
                LogID=_new_log_id(),
                ActorUserID=user.userid,
                Action="customer_assign_agent",
                TargetType="customer",
                TargetID=str(customer.CustomerID),
                Details={"agentUserID": agent_user_id},
                CreatedAt=_now_utc(),
            ).save()

            return Response({"ok": True, "CustomerID": customer.CustomerID, "AssignedAgentUserID": agent_user_id}, status=status.HTTP_200_OK)
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
            if _is_admin(user) or _is_manager(user):
                # Admins and Managers see all policies
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

    def get(self, request, etc: int):
        user, err = _require_user(request)
        if err:
            return err
        if not (_is_manager(user) or _is_admin(user)):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            policy_id = int(etc)
            p = Policy.objects(PolicyID=policy_id).first()
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

    def put(self, request, etc: int):
        user, err = _require_user(request)
        if err:
            return err
        if not (_is_manager(user) or _is_admin(user)):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            policy_id = int(etc)
            p = Policy.objects(PolicyID=policy_id).first()
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

    def patch(self, request, etc: int):
        return self.put(request, etc)

    def delete(self, request, etc: int):
        user, err = _require_user(request)
        if err:
            return err
        if not _is_admin(user):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        try:
            policy_id = int(etc)
            p = Policy.objects(PolicyID=policy_id).first()
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
