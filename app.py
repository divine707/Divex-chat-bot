import os
import json
from flask import Flask, request, jsonify, render_template
import requests

app = Flask(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
MEMORY_FILE = "memory.json"
USERNAME = "boss"

# ---- Simple memory: a JSON file storing facts learned about the user ----
def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    return {"facts": [], "history": []}

def save_memory(memory):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)

memory = load_memory()


@app.route("/")
def home():
    return render_template("index.html", username=USERNAME)


@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json.get("message", "")

    # Add user's message to running history
    memory["history"].append({"role": "user", "content": user_message})

    # Build the system prompt using any facts learned so far
    facts_text = "\n".join(f"- {fact}" for fact in memory["facts"])
    system_prompt = (
        f"You are a helpful assistant talking to {USERNAME}. "
        f"Here is what you remember about {USERNAME} so far:\n{facts_text or 'Nothing yet.'}\n"
        "If the user shares a durable personal fact or preference worth remembering "
        "(like a name, a preference, a goal), include it at the very end of your reply "
        "on its own line formatted exactly like: MEMORY: <short fact>. "
        "Only include a MEMORY line when there's actually something new and worth keeping. "
        "Never show the MEMORY line as part of your visible answer to the user's question — "
        "it will be stripped out automatically."
    )

    # Gemini expects "user"/"model" roles and a "parts" list per message
    gemini_contents = []
    for m in memory["history"][-20:]:
        role = "model" if m["role"] == "assistant" else "user"
        gemini_contents.append({"role": role, "parts": [{"text": m["content"]}]})

    response = requests.post(
        GEMINI_URL,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
        },
        json={
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": gemini_contents,
        },
    )

    data = response.json()
    print("GEMINI STATUS:", response.status_code)
    print("GEMINI RESPONSE:", data)
    reply_text = ""
    try:
        reply_text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        reply_text = "Sorry, I couldn't come up with a reply just now."

    # Extract and store any MEMORY: line, strip it from what the user sees
    visible_reply = reply_text
    for line in reply_text.splitlines():
        if line.strip().startswith("MEMORY:"):
            fact = line.strip()[len("MEMORY:"):].strip()
            if fact and fact not in memory["facts"]:
                memory["facts"].append(fact)
            visible_reply = visible_reply.replace(line, "").strip()

    memory["history"].append({"role": "assistant", "content": visible_reply})
    save_memory(memory)

    return jsonify({"reply": visible_reply})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
