"use client";

import { useState, useRef, useEffect } from "react";
import { Bot, Send, User, RefreshCw, Trash2, Terminal, Code } from "lucide-react";

// ─── Types ──────────────────────────────────────────────────────

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: { title: string }[];
  timestamp: number;
}

// ─── API Configuration ──────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:7337";

// ─── Chat Message Component ─────────────────────────────────────

function ChatMessage({ message }: { message: Message }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      {/* Avatar */}
      <div
        className={`w-8 h-8 rounded-lg shrink-0 flex items-center justify-center ${
          isUser
            ? "bg-forge-primary/20"
            : "bg-zinc-800"
        }`}
      >
        {isUser ? (
          <User size={16} className="text-forge-primary" />
        ) : (
          <Bot size={16} className="text-text-secondary" />
        )}
      </div>

      {/* Message bubble */}
      <div className={`max-w-[75%] ${isUser ? "text-right" : ""}`}>
        <div
          className={`rounded-xl px-4 py-3 text-sm leading-relaxed ${
            isUser
              ? "bg-forge-primary/15 text-text-primary rounded-tr-md"
              : "bg-forge-elevated text-text-primary rounded-tl-md"
          }`}
        >
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>

        {/* Sources */}
        {message.sources && message.sources.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1.5 justify-end">
            {message.sources.map((s, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono bg-zinc-800/50 text-text-muted"
              >
                <Code size={10} />
                {s.title.split("/").pop()?.slice(0, 24)}
              </span>
            ))}
          </div>
        )}

        <span className="text-[10px] text-text-muted mt-1 block">
          {new Date(message.timestamp).toLocaleTimeString()}
        </span>
      </div>
    </div>
  );
}

// ─── Typing Indicator ─────────────────────────────────────────

function TypingIndicator() {
  return (
    <div className="flex gap-3">
      <div className="w-8 h-8 rounded-lg shrink-0 bg-zinc-800 flex items-center justify-center">
        <Bot size={16} className="text-text-secondary" />
      </div>
      <div className="bg-forge-elevated rounded-xl rounded-tl-md px-4 py-3">
        <div className="flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-text-muted animate-bounce [animation-delay:-0.3s]" />
          <span className="w-1.5 h-1.5 rounded-full bg-text-muted animate-bounce [animation-delay:-0.15s]" />
          <span className="w-1.5 h-1.5 rounded-full bg-text-muted animate-bounce" />
        </div>
      </div>
    </div>
  );
}

// ─── Preset Prompts ─────────────────────────────────────────────

const PRESET_PROMPTS = [
  {
    icon: Terminal,
    label: "Debug this code",
    prompt: "Help me debug a Python function that's throwing an unexpected error",
  },
  {
    icon: Code,
    label: "Write a test",
    prompt: "Write a unit test for this Python function using pytest",
  },
  {
    icon: Bot,
    label: "Explain concept",
    prompt: "Explain how Python async/await works with a practical example",
  },
];

// ─── Model Selector ─────────────────────────────────────────────

const MODELS = [
  { id: "", label: "Auto (Recommended)", description: "Fast or balanced based on complexity" },
  { id: "qwen2.5-coder:7b", label: "Qwen 2.5 Coder 7B", description: "Fast, local" },
  { id: "qwen2.5-coder:14b", label: "Qwen 2.5 Coder 14B", description: "Balanced, local" },
  { id: "gpt-4o", label: "GPT-4o", description: "Cloud, powerful" },
  { id: "claude-opus-4", label: "Claude Opus 4", description: "Cloud, max quality" },
];

// ─── Main Page ──────────────────────────────────────────────────

