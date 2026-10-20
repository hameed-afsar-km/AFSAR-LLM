"use client";

import { useState, useEffect, useRef, useCallback } from "react";
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

const API_BASE = "http://127.0.0.1:8000";

const audioQueue: string[] = [];
let audioPlaying = false;

function playNextAudio() {
  if (audioQueue.length === 0) {
    audioPlaying = false;
    return;
  }
  audioPlaying = true;
  const url = audioQueue.shift()!;
  const audio = new Audio(url);
  audio.onended = () => {
    URL.revokeObjectURL(url);
    playNextAudio();
  };
  audio.play().catch(() => {
    URL.revokeObjectURL(url);
    playNextAudio();
  });
}

const ttsChainQueue: string[] = [];
let ttsChainBusy = false;

let msPlayer: {
  ms: MediaSource;
  sb: SourceBuffer;
  audio: HTMLAudioElement;
} | null = null;
const msChunkQueue: Uint8Array<ArrayBuffer>[] = [];
let msAppending = false;

function base64ToBytes(b64: string): Uint8Array<ArrayBuffer> {
  const binary = atob(b64);
  const buf = new ArrayBuffer(binary.length);
  const bytes = new Uint8Array(buf);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function appendSegment(segments: string[] | string) {
  if (typeof MediaSource === "undefined") {
    const list = Array.isArray(segments) ? segments : [segments];
    pushAudioSegments(list);
    return;
  }
  const bytes =
    typeof segments === "string" ? base64ToBytes(segments) : segments.map(base64ToBytes);
  const list = Array.isArray(bytes) ? bytes : [bytes];
  msChunkQueue.push(...list);
  void processMsQueue();
}

async function processMsQueue() {
  if (msAppending) return;
  msAppending = true;
  try {
    while (msChunkQueue.length > 0) {
      let sb: SourceBuffer;
      try {
        sb = await ensureMsSourceBuffer();
      } catch {
        const queued = msChunkQueue.splice(0);
        for (const bytes of queued) pushByteBlob(bytes);
        return;
      }
      if (sb.updating) {
        await new Promise<void>((resolve) => {
          sb.addEventListener("updateend", () => resolve(), { once: true });
        });
      }
      const chunk = msChunkQueue.shift()!;
      sb.appendBuffer(chunk);
      if (msPlayer?.audio.paused) {
        msPlayer.audio.play().catch(() => {});
      }
    }
  } finally {
    msAppending = false;
  }
}

function pushByteBlob(bytes: Uint8Array<ArrayBuffer>) {
  const url = URL.createObjectURL(new Blob([bytes], { type: "audio/mpeg" }));
  audioQueue.push(url);
  if (!audioPlaying) playNextAudio();
}

function ensureMsSourceBuffer(): Promise<SourceBuffer> {
  if (msPlayer && msPlayer.ms.readyState === "open") {
    return Promise.resolve(msPlayer.sb);
  }
  return new Promise((resolve, reject) => {
    const ms = new MediaSource();
    const url = URL.createObjectURL(ms);
    const audio = new Audio(url);
    audio.autoplay = true;
    ms.addEventListener(
      "sourceopen",
      () => {
        try {
          const sb = ms.addSourceBuffer("audio/mpeg");
          msPlayer = { ms, sb, audio };
          resolve(sb);
        } catch (err) {
          reject(err as Error);
        }
      },
      { once: true },
    );
    ms.addEventListener("error", () => reject(new Error("MediaSource error")), {
      once: true,
    });
  });
}

function queueSpeak(text: string) {
  const trimmed = text.trim();
  if (trimmed.length < 2) return;
  ttsChainQueue.push(trimmed);
  if (!ttsChainBusy) nextSpeak();
}

function nextSpeak() {
  if (ttsChainQueue.length === 0) {
    ttsChainBusy = false;
    return;
  }
  ttsChainBusy = true;
  const text = ttsChainQueue.shift()!;
  speakStreamed(text).finally(() => nextSpeak());
}

function pushAudioSegments(segments: string[]) {
  for (const b64 of segments) pushByteBlob(base64ToBytes(b64));
}

async function speakStreamed(text: string) {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/tts/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
  } catch {
    return;
  }
  if (!res.ok || !res.body) return;

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let segments: string[] = [];

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop()!;

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const payload = line.slice(6);
      if (!payload) continue;
      try {
        const parsed = JSON.parse(payload);
        if (parsed.done) {
          if (segments.length) {
            appendSegment(segments);
            segments = [];
          }
          continue;
        }
        if (!parsed.audio) continue;
        appendSegment(parsed.audio);
      } catch {
        // skip malformed event
      }
    }
  }
  if (segments.length) appendSegment(segments);
}

function isSentenceEnd(text: string) {
  return /[.!?\n]$/.test(text.trim());
}

