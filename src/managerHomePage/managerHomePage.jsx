import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

function ManagerHomePage() {
  const [sidebaropen, setSidebaropen] = useState(false);
  const [activeTab, setActiveTab] = useState("approvals");
  const [pendingPolicies, setPendingPolicies] = useState([]);
  const [agents, setAgents] = useState([]);
  const [allPolicies, setAllPolicies] = useState([]);
  const [customerPlans, setCustomerPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(null);
  const [processingId, setProcessingId] = useState(null);
  const [assignmentSelections, setAssignmentSelections] = useState({});

  const navigate = useNavigate();

  const storedUserID = localStorage.getItem("userID");

  useEffect(() => {
    if (!storedUserID) {
      navigate("/", { replace: true });
    }
  }, [storedUserID, navigate]);

  const navItems = [
    { id: "approvals", name: "Pending Approvals" },
    { id: "assign", name: "Assign Policies" },
    { id: "overview", name: "Agent Overview" },
  ];

  const handleSignOut = () => {
    localStorage.removeItem("userID");
    localStorage.removeItem("userRoleID");
    navigate("/", { replace: true });
  };

  const fetchData = async () => {
    if (!storedUserID) return;

    setLoading(true);
    setFetchError(null);

    try {
      const headers = {
        "Content-Type": "application/json",
        "x-user-id": String(storedUserID),
      };

      const [pendingRes, agentsRes, allPolRes] = await Promise.all([
        fetch("http://127.0.0.1:8000/api/manager/policies/pending/", {
          headers,
        }),
        fetch("http://127.0.0.1:8000/api/manager/employees/", { headers }),
        fetch("http://127.0.0.1:8000/api/manager/policies/assignable/", {
          headers,
        }),
      ]);

      const pendingData = await pendingRes.json();
      const agentsData = await agentsRes.json();
      const allPolData = await allPolRes.json();

      console.log("Fetched Data:", { pendingData, agentsData, allPolData });
      setCustomerPlans(pendingData.policies || []);

      const onlyPending = (pendingData.policies || []).filter((p) => {
        const s = String(p.Status || p.status || "pending").toLowerCase();
        return s === "pending";
      });
      setPendingPolicies(onlyPending);
      setAgents(agentsData.employees || []);
      setAllPolicies(allPolData.policies || []);
    } catch (error) {
      console.error("Fetch error:", error);
      setFetchError("Could not load live data. Using offline mode.");

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
      setCustomerPlans([
        { PolicyID: 801, CustomerID: 3001, Status: "approved", assignedAgentID: 101, policy_name: "Home Basic" },
        { PolicyID: 802, CustomerID: 3002, Status: "pending", assignedAgentID: 102, policy_name: "Auto Plus" },
        { PolicyID: 803, CustomerID: 3003, Status: "approved", assignedAgentID: 101, policy_name: "Home + Auto" },
      ]);
      setAgents([
        { userid: 101, username: "agent_smith", role: "agent" },
        { userid: 102, username: "agent_doe", role: "agent" },
      ]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [storedUserID]);

  const handleDecision = async (policyId, decision) => {
    console.log(`Policy ${policyId} decision: ${decision}`);
    setProcessingId(policyId);
    try {
      const response = await fetch(
        `http://127.0.0.1:8000/api/manager/policies/${policyId}/decision/`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-user-id": String(storedUserID),
          },
          body: JSON.stringify({ decision: decision }),
        }
      );

      if (response.ok) {
        let data = {};
        try {
          data = await response.json();
        } catch (e) {
          data = {};
        }
        const newStatus = (data && (data.newStatus || data.status)) || (decision === "approve" ? "approved" : "denied");


        setAllPolicies((prev) =>
          prev.map((p) =>
            p.PolicyID === policyId ? { ...p, Status: newStatus } : p
          )
        );

        setPendingPolicies((prev) => prev.filter((p) => p.PolicyID !== policyId));


        try {
          await fetchData();
        } catch (_) {
        }
      } else {
        alert("Failed to submit decision. Server returned an error.");
      }
    } catch (err) {
      console.error(err);
      alert("Network error submitting decision.");
    } finally {
      setProcessingId(null);
    }
  };

  const handleSelectionChange = (policyId, agentId) => {
    setAssignmentSelections((prev) => ({
      ...prev,
      [policyId]: agentId,
    }));
  };

  const handleAssignAgent = async (policyId) => {
    const agentId = assignmentSelections[policyId];
    if (!agentId) return alert("Please select an agent first.");

    setProcessingId(policyId);

    try {
      const response = await fetch(
        `http://127.0.0.1:8000/api/manager/policies/${policyId}/assign/`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-user-id": String(storedUserID),
          },

          body: JSON.stringify({ agentUserID: agentId }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || "Failed to assign");
      }

      setAllPolicies((prev) =>
        prev.map((p) =>
          p.PolicyID === policyId ? { ...p, assignedAgentID: agentId } : p
        )
      );
      setAssignmentSelections((prev) => {
        const newState = { ...prev };
        delete newState[policyId];
        return newState;
      });
    } catch (error) {
      console.error(error);
      alert("Failed to assign agent: " + error.message);
    } finally {
      setProcessingId(null);
    }
  };

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
        {processingId === policy.PolicyID ? (
          <div className="w-full flex justify-center py-2 text-gray-500 italic">
            Processing...
          </div>
        ) : (
          <>
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
          </>
        )}
      </div>
    </div>
  );

  const renderAssignTab = () => {
    const policiesToAssign = allPolicies.filter(
      (p) => !p.assignedAgentID && p.Status !== "rejected"
    );

    return (
      <div className="bg-white rounded-xl shadow-lg overflow-hidden border border-gray-200">
        <div className="p-4 border-b bg-gray-50 flex justify-between items-center">
          <h3 className="text-lg font-bold text-gray-700">
            Unassigned Policies
          </h3>
          <span className="bg-blue-100 text-blue-800 text-xs font-bold px-2 py-1 rounded-full">
            {policiesToAssign.length} Pending Assignment
          </span>
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
                  <td
                    colSpan="4"
                    className="p-8 text-center text-gray-400 italic"
                  >
                    All policies have been assigned.
                  </td>
                </tr>
              ) : (
                policiesToAssign.map((p) => (
                  <tr
                    key={p.PolicyID}
                    className="border-b hover:bg-gray-50 transition"
                  >
                    <td className="p-4 font-mono">{p.PolicyID}</td>
                    <td className="p-4">
                      <span
                        className={`px-2 py-1 rounded text-xs font-semibold ${
                          p.Status === "approved"
                            ? "bg-green-100 text-green-800"
                            : "bg-blue-100 text-blue-800"
                        }`}
                      >
                        {p.Status}
                      </span>
                    </td>
                    <td className="p-4">
                      <select
                        value={assignmentSelections[p.PolicyID] || ""}
                        onChange={(e) =>
                          handleSelectionChange(p.PolicyID, e.target.value)
                        }
                        className="bg-white border border-gray-300 rounded p-2 w-full focus:ring-2 focus:ring-blue-500 outline-none"
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
                        disabled={
                          !assignmentSelections[p.PolicyID] ||
                          processingId === p.PolicyID
                        }
                        onClick={() => handleAssignAgent(p.PolicyID)}
                        className={`px-4 py-2 rounded transition shadow-sm ${
                          !assignmentSelections[p.PolicyID]
                            ? "bg-gray-300 text-gray-500 cursor-not-allowed"
                            : "bg-blue-600 text-white hover:bg-blue-700"
                        }`}
                      >
                        {processingId === p.PolicyID ? "Saving..." : "Assign"}
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
    const getassignedAgentID = (p) => {
      const v =
        p.assignedAgentID ?? null;
      return v != null ? Number(v) : null;
    };
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {agents.map((agent) => {
          const agentPolicies = (customerPlans || []).filter(
            (p) => getassignedAgentID(p) === Number(agent.userid)
          );

          return (
            <div
              key={agent.userid}
              className="bg-white rounded-xl shadow p-5 border-t-4 border-blue-500 flex flex-col h-full"
            >
              <div className="flex justify-between items-center mb-4 border-b pb-2">
                <div>
                  <h3 className="text-lg font-bold text-gray-800">
                    {agent.username}
                  </h3>
                  <span className="text-xs text-gray-400 uppercase font-semibold">
                    {agent.role}
                  </span>
                </div>
                <div className="text-right">
                  <span className="block text-2xl font-bold text-blue-600">
                    {agentPolicies.length}
                  </span>
                  <span className="text-xs text-gray-500">Active Cases</span>
                </div>
              </div>

              <div className="space-y-2 flex-1">
                <h4 className="text-xs font-bold uppercase text-gray-400 tracking-wider mb-2">
                  Workload
                </h4>
                {agentPolicies.length > 0 ? (
                  <ul className="space-y-1 max-h-40 overflow-y-auto pr-2">
                    {agentPolicies.map((p) => (
                      <li
                        key={p.PolicyID || p.CustomerPlanID || `${agent.userid}-${Math.random()}`}
                        className="flex justify-between text-sm bg-gray-50 p-2 rounded border border-gray-100"
                      >
                        <span className="font-mono text-gray-600">
                          #{p.PolicyID || p.CustomerPlanID}
                        </span>
                        <span
                          className={`text-xs font-bold px-2 rounded ${
                            String(p.Status || p.status).toLowerCase() === "approved"
                              ? "text-green-600 bg-green-50"
                              : "text-yellow-600 bg-yellow-50"
                          }`}
                        >
                          {p.Status || p.status}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="h-20 flex items-center justify-center bg-gray-50 rounded border border-dashed border-gray-200">
                    <p className="text-sm italic text-gray-400">
                      No active assignments.
                    </p>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="flex bg-gray-100 min-h-screen font-sans">
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

        <div className="absolute bottom-6 left-0 w-full px-6">
          <button
            onClick={handleSignOut}
            className="w-full flex items-center justify-center gap-2 py-2 px-4 bg-red-50 text-red-600 font-semibold rounded-lg hover:bg-red-100 transition duration-200"
          >
            <span></span> Sign Out
          </button>
        </div>
      </div>

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
              <div className="w-8 h-8 rounded-full bg-purple-100 flex items-center justify-center text-purple-700 font-bold border border-purple-200 text-sm">
                M
              </div>
              <div>
                <p className="text-sm font-bold text-gray-700 leading-none">
                  Manager
                </p>
                <p className="text-xs text-gray-400 leading-none mt-1">
                  ID: {storedUserID}
                </p>
              </div>
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-6 lg:p-10">
          <div className="flex justify-between items-center mb-6">
            <h1 className="text-3xl font-bold text-gray-800">
              {navItems.find((n) => n.id === activeTab)?.name}
            </h1>
          </div>

          {fetchError && (
            <div className="bg-red-50 border-l-4 border-red-500 text-red-700 p-4 mb-6 rounded shadow-sm flex justify-between items-center">
              <div>
                <p className="font-bold">System Notification</p>
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
              {activeTab === "approvals" && (
                <div>
                  {pendingPolicies.length === 0 ? (
                    <div className="text-center p-12 bg-white rounded-xl border border-dashed border-gray-300 text-gray-400">
                      <div className="text-4xl mb-4"></div>
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
                <div className="max-w-6xl mx-auto">{renderAssignTab()}</div>
              )}

              {activeTab === "overview" && (
                <div className="max-w-6xl mx-auto">{renderOverviewTab()}</div>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}

export default ManagerHomePage;
