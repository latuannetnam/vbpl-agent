# Onyx Agent Configuration Guide

This document describes the configuration requirements for setting up the `VBPL Legal Research` agent in Onyx Standard.

## Setup Requirements

- **Deployment**: Onyx Standard (Lite is unsupported since it disables indexing and RAG).
- **Authentication**: Basic Auth with crawler service credentials and pilot users.
- **Corpus Source**: Create exactly one source named `vbpl-verified` targeting the pipeline index.

## Search UI Configuration

Configure the Onyx Search UI to target only the `vbpl-verified` source. Result cards must show:
- The instrument/provision identifier.
- The status badge (e.g. `Còn hiệu lực` or `Hết hiệu lực một phần`).
- Verification time (`status_checked_at`).
- Canonical `vbpl.vn` link.
- Excerpts showing the matching provision.

## Chat UI and Legal Agent Configuration

Create the `VBPL Legal Research` agent in the Onyx admin UI with the following constraints:

1. **Scope**: Scoped exclusively to the `vbpl-verified` document source.
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
