# UFL — Implementation Plan (bosqichma-bosqich)

> Bu reja `docs/superpowers/specs/2026-07-15-ufl-data-pipeline-design.md` spec asosida.
> Har vazifa: **nima qilinadi + tugadi deb hisoblash sharti (acceptance)**.
> Tartib muhim — pastdan yuqoriga quriladi. Har faza oxirida **checkpoint** (ishlashini tekshirish).

**Qisqacha:** Faza 0 (skelet+Docker) → Faza 1 (yadro pipeline, ⭐) → Faza 2 (statistika/byudjet) → Faza 3 (Web UI). Faza 1 tugasa — asosiy qiymat tayyor.

---

## FAZA 0 — Skelet va Docker (poydevor)

**Maqsad:** `docker compose up` ishga tushadi, `ufl version` javob beradi. Hech qanday pipeline mantiq yo'q — faqat poydevor.

### 0.1 — Loyiha metama'lumoti
- `pyproject.toml`: paket `ufl`, `src/` layout, entry point `ufl = "ufl.cli:app"`. Python `>=3.12,<3.13`.
- `requirements.txt` (pinned, ishonchli versiyalar): `typer`, `pymupdf`, `pytesseract`, `pillow`, `ebooklib`, `beautifulsoup4`, `python-docx`, `lxml`, `trafilatura`, `fasttext-wheel`, `transformers`, `sentencepiece`, `datasketch`, `tomli` (agar 3.10<), `pydantic`, `rich`, `fastapi`, `uvicorn`, `jinja2`, `python-multipart`.
- **Acceptance:** `pip install -r requirements.txt` toza muhitda xatosiz o'tadi (Docker ichida).

### 0.2 — Konfiguratsiya
- `config/ufl.toml`: kategoriya byudjetlari (spec §1 jadvali), pipeline chegaralari (min uzunlik, simvol %, til chegarasi, chars_per_token), tokenizer `model_id` va lokal yo'l, apostrof rejimi, yo'llar (`data/*`).
- `src/ufl/config.py`: TOML yuklash → `pydantic` model → validatsiya. Yaroqsiz config aniq xato beradi.
- **Acceptance:** `Config.load()` byudjet + chegaralarni qaytaradi; test bor.

### 0.3 — Logging va CLI skeleti
- `src/ufl/logging_setup.py`: `rich` bilan strukturaviy log.
- `src/ufl/cli.py` (typer): `ufl version`, `ufl run <path>` (hozircha "not implemented"), `ufl stats`.
- **Acceptance:** `ufl version` versiyani chiqaradi.

### 0.4 — Docker (⚠️ aniq va muammosiz — user Docker'da yangi)
- `Dockerfile`: `python:3.12-slim` bazasi; apt: `tesseract-ocr tesseract-ocr-uzb tesseract-ocr-uzb-cyrl djvulibre-bin poppler-utils`; `pip install -r requirements.txt`; kod nusxasi; non-root user.
- `docker-compose.yml`: `ufl` servisi (CLI/entrypoint), `data/` va `models/` volume, `.env`. (Web servisi Faza 3'da qo'shiladi, hozircha izohda tayyor turadi.)
- `.dockerignore`, `.env.example`.
- **Build vaqtida** til modeli va tokenizerni yuklab `models/` ga cache qilish uchun `scripts/fetch_models.py` (fastText `lid.176.ftz` + Gemma-4 tokenizer). Offline degradatsiya bilan.
- **Acceptance:**
  - `docker compose build` xatosiz.
  - `docker compose run --rm ufl ufl version` → versiya chiqadi.
  - `docs/DOCKER.md` dagi buyruqlar aynan ishlaydi (Windows + Ubuntu).

### ✅ Checkpoint 0
`docker compose run --rm ufl ufl version` ishlaydi. Tesseract (`tesseract --list-langs` → `uzb`, `uzb_cyrl`) va `djvutxt --help` image ichida mavjud.

---

## FAZA 1 — Yadro pipeline (⭐ ENG MUHIM)

**Maqsad:** istalgan formatdagi faylni toza o'zbekcha `.txt` ga aylantirish + statistika. CLI batch. Testlar bilan.

> Tartib: avval **tozalash modullari** (sof funksiyalar, oson test), keyin **ingest**, keyin **pipeline** ulash.

