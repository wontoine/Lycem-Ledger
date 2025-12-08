import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { apiUrl } from "../lib/api";

function AgentHomePage() {
  const [sidebaropen, setSidebaropen] = useState(false);
  const [activeTab, setActiveTab] = useState("policies");

  // Stores the list of policies assigned to this agent and claims requiring their attention
  const [myPolicies, setMyPolicies] = useState([]);
  const [claims, setClaims] = useState([]);

  // UI states for loading feedback and error handling
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(null);

  // Interaction states for modals and processing actions
  const [selectedPolicy, setSelectedPolicy] = useState(null);
  const [processing, setProcessing] = useState(false);

  // Per-claim temporary state for storing notes and disabling buttons during API calls
  const [decisionNotes, setDecisionNotes] = useState({});
  const [decisionBusy, setDecisionBusy] = useState({});

  // State for the policy creation form
  const [newPolicyForm, setNewPolicyForm] = useState({
    CustomerID: "",
    PlanID: "",
  });

  // State specifically for custom plan details when "Customized Plan" is selected
  const [customDetails, setCustomDetails] = useState({
    description: "",
    coverage: "",
    price: "",
  });

  // Pre-defined plan options available for agents to sell
  const availablePlans = [
    {
      planID: 1,
      PlanName: "Basic Home",
      Description: "Basic coverage for home structure and liability.",
      CoverageLim: 100000,
      BasePrice: 500,
    },
    {
      planID: 2,
      PlanName: "Auto Premium",
      Description: "Comprehensive coverage for vehicle damage and injury.",
      CoverageLim: 50000,
      BasePrice: 300,
    },
    {
      planID: 3,
      PlanName: "Life Secure",
      Description: "Term life insurance policy.",
      CoverageLim: 250000,
      BasePrice: 150,
    },
    {
      planID: 4,
      PlanName: "Customized Plan",
      Description: "Agent-defined coverage and pricing.",
      CoverageLim: 0,
      BasePrice: 0,
    },
  ];

  const navigate = useNavigate();
  const storedUserID = localStorage.getItem("userID");

  // Redirect to login if user session is invalid
  useEffect(() => {
    if (!storedUserID) {
      navigate("/", { replace: true });
    }
  }, [storedUserID, navigate]);

  // Sidebar navigation items
  const navItems = [
    { id: "policies", name: "My Policies" },
    { id: "claims", name: "Active Claims" },
    { id: "create", name: "Create Policy" },
  ];

  const handleSignOut = () => {
    localStorage.removeItem("userID");
    localStorage.removeItem("userRoleID");
    navigate("/", { replace: true });
  };

  // Fetches initial data for the dashboard: Assigned Policies and Claims
  const fetchData = async () => {
    if (!storedUserID) return;

    setLoading(true);
    setFetchError(null);

    try {
      const headers = {
        "Content-Type": "application/json",
        "x-user-id": String(storedUserID),
      };

      // Fetch both endpoints in parallel for efficiency
      const [policiesRes, claimsRes] = await Promise.all([
        fetch(apiUrl("/api/agent/policies/"), { headers }).catch(
          (err) => ({ ok: false, error: err })
        ),
        fetch(apiUrl("/api/agent/claims/"), { headers }).catch(
          (err) => ({ ok: false, error: err })
        ),
      ]);

      // Process Claims data
      let claimsData = [];
      if (claimsRes.ok) {
        const resJson = await claimsRes.json();
        claimsData = resJson.claims || [];
      } else {
        console.warn("Failed to fetch claims.");
      }

      // Process Policies data
      let policiesData = [];
      if (policiesRes.ok) {
        const resJson = await policiesRes.json();
        policiesData = resJson.policies || [];
      } else {
        console.warn("Failed to fetch policies.");
      }

      setClaims(claimsData);
      setMyPolicies(policiesData);
    } catch (error) {
      console.error("Fetch error:", error);
      setFetchError("Error connecting to server.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storedUserID]);

  // Handles the Agent's decision to Accept or Reject a claim
  const handleClaimDecision = async (claimId, decision) => {
    if (!storedUserID) return;
    const note = (decisionNotes?.[claimId] || "").trim();

    setDecisionBusy((prev) => ({ ...prev, [claimId]: true }));
    try {
      const res = await fetch(
        apiUrl(`/api/claims/${claimId}/decision/`),
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-user-id": String(storedUserID),
          },
          body: JSON.stringify({ decision, note }),
        }
      );

      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        console.error("Decision failed", data);
        alert(
          `Failed to ${decision} claim #${claimId}: ` +
            (data?.error || "Unknown error")
        );
        return;
      }

      // Optimistically update local state to reflect the decision immediately
      setClaims((prev) =>
        (prev || []).map((c) => {
          if (c.ClaimID !== claimId) return c;
          const newStatus = data?.newStatus || c.Status;
          const agentApprovalStatus =
            data?.agentApprovalStatus ||
            (decision === "accept" ? "approved" : "rejected");
          const agentStatusNote =
            data?.agentStatusNote !== undefined
              ? data.agentStatusNote
              : note || c.agentStatusNote;
          return {
            ...c,
            Status: newStatus,
            agentApprovalStatus,
            agentStatusNote,
          };
        })
      );

      // Clear the note input for this claim
      setDecisionNotes((prev) => ({ ...prev, [claimId]: "" }));
    } catch (err) {
      console.error("Network error submitting decision", err);
      alert("Network error submitting decision.");
    } finally {
      setDecisionBusy((prev) => ({ ...prev, [claimId]: false }));
    }
  };

  // Handles creation of a new policy for a customer
  const handleCreatePolicy = async (e) => {
    e.preventDefault();
    setProcessing(true);

    const selectedPlan = availablePlans.find(
      (p) => Number(p.planID) === Number(newPolicyForm.PlanID)
    );

    if (!selectedPlan) {
      alert("Invalid plan selected");
      setProcessing(false);
      return;
    }

    let payload = {
      userID: parseInt(newPolicyForm.CustomerID),
      planID: parseInt(selectedPlan.planID),
      PlanName: selectedPlan.PlanName,
      status: "pending",
    };

    // Use custom details if the "Customized Plan" option is selected
    if (Number(selectedPlan.planID) === 4) {
      payload.Description = customDetails.description;
      payload.CoverageLim = parseFloat(customDetails.coverage);
      payload.BasePrice = parseFloat(customDetails.price);
    } else {
      payload.Description = selectedPlan.Description;
      payload.CoverageLim = selectedPlan.CoverageLim;
      payload.BasePrice = selectedPlan.BasePrice;
    }

    try {
      const response = await fetch(
        apiUrl("/api/agent/create-plan/"),
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-user-id": String(storedUserID),
          },
          body: JSON.stringify(payload),
        }
      );

      const data = await response.json();

      if (response.ok) {
        alert(`Policy Created Successfully! ID: ${data.customerPlanID}`);
        // Reset form fields
        setNewPolicyForm({ CustomerID: "", PlanID: "" });
        setCustomDetails({ description: "", coverage: "", price: "" });
        // Refresh data and switch view to the policies list
        await fetchData();
        setActiveTab("policies");
      } else {
        console.error("Creation failed:", data);
        alert(
          `Error: ${
            data.error ? JSON.stringify(data.error) : "Failed to create policy"
          }`
        );
      }
    } catch (error) {
      console.error("Network error:", error);
      alert("Network error: Could not reach the server.");
    } finally {
      setProcessing(false);
    }
  };

  // --- Component Renderers ---

  // Renders the modal showing detailed info about a selected policy
  const PolicyDetailsModal = ({ policy, onClose }) => {
    if (!policy) return null;
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center p-4">
        <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden animate-fade-in-up">
          <div className="bg-blue-600 p-6 flex justify-between items-start text-white">
            <div>
              <h2 className="text-2xl font-bold">{policy.PlanName}</h2>
              <p className="text-blue-100">Policy #{policy.PolicyID}</p>
            </div>
            <button
              onClick={onClose}
              className="text-white hover:text-blue-200 text-2xl"
            >
              ×
            </button>
          </div>
          <div className="p-6 space-y-4">
            <div>
              <label className="text-xs font-bold text-gray-400 uppercase">
                Description
              </label>
              <p className="text-gray-700">{policy.Description}</p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-gray-50 p-3 rounded-lg">
                <label className="text-xs font-bold text-gray-400 uppercase">
                  Customer ID
                </label>
                <p className="text-gray-800 font-mono">{policy.CustomerID}</p>
              </div>
              <div className="bg-gray-50 p-3 rounded-lg">
                <label className="text-xs font-bold text-gray-400 uppercase">
                  Status
                </label>
                <p
                  className={`font-bold ${
                    (policy.Status || "").toLowerCase() === "active" ||
                    (policy.Status || "").toLowerCase() === "approved"
                      ? "text-green-600"
                      : "text-yellow-600"
                  }`}
                >
                  {policy.Status}
                </p>
              </div>
              <div className="bg-gray-50 p-3 rounded-lg">
                <label className="text-xs font-bold text-gray-400 uppercase">
                  Coverage Limit
                </label>
                <p className="text-gray-800">
                  ${policy.CoverageLim?.toLocaleString()}
                </p>
              </div>
              <div className="bg-gray-50 p-3 rounded-lg">
                <label className="text-xs font-bold text-gray-400 uppercase">
                  Base Price
                </label>
                <p className="text-gray-800">
                  ${policy.BasePrice?.toLocaleString()}
                </p>
              </div>
            </div>
          </div>
          <div className="p-4 bg-gray-50 text-right">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    );
  };

  // Renders the list of policies assigned to the agent
  const renderPoliciesTab = () => (
    <div>
      <h2 className="text-2xl font-bold text-gray-800 mb-6">
        My Assigned Policies
      </h2>
      {myPolicies.length === 0 ? (
        <div className="text-center p-12 bg-white rounded-xl border border-dashed border-gray-300 text-gray-400">
          No policies assigned yet.
        </div>
      ) : (
        <div className="grid sm:grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {myPolicies.map((policy) => (
            <div
              key={policy.PolicyID}
              onClick={() => setSelectedPolicy(policy)}
              className="bg-white p-6 shadow-lg rounded-xl border border-blue-100 hover:shadow-2xl hover:-translate-y-1 transition duration-200 cursor-pointer group"
            >
              <div className="flex justify-between items-start mb-4">
                <h3 className="text-lg font-extrabold text-gray-800 group-hover:text-blue-600 transition">
                  {policy.PlanName}
                </h3>
                <span
                  className={`px-2 py-1 rounded text-xs font-bold uppercase ${
                    (policy.Status || "").toLowerCase() === "active" ||
                    (policy.Status || "").toLowerCase() === "approved"
                      ? "bg-green-100 text-green-700"
                      : "bg-yellow-100 text-yellow-700"
                  }`}
                >
                  {policy.Status}
                </span>
              </div>
              <p className="text-sm text-gray-500 mb-4 line-clamp-2">
                {policy.Description}
              </p>
              <div className="flex justify-between items-center text-sm text-gray-600 border-t pt-4">
                <span>ID: {policy.PolicyID}</span>
                <span className="text-blue-600 font-semibold">
                  View Details →
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  // Renders the Claims Dashboard, split into Pending and History sections
  const renderClaimsTab = () => {
    // Filter logic: Separate pending claims from those already processed
    const pendingClaims = claims.filter(
      (c) =>
        !c.agentApprovalStatus ||
        c.agentApprovalStatus.toLowerCase() === "pending"
    );

    const pastClaims = claims.filter(
      (c) =>
        c.agentApprovalStatus &&
        c.agentApprovalStatus.toLowerCase() !== "pending"
    );

    return (
      <div className="max-w-6xl mx-auto space-y-12">
        {/* Section 1: Claims to be Approved (Pending) */}
        <section>
          <h2 className="text-2xl font-bold text-gray-800 mb-4 flex items-center gap-2">
            <span>📝</span> Pending Reviews
            <span className="text-sm font-normal text-gray-500 bg-gray-200 px-2 py-1 rounded-full">
              {pendingClaims.length}
            </span>
          </h2>

          <div className="bg-white rounded-xl shadow-lg overflow-hidden border border-gray-200">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-gray-600">
                <thead className="bg-gray-100 uppercase text-gray-500 font-bold">
                  <tr>
                    <th className="p-4">Claim ID</th>
                    <th className="p-4">Policy / Plan</th>
                    <th className="p-4">Reason</th>
                    <th className="p-4">Amount</th>
                    <th className="p-4">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingClaims.length === 0 ? (
                    <tr>
                      <td colSpan="5" className="p-8 text-center text-gray-400">
                        No claims waiting for review. Good job!
                      </td>
                    </tr>
                  ) : (
                    pendingClaims.map((claim) => (
                      <tr
                        key={claim.ClaimID}
                        className="border-b hover:bg-gray-50 transition"
                      >
                        <td className="p-4 font-mono font-bold text-gray-700">
                          #{claim.ClaimID}
                        </td>
                        <td className="p-4 font-mono">
                          {claim.CustomerPlanID || claim.PolicyID}
                        </td>
                        <td className="p-4 max-w-xs truncate">
                          {claim.Reason}
                        </td>
                        <td className="p-4 font-semibold text-gray-800">
                          ${claim.Amount?.toLocaleString()}
                        </td>
                        <td className="p-4">
                          <div className="flex flex-col gap-2 min-w-[220px]">
                            <input
                              type="text"
                              placeholder="Reason / Note (Optional)"
                              className="w-full p-2 border border-gray-300 rounded text-xs"
                              value={decisionNotes?.[claim.ClaimID] || ""}
                              onChange={(e) =>
                                setDecisionNotes((prev) => ({
                                  ...prev,
                                  [claim.ClaimID]: e.target.value,
                                }))
                              }
                              disabled={!!decisionBusy?.[claim.ClaimID]}
                            />
                            <div className="flex gap-2">
                              <button
                                className={`flex-1 py-1.5 rounded text-white text-xs font-bold shadow-sm transition ${
                                  decisionBusy?.[claim.ClaimID]
                                    ? "bg-green-300 cursor-not-allowed"
                                    : "bg-green-600 hover:bg-green-700"
                                }`}
                                onClick={() =>
                                  handleClaimDecision(claim.ClaimID, "accept")
                                }
                                disabled={!!decisionBusy?.[claim.ClaimID]}
                              >
                                Approve
                              </button>
                              <button
                                className={`flex-1 py-1.5 rounded text-white text-xs font-bold shadow-sm transition ${
                                  decisionBusy?.[claim.ClaimID]
                                    ? "bg-red-300 cursor-not-allowed"
                                    : "bg-red-600 hover:bg-red-700"
                                }`}
                                onClick={() =>
                                  handleClaimDecision(claim.ClaimID, "reject")
                                }
                                disabled={!!decisionBusy?.[claim.ClaimID]}
                              >
                                Reject
                              </button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* Section 2: Past Claims (History) */}
        <section>
          <h2 className="text-2xl font-bold text-gray-800 mb-4 flex items-center gap-2">
            <span>🗄️</span> Past Claims
            <span className="text-sm font-normal text-gray-500 bg-gray-200 px-2 py-1 rounded-full">
              {pastClaims.length}
            </span>
          </h2>

          <div className="bg-gray-50 rounded-xl shadow-inner border border-gray-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-gray-600">
                <thead className="bg-gray-200 uppercase text-gray-600 font-bold">
                  <tr>
                    <th className="p-4">Claim ID</th>
                    <th className="p-4">Plan ID</th>
                    <th className="p-4">Reason</th>
                    <th className="p-4">Amount</th>
                    <th className="p-4">Agent Decision</th>
                    <th className="p-4">Manager Status</th>
                  </tr>
                </thead>
                <tbody>
                  {pastClaims.length === 0 ? (
                    <tr>
                      <td colSpan="6" className="p-8 text-center text-gray-400">
                        No history available.
                      </td>
                    </tr>
                  ) : (
                    pastClaims.map((claim) => (
                      <tr
                        key={claim.ClaimID}
                        className="border-b border-gray-200 hover:bg-white transition"
                      >
                        <td className="p-4 font-mono font-bold text-gray-600">
                          #{claim.ClaimID}
                        </td>
                        <td className="p-4 font-mono">
                          {claim.CustomerPlanID || claim.PolicyID}
                        </td>
                        <td className="p-4 max-w-xs truncate">
                          {claim.Reason}
                        </td>
                        <td className="p-4 text-gray-800">
                          ${claim.Amount?.toLocaleString()}
                        </td>
                        <td className="p-4">
                          <div className="flex flex-col">
                            <span
                              className={`text-xs font-bold uppercase ${
                                (
                                  claim.agentApprovalStatus || ""
                                ).toLowerCase() === "approved"
                                  ? "text-green-600"
                                  : "text-red-600"
                              }`}
                            >
                              {claim.agentApprovalStatus || "Unknown"}
                            </span>
                            {claim.agentStatusNote && (
                              <span className="text-[10px] text-gray-400 italic truncate max-w-[150px]">
                                {claim.agentStatusNote}
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="p-4">
                          <span
                            className={`px-2 py-1 rounded text-xs font-bold uppercase ${
                              (
                                claim.managerApprovalStatus || ""
                              ).toLowerCase() === "approved"
                                ? "bg-green-100 text-green-700"
                                : (
                                    claim.managerApprovalStatus || ""
                                  ).toLowerCase() === "rejected"
                                ? "bg-red-100 text-red-700"
                                : "bg-yellow-100 text-yellow-700"
                            }`}
                          >
                            {claim.managerApprovalStatus ||
                              (claim.Status === "accepted"
                                ? "Approved"
                                : claim.Status === "rejected"
                                ? "Rejected"
                                : "Pending")}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>
    );
  };

  // Renders the form to create a new policy
  const renderCreateTab = () => {
    const isCustomPlan = Number(newPolicyForm.PlanID) === 4;
    const isValid =
      newPolicyForm.PlanID &&
      newPolicyForm.CustomerID &&
      (!isCustomPlan ||
        (customDetails.description &&
          customDetails.price &&
          customDetails.coverage));

    return (
      <div className="max-w-2xl mx-auto">
        <h2 className="text-2xl font-bold text-gray-800 mb-6">
          Create New Policy
        </h2>
        <div className="bg-white p-8 rounded-xl shadow-lg border border-gray-200">
          <form onSubmit={handleCreatePolicy} className="space-y-6">
            <div>
              <label className="block text-sm font-bold text-gray-700 mb-2">
                Customer ID
              </label>
              <input
                type="number"
                required
                placeholder="e.g. 456"
                className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
                value={newPolicyForm.CustomerID}
                onChange={(e) =>
                  setNewPolicyForm({
                    ...newPolicyForm,
                    CustomerID: e.target.value,
                  })
                }
              />
            </div>
            <div>
              <label className="block text-sm font-bold text-gray-700 mb-2">
                Select Plan
              </label>
              <div className="grid gap-4">
                {availablePlans.map((plan) => (
                  <div
                    key={plan.planID}
                    onClick={() =>
                      setNewPolicyForm({
                        ...newPolicyForm,
                        PlanID: plan.planID,
                      })
                    }
                    className={`p-4 rounded-lg border-2 cursor-pointer transition flex justify-between items-center ${
                      Number(newPolicyForm.PlanID) === plan.planID
                        ? "border-blue-600 bg-blue-50"
                        : "border-gray-200 hover:border-blue-300"
                    }`}
                  >
                    <div>
                      <h4 className="font-bold text-gray-800">
                        {plan.PlanName}
                      </h4>
                      <p className="text-xs text-gray-500">
                        {plan.Description}
                      </p>
                    </div>
                    {plan.planID !== 4 && (
                      <div className="text-right">
                        <p className="font-bold text-blue-600">
                          ${plan.BasePrice}/mo
                        </p>
                        <p className="text-xs text-gray-400">
                          Limit: ${plan.CoverageLim.toLocaleString()}
                        </p>
                      </div>
                    )}
                    {plan.planID === 4 && (
                      <div className="text-right text-xs font-bold text-blue-600 uppercase">
                        Configure Manually
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {isCustomPlan && (
              <div className="bg-blue-50 p-4 rounded-lg border border-blue-100 space-y-4 animate-fade-in">
                <h4 className="text-sm font-bold text-blue-800 border-b border-blue-200 pb-2">
                  Custom Plan Details
                </h4>
                <div>
                  <label className="block text-xs font-semibold text-blue-700 mb-1">
                    Description
                  </label>
                  <input
                    type="text"
                    required={isCustomPlan}
                    placeholder="Specific coverage details..."
                    className="w-full p-2 border border-blue-200 rounded focus:outline-none focus:border-blue-500"
                    value={customDetails.description}
                    onChange={(e) =>
                      setCustomDetails({
                        ...customDetails,
                        description: e.target.value,
                      })
                    }
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-blue-700 mb-1">
                      Base Price ($)
                    </label>
                    <input
                      type="number"
                      required={isCustomPlan}
                      placeholder="e.g. 600"
                      className="w-full p-2 border border-blue-200 rounded focus:outline-none focus:border-blue-500"
                      value={customDetails.price}
                      onChange={(e) =>
                        setCustomDetails({
                          ...customDetails,
                          price: e.target.value,
                        })
                      }
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-blue-700 mb-1">
                      Coverage Limit ($)
                    </label>
                    <input
                      type="number"
                      required={isCustomPlan}
                      placeholder="e.g. 150000"
                      className="w-full p-2 border border-blue-200 rounded focus:outline-none focus:border-blue-500"
                      value={customDetails.coverage}
                      onChange={(e) =>
                        setCustomDetails({
                          ...customDetails,
                          coverage: e.target.value,
                        })
                      }
                    />
                  </div>
                </div>
              </div>
            )}

            <button
              type="submit"
              disabled={!isValid || processing}
              className={`w-full py-3 rounded-lg font-bold text-white transition shadow-md ${
                !isValid || processing
                  ? "bg-gray-400 cursor-not-allowed"
                  : "bg-blue-600 hover:bg-blue-700 transform active:scale-95"
              }`}
            >
              {processing ? "Creating Policy..." : "Create Policy"}
            </button>
          </form>
        </div>
      </div>
    );
  };

  return (
    <div className="flex bg-gray-100 min-h-screen font-sans">
      {/* Sidebar Navigation */}
      <div
        className={`fixed inset-y-0 left-0 bg-white w-64 shadow-2xl transform transition-transform duration-300 ease-in-out z-40 ${
          sidebaropen ? "translate-x-0" : "-translate-x-full"
        } lg:static lg:translate-x-0 lg:shadow-none border-r border-gray-200`}
      >
        <div className="p-6 flex justify-between items-center border-b border-gray-100">
          <div className="text-2xl font-extrabold text-blue-700 tracking-tight">
            Agent Portal
          </div>
          <button
            className="lg:hidden text-gray-500"
            onClick={() => setSidebaropen(false)}
          >
            ✕
          </button>
        </div>
        <nav className="p-4 space-y-2">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={`flex items-center w-full text-left p-3 rounded-lg transition duration-150 group ${
                activeTab === item.id
                  ? "bg-blue-50 text-blue-700 border-r-4 border-blue-600"
                  : "text-gray-600 hover:bg-gray-50 hover:text-blue-600"
              }`}
              onClick={() => {
                setActiveTab(item.id);
                setSidebaropen(false);
              }}
            >
              <span className="font-semibold">{item.name}</span>
            </button>
          ))}
        </nav>
        <div className="absolute bottom-6 left-0 w-full px-6">
          <button
            onClick={handleSignOut}
            className="w-full flex items-center justify-center gap-2 py-2 px-4 bg-red-50 text-red-600 font-semibold rounded-lg hover:bg-red-100 transition duration-200"
          >
            <span>🚪</span> Sign Out
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col h-screen overflow-hidden">
        <header className="bg-white shadow-sm z-30 p-4 flex items-center justify-between lg:justify-end">
          <button
            className="lg:hidden p-2 text-gray-600"
            onClick={() => setSidebaropen(true)}
          >
            ☰
          </button>
          <div className="flex items-center gap-6 mr-auto lg:mr-0 lg:ml-auto">
            <button
              onClick={fetchData}
              className="text-sm text-blue-600 hover:underline flex items-center gap-1"
            >
              ↻ Refresh Data
            </button>
            <div className="flex items-center gap-3 py-1 px-3 bg-gray-50 rounded-xl border border-gray-200">
              <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-bold border border-blue-200 text-sm">
                A
              </div>
              <div>
                <p className="text-sm font-bold text-gray-700 leading-none">
                  Agent
                </p>
                <p className="text-xs text-gray-400 leading-none mt-1">
                  ID: {storedUserID}
                </p>
              </div>
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-6 lg:p-10">
          {fetchError && (
            <div className="bg-yellow-50 border-l-4 border-yellow-500 text-yellow-700 p-4 mb-6 rounded shadow-sm flex justify-between items-center">
              <div>
                <p className="font-bold">Connection Status</p>
                <p className="text-sm">{fetchError}</p>
              </div>
              <button onClick={fetchData} className="text-xs underline">
                Retry
              </button>
            </div>
          )}
          {loading ? (
            <div className="flex justify-center items-center h-64 flex-col gap-4 text-gray-400">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
              <p>Loading Dashboard...</p>
            </div>
          ) : (
            <>
              {activeTab === "policies" && renderPoliciesTab()}
              {activeTab === "claims" && renderClaimsTab()}
              {activeTab === "create" && renderCreateTab()}
            </>
          )}
        </div>
      </main>

      {selectedPolicy && (
        <PolicyDetailsModal
          policy={selectedPolicy}
          onClose={() => setSelectedPolicy(null)}
        />
      )}
    </div>
  );
}

export default AgentHomePage;