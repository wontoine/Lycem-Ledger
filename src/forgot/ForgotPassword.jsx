import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { apiUrl } from "../lib/api";

function ForgotPassword() {
  const navigate = useNavigate();

  // State to track the user's input (email or username)
  const [identifier, setIdentifier] = useState("");

  // State to manage UI feedback: loading status, success messages, or errors
  const [status, setStatus] = useState({ loading: false, message: "", error: "" });

  // Handles the form submission to request a password reset
  const handleSubmit = async (e) => {
    e.preventDefault();
    setStatus({ loading: true, message: "", error: "" });

    // Prepare payload. The backend accepts 'identifier' which matches against username or email.
    const body = { identifier: identifier.trim() };

    try {
      const res = await fetch(apiUrl("/api/auth/forgot-password/"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      // Security Best Practice: User Enumeration Prevention.
      // Whether the account exists or not (200 OK) or if the request fails logic-wise,
      // we display the exact same success message. This prevents attackers from
      // determining which emails are valid in the system.
      if (res.ok) {
        setStatus({
          loading: false,
          message:
            "If an account exists for that email/username, a reset link or token has been sent.",
          error: "",
        });
      } else {
        // Even if the backend returns an error (e.g. 404 Not Found), show the generic success message.
        setStatus({
          loading: false,
          message:
            "If an account exists for that email/username, a reset link or token has been sent.",
          error: "",
        });
      }
    } catch (err) {
      // In case of network failure, stop loading but display the same generic message
      // to maintain security consistency.
      setStatus({
        loading: false,
        message:
          "If an account exists for that email/username, a reset link or token has been sent.",
        error: "",
      });
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="header">
          <h1 className="title">Forgot your password?</h1>
          <p className="subtitle">
            Enter your email or username and we'll send instructions to reset your password.
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          {/* Conditional rendering for feedback messages */}
          {status.error && (
            <div className="error-text" style={{ color: "#b00020", marginBottom: 12 }}>
              {status.error}
            </div>
          )}
          {status.message && (
            <div className="success-text" style={{ color: "#0a7", marginBottom: 12 }}>
              {status.message}
            </div>
          )}

          <div className="form-group">
            <input
              type="text"
              placeholder="Email or Username"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              required
              className="input-field"
            />
          </div>

          <button type="submit" className="submit-btn" disabled={status.loading}>
            {status.loading ? "Sending..." : "Send reset instructions"}
          </button>

          {/* Navigation back to the main login screen */}
          <div className="signup-text" style={{ marginTop: 12 }}>
            Remembered your password? <Link to="/" className="signup-link">Back to login</Link>
          </div>
        </form>
      </div>
    </div>
  );
}

export default ForgotPassword;