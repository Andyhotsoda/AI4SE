"""
WebUI Server — FastAPI + SSE streaming chat interface.

DeepSeek-style dark theme with:
- Left panel: chat conversation
- Right panel: file preview
- SSE streaming for real-time agent output
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

# Add harness to path
sys.path.insert(0, str(Path(__file__).parent))

from harness.llm.deepseek_client import DeepSeekClient
from harness.llm.base import LLMAuthenticationError
from harness.tools.registry import ToolRegistry
from harness.tools.file_tool import ReadFileTool, WriteFileTool, ListDirectoryTool
from harness.tools.shell_tool import ShellTool
from harness.governance.danger_classifier import DangerClassifier
from harness.governance.policy_engine import PolicyEngine
from harness.governance.hitl import HITLStateMachine
from harness.governance.scope_fence import ScopeFence
from harness.governance.sandbox import Sandbox
from harness.governance.action_interceptor import ActionInterceptor
from harness.memory.session_store import SessionStore
from harness.memory.project_store import ProjectStore
from harness.core.context_builder import ContextBuilder
from harness.core.agent import Agent
from harness.core.action_parser import ActionParser

app = FastAPI(title="Coding Agent Harness")

# Working directory
WORK_DIR = os.path.abspath(".")

# Global session state
sessions: dict[str, tuple[SessionStore, ProjectStore]] = {}

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Coding Agent Harness</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#1a1a2e;color:#e0e0e0;height:100vh;display:flex}
#chat-panel{flex:1;display:flex;flex-direction:column;max-width:60%}
#chat-header{background:#16213e;padding:16px 20px;border-bottom:1px solid #0f3460;font-size:18px;font-weight:600}
#chat-messages{flex:1;overflow-y:auto;padding:20px}
#chat-input-area{background:#16213e;padding:16px;border-top:1px solid #0f3460}
#chat-form{display:flex;gap:8px}
#task-input{flex:1;background:#1a1a2e;border:1px solid #0f3460;color:#e0e0e0;padding:12px 16px;border-radius:8px;font-size:14px;outline:none}
#task-input:focus{border-color:#533483}
#send-btn{background:#533483;color:#fff;border:none;padding:12px 24px;border-radius:8px;cursor:pointer;font-size:14px;font-weight:600}
#send-btn:hover{background:#6b46c1}
#send-btn:disabled{opacity:0.5;cursor:not-allowed}
#file-panel{flex:1;background:#16213e;border-left:1px solid #0f3460;display:flex;flex-direction:column;max-width:40%}
#file-header{background:#16213e;padding:16px 20px;border-bottom:1px solid #0f3460;font-size:18px;font-weight:600;display:flex;justify-content:space-between;align-items:center}
#file-list{flex:1;overflow-y:auto;padding:12px}
#file-content-area{flex:2;overflow-y:auto;padding:16px;background:#1a1a2e;border-top:1px solid #0f3460}
#file-content{font-family:'Consolas','Monaco',monospace;font-size:13px;white-space:pre-wrap;line-height:1.5}
.file-item{padding:8px 12px;cursor:pointer;border-radius:4px;font-size:13px;margin:2px 0}
.file-item:hover{background:#0f3460}
.file-item.active{background:#533483}
.message{margin-bottom:16px;padding:12px 16px;border-radius:8px;line-height:1.6}
.message.user{background:#0f3460;margin-left:40px}
.message.assistant{background:#1a1a2e;margin-right:40px;border:1px solid #0f3460}
.message.system{background:#2d1b3d;font-size:12px;margin:0 60px;text-align:center;color:#a0a0a0}
.tool-exec{background:#1a2332;border:1px solid #0f3460;padding:8px 12px;margin:8px 0;border-radius:4px;font-size:12px;font-family:monospace}
.tool-exec .tool-name{color:#533483;font-weight:600}
.tool-exec .tool-result{color:#4ade80}
.tool-exec .tool-error{color:#f87171}
.tool-exec .tool-blocked{color:#fbbf24}
#loading{display:none;text-align:center;padding:12px;color:#a0a0a0}
#loading.active{display:block}
.spinner{display:inline-block;width:20px;height:20px;border:2px solid #0f3460;border-top:2px solid #533483;border-radius:50%;animation:spin 1s linear infinite;margin-right:8px}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>
<div id="chat-panel">
  <div id="chat-header">Coding Agent Harness</div>
  <div id="chat-messages"></div>
  <div id="loading"><span class="spinner"></span>Agent thinking...</div>
  <div id="chat-input-area">
    <form id="chat-form" onsubmit="sendMessage(event)">
      <input type="text" id="task-input" placeholder="Enter your coding task..." autocomplete="off">
      <button type="submit" id="send-btn">Send</button>
    </form>
  </div>
</div>
<div id="file-panel">
  <div id="file-header">
    <span>Project Files</span>
    <button onclick="refreshFiles()" style="background:#533483;color:#fff;border:none;padding:6px 12px;border-radius:4px;cursor:pointer;font-size:12px">Refresh</button>
  </div>
  <div id="file-list"></div>
  <div id="file-content-area">
    <div id="file-content" style="color:#888">Click a file to preview</div>
  </div>
</div>
<script>
const sessionId = Math.random().toString(36).substring(7);
let currentFilePath = null;

async function sendMessage(e) {
  e.preventDefault();
  const input = document.getElementById('task-input');
  const task = input.value.trim();
  if (!task) return;

  input.value = '';
  input.disabled = true;
  document.getElementById('send-btn').disabled = true;
  document.getElementById('loading').classList.add('active');

  addMessage('user', task);

  const response = await fetch('/chat', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: new URLSearchParams({task, session_id: sessionId}),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let currentAssistantDiv = null;

  while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, {stream: true});
    const lines = buffer.split('\\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const data = JSON.parse(line.slice(6));

      if (data.type === 'text') {
        if (!currentAssistantDiv) {
          currentAssistantDiv = addMessage('assistant', '');
        }
        currentAssistantDiv.innerHTML += data.content.replace(/\\n/g, '<br>');
        scrollToBottom();
      } else if (data.type === 'tool') {
        if (!currentAssistantDiv) {
          currentAssistantDiv = addMessage('assistant', '');
        }
        const div = document.createElement('div');
        div.className = 'tool-exec';
        const status = data.allowed ? (data.success ? 'tool-result' : 'tool-error') : 'tool-blocked';
        div.innerHTML = `<span class="tool-name">${data.tool}</span> ${data.params}<br><span class="${status}">${data.result}</span>`;
        currentAssistantDiv.appendChild(div);
        scrollToBottom();
      } else if (data.type === 'done') {
        document.getElementById('loading').classList.remove('active');
        refreshFiles();
      }
    }
  }

  input.disabled = false;
  document.getElementById('send-btn').disabled = false;
  document.getElementById('loading').classList.remove('active');
  refreshFiles();
}

function addMessage(role, content) {
  const container = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = `message ${role}`;
  if (content) div.innerHTML = content.replace(/\\n/g, '<br>');
  container.appendChild(div);
  scrollToBottom();
  return div;
}

function scrollToBottom() {
  const container = document.getElementById('chat-messages');
  container.scrollTop = container.scrollHeight;
}

async function refreshFiles() {
  const resp = await fetch(`/files?session_id=${sessionId}`);
  const files = await resp.json();
  const list = document.getElementById('file-list');
  list.innerHTML = files.map(f =>
    `<div class="file-item${f===currentFilePath?' active':''}" onclick="previewFile('${f}')">${f}</div>`
  ).join('');
}

async function previewFile(path) {
  currentFilePath = path;
  const resp = await fetch(`/file/${path}?session_id=${sessionId}`);
  const data = await resp.json();
  document.getElementById('file-content').textContent = data.content || '(empty)';
  refreshFiles();
}

refreshFiles();
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(HTML_TEMPLATE)


@app.get("/files")
async def list_files(session_id: str = "default"):
    """List project files."""
    files = []
    try:
        for entry in sorted(Path(WORK_DIR).iterdir()):
            if entry.name.startswith(".") or entry.name.startswith("__"):
                continue
            if entry.is_file():
                files.append(entry.name)
            elif entry.is_dir():
                for sub in sorted(entry.rglob("*.py")):
                    rel = str(sub.relative_to(WORK_DIR)).replace("\\", "/")
                    files.append(rel)
    except Exception:
        pass
    return files


@app.get("/file/{path:path}")
async def read_file(path: str, session_id: str = "default"):
    """Read a file's content."""
    try:
        full_path = Path(WORK_DIR) / path
        full_path = full_path.resolve()
        if not str(full_path).startswith(str(Path(WORK_DIR).resolve())):
            return {"content": "Access denied"}
        if full_path.exists() and full_path.is_file():
            content = full_path.read_text(encoding="utf-8", errors="replace")
            return {"content": content}
    except Exception as e:
        return {"content": f"Error: {e}"}
    return {"content": "(file not found)"}


