import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import SubmitClaimModal from "./submitClaim";

// --- Component Definition ---

function UserHomePage() {
  const [sidebaropen, setSidebaropen] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [policies, setPolicies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(null);
  const [selectedPolicy, setSelectedPolicy] = useState(null);

  const navigate = useNavigate();
  const storedUserID = localStorage.getItem("userID");

  const navItems = [
    { name: "Policies", path: "/policies", icon: "📄" },
    { name: "Claims", path: "/claims", icon: "🛡️" },
    { name: "Submit Claim", path: "#", icon: "➕" },
  ];

  // --- 1. NEW: Handle Logout Logic ---
  const handleLogout = () => {
    // A. Clear the stored ID
    localStorage.removeItem("userID");

    // B. Optional: clear other items if you have them
    // localStorage.clear();

    // C. Redirect to Login Page
    navigate("/");
  };
  // ----------------------------------

  useEffect(() => {
    if (!storedUserID) {
      setLoading(false);
      // If no ID, redirect immediately (security best practice)
      navigate("/");
      return;
    }

    const API_URL = `http://127.0.0.1:8000/api/policies/`;

    const fetchPolicies = async () => {
      try {
        const response = await fetch(API_URL, {
          method: "GET",
          headers: {
            "x-user-id": String(storedUserID),
          },
        });

        const text = await response.text();

        let data = [];
        let parseSuccess = false;

        try {
          data = JSON.parse(text);
          parseSuccess = true;
        } catch (err) {
          console.error("Not JSON:", err);
        }

        if (parseSuccess && Array.isArray(data) && data.length > 0) {
          setPolicies(data);
          setFetchError(null);
        } else {
          // Mock Data Fallback
          const mockPolicies = [
            {
              policy_id: "P001",
              policy_name: "Homeowner Plus",
              status: "Active",
              coverage_amount: 500000,
              start_date: "2024-01-01",
              premium: 1200,
            },
            {
              policy_id: "P002",
              policy_name: "Auto Platinum",
              status: "Pending",
              coverage_amount: 50000,
              start_date: "2024-05-15",
              premium: 800,
            },
          ];
          setPolicies(mockPolicies);
        }
      } catch (error) {
        console.error("Network error:", error);
        setFetchError("Network Error. Displaying mock data.");
      } finally {
        setLoading(false);
      }
    };

    fetchPolicies();
  }, [storedUserID, navigate]);

  const handleNavItemClick = (item) => {
    if (item.name === "Submit Claim") {
      setIsModalOpen(true);
    } else {
      setSidebaropen(false);
      if (item.path && item.path !== "#") {
        navigate(item.path);
      }
    }
  };

  const PolicyCard = ({ policy, onClick }) => (
    <div
      onClick={onClick}
      className="bg-white p-6 shadow-lg rounded-xl border border-blue-100 hover:shadow-xl transition duration-200 cursor-pointer"
    >
      <div className="flex justify-between items-start mb-4">
        <h2 className="text-xl font-extrabold text-blue-700 truncate">
          {policy.policy_name || `Policy #${policy.policy_id}`}
        </h2>
        <span
          className={`text-sm font-semibold px-3 py-1 rounded-full ${
            policy.status === "Active"
              ? "bg-green-100 text-green-700"
              : policy.status === "Pending"
              ? "bg-yellow-100 text-yellow-700"
              : "bg-red-100 text-red-700"
          }`}
        >
          {policy.status || "Unknown"}
        </span>
      </div>

      <p className="text-sm text-gray-500 mb-2">
        Policy ID:{" "}
        <span className="font-mono text-gray-700">{policy.policy_id}</span>
      </p>
      <p className="text-3xl font-bold text-gray-900 mb-4">
        $
        {policy.coverage_amount
          ? policy.coverage_amount.toLocaleString()
          : "N/A"}
      </p>

      <div className="flex justify-between text-sm text-gray-600">
        <div>
          <span className="font-medium">Start Date:</span>{" "}
          {policy.start_date || "N/A"}
        </div>
        <div>
          <span className="font-medium">Premium:</span> $
          {policy.premium || "N/A"}
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex bg-gray-100 min-h-screen">
      {/* Sidebar */}
      <div
        className={`fixed bg-white w-64 h-screen shadow-2xl transition-transform duration-300 ease-in-out z-40 flex flex-col ${
          sidebaropen ? "translate-x-0" : "-translate-x-full"
        } lg:static lg:w-64 lg:translate-x-0`}
      >
        <div className="p-4 flex justify-between items-center border-b">
          <div className="text-2xl font-extrabold text-blue-600">InsureApp</div>
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
              className="flex items-center w-full text-left p-3 rounded-lg text-gray-700 hover:bg-blue-100 hover:text-blue-700 transition duration-150"
              onClick={() => handleNavItemClick(item)}
            >
              <span className="text-xl mr-3">{item.icon}</span>
              <div className="font-semibold">{item.name}</div>
            </button>
          ))}
        </div>

        {/* --- 2. NEW: Sign Out Button Section --- */}
        <div className="p-4 border-t border-gray-200">
          <button
            onClick={handleLogout}
            className="flex items-center w-full text-left p-3 rounded-lg text-gray-600 hover:bg-red-50 hover:text-red-600 transition duration-150 group"
          >
            <span className="text-xl mr-3 group-hover:scale-110 transition-transform">
              🚪
            </span>
            <div className="font-bold">Sign Out</div>
          </button>

          <div className="mt-4 text-xs text-gray-400 px-2">
            User ID: {storedUserID ? storedUserID : "N/A"}
          </div>
        </div>
        {/* --------------------------------------- */}
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
          <h1 className="text-2xl font-extrabold text-gray-800">
            Policies Dashboard
          </h1>
          <div
            className="bg-blue-500 w-10 h-10 rounded-full flex items-center justify-center text-white font-bold cursor-default"
            title={`User ${storedUserID}`}
          >
            {storedUserID ? storedUserID[0].toUpperCase() : "U"}
          </div>
        </header>

        <div className="p-6 flex-1 overflow-y-auto">
          <h2 className="text-2xl font-bold text-gray-800 mb-6">
            Your Active Policies
          </h2>

          {loading && (
            <div className="text-center p-10 text-gray-500 text-lg">
              Loading policies...
            </div>
          )}

          {fetchError && (
            <div className="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 mb-4 rounded-lg">
              <p className="font-bold">Error</p>
              <p>{fetchError}</p>
            </div>
          )}

          {!loading && !fetchError && policies.length === 0 && (
            <div className="text-center p-10 bg-white rounded-lg shadow-lg">
              <p className="text-xl text-gray-600">
                You don't have any active policies yet.
              </p>
              <button
                className="mt-4 bg-blue-500 text-white px-4 py-2 rounded-lg hover:bg-blue-600"
                onClick={() => navigate("/browse-policies")}
              >
                Browse Policy Options
              </button>
            </div>
          )}

          <div className="grid sm:grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 pb-10">
            {policies.map((policy) => (
              <PolicyCard
                key={policy.policy_id}
                policy={policy}
                onClick={() => {
                  console.log("Policy clicked:", policy.policy_id);
                  setSelectedPolicy(policy);
                  setIsModalOpen(true);
                }}
              />
            ))}
          </div>
        </div>
      </main>

      {isModalOpen && (
        <SubmitClaimModal
          onClose={() => setIsModalOpen(false)}
          userID={storedUserID}
          selectedPolicy={selectedPolicy}
        />
      )}
    </div>
  );
}

export default UserHomePage;
