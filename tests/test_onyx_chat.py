import json
import httpx
import respx
from vbpl_kb.config import Settings
from vbpl_kb.onyx_chat import OnyxChatClient


@respx.mock
def test_send_uses_non_streaming_chat_api_and_preserves_sources() -> None:
    route = respx.post("http://onyx:8080/chat/send-chat-message").mock(
        return_value=httpx.Response(
            200,
            json={
                "answer": "Điều 1 áp dụng.",
                "answer_citationless": "Điều 1 áp dụng.",
                "top_documents": [{
                    "document_id": "vbpl:178717",
                    "chunk_ind": 4,
                    "semantic_identifier": "Luật 87/2025/QH15",
                    "link": "https://vbpl.vn/van-ban/chi-tiet/--178717",
                    "blurb": "Vị trí: dieu-1\nĐiều 1. Sửa đổi...",
                    "source_type": "vbpl_export",
                    "boost": 1,
                    "hidden": False,
                    "metadata": {"article4_order": "2"},
                    "match_highlights": [],
                }],
                "citation_info": [],
                "message_id": 9,
                "chat_session_id": "00000000-0000-0000-0000-000000000001",
                "error_msg": None,
                "tool_calls": [{
                    "tool_name": "internal_search",
                    "tool_arguments": {"queries": ["Hỏi Điều 1"]},
                    "tool_result": "Retrieved 1 VBPL chunk.",
                    "search_docs": [{
                        "document_id": "vbpl:178717",
                        "chunk_ind": 4,
                        "semantic_identifier": "Luật 87/2025/QH15",
                        "link": "https://vbpl.vn/van-ban/chi-tiet/--178717",
                        "blurb": "Vị trí: dieu-1\nĐiều 1. Sửa đổi...",
                        "source_type": "vbpl_export",
                        "boost": 1,
                        "hidden": False,
                        "metadata": {"article4_order": "2"},
                        "match_highlights": [],
                    }],
                }],
            },
        )
    )
    client = OnyxChatClient(
        Settings(
            onyx_base_url="http://onyx:8080",
            onyx_api_key="secret",
            onyx_internal_search_tool_id=41,
            onyx_document_set_name="VBPL",
        )
    )

    result = client.send("Hỏi Điều 1", persona_id=7)

    request = json.loads(route.calls.last.request.content)
    assert request == {
        "message": "Hỏi Điều 1",
        "chat_session_info": {"persona_id": 7},
        "stream": False,
        "include_citations": True,
        "allowed_tool_ids": [41],
        "forced_tool_id": 41,
        "internal_search_filters": {
            "source_type": ["vbpl_export"],
            "document_set": ["VBPL"],
        },
    }
    assert route.calls.last.request.headers["Authorization"] == "Bearer secret"
    assert result.documents[0].document_id == "vbpl:178717"
    assert result.documents[0].chunk_ind == 4
    assert result.documents[0].provision_key == "dieu-1"
    assert result.tool_calls[0].tool_name == "internal_search"
    assert result.tool_calls[0].search_docs[0].source_type == "vbpl_export"
