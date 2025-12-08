import React, { useState } from "react";
import { apiUrl } from "../lib/api";

function SubmitClaimModal({ onClose, userID, selectedPolicy }) {
  // Resolve customerPlanID from various possible shapes
  const resolvedCustomerPlanID = selectedPolicy
    ? (
        selectedPolicy.customerPlanID ||
        selectedPolicy.CustomerPlanID ||
        selectedPolicy.policy_id ||
        selectedPolicy.PolicyID ||
        selectedPolicy.planID ||
        selectedPolicy.planId ||
        ""
      )
    : "";

  const [claimData, setClaimData] = useState({
    // We keep this for display, but won't send it as 'customer_id' to backend
    // to avoid confusing UserID (e.g. 55) with CustomerID (e.g. 1001)
    CustomerID: userID,
    CustomerPlanID: resolvedCustomerPlanID,
    Amount: "",
    Reason: "",
  });

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setClaimData((prevData) => ({
      ...prevData,
      [name]: value,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);

    // Prepare payload
    // Note: We intentionally omit 'customer_id' here. The backend's ClaimListCreateView
    // will automatically look up the correct CustomerID for this user via the x-user-id header.
    const payload = {
      customerPlanID: claimData.CustomerPlanID,
      amount: parseFloat(claimData.Amount),
      reason: claimData.Reason,
    };

    // Corrected URL matching urls.py path("api/claims/", ...)
    const API_URL = apiUrl("/api/claims/");

    try {
      const response = await fetch(API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-user-id": String(userID), // Authenticate as the logged-in UserID
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        let errorData;
        try {
          errorData = await response.json();
        } catch (e) {
          throw new Error(`HTTP error! Status: ${response.status}`);
        }
        throw new Error(errorData.error || JSON.stringify(errorData));
      }

      const result = await response.json();
      console.log("Claim submitted successfully:", result);

      const rid = result.claimID || result.ClaimID || "(unknown)";
      alert(`Claim #${rid} submitted successfully!`);
      onClose();
    } catch (err) {
      console.error("Error submitting claim:", err.message);
      setError(`Submission failed: ${err.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-gray-600 bg-opacity-75 flex items-center justify-center z-50">
      <div className="bg-white p-6 rounded-lg shadow-2xl w-full max-w-lg mx-4">
        <div className="flex justify-between items-center border-b pb-3 mb-4">
          <h2 className="text-2xl font-bold text-gray-800">Submit New Claim</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-900 text-3xl font-light"
            disabled={isSubmitting}
          >
            &times;
          </button>
        </div>

        {selectedPolicy && (
          <div className="bg-blue-50 border-l-4 border-blue-500 p-3 mb-5 rounded text-blue-800">
            <p className="font-bold text-sm uppercase tracking-wide text-blue-600">
              Selected Policy
            </p>
            <p className="font-bold text-lg">
              {selectedPolicy.policy_name || selectedPolicy.PlanName || "Unnamed Policy"}
            </p>
            <p className="text-sm opacity-80">
              Coverage Limit: $
              {(selectedPolicy.coverage_amount || selectedPolicy.CoverageLim || 0).toLocaleString()}
            </p>
          </div>
        )}

        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative mb-4">
            <strong className="font-bold">Error! </strong>
            <span className="block sm:inline">{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="space-y-4">
            {/* Displaying UserID here labeled as Customer ID.
               Note: To the backend, UserID != CustomerID, but for UI simplicity we just show the logged-in ID.
            */}
            <div className="flex items-center justify-between bg-gray-50 p-3 rounded-md border border-gray-200">
              <label className="text-sm font-medium text-gray-700">
                User ID
              </label>
              <span className="text-sm font-mono font-bold text-gray-600">
                {claimData.CustomerID}
              </span>
            </div>

            <div>
              <label
                htmlFor="CustomerPlanID"
                className="block text-sm font-medium text-gray-700"
              >
                Customer Plan ID <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                name="CustomerPlanID"
                id="CustomerPlanID"
                value={claimData.CustomerPlanID}
                onChange={handleChange}
                required
                readOnly={!!selectedPolicy}
                disabled={isSubmitting || !!selectedPolicy}
                className={`mt-1 block w-full border rounded-md shadow-sm p-2 focus:ring-blue-500 focus:border-blue-500 ${
                  selectedPolicy
                    ? "bg-gray-100 text-gray-500 border-gray-300 cursor-not-allowed"
                    : "border-gray-300"
                }`}
                placeholder="e.g., 2"
              />
            </div>

            <div>
              <label
                htmlFor="Amount"
                className="block text-sm font-medium text-gray-700"
              >
                Claim Amount ($) <span className="text-red-500">*</span>
              </label>
              <input
                type="number"
                name="Amount"
                id="Amount"
                value={claimData.Amount}
                onChange={handleChange}
                required
                min="1"
                step="0.01"
                disabled={isSubmitting}
                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="e.g., 500.00"
              />
            </div>

            <div>
              <label
                htmlFor="Reason"
                className="block text-sm font-medium text-gray-700"
              >
                Reason for Claim <span className="text-red-500">*</span>
              </label>
              <textarea
                name="Reason"
                id="Reason"
                value={claimData.Reason}
                onChange={handleChange}
                rows="3"
                required
                disabled={isSubmitting}
                className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="Describe the incident briefly..."
              ></textarea>
            </div>
          </div>

          <div className="flex justify-end pt-4 mt-6 border-t space-x-3">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="bg-gray-200 text-gray-800 px-4 py-2 rounded-lg hover:bg-gray-300 transition"
            >
              Cancel
            </button>

            <button
              type="submit"
              disabled={isSubmitting}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:bg-blue-400 flex items-center transition shadow-md"
            >
              {isSubmitting ? "Processing..." : "Submit Claim"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default SubmitClaimModal;