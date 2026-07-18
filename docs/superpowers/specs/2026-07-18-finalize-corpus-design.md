# `ufl finalize-corpus` — Design

## Muammo

`UFL-Datas` papkasida (host: `../UFL-Datas`, konteynerda `docker-compose.override.yml` orqali
`/app/data/output`ga bog'langan) yig'ilgan matnlar jamoaning umumiy training bazasiga
topshirilishidan oldin ikki narsa hal qilinishi kerak:

1. **CPT (Continued Pre-Training) uchun sifat**: mavjud pipeline (`process_file`) har bir faylni
   yig'ish paytida bir marta filtrlaydi (fastText til aniqlash + evristika, sifat gate,
   header/footer tozalash, SHA1 dedup) — lekin bu dedup faqat **bitta CLI ishga tushirish**
   doirasida ishlaydi, turli sanalarda/turli manbalardan yig'ilgan fayllar bo'yicha emas.
   Professional CPT pipeline'larda (Dolma, FineWeb, RedPajama, CCNet) bundan tashqari:
   butun korpus bo'yicha exact-hash dedup va PII (email/telefon) tozalash standart hisoblanadi.
2. **Manba yashirish**: HuggingFace'dan (`tahrirchi/uz-crawl`, `tahrirchi/uz-books-v2`,
   `yakhyo/uz-wiki`) olingan shardlar fayl nomida dataset slug'ini saqlaydi
   (masalan `tahrirchi_uz-crawl__news__shard-000001.txt`) — bu HF va tashkilot nomini
   fosh qiladi. Jamoaga topshirishdan oldin bu qism yashirilishi kerak. ziyouz.com'dan
   olingan fayllar (`{id}_{slug}.txt`) allaqachon manbasiz ko'rinadi — ularga tegilmaydi.

## Qamrov (Scope)

Yangi `ufl finalize-corpus` CLI buyrug'i, uchta ketma-ket bosqich bilan:

1. Global (korpus-bo'ylab) exact-hash dedup
2. PII (email, telefon) tozalash
3. HF fayl nomlarini "de-branding" qilish (dataset slug → generic alias)

**Qamrovdan tashqarida (keyingi bosqich, hozir kerak emas):** MinHash near-dedup,
perplexity/klassifikator filtri, decontamination — tadqiqot natijasida kichik jamoa uchun past
ustuvorlik deb topildi (`docs/superpowers/specs/` — shu spec ichida eslatma sifatida qoldiriladi,
kelajakda alohida spec sifatida ko'rib chiqiladi).

## Arxitektura

- Yangi Typer buyruq: `cli.py`'da `finalize-corpus`, mavjud `fetch-hf`/`fetch-ziyouz` naqshiga mos.
- `config.paths.output` (`data/output`) ustida ishlaydi — bu konteynerda avtomatik `UFL-Datas`ga
  bog'langan, qo'shimcha konfiguratsiya kerak emas.
- **Standart holat: dry-run** (faqat hisobot). Haqiqiy o'zgarish uchun `--apply` flag shart.
  Sabab: dublikatlarni ko'chirish va fayl qayta nomlash qaytarib bo'lmaydigan amal.
- **Bosqich tartibi muhim**: dedup → PII → HF-rename (aynan shu tartibda). Sabab: dedup bosqichi
  har bir faylni `ufl.db`dagi mos yozuvga bog'lash uchun fayl nomidan manba identifikatorini
  hisoblaydi (masalan HF fayllar uchun `{dataset_slug}__{split}__shard-N.txt` → `hf:{dataset_id}:
  {split}:shard-N`). Agar rename avval bajarilsa, fayl nomida endi asl dataset_slug o'rniga
  generic alias turadi va bu bog'lanishni son ma'lumotisiz (alias→dataset teskari xaritasiz)
  ishonchli hisoblab bo'lmaydi. Shuning uchun rename doim OXIRIDA ishlaydi.
- Har bir jarayon o'z ishlagan davrida to'liq skanerlaydi (bir martalik "snapshot"), hozir
  yozilayotgan (hali yakunlanmagan) fayllarga tegmaydi — keyinroq qayta ishga tushirish
  xavfsiz (idempotent).

## Komponentlar

### 1. `src/ufl/finalize/dedup.py` — Global dedup

- `UFL-Datas/*/`(barcha kategoriya papkalari)dagi barcha `.txt` fayllarni skanerlaydi.
- Har biri uchun SHA1(fayl matni) hisoblaydi, xash bo'yicha guruhlaydi.
- Guruhda 1tadan ortiq fayl bo'lsa: birinchisi (fayl nomi bo'yicha) qoladi, qolganlari
  **o'chirilmaydi** — repo ichidagi `data/rejected/duplicates/{category}/{original_filename}`ga
  ko'chiriladi (qaytarib olish mumkin bo'lgan joy, git bilan boshqariladigan `data/` papkasi
  ostida, gitignored).
- Ko'chirilgan har bir fayl uchun, agar mos `ufl.db` yozuvi topilsa (fayl nomidan path
  hisoblab, DB'dan qidirib), `Store.mark_duplicate(path)` chaqiriladi — yozuv o'chirilmaydi,
  faqat `dedup_status='duplicate'` deb belgilanadi. Bu token hisobotlarida (`collected_tokens_
  by_category`) noto'g'ri sanalmasligi uchun kerak.
