import React, { useState, useEffect } from "react";

// --- Component Definition ---

function ManagerHomePage() {
  const [sidebaropen, setSidebaropen] = useState(false);
  const [activeTab, setActiveTab] = useState("approvals"); // 'approvals', 'assign', 'overview'

  // Data States
  const [pendingPolicies, setPendingPolicies] = useState([]);
  const [agents, setAgents] = useState([]);
  const [allPolicies, setAllPolicies] = useState([]); // For the overview/assign tabs
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(null);

  const storedUserID = localStorage.getItem("userID") || "3"; // Defaulting to 3 for manager testing

  // Navigation Items adapted for Manager
  const navItems = [
    { id: "approvals", name: "Pending Approvals", icon: "🛡️" },
    { id: "assign", name: "Assign Policies", icon: "👤" },
    { id: "overview", name: "Agent Overview", icon: "📊" },
  ];

  // --- Data Fetching ---
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const headers = {
          "Content-Type": "application/json",
          "x-user-id": String(storedUserID),
        };

        // 1. Fetch Pending Policies (For approval dashboard)
        // Uses ManagerPendingPoliciesView
        const pendingRes = await fetch(
          "http://127.0.0.1:8000/api/manager/policies/pending/",
          { headers }
        );
        const pendingData = await pendingRes.json();

        // 2. Fetch Agents (For assignment dropdowns)
        // Uses ManagerEmployeesView
        const agentsRes = await fetch(
          "http://127.0.0.1:8000/api/manager/employees/",
          { headers }
        );
        const agentsData = await agentsRes.json();

        // 3. Fetch All Policies (For assignment logic - assuming a general list view exists)
        // Using the general PolicyListCreateView but filtered for logic
        const allPolRes = await fetch("http://127.0.0.1:8000/api/policies/", {
          headers,
        });
        const allPolData = await allPolRes.json();

        // State Updates with Fallback Mock Data if backend is empty/down
        setPendingPolicies(
          pendingData.policies || [
            {
              PolicyID: 901,
              CustomerID: 456,
              Status: "pending",
              CreatedAt: "2025-11-13",
              policy_name: "Home Bundle A",
            },
            {
              PolicyID: 902,
              CustomerID: 457,
              Status: "pending",
              CreatedAt: "2025-11-14",
              policy_name: "Auto Ops",
            },
          ]
        );

        setAgents(
          agentsData.employees || [
            { userid: 101, username: "agent_smith", role: "agent" },
            { userid: 102, username: "agent_doe", role: "agent" },
          ]
        );

        setAllPolicies(allPolData.policies || []);
        setFetchError(null);
      } catch (error) {
        console.error("Fetch error:", error);
        setFetchError("Could not load manager data. Using offline mode.");
        // Mocks for offline testing
        setPendingPolicies([
          {
            PolicyID: 901,
            CustomerID: 456,
            Status: "pending",
            CreatedAt: "2025-11-13",
            policy_name: "Home Bundle A",
          },
          {
            PolicyID: 902,
            CustomerID: 457,
            Status: "pending",
            CreatedAt: "2025-11-14",
            policy_name: "Auto Ops",
          },
        ]);
        setAgents([
          { userid: 101, username: "Agent Smith", role: "agent" },
          { userid: 102, username: "Agent Doe", role: "agent" },
        ]);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [storedUserID]);

  // --- Actions ---

  const handleDecision = async (policyId, decision) => {
    try {
      const response = await fetch(
        `http://127.0.0.1:8000/api/policies/${policyId}/decision/`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-user-id": String(storedUserID),
          },
          body: JSON.stringify({ decision: decision }), // 'approve' or 'reject'
        }
      );

      if (response.ok) {
        // Remove the policy from the local list upon success
        setPendingPolicies((prev) =>
          prev.filter((p) => p.PolicyID !== policyId)
        );
        alert(`Policy ${policyId} ${decision}d successfully.`);
      } else {
        alert("Failed to submit decision.");
      }
    } catch (err) {
      console.error(err);
      alert("Network error submitting decision.");
    }
  };

  const handleAssignAgent = (policyId, agentId) => {
    // NOTE: You need to implement an endpoint for this, e.g., PATCH /api/policies/{id}/assign
    console.log(`Assigning Policy ${policyId} to Agent ${agentId}`);
    alert(`Simulated: Assigned Policy ${policyId} to Agent ID ${agentId}`);

    // Update local state to reflect assignment (for demo purposes)
    setAllPolicies((prev) =>
      prev.map((p) =>
        p.PolicyID === policyId ? { ...p, AssignedAgentID: agentId } : p
      )
    );
  };

  // --- Renderers ---

  const renderApprovalCard = (policy) => (
    <div
      key={policy.PolicyID}
      className="bg-white p-6 shadow-lg rounded-xl border border-blue-100 flex flex-col justify-between"
    >
      <div>
        <div className="flex justify-between items-start mb-4">
          <h2 className="text-xl font-extrabold text-blue-700 truncate">
            {policy.policy_name || `Policy #${policy.PolicyID}`}
          </h2>
          <span className="bg-yellow-100 text-yellow-800 text-xs font-bold px-2 py-1 rounded-full uppercase">
            {policy.Status}
          </span>
        </div>
        <p className="text-sm text-gray-600 mb-1">
          Customer ID: <span className="font-mono">{policy.CustomerID}</span>
        </p>
        <p className="text-sm text-gray-500 mb-4">
          Created: {new Date(policy.CreatedAt).toLocaleDateString()}
        </p>
      </div>

      <div className="flex gap-3 mt-4">
        <button
          onClick={() => handleDecision(policy.PolicyID, "approve")}
          className="flex-1 bg-green-500 hover:bg-green-600 text-white font-bold py-2 px-4 rounded-lg transition duration-200 shadow-md"
        >
          Approve
        </button>
        <button
          onClick={() => handleDecision(policy.PolicyID, "reject")}
          className="flex-1 bg-red-500 hover:bg-red-600 text-white font-bold py-2 px-4 rounded-lg transition duration-200 shadow-md"
        >
          Deny
        </button>
      </div>
    </div>
  );

  const renderAssignTab = () => {
    // Filter for policies that might need assignment (example logic)
    const policiesToAssign = allPolicies.filter((p) => !p.AssignedAgentID);

    return (
      <div className="bg-white rounded-xl shadow-lg overflow-hidden border border-gray-200">
        <div className="p-4 border-b bg-gray-50">
          <h3 className="text-lg font-bold text-gray-700">
            Unassigned Policies
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-gray-600">
            <thead className="bg-gray-100 uppercase text-gray-500 font-bold">
              <tr>
                <th className="p-4">Policy ID</th>
                <th className="p-4">Status</th>
                <th className="p-4">Assign To</th>
                <th className="p-4">Action</th>
              </tr>
            </thead>
            <tbody>
              {policiesToAssign.length === 0 ? (
                <tr>
                  <td colSpan="4" className="p-6 text-center">
                    No unassigned policies found.
                  </td>
                </tr>
              ) : (
                policiesToAssign.map((p) => (
                  <tr key={p.PolicyID} className="border-b hover:bg-gray-50">
                    <td className="p-4 font-mono">{p.PolicyID}</td>
                    <td className="p-4">
                      <span className="px-2 py-1 rounded text-xs font-semibold bg-blue-100 text-blue-800">
                        {p.Status}
                      </span>
                    </td>
                    <td className="p-4">
                      <select
                        id={`select-${p.PolicyID}`}
                        className="bg-white border border-gray-300 rounded p-2 w-full focus:ring-2 focus:ring-blue-500"
                      >
                        <option value="">Select Agent...</option>
                        {agents.map((a) => (
                          <option key={a.userid} value={a.userid}>
                            {a.username}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="p-4">
                      <button
                        onClick={() => {
                          const select = document.getElementById(
                            `select-${p.PolicyID}`
                          );
                          if (select.value)
                            handleAssignAgent(p.PolicyID, select.value);
                        }}
                        className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 transition"
                      >
                        Assign
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  const renderOverviewTab = () => {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {agents.map((agent) => {
          // Mock filtering: Find policies assigned to this agent
          // In real app, fetch this relation properly
          const agentPolicies = allPolicies.filter(
            (p) => p.AssignedAgentID == agent.userid
          );

          return (
            <div
              key={agent.userid}
              className="bg-white rounded-xl shadow p-5 border-t-4 border-blue-500"
            >
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-bold text-gray-800">
                  {agent.username}
                </h3>
                <span className="text-sm text-gray-500">
                  ID: {agent.userid}
                </span>
              </div>
              <div className="space-y-2">
                <h4 className="text-xs font-bold uppercase text-gray-400 tracking-wider">
                  Current Assignments
                </h4>
                {agentPolicies.length > 0 ? (
                  <ul className="space-y-1">
                    {agentPolicies.map((p) => (
                      <li
                        key={p.PolicyID}
                        className="flex justify-between text-sm bg-gray-50 p-2 rounded"
                      >
                        <span>Policy #{p.PolicyID}</span>
                        <span className="text-gray-500">{p.Status}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm italic text-gray-400">
                    No active assignments.
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  // --- Main Layout ---
  return (
    <div className="flex bg-gray-100 min-h-screen font-sans">
      {/* Sidebar */}
      <div
        className={`fixed inset-y-0 left-0 bg-white w-64 shadow-2xl transform transition-transform duration-300 ease-in-out z-40 ${
          sidebaropen ? "translate-x-0" : "-translate-x-full"
        } lg:static lg:translate-x-0 lg:shadow-none border-r border-gray-200`}
      >
        <div className="p-6 flex justify-between items-center border-b border-gray-100">
          <div className="text-2xl font-extrabold text-blue-700 tracking-tight">
            Manager Portal
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
              <span className="text-xl mr-3 group-hover:scale-110 transition-transform">
                {item.icon}
              </span>
              <span className="font-semibold">{item.name}</span>
            </button>
          ))}
        </nav>

        <div className="absolute bottom-6 left-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-purple-100 flex items-center justify-center text-purple-700 font-bold border border-purple-200">
              M
            </div>
            <div>
              <p className="text-sm font-bold text-gray-700">Manager</p>
              <p className="text-xs text-gray-400">ID: {storedUserID}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <main className="flex-1 flex flex-col h-screen overflow-hidden">
        <header className="bg-white shadow-sm z-30 p-4 flex items-center justify-between lg:justify-end">
          <button
            className="lg:hidden p-2 text-gray-600"
            onClick={() => setSidebaropen(true)}
          >
            ☰
          </button>
          <h1 className="hidden lg:block text-xl font-bold text-gray-800 mr-auto px-4">
            {navItems.find((n) => n.id === activeTab)?.name}
          </h1>
        </header>

        <div className="flex-1 overflow-y-auto p-6 lg:p-10">
          {fetchError && (
            <div className="bg-red-50 border-l-4 border-red-500 text-red-700 p-4 mb-6 rounded shadow-sm">
              <p className="font-bold">System Notification</p>
              <p>{fetchError}</p>
            </div>
          )}

          {/* TAB CONTENT RENDERER */}
          {loading ? (
            <div className="flex justify-center items-center h-64 text-gray-400">
              Loading Dashboard...
            </div>
          ) : (
            <>
              {activeTab === "approvals" && (
                <div>
                  <h2 className="text-2xl font-bold text-gray-800 mb-6">
                    Approvals Required
                  </h2>
                  {pendingPolicies.length === 0 ? (
                    <div className="text-center p-12 bg-white rounded-xl border border-dashed border-gray-300 text-gray-400">
                      No pending policies found. Good job!
                    </div>
                  ) : (
                    <div className="grid sm:grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                      {pendingPolicies.map(renderApprovalCard)}
                    </div>
                  )}
                </div>
              )}

              {activeTab === "assign" && (
                <div className="max-w-5xl mx-auto">
                  <h2 className="text-2xl font-bold text-gray-800 mb-6">
                    Assign Policies to Agents
                  </h2>
                  {renderAssignTab()}
                </div>
              )}

              {activeTab === "overview" && (
                <div className="max-w-6xl mx-auto">
                  <h2 className="text-2xl font-bold text-gray-800 mb-6">
                    Agent Workload Overview
                  </h2>
                  {renderOverviewTab()}
                </div>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}

export default ManagerHomePage;
