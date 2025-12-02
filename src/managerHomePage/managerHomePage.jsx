import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

function ManagerHomePage() {
  const [sidebaropen, setSidebaropen] = useState(false);
  const [activeTab, setActiveTab] = useState("claims");

  // Data
  const [claims, setClaims] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(null);

  // Interaction
  const [decisionNotes, setDecisionNotes] = useState({});
  const [decisionBusy, setDecisionBusy] = useState({});

  const navigate = useNavigate();
  const storedUserID = localStorage.getItem("userID");

  useEffect(() => {
    if (!storedUserID) {
      navigate("/", { replace: true });
    }
  }, [storedUserID, navigate]);

  const navItems = [
    { id: "claims", name: "Claim Reviews", icon: "Tb" },
    // You can add Policies or Employees tabs here later
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
      const response = await fetch("http://127.0.0.1:8000/api/supervisor/claims/", {
        headers: {
          "Content-Type": "application/json",
          "x-user-id": String(storedUserID),
        },
      });

      if (!response.ok) {
        throw new Error("Failed to fetch claims");
      }
      const data = await response.json();
      setClaims(data.claims || []);
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

  const handleDecision = async (claimId, decision) => {
    // Decision must be "approve" or "deny" for SupervisorClaimDecisionView
    if (!storedUserID) return;
    const note = (decisionNotes?.[claimId] || "").trim();

    setDecisionBusy((prev) => ({ ...prev, [claimId]: true }));
    try {
      const res = await fetch(
        `http://127.0.0.1:8000/api/supervisor/claims/${claimId}/decision/`,
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
        alert(`Failed to ${decision}: ${data?.error || "Unknown error"}`);
        return;
      }

      // Update local state
      setClaims((prev) =>
        prev.map((c) => {
          if (c.ClaimID !== claimId) return c;
          return {
            ...c,
            managerApprovalStatus:
              decision === "approve" ? "approved" : "rejected",
            managerNotes: note || c.managerNotes,
            Status: data.newStatus || c.Status,
          };
        })
      );
      setDecisionNotes((prev) => ({ ...prev, [claimId]: "" }));
    } catch (err) {
      console.error(err);
      alert("Network error.");
    } finally {
      setDecisionBusy((prev) => ({ ...prev, [claimId]: false }));
    }
  };

  const renderClaimsTab = () => {
    // Filter logic
    const pendingClaims = claims.filter(
      (c) =>
        !c.managerApprovalStatus ||
        c.managerApprovalStatus.toLowerCase() === "pending"
    );

    const pastClaims = claims.filter(
      (c) =>
        c.managerApprovalStatus &&
        c.managerApprovalStatus.toLowerCase() !== "pending"
    );

    return (
      <div className="max-w-6xl mx-auto space-y-12">
        {/* Section 1: Pending Manager Review */}
        <section>
          <h2 className="text-2xl font-bold text-gray-800 mb-4 flex items-center gap-2">
            <span>⚖️</span> Reviews Required
            <span className="text-sm font-normal text-gray-500 bg-gray-200 px-2 py-1 rounded-full">
              {pendingClaims.length}
            </span>
          </h2>

          <div className="bg-white rounded-xl shadow-lg overflow-hidden border border-gray-200">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-gray-600">
                <thead className="bg-purple-50 uppercase text-purple-900 font-bold">
                  <tr>
                    <th className="p-4">Claim ID</th>
                    <th className="p-4">Plan / Policy</th>
                    <th className="p-4">Agent Note</th>
                    <th className="p-4">Amount</th>
                    <th className="p-4">Manager Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingClaims.length === 0 ? (
                    <tr>
                      <td colSpan="5" className="p-8 text-center text-gray-400">
                        No claims waiting for approval.
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
                        <td className="p-4 max-w-xs">
                          <div className="flex flex-col">
                            <span className="text-xs text-green-600 font-bold uppercase">
                              Agent Approved
                            </span>
                            <span className="text-gray-500 text-xs italic truncate">
                              "{claim.agentStatusNote || "No notes"}"
                            </span>
                          </div>
                        </td>
                        <td className="p-4 font-semibold text-gray-800">
                          ${claim.Amount?.toLocaleString()}
                        </td>
                        <td className="p-4">
                          <div className="flex flex-col gap-2 min-w-[220px]">
                            <input
                              type="text"
                              placeholder="Manager Note (Optional)"
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
                                  handleDecision(claim.ClaimID, "approve")
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
                                  handleDecision(claim.ClaimID, "deny")
                                }
                                disabled={!!decisionBusy?.[claim.ClaimID]}
                              >
                                Deny
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

        {/* Section 2: Past Claims */}
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
                    <th className="p-4">Plan / Policy</th>
                    <th className="p-4">Reason</th>
                    <th className="p-4">Amount</th>
                    <th className="p-4">Manager Status</th>
                    <th className="p-4">Manager Note</th>
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
                        <td className="p-4 max-w-xs truncate">{claim.Reason}</td>
                        <td className="p-4 text-gray-800">
                          ${claim.Amount?.toLocaleString()}
                        </td>
                        <td className="p-4">
                          <span
                            className={`px-2 py-1 rounded text-xs font-bold uppercase ${
                              (claim.managerApprovalStatus || "").toLowerCase() ===
                              "approved"
                                ? "bg-green-100 text-green-700"
                                : "bg-red-100 text-red-700"
                            }`}
                          >
                            {claim.managerApprovalStatus || "Processed"}
                          </span>
                        </td>
                        <td className="p-4 text-xs text-gray-500 italic max-w-xs truncate">
                          {claim.managerNotes || "—"}
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
                {item.icon === "Tb" ? "📊" : "🔹"}
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
            <span>🚪</span> Sign Out
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
          {fetchError && (
            <div className="bg-yellow-50 border-l-4 border-yellow-500 text-yellow-700 p-4 mb-6 rounded shadow-sm">
              <p className="font-bold">Connection Status: {fetchError}</p>
            </div>
          )}
          {loading ? (
            <div className="flex justify-center items-center h-64 flex-col gap-4 text-gray-400">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
              <p>Loading Dashboard...</p>
            </div>
          ) : (
            renderClaimsTab()
          )}
        </div>
      </main>
    </div>
  );
}

export default ManagerHomePage;