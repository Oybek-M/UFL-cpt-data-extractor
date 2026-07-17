"""MiniMax AI klienti — ambigu sahifalar uchun maqola-tana tanlash (Rol A) va
auto-kategoriya (Rol B).

Manba: website-to-txt-collector/continuous_collector.py (1123-1346) — UFL uslubida port.

TOKEN TEJASH (foydalanuvchi talabi, MAJBURIY) — dizayn spec §6.3:
- Bu klient FAQAT `Collector` local-ekstraksiya qila olmagan (domen uchun `adapter` hali
  yo'q, nomzod ambigu) sahifalar uchun chaqiriladi. Domen uchun adapter bir marta
  aniqlangach (`select_candidate` muvaffaqiyatli bo'lgach saqlanadi), keyingi barcha
  sahifalar `collector.py`da MiniMax'siz local ishlaydi — token sarfi maqolalar soniga
  emas, DOMENLAR soniga proporsional.
- Belgi-byudjeti: eng ko'p 6 nomzod, jami <=180k belgi.
- `batch_hash` bilan bir xil so'rov qayta yuborilmaydi (`ai_batches` jadvali).
- Bounded retry: 429/5xx -> eksponensial backoff, eng ko'p 5 urinish; 401/403 ->
  butunlay to'xtash (`minimax_blocked` meta).
- `classify_category` faqat sarlavha + ~400 belgi snippet yuboradi, `max_completion_tokens`
  juda kichik (~16) — kategoriya-aniqlash amaliyoti ham arzon.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol

from ufl.crawl._time import parse_time, utc_now
from ufl.crawl.blocks import clean_content_blocks
from ufl.crawl.candidates import Candidate
from ufl.crawl.state import CrawlState

class InMemoryMetaState:
    """`get_meta`/`set_meta` — MiniMaxClient uchun domensiz/vaqtinchalik kontekstda
    (masalan `ufl run` fayl-avtokategoriya). Faqat joriy jarayon davomida saqlanadi —
    doimiy CrawlState kerak emas, chunki bloklash faqat bitta batch ichida ahamiyatli."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get_meta(self, key: str) -> str | None:
        return self._data.get(key)

    def set_meta(self, key: str, value: str) -> None:
        self._data[key] = value


DEFAULT_MODEL = "MiniMax-M2.7-highspeed"
DEFAULT_URL = "https://api.minimax.io/v1/chat/completions"
MAX_CANDIDATES = 6
MAX_TOTAL_CHARS = 180_000
MAX_RETRY_ATTEMPTS = 5
_STRUCTURED_METHODS = {"jsonld", "nuxt", "next"}


class PostResponse(Protocol):
    status_code: int
    text: str

    def json(self) -> Any: ...


PostFn = Callable[[str, dict[str, str], dict[str, Any], float], PostResponse]


def _default_post(url: str, headers: dict[str, str], json_body: dict[str, Any], timeout: float) -> PostResponse:
    import httpx

    return httpx.post(url, headers=headers, json=json_body, timeout=timeout)


def _first_json_object(text: str) -> dict:
    start = text.find("{")
    if start == -1:
        raise ValueError("Javobda JSON obyekt topilmadi")
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : index + 1])
    raise ValueError("Javobda to'liq JSON obyekt topilmadi")


@dataclass
class CandidateDecision:
    """`select_candidate` natijasi. `status`: accepted | non_article | quality_rejected | manual_review."""

    status: str
    method: str | None = None
    blocks: list[str] = field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""


