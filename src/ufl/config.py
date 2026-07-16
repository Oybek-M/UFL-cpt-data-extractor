"""UFL konfiguratsiyasini config/ufl.toml dan yuklash va validatsiya qilish."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_CONFIG_PATH = Path("config/ufl.toml")


class PathsConfig(BaseModel):
    input: Path
    output: Path
    rejected: Path
    reports: Path
    models_dir: Path
    db: Path = Path("data/ufl.db")


class BudgetConfig(BaseModel):
    categories: dict[str, int]
    category_labels: dict[str, str] = {}


class TokenizerConfig(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: str
    local_dir: Path
    chars_per_token: float = Field(gt=0)


class NormalizeConfig(BaseModel):
    apostrophe_mode: str
    quote_style: str


class QualityConfig(BaseModel):
    min_chars: int
    min_words: int
    max_non_letter_ratio: float
    max_repeated_ngram_ratio: float
    max_upper_ratio: float
    max_url_ratio: float


class LanguageConfig(BaseModel):
    min_confidence: float
    min_heuristic_score: float
    fasttext_model_path: Path


class OcrConfig(BaseModel):
    languages: str
    min_confidence: int
    dpi: int


class StructureConfig(BaseModel):
    header_footer_min_repeats: int
    detect_toc: bool
    detect_bibliography: bool


class DedupConfig(BaseModel):
    enabled: bool
    near_dup_enabled: bool


class CrawlConfig(BaseModel):
    output_dir: Path = Path("data/collected")
    request_timeout: float = 60.0
    request_delay: float = 0.6
    root_refresh_seconds: int = 300
    idle_sleep_seconds: int = 10
    shard_limit_bytes: int = 52_428_800
    user_agent: str = "UFL-Collector/1.0 (+https://ufl.ibos.uz)"
    min_local_chars: int = 700
    min_clean_chars: int = 250


class MiniMaxConfig(BaseModel):
    model: str = "MiniMax-M2.7-highspeed"
    url: str = "https://api.minimax.io/v1/chat/completions"
    min_confidence: float = 0.65


class Config(BaseModel):
    paths: PathsConfig
    budget: BudgetConfig
    tokenizer: TokenizerConfig
    normalize: NormalizeConfig
    quality: QualityConfig
    language: LanguageConfig
    ocr: OcrConfig
    structure: StructureConfig
    dedup: DedupConfig
    crawl: CrawlConfig = CrawlConfig()
    minimax: MiniMaxConfig = MiniMaxConfig()

    @classmethod
    def load(cls, path: Path | str = DEFAULT_CONFIG_PATH) -> "Config":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config fayl topilmadi: {path}")
        with path.open("rb") as f:
            raw = tomllib.load(f)
        config = cls.model_validate(raw)
        return config.with_env_overrides()

    def with_env_overrides(self) -> "Config":
        """.env / muhit o'zgaruvchilari config qiymatlarini override qiladi."""
        model_id = os.environ.get("UFL_TOKENIZER_MODEL_ID")
        if model_id:
            self.tokenizer.model_id = model_id
        return self
