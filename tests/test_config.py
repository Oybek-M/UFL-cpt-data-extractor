from pathlib import Path

from ufl.config import Config


def test_config_loads_default_file():
    config = Config.load(Path("config/ufl.toml"))
    assert config.budget.categories["books"] == 120_000_000
    assert sum(config.budget.categories.values()) == 1_200_000_000
    assert config.tokenizer.chars_per_token > 0
    assert config.normalize.apostrophe_mode in {"ascii", "unicode"}


def test_config_has_human_readable_category_labels():
    config = Config.load(Path("config/ufl.toml"))
    for category in config.budget.categories:
        assert category in config.budget.category_labels
        assert config.budget.category_labels[category]


def test_config_missing_file_raises(tmp_path):
    missing = tmp_path / "does_not_exist.toml"
    try:
        Config.load(missing)
        assert False, "FileNotFoundError kutilgan edi"
    except FileNotFoundError:
        pass
