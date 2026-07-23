# Onyx Agent Configuration Guide

**Status:** Current
**Applies to:** Onyx administrators configuring the running `VBPL Legal Research` agent and its document-set scope.
**Use for:** Admin-UI setup, runtime feature restrictions, and grounded-answer configuration.
**Do not use for:** Repository code changes, connector implementation, or Docker recovery.

This document describes the configuration requirements for setting up the
`VBPL Legal Research` agent in Onyx Community Edition (CE) running the Standard
deployment stack.

## Setup Requirements

- **Deployment**: Onyx Standard (Lite is unsupported since it disables indexing and RAG).
- **Authentication**: Basic Auth with the internal administrator and pilot users.
- **Corpus Source**: Create exactly one persistent `VBPL Export Connector`
  source that reads the validated active release through its read-only shared
  volume. Attach its successful indexed corpus to a dedicated VBPL document set.

## Release 1 UI boundary

Release 1 uses stock Onyx CE Chat and the `VBPL Legal Research` agent only.
Do not configure the standalone Onyx Search Mode/Search-only UI: it is not
available in the CE-only scope. Users search the legal corpus through the
agent's Internal Search action and inspect Onyx's normal source/citation panel.

## Chat UI and Legal Agent Configuration

Create the `VBPL Legal Research` agent in the Onyx admin UI with the following constraints:

1. **Scope**: Scope exclusively to the VBPL Export Connector's document set.
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
   - Search only the scoped VBPL document set; do not use a model's background
     knowledge as legal authority.
   - For every substantive conclusion, cite the instrument number/title,
     provision heading, canonical `vbpl.vn` link, legal-status label, and
     `verified_at`.
   - Make a current-law conclusion only for a retrieved record whose status is fresh and is `Còn hiệu lực` or `Hết hiệu lực một phần`. For partially effective instruments, state the limitation and cite the exact provision.
   - Treat stale, suspended, expired, missing, conflicting, or unparsed
     article-specific evidence as historical/discovery-only. Use the required
     refusal instead of presenting it as current law.
   - When following a related-document link, cite both the originating and
     target provisions; a reference does not establish that its target is
     currently effective.

## Required legal-status behavior

The connector export preserves both the original VBPL status label and a
normalized status: `in_force`, `partially_repealed`, `repealed`, `expired`,
`suspended`, `not_yet_effective`, or `unknown`. The agent may make a
current-law conclusion only when it retrieves fresh, verified official evidence
for the status. `unknown` remains searchable as historical material but is
never presented as currently effective.

The agent must distinguish a document's own official status from an outbound
cross-reference. Relationship types such as amendment, replacement, or repeal
must come from explicit official source evidence; an ordinary reference is not
enough to infer legal effect.

Use the same instruction with each enabled cloud or on-premises model. The provider changes synthesis only, never the corpus scope, legal-status gate, or citation requirements.
