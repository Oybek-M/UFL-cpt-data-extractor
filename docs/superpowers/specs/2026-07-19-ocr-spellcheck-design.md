# OCR-manba imlo tuzatish (`finalize-corpus` 5-bosqich) — Design

## Muammo

`strip_garbage_tokens` (avvalgi feature) faqat **shaklan noto'g'ri** narsalarni (ramz,
izolyatsiyalangan yakka harf, raqam-harf yopishish) tutadi. Lekin ba'zi OCR-chiqindi
**to'g'ri shaklda, lekin noto'g'ri harf bilan** keladi — masalan real fayldagi `kayta`
so'zi aslida `qayta` bo'lishi kerak edi (loyiha rahbari tomonidan tasdiqlangan: "kayta"
o'zbek tilida mavjud so'z emas).

Sabab (transliteratsiya jadvaliga asoslangan taxmin, `src/ufl/clean/transliterate.py`):
Kirill matnda OCR "қ" (qa) harfini "к" (ka) deb noto'g'ri o'qiydi (ikkalasi vizual
jihatdan juda o'xshash, pastki "quyruqcha" bilangina farqlanadi) — bu keyin
transliteratsiya orqali "q" o'rniga "k" bo'lib Lotin matnga o'tadi. `strip_garbage_tokens`
bunday so'zlarni tutolmaydi, chunki ular tarkibida hech qanday g'ayrioddiy belgi yo'q —
faqat harflar, to'g'ri uzunlikda, to'g'ri joyda.

## Qamrov (Scope)

Yangi 5-bosqich `finalize-corpus`ga (dedup → PII → rename → denoise → **spellcheck**).
**Faqat retroaktiv** — yig'ish (ingestion) pipeline'iga integratsiya qilinmaydi, chunki
ishonchli lug'atni qurish uchun butun tozza korpusni ko'rish kerak, bu faqat finalize
vaqtida to'liq mavjud.

- **Ishonchli lug'at manbai**: **faqat HuggingFace-manba fayllar** (`corpus-a/b/c__...`
  yoki hali qayta nomlanmagan `tahrirchi_...`/`yakhyo_...`). Web-crawl (`web_news`) va
  ziyouz — hech biri ishonchli lug'atga qo'shilmaydi, chunki ularning ikkalasida ham
  ekstraksiya/OCR muammosi bo'lishi mumkin (loyiha rahbari tomonidan aniq ko'rsatilgan).
