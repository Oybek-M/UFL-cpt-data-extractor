"""Oflayn ishlash uchun modellarni bir marta yuklab olish.

Ishlatish:
    docker compose run --rm ufl python scripts/fetch_models.py

Ikkala model ham ixtiyoriy: topilmasa pipeline ogohlantirib, taxminiy/gevristik
usulga o'tadi (crash bo'lmaydi) — shuning uchun bu skript xatoni yutib, exit 0 bilan tugaydi.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ufl.config import Config  # noqa: E402

FASTTEXT_LID_URL = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz"


def fetch_fasttext(dest: Path) -> None:
    if dest.exists():
        print(f"[fastText] allaqachon mavjud: {dest}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"[fastText] yuklanmoqda: {FASTTEXT_LID_URL}")
    try:
        urllib.request.urlretrieve(FASTTEXT_LID_URL, dest)
        print(f"[fastText] OK -> {dest}")
    except Exception as exc:  # noqa: BLE001
        print(f"[fastText] OGOHLANTIRISH: yuklab bo'lmadi ({exc}). Til aniqlash faqat gevristikaga tayanadi.")


def fetch_tokenizer(model_id: str, dest: Path) -> None:
    if dest.exists() and any(dest.iterdir()):
        print(f"[tokenizer] allaqachon mavjud: {dest}")
        return
    print(f"[tokenizer] yuklanmoqda: {model_id}")
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=model_id,
            local_dir=dest,
            allow_patterns=["tokenizer*", "*.model", "special_tokens_map.json"],
        )
        print(f"[tokenizer] OK -> {dest}")
    except Exception as exc:  # noqa: BLE001
        print(
            f"[tokenizer] OGOHLANTIRISH: yuklab bo'lmadi ({exc}).\n"
            "  Sabab: internet yo'q, HF_TOKEN kerak, yoki model_id noto'g'ri "
            "(config/ufl.toml [tokenizer].model_id ni tekshiring).\n"
            "  Pipeline shu tokenizer o'rniga taxminiy (belgi-nisbati) token hisobiga o'tadi."
        )


def main() -> None:
    config = Config.load()
    fetch_fasttext(config.language.fasttext_model_path)
    fetch_tokenizer(config.tokenizer.model_id, config.tokenizer.local_dir)
    print("\nTugadi. Yuqoridagi OGOHLANTIRISH bo'lsa ham pipeline ishlayveradi (fallback rejimda).")


if __name__ == "__main__":
    main()
