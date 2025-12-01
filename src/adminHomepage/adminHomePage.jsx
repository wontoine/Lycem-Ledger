import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

function AdminHomePage() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [auditLogs, setAuditLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(null);
  const [activeTab, setActiveTab] = useState("logs");
  const [expandedRows, setExpandedRows] = useState({});

  const navigate = useNavigate();
  const storedUserID = localStorage.getItem("userID");
  const storedRoleID = localStorage.getItem("userRoleID");

  const navItems = [{ id: "logs", name: "Audit Logs" }];

  const toggleRow = (index) => {
    setExpandedRows((prev) => ({
      ...prev,
      [index]: !prev[index],
    }));
  };

  const fetchAuditLogs = async () => {
    setLoading(true);
    setFetchError(null);

    try {
      const response = await fetch("http://127.0.0.1:8000/api/admin/audit-logs/", {
        headers: {
          "Content-Type": "application/json",
          "x-user-id": String(storedUserID),
        },
      });

      const data = await response.json();
      console.log("Audit Logs:", data);

      setAuditLogs(data.logs || []);
    } catch (error) {
      console.error(error);
      setFetchError("Could not load audit logs.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAuditLogs();
  }, []);

  const handleSignOut = () => {
    localStorage.clear();
    navigate("/", { replace: true });
  };

  // -------------------------------------------
  // 🔵 AUDIT LOG TABLE WITH EXPANDABLE DETAILS
  // -------------------------------------------
  const renderAuditLogTable = () => (
    <div className="bg-white rounded-xl shadow-lg border border-gray-200">
      <div className="p-4 border-b bg-gray-50 flex justify-between items-center">
        <h3 className="text-lg font-bold text-gray-700">System Audit Logs</h3>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-100 uppercase text-gray-500 font-bold text-xs">
            <tr>
              <th className="p-4">Timestamp</th>
              <th className="p-4">Actor</th>
              <th className="p-4">Action</th>
              <th className="p-4">Target</th>
              <th className="p-4">Info</th>
            </tr>
          </thead>

          <tbody>
            {auditLogs.length === 0 ? (
              <tr>
                <td colSpan="5" className="p-6 text-center text-gray-400 italic">
                  No logs available.
                </td>
              </tr>
            ) : (
              auditLogs.map((log, index) => (
                <React.Fragment key={index}>
                  {/* MAIN ROW */}
                  <tr className="border-b hover:bg-gray-50 transition">
                    <td className="p-4">{log.CreatedAt}</td>
                    <td className="p-4">{log.ActorUserID}</td>
                    <td className="p-4 font-semibold">{log.Action}</td>
                    <td className="p-4">
                      {log.TargetType} #{log.TargetID}
                    </td>
                    <td className="p-4">
                      <button
                        onClick={() => toggleRow(index)}
                        className="text-blue-600 underline text-sm hover:text-blue-800"
                      >
                        {expandedRows[index] ? "Hide Details" : "Show Details"}
                      </button>
                    </td>
                  </tr>

                  {/* EXPANDED DETAILS ROW */}
                  {expandedRows[index] && (
                    <tr className="bg-gray-50 border-b">
                      <td colSpan="5" className="p-4">
                        <div className="text-sm text-gray-700 space-y-2">
                          <div><strong>Log ID:</strong> {log.LogID}</div>
                          <div><strong>ActorUserID:</strong> {log.ActorUserID}</div>
                          <div><strong>Action:</strong> {log.Action}</div>
                          <div><strong>Target:</strong> {log.TargetType} #{log.TargetID}</div>
                          <div><strong>CreatedAt:</strong> {log.CreatedAt}</div>

                          <div>
                            <strong>Details:</strong>
                            <pre className="mt-2 p-3 bg-white rounded border border-gray-200 overflow-auto text-xs">
{JSON.stringify(log.Details || {}, null, 2)}
                            </pre>
                          </div>

                          {/* Automatically show any unknown fields */}
                          {Object.entries(log)
                            .filter(([key]) =>
                              ![
                                "LogID",
                                "ActorUserID",
                                "Action",
                                "TargetType",
                                "TargetID",
                                "Details",
                                "CreatedAt",
                              ].includes(key)
                            )
                            .map(([key, value]) => (
                              <div key={key}>
                                <strong>{key}:</strong> {JSON.stringify(value)}
                              </div>
                            ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );

  // -------------------------------------------
  // 🔵 PAGE LAYOUT
  // -------------------------------------------
  return (
    <div className="flex bg-gray-100 min-h-screen font-sans">
      {/* SIDEBAR */}
      <div
        className={`fixed inset-y-0 left-0 bg-white w-64 shadow-2xl transform transition-transform duration-300 z-40
          ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}
          lg:static lg:translate-x-0 border-r border-gray-200`}
      >
        <div className="p-6 flex justify-between items-center border-b border-gray-100">
          <div className="text-2xl font-extrabold text-blue-700 tracking-tight">Admin Portal</div>
          <button className="lg:hidden text-gray-500" onClick={() => setSidebarOpen(false)}>✕</button>
        </div>

        <nav className="p-4 space-y-2">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => {
                setActiveTab(item.id);
                setSidebarOpen(false);
              }}
              className={`flex w-full p-3 rounded-lg transition text-left font-semibold
                ${activeTab === item.id ? "bg-blue-100 text-blue-700" : "text-gray-700 hover:bg-gray-50"}`}
            >
              {item.name}
            </button>
          ))}
        </nav>

        <div className="absolute bottom-6 left-0 w-full px-6">
          <button
            onClick={handleSignOut}
            className="w-full py-2 bg-red-100 text-red-600 rounded-lg font-semibold hover:bg-red-200"
          >
            Sign Out
          </button>
        </div>
      </div>

      {/* MAIN CONTENT */}
      <main className="flex-1 flex flex-col h-screen overflow-hidden">
        <header className="bg-white shadow-sm p-4 flex items-center justify-between">
          <button className="lg:hidden p-2 text-gray-600" onClick={() => setSidebarOpen(true)}>☰</button>

          <div className="flex items-center gap-3 py-1 px-3 bg-gray-50 rounded-xl border border-gray-200">
            <div className="w-8 h-8 bg-purple-100 text-purple-700 rounded-full flex items-center justify-center font-bold text-sm">A</div>
            <div>
              <p className="text-sm font-bold text-gray-700">Administrator</p>
              <p className="text-xs text-gray-500 mt-1">ID: {storedUserID}</p>
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-8">
          <h1 className="text-3xl font-bold text-gray-800 mb-6">
            {navItems.find((n) => n.id === activeTab)?.name}
          </h1>

          {loading ? (
            <div className="flex justify-center items-center h-64 flex-col gap-4 text-gray-400">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
              <p>Loading...</p>
            </div>
          ) : (
            <>
              {activeTab === "logs" && renderAuditLogTable()}
            </>
          )}
        </div>
      </main>
    </div>
  );
}

export default AdminHomePage;