class MiniMaxClient:
    def __init__(
        self,
        api_key: str,
        state: CrawlState,
        *,
        model: str = DEFAULT_MODEL,
        url: str = DEFAULT_URL,
        min_confidence: float = 0.65,
        post: PostFn | None = None,
    ) -> None:
        self.api_key = api_key
        self.state = state
        self.model = model
        self.url = url
        self.min_confidence = min_confidence
        self._post = post or _default_post
        # Yangi/almashtirilgan kalit bilan ishga tushirilsa — bitta yangi urinishga ruxsat
        # (kalitning o'zi hech qachon saqlanmaydi/loglanmaydi).
        if api_key and state.get_meta("minimax_blocked"):
            state.set_meta("minimax_blocked", "")

    @property
    def blocked(self) -> bool:
        return bool(self.state.get_meta("minimax_blocked"))

    # --- Rol A: kalibratsiya (maqola-tana nomzodini tanlash) ---
    def select_candidate(
        self,
        *,
        domain: str,
        page_id: int,
        url: str,
        title: str,
        published: str | None,
        reason: str,
        candidates: list[Candidate],
    ) -> CandidateDecision | None:
        """Ambigu sahifa uchun MiniMax'dan nomzod tanlashni so'raydi.

        `None` — hali javob yo'q (kalitsiz/bloklangan/retry vaqti kelmagan): chaqiruvchi
        sahifani `ai_pending`ga qo'yib, keyinroq qayta urinadi.
        """
        if not self.api_key or self.blocked:
            return None

        candidate_payloads: list[dict[str, Any]] = []
        total_chars = 0
        for candidate in candidates[:MAX_CANDIDATES]:
            blocks = candidate.block_payload(character_budget=1_000_000)
            size = sum(len(block["text"]) for block in blocks)
            if candidate_payloads and total_chars + size > MAX_TOTAL_CHARS:
                break
            candidate_payloads.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "method": candidate.method,
                    "selector": candidate.selector,
                    "blocks": blocks,
                }
            )
            total_chars += size

        metadata_blocks = []
        if title:
            metadata_blocks.append({"block_id": "title_0001", "text": title})
        if published:
            metadata_blocks.append({"block_id": "date_0001", "text": published})
        page_payload = {
            "page_id": page_id,
            "url": url,
            "review_reason": reason,
            "metadata_blocks": metadata_blocks,
            "candidates": candidate_payloads,
        }
        identity = json.dumps(page_payload, ensure_ascii=False, sort_keys=True)
        batch_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

        old_batch = self.state.conn.execute(
            "SELECT status,retry_at,attempts FROM ai_batches WHERE batch_hash=?", (batch_hash,)
        ).fetchone()
        if old_batch:
            if old_batch["status"] == "complete":
                return None  # batch_hash dedup: bir xil payload qayta yuborilmaydi
            if old_batch["status"] == "retry":
                retry_at = parse_time(old_batch["retry_at"])
                if retry_at and retry_at > datetime.now(timezone.utc):
                    return None
                if int(old_batch["attempts"]) >= MAX_RETRY_ATTEMPTS:
                    self._record_batch(batch_hash, "manual_review", None, "MiniMax retry limiti tugadi")
                    return CandidateDecision("manual_review", reason="MiniMax retry limiti tugadi")

        request_body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You select article-body candidates using structural evidence.",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "instruction": (
                                "The page has already been converted from HTML into labeled "
                                "plain-text blocks. No raw HTML is present. Identify the "
                                "candidate containing the complete main article, every "
                                "main-content block, and every trash block (ads, captions, "
                                "share controls, navigation). Reject home/category/tag/"
                                "search/login/paywall pages. Do not rewrite or summarize any "
                                "text. Return one JSON object with exactly: page_id, "
                                "is_article, candidate_id, content_block_ids, "
                                "trash_block_ids, complete, confidence, reason."
                            ),
                            "domain": domain,
                            "page": page_payload,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "stream": False,
            "max_completion_tokens": 4000,
            "temperature": 0.1,
        }
        self._upsert_pending_batch(batch_hash, domain, page_id)

        try:
            response = self._post(
                self.url,
                {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                request_body,
                120.0,
            )
        except Exception as exc:  # noqa: BLE001 — tarmoq xatosi: qayta urinish
            self._record_batch(batch_hash, "retry", None, f"{type(exc).__name__}: {exc}", retry=True)
            return None

        if response.status_code in (401, 403):
            self._record_batch(batch_hash, "blocked", response.status_code, "MiniMax avtorizatsiyasi rad etildi")
            self.state.set_meta("minimax_blocked", f"HTTP {response.status_code} at {utc_now()}")
            return CandidateDecision("manual_review", reason="MiniMax bloklandi (401/403)")
        if response.status_code == 429 or response.status_code >= 500:
            self._record_batch(batch_hash, "retry", response.status_code, response.text[:500], retry=True)
            return None

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            decision = _first_json_object(content)
            if int(decision.get("page_id", page_id)) != page_id:
                raise ValueError("MiniMax noto'g'ri page_id qaytardi")
        except Exception as exc:  # noqa: BLE001
            self._record_batch(batch_hash, "manual_review", None, f"{type(exc).__name__}: {exc}")
            return CandidateDecision("manual_review", reason=f"parse_error: {exc}")

        self._record_batch(batch_hash, "complete", response.status_code, None)
        return self._apply_decision(domain, candidates, decision)

    def _apply_decision(
        self, domain: str, candidates: list[Candidate], decision: dict[str, Any]
    ) -> CandidateDecision:
        if not bool(decision.get("is_article")):
            return CandidateDecision(
                "non_article", reason=str(decision.get("reason", "MiniMax: maqola emas"))[:1000]
            )
        candidate_id = str(decision.get("candidate_id", ""))
        candidate = next((item for item in candidates if item.candidate_id == candidate_id), None)
        if candidate is None:
            return CandidateDecision("manual_review", reason=f"noma'lum nomzod: {candidate_id}")
        confidence = float(decision.get("confidence", 0.0))
        if confidence < self.min_confidence:
            return CandidateDecision(
                "manual_review", confidence=confidence, reason=f"ishonch darajasi past: {confidence:.2f}"
            )
        if not bool(decision.get("complete", False)):
            return CandidateDecision(
                "quality_rejected",
                confidence=confidence,
                reason=f"to'liqsiz ekstraksiya: {decision.get('reason', '')}"[:2000],
            )
        supplied = {block["block_id"]: block["text"] for block in candidate.block_payload(1_000_000)}
        content_ids = [str(value) for value in decision.get("content_block_ids", [])]
        trash_ids = {str(value) for value in decision.get("trash_block_ids", [])}
        if content_ids:
            unknown = [value for value in content_ids if value not in supplied]
            if unknown:
                return CandidateDecision("manual_review", reason=f"noma'lum blok ID: {unknown[:3]}")
            selected_blocks = [supplied[value] for value in content_ids if value not in trash_ids]
        else:
            selected_blocks = [value for key, value in supplied.items() if key not in trash_ids]
        selected_blocks = clean_content_blocks(selected_blocks)
        if len("\n\n".join(selected_blocks)) < 250:
            return CandidateDecision("manual_review", confidence=confidence, reason="MiniMax tanlagan tana juda qisqa")

        if not self.state.adapter(domain):
            stable_selector = "" if candidate.method in _STRUCTURED_METHODS else candidate.selector
            self.state.save_adapter(domain, candidate.method, stable_selector, confidence, 1)

        return CandidateDecision("accepted", method=candidate.method, blocks=selected_blocks, confidence=confidence)

    # --- Rol B: auto-kategoriya ---
    def classify_category(self, title: str, snippet: str, valid_categories: list[str]) -> str | None:
        """Faqat sarlavha + ~400 belgi snippet yuboradi (token tejash, spec §6.2)."""
        if not self.api_key or self.blocked:
            return None
        request_body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You classify article categories. Reply with only the category key.",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "instruction": (
                                "Classify this Uzbek-language article into exactly one category "
                                "from the list. Return only the category key, nothing else."
                            ),
                            "categories": valid_categories,
                            "title": title[:200],
                            "snippet": snippet[:400],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "stream": False,
            "max_completion_tokens": 16,
            "temperature": 0.1,
        }
        try:
            response = self._post(
                self.url,
                {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                request_body,
                30.0,
            )
        except Exception:  # noqa: BLE001 — tarmoq xatosi: default'ga tayanamiz
            return None
        if response.status_code in (401, 403):
            self.state.set_meta("minimax_blocked", f"HTTP {response.status_code} at {utc_now()}")
            return None
        if response.status_code != 200:
            return None
        try:
            body = response.json()
            content = str(body["choices"][0]["message"]["content"]).strip()
        except Exception:  # noqa: BLE001
            return None
        match = re.search(r"[a-z_]+", content.lower())
        guess = match.group(0) if match else ""
        return guess if guess in valid_categories else None

    # --- ai_batches boshqaruvi ---
    def _upsert_pending_batch(self, batch_hash: str, domain: str, page_id: int) -> None:
        stamp = utc_now()
        self.state.conn.execute(
            """INSERT OR IGNORE INTO ai_batches
               (batch_hash,domain,page_ids,status,request_file,attempts,created_at,updated_at)
               VALUES(?,?,?,'pending','',0,?,?)""",
            (batch_hash, domain, json.dumps([page_id]), stamp, stamp),
        )
        self.state.conn.execute(
            "UPDATE ai_batches SET status='processing',attempts=attempts+1,updated_at=? WHERE batch_hash=?",
            (stamp, batch_hash),
        )
        self.state.conn.commit()

    def _record_batch(
        self,
        batch_hash: str,
        status: str,
        http_status: int | None,
        error: str | None,
        retry: bool = False,
    ) -> None:
        attempts_row = self.state.conn.execute(
            "SELECT attempts FROM ai_batches WHERE batch_hash=?", (batch_hash,)
        ).fetchone()
        attempts = int(attempts_row["attempts"]) if attempts_row else 1
        delay_minutes = min(60, 5 * (2 ** max(0, attempts - 1)))
        retry_at = (
            (datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)).isoformat() if retry else None
        )
        self.state.conn.execute(
            "UPDATE ai_batches SET status=?,http_status=?,error=?,retry_at=?,updated_at=? WHERE batch_hash=?",
            (status, http_status, ((error or "")[:2000] or None), retry_at, utc_now(), batch_hash),
        )
        self.state.conn.commit()