- **Tekshiriladigan/tuzatiladigan qamrov**: **HF-manba BO'LMAGAN barcha fayllar** — nafaqat
  ziyouz, balki boshqa web-saytlardan olingan (`crawl` orqali yig'ilgan) barcha
  `web_news` fayllari ham (loyiha rahbari aniq ko'rsatgan: "yana bir saytdan olgan
  data'larimiz bor edi").

## Yondashuv

1. **Ishonchli chastota-lug'at qurish** — barcha HF-manba fayllarni o'qib, har bir
   (kichik harfga o'tkazilgan) so'zning kamida bir marta uchraganini belgilaydi
   (oddiy `set[str]`, hozircha faqat mavjud/yo'qligi tekshiriladi — chastota soni
   kelajakda kerak bo'lishi mumkin, lekin hozir shart emas).
2. **Tekshirish** — HF-manba bo'lmagan har bir faylning har bir qatoridagi har bir
   so'zi (kichik harfda) ishonchli lug'atda qidiriladi. Topilmasa — "shubhali".
3. **Tuzatish nomzodini qidirish** — shubhali so'z uchun, 5 ta ma'lum OCR-chalkashlik
   juftligi bo'yicha (`q↔k`, `g'↔g`, `h↔x`, `o'↔u`, `i↔y`), har ikki yo'nalishda
   (jami 10 ta nomzod) so'zdagi **mos belgining barcha uchrashuvi bir yo'la**
   almashtiriladi (masalan "kayta"dagi yagona `k` — agar so'zda 2 ta `k` bo'lsa,
   ikkalasi ham birdek `q`ga almashtiriladi, alohida-alohida emas — OCR bitta so'z
   ichida bir xil harfni tizimli ravishda bir xil noto'g'ri o'qiydi deb faraz
   qilinadi). Har nomzod ishonchli lug'atda qidiriladi.
4. **Yuqori-ishonch qoidasi**: agar almashtirishlar orasida **aynan bitta noyob**
   natija ishonchli lug'atda topilsa — asl so'z o'sha natija bilan **almashtiriladi**
   (katta-kichik harf holati saqlanadi). Agar **hech qanday** yoki **bir nechta har xil**
   natija topilsa — so'zga **tegilmaydi** (noaniqlik — "shubha bo'lsa tashla" emas,
   bu yerda "shubha bo'lsa tegma", chunki noto'g'ri tuzatish yangi xato yaratadi).
5. **MiniMax — ixtiyoriy** (`--use-minimax` bayrog'i, standart: o'chiq). Faqat qoidaga
   asoslangan tuzatish topa olmagan so'zlar uchun, va **har bir noyob so'z faqat bir
   marta** (necha marta uchraganidan qat'iy nazar, butun korpus bo'yicha) so'raladi.
   MiniMax'dan "bu so'z ehtimol OCR xatosi va to'g'ri shakli X" yoki "ANIQ EMAS"
   javobi kutiladi; faqat aniq javob bo'lsa qo'llaniladi.

## `_CONFUSION_PAIRS` (dastlabki, tasdiqlangan)

```python
_CONFUSION_PAIRS: list[tuple[str, str]] = [
    ("q", "k"), ("g'", "g"), ("h", "x"), ("o'", "u"), ("i", "y"),
]
```

Har juftlik ikkala yo'nalishda ham sinaladi (masalan `q↔k` — so'zdagi har bir `q`ni
`k`ga VA har bir `k`ni `q`ga almashtirib ko'riladi), chunki OCR xatosi qaysi tomonga
qarab yo'nalganini oldindan bilib bo'lmaydi.

## Arxitektura

### Yangi: `src/ufl/finalize/hf_rename.py`ga kichik qo'shimcha

```python
def is_hf_sourced_filename(filename: str) -> bool:
    """Fayl HF dataset'dan kelib chiqqanmi — hali qayta nomlanmagan
    (masalan tahrirchi_uz-crawl__...) yoki qayta nomlangan (corpus-a__...)
    holatlarning ikkalasini ham tekshiradi."""
    match = _SHARD_FILENAME_RE.match(filename)
    if match is None:
        return False
    slug = match.group("slug")
    return slug in _SLUG_TO_DATASET_ID or slug in DATASET_ALIAS.values()
```

(Bu yerga qo'yilishi sababi: HF-manbani aniqlash mantig'i allaqachon shu faylda,
takrorlanishning oldini olish uchun shu yerga qo'shiladi, alohida modulga emas.)

### Yangi: `src/ufl/finalize/spellcheck.py`

```python
def build_trusted_dictionary(output_dir: Path) -> set[str]:
    """HF-manba fayllardagi barcha (kichik harfli) so'zlarni to'playdi."""

def find_correction(word: str, trusted: set[str]) -> str | None:
    """5 ta chalkashlik juftligi bo'yicha yagona ishonchli nomzodni qidiradi.
    Topilmasa yoki bir nechta nomzod bo'lsa — None."""

def correct_line(
    line: str, trusted: set[str], *, on_correction: Callable[[str, str], None] | None = None,
) -> str:
    """Qatordagi har so'zni tekshiradi, topilgan tuzatishlarni qo'llaydi,
    har bir tuzatish uchun on_correction(asl, tuzatilgan) chaqiradi."""
```

### `finalize-corpus`ga 5-bosqich

- Faqat `--use-minimax` bayrog'i bilan MiniMax ishlatiladi (standart: o'chiq).
- Ishonchli lug'at bir marta quriladi (barcha HF-manba fayllar bo'yicha).
- Har bir HF-manba BO'LMAGAN faylning har qatori tekshiriladi.
- Har bir topilgan tuzatish **alohida log qatorida** chop etiladi:
  `[bold]Tuzatildi:[/bold] kayta -> qayta (fayl: ..., qator: N)`.
- Oxirida: jami tekshirilgan so'z, jami tuzatilgan so'z, jami fayl, va (agar
  `--use-minimax` yoqilgan bo'lsa) MiniMax'ga yuborilgan noyob so'z soni.

## Xatolarni boshqarish

Mavjud bosqichlar naqshiga mos: fayl o'qib/yozib bo'lmasa — o'sha faylni o'tkazib
yuborib ogohlantirish, jarayon to'xtamaydi. MiniMax so'rovi xato bersa — o'sha so'z
tuzatilmagan holda qoldiriladi, jarayon davom etadi.

## Testlash

TDD, mavjud naqshga mos:
- `tests/test_finalize_hf_rename.py` — `is_hf_sourced_filename` uchun testlar (asl
  nom, qayta nomlangan alias, notanish fayl).
- `tests/test_finalize_spellcheck.py` (yangi) — `build_trusted_dictionary` (faqat
  HF-manba fayllardan so'z to'plashi), `find_correction` (aynan `kayta`→`qayta`
  misoli, noaniq holat — ikkita nomzod — tuzatilmasligi, hech qanday nomzod
  topilmasa tuzatilmasligi), `correct_line` (on_correction callback chaqirilishi).
- `tests/test_cli_finalize_corpus.py` — 5-bosqichning to'liq CLI integratsiyasi
  (dry-run/`--apply`, MiniMax bayrog'isiz standart holat).
