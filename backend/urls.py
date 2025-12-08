"""
Main URL Configuration for the Backend API.
Routes requests to specific views for Authentication, Claims, Policies, and Role-based Dashboards.
"""

from django.contrib import admin
from django.urls import path, include
from . import views
from .claims_views import (
    AgentClaimsDashboard,
    AgentPoliciesView,
    ClaimDetailView,
    ClaimDecisionView,
    ClaimListCreateView,
    SupervisorClaimsReviewList,
    SupervisorClaimDecisionView,
    ManagerEmployeesView,
    ManagerUnassignedCustomersView,
    ManagerPoliciesView,
    ManagerPendingPoliciesView,
    ManagerAssignablePoliciesView,
    ManagerAssignPolicyView,
    ManagerPolicyDecisionView,
    ManagerAssignCustomerView,
    AdminAuditLogView,
    ItemListCreateView,
    ItemDetailView,
    PolicyListCreateView,
    PolicyDetailView,
    AgentCreatePlanView,
)

urlpatterns = [
    # --- System & Administration ---
    path("admin/", admin.site.urls),
    path("api/hello/", views.HelloWorldView.as_view(), name="hello"),
    path("api/health/", views.HealthCheckView.as_view(), name="health"),

    # --- Authentication ---
    # Primary authentication routes (Login, Register, Password Reset)
    path("api/auth/", include("authentication.urls")),
    # Alias route to support frontend clients requesting via root /auth/
    path("auth/", include("authentication.urls")),

    # --- Claims Workflow (Agent & Customer) ---
    # General CRUD for claims (Listing and Submission)
    path("api/claims/", ClaimListCreateView.as_view(), name="claims-list-create"),
    # Agent-specific dashboard to see assigned claims
    path("api/agent/claims/", AgentClaimsDashboard.as_view(), name="agent-claims"),
    # Agent-specific view of assigned policies
    path("api/agent/policies/", AgentPoliciesView.as_view(), name="agent-policies"),
    # Specific Claim Details (Get/Update/Delete)
    path("api/claims/<int:claim_id>/", ClaimDetailView.as_view(), name="claim-detail"),
    # Agent decision endpoint (Approve/Reject to move claim to review)
    path("api/claims/<int:claim_id>/decision/", ClaimDecisionView.as_view(), name="claim-decision"),

    # --- Supervisor/Manager Claim Review ---
    # List claims that have been approved by agents and await final manager approval
    path("api/supervisor/claims/", SupervisorClaimsReviewList.as_view(), name="supervisor-claims"),
    # Final decision endpoint for Managers (Final Approve/Deny)
    path("api/supervisor/claims/<int:claim_id>/decision/", SupervisorClaimDecisionView.as_view(), name="supervisor-claim-decision"),

    # --- Asset/Item Management ---
    # CRUD for items insured under a policy
    path("api/items/", ItemListCreateView.as_view(), name="items-list-create"),
    path("api/items/<int:item_id>/", ItemDetailView.as_view(), name="item-detail"),

    # --- Policy Management ---
    # General Policy CRUD
    path("api/policies/", PolicyListCreateView.as_view(), name="policies-list-create"),
    # Detailed view for a specific policy (used by Managers)
    path("api/manager/policies/<int:etc>/", PolicyDetailView.as_view(), name="policy-detail"),
    # Agent endpoint to create a new policy/plan for a customer
    path("api/agent/createPlan/", AgentCreatePlanView.as_view(), name="agent-create-plan"),
    # Alias for frontend consistency (kebab-case)
    path("api/agent/create-plan/", AgentCreatePlanView.as_view(), name="agent-create-plan-dashed"),

    # --- Manager Dashboard (Team & Assignments) ---
    # View direct reports (agents)
    path("api/manager/employees/", ManagerEmployeesView.as_view(), name="manager-employees"),
    # View customers not yet assigned to an agent
    path("api/manager/customers/unassigned/", ManagerUnassignedCustomersView.as_view(), name="manager-unassigned-customers"),
    # View all policies under the manager's purview
    path("api/manager/policies/", ManagerPoliciesView.as_view(), name="manager-policies"),
    # View policies pending creation approval
    path("api/manager/policies/pending/", ManagerPendingPoliciesView.as_view(), name="manager-policies-pending"),
    # View policies that need an agent assignment
    path("api/manager/policies/assignable/", ManagerAssignablePoliciesView.as_view(), name="manager-policies-assignable"),
    # Action: Assign a policy to an agent
    path("api/manager/policies/<int:policy_id>/assign/", ManagerAssignPolicyView.as_view(), name="manager-assign-policy"),
    # Action: Approve/Reject a new policy application
    path("api/manager/policies/<int:policy_id>/decision/", ManagerPolicyDecisionView.as_view(), name="manager-policy-decision"),
    # Action: Assign a customer to an agent
    path("api/manager/customers/<int:customer_id>/assign/", ManagerAssignCustomerView.as_view(), name="manager-assign-customer"),

    # --- Audit Logs ---
    # Admin-only view of system actions
    path("api/admin/audit-logs/", AdminAuditLogView.as_view(), name="admin-audit-logs"),
]