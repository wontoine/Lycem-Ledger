import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

function UserClaimsPage() {
  const [sidebaropen, setSidebaropen] = useState(false);
  const [claims, setClaims] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const navigate = useNavigate();
  const storedUserID = localStorage.getItem("userID");

  const navItems = [
    { name: "Policies", path: "/userHomePage" },
    { name: "Claims", path: "/claims" },
  ];

  const handleLogout = () => {
    localStorage.removeItem("userID");
    navigate("/");
  };

  useEffect(() => {
    if (!storedUserID) {
      navigate("/");
      return;
    }

    const fetchClaims = async () => {
      setLoading(true);
      setError(null);
      try {
        // Use the ClaimListCreateView endpoint defined in urls.py
        const response = await fetch("http://127.0.0.1:8000/api/claims/", {
          method: "GET",
          headers: {
            "Content-Type": "application/json",
            // The backend requires x-user-id to filter claims for this specific customer
            "x-user-id": storedUserID,
          },
        });

        if (!response.ok) {
          throw new Error(`Server error: ${response.status}`);
        }

        const data = await response.json();
        // The API returns { "claims": [...] }
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

  // Helper to normalize status for badge coloring
  const getStatusColor = (status) => {
    const s = (status || "").toLowerCase();
    if (s === "accepted" || s === "approved") return "bg-green-100 text-green-700";
    if (s === "rejected" || s === "denied") return "bg-red-100 text-red-700";
    return "bg-blue-100 text-blue-700"; // submitted/pending
  };

  return (
    <div className="flex bg-gray-100 min-h-screen">
      {/* Sidebar */}
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

      {/* Main Content */}
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
                      <th className="p-4">Policy / Plan ID</th>
                      <th className="p-4">Reason</th>
                      <th className="p-4 text-right">Amount</th>
                      <th className="p-4 text-center">Status</th>
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
                        <td className="p-4 font-mono text-blue-600">
                          {/* Display CustomerPlanID, fallback to PolicyID */}
                          {claim.CustomerPlanID || claim.PolicyID || "N/A"}
                        </td>
                        <td className="p-4 font-medium text-gray-800">
                          {claim.Reason}
                        </td>
                        <td className="p-4 text-gray-600 text-right font-mono">
                          ${(claim.Amount || 0).toLocaleString()}
                        </td>
                        <td className="p-4 text-center">
                          <span
                            className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide ${getStatusColor(
                              claim.Status
                            )}`}
                          >
                            {claim.Status}
                          </span>
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
    </div>
  );
}

export default UserClaimsPage;