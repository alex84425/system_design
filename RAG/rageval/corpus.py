"""語料載入：把 data/cocktails/*.md 讀成可檢索的文件。

真實專案裡語料就是一個資料夾的 markdown，loader 要自己處理
frontmatter 與正文的拆分——frontmatter 進 metadata（給 filter 用），
正文進 embedding。這一步沒人會幫你做。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Doc:
    """一份文件。

    `id`    : 檔名（不含副檔名），評估集的 ground truth 用的就是這個
    `meta`  : frontmatter 解析結果，metadata filtering 用
    `body`  : 正文 markdown
    `text`  : 實際要被索引的文字（名稱 + 材料 + 正文）
    """

    id: str
    meta: dict[str, Any]
    body: str
    path: str
    text: str = field(default="")

    def __post_init__(self):
        if not self.text:
            self.text = self.build_text()

    def build_text(self) -> str:
        """決定「什麼東西進索引」——這是 RAG 第一個會影響分數的設計決策。

        把名稱與關鍵欄位併進正文，是因為使用者常常直接問酒名，
        而正文裡不一定每段都提到名字。純正文索引會讓
        「Negroni 的比例是多少」這種題目意外地難撈。
        """
        m = self.meta
        head = " ".join(
            str(m.get(k, ""))
            for k in ("name_zh", "name_en", "base", "family", "glass")
        )
        flavors = " ".join(m.get("flavors", []))
        return f"{head} {flavors}\n{self.body}".strip()


_FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_scalar(v: str) -> Any:
    """極簡的 YAML 值解析。

    我們自己產的 frontmatter 只有字串與 [a, b, c] 兩種形態，
    不值得為此拉一個 pyyaml 進來。真實專案語料格式更雜時再換掉。
    """
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [x.strip() for x in inner.split(",")]
    return v


def parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    """回傳 (metadata, 正文)。沒有 frontmatter 時 metadata 為空字典。"""
    m = _FM.match(raw)
    if not m:
        return {}, raw.strip()
    meta: dict[str, Any] = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        meta[key.strip()] = _parse_scalar(val)
    return meta, raw[m.end():].strip()


def load_corpus(directory: str) -> list[Doc]:
    """讀取整個資料夾的 .md，依檔名排序（讓結果可重現）。"""
    docs: list[Doc] = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".md"):
            continue
        path = os.path.join(directory, name)
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        meta, body = parse_frontmatter(raw)
        doc_id = meta.get("id") or os.path.splitext(name)[0]
        docs.append(Doc(id=doc_id, meta=meta, body=body, path=path))
    if not docs:
        raise FileNotFoundError(f"{directory} 裡沒有 .md，先跑 build_dataset.py")
    return docs


def load_eval(path: str) -> list[dict[str, Any]]:
    """讀取評估集 jsonl。"""
    import json

    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items
