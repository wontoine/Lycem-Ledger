import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

function UserClaimsPage() {
  const [sidebaropen, setSidebaropen] = useState(false);
  const [claims, setClaims] = useState([]);
  const [loading, setLoading] = useState(true);

  const navigate = useNavigate();
  const storedUserID = localStorage.getItem("userID");

  const navItems = [
    { name: "Policies", path: "/home" },
    { name: "Claims", path: "/userClaims" },
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
      try {
        // TODO: Insert API call here (e.g., GET http://127.0.0.1:8000/api/user/claims/)

        const mockData = [
          {
            ClaimID: 101,
            PolicyID: "P001",
            Reason: "Water Damage",
            Amount: 5000,
            Status: "Pending",
          },
          {
            ClaimID: 102,
            PolicyID: "P003",
            Reason: "Car Accident",
            Amount: 1200,
            Status: "Approved",
          },
          {
            ClaimID: 103,
            PolicyID: "P001",
            Reason: "Theft",
            Amount: 800,
            Status: "Rejected",
          },
        ];
        setClaims(mockData);
      } catch (error) {
        console.error(error);
      } finally {
        setLoading(false);
      }
    };

    fetchClaims();
  }, [storedUserID, navigate]);

  return (
    <div className="flex bg-gray-100 min-h-screen">
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
              <span className="text-xl mr-3">{item.icon}</span>
              <div className="font-semibold">{item.name}</div>
            </button>
          ))}
        </div>

        <div className="p-4 border-t border-gray-200">
          <button
            onClick={handleLogout}
            className="flex items-center w-full text-left p-3 rounded-lg text-gray-600 hover:bg-red-50 hover:text-red-600 transition duration-150 group"
          >
            <span className="text-xl mr-3 group-hover:scale-110 transition-transform"></span>
            <div className="font-bold">Sign Out</div>
          </button>
          <div className="mt-4 text-xs text-gray-400 px-2">
            User ID: {storedUserID ? storedUserID : "N/A"}
          </div>
        </div>
      </div>

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
          {loading ? (
            <div className="text-center p-10 text-gray-500 text-lg flex flex-col items-center">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mb-3"></div>
              Loading claims...
            </div>
          ) : claims.length === 0 ? (
            <div className="text-center p-12 bg-white rounded-lg shadow-lg border border-gray-200">
              <div className="text-4xl mb-3">📂</div>
              <p className="text-xl text-gray-600 font-semibold">
                No claims found.
              </p>
              <p className="text-gray-500 mt-2">
                You haven't submitted any claims yet.
              </p>
            </div>
          ) : (
            <div className="bg-white rounded-xl shadow-lg overflow-hidden border border-gray-200">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm text-gray-600">
                  <thead className="bg-gray-50 text-gray-700 font-bold uppercase">
                    <tr>
                      <th className="p-4">Claim ID</th>
                      <th className="p-4">Policy</th>
                      <th className="p-4">Reason</th>
                      <th className="p-4">Amount</th>
                      <th className="p-4">Status</th>
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
                          {claim.PolicyID}
                        </td>
                        <td className="p-4 font-medium text-gray-800">
                          {claim.Reason}
                        </td>
                        <td className="p-4 text-gray-600">
                          ${claim.Amount.toLocaleString()}
                        </td>
                        <td className="p-4">
                          <span
                            className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide ${
                              claim.Status === "Approved"
                                ? "bg-green-100 text-green-700"
                                : claim.Status === "Rejected"
                                ? "bg-red-100 text-red-700"
                                : "bg-yellow-100 text-yellow-700"
                            }`}
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
