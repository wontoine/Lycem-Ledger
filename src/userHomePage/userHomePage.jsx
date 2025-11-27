import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import SubmitClaimModal from "./submitClaim";

// --- Helper Component: Policy Details Modal ---
const PolicyDetailsModal = ({
  policyId,
  userID,
  onClose,
  onOpenClaimModal,
}) => {
  const [details, setDetails] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [isSavingItem, setIsSavingItem] = useState(false);

  // Text Inputs
  const [newItem, setNewItem] = useState({
    name: "",
    value: "",
    description: "",
  });

  // Image Inputs
  const [itemImages, setItemImages] = useState({
    image1: null,
    image2: null,
  });

  useEffect(() => {
    const fetchDetails = async () => {
      // Mock Data for Details
      const mockDetails = {
        CustomerID: userID,
        Status: "Active",
        CreatedAt: "2024-01-01",
        items: [
          {
            ItemID: 101,
            Name: "MacBook Pro",
            Value: 2500,
            Description: "Electronics",
          },
          {
            ItemID: 102,
            Name: "Diamond Ring",
            Value: 5000,
            Description: "Jewelry",
          },
        ],
      };

      try {
        const response = await fetch(
          `http://127.0.0.1:8000/api/policies/${policyId}/`,
          {
            headers: { "x-user-id": String(userID) },
          }
        );
        if (!response.ok) throw new Error("Fetch failed");

        const data = await response.json();
        setDetails(data);
        setItems(data.items || []);
      } catch (error) {
        console.warn("Using Mock Data for Details:", error);
        setDetails(mockDetails);
        setItems(mockDetails.items);
      } finally {
        setLoading(false);
      }
    };

    if (policyId) fetchDetails();
  }, [policyId, userID]);

  const handleFileChange = (e, key) => {
    if (e.target.files && e.target.files[0]) {
      setItemImages((prev) => ({ ...prev, [key]: e.target.files[0] }));
    }
  };

  const handleAddItem = async (e) => {
    e.preventDefault();

    // Validation: Ensure both images are present
    if (!itemImages.image1 || !itemImages.image2) {
      alert("Please upload both required images.");
      return;
    }

    setIsSavingItem(true);

    try {
      // Create FormData object to send files + text
      const formData = new FormData();
      formData.append("policy_id", policyId);
      formData.append("name", newItem.name);
      formData.append("value", newItem.value);
      formData.append("description", newItem.description);
      formData.append("image1", itemImages.image1);
      formData.append("image2", itemImages.image2);

      const response = await fetch("http://127.0.0.1:8000/api/items/", {
        method: "POST",
        headers: {
          // NOTE: Do NOT set Content-Type to application/json when sending FormData
          // The browser will automatically set Content-Type: multipart/form-data
          "x-user-id": String(userID),
        },
        body: formData,
      });

      if (!response.ok) throw new Error("API Endpoint not available yet");

      const savedItem = await response.json();
      setItems([...items, savedItem]);

      // Reset Form
      setNewItem({ name: "", value: "", description: "" });
      setItemImages({ image1: null, image2: null });
      setShowAddForm(false);
    } catch (error) {
      console.warn("Using Local Fallback for Add Item:", error);

      // Fallback: Create a mock object locally so the UI updates
      const fallbackItem = {
        ItemID: Date.now(),
        Name: newItem.name,
        Value: newItem.value,
        Description: newItem.description,
        // Create temporary URLs for the images so they could theoretically be displayed
        Image1Url: itemImages.image1
          ? URL.createObjectURL(itemImages.image1)
          : null,
        Image2Url: itemImages.image2
          ? URL.createObjectURL(itemImages.image2)
          : null,
      };

      setItems([...items, fallbackItem]);
      setNewItem({ name: "", value: "", description: "" });
      setItemImages({ image1: null, image2: null });
      setShowAddForm(false);
    } finally {
      setIsSavingItem(false);
    }
  };

  if (!policyId) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center p-4 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl overflow-hidden animate-fade-in-up max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="bg-blue-600 p-6 flex justify-between items-start text-white shrink-0">
          <div>
            <h2 className="text-2xl font-bold">Policy Details</h2>
            <p className="text-blue-100 text-sm">ID: {policyId}</p>
          </div>
          <button
            onClick={onClose}
            className="text-white hover:text-blue-200 text-2xl font-bold"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto">
          {loading ? (
            <div className="text-center py-10 text-gray-500">
              Loading details...
            </div>
          ) : details ? (
            <div className="space-y-6">
              {/* Policy Info Grid */}
              <div className="grid grid-cols-2 gap-4 bg-blue-50 p-4 rounded-xl border border-blue-100">
                <div>
                  <p className="text-xs font-bold text-blue-800 uppercase">
                    Status
                  </p>
                  <p className="text-gray-700 font-semibold">
                    {details.Status || "Active"}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-bold text-blue-800 uppercase">
                    Customer ID
                  </p>
                  <p className="text-gray-700 font-mono">
                    {details.CustomerID}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-bold text-blue-800 uppercase">
                    Created At
                  </p>
                  <p className="text-gray-700">
                    {details.CreatedAt
                      ? new Date(details.CreatedAt).toLocaleDateString()
                      : "N/A"}
                  </p>
                </div>
              </div>

              {/* Items Section */}
              <div>
                <div className="flex justify-between items-center mb-3">
                  <h3 className="text-lg font-bold text-gray-800">
                    Insured Items
                  </h3>
                  <button
                    onClick={() => setShowAddForm(!showAddForm)}
                    className="text-sm text-blue-600 hover:text-blue-800 font-semibold"
                  >
                    {showAddForm ? "Cancel" : "+ Add Item"}
                  </button>
                </div>

                {/* Add Item Form */}
                {showAddForm && (
                  <form
                    onSubmit={handleAddItem}
                    className="bg-gray-100 p-4 rounded-lg mb-4 border border-gray-300"
                  >
                    {/* Text Fields */}
                    <div className="grid grid-cols-2 gap-3 mb-3">
                      <input
                        type="text"
                        placeholder="Item Name"
                        required
                        className="p-2 rounded border"
                        value={newItem.name}
                        onChange={(e) =>
                          setNewItem({ ...newItem, name: e.target.value })
                        }
                      />
                      <input
                        type="number"
                        placeholder="Value ($)"
                        required
                        className="p-2 rounded border"
                        value={newItem.value}
                        onChange={(e) =>
                          setNewItem({ ...newItem, value: e.target.value })
                        }
                      />
                    </div>
                    <input
                      type="text"
                      placeholder="Description"
                      className="w-full p-2 rounded border mb-3"
                      value={newItem.description}
                      onChange={(e) =>
                        setNewItem({ ...newItem, description: e.target.value })
                      }
                    />

                    {/* Image Uploads */}
                    <div className="grid grid-cols-2 gap-3 mb-4">
                      <div>
                        <label className="block text-xs font-bold text-gray-500 mb-1 uppercase">
                          Image 1 (Required)
                        </label>
                        <input
                          type="file"
                          accept="image/*"
                          required
                          onChange={(e) => handleFileChange(e, "image1")}
                          className="text-xs w-full bg-white border rounded p-1"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-bold text-gray-500 mb-1 uppercase">
                          Image 2 (Required)
                        </label>
                        <input
                          type="file"
                          accept="image/*"
                          required
                          onChange={(e) => handleFileChange(e, "image2")}
                          className="text-xs w-full bg-white border rounded p-1"
                        />
                      </div>
                    </div>

                    <button
                      type="submit"
                      disabled={isSavingItem}
                      className="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 font-bold disabled:bg-blue-400"
                    >
                      {isSavingItem ? "Saving..." : "Save Item"}
                    </button>
                  </form>
                )}

                {/* Items List */}
                <div className="border rounded-lg overflow-hidden">
                  <table className="w-full text-sm text-left">
                    <thead className="bg-gray-50 text-gray-500 font-bold">
                      <tr>
                        <th className="p-3">Item</th>
                        <th className="p-3">Description</th>
                        <th className="p-3 text-right">Value</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {items.length === 0 ? (
                        <tr>
                          <td
                            colSpan="3"
                            className="p-4 text-center text-gray-400"
                          >
                            No items listed on this policy.
                          </td>
                        </tr>
                      ) : (
                        items.map((item, idx) => (
                          <tr
                            key={item.ItemID || idx}
                            className="hover:bg-gray-50"
                          >
                            <td className="p-3 font-medium text-gray-800">
                              {item.Name}
                            </td>
                            <td className="p-3 text-gray-500">
                              {item.Description}
                            </td>
                            <td className="p-3 text-right font-mono">
                              ${item.Value?.toLocaleString()}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-red-500 text-center">
              Failed to load policy data.
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="p-4 border-t border-gray-100 bg-gray-50 shrink-0 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-600 font-semibold hover:bg-gray-200 rounded-lg transition"
          >
            Close
          </button>
          <button
            onClick={() => onOpenClaimModal(details)}
            className="px-6 py-2 bg-red-500 text-white font-bold rounded-lg hover:bg-red-600 shadow-md transition flex items-center gap-2"
          >
            Submit Claim
          </button>
        </div>
      </div>
    </div>
  );
};

// --- Main Component ---

function UserHomePage() {
  const [sidebaropen, setSidebaropen] = useState(false);

  // Modals Control
  const [isClaimModalOpen, setIsClaimModalOpen] = useState(false);
  const [selectedPolicyId, setSelectedPolicyId] = useState(null); // For Detail Modal
  const [claimPolicyData, setClaimPolicyData] = useState(null); // Data to pass to Claim Modal

  const [policies, setPolicies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(null);

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
      setLoading(false);
      navigate("/");
      return;
    }

    const API_URL = `http://127.0.0.1:8000/api/policies/`;

    const fetchPolicies = async () => {
      // Mock Data Fallback (Used if API fails)
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
        {
          policy_id: "P003",
          policy_name: "Life Basic",
          status: "Active",
          coverage_amount: 250000,
          start_date: "2023-11-20",
          premium: 450,
        },
      ];

      try {
        const response = await fetch(API_URL, {
          method: "GET",
          headers: { "x-user-id": String(storedUserID) },
        });

        if (!response.ok) throw new Error(`Server Status: ${response.status}`);

        const text = await response.text();
        let data = [];
        try {
          data = JSON.parse(text);
        } catch (err) {
          console.error("Not JSON:", err);
        }

        let finalPolicies = [];
        if (data && Array.isArray(data.policies)) {
          finalPolicies = data.policies;
        } else if (Array.isArray(data)) {
          finalPolicies = data;
        }

        if (finalPolicies.length > 0) {
          setPolicies(finalPolicies);
        } else {
          console.log("API returned empty list. Switching to Mock Data.");
          setPolicies(mockPolicies);
        }
        setFetchError(null);
      } catch (error) {
        console.warn(
          "Network error or API unreachable. Switching to Mock Data.",
          error
        );
        setPolicies(mockPolicies);
        setFetchError(null);
      } finally {
        setLoading(false);
      }
    };

    fetchPolicies();
  }, [storedUserID, navigate]);

  const handleNavItemClick = (item) => {
    if (item.name === "Submit Claim") {
      setIsClaimModalOpen(true);
    } else {
      setSidebaropen(false);
      if (item.path && item.path !== "#") navigate(item.path);
    }
  };

  const handlePolicyClick = (policy) => {
    const id = policy.PolicyID || policy.policy_id;
    setSelectedPolicyId(id);
  };

  const handleOpenClaimFromDetails = (policyDetails) => {
    setClaimPolicyData(policyDetails);
    setSelectedPolicyId(null);
    setIsClaimModalOpen(true);
  };

  const PolicyCard = ({ policy, onClick }) => (
    <div
      onClick={onClick}
      className="bg-white p-6 shadow-lg rounded-xl border border-blue-100 hover:shadow-xl transition duration-200 cursor-pointer group"
    >
      <div className="flex justify-between items-start mb-4">
        <h2 className="text-xl font-extrabold text-blue-700 truncate group-hover:text-blue-800">
          {policy.policy_name ||
            `Policy #${policy.PolicyID || policy.policy_id}`}
        </h2>
        <span
          className={`text-sm font-semibold px-3 py-1 rounded-full ${
            (policy.status || policy.Status) === "Active"
              ? "bg-green-100 text-green-700"
              : "bg-yellow-100 text-yellow-700"
          }`}
        >
          {policy.status || policy.Status || "Unknown"}
        </span>
      </div>

      <p className="text-sm text-gray-500 mb-2">
        Policy ID:{" "}
        <span className="font-mono text-gray-700">
          {policy.PolicyID || policy.policy_id}
        </span>
      </p>
      <p className="text-3xl font-bold text-gray-900 mb-4">
        $
        {policy.coverage_amount
          ? policy.coverage_amount.toLocaleString()
          : "N/A"}
      </p>

      <div className="flex justify-between text-sm text-gray-600 border-t pt-4 mt-2">
        <div>
          <span className="font-medium">Start:</span>{" "}
          {policy.start_date || policy.CreatedAt
            ? new Date(
                policy.start_date || policy.CreatedAt
              ).toLocaleDateString()
            : "N/A"}
        </div>
        <div className="text-blue-600 font-bold group-hover:underline">
          View Details →
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
              className="flex items-center w-full text-left p-3 rounded-lg text-gray-700 hover:bg-blue-100 hover:text-blue-700 transition duration-150"
              onClick={() => handleNavItemClick(item)}
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
          <h1 className="text-2xl font-extrabold text-gray-800">
            Policies Dashboard
          </h1>
          <div
            className="bg-blue-500 w-10 h-10 rounded-full flex items-center justify-center text-white font-bold cursor-default shadow-lg"
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
            <div className="text-center p-10 text-gray-500 text-lg flex flex-col items-center">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mb-3"></div>
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
            <div className="text-center p-10 bg-white rounded-lg shadow-lg border border-gray-200">
              <p className="text-xl text-gray-600 font-semibold">
                You don't have any active policies yet.
              </p>
              <p className="text-gray-500 mt-2">
                Please contact an insurance agent to have a policy assigned to
                you.
              </p>
            </div>
          )}

          <div className="grid sm:grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 pb-10">
            {policies.map((policy) => (
              <PolicyCard
                key={policy.policy_id || policy.PolicyID}
                policy={policy}
                onClick={() => handlePolicyClick(policy)}
              />
            ))}
          </div>
        </div>
      </main>

      {/* Modals */}
      {selectedPolicyId && (
        <PolicyDetailsModal
          policyId={selectedPolicyId}
          userID={storedUserID}
          onClose={() => setSelectedPolicyId(null)}
          onOpenClaimModal={handleOpenClaimFromDetails}
        />
      )}

      {isClaimModalOpen && (
        <SubmitClaimModal
          onClose={() => setIsClaimModalOpen(false)}
          userID={storedUserID}
          selectedPolicy={claimPolicyData}
        />
      )}
    </div>
  );
}

export default UserHomePage;
