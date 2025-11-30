import gradio as gr
from loguru import logger
import json
import time
import threading
import os

# Try to import the project's run_agent function. The project must provide:
# project/main_agent.py -> run_agent(user_input: str)
try:
    from project.main_agent import run_agent
except Exception as e:
    # Provide a fallback stub that returns an explanatory message so the UI still loads.
    def run_agent(user_input: str):
        return (
            "ERROR: couldn't import run_agent from project.main_agent. "
            "Make sure your repository exposes project/main_agent.py with a run_agent(user_input: str) function.\n"
            f"Import error: {e}"
        )

# Configure structured JSON logging with loguru
log_path = "spaces_app.log"
logger.remove()
logger.add(
    log_path,
    rotation="10 MB",
    retention="10 days",
    serialize=True,  # JSON structured logs
    enqueue=True,
)

# Helper to append conversation to display as markdown
def format_conversation(history):
    md = []
    for turn in history:
        role = turn.get("role", "user")
        text = turn.get("text", "")
        if role == "user":
            md.append(f"**User:** {text}")
        else:
            md.append(f"**Agent:** {text}")
    return "\n\n".join(md)

def process_input(user_input, history):
    logger.info(json.dumps({"event": "user_input", "text": user_input, "timestamp": time.time()}))
    # Call the project's agent
    try:
        response = run_agent(user_input)
    except Exception as e:
        response = f"Error running agent: {e}"
        logger.exception("run_agent failed")

    # Append to history
    history = history or []
    history.append({"role": "user", "text": user_input})
    history.append({"role": "agent", "text": str(response)})

    # Log the response
    logger.info(json.dumps({"event": "agent_response", "text": str(response), "timestamp": time.time()}))

    return format_conversation(history), history

# Read logs (tail) for display
def read_logs():
    if not os.path.exists(log_path):
        return ""
    try:
        # read last ~200 lines of the file
        with open(log_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 1024
            data = b""
            while size > 0 and len(data) < 200*200:
                if size - block > 0:
                    f.seek(size - block)
                else:
                    f.seek(0)
                data = f.read() + data
                size -= block
            text = data.decode(errors="ignore")
        # For nicer display, pretty-print each JSON line (if possible)
        out_lines = []
        for line in text.strip().splitlines()[-200:]:
            line = line.strip()
            try:
                js = json.loads(line)
                out_lines.append(json.dumps(js, indent=2))
            except Exception:
                out_lines.append(line)
        return "\n\n".join(out_lines)
    except Exception as e:
        return f"Could not read logs: {e}"

# Build Gradio UI
demo = gr.Blocks(title="Universal Multi-Agent - Hugging Face Deploy")

with demo:
    gr.Markdown("""# Universal Multi-Agent Interface

    Paste a prompt below and press **Submit**. This UI works with any multi-agent project
    that exposes `project/main_agent.py -> run_agent(user_input: str)`.

    - Session memory is kept for the conversation.
    - Structured JSON logs are written to `spaces_app.log`.
    """)

    with gr.Row():
        with gr.Column(scale=3):
            input_txt = gr.Textbox(lines=3, placeholder="Enter your prompt here...", label="Prompt")
            submit_btn = gr.Button("Submit")
            convo_md = gr.Markdown("", label="Conversation")
            state = gr.State([])  # stores the conversation as a list of turns
        with gr.Column(scale=1):
            with gr.Accordion("Logs (live)", open=False):
                logs_box = gr.Textbox(value=read_logs(), lines=20, interactive=False, show_label=False)
            # Interval to refresh logs every 2 seconds
            gr.Interval(2, fn=lambda: read_logs(), outputs=[logs_box])

    # Wire actions
    submit_btn.click(fn=process_input, inputs=[input_txt, state], outputs=[convo_md, state])
    # Also allow pressing Enter in the textbox to submit
    input_txt.submit(fn=process_input, inputs=[input_txt, state], outputs=[convo_md, state])

# Auto-launch Gradio for Spaces
demo.launch(server_name="0.0.0.0", server_port=7860)
