"""
LangGraph Multi-Agent Pipeline — Gradio UI 版本
==========================================
UI 讓使用者動態編輯每個 node 的 system prompt，然後執行 pipeline。

流程: PM → DEV → QA → [PASS] → END
                    ↘ [FAIL] → DEV (最多重試 N 次)

啟動方式:
    uv run python langgraph_ui.py
"""

import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Generator, TypedDict

import gradio as gr
from langgraph.graph import END, StateGraph

# ── 常數 ───────────────────────────────────────────────────────────

COPILOT_BIN = r"C:\Users\alex\AppData\Roaming\npm\copilot.cmd"
LOG_FILE = Path(__file__).parent / "agent_handoff.log"

# ── 預設 Prompt 模板 ───────────────────────────────────────────────

DEFAULT_PM_PROMPT = """\
你是PM。根據以下需求寫完整規格：

需求：{task}

輸出格式：
1. 功能描述
2. Input / Output 定義（型別）
3. Edge cases（至少5個，含空陣列、找不到、負數）
4. 驗收標準（含時間/空間複雜度）

用繁體中文，簡潔輸出。"""

DEFAULT_DEV_PROMPT = """\
你是DEV。根據以下 PM spec，用 Python 實作功能。
只輸出完整可執行的 Python code，不要其他說明。

Spec：
{spec}
{qa_feedback}"""

DEFAULT_QA_PROMPT = """\
你是QA。根據以下 code 和 spec，做以下事情：
1. 列出測試案例表格（案例名稱 / input / expected / 結果✓✗）
2. 說明是否符合驗收標準

最後一行必須只輸出以下其中一個（不要其他文字）：
QA_RESULT: PASS
QA_RESULT: FAIL

Code：
{code}

Spec 驗收標準：
{spec}"""

# ── State ──────────────────────────────────────────────────────────


class AgentState(TypedDict):
    task: str
    spec: str
    code: str
    test_result: str
    qa_passed: bool
    retry_count: int
    messages: list
    log: str  # 累積 UI 輸出


# ── Helpers ────────────────────────────────────────────────────────


def call_copilot(prompt: str) -> str:
    """把 prompt 寫入暫存檔，用 -p @file 方式傳給 copilot CLI。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write(prompt)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [COPILOT_BIN, "-p", f"@{tmp_path}"],
            capture_output=True,
            timeout=180,
            shell=False,
            encoding="utf-8",
            errors="replace",
        )
    finally:
        os.unlink(tmp_path)

    output = result.stdout or result.stderr or ""
    skip_prefixes = (
        "(node:",
        "Total usage",
        "API time",
        "Total session",
        "Total code",
        "Breakdown",
        " claude-",
        "✗ skill",
    )
    lines = output.split("\n")
    filtered = [l for l in lines if not any(l.startswith(p) for p in skip_prefixes)]
    return "\n".join(filtered).strip()


def write_handoff_log(from_node: str, to_node: str, content: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sep = "=" * 55
    entry = f"\n{sep}\n[{ts}]  {from_node}  →  {to_node}\n{sep}\n{content}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry)


def section(title: str, content: str) -> str:
    """格式化 UI log 區塊。"""
    bar = "─" * 50
    return f"\n{bar}\n▶ {title}\n{bar}\n{content}\n"


# ── Pipeline Builder ───────────────────────────────────────────────


def build_pipeline(pm_prompt_tpl: str, dev_prompt_tpl: str, qa_prompt_tpl: str, max_retries: int):
    """
    根據 UI 傳入的 prompt 模板動態建立 LangGraph pipeline。
    回傳 compiled graph。
    """

    def pm_node(state: AgentState) -> AgentState:
        prompt = pm_prompt_tpl.format(task=state["task"])
        spec = call_copilot(prompt)
        write_handoff_log("PM", "DEV", spec)
        return {
            **state,
            "spec": spec,
            "log": state["log"] + section("[PM] Spec 產出", spec),
            "messages": [*state["messages"], "[PM] ✅ Spec 完成"],
        }

    def dev_node(state: AgentState) -> AgentState:
        retry = state.get("retry_count", 0)
        qa_feedback = ""
        if state.get("test_result") and not state.get("qa_passed", True):
            qa_feedback = f"\n\n⚠️ 上一版 QA 測試失敗，請根據以下錯誤修復：\n{state['test_result']}"

        prompt = dev_prompt_tpl.format(
            spec=state["spec"],
            qa_feedback=qa_feedback,
        )
        code = call_copilot(prompt)
        write_handoff_log("DEV", "QA", code)
        label = f"[DEV] Code 產出（retry={retry}）"
        return {
            **state,
            "code": code,
            "log": state["log"] + section(label, code),
            "messages": [*state["messages"], f"[DEV] ✅ Code 完成（retry={retry}）"],
        }

    def qa_node(state: AgentState) -> AgentState:
        prompt = qa_prompt_tpl.format(
            code=state["code"],
            spec=state["spec"],
        )
        test_result = call_copilot(prompt)
        qa_passed = "QA_RESULT: PASS" in test_result
        status = "✅ PASS" if qa_passed else "❌ FAIL"
        next_node = "END" if qa_passed else "DEV (retry)"
        write_handoff_log("QA", next_node, f"判定: {status}\n\n{test_result}")
        return {
            **state,
            "test_result": test_result,
            "qa_passed": qa_passed,
            "log": state["log"] + section(f"[QA] 測試結果 {status}", test_result),
            "messages": [*state["messages"], f"[QA] {status}"],
        }

    def should_retry(state: AgentState) -> str:
        if state.get("qa_passed"):
            return "end"
        if state.get("retry_count", 0) >= max_retries:
            return "end"
        state["retry_count"] = state.get("retry_count", 0) + 1
        return "retry"

    graph = StateGraph(AgentState)
    graph.add_node("pm", pm_node)
    graph.add_node("dev", dev_node)
    graph.add_node("qa", qa_node)
    graph.set_entry_point("pm")
    graph.add_edge("pm", "dev")
    graph.add_edge("dev", "qa")
    graph.add_conditional_edges("qa", should_retry, {"end": END, "retry": "dev"})
    return graph.compile()


# ── Gradio 執行函式 ────────────────────────────────────────────────


def run_pipeline(
    task: str,
    pm_prompt: str,
    dev_prompt: str,
    qa_prompt: str,
    max_retries: int,
) -> Generator[tuple, None, None]:
    """Gradio generator：逐步更新三個獨立輸出框（PM / DEV / QA）。"""

    if not task.strip():
        yield ("⚠️ 請輸入任務需求！", "", "")
        return

    LOG_FILE.write_text("", encoding="utf-8")

    yield ("⏳ PM 分析需求中...", "", "")

    app = build_pipeline(pm_prompt, dev_prompt, qa_prompt, int(max_retries))

    initial_state: AgentState = {
        "task": task,
        "spec": "",
        "code": "",
        "test_result": "",
        "qa_passed": False,
        "retry_count": 0,
        "messages": [],
        "log": "",
    }

    pm_out = dev_out = qa_out = ""
    state = initial_state

    for state in app.stream(initial_state, stream_mode="values"):
        spec = state.get("spec", "")
        code = state.get("code", "")
        test_result = state.get("test_result", "")
        retry = state.get("retry_count", 0)
        qa_passed = state.get("qa_passed", False)

        if spec:
            pm_out = spec

        if code:
            prefix = f"[retry #{retry}]\n{'─'*40}\n" if retry > 0 else ""
            dev_out = prefix + code

        if test_result:
            status = "✅ PASS" if qa_passed else "❌ FAIL"
            qa_out = f"判定: {status}\n{'─'*40}\n{test_result}"

        yield (
            pm_out or "⏳ PM 分析中...",
            dev_out or ("⏳ DEV 實作中..." if pm_out else ""),
            qa_out or ("⏳ QA 測試中..." if dev_out else ""),
        )

    # 最終摘要
    result = "✅ PASS" if state.get("qa_passed") else "❌ FAIL（超過重試次數）"
    msgs = "\n".join(f"  {m}" for m in state.get("messages", []))
    footer = f"\n\n{'='*40}\n🏁 最終結果: {result}\n{msgs}\n📄 handoff log → {LOG_FILE}"
    yield (pm_out, dev_out, qa_out + footer)


# ── Gradio UI ──────────────────────────────────────────────────────


def build_ui():
    with gr.Blocks(title="LangGraph Multi-Agent UI") as demo:
        gr.Markdown(
            """
