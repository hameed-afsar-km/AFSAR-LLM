"use client";

import {
  useState,
  useEffect,
  useRef,
  useCallback,
  useLayoutEffect,
} from "react";
import styles from "./page.module.css";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Role = "user" | "assistant";

type Message = {
  role: Role;
  content: string;
};

type Conversation = {
  id: string;
  title: string;
  updated_at: string;
};

type Profile = {
  name: string;
  communication_style?: { language?: string; tone?: string; approach?: string };
  goals?: string[];
  preferences?: string[];
  projects?: string[];
};

type Memory = { memory: string };

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const API_BASE =
  (typeof window !== "undefined" && (window as any).__AFSAR_API_BASE__) ||
  process.env.NEXT_PUBLIC_API_BASE ||
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  "http://127.0.0.1:8000";

const SUGGESTIONS = [
  "What's on my schedule today?",
  "Give me a quick news briefing",
  "What are my current projects?",
  "Help me think through a problem",
];

// ---------------------------------------------------------------------------
// Audio / TTS helpers (unchanged from original)
// ---------------------------------------------------------------------------

const audioQueue: string[] = [];
let audioPlaying = false;

function playNextAudio() {
  if (audioQueue.length === 0) { audioPlaying = false; return; }
  audioPlaying = true;
  const url = audioQueue.shift()!;
  const audio = new Audio(url);
  audio.onended = () => { URL.revokeObjectURL(url); playNextAudio(); };
  audio.play().catch(() => { URL.revokeObjectURL(url); playNextAudio(); });
}

const ttsChainQueue: string[] = [];
let ttsChainBusy = false;

let msPlayer: { ms: MediaSource; sb: SourceBuffer; audio: HTMLAudioElement } | null = null;
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
  const bytes = typeof segments === "string" ? base64ToBytes(segments) : segments.map(base64ToBytes);
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
      try { sb = await ensureMsSourceBuffer(); }
      catch {
        const queued = msChunkQueue.splice(0);
        for (const bytes of queued) pushByteBlob(bytes);
        return;
      }
      while (sb.updating) {
        await new Promise<void>((resolve) => sb.addEventListener("updateend", () => resolve(), { once: true }));
      }
      const chunk = msChunkQueue.shift()!;
      try {
        sb.appendBuffer(chunk);
      } catch {
        pushByteBlob(chunk);
        continue;
      }
      if (msPlayer?.audio.paused) msPlayer.audio.play().catch(() => {});
    }
  } finally { msAppending = false; }
}

function pushByteBlob(bytes: Uint8Array<ArrayBuffer>) {
  const url = URL.createObjectURL(new Blob([bytes], { type: "audio/mpeg" }));
  audioQueue.push(url);
  if (!audioPlaying) playNextAudio();
}

function ensureMsSourceBuffer(): Promise<SourceBuffer> {
  if (msPlayer && msPlayer.ms.readyState === "open") return Promise.resolve(msPlayer.sb);
  return new Promise((resolve, reject) => {
    const ms = new MediaSource();
    const url = URL.createObjectURL(ms);
    const audio = new Audio(url);
    audio.autoplay = true;
    ms.addEventListener("sourceopen", () => {
      try { const sb = ms.addSourceBuffer("audio/mpeg"); msPlayer = { ms, sb, audio }; resolve(sb); }
      catch (err) { reject(err as Error); }
    }, { once: true });
    ms.addEventListener("error", () => reject(new Error("MediaSource error")), { once: true });
  });
}

function queueSpeak(text: string) {
  const trimmed = text.trim();
  if (trimmed.length < 2) return;
  ttsChainQueue.push(trimmed);
  if (!ttsChainBusy) nextSpeak();
}

function nextSpeak() {
  if (ttsChainQueue.length === 0) { ttsChainBusy = false; return; }
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
  } catch { return; }
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
        if (parsed.done) { if (segments.length) { appendSegment(segments); segments = []; } continue; }
        if (!parsed.audio) continue;
        appendSegment(parsed.audio);
      } catch { /* skip malformed */ }
    }
  }
  if (segments.length) appendSegment(segments);
}

