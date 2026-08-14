import React, { FormEvent, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Citation = { source: string; page: number; excerpt: string };
type Message = { role: "user" | "assistant"; text: string; citations?: Citation[] };
const API = import.meta.env.VITE_API_URL ?? "/api";

function requestError(error: unknown, action: string): string {
  if (error instanceof TypeError) {
    return `Cannot reach the backend. Start the API server, then ${action} again.`;
  }
  return error instanceof Error ? error.message : `${action} failed`;
}

function App() {
  const [sessionId, setSessionId] = useState<string>();
  const [fileName, setFileName] = useState("");
  const [side, setSide] = useState("neutral");
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function upload(file?: File) {
    if (!file) return;
    setBusy(true); setError("");
    const body = new FormData(); body.append("file", file);
    try {
      const response = await fetch(`${API}/cases`, { method: "POST", body });
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json(); setSessionId(data.session_id); setMessages([]); setFileName(`${data.filename} · ${data.pages} pages`);
    } catch (e) { setError(requestError(e, "upload")); }
    finally { setBusy(false); }
  }

  async function ask(event: FormEvent) {
    event.preventDefault(); if (!question.trim() || busy) return;
    const q = question; setQuestion(""); setMessages(m => [...m, { role: "user", text: q }]); setBusy(true); setError("");
    try {
      const response = await fetch(`${API}/chat`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, side, session_id: sessionId,
          conversation: messages.slice(-6).map(({ role, text }) => ({ role, text })) }) });
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json(); setMessages(m => [...m, { role: "assistant", text: data.answer, citations: data.citations }]);
    } catch (e) { setError(requestError(e, "try")); }
    finally { setBusy(false); }
  }

  return <main>
    <header><div className="mark">न्याय</div><div><p className="eyebrow">SUPREME COURT RESEARCH</p><h1>Legal Counsel</h1></div><span className="status">Evidence-first</span></header>
    <section className="layout">
      <aside><h2>Case workspace</h2><p>Upload the matter you are preparing. The case remains isolated to this session.</p>
        <label className="drop"><input type="file" accept="application/pdf" onChange={e => upload(e.target.files?.[0])}/><strong>{fileName || "Choose judgment PDF"}</strong><span>PDF · maximum 50 MB</span></label>
        <label>Representing<select value={side} onChange={e => setSide(e.target.value)}><option value="neutral">Neutral analysis</option><option value="petitioner">Petitioner</option><option value="respondent">Respondent</option></select></label>
        <div className="notice"><strong>Professional safeguard</strong><p>Verify the complete judgment, later treatment, statutes, and every pinpoint citation before court use.</p></div>
      </aside>
      <section className="chat"><div className="intro"><span>ARGUMENT DESK</span><h2>Build the case from the record.</h2><p>Ask for issues, a theory of the case, opposing arguments, rebuttal, or a hearing outline.</p></div>
        <div className="messages">{messages.map((m, i) => <article key={i} className={m.role}><small>{m.role === "user" ? "YOU" : "LEGAL COUNSEL"}</small><p>{m.text}</p>{m.citations?.length ? <details><summary>{m.citations.length} retrieved sources</summary>{m.citations.map((c,j)=><blockquote key={j}><b>p. {c.page}</b> · {c.source}<br/>{c.excerpt}</blockquote>)}</details>:null}</article>)}</div>
        {error && <p className="error">{error}</p>}
        <form onSubmit={ask}><textarea value={question} onChange={e=>setQuestion(e.target.value)} placeholder="Ask a question about this judgment…"/><button disabled={busy}>{busy ? "Working…" : "Ask →"}</button></form>
      </section>
    </section>
  </main>;
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App/></React.StrictMode>);
