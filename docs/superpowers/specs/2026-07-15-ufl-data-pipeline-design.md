# UFL — Uzbek CPT Data Pipeline — Design Spec

- **Sana:** 2026-07-15
- **Status:** Approved (design) → implementation plan bosqichiga o'tildi
- **Muallif:** UFL jamoasi (5 kishi) + Claude (Opus 4.8)
- **Repo:** `C:\Users\Oybek\Documents\Projects programming\StartUps\UFL`

---

## Qisqacha (Uzbek summary)

Biz o'zbek tilini yaxshi biladigan **lokal, offline LLM** quramiz. Baza model — **Gemma 4** (Google DeepMind, Apache 2.0). Uni o'zimiz tayyorlagan **toza o'zbekcha DATA** bilan CPT (continued pre-training) va SFT qilamiz. Bu bizga: to'liq offline ishlash, qaramlik yo'qligi, va kuchli privacy beradi (ayniqsa davlat tashkilotlari uchun muhim).

Bu hujjat — **DATA tayyorlash quvuri (pipeline)** dizayni. Vazifa: kitob va hujjatlardan (PDF, EPUB, DJVU, DOCX, FB2, TXT, HTML, hatto copy-paste matn) **faqat sof o'zbekcha (lotin)** matnni ajratib olish, muqova/mundarija/kolontitul/sahifa raqamlarini tashlash, **kirillni lotinga o'girish**, sifatsiz joylarni **drop qilish**, va natijada **toza `.txt` + statistika** (belgi va **Gemma token** hisobi bilan) berish.

**Asosiy tamoyil:** *shubha bo'lsa — tashla.* CPT uchun kam, lekin toza data — ko'p, lekin iflos datadan yaxshiroq.

---

## 1. Kontekst va maqsad

- **Loyiha:** UFL (Uzbek Foundational Language) — o'zbekcha lokal LLM. AI Tech Award / President Tech Award startup yo'nalishi uchun tayyorlanmoqda.
- **Baza model:** Gemma 4 (E2B/E4B · 12B · 26B MoE · 31B; Apache 2.0). Tokenizer — Gemma 4 SentencePiece.
- **DATA byudjeti (rasmlardan):** jami **1.5B token** = **1.2B o'zbekcha (lotin)** + **300M inglizcha retention**. Toza saqlash ~6 GB.
- **Bu quvurning vazifasi:** **CPT uchun o'zbekcha matn** yig'ish (1.2B token qismi). Har xil manbalardan (kitob, darslik, davlat hujjatlari, veb, ...) toza matn chiqarish.

### Uzbek CPT token taqsimoti (maqsad — pipeline shu byudjetga hisob yuritadi)

| Kategoriya (kalit) | % | Token | Config kaliti |
|---|---:|---:|---|
| Edited general web, news & magazines | 20% | 240M | `web_news` |
| Government, legal & public admin | 15% | 180M | `gov_legal` |
| Education, textbooks, science & academic | 15% | 180M | `education` |
| Wikipedia & reference | 15% | 180M | `reference` |
| Public-domain/licensed books & literature | 10% | 120M | `books` |
| Conversations, interviews, subtitles | 10% | 120M | `conversations` |
| Computing, technical docs & how-to | 10% | 120M | `technical` |
| Health, agriculture, business & finance | 5% | 60M | `domain_haf` |
| **Jami (Uzbek)** | **100%** | **1.2B** | |

> SFT (50k misol) — **bu quvurning vazifasi emas**, alohida ish. Pipeline faqat CPT matn extraktsiyasiga fokus (YAGNI).

---

## 2. Foydalanuvchilar va ish oqimi

- **Kim:** 5 kishilik IT jamoa. Har biri turli manbalardan kitob/hujjat yig'adi.
- **Qayerda ishlaydi:** Dev — Windows (Docker Desktop). Prod — Contabo VPS (Ubuntu 24.04), butun jamoa bitta instansiyani ishlatadi.
- **Oqim:**
  1. Foydalanuvchi faylni `data/input/<kategoriya>/` ga tashlaydi (yoki Web UI orqali yuklaydi, yoki matn paste qiladi).
  2. `ufl run` (CLI) yoki Web UI "Process" tugmasi.
  3. Pipeline har faylni tozalab, `data/output/` ga `.txt` yozadi; `data/reports/` ga statistika; `data/rejected/` ga tashlangan bo'laklar (audit uchun).
  4. Jamlanma dashboard byudjetga progress ko'rsatadi ("Books: 45M/120M").