# 🤖 LangGraph Multi-Agent Pipeline
動態編輯每個 Agent 的 Prompt，然後執行 Pipeline。

**流程**: PM → DEV → QA → (FAIL → DEV 重試)
"""
        )

        with gr.Row():
            task_input = gr.Textbox(
                label="📋 任務需求",
                placeholder="例如：實作 binary search，在已排序整數陣列中找目標值，回傳 index，找不到回傳 -1",
                lines=3,
                scale=4,
            )
            max_retries_slider = gr.Slider(
                label="🔄 最大重試次數",
                minimum=1,
                maximum=5,
                value=3,
                step=1,
                scale=1,
            )

        with gr.Accordion("🧑‍💼 PM Agent — Prompt 設定", open=False):
            gr.Markdown("可用變數：`{task}`")
            pm_prompt_box = gr.Textbox(
                value=DEFAULT_PM_PROMPT,
                lines=14,
                label="PM system prompt",
            )

        with gr.Accordion("👨‍💻 DEV Agent — Prompt 設定", open=False):
            gr.Markdown("可用變數：`{spec}`、`{qa_feedback}`")
            dev_prompt_box = gr.Textbox(
                value=DEFAULT_DEV_PROMPT,
                lines=10,
                label="DEV system prompt",
            )

        with gr.Accordion("🧪 QA Agent — Prompt 設定", open=False):
            gr.Markdown("可用變數：`{code}`、`{spec}`  **最後一行必須含 `QA_RESULT: PASS` 或 `QA_RESULT: FAIL`**")
            qa_prompt_box = gr.Textbox(
                value=DEFAULT_QA_PROMPT,
                lines=16,
                label="QA system prompt",
            )

        run_btn = gr.Button("▶ 執行 Pipeline", variant="primary", size="lg")

        with gr.Row():
            pm_out_box = gr.Textbox(
                label="🧑‍💼 PM — Spec 輸出",
                lines=20,
                max_lines=40,
                interactive=False,
            )
            dev_out_box = gr.Textbox(
                label="👨‍💻 DEV — Code 輸出",
                lines=20,
                max_lines=40,
                interactive=False,
            )
            qa_out_box = gr.Textbox(
                label="🧪 QA — 測試結果",
                lines=20,
                max_lines=40,
                interactive=False,
            )

        run_btn.click(
            fn=run_pipeline,
            inputs=[task_input, pm_prompt_box, dev_prompt_box, qa_prompt_box, max_retries_slider],
            outputs=[pm_out_box, dev_out_box, qa_out_box],
        )

    return demo


# ── Entry Point ────────────────────────────────────────────────────

if __name__ == "__main__":
    ui = build_ui()
    ui.launch(server_name="0.0.0.0", server_port=7860, share=False, theme=gr.themes.Soft())
