# VBPL Hierarchy-Aware Onyx Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make stock Onyx CE retrieve provision-level Vietnamese law as legally scoped authority bundles while preserving official status evidence, stable instrument identity, and fail-closed current-law behavior.

**Architecture:** The VBPL pipeline classifies authority and applicability, parses ordered provision sections, and records only evidence-backed legal relationships before producing checksummed schema-v2 releases. The existing connector remains backward compatible with schema v1, maps every schema-v2 provision to an Onyx `TextSection`, and leaves semantic/keyword relevance as the primary retrieval signal. The scoped Onyx agent performs staged Internal Search and direct Chat API acceptance tests prove the behavior without MCP.

**Tech Stack:** Python 3.12+, Pydantic 2, SQLite, pytest, Ruff, mypy, Typer, httpx, Docker Compose, PowerShell, pinned Onyx CE commit `e31b356...`, and the official VBPL API/canonical pages.

## Global Constraints

- Official VBPL API and canonical-page evidence are authoritative; ordinary citations and model knowledge are not legal-effect evidence.
- Use hierarchy regime `vn-vbqppl-2025-07-01`; do not apply it to conflict resolution for events before 1 July 2025.
- The Article 4 order has 15 authority groups. Forms in the same numbered group have equal modeled authority.
- Keep semantic and keyword relevance primary. Do not add a global Article 4 numeric boost or maintain a retrieval/reranking fork.
- Keep stable instrument IDs in the form `vbpl:<official-id>`.
- Current-law evidence must be successfully verified within the existing configured 24-hour freshness window.
- Preserve raw and normalized status, effective period, jurisdiction, transition, provision coordinates, source URL, corpus revision, and evidence hashes.
- Map numeric VBPL `referenceType` values only where retained official API data and a canonical VBPL page establish the meaning. Unmapped values remain `unknown`.
- Text heuristics may create candidates but may not establish `amends`, `supplements`, `replaces`, `repeals`, `suspends`, `continues_effect`, `details`, or `implements`.
- Missing `projection_schema_version` means schema v1 only. Every new projection declares schema v2. Unsupported versions fail validation.
- Retain the prior active release and prompt for rollback. Never delete SQLite state, raw snapshots, releases, connector/source records, the Onyx index, or Docker volumes to recover this rollout.
- The post-deployment indexed chunk count must not exceed 1.25 times the measured baseline without explicit user approval.
- Update `AGENTS.md` and current canonical documentation only after implementation behavior is settled. Current docs must not link to this dated plan or its design spec.
- Direct acceptance uses the ordinary authenticated Onyx Chat API or web UI. It must not call the current MCP server or MCP endpoint.

---

## File Structure

### Create

- `src/vbpl_kb/authority.py` — normalized issuer/form classification against the 15 Article 4 groups.
- `src/vbpl_kb/applicability.py` — effective-time, jurisdiction, transition, and status-evidence envelope.
- `src/vbpl_kb/provisions.py` — deterministic article/clause/point parsing and compact section headers.
- `src/vbpl_kb/onyx_chat.py` — ordinary authenticated non-streaming Onyx Chat API client.
- `src/vbpl_kb/acceptance.py` — live case execution, evidence recording, and acceptance metrics.
- `tests/test_authority.py`, `tests/test_applicability.py`, `tests/test_provisions.py` — focused domain tests.
- `tests/test_onyx_chat.py`, `tests/test_acceptance.py` — non-MCP Chat API and record tests.
- `tests/test_vbpl_export_connector.py` — executable schema-v1/v2 connector tests with stubbed Onyx models.
- `tests/fixtures/vbpl/references-178717.json` — minimal retained official evidence for verified relationship codes 3 and 10.
- `benchmarks/hierarchy-v1.json` — synthetic and live-query acceptance contract.

### Modify

- `src/vbpl_kb/models.py` — authority, applicability, section, relationship-evidence, and schema-v2 projection models.
- `src/vbpl_kb/normalize.py` — compose classification, applicability, provisions, headers, and compact metadata.
- `src/vbpl_kb/references.py` — verified structured mapping, candidate handling, deduplication, and relation tokens.
- `src/vbpl_kb/state.py` — migrate and persist relationship evidence without losing existing rows.
- `src/vbpl_kb/publish.py` — keep legacy diagnostic ingestion compatible with multi-section projections.
- `src/vbpl_kb/releases.py` — write/validate schema-v2 documents and expose staged promotion/rollback.
- `src/vbpl_kb/evaluate.py` — controlling-provision recall, bundle completeness, conflict, and safety metrics.
- `src/vbpl_kb/config.py`, `src/vbpl_kb/cli.py` — acceptance, staged release, and full re-index commands.
- `src/vbpl_kb/connector_control.py` — return inspectable connector status including chunk totals when present.
- `infra/onyx/overlay/backend/onyx/connectors/vbpl_export/connector.py` — prevalidate and emit schema-v1/v2 sections.
- `tests/test_normalize.py`, `tests/test_references.py`, `tests/test_state.py`, `tests/test_publish.py`, `tests/test_releases.py`, `tests/test_evaluate.py`, `tests/test_cli.py`, `tests/test_config.py`, `tests/test_connector_control.py`, `tests/test_release_deployment.py`.
- `AGENTS.md`, `README.md`, `docs/architecture.md`, `docs/legal-data-policy.md`, `docs/operations.md`, `docs/onyx-agent-setup.md`, `docs/onyx-agent-instruction.md`, `tests/test_documentation.py`.

### Runtime artifacts (ignored under `data/`)

- `data/evaluations/hierarchy-baseline.json`
- `data/evaluations/hierarchy-post-deploy.json`
- `data/rollback/active-release-before.json`
- `data/rollback/onyx-agent-instruction-before.md`

## Cross-Task Interfaces

```python
def classify_authority(
    document_type: str | dict[str, object] | None,
    issuer: str | dict[str, object] | None,
) -> AuthorityClassification: ...

def build_applicability(
    raw: dict[str, object],
    status: StatusObservation,
    authority: AuthorityClassification,
    revision: str,
) -> ApplicabilityEnvelope: ...

def split_provisions(text: str) -> tuple[Provision, ...]: ...

def normalize_relationships(
    from_vbpl_id: str,
    structured: list[dict[str, object]],
    candidates: list[RawReferenceCandidate],
    instrument_index: dict[str, str],
    corpus_revision: str,
) -> tuple[LegalReference, ...]: ...

def normalize_instrument(
    raw: dict[str, object],
    status: StatusObservation,
    revision: str,
    references: tuple[LegalReference, ...] = (),
) -> OnyxDocument: ...

class ReleaseExporter:
    def write_candidate(self, run_id: str) -> ReleaseManifest: ...
    def validate_candidate(self, manifest: ReleaseManifest) -> None: ...
    def load_manifest(self, release_id: str) -> ReleaseManifest: ...
    def promote(self, manifest: ReleaseManifest) -> ActiveRelease: ...

class OnyxChatClient:
    def send(self, message: str, persona_id: int, chat_session_id: str | None = None) -> ChatResult: ...

def run_acceptance(
    cases: tuple[AcceptanceCase, ...],
    chat: OnyxChatClient,
    context: AcceptanceContext,
) -> AcceptanceReport: ...
```

---

### Task 1: Add the direct Onyx Chat acceptance harness and capture the baseline

