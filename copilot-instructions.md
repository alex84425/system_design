# Copilot Instructions

> 專門給 GitHub Copilot（GPT-5.1）/ AI 代理人看的入口文件。
>
> 人類開發者主要還是看 README.md 和 spec 目錄下的文件。

---

## 專案簡介

本專案是 system design teacher，主要用途：

- 協助我準備 system design 面試，提供一個可互動、可持續優化的學習工具。
- 準備最小練習端

更完整的背景與設計請先閱讀下列 spec 文件。

---

## 請優先閱讀的文件（重要）

AI 代理人在開始任何大規模修改前，請**依序**閱讀：

1. system design pattern：
    - [spec/README.md](spec/README.md)

### Spec 閱讀與修改流程（從 spec/README.md 搬移）

在對專案行為或 UI 做任意修改前，AI 代理人應遵循以下順序：

1. **先讀 spec/README.md**：了解有哪些 spec，以及哪些是「通用」哪些是「專案特有」。
2. **再讀通用 spec**：

- [spec/construct-build-design.md](spec/construct-build-design.md)
- [spec/test-design.md](spec/test-design.md)
- [spec/provider-development-guideline.md](spec/provider-development-guideline.md)
  這些是「框架級 / 平台級」規則，適用於多個 service，請勿修改，只能遵守。