- Mos DB yozuvi topilmasa (masalan eski format yoki tashqi qo'shilgan fayl), faqat
  fayl ko'chiriladi, ogohlantirish chiqariladi.

### 2. `src/ufl/finalize/pii.py` — PII tozalash

- Regex naqshlar: email manzillar, telefon raqamlar (xalqaro `+998...` va mahalliy
  `0XX XXX XX XX` formatlari).
- Har bir `.txt` faylni o'qiydi, moslangan qismlarni olib tashlaydi, agar o'zgarish bo'lsa
  faylni qayta yozadi.
- Barcha kategoriyalarga qo'llanadi (nafaqat HF-manbali fayllarga).

### 3. `src/ufl/finalize/hf_rename.py` — HF de-branding

- `DATASET_ALIAS: dict[str, str]` — aniq xarita (`category_map.py` uslubida), masalan:
  ```python
  DATASET_ALIAS = {
      "tahrirchi/uz-crawl": "corpus-a",
      "tahrirchi/uz-books-v2": "corpus-b",
      "yakhyo/uz-wiki": "corpus-c",
  }
  ```
- `ufl.db`dan `path LIKE 'hf:%'` bo'lgan barcha yozuvlarni o'qiydi.
- Har biri uchun `path`dan (`hf:{dataset_id}:{split}:shard-{N}`) eski fayl nomini hisoblaydi:
  `f"{dataset_slug(dataset_id)}__{split}__shard-{N}.txt"` (mavjud `dataset_slug()` funksiyasi,
  `src/ufl/ingest/hf_dataset.py`).
- Agar `dataset_id` `DATASET_ALIAS`da bo'lsa va eski nomdagi fayl `{category}/` papkasida
  mavjud bo'lsa: yangi nomga (`f"{alias}__{split}__shard-{N}.txt"`) qayta nomlaydi.
- Agar `dataset_id` xaritada topilmasa: **o'tkazib yuboriladi va ogohlantiriladi** (hech qachon
  taxminiy alias yaratilmaydi — "shubha bo'lsa tashla" tamoyili, `category_map.py`dagi kabi).
  Oxirida "N ta dataset uchun alias topilmadi" xulosasi chiqadi.
- Eski nomdagi fayl topilmasa (allaqachon qayta nomlangan yoki hali yozilmagan) — jim
  o'tkazib yuboriladi (idempotentlik).
- `ufl.db`dagi `path` maydoni **o'zgarmaydi** — asl manba doim ichki audit uchun saqlanadi
  (bu DB hech qachon jamoaga berilmaydi).
- **Faqat `data/output/`dagi `.txt` fayl qayta nomlanadi.** `data/rejected/*.jsonl` va
  `data/reports/*.json` fayllariga tegilmaydi — ular hech qachon jamoaga berilmaydi
  (faqat ichki debug uchun), asl HF nomida qolaversa muammo emas.

## `ufl.db` sxema o'zgarishi

`Store` ga:
- Yangi ustun `dedup_status TEXT` (nullable) — mavjud production `ufl.db` fayli allaqachon
  bu ustunsiz yaratilgan bo'lgani uchun, `Store.__init__` da `PRAGMA table_info(books)` orqali
  ustun borligini tekshirib, yo'q bo'lsa `ALTER TABLE books ADD COLUMN dedup_status TEXT`
  bilan xavfsiz migratsiya qilinadi (mavjud qatorlar buzilmaydi).
- Yangi metod: `mark_duplicate(path: str) -> None`.
- `collected_tokens_by_category()` yangilanadi: `WHERE dedup_status IS NULL` shartini qo'shadi
  (dublikat deb belgilangan qatorlar statistikaga kirmaydi).

## Xatolarni boshqarish

- Konfiguratsiya/DB/output papka topilmasa — aniq xato bilan to'xtaydi.
- Har bir fayl operatsiyasi alohida `try/except` bilan o'raladi — bitta yomon fayl (ruxsat
  yo'q, band, va h.k.) butun jarayonni to'xtatmaydi; oxirida xatolar ro'yxati chiqadi.
- Noma'lum HF dataset (aliasi yo'q) — skip + ogohlantirish (yuqorida tavsiflangan).
- Dry-run (standart) — hech narsa yozilmaydi/ko'chirilmaydi/o'chirilmaydi, faqat hisobot:
  "N ta dublikat guruh (M fayl), K ta PII topildi (L faylda), P ta HF fayl qayta nomlanadi,
  Q ta dataset uchun alias topilmadi".

## Testlash

TDD, loyihaning mavjud naqshiga mos (`tests/test_cli_fetch_ziyouz.py` uslubida):
- `tests/test_finalize_dedup.py` — vaqtinchalik papkada bir xil/turli kontentli fayllar bilan
  guruhlash va ko'chirish mantig'i, `Store.mark_duplicate` chaqirilishi.
- `tests/test_finalize_pii.py` — turli email/telefon formatlar bilan regex mosligi,
  o'zgarish bo'lmagan faylga tegilmasligi.
- `tests/test_finalize_hf_rename.py` — vaqtinchalik SQLite DB + vaqtinchalik fayllar bilan
  `path`→eski nom→yangi nom hisoblanishi, noma'lum dataset uchun ogohlantirish, idempotentlik
  (fayl allaqachon qayta nomlangan bo'lsa qayta ishlamasligi).
- `tests/test_cli_finalize_corpus.py` — to'liq CLI integratsiyasi: dry-run hech narsa
  o'zgartirmasligi, `--apply` bilan barcha uch bosqich to'g'ri ishlashi.

## Hujjatlar

`docs/DOCKER.md`ga yangi bo'lim: `## 10. Korpusni yakunlash (finalize-corpus)` — qachon
ishlatish (jamoaga topshirishdan oldin), `--apply` bilan/siz misollar, dry-run natijasini
o'qish.