@app.post("/chat")
async def chat(task: str = Form(...), session_id: str = Form("default")):
    """Stream agent response via SSE."""
    async def generate():
        try:
            # Get or create session
            if session_id not in sessions:
                sessions[session_id] = (
                    SessionStore(),
                    ProjectStore(store_path=os.path.join(WORK_DIR, ".harness", "memory")),
                )
            session, project = sessions[session_id]

            # Build agent
            llm = DeepSeekClient(model="deepseek-chat")

            registry = ToolRegistry()
            registry.register(ReadFileTool())
            registry.register(WriteFileTool())
            registry.register(ListDirectoryTool())
            registry.register(ShellTool(working_dir=WORK_DIR))

            async def web_approve(req):
                return True  # Web mode: auto-approve for now

            interceptor = ActionInterceptor(
                classifier=DangerClassifier(),
                policy=PolicyEngine.create_default_policy(),
                hitl=HITLStateMachine(timeout_seconds=30, approval_callback=web_approve),
                fence=ScopeFence(allowed_directories=[WORK_DIR]),
                sandbox=Sandbox(strategy="subprocess"),
            )

            context = ContextBuilder(
                tool_registry=registry,
                session_store=session,
                project_store=project,
            )

            agent = Agent(
                llm=llm,
                tools=registry,
                interceptor=interceptor,
                sandbox=Sandbox(strategy="subprocess"),
                context_builder=context,
                session_store=session,
                project_store=project,
                max_iterations=30,
                max_consecutive_failures=5,
            )

            # Add user task to session
            session.add_turn(role="user", content=task)

            # Run agent loop with streaming
            async def stream_callback(event_type: str, data: dict):
                yield f"data: {json.dumps({'type': event_type, **data})}\n\n"

            async for event in _run_agent_streaming(agent, task, session):
                yield f"data: {json.dumps(event)}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            sessions[session_id] = (session, project)

        except LLMAuthenticationError as e:
            yield f"data: {json.dumps({'type': 'text', 'content': f'Error: No API key. Run harness setup-key.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'text', 'content': f'Error: {e}'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


