import json

from ufl.clean.dedup import DeduplicationStore
from ufl.pipeline import process_file, write_output

_UZBEK_PARAGRAPH = "Бу китоб жуда қизиқарли бўлиб, унда кўплаб воқеалар тасвирланган."
_ENGLISH_PARAGRAPH = (
    "This is a purely English paragraph without any Uzbek words "
    "that should definitely be filtered out here."
)
_SHORT_UZBEK_PARAGRAPH = "Бу жуда."


def _make_mixed_content_file(tmp_path) -> "Path":
    content = "\n\n".join(
        [_UZBEK_PARAGRAPH, _ENGLISH_PARAGRAPH, _SHORT_UZBEK_PARAGRAPH, _UZBEK_PARAGRAPH]
    )
    path = tmp_path / "sample.txt"
    path.write_text(content, encoding="utf-8")
    return path


def test_process_file_end_to_end_on_txt_with_mixed_content(tmp_path):
    path = _make_mixed_content_file(tmp_path)

    result = process_file(path, category="books", dedup_store=DeduplicationStore())

    assert result.format == "txt"
    assert result.total_blocks == 4
    assert result.kept_blocks == 1
    assert "kitob" in result.kept_text.lower()
    assert "qiziqarli" in result.kept_text.lower()
    assert "english paragraph" not in result.kept_text.lower()
    assert result.char_count == len(result.kept_text)
    assert result.estimated_tokens > 0

    dropped_reasons = {d.reason for d in result.dropped}
    assert dropped_reasons == {"til_ozbekcha_emas", "juda_qisqa", "takror"}


def test_process_file_transliterates_cyrillic_to_latin_apostrophe(tmp_path):
    path = _make_mixed_content_file(tmp_path)

    result = process_file(path, category="books", dedup_store=DeduplicationStore())

    assert "bo'lib" in result.kept_text
    assert "ko'plab" in result.kept_text


def test_write_output_creates_txt_report_and_rejected_files(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    source_path = _make_mixed_content_file(input_dir)
    result = process_file(source_path, category="books", dedup_store=DeduplicationStore())

    output_dir = tmp_path / "output"
    rejected_dir = tmp_path / "rejected"
    reports_dir = tmp_path / "reports"

    txt_path = write_output(
        result, output_dir=output_dir, rejected_dir=rejected_dir, reports_dir=reports_dir
    )

    assert txt_path.exists()
    assert txt_path.read_text(encoding="utf-8") == result.kept_text

    report_path = reports_dir / "sample.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["category"] == "books"
    assert report["kept_blocks"] == 1
    assert report["dropped_blocks"] == 3

    rejected_path = rejected_dir / "books" / "sample.jsonl"
    assert rejected_path.exists()
    rejected_lines = rejected_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(rejected_lines) == 3
    first_entry = json.loads(rejected_lines[0])
    assert set(first_entry.keys()) == {"text", "page", "reason"}
