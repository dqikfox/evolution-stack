# Character Model Patterns

Complete working pattern for dedicated Ollama character models — one model per persona with full identity baked into the Modelfile SYSTEM block.

## Architecture

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│   Modelfile SYSTEM  │────▶│   Ollama Model      │────▶│   /api/chat         │
│   (full persona)      │     │   (baked-in weight) │     │   (clean content)   │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
                                      │
                                      ▼
                              ┌─────────────────────┐
                              │   Runtime context   │
                              │   (mood, memory)    │
                              │   prepended to user │
                              └─────────────────────┘
```

## engine.py integration

```python
PERSONAS_DIR = Path(__file__).parent / "personas"
PERSONA_ALIASES = {"luna": "lila", "sprout": "pip"}

CHARACTER_MODELS = {
    "lumo": "lummings-lumo",
    "lila": "lummings-lila",
    "pip":  "lummings-pip",
    "nori": "lummings-nori",
    "moki": "lummings-moki",
}
DEFAULT_MODEL = "lummings-lumo"

def get_character_model(name: str) -> str:
    """Return the dedicated Ollama model name for a character, or fallback."""
    name = PERSONA_ALIASES.get(name.lower(), name.lower())
    return CHARACTER_MODELS.get(name, DEFAULT_MODEL)

def build_runtime_prompt(persona: dict, memory_summary: str = "",
                         mood: str = "", user_name: str = "") -> str:
    """Lightweight runtime prompt for dedicated character models.
    
    Character identity is already baked into the model via Modelfile SYSTEM.
    This only injects session-specific context (mood, memory, user).
    Keep it minimal to avoid overriding the baked-in persona.
    """
    parts = []
    if user_name:
        parts.append(f"The child you're talking to is named {user_name}.")
    if mood:
        parts.append(f"Your current mood is: {mood}.")
    if memory_summary:
        parts.append(f"MEMORY: {memory_summary}")
    return "\n".join(parts) if parts else "Stay in character."
```

## cli.py / server.py chat function

Use `/api/chat` directly — not `/v1/chat/completions` — to avoid exposing reasoning chains:

```python
import urllib.request, json

def chat(base_url: str, model: str, system: str, user: str, history=None,
         max_tokens: int = 256, temperature: float = 0.7, timeout: int = 60) -> dict:
    msgs = []
    if history:
        for h in history[-6:]:
            msgs.append({"role": h["role"], "content": h["content"]})
    msgs.append({"role": "user", "content": user})
    
    body = json.dumps({
        "model": model,
        "messages": msgs,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": temperature,
        }
    }).encode()
    
    req = urllib.request.Request(
        f"{base_url.rstrip('/').replace('/v1', '')}/api/chat",
        data=body, headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
            msg = data.get("message", {})
            content = msg.get("content", "").strip()
            # Fallback to thinking field if content is empty (reasoning models)
            if not content:
                content = msg.get("thinking", "").strip()
            return {"ok": True, "content": content}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}
```

## server.py request handler

```python
# Use dedicated character model; persona is baked into the Modelfile
model = get_character_model(persona_name)
runtime_ctx = build_runtime_prompt(persona, memory_summary=memory.summarize(), mood=mood.state)

# For character models, prepend context to user message instead of system message
# to avoid triggering reasoning/meta mode
if runtime_ctx.strip():
    final_user = f"{runtime_ctx}\n\n{user_msg}"
else:
    final_user = user_msg

r = chat(body.get("base_url", "http://127.0.0.1:11434/v1"),
         model, "", final_user, history=history)
```

## Frontend wiring

```javascript
const API_BASE = 'http://127.0.0.1:8511';
let apiAvailable = false;
let currentChatName = null;

fetch(`${API_BASE}/ui`, { method: 'HEAD', mode: 'no-cors' })
    .then(() => { apiAvailable = true; })
    .catch(() => { apiAvailable = false; });

function openChat(name) {
    currentChatName = name.toLowerCase();
    // ... clear scroller ...
    
    if (apiAvailable) {
        fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                persona: currentChatName,
                message: `Say hello to a new friend in your own voice.`
            })
        })
        .then(r => r.json())
        .then(data => {
            const reply = data.reply || `Hey! I'm ${name}.`;
            appendMessage(reply, 'lummings');
        })
        .catch(() => {
            appendMessage(`Hey! I'm ${name}. What are we imagining today?`, 'lummings');
        });
    } else {
        appendMessage(`Hey! I'm ${name}. What are we imagining today?`, 'lummings');
    }
}

function sendMessage() {
    const text = input.value.trim();
    if (!text) return;
    appendMessage(text, 'user');
    input.value = '';

    if (apiAvailable && currentChatName) {
        fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({persona: currentChatName, message: text})
        })
        .then(r => r.json())
        .then(data => {
            if (data.error) appendMessage(`(connection issue: ${data.error})`, 'lummings');
            else if (data.reply) appendMessage(data.reply, 'lummings');
            else appendMessage("(silent)", 'lummings');
        })
        .catch(() => {
            appendMessage(`(couldn't reach the Lummings server)`, 'lummings');
        });
    } else {
        // Fallback to static demo mode
    }
}
```

## Verified base models for characters

| Model | Size | Context | Family | Notes |
|---|---|---|---|---|
| `ornith-1.5:9b` | 9B | 262K | Qwen3.5 | Good balance of quality and speed; thinking model |
| `starscream-64k` | 26B | 262K | Gemma4 | Higher quality but slower; also thinking |
| `nous-hermes2:10.7b` | 11B | 4K | Llama | Non-thinking; simpler template |

## Decision table: when to use character models

| Scenario | Recommendation |
|---|---|
| Single persona, high fidelity | Dedicated model per character |
| Many personas, shared base | Runtime prompt swapping with single model |
| Thinking model (Qwen3.5/Gemma4) | Must use `/api/chat` + skip API system messages |
| Non-thinking model (Llama/Mistral) | Either `/api/chat` or `/v1/chat/completions` works |
| Production deployment | `num_predict=256` minimum; monitor `eval_count` |
