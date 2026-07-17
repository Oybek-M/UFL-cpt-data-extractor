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
- ✅ Web UI + VPS deploy
- ✅ Saytdan yig'ish (crawl): CLI/Web UI orqali butun sayt/blogdan toza matn — ixtiyoriy
  MiniMax AI yordami bilan (token-tejamkor: kalibratsiya domen uchun ~1 marta)
- ✅ Fayllardan (eBook/hujjat) extract: tekis papkaga tashlangan fayllar avtonom, mustaqil
  qayta ishlanadi (kategoriya avto-aniqlanadi); ixtiyoriy `--verify-with-minimax` — faqat
  shubhali bloklarni bitta so'rovda tekshiradi, matnni hech qachon tahrirlamaydi

## Tez boshlash (Docker)

```bash
docker compose build
docker compose run --rm ufl ufl version
docker compose run --rm ufl python scripts/fetch_models.py   # bir marta, oflayn uchun
# Kitoblarni data/input/<kategoriya>/ ga tashlang, keyin:
docker compose run --rm ufl ufl run data/input
docker compose run --rm ufl ufl stats

# Saytdan yig'ish:
docker compose run --rm ufl ufl crawl https://kun.uz --category web_news
```

To'liq Docker qo'llanmasi (Windows + Ubuntu VPS): **[docs/DOCKER.md](docs/DOCKER.md)** ·
Crawl bo'yicha batafsil: **[docs/DOCKER.md §6](docs/DOCKER.md#6-saytdan-yigish-crawl)**

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
- **Crawler dizayn (spec):** [docs/superpowers/specs/2026-07-16-website-crawler-integration-design.md](docs/superpowers/specs/2026-07-16-website-crawler-integration-design.md)
- **Crawler implementation plan:** [docs/IMPLEMENTATION_PLAN_CRAWLER.md](docs/IMPLEMENTATION_PLAN_CRAWLER.md)
- **Docker qo'llanma:** [docs/DOCKER.md](docs/DOCKER.md)

## Status

🟢 Asosiy pipeline + Web UI ishlab turibdi va **VPS'da production'da** (`https://ufl.ibos.uz`,
Nginx + Basic Auth + HTTPS orqasida). Crawler: 4.1–4.10 tayyor (poydevor, ko'p-strategiyali
ekstraksiya, resumable state, writer+byudjet, CLI, MiniMax, Web UI, wiki-boilerplate filtri,
VPS deploy).
