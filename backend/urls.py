"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from . import views
from .claims_views import (
    AgentClaimsDashboard,
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
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/hello/", views.HelloWorldView.as_view(), name="hello"),
    # Authentication routes handled by the authentication app
    path("api/auth/", include("authentication.urls")),
    # Alias without the /api prefix to support clients using /auth/... endpoints
    path("auth/", include("authentication.urls")),
    path("api/health/", views.HealthCheckView.as_view(), name="health"),
    # Claims and management endpoints
    # Claims CRUD
    path("api/claims/", ClaimListCreateView.as_view(), name="claims-list-create"),
    path("api/agent/claims/", AgentClaimsDashboard.as_view(), name="agent-claims"),
    path("api/claims/<int:claim_id>/", ClaimDetailView.as_view(), name="claim-detail"),
    path("api/claims/<int:claim_id>/decision/", ClaimDecisionView.as_view(), name="claim-decision"),
    # Supervisor review endpoints
    path("api/supervisor/claims/", SupervisorClaimsReviewList.as_view(), name="supervisor-claims"),
    path("api/supervisor/claims/<int:claim_id>/decision/", SupervisorClaimDecisionView.as_view(), name="supervisor-claim-decision"),
    # Items CRUD
    path("api/items/", ItemListCreateView.as_view(), name="items-list-create"),
    path("api/items/<int:item_id>/", ItemDetailView.as_view(), name="item-detail"),
    # Policies CRUD + manager approval endpoints
    path("api/policies/", PolicyListCreateView.as_view(), name="policies-list-create"),
    path("api/policies/<int:policy_id>/", PolicyDetailView.as_view(), name="policy-detail"),
    path("api/manager/employees/", ManagerEmployeesView.as_view(), name="manager-employees"),
    path("api/manager/customers/unassigned/", ManagerUnassignedCustomersView.as_view(), name="manager-unassigned-customers"),
    path("api/manager/policies/", ManagerPoliciesView.as_view(), name="manager-policies"),
    path("api/manager/policies/pending/", ManagerPendingPoliciesView.as_view(), name="manager-policies-pending"),
    path("api/manager/policies/assignable/", ManagerAssignablePoliciesView.as_view(), name="manager-policies-assignable"),
    path("api/manager/policies/<int:policy_id>/assign/", ManagerAssignPolicyView.as_view(), name="manager-assign-policy"),
    path("api/manager/policies/<int:policy_id>/decision/", ManagerPolicyDecisionView.as_view(), name="manager-policy-decision"),
    path("api/manager/customers/<int:customer_id>/assign/", ManagerAssignCustomerView.as_view(), name="manager-assign-customer"),
    path("api/admin/audit-logs/", AdminAuditLogView.as_view(), name="admin-audit-logs"),
]
