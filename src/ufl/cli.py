"""UFL CLI — `ufl version|run|stats`."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from ufl import __version__
from ufl.config import Config
from ufl.logging_setup import setup_logging

app = typer.Typer(name="ufl", help="Uzbek CPT data pipeline — kitoblardan toza matn ajratib olish.")
console = Console()


@app.command()
def version() -> None:
    """UFL versiyasini chiqarish."""
    console.print(f"ufl [bold green]{__version__}[/bold green]")


@app.command()
def run(
    input_path: Path = typer.Argument(..., help="Fayl yoki papka yo'li (masalan data/input)"),
    config_path: Path = typer.Option(Path("config/ufl.toml"), "--config", help="Config fayl yo'li"),
) -> None:
    """Berilgan papkadagi fayllarni pipeline orqali qayta ishlash."""
    setup_logging()
    config = Config.load(config_path)

    if not input_path.exists():
        console.print(f"[bold red]Xato:[/bold red] '{input_path}' topilmadi.")
        raise typer.Exit(code=1)

    files = [p for p in input_path.rglob("*") if p.is_file()] if input_path.is_dir() else [input_path]
    console.print(f"[bold]{len(files)}[/bold] fayl topildi: {input_path}")
    console.print(
        "[yellow]Pipeline hali implement qilinmagan (Faza 1 da qo'shiladi).[/yellow]\n"
        f"Config yuklandi: {len(config.budget.categories)} kategoriya, "
        f"tokenizer={config.tokenizer.model_id}"
    )


@app.command()
def stats(
    config_path: Path = typer.Option(Path("config/ufl.toml"), "--config", help="Config fayl yo'li"),
) -> None:
    """Jamlanma statistika va byudjet progressni ko'rsatish."""
    setup_logging()
    config = Config.load(config_path)
    console.print(
        "[yellow]Statistika hisobot hali implement qilinmagan (Faza 2 da qo'shiladi).[/yellow]\n"
        f"Byudjet kategoriyalari: {list(config.budget.categories.keys())}"
    )


if __name__ == "__main__":
    app()
