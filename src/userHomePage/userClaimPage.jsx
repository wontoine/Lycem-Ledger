import React, { useState, useEffect } from "react";
import { apiUrl } from "../lib/api";
import { useNavigate } from "react-router-dom";

// --- Helper: Status Badge Component ---
// Displays a colored badge based on the status of a claim (e.g., Pending, Approved, Rejected).
const StatusBadge = ({ status }) => {
  const s = (status || "").toLowerCase();
  let colorClass = "bg-blue-100 text-blue-700"; // Default for 'submitted' or unknown statuses

  if (s === "accepted" || s === "approved") {
    colorClass = "bg-green-100 text-green-700";
  } else if (s === "rejected" || s === "denied") {
    colorClass = "bg-red-100 text-red-700";
  } else if (s === "pending" || s === "in_review") {
    // Specifically handle 'in_review' to indicate intermediate agent approval
    colorClass = "bg-yellow-100 text-yellow-700";
  }

  return (
    <span
      className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide ${colorClass}`}
    >
      {status || "Unknown"}
    </span>
  );
};

// --- Helper: Date Formatter ---
// Converts ISO date strings into a readable format (e.g., "Nov 13, 2025, 02:30 PM").
const formatDate = (dateString) => {
  if (!dateString) return "N/A";
  return new Date(dateString).toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

// --- Component: Claim Details Modal ---
// A modal pop-up that shows detailed information about a specific claim, including
// the approval workflow status from both the Agent and the Manager.
const ClaimDetailsModal = ({ claim, onClose }) => {
  if (!claim) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center p-4 backdrop-blur-sm animate-fade-in">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Modal Header */}
        <div className="bg-blue-600 p-6 flex justify-between items-start text-white shrink-0">
          <div>
            <h2 className="text-2xl font-bold">Claim Details</h2>
            <p className="text-blue-100 text-sm font-mono mt-1">
              ID: {claim.ClaimID}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-white hover:text-blue-200 text-3xl font-light leading-none"
          >
            &times;
          </button>
        </div>

        {/* Scrollable Content Area */}
        <div className="p-6 overflow-y-auto space-y-6">
          {/* Top Row: Status and Amount summary */}
          <div className="grid grid-cols-2 gap-4">
            <div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
              <label className="text-xs font-bold text-gray-400 uppercase">
                Current Status
              </label>
              <div className="mt-1">
                <StatusBadge status={claim.Status} />
              </div>
            </div>
            <div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
              <label className="text-xs font-bold text-gray-400 uppercase">
                Claim Amount
              </label>
              <p className="text-xl font-bold text-gray-800">
                ${(claim.Amount || 0).toLocaleString()}
              </p>
            </div>
          </div>

          {/* Identification Numbers (Plan, Policy, Customer) */}
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <label className="block text-xs font-bold text-gray-500 uppercase">
                Customer Plan ID
              </label>
              <span className="font-mono text-blue-600 font-bold">
                {claim.CustomerPlanID || "N/A"}
              </span>
            </div>
            <div>
              <label className="block text-xs font-bold text-gray-500 uppercase">
                Policy ID
              </label>
              <span className="font-mono text-gray-700">
                {claim.PolicyID || "N/A"}
              </span>
            </div>
            <div>
              <label className="block text-xs font-bold text-gray-500 uppercase">
                Customer ID
              </label>
              <span className="font-mono text-gray-700">
                {claim.CustomerID || "N/A"}
              </span>
            </div>
          </div>

          {/* Description of the incident */}
          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase mb-1">
              Reason for Claim
            </label>
            <div className="bg-gray-50 p-4 rounded-lg border border-gray-200 text-gray-700 italic">
              "{claim.Reason}"
            </div>
          </div>

          {/* Timeline information */}
          <div className="border-t pt-4">
            <h3 className="text-sm font-bold text-gray-800 mb-3">Timeline</h3>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-500">Filed On:</span>
                <p className="font-medium">{formatDate(claim.CreatedAt)}</p>
              </div>
              <div>
                <span className="text-gray-500">Last Updated:</span>
                <p className="font-medium">{formatDate(claim.UpdatedAt)}</p>
              </div>
            </div>
          </div>

          {/* Internal Review Details (Agent vs Manager decisions) */}
          {(claim.agentApprovalStatus || claim.managerApprovalStatus) && (
            <div className="border-t pt-4">
              <h3 className="text-sm font-bold text-gray-800 mb-3">
                Review Details
              </h3>
              <div className="space-y-3">
                {/* Agent Decision Block */}
                <div className="flex items-start gap-3 p-3 rounded-lg bg-blue-50 border border-blue-100">
                  <div className="min-w-[4rem] font-bold text-xs text-blue-800 uppercase mt-1">
                    Agent
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-bold text-gray-900">
                        Decision:
                      </span>
                      <StatusBadge status={claim.agentApprovalStatus || "Pending"} />
                    </div>
                    {claim.agentStatusNote && (
                      <p className="text-sm text-gray-600">
                        <span className="font-semibold">Note:</span>{" "}
                        {claim.agentStatusNote}
                      </p>
                    )}
                  </div>
                </div>

                {/* Manager Decision Block */}
                <div className="flex items-start gap-3 p-3 rounded-lg bg-purple-50 border border-purple-100">
                  <div className="min-w-[4rem] font-bold text-xs text-purple-800 uppercase mt-1">
                    Manager
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-bold text-gray-900">
                        Decision:
                      </span>
                      <StatusBadge status={claim.managerApprovalStatus || "Pending"} />
                    </div>
                    {claim.managerApprovedAt && (
                      <div className="text-xs text-gray-500 mb-1">
                        Review Date: {formatDate(claim.managerApprovedAt)}
                      </div>
                    )}
                    {claim.managerNotes && (
                      <p className="text-sm text-gray-600">
                        <span className="font-semibold">Note:</span>{" "}
                        {claim.managerNotes}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer Action Buttons */}
        <div className="p-4 bg-gray-50 border-t flex justify-end">
          <button
            onClick={onClose}
            className="px-6 py-2 bg-gray-200 hover:bg-gray-300 text-gray-800 font-semibold rounded-lg transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

// --- Main Page Component ---
function UserClaimsPage() {
  const [sidebaropen, setSidebaropen] = useState(false);
  const [claims, setClaims] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // State for the modal popup
  const [selectedClaim, setSelectedClaim] = useState(null);

  const navigate = useNavigate();
  const storedUserID = localStorage.getItem("userID");

  const navItems = [
    { name: "Policies", path: "/home" },
    { name: "Claims", path: "/claims" },
  ];

  const handleLogout = () => {
    localStorage.removeItem("userID");
    navigate("/");
  };

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!storedUserID) {
      navigate("/");
      return;
    }

    // Fetch claims specifically for this user
    const fetchClaims = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(apiUrl("/api/claims/"), {
          method: "GET",
          headers: {
            "Content-Type": "application/json",
            "x-user-id": storedUserID,
          },
        });

        if (!response.ok) {
          throw new Error(`Server error: ${response.status}`);
        }

        const data = await response.json();
        setClaims(data.claims || []);
      } catch (err) {
        console.error("Error fetching claims:", err);
        setError("Failed to load claims. Please try again later.");
      } finally {
        setLoading(false);
      }
    };

    fetchClaims();
  }, [storedUserID, navigate]);

  return (
    <div className="flex bg-gray-100 min-h-screen font-sans">
      {/* Sidebar Navigation */}
      <div
        className={`fixed bg-white w-64 h-screen shadow-2xl transition-transform duration-300 ease-in-out z-40 flex flex-col ${
          sidebaropen ? "translate-x-0" : "-translate-x-full"
        } lg:static lg:w-64 lg:translate-x-0`}
      >
        <div className="p-4 flex justify-between items-center border-b">
          <div className="text-2xl font-extrabold text-blue-600">
            Lyceum Ledger
          </div>
          <button
            className="lg:hidden p-1"
            onClick={() => setSidebaropen(false)}
          >
            ✕
          </button>
        </div>

        <div className="p-4 space-y-2 flex-1">
          {navItems.map((item) => (
            <button
              key={item.name}
              className={`flex items-center w-full text-left p-3 rounded-lg transition duration-150 ${
                item.name === "Claims"
                  ? "bg-blue-50 text-blue-700 border-r-4 border-blue-600"
                  : "text-gray-600 hover:bg-gray-50 hover:text-blue-600"
              }`}
              onClick={() => navigate(item.path)}
            >
              <div className="font-semibold">{item.name}</div>
            </button>
          ))}
        </div>

        <div className="p-4 border-t border-gray-200">
          <button
            onClick={handleLogout}
            className="flex items-center w-full text-left p-3 rounded-lg text-gray-600 hover:bg-red-50 hover:text-red-600 transition duration-150 group"
          >
            <div className="font-bold">Sign Out</div>
          </button>
          <div className="mt-4 text-xs text-gray-400 px-2">
            User ID: {storedUserID ? storedUserID : "N/A"}
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <main className="flex-1 overflow-y-auto h-screen flex flex-col">
        <header className="sticky top-0 bg-white flex justify-between items-center p-4 shadow-md z-30">
          <button
            className="p-2 text-xl font-bold lg:hidden rounded-lg hover:bg-gray-100"
            onClick={() => setSidebaropen(true)}
          >
            ☰
          </button>
          <h1 className="text-2xl font-extrabold text-gray-800">My Claims</h1>
          <div
            className="bg-blue-500 w-10 h-10 rounded-full flex items-center justify-center text-white font-bold cursor-default shadow-lg"
            title={`User ${storedUserID}`}
          >
            {storedUserID ? storedUserID[0].toUpperCase() : "U"}
          </div>
        </header>

        <div className="p-6 flex-1 overflow-y-auto">
          {loading && (
            <div className="text-center p-10 text-gray-500 text-lg flex flex-col items-center">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mb-3"></div>
              Loading claims...
            </div>
          )}

          {error && (
            <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative mb-4">
              <strong className="font-bold">Error: </strong>
              <span className="block sm:inline">{error}</span>
            </div>
          )}

          {!loading && !error && claims.length === 0 && (
            <div className="text-center p-12 bg-white rounded-lg shadow-lg border border-gray-200">
              <div className="text-4xl mb-3">📂</div>
              <p className="text-xl text-gray-600 font-semibold">
                No claims found.
              </p>
              <p className="text-gray-500 mt-2">
                You haven't submitted any claims yet.
              </p>
            </div>
          )}

          {!loading && !error && claims.length > 0 && (
            <div className="bg-white rounded-xl shadow-lg overflow-hidden border border-gray-200">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm text-gray-600">
                  <thead className="bg-gray-50 text-gray-700 font-bold uppercase">
                    <tr>
                      <th className="p-4">Claim ID</th>
                      <th className="p-4">Date Filed</th>
                      <th className="p-4">Reason</th>
                      <th className="p-4 text-right">Amount</th>
                      <th className="p-4 text-center">Status</th>
                      <th className="p-4 text-center">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {claims.map((claim) => (
                      <tr
                        key={claim.ClaimID}
                        className="hover:bg-gray-50 transition"
                      >
                        <td className="p-4 font-mono font-bold text-gray-800">
                          #{claim.ClaimID}
                        </td>
                        <td className="p-4 text-gray-600">
                          {new Date(claim.CreatedAt).toLocaleDateString()}
                        </td>
                        <td className="p-4 font-medium text-gray-800 truncate max-w-xs">
                          {claim.Reason}
                        </td>
                        <td className="p-4 text-gray-600 text-right font-mono">
                          ${(claim.Amount || 0).toLocaleString()}
                        </td>
                        <td className="p-4 text-center">
                          <StatusBadge status={claim.Status} />
                        </td>
                        <td className="p-4 text-center">
                          <button
                            onClick={() => setSelectedClaim(claim)}
                            className="bg-blue-600 text-white px-3 py-1.5 rounded-md text-xs font-bold hover:bg-blue-700 shadow transition"
                          >
                            View
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Claim Details Modal */}
      {selectedClaim && (
        <ClaimDetailsModal
          claim={selectedClaim}
          onClose={() => setSelectedClaim(null)}
        />
      )}
    </div>
  );
}

export default UserClaimsPage;