export default function AgentPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Hi! I'm the ForgeAI coding agent. I can help you write, debug, and understand code using your project's context.\n\nTry asking me a question or use one of the quick prompts below.",
      timestamp: Date.now(),
    },
  ]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [modelOpen, setModelOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  // Focus input on load
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSend = async () => {
    const question = input.trim();
    if (!question || streaming) return;

    setInput("");
    setStreaming(true);
    setStreamingContent("");

    // Add user message
    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: "user",
      content: question,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);

    // Add a placeholder for assistant message
    const assistantId = `assistant-${Date.now()}`;

    try {
      const response = await fetch(`${API_BASE}/api/agent/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          model: selectedModel,
          query_expansion: true,
          mmr: true,
          history: messages
            .filter((m) => m.id !== "welcome")
            .slice(-10)
            .map((m) => ({ role: m.role, content: m.content })),
        }),
      });

      if (!response.ok) {
        throw new Error(`API ${response.status}: ${await response.text()}`);
      }

      // Read SSE stream
      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response stream");

      const decoder = new TextDecoder();
      let fullContent = "";
      let sources: { title: string }[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.token) {
                fullContent += data.token;
                setStreamingContent(fullContent);
              }
              if (data.done) {
                sources = data.sources || [];
              }
              if (data.error) {
                throw new Error(data.error);
              }
            } catch (e) {
              if (e instanceof SyntaxError) continue;
              throw e;
            }
          }
        }
      }

      // Add complete message
      const assistantMsg: Message = {
        id: assistantId,
        role: "assistant",
        content: fullContent,
        sources: sources.length > 0 ? sources : undefined,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setStreamingContent("");
    } catch (err) {
      const errorMsg: Message = {
        id: assistantId,
        role: "assistant",
        content: `**Error:** ${err instanceof Error ? err.message : "Request failed"}\n\nMake sure the ForgeAI server is running on port 7337.`,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, errorMsg]);
      setStreamingContent("");
    } finally {
      setStreaming(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleClear = () => {
    setMessages([
      {
        id: `welcome-${Date.now()}`,
        role: "assistant",
        content:
          "Conversation cleared. How can I help you with your code?",
        timestamp: Date.now(),
      },
    ]);
    setStreaming(false);
    setStreamingContent("");
    inputRef.current?.focus();
  };

  return (
    <div className="flex flex-col h-[calc(100vh-6rem)]">
      {/* Header */}
      <div className="flex items-start justify-between mb-4 shrink-0">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Agent</h1>
          <p className="text-sm text-text-muted mt-1">
            Chat with the ForgeAI coding agent using your project&apos;s context.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Model selector */}
          <div className="relative">
            <button
              onClick={() => setModelOpen(!modelOpen)}
              className="btn-secondary text-xs gap-1.5"
            >
              <Bot size={14} />
              {selectedModel
                ? MODELS.find((m) => m.id === selectedModel)?.label
                : "Auto"}
            </button>
            {modelOpen && (
              <>
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setModelOpen(false)}
                />
                <div className="absolute right-0 top-full mt-1 z-20 w-64 bg-forge-surface border border-forge-border rounded-lg shadow-xl py-1">
                  {MODELS.map((model) => (
                    <button
                      key={model.id}
                      onClick={() => {
                        setSelectedModel(model.id);
                        setModelOpen(false);
                      }}
                      className={`w-full text-left px-4 py-2.5 text-sm transition-colors hover:bg-forge-elevated ${
                        selectedModel === model.id
                          ? "text-forge-primary bg-forge-primary/5"
                          : "text-text-secondary"
                      }`}
                    >
                      <div className="font-medium">{model.label}</div>
                      <div className="text-[11px] text-text-muted mt-0.5">
                        {model.description}
                      </div>
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>

          <button
            onClick={handleClear}
            className="btn-ghost text-xs gap-1.5"
            title="Clear conversation"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-2 mb-4 scroll-smooth">
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}

        {/* Streaming content */}
        {streaming && streamingContent && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-lg shrink-0 bg-zinc-800 flex items-center justify-center">
              <Bot size={16} className="text-text-secondary" />
            </div>
            <div className="bg-forge-elevated rounded-xl rounded-tl-md px-4 py-3 text-sm leading-relaxed">
              <p className="whitespace-pre-wrap text-text-primary">
                {streamingContent}
              </p>
            </div>
          </div>
        )}

        {/* Typing indicator */}
        {streaming && !streamingContent && <TypingIndicator />}

        {/* Preset prompts (only when no messages beyond welcome) */}
        {messages.length === 1 && !streaming && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-4">
            {PRESET_PROMPTS.map((preset) => {
              const Icon = preset.icon;
              return (
                <button
                  key={preset.label}
                  onClick={() => {
                    setInput(preset.prompt);
                    inputRef.current?.focus();
                  }}
                  className="card-hover p-3 text-left flex items-center gap-3"
                >
                  <div className="p-1.5 rounded-lg bg-forge-primary/10">
                    <Icon size={16} className="text-forge-primary" />
                  </div>
                  <span className="text-sm text-text-secondary">
                    {preset.label}
                  </span>
                </button>
              );
            })}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="shrink-0 border-t border-forge-border pt-4">
        <div className="flex gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question... (Shift+Enter for new line)"
            rows={1}
            className="input resize-none min-h-[44px] max-h-32 py-3"
            disabled={streaming}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || streaming}
            className="btn-primary px-4 shrink-0 self-end"
          >
            {streaming ? (
              <RefreshCw size={16} className="animate-spin" />
            ) : (
              <Send size={16} />
            )}
          </button>
        </div>
        <p className="text-[10px] text-text-muted mt-1.5">
          Responses are generated using {selectedModel || "the auto-selected model"}. 
          Agent uses RAG context from your indexed projects.
        </p>
      </div>
    </div>
  );
}
