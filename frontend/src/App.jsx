import { useState, useEffect, useRef, useCallback } from "react";
import "./App.css";

const API = "";
let _nextId = 1;
const uid = () => String(_nextId++);

function makeSession(n) {
  return { id: uid(), name: `Chat ${n}`, messages: [], activePdf: null, asking: false, input: "" };
}

const ROLES = [
  { value: "procurement_manager", label: "Procurement Manager" },
  { value: "maintenance_engineer", label: "Maintenance Engineer" },
  { value: "facility_manager", label: "Facility Manager" },
  { value: "default", label: "General" },
];

export default function App() {
  const [documents, setDocuments] = useState([]);
  const [sessions, setSessions] = useState([makeSession(1)]);
  const [activeId, setActiveId] = useState(sessions[0].id);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [userContext, setUserContext] = useState({ user_id: "user_1", name: "User", role: "default" });
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);

  const active = sessions.find((s) => s.id === activeId) || sessions[0];

  function patchSession(id, patch) {
    setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, ...patch } : s)));
  }

  const fetchDocuments = useCallback(async () => {
    try {
      const res = await fetch(`${API}/documents`);
      const data = await res.json();
      setDocuments(data.documents || []);
    } catch { }
  }, []);

  useEffect(() => {
    fetchDocuments();
    const interval = setInterval(fetchDocuments, 5000);
    return () => clearInterval(interval);
  }, [fetchDocuments]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [active.messages]);

  // ── Sessions ──────────────────────────────────────
  function newSession() {
    const s = makeSession(sessions.length + 1);
    setSessions((prev) => [...prev, s]);
    setActiveId(s.id);
  }

  function closeSession(e, id) {
    e.stopPropagation();
    if (sessions.length === 1) return;
    const idx = sessions.findIndex((s) => s.id === id);
    const next = sessions.filter((s) => s.id !== id);
    setSessions(next);
    if (activeId === id) setActiveId(next[Math.max(0, idx - 1)].id);
  }

  // ── Upload ────────────────────────────────────────
  async function handleUpload(file) {
    if (!file || !file.name.endsWith(".pdf")) return;
    setUploading(true);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(`${API}/upload`, { method: "POST", body: form });
      if (!res.ok) throw new Error("Upload failed");
      await fetchDocuments();
    } catch (e) {
      alert("Upload failed: " + e.message);
    } finally {
      setUploading(false);
    }
  }

  function onFileInput(e) {
    const file = e.target.files?.[0];
    if (file) handleUpload(file);
    e.target.value = "";
  }

  function onDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleUpload(file);
  }

  // ── Delete document ───────────────────────────────
  async function deletePdf(e, doc) {
    e.stopPropagation();
    if (!confirm(`Delete "${doc.filename}"?`)) return;
    await fetch(`${API}/documents/${doc.pdf_id}`, { method: "DELETE" });
    setSessions((prev) =>
      prev.map((s) =>
        s.activePdf?.pdf_id === doc.pdf_id
          ? { ...s, activePdf: null, messages: [] }
          : s
      )
    );
    fetchDocuments();
  }

  // ── Select PDF (for active tab only) ─────────────
  function selectPdf(doc) {
    patchSession(activeId, {
      activePdf: active.activePdf?.pdf_id === doc.pdf_id ? null : doc,
      messages: [],
    });
  }

  // ── Chat ──────────────────────────────────────────
  async function sendMessage() {
    const question = active.input.trim();
    if (!question || active.asking) return;

    const withUser = [...active.messages, { role: "user", text: question }];
    const withLoader = [...withUser, { role: "assistant", text: "Thinking...", loading: true }];
    patchSession(activeId, { messages: withLoader, input: "", asking: true });

    try {
      const history = active.messages
        .filter((m) => !m.loading)
        .slice(-6)
        .map((m) => ({ role: m.role, content: m.text }));

      const res = await fetch(`${API}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          pdf_id: active.activePdf?.pdf_id || null,
          history,
          user_context: userContext.role !== "default" ? userContext : null,
        }),
      });
      const data = await res.json();
      setSessions((prev) =>
        prev.map((s) => {
          if (s.id !== activeId) return s;
          const msgs = [...s.messages];
          msgs[msgs.length - 1] = {
            role: "assistant",
            text: data.answer,
            sources: data.sources || [],
            loading: false,
          };
          return { ...s, messages: msgs, asking: false };
        })
      );
    } catch {
      setSessions((prev) =>
        prev.map((s) => {
          if (s.id !== activeId) return s;
          const msgs = [...s.messages];
          msgs[msgs.length - 1] = { role: "assistant", text: "Error: could not reach the server.", loading: false };
          return { ...s, messages: msgs, asking: false };
        })
      );
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>PDF Chat Agent</h1>
        <div className="role-selector">
          <label htmlFor="role-select">Role:</label>
          <select
            id="role-select"
            value={userContext.role}
            onChange={(e) => setUserContext((prev) => ({ ...prev, role: e.target.value }))}
          >
            {ROLES.map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
        </div>
      </header>

      <div className="main">
        {/* ── Left Sidebar ── */}
        <aside className="sidebar">
          <div className="sidebar-title">Documents</div>

          <div
            className={`upload-zone ${dragOver ? "drag-over" : ""}`}
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
          >
            <input ref={fileInputRef} type="file" accept=".pdf" onChange={onFileInput} />
            <div className="upload-icon">📄</div>
            <p><strong>Click or drag</strong> a PDF here</p>
          </div>

          {uploading && (
            <div className="upload-progress"><span>⏳</span> Uploading &amp; processing…</div>
          )}

          <div className="doc-list">
            {documents.length === 0 ? (
              <div className="doc-list-empty">No PDFs uploaded yet</div>
            ) : (
              documents.map((doc) => (
                <div
                  key={doc.pdf_id}
                  className={`doc-item ${active.activePdf?.pdf_id === doc.pdf_id ? "active" : ""}`}
                  onClick={() => selectPdf(doc)}
                  title={doc.filename}
                >
                  <span className="doc-icon">📑</span>
                  <span className="doc-name">{doc.filename || doc.pdf_id}</span>
                  <button className="doc-delete" onClick={(e) => deletePdf(e, doc)} title="Delete">✕</button>
                </div>
              ))
            )}
          </div>
        </aside>

        {/* ── Right Chat Panel ── */}
        <section className="chat-panel">

          {/* Tab bar */}
          <div className="tab-bar">
            {sessions.map((s) => (
              <div
                key={s.id}
                className={`tab ${s.id === activeId ? "active" : ""}`}
                onClick={() => setActiveId(s.id)}
                title={s.name}
              >
                <span className="tab-name">{s.name}</span>
                {sessions.length > 1 && (
                  <button className="tab-close" onClick={(e) => closeSession(e, s.id)}>✕</button>
                )}
              </div>
            ))}
            <button className="tab-new" onClick={newSession} title="New chat">+</button>
          </div>

          {/* Chat context header */}
          <div className="chat-header">
            {active.activePdf
              ? <><span style={{ color: "#8b949e" }}>Chatting with </span><span>{active.activePdf.filename}</span></>
              : "Select a document — or ask across all PDFs"}
          </div>

          {/* Messages */}
          {active.messages.length === 0 ? (
            <div className="empty-chat">
              <div className="big-icon">💬</div>
              <p>Ask a question about your PDF</p>
            </div>
          ) : (
            <div className="messages">
              {active.messages.map((msg, i) => (
                <div key={i} className={`message ${msg.role}`}>
                  <div className="message-label">{msg.role === "user" ? "You" : "Claude"}</div>
                  <div className={`message-bubble ${msg.loading ? "loading" : ""}`}>{msg.text}</div>
                  {msg.role === "assistant" && !msg.loading && msg.sources?.length > 0 && (
                    <div className="sources">
                      <div className="sources-label">Sources</div>
                      {msg.sources.map((src, j) => (
                        <div key={j} className="source-card">
                          <div className="source-meta">
                            <span className="source-file">📄 {src.filename || "Unknown"}</span>
                            {src.page_number && <span className="source-page">Page {src.page_number}</span>}
                            <span className="source-score">Score: {src.score}</span>
                          </div>
                          <div className="source-text">{src.text}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}

          {/* Input */}
          <div className="chat-input-area">
            <textarea
              rows={1}
              placeholder={active.activePdf ? `Ask about "${active.activePdf.filename}"…` : "Ask a question across all PDFs…"}
              value={active.input}
              onChange={(e) => patchSession(activeId, { input: e.target.value })}
              onKeyDown={onKeyDown}
              disabled={active.asking}
            />
            <button className="send-btn" onClick={sendMessage} disabled={!active.input.trim() || active.asking}>
              {active.asking ? "…" : "Send"}
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
