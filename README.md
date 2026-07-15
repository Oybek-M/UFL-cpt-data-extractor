# UFL — Uzbek CPT Data Pipeline

O'zbekcha lokal LLM (baza: **Gemma 4**) uchun **toza CPT matn** tayyorlaydigan quvur.
Kitob va hujjatlardan (PDF, EPUB, DJVU, DOCX, FB2, TXT, HTML, copy-paste) **faqat sof o'zbekcha (lotin)** matnni ajratib oladi, kirillni lotinga o'giradi, shovqin (muqova, mundarija, kolontitul, sahifa raqami) va begona tillarni tashlaydi, va **belgi + Gemma-token** statistikasini beradi.

> **Tamoyil:** *shubha bo'lsa — tashla.* CPT uchun faqat toza, muammosiz DATA.

## Nima qiladi

- ✅ Avto-format aniqlash: raqamli PDF vs skaner (OCR)
- ✅ Skaner → Tesseract OCR (`uzb`, `uzb_cyrl`), sifatsiz joy DROP
- ✅ Kirill → Lotin (o'zbek qoidalari)
- ✅ Faqat o'zbekcha qoldirish (rus/ingliz/boshqa tashlanadi)
- ✅ Struktura tozalash (front-matter, header/footer, sahifa raqami)
- ✅ Sifat filtri + deduplikatsiya
- ✅ Statistika: belgi, so'z, Gemma-token, taxminiy token, byudjet progress
- ✅ Web UI (Faza 3) + VPS deploy

## Tez boshlash (Docker)

```bash
docker compose build
docker compose run --rm ufl ufl version
# Kitoblarni data/input/<kategoriya>/ ga tashlang, keyin:
docker compose run --rm ufl ufl run data/input
docker compose run --rm ufl ufl stats
```

To'liq Docker qo'llanmasi (Windows + Ubuntu VPS): **[docs/DOCKER.md](docs/DOCKER.md)**

## Kategoriyalar (CPT byudjeti — 1.2B token)

`web_news` 240M · `gov_legal` 180M · `education` 180M · `reference` 180M · `books` 120M · `conversations` 120M · `technical` 120M · `domain_haf` 60M

Kitobni tegishli kategoriya papkasiga qo'ying: `data/input/books/`, `data/input/education/`, ...

## Struktura

```
config/ufl.toml     sozlamalar + byudjet + chegaralar
data/               input/ output/ rejected/ reports/
models/             Gemma-4 tokenizer + til modeli (oflayn)
src/ufl/            ingest/ clean/ stats/ store/ web/
tests/              unit + integration
docs/               spec, implementation plan, Docker qo'llanma
```

## Hujjatlar

- **Dizayn (spec):** [docs/superpowers/specs/2026-07-15-ufl-data-pipeline-design.md](docs/superpowers/specs/2026-07-15-ufl-data-pipeline-design.md)
- **Implementation plan:** [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md)
- **Docker qo'llanma:** [docs/DOCKER.md](docs/DOCKER.md)

## Status

🟡 Rejalashtirish tugadi — implementatsiya boshlanadi (Faza 0 → 1 → 2 → 3).
