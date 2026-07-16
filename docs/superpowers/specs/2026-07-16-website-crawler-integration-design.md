# UFL — Web-sayt Crawler integratsiyasi (dizayn spetsifikatsiyasi)

> Sana: 2026-07-16
> Manba tahlili: `website-to-txt-collector/continuous_collector.py` (1710 qator, real test qilingan)
> Maqsad: butun web-saytlardan avtomatik, ko'p-strategiyali, resumable, robots-hurmat qiluvchi
> maqola yig'ish qobiliyatini UFL ichiga qo'shish — har bir maqola UFL'ning mavjud
> tozalash pipeline'idan (til/sifat/dedup/transliteratsiya) o'tadi.

---

## 1. Motivatsiya va asosiy g'oya

Hozirgi UFL **bittalab** manba bilan ishlaydi: bitta fayl yoki bitta URL → bitta `.txt`.
CPT uchun 1.2B token yig'ish shu tezlikda juda sekin. `website-to-txt-collector` esa
**butun saytni** avtomatik crawl qiladi: sitemap + havola-kashfiyoti orqali minglab
maqola URL'ini topadi, eng yangi sanadan boshlab har birini yuklab, maqola tanasini
ajratadi.

**Bo'linish (separation of concerns):**

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. KASHFIYOT + EKSTRAKSIYA  (collector'dan port qilinadi)          │
│    robots.txt → sitemap → URL queue (newest-first) →              │
│    HTML yuklab olish → ko'p-strategiyali nomzod ekstraksiya        │
│    (JSON-LD / Nuxt / Next.js / DOM-evristika)                     │
├─────────────────────────────────────────────────────────────────┤
│ 2. TANLASH  (ixtiyoriy MiniMax + local qoidalar)                  │
│    noaniq layout'da to'g'ri nomzodni tanlash + trash bloklarni    │
│    aniqlash. MiniMax ixtiyoriy booster.                           │
├─────────────────────────────────────────────────────────────────┤
│ 3. TOZALASH + FILTR  (UFL'ning MAVJUD pipeline'i)                  │
│    transliteratsiya → TIL ANIQLASH (faqat o'zbekcha!) → sifat →   │
│    normalizatsiya → dedup                                         │
├─────────────────────────────────────────────────────────────────┤
│ 4. CHIQISH + HISOB  (collector'ning bundled writer'i + UFL budget)│
│    juft chiqish (.txt + .jsonl), oy-bo'yicha bundling, ~50MiB     │
│    shard, crash-safe atomik yozuv → UFL budget/kategoriya hisobi  │
└─────────────────────────────────────────────────────────────────┘
```

**Eng muhim qaror:** collector maqola tanasini *topadi*; UFL uni *tozalaydi va filtrlaydi*.
Collector'ning o'z `clean_content_blocks` va `DatasetWriter` mantig'i ba'zi joyda
saqlanadi (bundling/atomik yozuv), lekin til-filtri, transliteratsiya, sifat gate,
dedup — UFL'niki. Bu UFL'ning "faqat sof o'zbekcha" falsafasini crawl'ga ham tatbiq etadi
(collector o'zi til-filtri qilmaydi — bu bizning qo'shimchamiz).

---

## 2. Foydalanuvchi tasdiqlagan qarorlar (2026-07-16)

1. **Ko'lam:** to'liq crawler (butun-sayt) + MiniMax integratsiyasi ham. Foydalanuvchi
   MiniMax uchun API kalit oladi.
2. **MiniMax:** qo'shiladi, lekin **ixtiyoriy** (kalit `.env`/env orqali beriladi; kalitsiz
   local rejimda ishlaydi). Kalitsiz ham to'liq foydali bo'lishi shart.
3. **Kategoriya:** ikkala rejim ham bo'lsin:
   - **Manual:** foydalanuvchi crawl boshlaganda kategoriya tanlaydi → butun sayt shu
     kategoriyaga (tegilmaydi).
   - **Auto:** MiniMax har bir maqolani UFL'ning 8 kategoriyasidan biriga ajratadi
     (faqat kalit bo'lsa; kalitsiz auto rejim `web_news`ga standart tushadi + ogohlantiradi).
4. **Boshqaruv:** ikkalasi ham — CLI (`ufl crawl ...`) **va** web UI (boshlash/to'xtatish + progress).

---

## 3. Manba tool tahlili (nima port qilinadi)

`continuous_collector.py` bitta faylda quyidagi bloklardan iborat. UFL'ga port qilinganda
UFL-uslubidagi modullarga bo'linadi (§4).

| Manba qismi (qatorlar) | Vazifa | UFL destinatsiyasi |
|---|---|---|
| `canonical_url`, `belongs_to_site`, `collectable_url`, `date_from_url`, `url_hash`, `host_key`, `domain_folder` (96-181) | URL kanonizatsiya + SSRF xavfsizlik + sayt-a'zolik | `crawl/urls.py` (UFL `ingest/url.py`dagi SSRF bilan birlashtiriladi) |
| `clean_lines`, `fragment_blocks`, `fragment_text`, `obvious_trash_block`, `clean_content_blocks` (184-282) | HTML → tartibli matn bloklari | `crawl/blocks.py` |
| `Candidate`, `candidates_from_page`, `dom_candidate`, `extract_metadata`, `probable_article_page`, `recursive_json_values` (313-868) | **TOJ: ko'p-strategiyali nomzod ekstraksiya** (JSON-LD/Nuxt/Next/DOM) | `crawl/candidates.py` |
| `WebClient`, `RobotsPolicy` (605-645) | rate-limit sessiya + robots.txt | `crawl/web_client.py` |
| `parse_sitemap` (652-669) | sitemap XML/gzip parser | `crawl/sitemap.py` |
| `State` (337-603) | SQLite: sitemaps/pages/adapters/ai_batches + recovery | `crawl/state.py` |
| `DatasetWriter` (878-1120) | crash-safe juft chiqish + bundling + sharding | `crawl/writer.py` (UFL clean pipeline chaqiradi) |
| `MiniMax` (1123-1346) | AI kalibratsiya | `crawl/minimax.py` (+ auto-kategoriya kengaytmasi) |
| `Collector` (1385-1657) | orkestratsiya (sitemap→page→ai loop) | `crawl/collector.py` |

**Diqqat — nimalarni ATMAYMIZ:** collector'ning `clean_content_blocks` faqat obvious-trash
(reklama/caption) tashlaydi va dublikat bloklarni oladi. UFL bunga qo'shimcha: **til aniqlash
(faqat o'zbekcha)**, **transliteratsiya (kirill→lotin)**, **sifat gate**, **normalizatsiya**,
**persistent dedup**. Ya'ni collector'ning tozalashi UFL pipeline'iga *kirish*, yakuniy emas.

---

## 4. UFL package strukturasi (yangi `src/ufl/crawl/`)

```
src/ufl/crawl/
  __init__.py
  urls.py          # canonical_url, belongs_to_site, collectable_url, date_from_url,
                   #   host_key, domain_folder  (ingest/url.py SSRF bilan birlashtirilgan)
  blocks.py        # clean_lines, fragment_blocks, fragment_text, obvious_trash_block
  candidates.py    # Candidate, candidates_from_page, dom_candidate, extract_metadata,
                   #   probable_article_page, recursive_json_values
  web_client.py    # WebClient (rate-limit), RobotsPolicy
  sitemap.py       # parse_sitemap
  state.py         # CrawlState (per-domain SQLite: sitemaps/pages/adapters/ai_batches)
  writer.py        # BundledWriter — UFL clean pipeline'dan o'tgan matnni juft chiqishga yozadi
  minimax.py       # MiniMaxClient — kalibratsiya + auto-kategoriya (ixtiyoriy)
  collector.py     # Collector — orkestratsiya, UFL pipeline'ga ulaydi
  categorize.py    # kategoriya tanlash: manual (o'zgarmas) yoki auto (MiniMax)
```

**UFL mavjud modullaridan qayta ishlatiladi (o'zgartirilmaydi yoki minimal):**
- `clean/transliterate.py` — `to_latin`
- `clean/language.py` — `is_uzbek` (crawl uchun til-filtri MAJBURIY)
- `clean/quality.py` — `assess`
- `clean/normalize.py` — `normalize`
- `clean/dedup.py` — `DeduplicationStore` (crawl uchun persistent variant kerak, §7)
- `stats/tokens.py`, `stats/budget.py` — token/budjet hisobi
- `store/db.py` — UFL budget DB (crawl accepted maqolalarni shu yerga yozadi)
- `config.py` — yangi `[crawl]` va `[minimax]` seksiyalari

---

## 5. Maqola oqimi (article flow) — batafsil

Bitta crawl qadamida bitta `discovered` sahifa quyidagicha kechadi:

```
next_page() (newest-first)
  → robots.allowed? → yo'q bo'lsa access_denied
  → WebClient.get(url)  (rate-limited, robots-hurmat)
  → Content-Type html? → yo'q bo'lsa extraction_failed
  → BeautifulSoup → extract_metadata (title, published)
  → _discover_links (yangi URL'larni queue'ga)   [crawl kengayadi]
  → candidates_from_page (JSON-LD/Nuxt/Next/DOM nomzodlar, skorlangan)
  → nomzod tanlash:
       adapter bor?  → kESHlangan method bilan tanla
       MiniMax kalit bor + noaniq?  → AI kalibratsiya (candidate + trash + complete?)
       kalitsiz + method ∈ {jsonld,nuxt,next} + yetarli uzun?  → local qabul
       aks holda  → ai_pending (kalit kutadi) yoki reject
  → tanlangan nomzod bloklari
       ▼▼▼  BU YERDA UFL PIPELINE BOSHLANADI  ▼▼▼
  → har blok: to_latin (translit) → is_uzbek? (YO'Q bo'lsa blokni tashla)
              → assess (sifat) → normalize → dedup.check_and_add
  → qolgan bloklar birlashtiriladi (title + body)
  → agar toza tana < 250 belgi → quality_rejected
  → kategoriya: manual (o'zgarmas) yoki auto (MiniMax classify)
       ▲▲▲  UFL PIPELINE TUGADI  ▲▲▲
  → BundledWriter.write_article → juft .txt+.jsonl (atomik, bundled)
  → UFL Store.record (budget: kategoriya += tokens)
  → pages.status = 'done'
```

**Muhim:** til-filtri blok darajasida ishlaydi — bir maqolada o'zbekcha + ruscha aralash
bo'lsa, faqat o'zbekcha bloklar qoladi ("shubha bo'lsa — tashla" falsafasi). Agar til-filtridan
keyin tana juda qisqa qolsa, maqola `quality_rejected` bo'ladi.

---

## 6. MiniMax integratsiyasi (ikki rol)

MiniMax **ixtiyoriy**. Kalit `MINIMAX_API_KEY` env / `.env` orqali. Kalitsiz — barcha
MiniMax bosqichlari o'tkazib yuboriladi, local qoidalar ishlaydi.

### 6.1 Rol A — Kalibratsiya (collector'dan)
Noaniq layout'da: sahifa **labellangan matn bloklariga** aylantiriladi (xom HTML EMAS,
maxfiylik uchun), MiniMax'ga yuboriladi. MiniMax qaytaradi: `is_article`, `candidate_id`,
`title_block_id`, `date_block_id`, `content_block_ids`, `trash_block_ids`, `complete`,
`confidence`, `reason`. Natija adapter sifatida kESHlanadi (shu domen uchun keyingi
sahifalarga qayta ishlatiladi). Batafsil validatsiya (§ manba 1247-1305): noto'g'ri
page_id/candidate_id/title_block → xato; `confidence < 0.65` → rad; `complete=false` → truncated deb rad.

### 6.2 Rol B — Auto-kategoriya (YANGI, UFL uchun)
Foydalanuvchi crawl'da **auto** rejim tanlasa: har bir qabul qilingan maqolaning toza
matni (yoki title + birinchi ~500 belgi) MiniMax'ga yuboriladi, u UFL'ning 8 kategoriyasidan
(`web_news, gov_legal, education, reference, books, conversations, technical, domain_haf`)
birini qaytaradi. Prompt aniq: faqat ro'yxatdan tanlash, tushuntirishsiz. Noto'g'ri/noaniq
javob → `web_news` (standart) + log.

**Xavfsizlik (manba 85-qatordan):** API kalit faqat `Authorization` header'da yuboriladi,
hech qachon DB yoki log'ga yozilmaydi. Kalit `.gitignore`da (`.env`). Rate-limit (429) va
5xx → eksponensial backoff bilan retry; 401/403 → `minimax_blocked` (qayta urinmaydi).

---

## 7. Persistent dedup (crawl uchun kengaytma)

UFL'ning hozirgi `DeduplicationStore` — in-memory (bitta process ichida). Uzoq crawl uchun:
- **Process ichida:** in-memory dedup yetarli (bitta uzluksiz crawl).
- **Restart'lar aro:** collector'ning URL-darajasidagi `pages` jadvali (UNIQUE url) +
  `output_items` (yozilgan sahifalar) qayta yozishni oldini oladi. Kontent-darajasidagi
  cross-restart dedup v1 uchun shart emas (URL-dedup + domen-ichi kontent-hash yetarli).
- **Kelajak (v2):** `crawl/state.py`da `content_hashes` jadvali (SHA-256) qo'shib, kirill→lotin
  normalizatsiyadan keyingi tana hash'ini saqlash — saytlararo dublikatni ushlaydi.

---

## 8. Konfiguratsiya (`config/ufl.toml` yangi seksiyalar)

```toml
[crawl]
request_timeout = 60
request_delay = 0.6          # bir xost uchun so'rovlar orasidagi minimal kechikish (s)
root_refresh_seconds = 300   # sitemap qayta tekshirish oralig'i
idle_sleep_seconds = 10
shard_limit_bytes = 52428800 # 50 MiB — bundling chegarasi
user_agent = "UFL-Collector/1.0 (+https://ufl.ibos.uz)"
min_local_chars = 700        # kalitsiz local qabul uchun minimal nomzod uzunligi
min_clean_chars = 250        # tozalashdan keyin minimal tana uzunligi

[minimax]
enabled = false              # env MINIMAX_API_KEY bo'lsa avtomatik yoqiladi
model = "MiniMax-M2.7-highspeed"
url = "https://api.minimax.io/v1/chat/completions"
min_confidence = 0.65
```

`.env.example`ga: `MINIMAX_API_KEY=` (bo'sh) qo'shiladi.

---

## 9. CLI interfeysi

```bash
# Butun saytni crawl qilish (uzluksiz, newest-first)
ufl crawl https://kun.uz --category web_news
ufl crawl https://daryo.uz --category auto        # MiniMax auto-klassifikatsiya
ufl crawl https://gov.uz --category gov_legal --max-articles 500
ufl crawl https://kun.uz --once                   # queue bo'shaguncha ishlab to'xta

# Crawl holati
ufl crawl-status https://kun.uz                   # yig'ilgan/kutayotgan/rad hisobi
```

- `--category`: 8 kategoriyadan biri **yoki** `auto`.
- Kalit: `MINIMAX_API_KEY` env'dan (CLI'ga yozilmaydi — log/history xavfsizligi).
- `--max-articles N`: N ta qabul qilingandan keyin to'xta (test/limit uchun).
- `--once`, `--max-steps`: test/debug (collector'dagi kabi).
- Docker'da: `docker compose run --rm ufl ufl crawl https://kun.uz --category web_news`.
  Uzoq ishlash uchun VPS'da alohida detached konteyner (§11).

---

## 10. Web UI

**Yangi sahifa: "Saytdan yig'ish (crawl)"** (`/crawl` GET forma + POST start).
- Maydonlar: sayt URL, kategoriya (dropdown: 8 kategoriya + "Auto (MiniMax)"), `max-articles`
  (ixtiyoriy limit).
- POST `/crawl/start` → crawl'ni **fon jarayoni** sifatida ishga tushiradi (`subprocess`
  yoki `multiprocessing` — web-server so'rov thread'ini bloklamasin; oldingi OCR muzlash
  darsini takrorlamaslik uchun). Har domen uchun bitta faol crawl (qayta boshlansa — resume).
- **Progress sahifasi** `/crawl/status/{domain}`: crawl state DB'dan o'qiydi — `done`,
  `discovered` (kutayotgan), `ai_pending`, `quality_rejected`, `failed` hisobi + oxirgi
  yig'ilgan maqolalar + kategoriya bo'yicha token o'sishi. Auto-refresh (meta-refresh yoki
  kichik polling).
- POST `/crawl/stop/{domain}` → fon jarayoniga to'xtash signali (keyingi qadamda xavfsiz
  to'xtaydi — atomik yozuv tufayli ma'lumot yo'qolmaydi).
- Dashboard byudjet jadvali crawl'dan kelgan tokenlarni ham ko'rsatadi (mavjud budget
  hisobiga qo'shiladi).

**Xavfsizlik:** crawl fon jarayoni web thread'da EMAS — bu oldingi "og'ir fayl butun
ilovani muzlatdi" muammosining aynan takrorlanishini oldini oladi.

---

## 11. Docker / VPS deploy

- **Windows dev:** `docker compose run --rm ufl ufl crawl ...` — sinov uchun `--once`/`--max-articles`.
- **VPS (uzoq ishlash):** crawl kunlab ishlashi mumkin. Variantlar:
  1. **Detached konteyner:** `docker compose run -d --name ufl-crawl-kunuz ufl ufl crawl https://kun.uz --category web_news` — mustaqil, `restart` siyosati bilan.
  2. **Web-boshqariladigan fon jarayoni:** `web` konteyneri ichida `subprocess` — bitta konteyner, lekin crawl web bilan resurs bo'lishadi.
  - Tavsiya: v1 uchun **CLI + detached konteyner** (ishonchli), web UI progress'ni o'sha
    domen state DB'dan o'qiydi. Web'dan "start" tugmasi kichik crawl'lar uchun `subprocess`.
- **Volume:** crawl chiqishi `data/collected/<domain>/` ostida (UFL `data/` volume'ida,
  host'da qoladi). `.gitignore`ga `data/collected/**` qo'shiladi.
- **Rate-limit / odob:** `request_delay` (0.6s) + robots.txt hurmat — server yoki maqsad-saytga
  zarar bermaslik uchun. VPS IP'dan ko'p sayt crawl qilinsa — IP bloklanish xavfini hisobga ol.

---

## 12. Xavfsizlik, huquq va maxfiylik

1. **SSRF:** `canonical_url` ichki/xususiy IP, localhost, credential-URL, juda uzun URL'ni
   rad etadi (collector'da bor, UFL `ingest/url.py` bilan birlashtiriladi).
2. **robots.txt:** har doim hurmat qilinadi (`RobotsPolicy.allowed`).
3. **API kalit:** faqat header'da, DB/log'ga yozilmaydi, `.gitignore`da.
4. **ToS / litsenziya (MUHIM):** har bir maqsad-sayt matn/data-mining'ga ruxsat berishini
   jamoa tekshirishi kerak. Repo public bo'ladi va Tech Award uchun — CPT korpusi huquqiy
   toza bo'lishi shart. Bu spec texnik imkoniyat beradi; **huquqiy javobgarlik foydalanuvchida**.
   README/DOCKER.md'ga aniq eslatma qo'shiladi.
5. **Rate-limit:** odobli scraping — maqsad-serverni ortiqcha yuklamaslik.

---

## 13. UFL'ning o'ziga 1-2 yaxshilanish (crawl'dan tashqari)

Manba tahlili va sessiya davomidagi kuzatuvlar asosida:

### Yaxshilanish A — `/url` bitta-sahifa ekstraksiyasini kuchaytirish
Hozirgi `ingest/html.py` faqat trafilatura ishlatadi. Yangi `crawl/candidates.py`
ko'p-strategiyali ekstraktor (JSON-LD/Nuxt/Next/DOM skorlash) — zamonaviy JS-og'ir o'zbek
saytlarida ancha mustahkam. `/url` va HTML-fayl ingest shu yangi ekstraktorni ishlatadigan
qilib yangilanadi (trafilatura fallback sifatida qoladi). Bu Faza 4.2'dan tabiiy chiqadi.

### Yaxshilanish B — Wiki/CMS boilerplate qoldig'ini tozalash
Sessiyada kuzatilgan: Wikipedia'dan "[tahrir | manbasini tahrirlash]" kabi tahrir-havola
qoldiqlari toza matnga sizib o'tdi. `clean/structure.py` yoki `clean/quality.py`ga bunday
CMS-artefakt naqshlari (`[tahrir]`, `[edit]`, `[manbasini tahrirlash]`, `[изменить]` va h.k.)
uchun filtr qo'shiladi.

---

## 14. Fazalar (Sonnet TDD bilan implement qiladi)

Har faza: RED (test yoz) → GREEN (implement) → real-input verifikatsiya → commit.
Har faza mustaqil commit. MiniMax fazalari kalitsiz ham ishlashini ta'minlash uchun DI
(dependency injection) pattern — testlar soxta MiniMax injektlaydi.

| Faza | Nomi | Asosiy natija |
|---|---|---|
| **4.1** | Crawl poydevori | `urls.py` (SSRF birlashtirilgan), `web_client.py` (rate-limit+robots), `sitemap.py` — testlar bilan |
| **4.2** | Ko'p-strategiyali ekstraksiya | `blocks.py` + `candidates.py` (JSON-LD/Nuxt/Next/DOM) — real HTML fixture'lar bilan test. **+ Yaxshilanish A** (`/url` shu ekstraktorga o'tadi) |
| **4.3** | Crawl state DB | `state.py` (sitemaps/pages/adapters, recovery, resumable) — test |
| **4.4** | Collector + UFL pipeline ulash | `collector.py` — kashfiyot→ekstraksiya→**UFL clean pipeline**→ til-filtri. Local rejim (MiniMax'siz). Real sayt bilan `--once` test |
| **4.5** | Bundled writer + budget | `writer.py` (crash-safe juft chiqish, bundling, sharding) + UFL `Store`/budget hisobi |
| **4.6** | CLI `ufl crawl` | `crawl`/`crawl-status` buyruqlari — test + real Docker run |
| **4.7** | MiniMax (ixtiyoriy) | `minimax.py` — kalibratsiya (Rol A) + auto-kategoriya (Rol B). Kalitsiz o'tkazib yuboriladi. DI bilan test |
| **4.8** | Web UI crawl | `/crawl` forma + `/crawl/start|stop|status` (fon jarayoni, web'ni bloklamaydi) — brauzerda verifikatsiya |
| **4.9** | Yaxshilanish B + hujjatlar | CMS-boilerplate filtri (`[tahrir]` va h.k.) + DOCKER.md/README crawl bo'limi + ToS eslatmasi |
| **4.10** | VPS deploy | Detached crawl konteyner + web progress + `data/collected` volume/gitignore |

**Baholangan hajm:** katta feature (~10 faza). Sonnet har fazani mustaqil bajaradi;
MiniMax fazalari (4.7) kalit kelgunча local rejimda to'liq test qilinadi.

---

## 15. Ochiq savollar / kelajak (v2)

- Saytlararo kontent-dedup (`content_hashes` jadvali) — v2.
- Bir vaqtda ko'p domen parallel crawl (hozircha ketma-ket, bitta process bitta domen).
- Auto-kategoriya sifatini o'lchash (MiniMax klassifikatsiya aniqligi) — namuna-QA.
- Bepul til-model (fastText) + Gemma tokenizer VPS'da yuklab olinsa, crawl chiqishi aniq
  token bilan hisoblanadi (hozir taxminiy).
