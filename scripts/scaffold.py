from pathlib import Path

import typer

app = typer.Typer()

SRC_DIR = Path(__file__).resolve().parent.parent / "src"

SUBMODULE_STRUCTURE = [
    Path("."),
    Path("models"),
    Path("dto"),
    Path("repositories"),
    Path("services"),
    Path("use_cases"),
    Path("endpoints"),
    Path("endpoints/v1"),
    Path("endpoints/v1/routes"),
    Path("endpoints/v1/schemas"),
    Path("endpoints/v1/schemas/request"),
    Path("endpoints/v1/schemas/response"),
]


@app.command()
def submodule(name: str) -> None:
    """Scaffold an empty vertical-slice submodule under src/."""
    root = SRC_DIR / name

    for relative_dir in SUBMODULE_STRUCTURE:
        directory = root / relative_dir
        directory.mkdir(parents=True, exist_ok=True)

        init_file = directory / "__init__.py"
        if init_file.exists():
            typer.echo(
                f"⏭️  skipped {init_file.relative_to(SRC_DIR.parent)} (already exists)"
            )
        else:
            init_file.touch()
            typer.echo(f"✅ created {init_file.relative_to(SRC_DIR.parent)}")


if __name__ == "__main__":
    app()