---

## 3. Kirish (input) turlari

| Tur | Manba | Ingest yo'li |
|---|---|---|
| Raqamli PDF | matn tanlanadigan PDF | PyMuPDF text layer |
| Skaner PDF | rasm sahifalar | render → Tesseract OCR |
| DJVU | skaner kitoblar | DjVuLibre `djvutxt` (text layer) yoki `ddjvu` → OCR |
| EPUB | e-kitob | ebooklib → XHTML → matn |
| DOCX | Word hujjat | python-docx |
| FB2 | FictionBook | lxml (XML) |
| TXT | oddiy matn | to'g'ridan-to'g'ri |
| HTML / DevTools dump | veb-sahifa | trafilatura (asosiy kontent, boilerplate tashlanadi) |
| Paste (matn) | copy-paste | Web UI textarea / `--text` |

**Auto-detect:** har fayl uchun format aniqlanadi (kengaytma + magic bytes). PDF/DJVU uchun **har sahifa** "raqamli matn bormi?" tekshiriladi — bo'lsa text layer, bo'lmasa OCR. OCR sifati past bo'lsa (quyida "sifat gate") — o'sha sahifa/bo'lak **drop**.

---

## 4. Pipeline bosqichlari (bitta hujjat = 10 qadam)

```
1. DETECT     format + (PDF/DJVU) sahifa: raqamli yoki skaner
2. INGEST     matnni "bloklar" ga ajratib olish (sahifa/paragraf metadata bilan)
              skaner → OCR; OCR ishonchi past → o'sha blok DROP
3. STRUCTURE  muqova, titul, mualliflik, mundarija (TOC), kolontitul (running header/footer),
              sahifa raqamlari, izohlar/footnote raqamlari, adabiyotlar ro'yxati → olib tashlash
4. TRANSLIT   kirill → lotin (o'zbek qoidalari, §7)
5. LANGUAGE   har blok tili aniqlanadi; faqat O'ZBEKCHA qoladi, boshqasi DROP (§8)
6. QUALITY    buzuq OCR, juda qisqa, ortiqcha simvol/raqam, takroriy n-gram,
              "so'z emas" bloklar → DROP (§9)
7. NORMALIZE  Unicode NFC, bo'sh joy, apostrof (ASCII '), tirnoq, tinish belgilari (§10)
8. DEDUP      aynan va normallashtirilgan takror paragraf/hujjat → olib tashlash (§11)
9. WRITE      toza matn → data/output/<kategoriya>/<fayl>.txt (+ JSONL)
10. STATS     belgi, so'z, Gemma-token, taxminiy-token, char/token, drop%; byudjetga qo'shish
```

Har bosqich alohida modul — mustaqil test qilinadi. Bitta blok istalgan bosqichda "DROP" bo'lsa, `rejected/` ga sababi bilan yoziladi (audit + sozlash uchun).

---

## 5. Sifat falsafasi (CPT uchun kritik)

Foydalanuvchi talabi: **"toza, hech qanday muammosiz DATA"**. Shuning uchun:

- **Precision > Recall.** Shubhali blokni saqlashdan ko'ra tashlagan afzal.
- Har DROP qarori **loglanadi** (`rejected/`), shunda chegaralarni (thresholds) sozlab, nima ketayotganini ko'ramiz.
- Barcha chegaralar `config/ufl.toml` da — kod o'zgartirmasdan sozlanadi.
- Bitta yomon fayl **butun batch'ni to'xtatmasligi** kerak (izolyatsiya + xatolarni yutish, §13).

---

## 6. Struktura tozalash (front-matter, header/footer, sahifa raqami)

Gevristik (heuristic) yondashuv, `config` bilan sozlanadi:

