import { useState, useRef, useEffect } from "react";
import { Send, Menu, StopCircle, Sparkles } from "lucide-react";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

interface ChatAreaProps {
  onToggleSidebar: () => void;
}

const suggestions = [
  "Explain how transformer attention works",
  "Write a React custom hook for WebSocket",
  "Debug this Python async function",
  "Design a REST API for a todo app",
];

const models = [
  { id: "claude-opus", name: "Claude Opus 4.5", provider: "Anthropic" },
  { id: "claude-sonnet", name: "Claude Sonnet 4", provider: "Anthropic" },
  { id: "gpt4o", name: "GPT-4o", provider: "OpenAI" },
  { id: "deepseek", name: "DeepSeek Coder", provider: "DeepSeek" },
];

export default function ChatArea({ onToggleSidebar }: ChatAreaProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedModel, setSelectedModel] = useState(models[0]);
  const [showModelPicker, setShowModelPicker] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = async () => {
    if (!input.trim() || isStreaming) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsStreaming(true);

    // Simulate AI response
    setTimeout(() => {
      const aiResponses: Record<string, string> = {
        "Explain how transformer attention works":
          `## Transformer Attention Mechanism

The attention mechanism is the core innovation of transformer architectures. Here's how it works:

### Scaled Dot-Product Attention

$$\\text{Attention}(Q, K, V) = \\text{softmax}\\left(\\frac{QK^T}{\\sqrt{d_k}}\\right)V$$

1. **Query (Q)**: What we're looking for
2. **Key (K)**: What we can match against
3. **Value (V)**: What we return

The dot product $QK^T$ measures similarity between queries and keys. Dividing by $\\sqrt{d_k}$ prevents gradient instability.

### Multi-Head Attention

Instead of one attention function, transformers use multiple parallel attention heads:

\`\`\`python
class MultiHeadAttention(nn.Module):
    def __init__(self, d_model, num_heads):
        super().__init__()
        self.num_heads = num_heads
        self.d_k = d_model // num_heads
        self.W_q = nn.Linear(d_model, d_model)
        self.W_k = nn.Linear(d_model, d_model)
        self.W_v = nn.Linear(d_model, d_model)
        self.W_o = nn.Linear(d_model, d_model)
    
    def forward(self, x):
        batch_size = x.size(0)
        Q = self.W_q(x).view(batch_size, -1, self.num_heads, self.d_k).transpose(1, 2)
        K = self.W_k(x).view(batch_size, -1, self.num_heads, self.d_k).transpose(1, 2)
        V = self.W_v(x).view(batch_size, -1, self.num_heads, self.d_k).transpose(1, 2)
        
        scores = torch.matmul(Q, K.transpose(-2, -1)) / math.sqrt(self.d_k)
        attn = torch.softmax(scores, dim=-1)
        out = torch.matmul(attn, V).transpose(1, 2).contiguous()
        return self.W_o(out.view(batch_size, -1, self.num_heads * self.d_k))
\`\`\`

This allows the model to attend to information from different representation subspaces.`,
      };

      const reply =
        aiResponses[userMsg.content] ||
        `That's a great question! Let me think about this carefully.

Here's my analysis of **${userMsg.content}**:

1. **First principles**: Let's break this down from the ground up
2. **Key considerations**: Performance, readability, and maintainability
3. **Recommended approach**: I suggest using a modular design

\`\`\`typescript
// Example implementation
function solve(input: string): string {
  return \`Processing: \${input}\`;
}
\`\`\`

> **Note**: This is a simulated response for demonstration purposes. In production, this would call the actual AI model.`;

      const aiMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: reply,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, aiMsg]);
      setIsStreaming(false);
    }, 1500);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Auto-resize textarea
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 200)}px`;
    }
  }, [input]);

  return (
    <div className="flex-1 flex flex-col min-w-0 h-full relative">
      {/* Chat Header */}
      <div className="flex items-center justify-center px-4 py-2 relative">
        <button
          onClick={onToggleSidebar}
          className="absolute left-3 p-1 rounded hover:bg-[var(--panel)] text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          <Menu size={18} />
        </button>
        <div className="text-xs text-zinc-500">
          {messages.length > 0 && (
            <span className="text-zinc-600">{messages.length} messages</span>
          )}
        </div>
      </div>

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto px-4">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center animate-fade-in">
            <Sparkles size={32} className="text-[var(--accent)]/40 mb-4" />
            <h1 className="text-2xl font-bold bg-gradient-to-r from-[var(--accent)] to-cyan-400 bg-clip-text text-transparent mb-2">
              Odysseus
            </h1>
            <p className="text-sm text-zinc-500 mb-2">Welcome! Ask me anything.</p>
            <p className="text-xs text-zinc-600 mb-8 max-w-xs leading-relaxed">
              Tip: Use <span className="text-[var(--accent)]">/setup</span> to configure your providers
            </p>

            <div className="grid grid-cols-2 gap-2 max-w-md">
              {suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => {
                    setInput(s);
                    inputRef.current?.focus();
                  }}
                  className="text-xs text-left px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--panel)] hover:bg-[var(--panel-alt)] hover:border-[var(--accent)]/30 transition-all text-zinc-400 hover:text-[var(--fg)]"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="max-w-3xl mx-auto space-y-4 py-4">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"} animate-fade-in`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                    msg.role === "user"
                      ? "bg-[var(--accent)]/20 rounded-br-md"
                      : "bg-[var(--panel)] rounded-bl-md border border-[var(--border)]"
                  }`}
                >
                  {msg.role === "assistant" && (
                    <div className="flex items-center gap-2 mb-2">
                      <Sparkles size={12} className="text-[var(--accent)]" />
                      <span className="text-[10px] text-zinc-500 font-medium">
                        {selectedModel.name}
                      </span>
                    </div>
                  )}
                  <div className="text-sm leading-relaxed whitespace-pre-wrap">
                    {msg.content}
                  </div>
                  <div className="text-[10px] text-zinc-600 mt-2 text-right">
                    {msg.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </div>
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Input Bar */}
      <div className="px-4 pb-4 pt-2">
        <div className="max-w-3xl mx-auto glass rounded-2xl border border-[var(--border)] p-3">
          {/* Model Picker */}
          <div className="relative mb-2">
            <button
              onClick={() => setShowModelPicker(!showModelPicker)}
              className="flex items-center gap-1 text-[11px] text-zinc-500 hover:text-[var(--fg)] transition-colors"
            >
              <Sparkles size={10} className="text-[var(--accent)]" />
              {selectedModel.name}
              <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>

            {showModelPicker && (
              <div className="absolute bottom-full left-0 mb-2 glass border border-[var(--border)] rounded-lg shadow-xl p-1 min-w-[200px] z-20">
                {models.map((model) => (
                  <button
                    key={model.id}
                    onClick={() => {
                      setSelectedModel(model);
                      setShowModelPicker(false);
                    }}
                    className={`w-full text-left px-3 py-2 rounded text-xs transition-colors ${
                      selectedModel.id === model.id
                        ? "bg-[var(--accent)]/10 text-[var(--fg)]"
                        : "text-zinc-400 hover:text-[var(--fg)] hover:bg-[var(--panel)]"
                    }`}
                  >
                    <div className="font-medium">{model.name}</div>
                    <div className="text-[10px] text-zinc-500">{model.provider}</div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Input Row */}
          <div className="flex items-end gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message Odysseus..."
              rows={1}
              className="flex-1 bg-transparent border-none outline-none resize-none text-sm text-[var(--fg)] placeholder:text-zinc-600 max-h-[200px]"
            />
            <button
              onClick={isStreaming ? () => setIsStreaming(false) : handleSubmit}
              disabled={!input.trim() && !isStreaming}
              className={`flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center transition-all ${
                isStreaming
                  ? "bg-[var(--error)] text-white hover:bg-[var(--error)]/80"
                  : input.trim()
                    ? "bg-[var(--accent)] text-white hover:brightness-110"
                    : "bg-[var(--panel)] text-zinc-600"
              }`}
            >
              {isStreaming ? <StopCircle size={16} /> : <Send size={16} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
