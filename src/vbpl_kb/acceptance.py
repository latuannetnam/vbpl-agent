from datetime import datetime, UTC
from typing import Any
from pydantic import BaseModel, ConfigDict

from vbpl_kb.onyx_chat import RetrievedChunk, ToolCallEvidence, ChatResult


class AcceptanceCase(BaseModel):
    model_config = ConfigDict(frozen=True)
    case_id: str
    messages: tuple[str, ...]
    expected_document_ids: tuple[str, ...] = ()
    expected_provision_keys: tuple[str, ...] = ()
    excluded_document_ids: tuple[str, ...] = ()
    expects_clarification: bool = False


class AcceptanceContext(BaseModel):
    model_config = ConfigDict(frozen=True)
    label: str
    model_name: str
    persona_id: int
    prompt_sha256: str
    release_id: str
    connector_status: dict[str, Any]


class AcceptanceRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    case_id: str
    messages: tuple[str, ...]
    answers: tuple[str, ...]
    chat_session_id: str
    retrieved_chunks: tuple[RetrievedChunk, ...]
    tool_calls: tuple[ToolCallEvidence, ...]
    passed: bool
    failures: tuple[str, ...]


class AcceptanceReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    passed: bool
    failures: tuple[str, ...]
    records: tuple[AcceptanceRecord, ...]
    context: AcceptanceContext
    timestamp: str


def run_acceptance(
    cases: tuple[AcceptanceCase, ...] | list[AcceptanceCase],
    chat: Any,
    context: AcceptanceContext,
) -> AcceptanceReport:
    records: list[AcceptanceRecord] = []
    all_report_failures: list[str] = []
    overall_passed = True

    for case in cases:
        case_failures: list[str] = []
        answers: list[str] = []
        all_retrieved_chunks: list[RetrievedChunk] = []
        all_tool_calls: list[ToolCallEvidence] = []
        session_id: str | None = None

        for msg in case.messages:
            res: ChatResult = chat.send(msg, persona_id=context.persona_id, chat_session_id=session_id)
            session_id = res.chat_session_id
            answers.append(res.answer)
            all_retrieved_chunks.extend(res.documents)
            all_tool_calls.extend(res.tool_calls)

            # Check tool call rules
            if not res.tool_calls:
                case_failures.append(f"Case '{case.case_id}': Answer missing required 'internal_search' tool call evidence")
            else:
                for tc in res.tool_calls:
                    if tc.tool_name != "internal_search":
                        case_failures.append(f"Case '{case.case_id}': Unauthorized tool call '{tc.tool_name}' used")
                    if not tc.search_docs:
                        case_failures.append(f"Case '{case.case_id}': 'internal_search' returned empty search_docs")
                    for doc in tc.search_docs:
                        if doc.source_type != "vbpl_export":
                            case_failures.append(f"Case '{case.case_id}': Invalid source_type '{doc.source_type}' (must be 'vbpl_export')")
                        if not doc.document_id.startswith("vbpl:"):
                            case_failures.append(f"Case '{case.case_id}': Invalid document_id '{doc.document_id}' (must start with 'vbpl:')")
                        all_retrieved_chunks.append(doc)

            for doc in res.documents:
                if doc.source_type != "vbpl_export":
                    case_failures.append(f"Case '{case.case_id}': Top document has invalid source_type '{doc.source_type}'")
                if not doc.document_id.startswith("vbpl:"):
                    case_failures.append(f"Case '{case.case_id}': Top document has invalid document_id '{doc.document_id}'")

        # Deduplicate retrieved chunks while preserving order
        seen_chunks: set[tuple[str, int]] = set()
        unique_chunks: list[RetrievedChunk] = []
        for c in all_retrieved_chunks:
            key = (c.document_id, c.chunk_ind)
            if key not in seen_chunks:
                seen_chunks.add(key)
                unique_chunks.append(c)

        retrieved_doc_ids = {c.document_id for c in unique_chunks}
        retrieved_provision_keys = {c.provision_key for c in unique_chunks if c.provision_key}

        # Check expected document IDs
        for expected_id in case.expected_document_ids:
            if expected_id not in retrieved_doc_ids:
                case_failures.append(f"Case '{case.case_id}': Missing expected document ID '{expected_id}'")

        # Check expected provision keys
        for expected_pk in case.expected_provision_keys:
            if expected_pk not in retrieved_provision_keys:
                case_failures.append(f"Case '{case.case_id}': Missing expected provision key '{expected_pk}'")

        # Check excluded document IDs
        for excluded_id in case.excluded_document_ids:
            if excluded_id in retrieved_doc_ids:
                case_failures.append(f"Case '{case.case_id}': Found excluded document ID '{excluded_id}'")

        case_passed = len(case_failures) == 0
        if not case_passed:
            overall_passed = False
            all_report_failures.extend(case_failures)

        records.append(
            AcceptanceRecord(
                case_id=case.case_id,
                messages=tuple(case.messages),
                answers=tuple(answers),
                chat_session_id=session_id or "",
                retrieved_chunks=tuple(unique_chunks),
                tool_calls=tuple(all_tool_calls),
                passed=case_passed,
                failures=tuple(case_failures),
            )
        )

    return AcceptanceReport(
        passed=overall_passed,
        failures=tuple(all_report_failures),
        records=tuple(records),
        context=context,
        timestamp=datetime.now(UTC).isoformat(),
    )


def run_single_result_acceptance(result: ChatResult) -> AcceptanceReport:
    class SingleResultChatClient:
        def send(self, message: str, persona_id: int, chat_session_id: str | None = None) -> ChatResult:
            return result

    context = AcceptanceContext(
        label="single_test",
        model_name="test-model",
        persona_id=1,
        prompt_sha256="0" * 64,
        release_id="test-release",
        connector_status={},
    )
    case = AcceptanceCase(
        case_id="single_test_case",
        messages=("Test query",),
    )
    return run_acceptance((case,), SingleResultChatClient(), context)


def chat_result_with_search_source(source_type: str) -> ChatResult:
    chunk = RetrievedChunk(
        document_id="vbpl:100",
        chunk_ind=0,
        semantic_identifier="Doc 100",
        link=None,
        blurb="Vị trí: dieu-1\nTest",
        source_type=source_type,
        metadata={},
    )
    tool_call = ToolCallEvidence(
        tool_name="internal_search",
        tool_arguments={"queries": ["test"]},
        search_docs=(chunk,),
    )
    return ChatResult(
        answer="Test answer",
        chat_session_id="sess-1",
        documents=(chunk,),
        tool_calls=(tool_call,),
        raw_response={},
    )
