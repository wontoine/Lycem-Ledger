import React, { useState, useEffect } from "react";
import { apiUrl } from "../lib/api";
import { useNavigate } from "react-router-dom";
import SubmitClaimModal from "./submitClaim";

// Component: Modal displaying detailed information about a specific policy
// It fetches deeper details (like insured items) when opened.
const PolicyDetailsModal = ({
  policyId,
  userID,
  onClose,
  onOpenClaimModal,
}) => {
  const [details, setDetails] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  // State for the "Add New Item" sub-form within the modal
  const [showAddForm, setShowAddForm] = useState(false);
  const [isSavingItem, setIsSavingItem] = useState(false);

  // Form State: Captures input for adding a new insured item
  const [newItem, setNewItem] = useState({
    name: "",
    estimatedValue: "",
    description: "",
    category: "Electronics",
    purchaseDate: "",
  });

  // State: Stores file objects for item images
  const [itemImages, setItemImages] = useState({
    image1: null,
    image2: null,
  });

  // Fetch detailed policy data (including items) when the modal mounts
  useEffect(() => {
    const fetchDetails = async () => {
      try {
        const response = await fetch(
          apiUrl(`/api/auth/policies/${policyId}`),
          {
            headers: {
              "Content-Type": "application/json",
            },
          }
        );

        if (!response.ok) throw new Error("Fetch failed");

        const data = await response.json();
        setDetails(data.policy || data);
        setItems(data.items || []);
      } catch (error) {
        console.warn("Error fetching policy details:", error);
      } finally {
        setLoading(false);
      }
    };

    if (policyId) fetchDetails();
  }, [policyId, userID]);

  // Handler for file inputs (image uploads)
  const handleFileChange = (e, key) => {
    if (e.target.files && e.target.files[0]) {
      setItemImages((prev) => ({ ...prev, [key]: e.target.files[0] }));
    }
  };

  // Submits the new item to the backend (Multipart form data for images)
  const handleAddItem = async (e) => {
    e.preventDefault();

    if (!itemImages.image1 || !itemImages.image2) {
      alert("Please upload both required images.");
      return;
    }

    setIsSavingItem(true);

    try {
      const formData = new FormData();

      // Format date for backend compatibility
      const dateStr = newItem.purchaseDate
        ? new Date(newItem.purchaseDate).toISOString().split(".")[0]
        : new Date().toISOString().split(".")[0];

      formData.append("name", newItem.name);
      formData.append("estimatedValue", newItem.estimatedValue);
      formData.append("customerPlanID", policyId);
      formData.append("customerID", userID);
      formData.append("description", newItem.description);
      formData.append("Category", newItem.category);
      formData.append("purchaseDate", dateStr);
      formData.append("image1", itemImages.image1);
      formData.append("image2", itemImages.image2);

      const response = await fetch(
        apiUrl(`/api/auth/items/add/`),
        {
          customerID: userID,
          customerPlanID: policyId,
          method: "POST",
          body: formData,
        }
      );

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(errText);
      }

      const savedData = await response.json();

      // Update local list with the newly created item
      const newItemObj = savedData.item || savedData;
      setItems([...items, newItemObj]);

      // Reset Form fields
      setNewItem({
        name: "",
        estimatedValue: "",
        description: "",
        category: "Electronics",
        purchaseDate: "",
      });
      setItemImages({ image1: null, image2: null });
      setShowAddForm(false);
      alert("Item added successfully!");
    } catch (error) {
      console.error("Add Item Error:", error);
      alert("Failed to add item. Please try again.");
    } finally {
      setIsSavingItem(false);
    }
  };

  if (!policyId) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex justify-center items-center p-4 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl overflow-hidden animate-fade-in-up max-h-[90vh] flex flex-col">
        {/* Modal Header */}
        <div className="bg-blue-600 p-6 flex justify-between items-start text-white shrink-0">
          <div>
            <h2 className="text-2xl font-bold">Policy Details</h2>
            <p className="text-blue-100 text-sm">Policy ID: {policyId}</p>
          </div>
          <button
            onClick={onClose}
            className="text-white hover:text-blue-200 text-2xl font-bold leading-none focus:outline-none"
            title="Close"
          >
            ✕
          </button>
        </div>

        {/* Modal Content Area */}
        <div className="p-6 overflow-y-auto flex-1">
          {loading ? (
            <div className="text-center py-10 text-gray-500">
              Loading details...
            </div>
          ) : details ? (
            <div className="space-y-6">
              {/* Policy Summary Card */}
              <div className="grid grid-cols-2 gap-4 bg-blue-50 p-4 rounded-xl border border-blue-100">
                <div>
                  <p className="text-xs font-bold text-blue-800 uppercase">
                    Status
                  </p>
                  <p className="text-gray-700 font-semibold">
                    {details.status || details.Status || "Active"}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-bold text-blue-800 uppercase">
                    Premium
                  </p>
                  <p className="text-gray-700 font-mono">
                    $
                    {(
                      details.currentPremium ||
                      details.basePrice ||
                      0
                    ).toLocaleString()}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-bold text-blue-800 uppercase">
                    Start Date
                  </p>
                  <p className="text-gray-700">
                    {details.startDate
                      ? new Date(details.startDate).toLocaleDateString()
                      : "N/A"}
                  </p>
                </div>
              </div>

              {/* Insured Items Section */}
              <div>
                <div className="flex justify-between items-center mb-3">
                  <h3 className="text-lg font-bold text-gray-800">
                    Insured Items
                  </h3>
                  <button
                    onClick={() => setShowAddForm(!showAddForm)}
                    className="bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold px-3 py-1.5 rounded-lg shadow transition"
                  >
                    {showAddForm ? "Cancel" : "+ Add Item"}
                  </button>
                </div>

                {/* Add Item Form (Conditionally Rendered) */}
                {showAddForm && (
                  <form
                    onSubmit={handleAddItem}
                    className="bg-gray-100 p-4 rounded-lg border border-gray-300 shadow-inner mb-4"
                  >
                    <h4 className="font-bold text-gray-700 mb-3 border-b pb-1">
                      New Item Details
                    </h4>

                    <div className="grid grid-cols-2 gap-3 mb-3">
                      <div>
                        <label className="text-xs font-bold text-gray-500">
                          Item Name
                        </label>
                        <input
                          type="text"
                          required
                          className="w-full p-2 rounded border"
                          value={newItem.name}
                          onChange={(e) =>
                            setNewItem({ ...newItem, name: e.target.value })
                          }
                        />
                      </div>
                      <div>
                        <label className="text-xs font-bold text-gray-500">
                          Est. Value ($)
                        </label>
                        <input
                          type="number"
                          required
                          className="w-full p-2 rounded border"
                          value={newItem.estimatedValue}
                          onChange={(e) =>
                            setNewItem({
                              ...newItem,
                              estimatedValue: e.target.value,
                            })
                          }
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-3 mb-3">
                      <div>
                        <label className="text-xs font-bold text-gray-500">
                          Category
                        </label>
                        <select
                          className="w-full p-2 rounded border bg-white"
                          value={newItem.category}
                          onChange={(e) =>
                            setNewItem({ ...newItem, category: e.target.value })
                          }
                        >
                          <option value="Electronics">Electronics</option>
                          <option value="Jewelry">Jewelry</option>
                          <option value="Furniture">Furniture</option>
                          <option value="Appliances">Appliances</option>
                          <option value="Other">Other</option>
                        </select>
                      </div>
                      <div>
                        <label className="text-xs font-bold text-gray-500">
                          Purchase Date
                        </label>
                        <input
                          type="date"
                          required
                          className="w-full p-2 rounded border"
                          value={newItem.purchaseDate}
                          onChange={(e) =>
                            setNewItem({
                              ...newItem,
                              purchaseDate: e.target.value,
                            })
                          }
                        />
                      </div>
                    </div>

                    <div className="mb-3">
                      <label className="text-xs font-bold text-gray-500">
                        Description
                      </label>
                      <input
                        type="text"
                        className="w-full p-2 rounded border"
                        value={newItem.description}
                        onChange={(e) =>
                          setNewItem({
                            ...newItem,
                            description: e.target.value,
                          })
                        }
                      />
                    </div>

                    {/* Image Upload Inputs */}
                    <div className="grid grid-cols-2 gap-3 mb-4">
                      <div>
                        <label className="block text-xs font-bold text-gray-500 mb-1">
                          Image 1 (Req)
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
                        <label className="block text-xs font-bold text-gray-500 mb-1">
                          Image 2 (Req)
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
                      className="w-full bg-green-600 text-white py-2 rounded hover:bg-green-700 font-bold disabled:bg-gray-400 shadow"
                    >
                      {isSavingItem ? "Uploading..." : "Save Item"}
                    </button>
                  </form>
                )}

                {/* Items List Table */}
                <div className="border rounded-lg overflow-hidden">
                  <table className="w-full text-sm text-left">
                    <thead className="bg-gray-50 text-gray-500 font-bold">
                      <tr>
                        <th className="p-3">Item</th>
                        <th className="p-3">Category</th>
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
                            No items added yet.
                          </td>
                        </tr>
                      ) : (
                        items.map((item, idx) => (
                          <tr
                            key={item.itemID || item.ItemID || idx}
                            className="hover:bg-gray-50"
                          >
                            <td className="p-3">
                              <div className="font-medium text-gray-800">
                                {item.name || item.Name}
                              </div>
                              <div className="text-xs text-gray-500">
                                {item.description || item.Description}
                              </div>
                            </td>
                            <td className="p-3 text-gray-600">
                              {item.category || item.Category || "N/A"}
                            </td>
                            <td className="p-3 text-right font-mono">
                              $
                              {(
                                item.estimatedValue ||
                                item.Value ||
                                0
                              ).toLocaleString()}
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

        {/* Modal Footer: Actions */}
        <div className="p-4 border-t border-gray-100 bg-gray-50 shrink-0 flex justify-end gap-3 rounded-b-2xl">
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

// --- Main Page Component ---
function UserHomePage() {
  const [sidebaropen, setSidebaropen] = useState(false);

  // States for managing modals (Policy Details vs Submit Claim)
  const [isClaimModalOpen, setIsClaimModalOpen] = useState(false);
  const [selectedPolicyId, setSelectedPolicyId] = useState(null);
  const [claimPolicyData, setClaimPolicyData] = useState(null);

  // Data states
  const [policies, setPolicies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(null);

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

  // On mount, verify user session and fetch their policies
  useEffect(() => {
    if (!storedUserID) {
      setLoading(false);
      navigate("/");
      return;
    }

    // Endpoint retrieves plans assigned to the logged-in UserID
    const API_URL = apiUrl(`/auth/customer/plans/?userID=${storedUserID}`);

    const fetchPolicies = async () => {
      // Fallback data structure for development/offline testing
      const mockPolicies = [
        {
          policy_id: "P001",
          policy_name: "Homeowner Plus (Mock)",
          status: "Active",
          coverage_amount: 500000,
          start_date: "2024-01-01",
          premium: 1200,
        },
      ];

      try {
        const response = await fetch(API_URL, {
          method: "GET",
          headers: {
            "Content-Type": "application/json",
          },
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

        // Normalize data structure (handle various API response formats)
        if (data && Array.isArray(data.plans)) {
          finalPolicies = data.plans;
        } else if (data && Array.isArray(data.policies)) {
          finalPolicies = data.policies;
        } else if (Array.isArray(data)) {
          finalPolicies = data;
        }

        if (finalPolicies.length > 0) {
          setPolicies(finalPolicies);
        } else {
          setPolicies(mockPolicies);
        }
        setFetchError(null);
      } catch (error) {
        console.warn("Network error. Switching to Mock Data.", error);
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

  // Opens the details modal for a specific policy
  const handlePolicyClick = (policy) => {
    // Determine the correct ID field based on data source
    const id = policy.customerPlanID || policy.PolicyID || policy.policy_id;
    if (id) {
      setSelectedPolicyId(id);
    } else {
      console.error("Clicked policy has no ID:", policy);
    }
  };

  // Transitions from the Details Modal to the Submit Claim Modal
  const handleOpenClaimFromDetails = (policyDetails) => {
    setClaimPolicyData(policyDetails);
    setSelectedPolicyId(null);
    setIsClaimModalOpen(true);
  };

  // Sub-component: Displays summary info for a single policy on the dashboard
  const PolicyCard = ({ policy, onClick }) => (
    <div
      onClick={onClick}
      className="bg-white p-6 shadow-lg rounded-xl border border-blue-100 hover:shadow-xl transition duration-200 cursor-pointer group"
    >
      <div className="flex justify-between items-start mb-4">
        <h2 className="text-xl font-extrabold text-blue-700 truncate group-hover:text-blue-800">
          {policy.planName ||
            policy.policy_name ||
            `Policy #${policy.customerPlanID || policy.PolicyID}`}
        </h2>
        <span
          className={`text-sm font-semibold px-3 py-1 rounded-full ${
            (policy.status || policy.Status || "").toLowerCase() === "active"
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
          {policy.customerPlanID || policy.PolicyID || policy.policy_id}
        </span>
      </p>

      <p className="text-3xl font-bold text-gray-900 mb-4">
        $
        {(
          policy.currentPremium ||
          policy.coverage_amount ||
          0
        ).toLocaleString()}
      </p>

      <div className="flex justify-between text-sm text-gray-600 border-t pt-4 mt-2">
        <div>
          <span className="font-medium">Start:</span>{" "}
          {policy.startDate || policy.start_date || policy.CreatedAt
            ? new Date(
                policy.startDate || policy.start_date || policy.CreatedAt
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

          {/* Policies Grid */}
          <div className="grid sm:grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 pb-10">
            {policies.map((policy) => (
              <PolicyCard
                key={
                  policy.customerPlanID || policy.policy_id || policy.PolicyID
                }
                policy={policy}
                onClick={() => handlePolicyClick(policy)}
              />
            ))}
          </div>
        </div>
      </main>

      {/* Conditional Modals */}
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