async def _run_agent_streaming(agent: Agent, task: str, session: SessionStore):
    """Run the agent loop, yielding SSE events for each step."""
    from harness.llm.base import LLMError
    from harness.tools.base import ActionResult
    from harness.core.action_parser import ActionParser
    from harness.core.stop_decision import StopReason

    agent._stop_engine.reset()
    agent._turns = []

    while True:
        messages = agent._context_builder.build()

        try:
            llm_response = await agent._llm.complete(messages)
        except LLMError as e:
            yield {"type": "text", "content": f"\n[Error: {e}]\n"}
            break

        full_response = llm_response.content
        actions = ActionParser.parse(full_response)
        natural_text = ActionParser.extract_text(full_response)

        # Stream natural language text
        if natural_text:
            yield {"type": "text", "content": natural_text}

        agent._session_store.add_turn(role="assistant", content=full_response)

        all_succeeded = True
        for action in actions:
            intercept = await agent._interceptor.intercept(action)

            params_str = json.dumps(action.parameters, ensure_ascii=False)
            if not intercept.allowed:
                yield {
                    "type": "tool",
                    "tool": action.tool_name,
                    "params": params_str,
                    "result": f"Blocked: {intercept.reason}",
                    "allowed": False,
                    "success": False,
                }
                agent._session_store.add_turn(
                    role="feedback",
                    content=f"Action blocked: {intercept.reason}",
                )
                all_succeeded = False
                continue

            if intercept.use_sandbox:
                result = await agent._sandbox.execute(action, agent._tools.dispatch)
            else:
                result = await agent._tools.dispatch(action)

            yield {
                "type": "tool",
                "tool": action.tool_name,
                "params": params_str,
                "result": result.output[:500] if result.success else f"Error: {result.error}",
                "allowed": True,
                "success": result.success,
            }

            result_msg = f"Result of {action.tool_name}: {result.output if result.success else result.error}"
            agent._session_store.add_turn(role="feedback", content=result_msg)

            if not result.success:
                all_succeeded = False

        agent_stopped = ActionParser.has_stop_action(actions)
        if not actions and natural_text.strip():
            agent_stopped = True

        decision = agent._stop_engine.evaluate(
            agent_stopped=agent_stopped,
            action_succeeded=all_succeeded if actions else None,
        )

        if decision.should_stop:
            break

    yield {"type": "done"}


def main():
    """Start the WebUI server."""
    print("=" * 60)
    print("Coding Agent Harness - WebUI")
    print("Open http://localhost:8000 in your browser")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()