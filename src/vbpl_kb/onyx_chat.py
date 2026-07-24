import re
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from vbpl_kb.config import Settings


class RetrievedChunk(BaseModel):
    model_config = ConfigDict(frozen=True)
    document_id: str
    chunk_ind: int
    semantic_identifier: str
    link: str | None
    blurb: str
    source_type: str
    metadata: dict[str, Any]

    @property
    def provision_key(self) -> str:
        match = re.search(r"(?m)^Vị trí:\s*(\S+)\s*$", self.blurb)
        if match:
            return match.group(1)
        legacy = self.metadata.get("provision_key", "")
        return legacy if isinstance(legacy, str) else ""


class ToolCallEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)
    tool_name: str
    tool_arguments: dict[str, Any]
    search_docs: tuple[RetrievedChunk, ...]


class ChatResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    answer: str
    chat_session_id: str
    documents: tuple[RetrievedChunk, ...]
    tool_calls: tuple[ToolCallEvidence, ...] = ()
    raw_response: dict[str, Any]


class OnyxChatClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(
        self,
        message: str,
        persona_id: int,
        chat_session_id: str | None = None,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "message": message,
            "stream": False,
            "include_citations": True,
            "allowed_tool_ids": [self.settings.onyx_internal_search_tool_id],
            "forced_tool_id": self.settings.onyx_internal_search_tool_id,
            "internal_search_filters": {
                "source_type": ["vbpl_export"],
                "document_set": [self.settings.onyx_document_set_name],
            },
        }
        if chat_session_id is None:
            payload["chat_session_info"] = {"persona_id": persona_id}
        else:
            payload["chat_session_id"] = chat_session_id
        headers: dict[str, str] = {}
        api_key = self.settings.onyx_api_key.get_secret_value()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        url = (
            f"{self.settings.onyx_base_url.rstrip('/')}"
            f"{self.settings.onyx_chat_path}"
        )
        response = httpx.post(
            url,
            json=payload,
            headers=headers,
            timeout=max(self.settings.onyx_request_timeout_seconds, 600.0),
        )
        response.raise_for_status()
        data = response.json()
        if data.get("error_msg"):
            raise RuntimeError(str(data["error_msg"]))
        session_id = data.get("chat_session_id")
        if not isinstance(session_id, str):
            raise RuntimeError("Onyx response did not include chat_session_id")
        return ChatResult(
            answer=str(data.get("answer", "")),
            chat_session_id=session_id,
            documents=tuple(
                RetrievedChunk.model_validate(item)
                for item in data.get("top_documents", [])
            ),
            tool_calls=tuple(
                ToolCallEvidence(
                    tool_name=str(item.get("tool_name", "")),
                    tool_arguments=dict(item.get("tool_arguments", {})),
                    search_docs=tuple(
                        RetrievedChunk.model_validate(document)
                        for document in (item.get("search_docs") or [])
                    ),
                )
                for item in data.get("tool_calls", [])
            ),
            raw_response=data,
        )
