"use client";

import { useState, useEffect, useRef } from "react";
import styles from "./page.module.css";

type Message = {
  role: "user" | "assistant";
  content: string;
};

type Profile = {
  name: string;
  communication_style: {
    language: string;
    tone: string;
    approach: string;
  };
  goals: string[];
  preferences: string[];
  projects: string[];
};

type Memory = {
  memory: string;
};

export default function Home() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [synthesizeInput, setSynthesizeInput] = useState("");
  const [synthesizeLoading, setSynthesizeLoading] = useState(false);
  const [synthesizeMessage, setSynthesizeMessage] = useState("");

  const [messages, setMessages] = useState<Message[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [savedInChat, setSavedInChat] = useState<string | null>(null);

  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function fetchData() {
    try {
      const res = await fetch("http://localhost:8000/data");
      const data = await res.json();
      setProfile(data.profile);
      setMemories(data.memories);
    } catch (err) {
      console.error("Failed to load data", err);
    }
  }

  async function handleSynthesize(e: React.FormEvent) {
    e.preventDefault();
    if (!synthesizeInput.trim()) return;
    setSynthesizeLoading(true);
    setSynthesizeMessage("");
    try {
      const res = await fetch("http://localhost:8000/synthesize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input: synthesizeInput }),
      });
      const data = await res.json();
      setProfile(data.profile);
      setMemories(data.memories);
      const changes = data.changes;
      const changedFields = Object.keys(changes).filter((k) =>
        Array.isArray(changes[k])
          ? (changes[k] as unknown[]).length > 0
          : changes[k],
      );
      if (changedFields.length > 0) {
        setSynthesizeMessage(`Updated: ${changedFields.join(", ")}`);
      } else {
        setSynthesizeMessage("No new information detected.");
      }
      setSynthesizeInput("");
    } catch (err) {
      setSynthesizeMessage("Error: " + (err as Error).message);
    } finally {
      setSynthesizeLoading(false);
    }
  }

  async function handleChatSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!chatInput.trim()) return;
    const userMessage = chatInput;
    setChatInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setChatLoading(true);
    try {
      const res = await fetch("http://localhost:8000/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input: userMessage }),
      });
      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.output },
      ]);
      // auto-synthesize: try to extract and save info from user's message
      try {
        const synthRes = await fetch("http://localhost:8000/synthesize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ input: userMessage }),
        });
        const synthData = await synthRes.json();
        const changes = synthData.changes;
        const changedFields = Object.keys(changes).filter((k) =>
          Array.isArray(changes[k])
            ? (changes[k] as unknown[]).length > 0
            : changes[k],
        );
        if (changedFields.length > 0) {
          setProfile(synthData.profile);
          setMemories(synthData.memories);
          setSavedInChat(`Saved: ${changedFields.join(", ")}`);
          setTimeout(() => setSavedInChat(null), 4000);
        }
      } catch {
        // background save failed silently
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Error: " + (err as Error).message },
      ]);
    } finally {
      setChatLoading(false);
    }
  }

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <h1 className={styles.title}>AFSAR</h1>
        <span className={styles.subtitle}>Personal AI Assistant</span>
      </header>
      <main className={styles.main}>
        <section className={styles.panel}>
          <h2 className={styles.panelTitle}>About Me</h2>

          <div className={styles.profileSection}>
            {profile && (
              <div className={styles.profileCards}>
                <div className={styles.card}>
                  <span className={styles.cardLabel}>Name</span>
                  <span>{profile.name}</span>
                </div>
                <div className={styles.card}>
                  <span className={styles.cardLabel}>Communication Style</span>
                  <span>
                    {profile.communication_style?.language} &middot;{" "}
                    {profile.communication_style?.tone} &middot;{" "}
                    {profile.communication_style?.approach}
                  </span>
                </div>
                <div className={styles.card}>
                  <span className={styles.cardLabel}>Goals</span>
                  <ul>
                    {profile.goals?.map((g, i) => (
                      <li key={i}>{g}</li>
                    ))}
                  </ul>
                </div>
                <div className={styles.card}>
                  <span className={styles.cardLabel}>Preferences</span>
                  <ul>
                    {profile.preferences?.map((p, i) => (
                      <li key={i}>{p}</li>
                    ))}
                  </ul>
                </div>
                <div className={styles.card}>
                  <span className={styles.cardLabel}>Projects</span>
                  <ul>
                    {profile.projects?.map((p, i) => (
                      <li key={i}>{p}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            <h3>Memories</h3>
            {memories.length > 0 ? (
              <ul className={styles.memoryList}>
                {memories.map((m, i) => (
                  <li key={i}>{m.memory}</li>
                ))}
              </ul>
            ) : (
              <p className={styles.emptyText}>No memories yet.</p>
            )}
          </div>

          <div className={styles.synthesizeSection}>
            <h3>Add Information</h3>
            <p className={styles.hint}>
              Tell me something about yourself. AI will categorize and save it
              automatically.
            </p>
            <form onSubmit={handleSynthesize} className={styles.synthesizeForm}>
              <textarea
                className={styles.textarea}
                placeholder="e.g. I'm learning React and want to build a dashboard..."
                value={synthesizeInput}
                onChange={(e) => setSynthesizeInput(e.target.value)}
                rows={4}
              />
              <button
                type="submit"
                className={styles.button}
                disabled={synthesizeLoading}
              >
                {synthesizeLoading ? "Analyzing..." : "Synthesize & Save"}
              </button>
            </form>
            {synthesizeMessage && (
              <div className={styles.synthMessage}>{synthesizeMessage}</div>
            )}
          </div>
        </section>

        <section className={styles.panel}>
          <h2 className={styles.panelTitle}>Chat</h2>
          <div className={styles.chatMessages}>
            {messages.length === 0 && !chatLoading && (
              <div className={styles.chatEmpty}>
                <p>Start a conversation with AfsarLLM</p>
              </div>
            )}
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`${styles.message} ${msg.role === "user" ? styles.user : styles.assistant}`}
              >
                <div className={styles.messageBubble}>{msg.content}</div>
              </div>
            ))}
            {chatLoading && (
              <div className={`${styles.message} ${styles.assistant}`}>
                <div className={styles.messageBubble}>Thinking...</div>
              </div>
            )}
            {savedInChat && (
              <div className={styles.savedIndicator}>{savedInChat}</div>
            )}
            <div ref={chatEndRef} />
          </div>
          <form onSubmit={handleChatSubmit} className={styles.chatForm}>
            <input
              className={styles.chatInput}
              placeholder="Type a message..."
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              disabled={chatLoading}
            />
            <button
              type="submit"
              className={styles.button}
              disabled={chatLoading || !chatInput.trim()}
            >
              Send
            </button>
          </form>
        </section>
      </main>
    </div>
  );
}