function isSentenceEnd(text: string) {
  return /[.!?\n]$/.test(text.trim());
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Home() {
  // -- Data state --
  const [profile, setProfile] = useState<Profile | null>(null);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);

  // -- Chat state --
  const [messages, setMessages] = useState<Message[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);

  // -- TTS / Mic --
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [listening, setListening] = useState(false);

  // -- Synthesize --
  const [synthesizeInput, setSynthesizeInput] = useState("");
  const [synthesizeLoading, setSynthesizeLoading] = useState(false);
  const [synthesizeMessage, setSynthesizeMessage] = useState("");

  // -- UI state --
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);

  // -- Refs --
  const chatEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const recognitionRef = useRef<any>(null);
  const streamContentRef = useRef("");
  const pendingSpeechRef = useRef("");
  const lastStreamAtRef = useRef(0);
  const pauseTimerRef = useRef<number | null>(null);

  // ---------------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------------

  useEffect(() => {
    fetchData();
    fetchConversations();
    checkBackendStatus();

    const interval = setInterval(checkBackendStatus, 15000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-resize textarea
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
  }, [chatInput]);

  // Listen for Tauri "open-settings" event
  useEffect(() => {
    let unlisten: (() => void) | undefined;
    (async () => {
      try {
        const { listen } = await import("@tauri-apps/api/event");
        unlisten = await listen("open-settings", () => setSettingsOpen(true));
      } catch { /* not in Tauri context */ }
    })();
    return () => { unlisten?.(); };
  }, []);

  // ---------------------------------------------------------------------------
  // API helpers
  // ---------------------------------------------------------------------------

  async function checkBackendStatus() {
    try {
      const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(3000) });
      setBackendOnline(res.ok);
    } catch {
      setBackendOnline(false);
    }
  }

  async function fetchData() {
    try {
      const res = await fetch(`${API_BASE}/data`);
      const data = await res.json();
      setProfile(data.profile ?? null);
      setMemories(Array.isArray(data.memories) ? data.memories : []);
    } catch { /* silent */ }
  }

  async function fetchConversations() {
    try {
      const res = await fetch(`${API_BASE}/conversations`);
      const data = await res.json();
      setConversations(Array.isArray(data.conversations) ? data.conversations : []);
    } catch { /* silent */ }
  }

  async function createConversation(): Promise<string | null> {
    try {
      const res = await fetch(`${API_BASE}/conversations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "New Chat" }),
      });
      const data = await res.json();
      const conv = data.conversation;
      setConversations((prev) => [conv, ...prev]);
      return conv.id;
    } catch { return null; }
  }

  async function loadConversation(convId: string) {
    setActiveConvId(convId);
    try {
      const res = await fetch(`${API_BASE}/conversations/${convId}`);
      const data = await res.json();
      const msgs: Message[] = (data.messages || []).map((m: any) => ({
        role: m.role as Role,
        content: m.content,
      }));
      setMessages(msgs);
    } catch { setMessages([]); }
  }

  async function deleteConversation(convId: string, e: React.MouseEvent) {
    e.stopPropagation();
    try {
      await fetch(`${API_BASE}/conversations/${convId}`, { method: "DELETE" });
      setConversations((prev) => prev.filter((c) => c.id !== convId));
      if (activeConvId === convId) {
        setActiveConvId(null);
        setMessages([]);
      }
    } catch { /* silent */ }
  }

  async function handleNewChat() {
    const id = await createConversation();
    if (id) {
      setActiveConvId(id);
      setMessages([]);
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
        Array.isArray(changes[k]) ? (changes[k] as unknown[]).length > 0 : changes[k]
      );
      setSynthesizeMessage(
        changedFields.length > 0
          ? `✓ Updated: ${changedFields.join(", ")}`
          : "No new information detected."
      );
      setSynthesizeInput("");
    } catch (err) {
      setSynthesizeMessage("Error: " + (err as Error).message);
    } finally {
      setSynthesizeLoading(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Chat
  // ---------------------------------------------------------------------------

  async function handleChatSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!chatInput.trim() || chatLoading) return;
    await submitChat(chatInput);
  }

  async function submitChat(userMessage: string) {
    setChatInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setChatLoading(true);
    streamContentRef.current = "";

    // Ensure conversation
    let convId = activeConvId;
    if (!convId) {
      convId = await createConversation();
      if (convId) setActiveConvId(convId);
    }

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
        if (pendingSpeechRef.current.trim().length >= 10 && Date.now() - lastStreamAtRef.current >= 350) {
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
        body: JSON.stringify({
          input: userMessage,
          history: messages,
          conversation_id: convId,
        }),
      });

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let assistantMessage = "";
      let buffer = "";

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
            if (parsed.done) break;
            if (!parsed.token) continue;

            const token = parsed.token;
            assistantMessage += token;
            pendingSpeechRef.current += token;
            lastStreamAtRef.current = Date.now();

            setMessages((prev) => {
              const updated = [...prev];
              if (updated.length > 0 && updated[updated.length - 1].role === "assistant") {
                updated[updated.length - 1] = { role: "assistant", content: assistantMessage };
              } else {
                updated.push({ role: "assistant", content: assistantMessage });
              }
              return updated;
            });

            if (ttsEnabled) {
              const pending = pendingSpeechRef.current;
              if (isSentenceEnd(pending)) { stopPauseFlush(); flushSpeech(); }
              else if (pending.length >= 80) { flushAtBoundary(); }
              else { schedulePauseFlush(); }
            }
          } catch { /* skip malformed */ }
        }
      }

      stopPauseFlush();
      flushSpeech();

      // Update conversation list order
      if (convId) {
        setConversations((prev) => {
          const idx = prev.findIndex((c) => c.id === convId);
          if (idx < 0) return prev;
          const updated = [...prev];
          updated.splice(idx, 1);
          const conv = { ...prev[idx], updated_at: new Date().toISOString() };
          // Auto-title on first user message
          if (conv.title === "New Chat") conv.title = userMessage.slice(0, 38) + (userMessage.length > 38 ? "…" : "");
          return [conv, ...updated];
        });
      }
    } catch (err) {
      stopPauseFlush();
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Error: " + (err as Error).message },
      ]);
    } finally {
      setChatLoading(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Mic
  // ---------------------------------------------------------------------------

  const toggleMic = useCallback(() => {
    const SpeechRecognitionAPI = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
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

  // Keyboard shortcut — Enter sends, Shift+Enter = newline
  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!chatLoading && chatInput.trim()) submitChat(chatInput);
    }
  }

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  const statusClass = backendOnline === null
    ? styles.statusDot + " " + styles.pending
    : backendOnline
      ? styles.statusDot + " " + styles.online
      : styles.statusDot + " " + styles.offline;

  const activeConvTitle = conversations.find((c) => c.id === activeConvId)?.title ?? "New conversation";

  // ---------------------------------------------------------------------------
  // JSX
  // ---------------------------------------------------------------------------

  return (
    <div className={styles.app}>

      {/* ===== Sidebar ===== */}
      <aside className={styles.sidebar}>
        <div className={styles.sidebarHeader}>
          <div className={styles.brand}>
            <div className={styles.brandLogo}>A</div>
            <div>
              <div className={styles.brandName}>AFSAR</div>
              <div className={styles.brandTagline}>Personal AI</div>
            </div>
          </div>

          <button id="new-chat-btn" className={styles.newChatBtn} onClick={handleNewChat}>
            <span className={styles.newChatIcon}>＋</span>
            New conversation
          </button>
        </div>

        {conversations.length > 0 && (
          <div className={styles.sidebarSection}>Recents</div>
        )}

        <div className={styles.convList} id="conv-list">
          {conversations.map((conv) => (
            <div
              key={conv.id}
              id={`conv-${conv.id}`}
              className={`${styles.convItem} ${activeConvId === conv.id ? styles.convItemActive : ""}`}
              onClick={() => loadConversation(conv.id)}
            >
              <span className={styles.convItemIcon}>💬</span>
              <span className={styles.convItemTitle}>{conv.title}</span>
              <button
                className={styles.convItemDelete}
                onClick={(e) => deleteConversation(conv.id, e)}
                title="Delete"
              >
                ×
              </button>
            </div>
          ))}
        </div>

        {/* Profile & Memory quick-view */}
        <div className={styles.profilePanel}>
          {profile && (
            <>
              <div className={styles.profilePanelTitle}>Profile</div>
              <div className={styles.infoCard}>
                <span className={styles.infoCardLabel}>Name</span>
                <span className={styles.infoCardValue}>{profile.name}</span>
              </div>
              {profile.goals && profile.goals.length > 0 && (
                <div className={styles.infoCard}>
                  <span className={styles.infoCardLabel}>Goals</span>
                  <ul className={styles.infoCardList}>
                    {profile.goals.slice(0, 3).map((g, i) => <li key={i}>{g}</li>)}
                  </ul>
                </div>
              )}
            </>
          )}

          {memories.length > 0 && (
            <>
              <div className={styles.profilePanelTitle}>Memories</div>
              <ul className={styles.memoryList}>
                {memories.slice(0, 5).map((m, i) => (
                  <li key={i} className={styles.memoryItem}>{m.memory}</li>
                ))}
              </ul>
            </>
          )}

          {/* Synthesize */}
          <div className={styles.synthesizeBlock}>
            <div className={styles.synthesizeLabel}>Add information</div>
            <div className={styles.synthesizeHint}>Tell me something new about yourself.</div>
            <form onSubmit={handleSynthesize}>
              <textarea
                id="synthesize-input"
                className={styles.synthesizeTextarea}
                placeholder="e.g. I'm learning Rust..."
                value={synthesizeInput}
                onChange={(e) => setSynthesizeInput(e.target.value)}
                rows={3}
              />
              <button
                id="synthesize-btn"
                type="submit"
                className={styles.synthesizeBtn}
                disabled={synthesizeLoading || !synthesizeInput.trim()}
              >
                {synthesizeLoading ? "Analyzing…" : "Synthesize & Save"}
              </button>
            </form>
            {synthesizeMessage && (
              <div className={styles.synthesizeMsg}>{synthesizeMessage}</div>
            )}
          </div>
        </div>

        <div className={styles.sidebarFooter}>
          <button
            id="settings-btn"
            className={styles.sidebarAction}
            onClick={() => setSettingsOpen(true)}
          >
            <span className={styles.sidebarActionIcon}>⚙</span>
            Settings
          </button>
        </div>
      </aside>

      {/* ===== Main ===== */}
      <div className={styles.main}>

        {/* Top bar */}
        <div className={styles.topBar}>
          <div className={styles.topBarTitle}>{activeConvId ? activeConvTitle : "AFSAR Assistant"}</div>

          <div className={statusClass} title={backendOnline ? "Backend online" : "Backend offline"} />
          <span className={styles.statusLabel}>
            {backendOnline === null ? "Connecting…" : backendOnline ? "Online" : "Offline"}
          </span>

          <button
            id="tts-toggle-btn"
            className={styles.iconBtn}
            onClick={() => setTtsEnabled((p) => !p)}
            title={ttsEnabled ? "Mute voice" : "Enable voice"}
          >
            {ttsEnabled ? "🔊" : "🔇"}
          </button>

          <button
            id="settings-top-btn"
            className={styles.iconBtn}
            onClick={() => setSettingsOpen(true)}
            title="Settings"
          >
            ⚙
          </button>
        </div>

        {/* Chat area */}
        <div className={styles.chatArea}>
          <div className={styles.messages} id="messages-list">

            {messages.length === 0 && !chatLoading && (
              <div className={styles.emptyState}>
                <div className={styles.emptyLogo}>A</div>
                <div className={styles.emptyTitle}>Hey, boss.</div>
                <div className={styles.emptySubtitle}>
                  Ready when you are. Type a message, speak, or pick a suggestion.
                </div>
                <div className={styles.emptySuggestions}>
                  {SUGGESTIONS.map((s, i) => (
                    <button
                      key={i}
                      id={`suggestion-${i}`}
                      className={styles.suggestionChip}
                      onClick={() => submitChat(s)}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg, i) => (
              <div
                key={i}
                id={`msg-${i}`}
                className={`${styles.messageRow} ${msg.role === "user" ? styles.messageRowUser : ""}`}
              >
                <div className={`${styles.avatar} ${msg.role === "user" ? styles.avatarUser : styles.avatarAssistant}`}>
                  {msg.role === "user" ? "U" : "A"}
                </div>
                <div className={`${styles.bubble} ${msg.role === "user" ? styles.bubbleUser : styles.bubbleAssistant} selectableText`}>
                  {msg.content}
                </div>
              </div>
            ))}

            {chatLoading && (messages.length === 0 || messages[messages.length - 1].role !== "assistant") && (
              <div className={`${styles.messageRow}`}>
                <div className={`${styles.avatar} ${styles.avatarAssistant}`}>A</div>
                <div className={styles.thinkingDots}>
                  <span /><span /><span />
                </div>
              </div>
            )}

            <div ref={chatEndRef} />
          </div>

          {/* Input */}
          <div className={styles.inputArea}>
            <form onSubmit={handleChatSubmit}>
              <div className={styles.inputRow}>
                <textarea
                  ref={textareaRef}
                  id="chat-input"
                  className={styles.chatInput}
                  placeholder={listening ? "Listening…" : ttsEnabled ? "Type or speak…" : "Type a message…"}
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={chatLoading || listening}
                  rows={1}
                />
                <div className={styles.inputActions}>
                  <button
                    id="mic-btn"
                    type="button"
                    className={`${styles.roundBtn} ${listening ? styles.roundBtnActive : ""}`}
                    onClick={toggleMic}
                    title={listening ? "Stop" : "Voice input"}
                  >
                    🎤
                  </button>
                  <button
                    id="send-btn"
                    type="submit"
                    className={styles.sendBtn}
                    disabled={chatLoading || !chatInput.trim() || listening}
                    title="Send"
                  >
                    ↑
                  </button>
                </div>
              </div>
              <div className={styles.inputHint}>
                Enter to send · Shift+Enter for new line · Ctrl+Shift+Space to focus
              </div>
            </form>
          </div>
        </div>
      </div>

      {/* ===== Settings Drawer ===== */}
      {settingsOpen && (
        <div className={styles.drawerOverlay} onClick={() => setSettingsOpen(false)}>
          <div className={styles.drawer} onClick={(e) => e.stopPropagation()} id="settings-drawer">
            <div className={styles.drawerHeader}>
              <div className={styles.drawerTitle}>Settings</div>
              <button id="drawer-close-btn" className={styles.drawerClose} onClick={() => setSettingsOpen(false)}>×</button>
            </div>

            <div className={styles.drawerBody}>

              {/* Backend status */}
              <div className={styles.settingGroup}>
                <div className={styles.settingGroupLabel}>Backend</div>
                <div className={styles.settingRow}>
                  <span className={styles.settingLabel}>API endpoint</span>
                  <span className={styles.settingValue}>{API_BASE}</span>
                </div>
                <div className={styles.settingRow}>
                  <span className={styles.settingLabel}>Status</span>
                  <span className={`${styles.statusBadge} ${backendOnline ? styles.statusBadgeOnline : styles.statusBadgeOffline}`}>
                    {backendOnline ? "● Online" : "● Offline"}
                  </span>
                </div>
              </div>

              {/* Voice */}
              <div className={styles.settingGroup}>
                <div className={styles.settingGroupLabel}>Voice</div>
                <div className={styles.settingRow}>
                  <span className={styles.settingLabel}>Text-to-speech</span>
                  <label className={styles.toggle}>
                    <input
                      id="tts-toggle-setting"
                      type="checkbox"
                      checked={ttsEnabled}
                      onChange={(e) => setTtsEnabled(e.target.checked)}
                    />
                    <span className={styles.toggleTrack} />
                  </label>
                </div>
              </div>

              {/* Profile summary */}
              {profile && (
                <div className={styles.settingGroup}>
                  <div className={styles.settingGroupLabel}>Your Profile</div>
                  <div className={styles.settingRow}>
                    <span className={styles.settingLabel}>Name</span>
                    <span className={styles.settingValue}>{profile.name}</span>
                  </div>
                  {profile.communication_style && (
                    <div className={styles.settingRow}>
                      <span className={styles.settingLabel}>Style</span>
                      <span className={styles.settingValue}>
                        {[profile.communication_style.language, profile.communication_style.tone].filter(Boolean).join(" · ")}
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* Memories count */}
              <div className={styles.settingGroup}>
                <div className={styles.settingGroupLabel}>Memory</div>
                <div className={styles.settingRow}>
                  <span className={styles.settingLabel}>Stored memories</span>
                  <span className={styles.settingValue}>{memories.length}</span>
                </div>
                <div className={styles.settingRow}>
                  <span className={styles.settingLabel}>Conversations</span>
                  <span className={styles.settingValue}>{conversations.length}</span>
                </div>
              </div>

              {/* About */}
              <div className={styles.settingGroup}>
                <div className={styles.settingGroupLabel}>About</div>
                <div className={styles.settingRow}>
                  <span className={styles.settingLabel}>Version</span>
                  <span className={styles.settingValue}>0.1.0</span>
                </div>
                <div className={styles.settingRow}>
                  <span className={styles.settingLabel}>Model</span>
                  <span className={styles.settingValue}>llama3.2:3b via Ollama</span>
                </div>
              </div>

            </div>
          </div>
        </div>
      )}
    </div>
  );
}
