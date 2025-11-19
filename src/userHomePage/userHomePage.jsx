import React, { useState, useEffect } from "react";
// Import necessary Router components
import { useNavigate, BrowserRouter, Routes, Route } from "react-router-dom";
import SubmitClaimModal from "./submitClaim";

// --- Component Definition ---

function UserHomePage() {
  const [sidebaropen, setSidebaropen] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [policies, setPolicies] = useState([]); // State to hold policy data
  const [loading, setLoading] = useState(true); // State for loading indicator
  const [fetchError, setFetchError] = useState(null); // State for errors

  // useNavigate is now safe to use because the component is rendered inside <BrowserRouter>
  const navigate = useNavigate();
  // Retrieve the stored userID for authentication/filtering
  const storedUserID = localStorage.getItem("userID");

  const navItems = [
    { name: "Policies", icon: "📜", path: "/policies" },
    { name: "Claims", icon: "📝", path: "/claims" },
    { name: "Submit Claim", icon: "✅", path: "#" },
  ];

  // --- Policy Data Fetching using useEffect ---
  useEffect(() => {
    if (!storedUserID) {
      setLoading(false);
      setFetchError("User ID not found. Please log in.");
      // Optional: Redirect to login if no user ID
      // navigate('/login');
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

        if (!response.ok) {
          throw new Error(
            `Failed to fetch policies: Status ${response.status}`
          );
        }

        const data = await response.json();
        // Fallback to mock data if API is empty or for local testing
        const mockPolicies =
          data.length > 0
            ? data
            : [
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
                {
                  policy_id: "P003",
                  policy_name: "Life Basic",
                  status: "Active",
                  coverage_amount: 250000,
                  start_date: "2023-11-20",
                  premium: 450,
                },
              ];
        setPolicies(mockPolicies);
        setFetchError(null);
      } catch (error) {
        console.error("Policy fetch error:", error);
        // Display mock data on error
        setPolicies([
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
        ]);
        setFetchError("Could not load real policies. Displaying mock data.");
      } finally {
        setLoading(false);
      }
    };

    fetchPolicies();
  }, [storedUserID]);

  // --- Handlers ---
  const handleNavItemClick = (item) => {
    if (item.name === "Submit Claim") {
      setIsModalOpen(true);
    } else {
      setSidebaropen(false);
      if (item.path && item.path !== "#") {
        navigate(item.path); // Use navigate only if a path exists
      }
    }
  };

  // --- Policy Card Renderer Component (Nested) ---
  const PolicyCard = ({ policy }) => (
    <div className="bg-white p-6 shadow-lg rounded-xl border border-blue-100 hover:shadow-xl transition duration-200 cursor-pointer">
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

  // --- JSX Rendering ---
  return (
    <div className="flex bg-gray-100 min-h-screen">
      {/* Sidebar */}
      <div
        className={`fixed bg-white w-64 h-full shadow-2xl transition-transform duration-300 ease-in-out z-40 ${
          sidebaropen ? "translate-x-0" : "-translate-x-full"
        } lg:static lg:w-64 lg:translate-x-0`}
      >
        <div className="p-4 flex justify-between items-center border-b">
          <div className="text-2xl font-extrabold text-blue-600">
            {" "}
            InsureApp{" "}
          </div>
          <button
            className="lg:hidden p-1"
            onClick={() => setSidebaropen(false)}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>
        <div className="p-4 space-y-2">
          {navItems.map((item) => (
            <button
              key={item.name}
              className="flex items-center w-full text-left p-3 rounded-lg text-gray-700 hover:bg-blue-100 hover:text-blue-700 transition duration-150"
              onClick={() => handleNavItemClick(item)}
            >
              <div className="text-xl mr-3">{item.icon}</div>
              <div className="font-semibold">{item.name}</div>
            </button>
          ))}
        </div>
        <div className="absolute bottom-4 left-4 text-sm text-gray-500">
          User ID: {storedUserID ? storedUserID.substring(0, 8) + "..." : "N/A"}
        </div>
      </div>

      {/* Main Content Area */}
      <main className="flex-1 overflow-y-auto">
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
          <div className="bg-blue-500 w-10 h-10 rounded-full flex items-center justify-center text-white font-bold">
            {storedUserID ? storedUserID[0].toUpperCase() : "U"}
          </div>
        </header>

        <div className="p-6">
          <h2 className="text-2xl font-bold text-gray-800 mb-6">
            Your Active Policies
          </h2>

          {/* Conditional Rendering based on state */}
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

          {/* Policy Cards Grid: Dynamic Policy Card Rendering */}
          <div className="grid sm:grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {policies.map((policy) => (
              <PolicyCard key={policy.policy_id} policy={policy} />
            ))}
          </div>
        </div>
      </main>

      {/* Submit Claim Modal */}
      {isModalOpen && (
        <SubmitClaimModal
          onClose={() => setIsModalOpen(false)}
          userID={storedUserID}
        />
      )}
    </div>
  );
}
export default UserHomePage;