**Files:**
- Create: `src/vbpl_kb/onyx_chat.py`, `src/vbpl_kb/acceptance.py`
- Create: `tests/test_onyx_chat.py`, `tests/test_acceptance.py`
- Create: `benchmarks/hierarchy-v1.json`
- Modify: `src/vbpl_kb/config.py`, `src/vbpl_kb/cli.py`, `tests/test_config.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes the current Onyx backend route `POST /chat/send-chat-message`.
- Produces `ChatResult`, `AcceptanceCase`, `AcceptanceContext`, `AcceptanceRecord`, `AcceptanceReport`, and CLI command `onyx-acceptance`.
- Writes non-secret records under `data/evaluations`; it never prints or serializes the API key.

- [ ] **Step 1: Write the failing ordinary Chat API test**

```python
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
                "tool_calls": [],
            },
        )
    )
    client = OnyxChatClient(
        Settings(onyx_base_url="http://onyx:8080", onyx_api_key="secret")
    )

    result = client.send("Hỏi Điều 1", persona_id=7)

    request = json.loads(route.calls.last.request.content)
    assert request == {
        "message": "Hỏi Điều 1",
        "chat_session_info": {"persona_id": 7},
        "stream": False,
        "include_citations": True,
    }
    assert route.calls.last.request.headers["Authorization"] == "Bearer secret"
    assert result.documents[0].document_id == "vbpl:178717"
    assert result.documents[0].chunk_ind == 4
    assert result.documents[0].provision_key == "dieu-1"
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_onyx_chat.py::test_send_uses_non_streaming_chat_api_and_preserves_sources -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'vbpl_kb.onyx_chat'`.

- [ ] **Step 3: Implement the minimal Chat client**

```python
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
    metadata: dict[str, str | list[str]]

    @property
    def provision_key(self) -> str:
        match = re.search(r"(?m)^Vị trí:\s*(\S+)\s*$", self.blurb)
        if match:
            return match.group(1)
        legacy = self.metadata.get("provision_key", "")
        return legacy if isinstance(legacy, str) else ""


class ChatResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    answer: str
    chat_session_id: str
    documents: tuple[RetrievedChunk, ...]
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
            timeout=self.settings.onyx_request_timeout_seconds,
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
            raw_response=data,
        )
