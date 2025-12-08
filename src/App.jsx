import { Routes, Route } from "react-router-dom";
import "./App.css";
import Login from "./login/login.jsx";
import UserHomePage from "./userHomePage/userHomePage.jsx";
import SubmitClaimModal from "./userHomePage/submitClaim.jsx";
import ManagerHomePage from "./managerHomePage/managerHomePage.jsx";
import AgentHomePage from "./agentHomePage/agentHomePage.jsx";
import UserClaimsPage from "./userHomePage/userClaimPage.jsx";
import Signup from "./signup/Signup.jsx";
import ForgotPassword from "./forgot/ForgotPassword.jsx";


function App() {
  return (
    <div className="App">
      <Routes>
        <Route path="/" element={<Login />} />
        <Route path="/home" element={<UserHomePage />} />
        <Route path="/claims" element={<UserClaimsPage />} />
        <Route path="/managerHomePage" element={<ManagerHomePage />} />
        <Route path="/agentHomePage" element={<AgentHomePage />} />
        <Route path="/submitClaim" element={<SubmitClaimModal />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
      </Routes>
    </div>
  );
}

export default App;