### 1.1 — Transliteratsiya (`clean/transliterate.py`)
- Spec §7 jadvali va maxsus qoidalar (Е/Ye, Ц/ts-s, ъ→`'`, ь→drop, bosh harf, CAPS).
- Funksiya: `to_latin(text: str) -> str`.
- **Test:** `tests/fixtures/translit_pairs.tsv` (≥50 juftlik, edge-case'lar). `test_transliterate.py` hammasini tekshiradi.
- **Acceptance:** barcha golden juftliklar o'tadi.

### 1.2 — Normalizatsiya (`clean/normalize.py`)
- NFC, apostrof birlashtirish (config rejimi), tirnoq, bo'sh joy, so'z bo'linishi (`-\n`), ko'rinmas belgilar.
- **Test:** `test_normalize.py` (aралash apostrof, ortiqcha bo'shliq, soft-hyphen namunalari).
- **Acceptance:** namunalar kutilgan normal shaklga keladi.

### 1.3 — Til aniqlash (`clean/language.py`)
- fastText `lid.176.ftz` yuklash (lokal) + o'zbekcha gevristika (harf to'plami + stopword ro'yxati).
- `is_uzbek(block: str) -> (bool, score)`; gibrid qaror (spec §8).
- **Test:** `test_language.py` — o'zbek/rus/ingliz/turk/qozoq namunalari to'g'ri klassifikatsiya.
- **Acceptance:** o'zbekcha ≥ kutilgan aniqlik; ruscha/inglizcha DROP.

### 1.4 — Sifat gate (`clean/quality.py`)
- Spec §9 qoidalari (uzunlik, simvol %, buzuq OCR, takror n-gram, alifbo aralashmasi, CAPS, URL/kod).
- `assess(block) -> QualityResult{keep: bool, reason: str}`.
- **Test:** `test_quality.py` — toza vs buzuq bloklar.
- **Acceptance:** buzuq namunalar DROP, toza namunalar KEEP; har DROP sababli.

### 1.5 — Struktura tozalash (`clean/structure.py`)
- Front-matter (titul/TOC/mualliflik), kolontitul (takrorlanuvchi qatorlar), sahifa raqami, footnote, adabiyotlar ro'yxati (spec §6).
- Input: sahifa/blok metadatali hujjat; Output: shovqinsiz bloklar.
- **Test:** `test_structure.py` — namuna TOC/kolontitul/sahifa-raqami olib tashlanadi.
- **Acceptance:** namunalarda front-matter va kolontitul yo'qoladi, asosiy matn qoladi.

### 1.6 — Deduplikatsiya (`clean/dedup.py`)
- Exact + normallashtirilgan hash (v1). MinHash interfeysi tayyor (Faza 2 yoqadi).
- Global holat (hozircha xotira/keyin SQLite).
- **Test:** takror paragraflar bir marta qoladi.

### 1.7 — Ingest: matnli formatlar (`ingest/`)
- `detect.py`: format (kengaytma + magic bytes).
- `txt.py`, `docx.py`, `fb2.py`, `epub.py`, `html.py` (trafilatura), `paste` (matn).
- `base.py`: umumiy `Document{blocks:[{text, page, kind}]}` modeli.
- **Acceptance:** har format namunasidan bloklar chiqadi.

### 1.8 — Ingest: PDF + OCR (`ingest/pdf.py`, `ingest/ocr.py`)
- PyMuPDF: har sahifada text layer bormi? bo'lsa matn; bo'lmasa `ocr.py` (Tesseract `uzb`+`uzb_cyrl`, render 300dpi).
- OCR ishonch pastligida sahifa/blok DROP (spec §5).
- Header/footer aniqlash uchun koordinatalar (`structure.py` ga uzatiladi).
- **Acceptance:** raqamli PDF → matn; skaner PDF namunasi → OCR matn yoki DROP.

### 1.9 — Ingest: DJVU (`ingest/djvu.py`)
- `djvutxt` (text layer) → bo'lmasa `ddjvu` → rasm → OCR.
- **Acceptance:** namuna `.djvu` dan matn (yoki muammosiz skip).

### 1.10 — Token hisobi (`stats/tokens.py`)
- Gemma-4 tokenizer (`transformers`, lokal cache) + taxminiy (`chars_per_token`). Ikkalasi.
- Tokenizer yo'q → ogohlantirish + faqat taxminiy (crash emas).
- **Acceptance:** namuna matn uchun ikkala son chiqadi.

### 1.11 — Pipeline ulash (`pipeline.py`) + statistika (`stats/report.py`)
- Bitta hujjat: DETECT→INGEST→STRUCTURE→TRANSLIT→LANGUAGE→QUALITY→NORMALIZE→DEDUP→WRITE→STATS.
- Fayl izolyatsiyasi (try/except), `rejected/` ga DROP log, `reports/<fayl>.json`.
- **Acceptance:** namuna kitob → `data/output/.../*.txt` + `reports/*.json`.

### 1.12 — CLI batch (`cli.py ufl run`)
- Papkani rekursiv aylanib (kategoriya = papka nomi), har faylni pipeline'dan o'tkazadi, `rich` progress, xulosa.
- Resumable (tugallanganlarni skip — Faza 2 SQLite bilan to'liq).
- **Acceptance:** `ufl run data/input` → barcha fayllar qayta ishlanadi, xulosa chiqadi.

### ✅ Checkpoint 1
`docker compose run --rm ufl ufl run data/input` bir nechta xil formatli namunani toza `.txt` ga aylantiradi; kirill→lotin ishlaydi; ruscha/inglizcha tashlanadi; har fayl uchun belgi+token statistikasi bor. Barcha unit-testlar yashil.

---

## FAZA 2 — Statistika / byudjet store

**Maqsad:** SQLite'da barqaror statistika + byudjet progress (spec §1 jadvaliga).

### 2.1 — SQLite store (`store/db.py`)
- Spec §15 sxema (`books`, `dedup_hashes`, `budget`). Migratsiya/init.
- Pipeline natijalari va dedup shu yerga yoziladi; resumable to'liq ishlaydi.
- **Acceptance:** qayta `ufl run` tugallanganlarni skip qiladi; dedup global.

### 2.2 — Byudjet hisobi (`stats/budget.py`)
- Kategoriya bo'yicha yig'ilgan token vs maqsad; foiz.
- **Acceptance:** to'g'ri yig'indi + progress.

### 2.3 — `ufl stats` hisobot
- Terminal jadval (`rich`): kategoriya, yig'ilgan/maqsad, %, jami. `summary.json` + `summary.md`.
- **Acceptance:** `ufl stats` byudjet progressni chiqaradi.

### ✅ Checkpoint 2
`ufl stats` "Books: X/120M", "Jami: Y/1.2B" ko'rinishida progress beradi; qayta ishga tushirish ish takrorlamaydi.

---

## FAZA 3 — Web UI + VPS deploy

**Maqsad:** jamoa uchun oddiy web panel; Contabo VPS'da ishlaydi.

### 3.1 — FastAPI backend (`web/app.py`, `routes.py`)
- Endpointlar: upload (fayl/paste + kategoriya), jarayon (BackgroundTasks), natija, `.txt` yuklab olish, byudjet dashboard (JSON).
- **Acceptance:** `curl` bilan upload→process→result ishlaydi.

### 3.2 — Frontend (Jinja2 + minimal JS)
- Sahifalar: Upload/paste, Jarayon holati, Natijalar, **Byudjet dashboard** (progress barlar). Build-step yo'q.
- **Acceptance:** brauzerda fayl yuklab, natija va dashboard ko'rinadi.

### 3.3 — Auth + xavfsizlik (`web/auth.py`)
- Oddiy login/parol (`.env`) yoki IP allowlist. CSRF/limit. (Privacy talabi.)
- **Acceptance:** parolsiz kirish rad etiladi.

### 3.4 — VPS deploy (`docs/DOCKER.md` bo'limi)
- `docker-compose.yml` ga `web` servisi; Nginx reverse-proxy + HTTPS; `data/`,`models/` volume.
- **Acceptance:** Contabo'da `docker compose up -d` → jamoa URL orqali ishlatadi.

### ✅ Checkpoint 3
Jamoa a'zosi brauzerda kitob yuklab, toza `.txt` oladi va byudjet progressni ko'radi. VPS'da barqaror ishlaydi.

---

## Umumiy "Definition of Done"

- [ ] Barcha unit + integration testlar yashil (Docker ichida).
- [ ] `ufl run` bir nechta xil formatni muammosiz qayta ishlaydi; bitta yomon fayl batch'ni to'xtatmaydi.
- [ ] Kirill→lotin golden testlar o'tadi; ruscha/inglizcha DROP.
- [ ] Statistika belgi + Gemma-token + taxminiy tokenni beradi; byudjet progress to'g'ri.
- [ ] `docs/DOCKER.md` bo'yicha begona odam ham Windows va Ubuntu'da ishga tushira oladi.
- [ ] `data/rejected/` DROP sabablarini ko'rsatadi (audit/sozlash uchun).

## Implementatsiya tartibi bo'yicha eslatma (Sonnet uchun)

1. **TDD:** har `clean/*` moduli — avval test (golden), keyin kod.
2. Har modul **sof funksiya**, I/O faqat `pipeline.py`/`store`/`cli` da.
3. Har faza checkpoint'ini **Docker ichida** tekshirib, keyin keyingisiga o'tish.
4. Optional deps (Tesseract/DjVu/tokenizer) yo'qligida **degradatsiya**, crash emas.
5. Har bosqichda foydalanuvchiga qisqa hisobot.
