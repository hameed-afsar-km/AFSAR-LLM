"use client";

import { useState } from "react";
import styles from "./page.module.css";

export default function Home() {
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim()) return;
    setLoading(true);
    setOutput("");
    try {
      const res = await fetch("http://localhost:8000/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input }),
      });
      const data = await res.json();
      setOutput(data.output);
    } catch (err) {
      setOutput("Error: " + (err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>AFSAR LLM Interface</h1>
      <form onSubmit={handleSubmit} className={styles.form}>
        <textarea
          className={styles.textarea}
          placeholder="Type your input here..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          rows={5}
        />
        <button type="submit" className={styles.button} disabled={loading}>
          {loading ? "Generating..." : "Send"}
        </button>
      </form>
      {output && (
        <div className={styles.output}>
          <strong>Output:</strong>
          <p>{output}</p>
        </div>
      )}
    </div>
  );
}