export default function Home() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [synthesizeInput, setSynthesizeInput] = useState("");
  const [synthesizeLoading, setSynthesizeLoading] = useState(false);
  const [synthesizeMessage, setSynthesizeMessage] = useState("");

  const [messages, setMessages] = useState<Message[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [listening, setListening] = useState(false);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);
  const streamContentRef = useRef("");
  const pendingSpeechRef = useRef("");
  const lastStreamAtRef = useRef(0);
  const pauseTimerRef = useRef<number | null>(null);

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function fetchData() {
    try {
      const res = await fetch(`${API_BASE}/data`);
      const data = await res.json();
      setProfile(data.profile ?? null);
      setMemories(Array.isArray(data.memories) ? data.memories : []);
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
      const res = await fetch(`${API_BASE}/synthesize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input: synthesizeInput }),
      });
      const data = await res.json();
      setProfile(data.profile ?? null);
      setMemories(Array.isArray(data.memories) ? data.memories : []);
      const changes = data.changes;
      const changedFields = Object.keys(changes ?? {}).filter((k) =>
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
    submitChat(chatInput);
  }

  async function submitChat(userMessage: string) {
    setChatInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setChatLoading(true);
    streamContentRef.current = "";

    const stopPauseFlush = () => {
      if (pauseTimerRef.current !== null) {
        window.clearInterval(pauseTimerRef.current);
        pauseTimerRef.current = null;
      }
    };

    const flushSpeech = () => {
      const pending = pendingSpeechRef.current;
      pendingSpeechRef.current = "";
      if (!pending.trim()) return;
      queueSpeak(pending);
    };

    const schedulePauseFlush = () => {
      if (pauseTimerRef.current !== null) return;
      pauseTimerRef.current = window.setInterval(() => {
        if (
          pendingSpeechRef.current.trim().length >= 10 &&
          Date.now() - lastStreamAtRef.current >= 350
        ) {
          stopPauseFlush();
          flushSpeech();
        }
      }, 150);
    };

    const flushAtBoundary = () => {
      const pending = pendingSpeechRef.current;
      let cut = -1;
      for (const c of [",", ";", ".", "!", "?", ":", " "]) {
        const i = pending.lastIndexOf(c);
        if (i > cut) cut = i;
      }
      if (cut > 0 && cut < pending.length - 1) {
        pendingSpeechRef.current = pending.slice(cut + 1).trimStart();
        stopPauseFlush();
        queueSpeak(pending.slice(0, cut + 1));
        schedulePauseFlush();
      } else {
        stopPauseFlush();
        flushSpeech();
      }
    };

    try {
      const res = await fetch(`${API_BASE}/generate/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input: userMessage, history: messages }),
      });

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let assistantMessage = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6);
          if (!payload) continue;

          try {
            const parsed = JSON.parse(payload);
            if (parsed.done) break;
            if (!parsed.token) continue;

            const token = parsed.token;
            assistantMessage += token;
            pendingSpeechRef.current += token;
            lastStreamAtRef.current = Date.now();

            setMessages((prev) => {
              const updated = [...prev];
              if (
                updated.length > 0 &&
                updated[updated.length - 1].role === "assistant"
              ) {
                updated[updated.length - 1] = {
                  role: "assistant",
                  content: assistantMessage,
                };
              } else {
                updated.push({
                  role: "assistant",
                  content: assistantMessage,
                });
              }
              return updated;
            });

            if (ttsEnabled) {
              const pending = pendingSpeechRef.current;
              if (isSentenceEnd(pending)) {
                stopPauseFlush();
                flushSpeech();
              } else if (pending.length >= 80) {
                flushAtBoundary();
              } else {
                schedulePauseFlush();
              }
            }
          } catch {
            // skip malformed JSON
          }
        }
      }

      stopPauseFlush();
      flushSpeech();

      setChatLoading(false);
    } catch (err) {
      stopPauseFlush();
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Error: " + (err as Error).message,
        },
      ]);
      setChatLoading(false);
    }
  }

  const toggleMic = useCallback(() => {
    const SpeechRecognitionAPI =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognitionAPI) return;

    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }

    const recognition = new SpeechRecognitionAPI();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.continuous = false;

    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript;
      setChatInput(transcript);
      submitChat(transcript);
    };

    recognition.onerror = () => setListening(false);
    recognition.onend = () => setListening(false);

    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
  }, [listening, messages, ttsEnabled]);

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
            {chatLoading &&
              (messages.length === 0 ||
                messages[messages.length - 1].role !== "assistant") && (
                <div className={`${styles.message} ${styles.assistant}`}>
                  <div className={styles.messageBubble}>Thinking...</div>
                </div>
              )}
            <div ref={chatEndRef} />
          </div>
          <form onSubmit={handleChatSubmit} className={styles.chatForm}>
            <button
              type="button"
              className={`${styles.micButton} ${listening ? styles.micActive : ""}`}
              onClick={toggleMic}
              title={listening ? "Stop listening" : "Voice input"}
            >
              {listening ? "◉" : "🎤"}
            </button>
            <input
              className={styles.chatInput}
              placeholder={
                listening
                  ? "Listening..."
                  : ttsEnabled
                    ? "Type or speak..."
                    : "Type a message..."
              }
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              disabled={chatLoading || listening}
            />
            <button
              type="button"
              className={`${styles.ttsToggle} ${ttsEnabled ? styles.ttsActive : ""}`}
              onClick={() => setTtsEnabled((p) => !p)}
              title={ttsEnabled ? "Mute TTS" : "Enable TTS"}
            >
              {ttsEnabled ? "🔊" : "🔇"}
            </button>
            <button
              type="submit"
              className={styles.button}
              disabled={chatLoading || !chatInput.trim() || listening}
            >
              Send
            </button>
          </form>
        </section>
      </main>
    </div>
  );
}
