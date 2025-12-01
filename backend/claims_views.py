from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings

from users.models import User, Claim, Item, Policy, AuditLog, Customer, CustomerPlan, InsurancePlan, Supervisor, Agent
from datetime import datetime, timedelta
from django.utils import timezone
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
            # Determine the AgentID for this logged-in user
            agent_id = None
            try:
                agent_doc = Agent.objects(UserID=user.userid).first()
                if agent_doc and getattr(agent_doc, "AgentID", None):
                    agent_id = int(getattr(agent_doc, "AgentID"))
            except Exception:
                pass

            # --- CORRECTION START ---
            # Build query to find plans assigned to either the AgentID OR the UserID
            query_filter = [
                {"assignedAgentID": user.userid},
                {"AssignedAgentID": user.userid},
                {"assignedAgentID": str(user.userid)},
                {"AssignedAgentID": str(user.userid)},
            ]

            if agent_id:
                query_filter.extend([
                    {"assignedAgentID": agent_id},
                    {"AssignedAgentID": agent_id},
                    {"assignedAgentID": str(agent_id)},
                    {"AssignedAgentID": str(agent_id)},
                ])

            try:
                assigned_plans = CustomerPlan.objects(__raw__={"$or": query_filter})
            except Exception:
                assigned_plans = []
            # --- CORRECTION END ---

            # Prefer linking via CustomerPlanID instead of CustomerID
            plan_ids = set()
            customer_ids = set()
            for cp in assigned_plans:
                try:
                    pid = getattr(cp, "CustomerPlanID", None) or getattr(getattr(cp, "_data", {}), "get",
                                                                         lambda *_: None)("CustomerPlanID")
                except Exception:
                    pid = None
                if pid is not None:
                    try:
                        plan_ids.add(int(pid))
                    except Exception:
                        pass
                # Also collect customer IDs to support legacy claims without CustomerPlanID
                try:
                    cid = getattr(cp, "CustomerID", None) or (
                        cp._data.get("CustomerID") if hasattr(cp, "_data") else None)
                except Exception:
                    cid = None
                if cid is not None:
                    try:
                        customer_ids.add(int(cid))
                    except Exception:
                        pass

            # Build primary query: claims linked to these customer plan IDs (support int and string storage)
            claims = []
            debug = str(getattr(getattr(request, "GET", None), "get", lambda *_: "0")("debug") or "0").lower() in ("1",
                                                                                                                   "true",
                                                                                                                   "yes")
            tried_primary = False
            tried_fallback_customer = False
            tried_fallback_assigned = False

            if plan_ids:
                tried_primary = True
                try:
                    plan_id_list = list(plan_ids)
                    plan_id_str_list = [str(p) for p in plan_id_list]
                    claims = Claim.objects(__raw__={
                        "$or": [
                            {"CustomerPlanID": {"$in": plan_id_list}},
                            {"CustomerPlanID": {"$in": plan_id_str_list}},
                        ]
                    })
                except Exception:
                    claims = []

            # Fallback 1: legacy claims linked only by CustomerID (no CustomerPlanID on claim)
            if (not claims) and customer_ids:
                tried_fallback_customer = True
                try:
                    cid_list = list(customer_ids)
                    cid_str_list = [str(c) for c in cid_list]
                    claims = Claim.objects(__raw__={
                        "$and": [
                            {"CustomerID": {"$in": cid_list + cid_str_list}},
                            {"$or": [
                                {"CustomerPlanID": {"$exists": False}},
                                {"CustomerPlanID": None},
                                {"CustomerPlanID": ""}
                            ]}
                        ]
                    })
                except Exception:
                    claims = []

            # Fallback 2: as a last resort, include claims explicitly assigned to the agent user
            if not claims:
                tried_fallback_assigned = True
                try:
                    claims = Claim.objects(AssignedToUserID=user.userid)
                except Exception:
                    claims = []

            data = [
                {
                    "ClaimID": c.ClaimID,
                    "CustomerID": c.CustomerID,
                    "PolicyID": c.PolicyID,
                    "CustomerPlanID": getattr(c, "CustomerPlanID", None),
                    "Status": c.Status,
                    "Amount": c.Amount,
                    "Reason": c.Reason,
                    "ItemIDs": list(getattr(c, "ItemIDs", []) or []),
                    "CreatedAt": getattr(c, "CreatedAt", None),
                    "UpdatedAt": getattr(c, "UpdatedAt", None),
                }
                for c in claims
            ]

            if debug:
                meta = {
                    "agentUserID": user.userid,
                    "agentID": agent_id,
                    "planCount": len(plan_ids),
                    "customerCount": len(customer_ids),
                    "usedPrimary": tried_primary,
                    "usedFallbackCustomer": tried_fallback_customer,
                    "usedFallbackAssigned": tried_fallback_assigned,
                    "resultCount": len(data),
                }
                return Response({"claims": data, "debug": meta}, status=status.HTTP_200_OK)

            return Response({"claims": data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AgentPoliciesView(APIView):
    """
    Returns policies (customer plans) for the logged-in agent.

    The frontend expects an array under the key 'policies'. Each entry should
    include fields similar to a policy card shown in the Agent Home Page.
    """

    def get(self, request):
        user, err = _require_user(request)
        if err:
            return err
        if not _is_agent(user):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        try:
            # Determine AgentID for this user (if it exists)
            agent_id = None
            try:
                agent_doc = Agent.objects(UserID=user.userid).first()
                if agent_doc and getattr(agent_doc, "AgentID", None):
                    agent_id = int(getattr(agent_doc, "AgentID"))
            except Exception:
                pass

            # --- CORRECTION START ---
            # Search for plans assigned to either UserID OR AgentID
            query_filter = [
                {"assignedAgentID": user.userid},
                {"AssignedAgentID": user.userid},
                {"assignedAgentID": str(user.userid)},
                {"AssignedAgentID": str(user.userid)},
            ]

            if agent_id:
                query_filter.extend([
                    {"assignedAgentID": agent_id},
                    {"AssignedAgentID": agent_id},
                    {"assignedAgentID": str(agent_id)},
                    {"AssignedAgentID": str(agent_id)},
                ])

            try:
                assigned_plans = CustomerPlan.objects(__raw__={"$or": query_filter})
            except Exception:
                assigned_plans = []

            # --- CORRECTION END ---

            def _get(cp, *names, default=None):
                for n in names:
                    try:
                        if hasattr(cp, n):
                            val = getattr(cp, n)
                            if val is not None:
                                return val
                        # Fallback to raw data if available
                        if hasattr(cp, "_data") and n in cp._data and cp._data[n] is not None:
                            return cp._data[n]
                    except Exception:
                        continue
                return default

            # Build a lookup of planID -> InsurancePlan to enrich any missing fields
            plan_ids = set()
            for cp in assigned_plans:
                pid = _get(cp, "planID", "PlanID")
                if pid is not None:
                    try:
                        plan_ids.add(int(pid))
                    except Exception:
                        pass

            plan_lookup = {}
            if plan_ids:
                try:
                    plans = InsurancePlan.objects(planID__in=list(plan_ids))
                    for p in plans:
                        try:
                            plan_lookup[int(getattr(p, "planID", None) or p._data.get("planID"))] = p
                        except Exception:
                            continue
                except Exception:
                    plan_lookup = {}

            def _plan_val(p, *names):
                for n in names:
                    try:
                        v = getattr(p, n, None)
                        if v is not None:
                            return v
                    except Exception:
                        pass
                    try:
                        d = getattr(p, "_data", {})
                        if n in d and d[n] is not None:
                            return d[n]
                    except Exception:
                        pass
                return None

            policies = []
            for cp in assigned_plans:
                cp_plan_id = _get(cp, "planID", "PlanID")
                ip = None
                try:
                    if cp_plan_id is not None:
                        ip = plan_lookup.get(int(cp_plan_id))
                except Exception:
                    ip = None

                policy = {
                    "PolicyID": _get(cp, "CustomerPlanID", "customerPlanID", "customerplanID"),
                    "CustomerID": _get(cp, "CustomerID", "customerID"),
                    "Status": _get(cp, "Status", default="Active"),
                    # Prefer values from customerPlans; fallback to insurancePlans
                    "PlanName": _get(cp, "PlanName", "planName") or (ip and _plan_val(ip, "PlanName")),
                    "Description": _get(cp, "Description", "description") or (ip and _plan_val(ip, "Description")),
                    "CoverageLim": _get(cp, "CoverageLim", "coverageLim")
                    if _get(cp, "CoverageLim", "coverageLim") is not None else (ip and _plan_val(ip, "CoverageLim")),
                    # BasePrice is the catalog value; CurrentPremium is the customer plan price
                    "BasePrice": _get(cp, "CurrentPremium", "BasePrice", "basePrice")
                    if _get(cp, "CurrentPremium", "BasePrice", "basePrice") is not None else (
                                ip and _plan_val(ip, "BasePrice")),
                    "StartDate": _get(cp, "StartDate", "startDate"),
                    "EndDate": _get(cp, "EndDate", "endDate"),
                    "planID": cp_plan_id,
                    "assignedAgentID": _get(cp, "assignedAgentID", "AssignedAgentID"),
                }
                policies.append(policy)

            return Response({"policies": policies}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AgentCreatePlanView(APIView):
    """
    Agent creates a new customer plan entry in customerPlans.
    Input payload (from frontend):
      {
        userID,           # here this is the customerID
        planID,           # plan id from selected plan
        PlanName,
        Description,
        CoverageLim,
        BasePrice,
        status            # e.g., "approved" (we store in Status)
      }
    """

    def post(self, request):
        user, err = _require_user(request)
        if err:
            return err
        if not (_is_agent(user) or _is_manager(user) or _is_admin(user)):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        data = request.data if isinstance(request.data, dict) else {}

        # Required fields
        try:
            customer_id = int(data.get("userID"))
        except Exception:
            return Response({"error": {"userID": "Must be an integer (customerID)"}},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            plan_id_val = int(data.get("planID"))
        except Exception:
            return Response({"error": {"planID": "Must be an integer"}}, status=status.HTTP_400_BAD_REQUEST)
        try:
            base_price = float(data.get("BasePrice"))
        except Exception:
            return Response({"error": {"BasePrice": "Must be numeric"}}, status=status.HTTP_400_BAD_REQUEST)

        plan_name = str(data.get("PlanName") or "").strip()
        desc = str(data.get("Description")).strip() if data.get("Description") else None
        coverage = data.get("CoverageLim")
        try:
            coverage_val = float(coverage) if coverage not in (None, "") else None
        except Exception:
            return Response({"error": {"CoverageLim": "Must be numeric"}}, status=status.HTTP_400_BAD_REQUEST)
        status_val = str(data.get("status") or "").strip() or "Active"

        # Generate next CustomerPlanID
        try:
            last = CustomerPlan.objects.order_by("-CustomerPlanID").first()
            last_id = None
            if last:
                last_id = getattr(last, "CustomerPlanID", None)
                if last_id is None and hasattr(last, "_data"):
                    last_id = last._data.get("CustomerPlanID") or last._data.get("customerPlanID")
            next_cpid = (int(last_id) + 1) if last_id is not None else 1
        except Exception:
            next_cpid = 1

        start_dt = timezone.now()
        end_dt = start_dt + timedelta(days=365)

        # Resolve the logged-in Agent's AgentID (to set assignedAgentID on the plan)
        agent_id_for_assignment = None
        try:
            ag = Agent.objects(UserID=user.userid).first()
            if ag and getattr(ag, "AgentID", None) is not None:
                agent_id_for_assignment = int(getattr(ag, "AgentID"))
        except Exception:
            agent_id_for_assignment = None

        try:
            plan = CustomerPlan(
                CustomerPlanID=next_cpid,
                CustomerID=customer_id,
                StartDate=start_dt,
                EndDate=end_dt,
                CurrentPremium=base_price,
                Status=status_val,
                planID=plan_id_val,
            )
            # Optional extras (strict=False allows these)
            if plan_name:
                plan.PlanName = plan_name
            if desc:
                plan.Description = desc
            if coverage_val is not None:
                plan.coverageLim = coverage_val
            if agent_id_for_assignment is not None:
                # Persist assignment by AgentID on the customer plan so agents can later see it
                setattr(plan, "assignedAgentID", agent_id_for_assignment)
            plan.save()
        except Exception as e:
            msg = "Unable to create customer plan"
            if settings.DEBUG:
                msg = f"Create failed: {e}"
            return Response({"error": msg}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(
            {
                "created": True,
                "customerPlanID": next_cpid,
                "CustomerID": customer_id,
                "planID": plan_id_val,
                "Status": status_val,
                "CurrentPremium": base_price,
                "StartDate": start_dt.isoformat(),
                "EndDate": end_dt.isoformat(),
                "PlanName": plan_name or None,
                "Description": desc or None,
                "CoverageLim": coverage_val,
                "assignedAgentID": agent_id_for_assignment,
            },
            status=status.HTTP_201_CREATED,
        )


class ClaimDetailView(APIView):
    """
    Main view for looking at one specific claim. Does read, update, and delete.
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
                    "CustomerPlanID": getattr(claim, "CustomerPlanID", None),
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
                "CustomerPlanID": (lambda v: int(v) if v is not None else None),
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
                    "CustomerPlanID": getattr(c, "CustomerPlanID", None),
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
    Shows a manager all policies they are responsible for.
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
    """

    def get(self, request):
        """
        Determine policies strictly by supervisor -> team -> customers mapping
        using the x-user-id provided.
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
                    # Include assignment info so Manager Overview can group by agent
                    "assignedAgentID": _get_field(cp, 'assignedAgentID', 'AssignedAgentID'),
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

            # Customer plans for these customers that are missing an assigned agent
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

            # Filter plans that have not been assigned to an agent yet
            filtered = []
            for cp in plans:
                # Consider any of these as an assignment marker (support field casing variants)
                has_assign = _get(cp, 'assignedAgentID', 'AssignedAgentID')
                # Treat the following as effectively unassigned:
                # None, empty string, 0/"0", and the string values "null"/"None" (any case)
                unassigned_markers = (None, 0, "", "0")
                if has_assign in unassigned_markers:
                    filtered.append(cp)
                    continue
                try:
                    if isinstance(has_assign, str) and has_assign.strip().lower() in ("null", "none"):
                        filtered.append(cp)
                        continue
                except Exception:
                    pass
                # Otherwise, this plan is considered assigned and excluded
                # from the assignable list.
                # (No action needed when assigned.)
                #
                # Note: we intentionally do not try to coerce non-empty strings
                # to integers here; any non-empty, non-null-like value denotes
                # an existing assignment.

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
    Assign a customer plan (policy) to an agent by setting assignedAgentID on the plan.
    """

    def post(self, request, policy_id: int):
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

            # Use a raw MongoDB update to set assignedAgentID (matches Temp version behavior)
            try:
                print(f"DEBUG: Attempting raw update for Policy {policy_id} -> Agent {agent_user_id}")
                CustomerPlan.objects(id=cp.id).update(__raw__={
                    "$set": {
                        "assignedAgentID": agent_user_id
                    }
                })
                print("DEBUG: Raw update command sent.")
            except Exception as e:
                return Response({"error": f"Failed to update policy assignment: {e}"},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            return Response({"ok": True, "assignedAgentID": agent_user_id}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ManagerPolicyDecisionView(APIView):
    """
    Manager approves or rejects a pending policy.
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
            # Primary: handle CustomerPlan approvals first (per Temp version)
            cplan = CustomerPlan.objects(CustomerPlanID=int(policy_id)).first()
            if cplan:
                # Read status flexibly
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

                raw_status = _get(cplan, 'Status', 'status', default='pending')
                try:
                    current_status = str(raw_status if raw_status is not None else 'pending').strip().lower()
                except Exception:
                    current_status = 'pending'
                if current_status != "pending":
                    return Response({"error": "CustomerPlan is not pending"}, status=status.HTTP_400_BAD_REQUEST)

                # Temp uses "denied" for reject branch
                new_status = "approved" if decision == "approve" else "denied"
                try:
                    # Raw update to avoid field constraints
                    CustomerPlan._get_collection().update_one(
                        {"_id": cplan.id},
                        {"$set": {"Status": new_status, "UpdatedAt": _now_utc()}},
                    )
                except Exception as ue:
                    return Response({"error": f"Failed to update CustomerPlan: {ue}"},
                                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                # Audit log (non-fatal if fails)
                try:
                    AuditLog(
                        LogID=_new_log_id(),
                        ActorUserID=user.userid,
                        Action=f"customerplan_{decision}",
                        TargetType="customerplan",
                        TargetID=str(cplan.CustomerPlanID),
                        Details=None,
                        CreatedAt=_now_utc(),
                    ).save()
                except Exception as _log_err:
                    print(f"[warn] AuditLog save failed (customerplan decision): {_log_err}")

                return Response({"ok": True, "newStatus": new_status}, status=status.HTTP_200_OK)

            # Fallback: legacy Policy object path
            policy = Policy.objects(PolicyID=int(policy_id)).first()
            if not policy:
                return Response({"error": "Policy/CustomerPlan not found"}, status=status.HTTP_404_NOT_FOUND)

            if getattr(policy, 'Status', 'pending') != "pending":
                return Response({"error": "Policy is not pending"}, status=status.HTTP_400_BAD_REQUEST)

            new_status = "approved" if decision == "approve" else "denied"
            try:
                Policy._get_collection().update_one(
                    {"_id": policy.id},
                    {"$set": {"Status": new_status, "UpdatedAt": _now_utc()}},
                )
            except Exception as ue:
                return Response({"error": f"Failed to update Policy: {ue}"},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            try:
                AuditLog(
                    LogID=_new_log_id(),
                    ActorUserID=user.userid,
                    Action=f"policy_{decision}",
                    TargetType="policy",
                    TargetID=str(policy.PolicyID),
                    Details=None,
                    CreatedAt=_now_utc(),
                ).save()
            except Exception as _log_err:
                print(f"[warn] AuditLog save failed (policy decision): {_log_err}")

            return Response({"ok": True, "newStatus": new_status}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminAuditLogView(APIView):
    """
    The 'Big Brother' view. Admins can see the last 500 actions taken in the system.
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

            return Response({"ok": True, "CustomerID": customer.CustomerID, "AssignedAgentUserID": agent_user_id},
                            status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ClaimListCreateView(APIView):
    """
    The main endpoint for getting lists of claims or creating a new one.
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
                    "CustomerPlanID": getattr(c, "CustomerPlanID", None),
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
            customer_plan_id = g("CustomerPlanID", "customerPlanID", "customer_plan_id")
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
            customer_plan_id = int(customer_plan_id) if customer_plan_id is not None and str(
                customer_plan_id) != "" else None

            # If agent creates it, they can assign it to themselves automatically
            assigned_to = int(assigned_to) if assigned_to is not None and str(assigned_to) != "" else (
                user.userid if _is_agent(user) and not is_customer else None)

            amount = float(amount) if amount is not None and str(amount) != "" else None
            item_ids = list(item_ids or [])

            # Check if this ID is already taken
            if Claim.objects(ClaimID=claim_id).first():
                return Response({"error": "ClaimID already exists"}, status=status.HTTP_409_CONFLICT)

            # Ensure we have a valid CustomerPlanID for this claim. If not supplied,
            # try to infer from first item (if items reference a plan).
            plan_doc = None
            if customer_plan_id is not None:
                plan_doc = CustomerPlan.objects(CustomerPlanID=customer_plan_id).first()
                if not plan_doc:
                    return Response({"error": "CustomerPlanID not found"}, status=status.HTTP_400_BAD_REQUEST)
            elif item_ids:
                try:
                    itm = Item.objects(ItemID=int(item_ids[0])).first()
                except Exception:
                    itm = None
                if itm is not None:
                    inferred_cpid = getattr(itm, "CustomerPlanID", None) or (
                        getattr(itm, "_data", {}).get("CustomerPlanID") if hasattr(itm, "_data") else None
                    )
                    if inferred_cpid is not None:
                        customer_plan_id = int(inferred_cpid)
                        plan_doc = CustomerPlan.objects(CustomerPlanID=customer_plan_id).first()
            # If still no plan, require it
            if plan_doc is None:
                return Response({"error": "Missing field: CustomerPlanID"}, status=status.HTTP_400_BAD_REQUEST)

            # Validate that CustomerID matches the plan's owner
            try:
                plan_customer_id = int(getattr(plan_doc, "CustomerID", None) or plan_doc._data.get("CustomerID"))
            except Exception:
                plan_customer_id = None
            if plan_customer_id is not None and int(customer_id) != int(plan_customer_id):
                return Response({"error": "CustomerID does not match the CustomerPlan owner"},
                                status=status.HTTP_400_BAD_REQUEST)

            claim = Claim(
                ClaimID=claim_id,
                CustomerID=customer_id,
                PolicyID=policy_id,
                CustomerPlanID=customer_plan_id,
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