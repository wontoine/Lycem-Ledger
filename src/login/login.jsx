import React, { useState } from "react";
import { User, Lock } from "lucide-react";
import "./LoginForm.css";
import { useNavigate } from "react-router-dom";

const UserIcon = ({ size = 24, className = "" }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
    <circle cx="12" cy="7" r="4" />
  </svg>
);

const LockIcon = ({ size = 24, className = "" }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
  </svg>
);
const Login = () => {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    setErrorMessage("");

    // Trim to avoid accidental whitespace causing 401
    const uname = (username || "").trim();
    const pwd = (password || "").trim();

    console.log("Username:", uname, "Password:", pwd);

    // Prepare payload: backend accepts username or email; if the input looks like an email, send in both fields
    const looksLikeEmail = uname.includes("@");
    const body = looksLikeEmail
      ? { username: uname, email: uname, password: pwd }
      : { username: uname, password: pwd };

    fetch("http://127.0.0.1:8000/api/auth/login/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    })
      .then(async (response) => {
        // Try to parse JSON for both success and error responses
        let data = null;
        try {
          data = await response.json();
        } catch (_e) {
          // Non-JSON or empty body
        }

        if (!response.ok) {
          const detail = (data && (data.error?.detail || data.error || data.message)) || `HTTP ${response.status}`;
          throw new Error(typeof detail === "string" ? detail : `HTTP error! Status: ${response.status}`);
        }

        return data;
      })
      .then((data) => {
        if (data.approved) {
          if (data.user.roleID === 1) {
            navigate("/home");
            localStorage.setItem("userID", data.user.userid);
            localStorage.setItem("userRoleID", data.user.roleID);
          } else if (data.user.roleID === 2) {
            console.log(data);
            navigate("/agentHomePage");
            localStorage.setItem("userID", data.user.userid);
            localStorage.setItem("userRoleID", data.user.roleID);
          } else if (data.user.roleID === 3) {
            console.log(data);
            navigate("/managerHomePage");
            localStorage.setItem("userID", data.user.userid);
            localStorage.setItem("userRoleID", data.user.roleID);
          } else if (data.user.roleID === 4) {
            console.log(data);
            navigate("/adminHomePage");
            localStorage.setItem("userID", data.user.userid);
            localStorage.setItem("userRoleID", data.user.roleID);
          } else {
            console.log(data.user);
            setErrorMessage("Login failed: Insufficient permissions");
          }
        } else {
          setErrorMessage("Login failed: User not approved");
        }
      })
      .catch((error) => {
        console.error("Error during login:", error);
        setErrorMessage(String(error?.message || error));
      });
  };

  return (
    <div className="login-page">
      <div className="login-card">
        {/* Header Section */}
        <div className="header">
          <h1 className="title">Welcome back</h1>
          <p className="subtitle">Please enter your details</p>
        </div>

        <form onSubmit={handleSubmit}>
          {/* Error message */}
          {errorMessage && (
            <div className="error-text" style={{ color: "#b00020", marginBottom: 12 }}>
              {errorMessage}
            </div>
          )}
          {/* Username Input */}
          <div className="form-group">
            <input
              type="text"
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              className="input-field"
            />
            <div className="icon-wrapper">
              <UserIcon />
            </div>
          </div>

          {/* Password Input */}
          <div className="form-group">
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="input-field"
            />
            <div className="icon-wrapper">
              <LockIcon />
            </div>
          </div>

          {/* Forgot Password Link */}
          <div className="forgot-password">
            <a href="#" className="forgot-link">
              Forgot password?
            </a>
          </div>

          {/* Submit Button */}
          <button type="submit" className="submit-btn">
            Login
          </button>

          {/* Sign up prompt */}
          <div className="signup-text">
            Don't have an account?{" "}
            <a href="#" className="signup-link">
              Sign up
            </a>
          </div>
        </form>
      </div>
    </div>
  );
};
export default Login;
