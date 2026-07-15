# UFL — Docker image (Windows dev va Ubuntu VPS uchun bir xil)
FROM python:3.12-slim

# Tizim kutubxonalari:
#   tesseract-ocr + uzb/uzb_cyrl til paketlari -> skaner kitoblarni OCR qilish
#   djvulibre-bin                              -> .djvu fayllardan matn/rasm chiqarish
#   poppler-utils                              -> PDF yordamchi vositalar (fallback)
#   build-essential                            -> ba'zi Python paketlarini ishonchli o'rnatish uchun zaxira
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-uzb \
    tesseract-ocr-uzb-cyrl \
    djvulibre-bin \
    poppler-utils \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Avval faqat requirements.txt nusxalanadi -> kod o'zgarsa ham pip install qayta ishlamaydi (layer cache)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Paket metadata + kod + testlar
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY tests/ ./tests/

# Editable o'rnatish: docker-compose src/ ni volume qilib mount qiladi,
# shunda kod o'zgarganda image qayta qurish shart emas.
RUN pip install --no-cache-dir -e .

# Config (docker-compose runtime'da ./config volume bilan override qiladi)
COPY config/ ./config/

# Ishlash uchun kerakli papkalar (volume orqali host bilan bog'lanadi)
RUN mkdir -p data/input data/output data/rejected data/reports models

# Eslatma: hozircha root sifatida ishlaydi (CLI, tashqi tarmoqqa ochiq emas).
# Faza 3 (Web UI, tarmoqqa ochiq) qo'shilganda non-root user + UID moslash qo'shiladi.

CMD ["ufl", "version"]
