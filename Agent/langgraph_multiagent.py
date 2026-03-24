"""
LangGraph Multi-Agent Pipeline with copilot CLI
流程: PM → DEV → QA → [PASS] → END
                   ↘ [FAIL] → DEV (最多重試 3 次)
"""

import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, StateGraph

MAX_RETRIES = 3
LOG_FILE = Path(__file__).parent / "agent_handoff.log"

# copilot.cmd 的完整 Windows 路徑
COPILOT_BIN = r"C:\Users\alex\AppData\Roaming\npm\copilot.cmd"


# ── Handoff Logger ────────────────────────────────────────────────


def write_handoff_log(from_node: str, to_node: str, content: str) -> None:
    """把 from_node 傳給 to_node 的最後一次訊息附加寫入 LOG_FILE"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    separator = "=" * 55
    entry = f"\n{separator}\n" f"[{ts}]  {from_node}  →  {to_node}\n" f"{separator}\n" f"{content}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry)


# ── Copilot LLM Wrapper ────────────────────────────────────────────


def call_copilot(prompt: str) -> str:
    """把 prompt 寫入暫存檔，用 -p @file 方式傳給 copilot，避免 Windows cmd 截斷中文"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write(prompt)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [COPILOT_BIN, "-p", f"@{tmp_path}"],
            capture_output=True,
            timeout=120,
            shell=False,
            encoding="utf-8",
            errors="replace",
        )
        output = result.stdout or result.stderr or ""
    finally:
        os.unlink(tmp_path)

    output = result.stdout or result.stderr or ""
    lines = output.split("\n")
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
    filtered = [l for l in lines if not any(l.startswith(p) for p in skip_prefixes)]
    return "\n".join(filtered).strip()


# ── State ──────────────────────────────────────────────────────────


class AgentState(TypedDict):
    task: str  # 原始需求
    spec: str  # PM 產出的規格
    code: str  # DEV 產出的程式碼
    test_result: str  # QA 測試結果
    qa_passed: bool  # QA 是否通過
    retry_count: int  # DEV 已重試次數
    messages: list  # 執行日誌


# ── Nodes ──────────────────────────────────────────────────────────


def pm_node(state: AgentState) -> AgentState:
    print("\n" + "=" * 55)
    print(">>> [PM Agent] 分析需求，產出 Spec...")
    print("=" * 55)

    prompt = f"""你是PM。根據以下需求寫完整規格：

需求：{state['task']}

輸出格式：
1. 功能描述
2. Input / Output 定義（型別）
3. Edge cases（至少5個，含空陣列、找不到、負數）
4. 驗收標準（含時間/空間複雜度）

用繁體中文，簡潔輸出。"""

    spec = call_copilot(prompt)
    print(spec)

    write_handoff_log("PM", "DEV", spec)

    return {
        **state,
        "spec": spec,
        "messages": [*state["messages"], "[PM] ✅ Spec 產出完成"],
    }


def dev_node(state: AgentState) -> AgentState:
    retry = state.get("retry_count", 0)

    print("\n" + "=" * 55)
    if retry == 0:
        print(">>> [DEV Agent] 根據 Spec 實作 Code...")
    else:
        print(f">>> [DEV Agent] 修復 Code（第 {retry} 次重試）...")
    print("=" * 55)

    qa_feedback = ""
    if state.get("test_result") and not state.get("qa_passed", True):
        qa_feedback = f"\n\n⚠️ 上一版 QA 測試失敗，請根據以下錯誤修復：\n{state['test_result']}"

    prompt = f"""你是DEV。根據以下 PM spec，用 Python 實作功能。
只輸出完整可執行的 Python code，不要其他說明。

Spec：
{state['spec']}
{qa_feedback}"""

    code = call_copilot(prompt)
    print(code)

    write_handoff_log("DEV", "QA", code)

    return {
        **state,
        "code": code,
        "messages": [*state["messages"], f"[DEV] ✅ Code 產出完成（retry={retry}）"],
    }


def qa_node(state: AgentState) -> AgentState:
    print("\n" + "=" * 55)
    print(">>> [QA Agent] 執行測試評估...")
    print("=" * 55)

    prompt = f"""你是QA。根據以下 code 和 spec，做以下事情：
1. 列出測試案例表格（案例名稱 / input / expected / 結果✓✗）
2. 說明是否符合驗收標準

最後一行必須只輸出以下其中一個（不要其他文字）：
QA_RESULT: PASS
QA_RESULT: FAIL

Code：
{state['code']}

Spec 驗收標準：
{state['spec']}"""

    test_result = call_copilot(prompt)
    print(test_result)

    qa_passed = "QA_RESULT: PASS" in test_result

    status = "✅ PASS" if qa_passed else "❌ FAIL"
    print(f"\n>>> QA 判定: {status}")

    next_node = "END" if qa_passed else "DEV (retry)"
    write_handoff_log("QA", next_node, f"判定: {status}\n\n{test_result}")

    return {
        **state,
        "test_result": test_result,
        "qa_passed": qa_passed,
        "messages": [*state["messages"], f"[QA] {status}"],
    }


# ── Conditional Edge ───────────────────────────────────────────────


def should_retry(state: AgentState) -> str:
    if state.get("qa_passed"):
        return "end"

    retry_count = state.get("retry_count", 0)
    if retry_count >= MAX_RETRIES:
        print(f"\n⛔ 超過最大重試次數 ({MAX_RETRIES})，強制結束")
        return "end"

    # 遞增 retry_count，傳回 retry 讓 graph 回到 dev_node
    state["retry_count"] = retry_count + 1
    print(f"\n🔄 QA 未通過，退回 DEV 重試（{state['retry_count']}/{MAX_RETRIES}）...")
    return "retry"


# ── Build Graph ────────────────────────────────────────────────────


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("pm", pm_node)
    graph.add_node("dev", dev_node)
    graph.add_node("qa", qa_node)

    graph.set_entry_point("pm")
    graph.add_edge("pm", "dev")
    graph.add_edge("dev", "qa")
    graph.add_conditional_edges(
        "qa",
        should_retry,
        {
            "end": END,
            "retry": "dev",  # QA 失敗 → 回 DEV 重試
        },
    )

    return graph.compile()


# ── Main ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = build_graph()

    initial_state: AgentState = {
        "task": "實作 binary search，在已排序整數陣列中找目標值，回傳 index，找不到回傳 -1",
        "spec": "",
        "code": "",
        "test_result": "",
        "qa_passed": False,
        "retry_count": 0,
        "messages": [],
    }

    # 每次執行先清空 log
    LOG_FILE.write_text("", encoding="utf-8")

    print("\n" + "🚀 " * 18)
    print("  LangGraph Multi-Agent Pipeline 啟動")
    print("  流程: PM → DEV → QA → (FAIL → DEV 重試，最多3次)")
    print("🚀 " * 18)

    final_state = app.invoke(initial_state)

    print("\n" + "=" * 55)
    print("  Pipeline 完成！執行日誌：")
    print("=" * 55)
    for msg in final_state["messages"]:
        print(f"  {msg}")

    result = "✅ PASS" if final_state["qa_passed"] else "❌ FAIL（超過重試次數）"
    print(f"\n最終結果: {result}")
