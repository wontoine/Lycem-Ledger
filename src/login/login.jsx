import React, { useState } from "react";
import { User, Lock } from "lucide-react";
import "./LoginForm.css";
import { useNavigate } from "react-router-dom";
import { apiUrl } from "../lib/api";

// Icon components for username and password fields
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

    // Ensure clean input to prevent accidental whitespace failures
    const uname = (username || "").trim();
    const pwd = (password || "").trim();

    console.log("Username:", uname, "Password:", pwd);

    // Build the request body:
    // If the username looks like an email, we send it as both 'username' and 'email'
    // to give the backend maximum flexibility in resolving the user.
    const looksLikeEmail = uname.includes("@");
    const body = looksLikeEmail
      ? { username: uname, email: uname, password: pwd }
      : { username: uname, password: pwd };

    fetch(apiUrl("/api/auth/login/"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    })
      .then(async (response) => {
        // Attempt to parse the JSON response body
        // If parsing fails (e.g. empty body or 500 error page), data remains null
        let data = null;
        try {
          data = await response.json();
        } catch (_e) {
          // Response was not JSON
        }

        if (!response.ok) {
          // Extract a meaningful error message from the response object or fallback to status text
          const detail = (data && (data.error?.detail || data.error || data.message)) || `HTTP ${response.status}`;
          throw new Error(typeof detail === "string" ? detail : `HTTP error! Status: ${response.status}`);
        }

        return data;
      })
      .then((data) => {
        if (data.approved) {
          // Store session data for authentication in subsequent requests
          localStorage.setItem("userID", data.user.userid);
          localStorage.setItem("userRoleID", data.user.roleID);

          // Route the user to the correct dashboard based on their Role ID
          // 1: Customer -> /home
          // 2: Agent    -> /agentHomePage
          // 3: Manager  -> /managerHomePage
          // 4: Admin    -> /adminHomePage
          if (data.user.roleID === 1) {
            navigate("/home");
          } else if (data.user.roleID === 2) {
            console.log(data);
            navigate("/agentHomePage");
          } else if (data.user.roleID === 3) {
            console.log(data);
            navigate("/managerHomePage");
          } else if (data.user.roleID === 4) {
            console.log(data);
            navigate("/adminHomePage");
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
        <div className="header">
          <h1 className="title">Welcome back</h1>
          <p className="subtitle">Please enter your details</p>
        </div>

        <form onSubmit={handleSubmit}>
          {/* Display any API or validation errors */}
          {errorMessage && (
            <div className="error-text" style={{ color: "#b00020", marginBottom: 12 }}>
              {errorMessage}
            </div>
          )}

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

          <div className="forgot-password">
            <a href="/forgot-password" className="forgot-link">
              Forgot password?
            </a>
          </div>

          <button type="submit" className="submit-btn">
            Login
          </button>

          <div className="signup-text">
            Don't have an account?{" "}
            <a href="/signup" className="signup-link">
              Sign up
            </a>
          </div>
        </form>
      </div>
    </div>
  );
};
export default Login;