- **Front-matter (kitob boshi):** titul, mualliflik huquqi, ISBN, nashriyot, bag'ishlov, mundarija (TOC). Aniqlash signallari: hujjat boshidagi joylashuv + kalit so'zlar (`ISBN`, `UDK`, `KBK`, `nashriyot`, `mundarija`, `tahrir`), qisqa qatorlar ko'pligi, sahifa/nuqta ketma-ketligi (TOC: "1.2 Bob .......... 34").
- **Kolontitul (running header/footer):** sahifalar bo'ylab **takrorlanadigan** yuqori/quyi qatorlar. Aniqlash: bir necha sahifada bir xil (yoki deyarli bir xil) qisqa qator → kolontitul → tashlanadi. PyMuPDF koordinatalari (Y-pozitsiya) bilan aniqlik oshadi.
- **Sahifa raqami:** sahifaning yuqori/quyi qismidagi yolg'iz son (yoki "- 12 -", "12-bet"). Regex + pozitsiya.
- **Footnote/izoh belgilari:** matn ichidagi ustki indeks raqamlar; sahifa oxiridagi izoh bloklari (ixtiyoriy: config bilan saqlash/tashlash).
- **Adabiyotlar ro'yxati / bibliografiya:** ko'p havola/raqam/lotin nomlar bo'lgan bloklar — CPT uchun shovqin, tashlanadi (config bilan).

> Bu bosqich "mukammal" bo'lolmaydi — maqsad **aksariyat shovqinni** olib tashlash. Qolgan noaniqliklarni §9 sifat gate ushlaydi.

---

## 7. Transliteratsiya (Kirill → Lotin, o'zbek)

Rasmiy o'zbek lotin alifbosi asosida, apostrof = **ASCII `'`** (config bilan `oʻ/gʻ` belgiga o'tsa bo'ladi).

### Asosiy jadval

| Kirill | Lotin | Izoh |
|---|---|---|
| А Б В Г Д | A B V G D | |
| Е е | E / Ye | so'z boshida yoki unlidan keyin → **Ye/ye**; undoshdan keyin → **e** |
| Ё ё | Yo yo | |
| Ж ж | J j | |
| З И Й К Л М Н | Z I Y K L M N | |
| О П Р С Т У | O P R S T U | |
| Ф | F | |
| Х х | X x | |
| Ц ц | Ts / s | so'z boshi/unlilar orasida → **ts**; aks holda → **s** (config) |
| Ч ч | Ch ch | |
| Ш ш | Sh sh | |
| Щ щ | Sh sh | |
| Ъ ъ | `'` | tutuq belgisi (masalan, маъно → ma'no) |
| Ь ь | (tashlanadi) | yumshoqlik belgisi — o'zbek lotinida yo'q |
| Э э | E e | |
| Ю ю | Yu yu | |
| Я я | Ya ya | |
| Ў ў | O' o' | |
| Қ қ | Q q | |
| Ғ ғ | G' g' | |
| Ҳ ҳ | H h | (Х=x dan farqli) |

### Maxsus qoidalar