```

Add these settings:

```python
onyx_chat_path: str = "/chat/send-chat-message"
onyx_persona_id: int | None = None
onyx_model_name: str = ""
evaluation_dir: Path = Path("data/evaluations")
```

- [ ] **Step 4: Write the failing multi-turn record test**

```python
def test_acceptance_reuses_session_and_records_retrieved_chunks(tmp_path) -> None:
    chat = FakeChatClient([
        ChatResult(answer="Bạn hỏi tháng 7/2026.", chat_session_id="session-1", documents=(), raw_response={}),
        ChatResult(
            answer="Văn bản huyện còn trong thời kỳ chuyển tiếp.",
            chat_session_id="session-1",
            documents=(RetrievedChunk(
                document_id="vbpl:178717",
                chunk_ind=12,
                semantic_identifier="Luật 87/2025/QH15",
                link="https://vbpl.vn/van-ban/chi-tiet/--178717",
                blurb="Vị trí: dieu-3\nĐiều 3. Điều khoản chuyển tiếp",
                metadata={"article4_order": "2"},
            ),),
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
```

- [ ] **Step 5: Implement acceptance models, JSON output, and the CLI command**

Implement immutable Pydantic models. `run_acceptance` must:

1. reuse the returned session ID for later messages in the same case;
2. retain query, answer, document ID, chunk index, blurb, metadata, and official link;
3. calculate structural pass/fail from expected/excluded IDs and provision keys;
4. record model name, persona ID, prompt SHA-256, release ID, connector status, and UTC timestamp;
5. never record request headers or secrets.

The command contract is:

```python
@app.command(name="onyx-acceptance")
def onyx_acceptance(
    benchmark_path: Path,
    label: str = typer.Option(..., "--label"),
    prompt_path: Path = typer.Option(
        Path("docs/onyx-agent-instruction.md"), "--prompt-path"
    ),
    output_path: Path | None = typer.Option(None, "--output"),
    record_only: bool = typer.Option(False, "--record-only"),
) -> None:
    ...
```

It must fail before making a request when `onyx_persona_id`, `onyx_model_name`, `onyx_connector_id`, or a readable active release is absent.

- [ ] **Step 6: Add the initial checked-in case set**

`benchmarks/hierarchy-v1.json` contains these exact case IDs and message intents:

```json
[
  {
    "case_id": "law-87-controls-hierarchy",
    "messages": ["Theo pháp luật hiện hành, Điều 4 Luật Ban hành VBQPPL quy định hệ thống VBQPPL như thế nào?"],
    "expected_document_ids": ["vbpl:178717"],
    "expected_provision_keys": ["dieu-1/khoan-1"],
    "excluded_document_ids": []
  },
  {
    "case_id": "district-transition-context",
    "messages": [
      "Tôi đang xem quy định áp dụng tại Việt Nam vào tháng 7 năm 2026.",
      "Văn bản của HĐND và UBND cấp huyện trước khi sắp xếp còn hiệu lực không?"
    ],
    "expected_document_ids": ["vbpl:178717"],
    "expected_provision_keys": ["dieu-3/khoan-1"],
    "excluded_document_ids": []
  },
  {
    "case_id": "district-transition-expired",
    "messages": ["Đến ngày 01/03/2027, có thể mặc nhiên coi văn bản cấp huyện trước sắp xếp vẫn còn hiệu lực không?"],
    "expected_document_ids": ["vbpl:178717"],
    "expected_provision_keys": ["dieu-3"],
    "excluded_document_ids": []
  },
  {
    "case_id": "amendment-family",
    "messages": ["Luật 87/2025/QH15 sửa đổi văn bản nào và căn cứ pháp lý nào chứng minh quan hệ đó?"],
    "expected_document_ids": ["vbpl:178717", "vbpl:175440"],
    "expected_provision_keys": ["dieu-1"],
    "excluded_document_ids": []
  },
  {
    "case_id": "partial-effect-fail-closed",
    "messages": ["Có thể dựa vào toàn bộ Luật 64/2025/QH15 như pháp luật hiện hành mà không kiểm tra phần bị sửa đổi không?"],
    "expected_document_ids": ["vbpl:175440", "vbpl:178717"],
    "expected_provision_keys": [],
    "excluded_document_ids": []
  },
  {
    "case_id": "material-jurisdiction-clarification",
    "messages": ["Nghị quyết của địa phương này có áp dụng cho trường hợp của tôi không?"],
    "expected_document_ids": [],
    "expected_provision_keys": [],
    "excluded_document_ids": [],
    "expects_clarification": true
  }
]
```

- [ ] **Step 7: Verify, capture the current baseline, and commit**

Run:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_onyx_chat.py tests/test_acceptance.py tests/test_config.py tests/test_cli.py -q
uv run ruff check src/vbpl_kb/onyx_chat.py src/vbpl_kb/acceptance.py tests/test_onyx_chat.py tests/test_acceptance.py
uv run mypy src
uv run vbpl-kb onyx-acceptance benchmarks/hierarchy-v1.json --label baseline --record-only --output data/evaluations/hierarchy-baseline.json
```

Expected: tests, Ruff, and mypy pass. The live command reaches `/chat/send-chat-message`, writes a baseline record, and may record failed cases because it is intentionally pre-change. Confirm the JSON contains no bearer token, password, cookie, or API key.

```powershell
git add src/vbpl_kb/onyx_chat.py src/vbpl_kb/acceptance.py src/vbpl_kb/config.py src/vbpl_kb/cli.py tests/test_onyx_chat.py tests/test_acceptance.py tests/test_config.py tests/test_cli.py benchmarks/hierarchy-v1.json
git commit -m "test: capture direct Onyx hierarchy baseline"
```

---

### Task 2: Implement the versioned Article 4 authority classifier

**Files:**
- Create: `src/vbpl_kb/authority.py`, `tests/test_authority.py`
- Modify: `src/vbpl_kb/models.py`

**Interfaces:**
- Produces `AuthorityClassification` and `classify_authority(document_type, issuer)`.
- `article4_order` is `int | None`; `authority_group` is a stable slug; unknown and legacy states are explicit.

- [ ] **Step 1: Write a failing parametrized test for all 15 groups**

```python
@pytest.mark.parametrize(
    ("form", "issuer", "order", "group"),
    [
        ("Hiến pháp", "Quốc hội", 1, "constitution"),
        ("Luật", "Quốc hội", 2, "national_assembly_law"),
        ("Pháp lệnh", "Ủy ban Thường vụ Quốc hội", 3, "standing_committee"),
        ("Lệnh", "Chủ tịch nước", 4, "president"),
        ("Nghị định", "Chính phủ", 5, "government"),
        ("Quyết định", "Thủ tướng Chính phủ", 6, "prime_minister"),
        ("Nghị quyết", "Hội đồng Thẩm phán Tòa án nhân dân tối cao", 7, "supreme_court_council"),
        ("Thông tư", "Bộ trưởng Bộ Tư pháp", 8, "authorized_central_circular"),
        ("Thông tư liên tịch", "Bộ trưởng Bộ Tư pháp và Chánh án TANDTC", 9, "joint_circular"),
        ("Nghị quyết", "Hội đồng nhân dân tỉnh Bắc Ninh", 10, "provincial_council"),
        ("Quyết định", "Ủy ban nhân dân tỉnh Bắc Ninh", 11, "provincial_committee"),
        ("Quyết định", "Chủ tịch Ủy ban nhân dân tỉnh Bắc Ninh", 12, "provincial_chair"),
        ("Văn bản quy phạm pháp luật", "Chính quyền đặc khu Vân Đồn", 13, "special_zone"),
        ("Nghị quyết", "Hội đồng nhân dân phường Ba Đình", 14, "commune_council"),
        ("Quyết định", "Ủy ban nhân dân xã Minh Tân", 15, "commune_committee"),
    ],
)
def test_classifies_all_article_4_groups(form, issuer, order, group) -> None:
    result = classify_authority(form, issuer)
    assert result.article4_order == order
    assert result.authority_group == group
    assert result.classification_status == "known"
    assert result.hierarchy_regime == "vn-vbqppl-2025-07-01"
```

Also test:

```python
def test_structured_form_and_issuer_sensitive_decision() -> None:
    result = classify_authority(
        {"name": "Quyết định", "code": "QD", "parentCode": "VBQPPL"},
        "Chủ tịch Ủy ban nhân dân tỉnh Bắc Ninh",
    )
    assert result.article4_order == 12

def test_non_normative_parent_code_is_not_guessed_from_title() -> None:
    result = classify_authority(
        {"name": "Công văn", "code": "CV", "parentCode": "VBHC"},
        "Bộ Tư pháp",
    )
    assert result.classification_status == "not_normative"
    assert result.is_normative is False

def test_legacy_district_is_explicit() -> None:
    result = classify_authority("Quyết định", "Ủy ban nhân dân huyện Đông Anh")
    assert result.classification_status == "legacy_transitional"
    assert result.article4_order is None
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
uv run pytest tests/test_authority.py -q
```

Expected: FAIL because `vbpl_kb.authority` does not exist.

- [ ] **Step 3: Add the immutable model and rule table**

```python
class AuthorityClassification(BaseModel):
    model_config = ConfigDict(frozen=True)
    hierarchy_regime: str
    article4_order: int | None
    normative_form: str
    authority_group: str
    issuer_type: str
    classification_status: Literal[
        "known", "unknown", "not_normative", "legacy_transitional"
    ]
    classification_source: str
    classification_version: str
    is_normative: bool
```

In `authority.py`, use:

```python
HIERARCHY_REGIME = "vn-vbqppl-2025-07-01"
CLASSIFICATION_VERSION = "article4-87-2025-v1"

ARTICLE4_RULES = (
    AuthorityRule(1, "constitution", ("hien phap",), ("quoc hoi",)),
    AuthorityRule(2, "national_assembly_law", ("bo luat", "luat", "nghi quyet"), ("quoc hoi",)),
    AuthorityRule(3, "standing_committee", ("phap lenh", "nghi quyet", "nghi quyet lien tich"), ("uy ban thuong vu quoc hoi",)),
    AuthorityRule(4, "president", ("lenh", "quyet dinh"), ("chu tich nuoc",)),
    AuthorityRule(5, "government", ("nghi dinh", "nghi quyet", "nghi quyet lien tich"), ("chinh phu",)),
    AuthorityRule(6, "prime_minister", ("quyet dinh",), ("thu tuong chinh phu",)),
    AuthorityRule(7, "supreme_court_council", ("nghi quyet",), ("hoi dong tham phan toa an nhan dan toi cao",)),
    AuthorityRule(8, "authorized_central_circular", ("thong tu",), ("chanh an toa an nhan dan toi cao", "vien truong vien kiem sat nhan dan toi cao", "bo truong", "thu truong co quan ngang bo", "tong kiem toan nha nuoc")),
    AuthorityRule(9, "joint_circular", ("thong tu lien tich",), ("chanh an", "vien truong", "tong kiem toan", "bo truong", "thu truong co quan ngang bo"), match_any_two_issuers=True),
    AuthorityRule(10, "provincial_council", ("nghi quyet",), ("hoi dong nhan dan tinh", "hoi dong nhan dan thanh pho")),
    AuthorityRule(11, "provincial_committee", ("quyet dinh",), ("uy ban nhan dan tinh", "uy ban nhan dan thanh pho")),
    AuthorityRule(12, "provincial_chair", ("quyet dinh",), ("chu tich uy ban nhan dan tinh", "chu tich uy ban nhan dan thanh pho")),
    AuthorityRule(13, "special_zone", ("van ban quy pham phap luat",), ("chinh quyen dac khu", "don vi hanh chinh kinh te dac biet")),
    AuthorityRule(14, "commune_council", ("nghi quyet",), ("hoi dong nhan dan xa", "hoi dong nhan dan phuong", "hoi dong nhan dan dac khu")),
    AuthorityRule(15, "commune_committee", ("quyet dinh",), ("uy ban nhan dan xa", "uy ban nhan dan phuong", "uy ban nhan dan dac khu")),
)
```

Normalize Vietnamese accents, whitespace, punctuation, and structured `name`/`code`/`parentCode`. Evaluate the most issuer-specific rules first so `Chủ tịch UBND tỉnh` does not match `UBND tỉnh`. If official form and issuer conflict with the title, return the classification derived from official fields and do not parse the title as a fallback.

- [ ] **Step 4: Verify and commit**

Run:

```powershell
uv run pytest tests/test_authority.py -q
uv run ruff check src/vbpl_kb/authority.py tests/test_authority.py
uv run mypy src
```

Expected: all commands pass.

```powershell
git add src/vbpl_kb/authority.py src/vbpl_kb/models.py tests/test_authority.py
git commit -m "feat: classify VBPL Article 4 authority"
```

---

### Task 3: Build applicability envelopes and deterministic provision sections

**Files:**
- Create: `src/vbpl_kb/applicability.py`, `src/vbpl_kb/provisions.py`
- Create: `tests/test_applicability.py`, `tests/test_provisions.py`
- Modify: `src/vbpl_kb/models.py`, `src/vbpl_kb/normalize.py`, `tests/test_normalize.py`

**Interfaces:**
- Consumes `AuthorityClassification`, raw VBPL detail, `StatusObservation`, and plain legal text.
- Produces `ApplicabilityEnvelope`, ordered `Provision` objects, and schema-v2 `OnyxSection` values.

- [ ] **Step 1: Write failing applicability tests**

```python
def test_national_law_carries_status_evidence_and_effective_range(status) -> None:
    envelope = build_applicability(
        {
            "effFrom": "2025-07-01T00:00:00",
            "effTo": None,
            "agencyName": "Quốc hội",
        },
        status,
        AuthorityClassification(
            hierarchy_regime="vn-vbqppl-2025-07-01",
            article4_order=2,
            normative_form="luat",
            authority_group="national_assembly_law",
            issuer_type="quoc_hoi",
            classification_status="known",
            classification_source="official_form+issuer",
            classification_version="article4-87-2025-v1",
            is_normative=True,
        ),
        "vbpl-2026-07-24",
    )
    assert envelope.jurisdiction_level == "national"
    assert envelope.effective_from == "2025-07-01T00:00:00"
    assert envelope.status_evidence_hash == status.content_hash

def test_legacy_district_transition_has_hard_end(status) -> None:
    authority = classify_authority("Quyết định", "Ủy ban nhân dân huyện Đông Anh")
    envelope = build_applicability(
        {"agencyName": "Ủy ban nhân dân huyện Đông Anh"},
        status,
        authority,
        "vbpl-2026-07-24",
    )
    assert envelope.jurisdiction_level == "legacy_district"
    assert envelope.transitional_until == "2027-02-28T23:59:59+07:00"
```

- [ ] **Step 2: Write failing provision and isolated-header tests**

```python
def test_split_provisions_is_ordered_and_preserves_nested_amended_text() -> None:
    sections = split_provisions(
        "Điều 1. Sửa đổi\n"
        "1. Sửa đổi Điều 4 như sau:\n"
        "“Điều 4. Hệ thống văn bản\n"
        "1. Hiến pháp.\n"
        "2. Bộ luật, luật.\n"
        "Điều 2. Thi hành\n"
        "Nội dung."
    )
    assert [section.provision_key for section in sections] == [
        "dieu-1",
        "dieu-1/khoan-1",
        "dieu-1/khoan-1/noi-dung-sua-doi/dieu-4",
        "dieu-1/khoan-1/noi-dung-sua-doi/dieu-4/khoan-1",
        "dieu-1/khoan-1/noi-dung-sua-doi/dieu-4/khoan-2",
        "dieu-2",
    ]

def test_each_retrievable_section_repeats_compact_legal_context(status) -> None:
    doc = normalize_instrument(
        {
            "id": "178717",
            "docType": {"name": "Luật", "parentCode": "VBQPPL"},
            "docNum": "87/2025/QH15",
            "title": "Luật 87/2025/QH15",
            "agencyName": "Quốc hội",
            "fullText": "Điều 1. Nội dung\n1. Khoản một.",
            "effFrom": "2025-07-01T00:00:00",
        },
        status,
        "vbpl-2026-07-24",
    )
    assert doc.projection_schema_version == 2
    assert doc.sections[1].section_id == "dieu-1/khoan-1"
    assert "Văn bản: Luật 87/2025/QH15" in doc.sections[1].text
    assert "Thẩm quyền Điều 4: 2" in doc.sections[1].text
    assert f"Xác minh: {status.checked_at.isoformat()}" in doc.sections[1].text
```

- [ ] **Step 3: Run and verify failures**

Run:

```powershell
uv run pytest tests/test_applicability.py tests/test_provisions.py tests/test_normalize.py -q
```

Expected: FAIL because applicability, provision, and multi-section models are absent.

- [ ] **Step 4: Add the envelope and section models**

```python
class ApplicabilityEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)
    legal_status_raw: str
    legal_status_normalized: str
    verified_at: str
    status_source: str
    effective_from: str
    effective_to: str
    jurisdiction_level: Literal[
        "national", "province", "commune", "special_zone",
        "legacy_district", "unknown"
    ]
    jurisdiction_code: str
    jurisdiction_name: str
    transitional_until: str
    source_url: str
    corpus_revision: str
    status_evidence_hash: str


class Provision(BaseModel):
    model_config = ConfigDict(frozen=True)
    provision_key: str
    article_number: str
    clause_number: str
    point_label: str
    provision_heading: str
    citation_structure: Literal["parsed", "unparsed"]
    text: str


class OnyxSection(BaseModel):
    model_config = ConfigDict(frozen=True)
    section_id: str
    text: str
    link: str
```

`build_applicability` uses `status.checked_at` as the sole verification clock input, `status.content_hash` as `status_evidence_hash`, `raw["effTo"]` when present, national jurisdiction for groups 1-9, issuer-derived province/commune/special-zone names for groups 10-15, and the fixed district transition end only for `legacy_transitional`.

- [ ] **Step 5: Implement deterministic splitting and compact headers**

The parser must:

- strip HTML before parsing;
- recognize `Điều`, numbered clauses, and lettered points;
- treat quoted `“Điều ...` under an amending clause as `noi-dung-sua-doi`;
- preserve preamble as `mo-dau` when it has substantive text;
- emit one `toan-van` section with `citation_structure=unparsed` when no article is found;
- disambiguate repeated keys deterministically with `~2`, `~3`, never a random ID.

Use this header formatter:

```python
def render_context_header(
    *,
    title: str,
    document_number: str,
    provision: Provision,
    authority: AuthorityClassification,
    applicability: ApplicabilityEnvelope,
    relation_tokens: tuple[str, ...],
) -> str:
    order = (
        str(authority.article4_order)
        if authority.article4_order is not None
        else "unknown"
    )
    relations = ", ".join(relation_tokens) if relation_tokens else "none"
    return "\n".join((
        f"Văn bản: {title}",
        f"Số hiệu: {document_number}",
        f"Vị trí: {provision.provision_key}",
        f"Hình thức: {authority.normative_form}",
        f"Cơ quan: {authority.issuer_type}",
        f"Thẩm quyền Điều 4: {order}",
        f"Trạng thái: {applicability.legal_status_normalized}",
        f"Xác minh: {applicability.verified_at}",
        f"Hiệu lực: {applicability.effective_from} -> {applicability.effective_to}",
        f"Phạm vi: {applicability.jurisdiction_level}:{applicability.jurisdiction_name}",
        f"Quan hệ đã xác minh: {relations}",
    ))
```

Keep metadata values as short strings or lists of short strings. Do not put raw HTML, raw reference payloads, or long evidence quotes in metadata/header text.

- [ ] **Step 6: Verify and commit**

Run:

```powershell
uv run pytest tests/test_applicability.py tests/test_provisions.py tests/test_normalize.py -q
uv run ruff check src/vbpl_kb/applicability.py src/vbpl_kb/provisions.py src/vbpl_kb/normalize.py
uv run mypy src
```

Expected: all commands pass.

```powershell
git add src/vbpl_kb/applicability.py src/vbpl_kb/provisions.py src/vbpl_kb/models.py src/vbpl_kb/normalize.py tests/test_applicability.py tests/test_provisions.py tests/test_normalize.py
git commit -m "feat: project VBPL applicability and provisions"
```

---

### Task 4: Replace guessed relationships with a verified, revisioned graph

**Files:**
- Modify: `src/vbpl_kb/models.py`, `src/vbpl_kb/references.py`, `src/vbpl_kb/state.py`
- Modify: `tests/test_references.py`, `tests/test_state.py`
- Create: `tests/fixtures/vbpl/references-178717.json`

**Interfaces:**
- Produces evidence-bearing `LegalReference` records and compact `relation_tokens`.
- Verified numeric mapping v1 contains only `3 -> legal_basis` and `10 -> amends`, grounded in the official 178717 API payload plus the official related-documents page labeling 175440 as `Văn bản bị sửa đổi`.

- [ ] **Step 1: Write failing relationship safety tests**

```python
def test_verified_structured_codes_keep_evidence_and_deduplicate() -> None:
    edges = normalize_relationships(
        from_vbpl_id="178717",
        structured=[
            {"id": "a", "referenceType": 3, "targetDocument": {"id": "32801", "docNum": "Không số"}},
            {"id": "b", "referenceType": 10, "targetDocument": {"id": "175440", "docNum": "64/2025/QH15"}},
            {"id": "c", "referenceType": 10, "targetDocument": {"id": "175440", "docNum": "64/2025/QH15"}},
        ],
        candidates=[],
        instrument_index={},
        corpus_revision="run-1",
    )
    assert [(edge.relation_type, edge.to_vbpl_id) for edge in edges] == [
        ("legal_basis", "32801"),
        ("amends", "175440"),
    ]
    assert all(edge.evidence_kind == "official_structured" for edge in edges)
    assert all(len(edge.evidence_hash) == 64 for edge in edges)

def test_unmapped_structured_code_remains_unknown() -> None:
    edge = normalize_relationships(
        "A",
        [{"referenceType": 999, "targetDocument": {"id": "B", "docNum": "B/2026"}}],
        [],
        {},
        "run-1",
    )[0]
    assert edge.relation_type == "unknown"
    assert edge.resolution_state == "unmapped"

def test_text_amendment_verb_is_candidate_not_legal_effect() -> None:
    candidate = extract_references("A", "dieu-1", "Sửa đổi Luật số 64/2025/QH15.")[0]
    edge = normalize_relationships(
        "A", [], [candidate], {"luat:64/2025/qh15": "B"}, "run-1"
    )[0]
    assert edge.relation_type == "unknown"
    assert edge.evidence_kind == "text_candidate"
    assert edge.resolution_state == "candidate"
    assert relationship_tokens((edge,)) == ()

def test_heuristic_self_edge_is_not_searchable() -> None:
    candidate = extract_references("178717", "dieu-1", "Luật số 87/2025/QH15.")[0]
    edge = normalize_relationships(
        "178717", [], [candidate], {"luat:87/2025/qh15": "178717"}, "run-1"
    )[0]
    assert edge.searchable is False
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
uv run pytest tests/test_references.py tests/test_state.py -q
```

Expected: FAIL because evidence fields and safe normalization do not exist.

- [ ] **Step 3: Expand the relationship model and verified mapping**

Retain this minimal official fixture rather than the full 20,000-character document body:

```json
{
  "source_id": "178717",
  "api_url": "https://vbpl-bientap-gateway.moj.gov.vn/api/qtdc/public/doc/178717",
  "canonical_relationship_url": "https://vbpl.vn/TW/Pages/vbpq-vanbanlienquan.aspx?ItemID=178717",
  "references": [
    {
      "referenceType": 3,
      "targetDocument": {"id": "32801", "docNum": "Không số"},
      "canonical_label": "Văn bản căn cứ"
    },
    {
      "referenceType": 10,
      "targetDocument": {"id": "175440", "docNum": "64/2025/QH15"},
      "canonical_label": "Văn bản bị sửa đổi"
    }
  ]
}
```

```python
class LegalReference(BaseModel):
    model_config = ConfigDict(frozen=True)
    from_vbpl_id: str
    from_provision_key: str
    to_vbpl_id: str | None
    to_provision_key: str | None
    relation_type: Literal[
        "cites", "legal_basis", "details", "implements", "delegated_by",
        "amends", "supplements", "replaces", "repeals", "suspends",
        "continues_effect", "unknown"
    ]
    evidence_kind: Literal["official_structured", "official_page", "text_candidate"]
    evidence_reference: str
    source_quote: str
    source_offset: int | None
    resolution_state: Literal["verified", "resolved_citation", "candidate", "unmapped", "unresolved"]
    evidence_hash: str
    corpus_revision: str
    searchable: bool
```

Use this exact initial numeric mapping:

```python
VERIFIED_REFERENCE_TYPES = {
    3: VerifiedReferenceType(
        relation_type="legal_basis",
        evidence_url="https://vbpl.vn/TW/Pages/vbpq-vanbanlienquan.aspx?ItemID=178717",
        evidence_label="Văn bản căn cứ",
        example_source_id="178717",
        example_target_id="32801",
    ),
    10: VerifiedReferenceType(
        relation_type="amends",
        evidence_url="https://vbpl.vn/TW/Pages/vbpq-vanbanlienquan.aspx?ItemID=178717",
        evidence_label="Văn bản bị sửa đổi",
        example_source_id="178717",
        example_target_id="175440",
    ),
}
```

Do not add another code unless its official payload and canonical-page category are retained in a focused fixture/test.

- [ ] **Step 4: Implement normalization, deduplication, and tokens**

`normalize_relationships` sorts structured references by their stable payload representation, then text candidates. Deduplicate by:

```python
(
    edge.from_vbpl_id,
    edge.from_provision_key,
    edge.to_vbpl_id,
    edge.to_provision_key,
    edge.relation_type,
    edge.evidence_kind,
)
```

`relationship_tokens` returns only verified, searchable edges with resolved targets:

```python
def relationship_tokens(references: tuple[LegalReference, ...]) -> tuple[str, ...]:
    tokens = {
        f"{edge.relation_type}:{edge.to_vbpl_id}"
        for edge in references
        if edge.searchable
        and edge.to_vbpl_id is not None
        and edge.resolution_state in {"verified", "resolved_citation"}
        and edge.relation_type != "unknown"
    }
    return tuple(sorted(tokens))
```

- [ ] **Step 5: Migrate SQLite without dropping existing evidence**

Add columns with idempotent `PRAGMA table_info` checks:

```text
evidence_kind TEXT NOT NULL DEFAULT 'text_candidate'
evidence_reference TEXT NOT NULL DEFAULT ''
source_offset INTEGER
resolution_state TEXT NOT NULL DEFAULT 'unresolved'
evidence_hash TEXT NOT NULL DEFAULT ''
corpus_revision TEXT NOT NULL DEFAULT ''
searchable INTEGER NOT NULL DEFAULT 0
```

Update `record_reference` to persist every field and deduplicate within `run_id`. Existing rows remain intact and default to non-searchable rather than acquiring guessed legal meaning.

- [ ] **Step 6: Verify and commit**

Run:

```powershell
uv run pytest tests/test_references.py tests/test_state.py -q
uv run ruff check src/vbpl_kb/references.py src/vbpl_kb/state.py
uv run mypy src
```

Expected: all commands pass.

```powershell
git add src/vbpl_kb/models.py src/vbpl_kb/references.py src/vbpl_kb/state.py tests/test_references.py tests/test_state.py
git commit -m "feat: verify VBPL legal relationships"
```

---

### Task 5: Produce and validate immutable schema-v2 releases

**Files:**
- Modify: `src/vbpl_kb/models.py`, `src/vbpl_kb/normalize.py`, `src/vbpl_kb/publish.py`, `src/vbpl_kb/releases.py`, `src/vbpl_kb/cli.py`
- Modify: `tests/test_normalize.py`, `tests/test_publish.py`, `tests/test_releases.py`, `tests/test_cli.py`

**Interfaces:**
- New projections always serialize `projection_schema_version: 2`.
- `OnyxDocument.sections` is ordered and non-empty; `OnyxDocument.content` remains a read-only joined compatibility property for the diagnostic legacy publisher.
- Adds CLI commands `export-candidate`, `validate-release`, `promote-release`, and `reindex-connector`.

- [ ] **Step 1: Write failing schema-v2 and prior-pointer tests**

```python
def test_candidate_contains_ordered_schema_v2_sections(tmp_path, store) -> None:
    exporter = ReleaseExporter(store, tmp_path / "exports")
    manifest = exporter.write_candidate("good")
    payload = json.loads(
        (manifest.manifest_path.parent / manifest.documents[0]["relative_path"])
        .read_text(encoding="utf-8")
    )
    assert payload["projection_schema_version"] == 2
    assert payload["document_id"] == "vbpl:123"
    assert payload["sections"][0]["section_id"] == "dieu-1"
    assert payload["sections"][0]["link"].startswith("https://vbpl.vn/")
    assert manifest.section_count >= manifest.document_count

def test_unsupported_projection_blocks_promotion_and_keeps_pointer(tmp_path, store) -> None:
    exporter = ReleaseExporter(store, tmp_path / "exports")
    prior = exporter.promote(exporter.write_candidate("good"))
    bad = make_manifest_with_projection_version(tmp_path, version=3)
    with pytest.raises(ReleaseBlocked, match="Unsupported projection schema"):
        exporter.promote(bad)
    assert exporter.read_active() == prior

def test_existing_candidate_is_revalidated_not_accepted_by_count_only(tmp_path, store) -> None:
    exporter = ReleaseExporter(store, tmp_path / "exports")
    manifest = exporter.write_candidate("good")
    document = manifest.manifest_path.parent / manifest.documents[0]["relative_path"]
    document.write_text("{}", encoding="utf-8")
    with pytest.raises(ReleaseBlocked, match="checksum"):
        exporter.write_candidate("good")
```

- [ ] **Step 2: Run and verify failures**

Run:

```powershell
uv run pytest tests/test_normalize.py tests/test_publish.py tests/test_releases.py tests/test_cli.py -q
```

Expected: FAIL on missing schema-v2 serialization and staged CLI commands.

- [ ] **Step 3: Finalize the schema-v2 projection model**

```python
class OnyxDocument(BaseModel):
    model_config = ConfigDict(frozen=True)
    projection_schema_version: Literal[2] = 2
    document_id: str
    sections: tuple[OnyxSection, ...]
    link: str
    metadata: dict[str, str | list[str]]

    @property
    def content(self) -> str:
        return "\n\n".join(section.text for section in self.sections)
```

`normalize_instrument` metadata includes exactly these hierarchy/applicability keys plus existing title/number fields:

```text
hierarchy_regime, article4_order, normative_form, authority_group,
issuer_type, classification_status, classification_source,
classification_version, is_normative, legal_status_raw,
legal_status_normalized, verified_at, status_source, effective_from,
effective_to, jurisdiction_level, jurisdiction_code, jurisdiction_name,
transitional_until, source_url, corpus_revision, status_evidence_hash,
citation_structure, document_number, title, relation_tokens
```

- [ ] **Step 4: Serialize and prevalidate releases**

Each document JSON has:

```python
doc_payload = {
    "projection_schema_version": final_doc.projection_schema_version,
    "document_id": final_doc.document_id,
    "sections": [section.model_dump() for section in final_doc.sections],
    "link": final_doc.link,
    "metadata": final_doc.metadata,
}
```

Each manifest has `projection_schema_version`, `document_count`, and `section_count`. `validate_candidate` checks all manifest/document checksums, path containment under the release directory, stable ID format, version exactly 2, non-empty ordered sections, unique section IDs within a document, non-empty text/link, and scalar/list-of-string metadata before pointer replacement.

Remove the current count-only candidate resume shortcut. A pre-existing candidate may be reused only after full manifest and document validation.

- [ ] **Step 5: Add staged CLI commands and rollback-capable loading**

The commands use `Settings.export_dir` and never trigger one another implicitly:

```text
export-candidate --revision <run-id>
validate-release --revision <run-id>
promote-release --revision <run-id>
reindex-connector --from-beginning
```

`promote-release` calls `load_manifest(revision)`, `validate_candidate`, then `promote`. `reindex-connector` requires `onyx_connector_id`, calls `trigger(..., from_beginning=True)`, and waits for the exact returned attempt to finish.

- [ ] **Step 6: Verify and commit**

Run:

```powershell
uv run pytest tests/test_normalize.py tests/test_publish.py tests/test_releases.py tests/test_cli.py -q
uv run ruff check src/vbpl_kb/normalize.py src/vbpl_kb/publish.py src/vbpl_kb/releases.py src/vbpl_kb/cli.py
uv run mypy src
```

Expected: all commands pass.

```powershell
git add src/vbpl_kb/models.py src/vbpl_kb/normalize.py src/vbpl_kb/publish.py src/vbpl_kb/releases.py src/vbpl_kb/cli.py tests/test_normalize.py tests/test_publish.py tests/test_releases.py tests/test_cli.py
git commit -m "feat: publish provision-aware VBPL releases"
```

---

### Task 6: Make the pinned Onyx connector backward compatible with schema v2

**Files:**
- Modify: `infra/onyx/overlay/backend/onyx/connectors/vbpl_export/connector.py`
- Create: `tests/test_vbpl_export_connector.py`
- Modify: `tests/test_release_deployment.py`

**Interfaces:**
- Missing version reads legacy `content` as one `TextSection`.
- Version 2 reads every ordered export section as `TextSection(text=..., link=..., heading=section_id)`.
- Any other version raises `VBPLExportConnectorError` before the connector yields a document.

- [ ] **Step 1: Write failing executable connector tests**

Use stub modules for `onyx.connectors.interfaces`, `onyx.connectors.models`, `onyx.configs.app_configs`, then load the overlay with `importlib.util.spec_from_file_location`.

```python
def test_connector_reads_legacy_missing_version_as_one_section(connector_factory) -> None:
    connector = connector_factory({
        "document_id": "vbpl:1",
        "content": "legacy",
        "link": "https://vbpl.vn/1",
        "metadata": {"title": "Legacy"},
    })
    document = list(connector.load_from_state())[0][0]
    assert [section.text for section in document.sections] == ["legacy"]

def test_connector_reads_ordered_schema_v2_sections(connector_factory) -> None:
    connector = connector_factory({
        "projection_schema_version": 2,
        "document_id": "vbpl:1",
        "sections": [
            {"section_id": "dieu-1", "text": "Điều 1", "link": "https://vbpl.vn/1"},
            {"section_id": "dieu-2", "text": "Điều 2", "link": "https://vbpl.vn/1"},
        ],
        "link": "https://vbpl.vn/1",
        "metadata": {"title": "Schema v2"},
    })
    document = list(connector.load_from_state())[0][0]
    assert [section.heading for section in document.sections] == ["dieu-1", "dieu-2"]
    assert all(section.link == "https://vbpl.vn/1" for section in document.sections)

def test_connector_rejects_unsupported_version_before_yield(connector_factory) -> None:
    connector = connector_factory({
        "projection_schema_version": 3,
        "document_id": "vbpl:1",
        "sections": [],
        "metadata": {"title": "Bad"},
    })
    with pytest.raises(VBPLExportConnectorError, match="Unsupported projection schema"):
        list(connector.load_from_state())

def test_connector_sanitizes_oversized_metadata_without_losing_relation_tokens(
    connector_factory,
) -> None:
    connector = connector_factory({
        "projection_schema_version": 2,
        "document_id": "vbpl:1",
        "sections": [{"section_id": "dieu-1", "text": "Điều 1", "link": "https://vbpl.vn/1"}],
        "link": "https://vbpl.vn/1",
        "metadata": {
            "title": "X" * 300,
            "relation_tokens": ["amends:175440"],
        },
    })
    document = list(connector.load_from_state())[0][0]
    assert len(document.metadata["title"]) <= 243
    assert document.metadata["relation_tokens"] == ["amends:175440"]
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
uv run pytest tests/test_vbpl_export_connector.py tests/test_release_deployment.py -q
```

Expected: legacy passes or nearly passes; schema v2 and unsupported-version tests fail.

- [ ] **Step 3: Prevalidate the active release and map sections**

Add:

```python
def _projection_version(raw_doc: dict[str, Any]) -> int:
    value = raw_doc.get("projection_schema_version")
    if value is None:
        return 1
    if type(value) is not int:
        raise VBPLExportConnectorError("projection_schema_version must be an integer")
    if value not in (1, 2):
        raise VBPLExportConnectorError(
            f"Unsupported projection schema version: {value}"
        )
    return value


def _text_sections(raw_doc: dict[str, Any]) -> list[TextSection]:
    version = _projection_version(raw_doc)
    if version == 1:
        content = raw_doc.get("content")
        if not isinstance(content, str) or not content.strip():
            raise VBPLExportConnectorError("Schema-v1 content is empty")
        return [TextSection(text=content, link=raw_doc.get("link"))]
    raw_sections = raw_doc.get("sections")
    if not isinstance(raw_sections, list) or not raw_sections:
        raise VBPLExportConnectorError("Schema-v2 sections must be non-empty")
    sections: list[TextSection] = []
    seen: set[str] = set()
    for raw_section in raw_sections:
        section_id = raw_section.get("section_id")
        text = raw_section.get("text")
        link = raw_section.get("link")
        if not all(isinstance(value, str) and value for value in (section_id, text, link)):
            raise VBPLExportConnectorError("Invalid schema-v2 section")
        if section_id in seen:
            raise VBPLExportConnectorError(f"Duplicate section_id: {section_id}")
        seen.add(section_id)
        sections.append(TextSection(text=text, link=link, heading=section_id))
    return sections
```

Before yielding the first batch, make one validation pass over all manifest paths/checksums and projection versions. The second pass constructs documents and batches them. This prevents an unsupported document late in the manifest from causing a partial mixed-schema run.

- [ ] **Step 4: Verify the overlay and pinned checkout**

Run:

```powershell
uv run pytest tests/test_vbpl_export_connector.py tests/test_release_deployment.py -q
git -C .onyx/onyx rev-parse HEAD
git -C .onyx/onyx apply --check ../../infra/onyx/patches/vbpl-export-connector.patch
```

Expected: tests pass; HEAD equals `infra/onyx/onyx.lock.json`; patch check exits 0. The registration patch should remain unchanged unless the pinned Onyx registration surface has changed.

- [ ] **Step 5: Commit**

```powershell
git add infra/onyx/overlay/backend/onyx/connectors/vbpl_export/connector.py tests/test_vbpl_export_connector.py tests/test_release_deployment.py
git commit -m "feat: index schema-v2 VBPL sections in Onyx"
```

---

### Task 7: Add authority-bundle evaluation and connector observability

**Files:**
- Modify: `src/vbpl_kb/evaluate.py`, `src/vbpl_kb/acceptance.py`, `src/vbpl_kb/connector_control.py`
- Modify: `tests/test_evaluate.py`, `tests/test_acceptance.py`, `tests/test_connector_control.py`
- Modify: `benchmarks/hierarchy-v1.json`

**Interfaces:**
- `OnyxConnectorClient.get_status(connector_id) -> ConnectorStatus`.
- `wait_for_indexed(...) -> ConnectorStatus`.
- `evaluate_authority_bundles` emits safety failures, conflict accuracy, unresolved accuracy, controlling recall@10, bundle completeness@10, and chunk-count ratio.

- [ ] **Step 1: Write failing metric tests**

```python
def test_bundle_metrics_enforce_all_design_gates() -> None:
    report = evaluate_authority_bundles(
        cases=[{
            "case_id": "bundle",
            "expected_document_ids": ["vbpl:law", "vbpl:decree"],
            "expected_controlling_id": "vbpl:law",
            "expected_conflict_outcome": "resolved",
        }],
        results=[{
            "case_id": "bundle",
            "document_ids": ["vbpl:law", "vbpl:decree"],
            "current_law_safe": True,
            "conflict_outcome": "resolved",
        }],
        baseline_chunk_count=100,
        candidate_chunk_count=120,
    )
    assert report.metrics["controlling_provision_recall_at_10"] == 1.0
    assert report.metrics["authority_bundle_completeness_at_10"] == 1.0
    assert report.metrics["chunk_count_ratio"] == 1.2
    assert report.passed is True

def test_chunk_growth_over_125_percent_blocks_acceptance() -> None:
    report = evaluate_authority_bundles(
        cases=[], results=[], baseline_chunk_count=100, candidate_chunk_count=126
    )
    assert report.passed is False
```

- [ ] **Step 2: Write the failing connector status test**

```python
@respx.mock
def test_wait_returns_matching_completed_attempt_with_chunk_total() -> None:
    respx.post("http://onyx:8080/manage/admin/connector/indexing-status").mock(
        return_value=httpx.Response(200, json={"statuses": [{
            "connector_id": 7,
            "last_status": "success",
            "in_progress": False,
            "total_chunks": 120,
            "attempt_id": 41,
        }]})
    )
    status = OnyxConnectorClient(
        Settings(onyx_base_url="http://onyx:8080")
    ).wait_for_indexed(7, timeout_seconds=1)
    assert status.attempt_id == 41
    assert status.total_chunks == 120
```

- [ ] **Step 3: Implement gates and status parsing**

The report passes only when:

```python
passed = (
    safety_failures == 0
    and conflict_accuracy == 1.0
    and unresolved_accuracy == 1.0
    and controlling_recall_at_10 >= 0.95
    and bundle_completeness_at_10 >= 0.90
    and chunk_count_ratio <= 1.25
)
```

When a case category has zero examples, its accuracy is `1.0`; when a chunk baseline is missing, the report is incomplete and fails rather than silently assuming a ratio. `ConnectorStatus` retains only non-secret scalar status fields plus a sanitized raw payload.

- [ ] **Step 4: Verify and commit**

Run:

```powershell
uv run pytest tests/test_evaluate.py tests/test_acceptance.py tests/test_connector_control.py -q
uv run ruff check src/vbpl_kb/evaluate.py src/vbpl_kb/acceptance.py src/vbpl_kb/connector_control.py
uv run mypy src
```

Expected: all commands pass.

```powershell
git add src/vbpl_kb/evaluate.py src/vbpl_kb/acceptance.py src/vbpl_kb/connector_control.py tests/test_evaluate.py tests/test_acceptance.py tests/test_connector_control.py benchmarks/hierarchy-v1.json
git commit -m "test: gate hierarchy-aware authority bundles"
```

---

### Task 8: Update the canonical agent instruction and current documentation

**Files:**
- Modify: `docs/onyx-agent-instruction.md`, `docs/onyx-agent-setup.md`
- Modify: `docs/architecture.md`, `docs/legal-data-policy.md`, `docs/operations.md`
- Modify: `AGENTS.md`, `README.md`, `tests/test_documentation.py`

**Interfaces:**
- `docs/onyx-agent-instruction.md` is the only canonical runtime prompt for this feature.
- `AGENTS.md` remains a thin coding-agent router and does not duplicate the 15 groups or runtime prompt.

- [ ] **Step 1: Write failing documentation and prompt contract tests**

```python
def test_canonical_agent_instruction_requires_staged_authority_bundle_search() -> None:
    text = (ROOT / "docs/onyx-agent-instruction.md").read_text(encoding="utf-8")
    required = (
        "24 giờ",
        "xác định tọa độ pháp lý",
        "truy xuất quy định điều chỉnh trực tiếp",
        "mở rộng authority bundle",
        "relation_tokens",
        "cùng một cơ quan ban hành",
        "01/07/2025",
        "28/02/2027",
        "Không tìm thấy căn cứ VBPL đã được xác minh để trả lời câu hỏi này.",
    )
    for phrase in required:
        assert phrase in text
    assert "Hiến pháp > Luật > Nghị định > Thông tư" not in text
    assert "Lex Specialis" not in text

def test_current_docs_route_hierarchy_work_without_historical_links() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "hierarchy" in agents.casefold()
    assert "docs/legal-data-policy.md" in agents
    assert "docs/architecture.md" in agents
    assert "docs/superpowers/specs/" not in agents
    assert "docs/superpowers/plans/" not in agents
```

- [ ] **Step 2: Run and verify failure**

Run:

```powershell
uv run pytest tests/test_documentation.py -q
```

Expected: FAIL because the current prompt still contains the simplified four-level ladder and generic Lex Specialis rule.

- [ ] **Step 3: Replace the canonical prompt**

The prompt must direct the agent to:

1. use only the assigned VBPL document set and Internal Search;
2. infer subject, conduct, requested consequence, event time, jurisdiction, and current/historical intent from the request and conversation;
3. ask one focused question only when a missing fact could materially change the result;
4. retrieve the controlling provision first;
5. reject stale, missing, conflicting, non-applicable, or insufficiently granular evidence for current-law conclusions;
6. expand with instrument number, provision key, and verified `relation_tokens`;
7. include applicable implementation/local detail instead of suppressing subordinate instruments;
8. apply higher legal effect only after scope applicability;
9. use the later rule only for different rules from the same issuing authority;
10. apply treaty precedence except against the Constitution and respect explicit National Assembly exceptions;
11. never apply a generic automatic `lex specialis` override;
12. preserve unresolved conflicts;
13. avoid the 2025 hierarchy for pre-1 July 2025 conflict resolution;
14. enforce the district transition no later than 28 February 2027;
15. allow an earlier end to district or implementing-instrument continuation only when verified replacement, cessation, or continuation evidence establishes it;
16. refuse to treat a partially effective instrument as proof that a specific provision remains effective without provision-level evidence;
17. cite number/title, article/clause/point, issuer, effective date, status, `verified_at`, and official URL;
18. use the exact refusal sentence when verified support is absent.

- [ ] **Step 4: Update current docs after behavior is settled**

- `docs/architecture.md`: schema-v2 projection, authority/applicability modules, verified graph, v1/v2 connector, stock Onyx staged retrieval.
- `docs/legal-data-policy.md`: code 3/10 evidence mapping, unknown-code policy, text-candidate restriction, 24-hour/current-law and transition rules.
- `docs/operations.md`: baseline, candidate validation, connector rebuild before promotion, full re-index, direct Chat acceptance, exact rollback, prohibited deletion.
- `docs/onyx-agent-setup.md`: copy only `docs/onyx-agent-instruction.md`, assign the VBPL document set and Internal Search, record persona/model IDs, apply/restore prompt through Onyx administration.
- `README.md`: concise current workflow and links to the canonical docs.
- `AGENTS.md`: route hierarchy/applicability/relation/projection changes to architecture, legal policy, development workflow, and focused tests; do not embed runtime instructions.

- [ ] **Step 5: Run the full offline verification gate and commit**

Run:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest -q
uv run ruff check .
uv run mypy src
git diff --check
```

Expected: all tests pass, Ruff reports no issues, mypy reports no issues, and Git reports no whitespace errors.

```powershell
git add AGENTS.md README.md docs/architecture.md docs/legal-data-policy.md docs/operations.md docs/onyx-agent-setup.md docs/onyx-agent-instruction.md tests/test_documentation.py
git commit -m "docs: operate hierarchy-aware VBPL search"
```

---

### Task 9: Deploy, promote, re-index, and prove the behavior on the current Onyx instance

**Files:**
- Runtime only: ignored artifacts under `data/evaluations/` and `data/rollback/`
- No tracked implementation files should change during this task.

**Interfaces:**
- Uses the persistent existing VBPL Export connector and direct Onyx Chat/Internal Search.
- Does not use MCP, recreate the connector, delete the source, or clear the index.

- [ ] **Step 1: Save exact rollback inputs before changing external state**

```powershell
New-Item -ItemType Directory -Force data/rollback | Out-Null
Copy-Item -LiteralPath data/exports/active-release.json -Destination data/rollback/active-release-before.json
Get-FileHash -Algorithm SHA256 docs/onyx-agent-instruction.md
```

In the Onyx administration UI, open the current VBPL Legal Agent, copy its live instruction verbatim to `data/rollback/onyx-agent-instruction-before.md`, and record persona ID, model, model parameters, document set, and connector ID in the baseline JSON. Do not save cookies, passwords, or API keys.

- [ ] **Step 2: Generate and validate schema v2 without promotion**

Use the completed current crawl revision:

```powershell
$revision = (Get-Date).ToUniversalTime().ToString("'vbpl-hierarchy-'yyyy-MM-dd-HHmmss")
uv run vbpl-kb crawl --revision $revision
uv run vbpl-kb export-candidate --revision $revision
uv run vbpl-kb validate-release --revision $revision
```

Expected: crawl coverage is `1.0`; every official status is present; candidate validation exits 0; `active-release.json` still names the pre-rollout release.

- [ ] **Step 3: Compare the candidate with the captured baseline**

Inspect the candidate manifest and run the offline evaluation. Acceptance requires:

- stable `vbpl:<official-id>` IDs;
- zero unsafe current-law conclusions;
- 100% resolved/unresolved conflict correctness on the checked-in corpus;
- controlling-provision recall@10 at least 95%;
- authority-bundle completeness@10 at least 90%;
- projected/measured chunk growth no more than 1.25 times baseline.

If any gate fails, stop without promotion.

- [ ] **Step 4: Deploy the backward-compatible connector before schema-v2 promotion**

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/bootstrap-onyx.ps1
pwsh -ExecutionPolicy Bypass -File scripts/start-onyx.ps1
docker compose -f .onyx/onyx/deployment/docker_compose/docker-compose.yml -f infra/onyx/docker-compose.vbpl-connector.yml ps
```

Expected: the pinned checkout and overlay validate, `api_server` and `background` use the rebuilt `vbpl-onyx-backend:latest`, the existing volumes remain attached, and the VBPL export mount is read-only on `background`.

- [ ] **Step 5: Promote atomically and perform exactly one full re-index**

```powershell
uv run vbpl-kb promote-release --revision $revision
uv run vbpl-kb reindex-connector --from-beginning
```

Expected: pointer replacement is atomic; the existing connector finishes successfully; returned status includes the attempt ID and chunk total when Onyx provides it.

- [ ] **Step 6: Apply the canonical prompt through Onyx administration**

In the existing VBPL Legal Agent:

1. keep the same persona/agent identity, model, parameters, tools, and document set;
2. replace only the instruction with the complete contents of `docs/onyx-agent-instruction.md`;
3. ensure Internal Search is enabled and Web Search/MCP are not used;
4. save and reopen the agent to confirm the stored instruction.

- [ ] **Step 7: Run the direct non-MCP post-deployment acceptance**

```powershell
uv run vbpl-kb onyx-acceptance benchmarks/hierarchy-v1.json --label post-deploy --output data/evaluations/hierarchy-post-deploy.json
```

Expected: the command uses `/chat/send-chat-message`, not `/mcp`; all automated gates pass. Manually inspect and add findings for:

- controlling and supporting instruments;
- Article 4 ordering after applicability filtering;
- status and `verified_at`;
- provision-level citations and official links;
- necessary implementing/local instruments;
- stale, inapplicable, and unresolved exclusions/labels;
- contextual inference in the second message of a session;
- focused clarification only in the materially ambiguous case.

Direct Onyx verification is a completion gate. Do not claim completion if the live report is missing or failed.

- [ ] **Step 8: Roll back exactly if a live gate fails**

Read the saved pointer to obtain the prior release ID, then:

```powershell
$prior = Get-Content -Raw data/rollback/active-release-before.json | ConvertFrom-Json
uv run vbpl-kb promote-release --revision $prior.release_id
uv run vbpl-kb reindex-connector --from-beginning
```

Restore `data/rollback/onyx-agent-instruction-before.md` through the same Onyx Agent UI if the prompt changed. Do not recreate/delete the connector and do not delete state, raw data, releases, indexes, or volumes.

- [ ] **Step 9: Final verification**

Run:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest -q
uv run ruff check .
uv run mypy src
git diff --check
git status --short
```

Expected: all automated verification passes; only intentionally ignored runtime reports exist under `data/`; tracked worktree is clean.

---

## Plan Self-Review

### Spec coverage

- Baseline and direct non-MCP Chat evidence: Tasks 1 and 9.
- All 15 Article 4 groups, issuer-sensitive/unknown/non-normative/legacy states: Task 2.
- Status, 24-hour evidence, effective period, jurisdiction, district transition, and provision coordinates: Task 3.
- Verified structured mapping, unknown codes, text candidates, evidence hashes, deduplication, and self-edge exclusion: Task 4.
- Stable IDs, ordered sections, compact headers, schema-v2 validation, atomic promotion, and prior release preservation: Task 5.
- Schema-v1 compatibility, schema-v2 `TextSection` mapping, unsupported-version refusal, batching, and checksum prevalidation: Task 6.
- Retrieval, conflict, unresolved, bundle, safety, and chunk-growth gates: Task 7.
- Context inference, focused clarification, conservative hierarchy rules, citations, canonical prompt, and current-doc updates: Task 8.
- Candidate-first rollout, connector-first deployment, one full re-index, prompt application, live Chat acceptance, and exact rollback: Task 9.

### Type consistency

- `AuthorityClassification` from Task 2 is consumed by Task 3.
- `ApplicabilityEnvelope`, `Provision`, and `OnyxSection` from Task 3 are consumed by schema-v2 `OnyxDocument` in Task 5.
- `LegalReference` and `relationship_tokens` from Task 4 are consumed by normalization/release projection in Task 5.
- Schema-v2 JSON from Task 5 is consumed by the exact v1/v2 connector contract in Task 6.
- `ConnectorStatus` from Task 7 and `ChatResult` from Task 1 are stored in `AcceptanceReport`, then used by Task 9.

### Placeholder scan

The plan contains no placeholder markers, deferred implementation, guessed route, guessed numeric relation mapping, or unnamed test. Live identifiers are required configuration values rather than invented constants, and every live command fails closed when they are absent.
