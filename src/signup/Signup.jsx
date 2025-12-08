import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { apiUrl } from "../lib/api";

function Signup() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    email: "",
    username: "",
    customerPlanID: "",
    password: "",
  });
  const [status, setStatus] = useState({ loading: false, error: "", message: "" });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setStatus({ loading: true, error: "", message: "" });

    const payload = {
      email: form.email.trim(),
      username: form.username.trim(),
      customerPlanID: form.customerPlanID ? Number(form.customerPlanID) : undefined,
      password: form.password,
    };

    try {
      const res = await fetch(apiUrl("/api/auth/create-account/"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail =
          (data && (data.error?.detail || data.error || data.message)) ||
          `Sign up failed (HTTP ${res.status})`;
        throw new Error(typeof detail === "string" ? detail : `HTTP ${res.status}`);
      }

      setStatus({ loading: false, error: "", message: "Account created! Redirecting to login..." });
      // Give a brief success pause, then go to login
      setTimeout(() => navigate("/", { replace: true }), 900);
    } catch (err) {
      setStatus({ loading: false, error: String(err?.message || err), message: "" });
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="header">
          <h1 className="title">Create your account</h1>
          <p className="subtitle">Use the email on your policy to sign up</p>
        </div>

        <form onSubmit={handleSubmit}>
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
              type="email"
              name="email"
              placeholder="Email (must match policy records)"
              value={form.email}
              onChange={handleChange}
              required
              className="input-field"
            />
          </div>

          <div className="form-group">
            <input
              type="text"
              name="username"
              placeholder="Username"
              value={form.username}
              onChange={handleChange}
              required
              className="input-field"
            />
          </div>

          <div className="form-group">
            <input
              type="number"
              name="customerPlanID"
              placeholder="Customer Plan ID"
              value={form.customerPlanID}
              onChange={handleChange}
              required
              className="input-field"
            />
          </div>

          <div className="form-group">
            <input
              type="password"
              name="password"
              placeholder="Password"
              value={form.password}
              onChange={handleChange}
              required
              className="input-field"
            />
          </div>

          <button type="submit" className="submit-btn" disabled={status.loading}>
            {status.loading ? "Creating..." : "Create account"}
          </button>

          <div className="signup-text" style={{ marginTop: 12 }}>
            Already have an account? <Link to="/" className="signup-link">Back to login</Link>
          </div>
        </form>
      </div>
    </div>
  );
}

export default Signup;
