from vbpl_kb.onyx_chat import RetrievedChunk, ToolCallEvidence, ChatResult
from vbpl_kb.acceptance import (
    AcceptanceCase,
    AcceptanceContext,
    run_acceptance,
    run_single_result_acceptance,
    chat_result_with_search_source,
)


class FakeChatClient:
    def __init__(self, responses: list[ChatResult]) -> None:
        self.responses = list(responses)
        self.session_ids: list[str | None] = []

    def send(self, message: str, persona_id: int, chat_session_id: str | None = None) -> ChatResult:
        self.session_ids.append(chat_session_id)
        return self.responses.pop(0)


def test_acceptance_reuses_session_and_records_retrieved_chunks(tmp_path) -> None:
    retrieved = RetrievedChunk(
        document_id="vbpl:178717",
        chunk_ind=12,
        semantic_identifier="Luật 87/2025/QH15",
        link="https://vbpl.vn/van-ban/chi-tiet/--178717",
        blurb="Vị trí: dieu-3\nĐiều 3. Điều khoản chuyển tiếp",
        source_type="vbpl_export",
        metadata={"article4_order": "2"},
    )
    search_call = ToolCallEvidence(
        tool_name="internal_search",
        tool_arguments={"queries": ["Văn bản huyện còn hiệu lực không?"]},
        search_docs=(retrieved,),
    )
    chat = FakeChatClient([
        ChatResult(
            answer="Bạn hỏi tháng 7/2026.",
            chat_session_id="session-1",
            documents=(retrieved,),
            tool_calls=(search_call,),
            raw_response={},
        ),
        ChatResult(
            answer="Văn bản huyện còn trong thời kỳ chuyển tiếp.",
            chat_session_id="session-1",
            documents=(retrieved,),
            tool_calls=(search_call,),
            raw_response={},
        ),
    ])
    report = run_acceptance(
        cases=(AcceptanceCase(
            case_id="context",
            messages=("Tôi hỏi tại Việt Nam tháng 7/2026.", "Văn bản huyện còn hiệu lực không?"),
            expected_document_ids=("vbpl:178717",),
            expected_provision_keys=("dieu-3",),
        ),),
        chat=chat,
        context=AcceptanceContext(
            label="baseline",
            model_name="model-a",
            persona_id=7,
            prompt_sha256="a" * 64,
            release_id="vbpl-2026-07-22",
            connector_status={"status": "success", "total_chunks": 100},
        ),
    )

    assert chat.session_ids == [None, "session-1"]
    assert report.records[0].retrieved_chunks[0].chunk_ind == 12
    assert report.context.prompt_sha256 == "a" * 64


def test_acceptance_rejects_answer_without_internal_search_evidence() -> None:
    result = ChatResult(
        answer="Điều 1 áp dụng.",
        chat_session_id="session-1",
        documents=(),
        tool_calls=(),
        raw_response={},
    )

    report = run_single_result_acceptance(result)

    assert report.passed is False
    assert any("internal_search" in f for f in report.failures)


def test_acceptance_rejects_internal_search_from_non_vbpl_source() -> None:
    result = chat_result_with_search_source("web")

    report = run_single_result_acceptance(result)

    assert report.passed is False
    assert any("vbpl_export" in f for f in report.failures)