- Bosh harf holati saqlanadi: `Ясин → Yasin`, `ЮНЕСКО → YUNESKO` (to'liq katta harf so'zda `Yu/Ya` emas, `YU/YA`).
- `нг` tabiiy ravishda `ng` bo'ladi.
- Aралашgan matn (bitta so'zda kirill+lotin) — buzuq deb belgilanadi (§9).
- **Test suite:** ma'lum kirill↔lotin juftliklari bilan (`tests/fixtures/translit_pairs.tsv`) — regressiyani ushlash uchun. Edge-case'lar (Е/Ye, Ц/ts/s, ъ) alohida test.

---

## 8. Til aniqlash (faqat o'zbekcha qoldirish)

**Gibrid yondashuv** (ishonchlilik uchun):

1. **fastText `lid.176`** (offline, `models/lid.176.ftz`, ~1 MB) — har blokka til ehtimoli.
2. **O'zbekcha gevristika** — o'zbek lotin uchun xos signallar: harf to'plami (`o'`, `g'`, `sh`, `ch`, `ng`), yuqori chastotali so'zlar (`va`, `bu`, `bilan`, `uchun`, `emas`, `ham`, `bo'lsa`, ...). Turkiy tillar (turk, ozarbayjon, qozoq) bilan chalkashmaslik uchun fastText'ni to'ldiradi.
3. **Qaror:** blok o'zbekcha deb tan olinadi, agar fastText `uz` yuqori bo'lsa **yoki** gevristika kuchli bo'lsa; aks holda **DROP**. Chegaralar `config` da.

- Blok darajasi: paragraf (yoki jumla) — shunda aralash hujjatdan o'zbekcha qismlar ajralib qoladi, ruscha/inglizcha tashlanadi.
- Juda qisqa bloklar (til aniqlash ishonchsiz) — gevristika + kontekst; shubhada DROP.

---

## 9. Sifat gate (quality filter)

Blok **DROP** bo'ladi, agar (chegaralar `config` da):

- **Uzunlik:** minimal belgidan qisqa (masalan < 25) yoki so'zlar juda kam.
- **Simvol nisbati:** harf bo'lmagan belgilar (raqam, tinish, `|`, `_`, ...) ulushi yuqori (masalan > 40%).
- **Buzuq OCR signali:** yolg'iz harflar ko'p, unli/undosh balansi buzuq, lug'atdan tashqari "so'z"lar ulushi yuqori.
- **Takror:** bir xil n-gram/so'z ketma-ket takrorlanishi (OCR yoki formatlash shovqini).
- **Alifbo aralashmasi:** bitta so'zda lotin+kirill+raqam aralash.
- **Katta harf/qatlam:** to'liq CAPS uzun bloklar (sarlavha/reklama), config bilan.
- **URL/email/kod ulushi** yuqori bloklar (config; "technical" kategoriyada yumshatiladi).

Har DROP → `rejected/` ga `{sabab, matn, fayl, sahifa}` bilan yoziladi.

---

## 10. Normalizatsiya

- Unicode **NFC**.
- Barcha apostrof-shakllar (`'`, `’`, `‘`, `ʻ`, `ʼ`, `` ` ``) → **ASCII `'`** (config: `oʻ/gʻ` ga o'tish mumkin).
- Tirnoqlar (`« »`, `" "`, `„ "`) → sozlanadigan standart (`"`).
- Bo'sh joy: bir nechta probel/tab → bitta; qatordagi ortiqcha bo'shliqlar; so'z bo'linishi (`so-\nz` → `soz`) tuzatiladi.
- Chiziqcha turlari (`—`, `–`, `-`) → standart.
- Ko'rinmas belgilar (zero-width, soft hyphen) → olib tashlanadi.
- Paragraf chegaralari saqlanadi (CPT uchun tabiiy matn oqimi muhim).

---

## 11. Deduplikatsiya

- **Aynan (exact):** paragraf va hujjat hash (SHA-1) — bir xillar bir marta.
- **Normallashtirilgan:** kichik harf + bo'sh joy siqilgan hash — kichik farqli takrorlar.
- **Near-dup (Faza 2+):** `datasketch` MinHash LSH — o'xshash paragraflar (ixtiyoriy, katta korpus uchun).
- Dedup **global** (barcha fayllar bo'ylab), holat SQLite'da saqlanadi.

---

## 12. Statistika va token hisobi

Har fayl va jamlanma uchun:

- **Belgi (character)** soni (toza matn).
- **So'z** soni.
- **Gemma-4 token** soni — `transformers` `AutoTokenizer` (config: `tokenizer.model_id` yoki lokal `models/` yo'li). Offline uchun tokenizer image ichida cache'lanadi.
- **Taxminiy token** — belgi-nisbati (config: `chars_per_token`, kalibrlanadi). Ikkalasi **birga** ko'rsatiladi.
- **char/token nisbati** (real).
- **Drop foizi** (qancha input tashlandi).
- **Kategoriya byudjetiga qo'shilish:** SQLite'da yig'iladi, dashboard "yig'ilgan/maqsad" ni ko'rsatadi.

> **Tokenizer offline strategiyasi:** birinchi build'da Gemma-4 tokenizer yuklab, `models/tokenizer/` ga saqlanadi → keyin internetsiz ishlaydi. Agar yuklab bo'lmasa (masalan gated), pipeline **taxminiy hisob** bilan davom etadi va ogohlantiradi (hech qачон to'xtamaydi).

---

## 13. Ishonchlilik va xatolarni boshqarish

Foydalanuvchi talabi: **"hech qanday texnik muammo bo'lmasin, ayniqsa Python'da."**

- **Docker-first:** dev + prod bir xil image (Python **3.12**, barcha tizim kutubxonalari ichida). Windows'dagi Python 3.14 wheel muammolari umuman yo'qoladi.
- **Pinned dependencies:** `requirements.txt` da aniq versiyalar (reproducible).
- **Fayl izolyatsiyasi:** har fayl `try/except` ichida; bitta fayl xatosi butun batch'ni to'xtatmaydi — xato loglanadi, keyingi faylga o'tiladi.
- **Resumable:** qayta ishlangan fayllar SQLite'da belgilanadi; `ufl run` qайта ishga tushsa, tugallanganlarni o'tkazib yuboradi.
- **Structured logging:** har fayl uchun status (ok/skip/error), sabab.
- **Optional deps degradatsiyasi:** Tesseract yo'q → skaner fayllar skip + ogohlantirish (crash emas). DjVuLibre yo'q → `.djvu` skip. Tokenizer yo'q → taxminiy hisob.

---

## 14. Arxitektura (modullar)

```
UFL/
  Dockerfile · docker-compose.yml · .dockerignore · .env.example
  requirements.txt (pinned) · pyproject.toml · README.md
  config/ufl.toml                    # sozlamalar + kategoriya byudjetlari + chegaralar
  models/                            # Gemma-4 tokenizer + lid.176.ftz (oflayn)
  data/  input/ output/ rejected/ reports/
  src/ufl/
    __init__.py
    config.py                        # ufl.toml ni yuklash + validatsiya
    cli.py                           # `ufl run|stats|version` (typer)
    pipeline.py                      # bitta hujjat orkestратsiyasi
    logging_setup.py
    ingest/
      __init__.py  detect.py  base.py
      pdf.py  djvu.py  epub.py  docx.py  fb2.py  html.py  txt.py
      ocr.py                         # Tesseract wrapper (uzb, uzb_cyrl)
    clean/
      __init__.py
      structure.py                   # front-matter, header/footer, sahifa raqami
      transliterate.py               # kirill → lotin
      language.py                    # fastText + gevristika
      quality.py                     # sifat gate
      normalize.py                   # NFC, apostrof, bo'sh joy
      dedup.py                       # hash + MinHash
    stats/
      __init__.py  tokens.py  report.py  budget.py
    store/
      __init__.py  db.py             # SQLite (books, blocks, dedup, budget)
    web/                             # Faza 3
      app.py (FastAPI)  routes.py  auth.py
      templates/  static/
  tests/
    test_transliterate.py  test_language.py  test_quality.py
    test_structure.py  test_normalize.py  test_pipeline.py
    fixtures/  translit_pairs.tsv  sample_*.{pdf,txt,html}
```

**Modul chegaralari:** har modul aniq bitta vazifa, sof funksiya (input → output), yon ta'sirsiz (I/O faqat `pipeline.py`, `store/`, `cli.py` da). Shu tufayli har biri alohida test qilinadi.

---

## 15. Ma'lumot modeli (SQLite)

- `books(id, path, category, format, sha1, status, pages, chars, words, gemma_tokens, est_tokens, dropped_pct, processed_at, error)`
- `dedup_hashes(hash, book_id)` — global dedup.
- `budget(category, target_tokens, collected_tokens)` — dashboard.
- (Web, Faza 3) `jobs(id, status, created_at, ...)`.

---

## 16. Chiqish (output) formatlari

- **`.txt`** — toza matn (asosiy CPT format), har kategoriya papkasida.
- **`.jsonl`** — `{text, source, category, meta}` (HF `datasets` bilan mos, kelajakda `datatrove`/scale uchun).
- **`reports/<fayl>.json`** — per-book statistika.
- **`reports/summary.json` + `summary.md`** — jamlanma byudjet progress.

---

## 17. Deployment (Docker) — qisqacha (to'liq: `docs/DOCKER.md`)

- **Windows (dev):** Docker Desktop + WSL2. `docker compose up`.
- **Contabo VPS (Ubuntu 24.04):** Docker Engine + compose plugin (rasmiy apt usuli — `docs/DOCKER.md` da qadam-baqadam). Web UI Nginx reverse-proxy orqasida, **parol/IP himoya** bilan (privacy).
- **Volumes:** `data/` va `models/` host'da (persist), image faqat kod + tizim libs.
- **Yangilash:** `git pull && docker compose build && docker compose up -d`.

---

## 18. Web UI (Faza 3)

- **FastAPI + uvicorn**, Jinja2 templates + minimal JS (build-step yo'q → ishonchli).
- Sahifalar: (1) Upload/paste + kategoriya tanlash, (2) Jarayon holati, (3) Natijalar (per-book stats, `.txt` yuklab olish), (4) **Byudjet dashboard** (progress barlar).
- Auth: oddiy login/parol (jamoa uchun) yoki IP allowlist. HTTPS (Nginx).
- Jarayon: FastAPI BackgroundTasks + SQLite job store (v1). Scale kerak bo'lsa RQ/Redis (keyin).

---

## 19. Test strategiyasi

- **Unit:** transliterate (juftliklar), language (o'zbek/rus/ingliz/turk namunalari), quality (drop qoidalari), structure (TOC/kolontitul namunalari), normalize.
- **Integration:** kichik namuna PDF/TXT/HTML → to'liq pipeline → kutilgan toza chiqish + stats.
- **Fixtures:** `tests/fixtures/` da kichik namunalar (kirill kitob parchasi, aralash tilli, skaner-simulyatsiya).
- **Regression:** transliteratsiya va sifat qoidalari uchun oltin (golden) fayllar.

---

## 20. Risklar va yechimlar

| Risk | Yechim |
|---|---|
| Python 3.14 wheel yo'qligi | Docker + Python 3.12 (dev+prod bir xil) |
| Gemma-4 tokenizer gated/topilmaydi | config'da model_id; lokal cache; topilmasa taxminiy hisobga degradatsiya |
| OCR sifati past (skaner) | ishonch chegarasi + sifat gate → shubhali sahifa DROP |
| Transliteratsiya edge-case (Е/Ye, Ц) | qoidalar + test suite (golden pairs) |
| DJVU Windows'da qiyin | DjVuLibre Docker image ichida (Linux) — muammosiz |
| Turkiy tillar bilan chalkashish | fastText + o'zbekcha gevristika gibrid |
| Bitta yomon fayl batch'ni buzadi | fayl izolyatsiyasi + xato yutish + resumable |
| VPS'da Docker yo'q, tajriba kam | `docs/DOCKER.md` — qadam-baqadam, copy-paste buyruqlar |

---

## 21. Fazalar (qisqacha — batafsil: `docs/IMPLEMENTATION_PLAN.md`)

- **Faza 0 — Skelet:** repo, Docker, config, pinned deps, `ufl version` ishlaydi.
- **Faza 1 — Yadro pipeline (⭐ eng muhim):** barcha ingest + tozalash + translit + til + sifat + dedup + `.txt` + stats + CLI + testlar.
- **Faza 2 — Statistika/byudjet:** SQLite store + per-book & jamlanma hisobot + byudjet progress.
- **Faza 3 — Web UI:** FastAPI panel + VPS deploy.

---

## 22. Non-goals (v1 doirasidan tashqari)

- SFT ma'lumot generatsiyasi (alohida ish).
- Modelni train qilish/infra (bu quvur faqat DATA tayyorlaydi).
- Inglizcha 300M retention yig'ish (keyin; bu quvur o'zbekchaga fokus).
- Mukammal 100% struktura tozalash (maqsad — sifat gate bilan birga "yetarlicha toza").
- Ko'p-foydalanuvchi hisob boshqaruvi / murakkab RBAC (oddiy auth yetarli).
