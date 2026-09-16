"use client";

import { useRef, useState } from "react";

interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCall[];
  latencyMs?: number;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setError(null);
    const next: Message[] = [...messages, { role: "user", content: text }];
    setMessages(next);
    setInput("");
    setBusy(true);
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ messages: next.map((m) => ({ role: m.role, content: m.content })) }),
      });
      const data = (await response.json()) as {
        response?: string;
        toolCalls?: ToolCall[];
        error?: string | null;
        latencyMs?: number;
      };
      if (!response.ok) {
        setError(data.error ?? `chat failed (${response.status})`);
        return;
      }
      setMessages([
        ...next,
        {
          role: "assistant",
          content: data.response ?? "",
          toolCalls: data.toolCalls ?? [],
          latencyMs: data.latencyMs,
        },
      ]);
      if (data.error) setError(data.error);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      requestAnimationFrame(() => boxRef.current?.scrollTo({ top: boxRef.current.scrollHeight }));
    }
  }

  return (
    <main style={{ maxWidth: 760, margin: "0 auto", padding: "24px 16px 40px" }}>
      <h1 style={{ fontSize: 20, margin: "0 0 4px" }}>Support Agent</h1>
      <p style={{ margin: "0 0 16px", color: "#57534e", fontSize: 14 }}>
        Same agent core as the evals. Try: “When does Alex Chen&apos;s subscription renew?”
      </p>
      <div
        ref={boxRef}
        style={{
          border: "1px solid #e7e0d4",
          borderRadius: 12,
          minHeight: 320,
          maxHeight: 520,
          overflowY: "auto",
          padding: 12,
          background: "#fffcf7",
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        {messages.length === 0 && (
          <div style={{ color: "#a8a29e", fontSize: 14 }}>No messages yet. Ask something below.</div>
        )}
        {messages.map((m, i) => (
          <div key={i}>
            <div
              style={{
                whiteSpace: "pre-wrap",
                padding: "8px 12px",
                borderRadius: 10,
                background: m.role === "user" ? "#e8f1fb" : "#f6f3ec",
                color: m.role === "user" ? "#1e3a5f" : "#1c1917",
                fontSize: 14,
              }}
            >
              {m.content}
            </div>
            {m.toolCalls && m.toolCalls.length > 0 && (
              <div style={{ marginTop: 4, fontSize: 12, color: "#57534e" }}>
                tools: {m.toolCalls.map((t) => t.name).join(", ")}
                {typeof m.latencyMs === "number" ? ` · ${m.latencyMs}ms` : ""}
              </div>
            )}
          </div>
        ))}
        {busy && <div style={{ color: "#a8a29e", fontSize: 14 }}>Thinking…</div>}
      </div>
      {error && (
        <div
          style={{
            marginTop: 8,
            padding: "8px 12px",
            background: "#ffe4e6",
            color: "#9f1239",
            borderRadius: 8,
            fontSize: 13,
          }}
        >
          {error}
        </div>
      )}
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void send();
          }}
          placeholder="Ask the support agent…"
          disabled={busy}
          style={{
            flex: 1,
            padding: "10px 12px",
            borderRadius: 8,
            border: "1px solid #d6d3d1",
            fontSize: 14,
          }}
        />
        <button
          onClick={() => void send()}
          disabled={busy}
          style={{
            padding: "10px 18px",
            borderRadius: 8,
            border: "none",
            background: "#1c1917",
            color: "white",
            fontSize: 14,
            cursor: busy ? "default" : "pointer",
          }}
        >
          Send
        </button>
      </div>
    </main>
  );
}
