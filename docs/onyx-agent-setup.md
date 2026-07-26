# Onyx Agent Configuration Guide

**Status:** Current
**Applies to:** Onyx administrators configuring the running `VBPL Legal Research` agent and multi-resolution document sets.
**Use for:** Admin-UI setup, multi-resolution connector binding, runtime feature restrictions, and grounded-answer configuration.
**Do not use for:** Repository code changes, connector implementation, or Docker recovery.

This document describes the configuration requirements for setting up the
`VBPL Legal Research` agent in Onyx Community Edition (CE) running the Standard
deployment stack.

## Setup Requirements

- **Deployment**: Onyx Standard (Lite is unsupported since it disables indexing and RAG).
- **Authentication**: Basic Auth with the internal administrator and pilot users.
- **Multi-Resolution Corpus Sources**: Configure 3 persistent `VBPL Export Connector`
  sources reading the validated active release:
  1. `vbpl_current` (`corpus_view`: `current`) bound to Document Set **`VBPL Current`**
  2. `vbpl_history` (`corpus_view`: `history`) bound to Document Set **`VBPL History`**
  3. `vbpl_evidence` (`corpus_view`: `evidence`) bound to Document Set **`VBPL Evidence`**

## Release 1 UI boundary

Release 1 uses stock Onyx CE Chat and the `VBPL Legal Research` agent only.
Do not configure the standalone Onyx Search Mode/Search-only UI: it is not
available in the CE-only scope. Users search the legal corpus through the
agent's Internal Search action across the `VBPL Current` document set by default.

## Chat UI and Legal Agent Configuration

Create the `VBPL Legal Research` agent in the Onyx admin UI with the following constraints:

1. **Scope**: Scope primarily to the **`VBPL Current`** document set for current-law queries.
2. **Disabled Features**:
   - **Web Search**: Disabled.
   - **Code Execution**: Disabled.
   - **Craft**: Disabled.
   - **External MCP**: Disabled.
3. **Model Options**:
   - **Cloud default**: Default model (e.g., GPT-4o or Claude 3.5 Sonnet).
   - **Local alternative**: Local model via Ollama / LM Studio or local OpenAI-compatible endpoint.
   - *Warning*: Do not send sensitive case facts to the cloud provider unless explicitly approved.
4. **Required Agent Refusal**:
   - The agent must be instructed to refuse current-law conclusions when verified evidence is not found in the corpus, returning exactly the following message:
     ```text
     Không tìm thấy căn cứ VBPL đã được xác minh để trả lời câu hỏi này.
     ```
5. **Grounded-answer contract**:
   - Search only the scoped VBPL document sets; do not use a model's background
     knowledge as legal authority.
   - For every substantive conclusion, cite the instrument number/title,
     provision heading, canonical `vbpl.vn` link, legal-status label, and
     `verified_at`.
   - Make a current-law conclusion only for a retrieved record from `VBPL Current` whose status is fresh and is `Còn hiệu lực` or `Hết hiệu lực một phần`. For partially effective instruments, state the limitation and cite the exact provision.
