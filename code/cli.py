"""CLI entry point — interactive setup wizard + three execution modes.

Modes:
  1. Single ticket   — triage one ticket, show rich result panel
  2. Batch CSV       — process support_tickets/support_tickets.csv with progress bar
  3. Interactive REPL — type tickets one by one

Non-interactive (scripting) flags:
  --ticket / --csv / --interactive  — select mode directly
  --provider / --key / --model-low / --model-medium / --model-high  — skip wizard

Usage (run from repo root):
  python code/cli.py
  python code/cli.py --ticket "I can't log in" --company HackerRank
  python code/cli.py --csv support_tickets/support_tickets.csv
  python code/cli.py --interactive
  python code/cli.py --provider gemini --key AIza... --ticket "..."
"""
from __future__ import annotations

import argparse
import csv
import getpass
import json
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

# Allow running as `python code/cli.py` from repo root or as `python -m cli`
_CODE_DIR = Path(__file__).resolve().parent
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Column,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from config import settings
from domain.types import TicketState
from pipeline import PipelineFactory

console = Console()

# ── Provider / Model Defaults ──────────────────────────────────────────────────

PROVIDER_DEFAULTS = {
    "gemini": {
        "label": "Google Gemini",
        "description": "Full pipeline — Flash-Lite / Flash / Pro",
        "badge": "[bold green]RECOMMENDED[/bold green]",
        "low": "gemini-3.1-flash-lite-preview",
        "medium": "gemini-3-flash-preview",
        "high": "gemini-3.1-pro-preview",
        "low_label": "gemini-3.1-flash-lite-preview",
        "medium_label": "gemini-3-flash-preview",
        "high_label": "gemini-3.1-pro-preview",
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "description": "Haiku / Sonnet / Opus",
        "badge": "",
        "low": "claude-haiku-3-5",
        "medium": "claude-sonnet-4-5",
        "high": "claude-opus-4-5",
        "low_label": "claude-haiku-3-5",
        "medium_label": "claude-sonnet-4-5",
        "high_label": "claude-opus-4-5",
    },
    "openai": {
        "label": "OpenAI",
        "description": "GPT-4o-mini / GPT-4o / O3",
        "badge": "",
        "low": "gpt-4o-mini",
        "medium": "gpt-4o",
        "high": "o3",
        "low_label": "gpt-4o-mini",
        "medium_label": "gpt-4o",
        "high_label": "o3",
    },
}

PROVIDER_KEYS = ["gemini", "anthropic", "openai"]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _run_ticket_with_state(pipeline, ticket: str, company: str, subject: str):
    """Run pipeline and return (output_dict, state)."""
    state = TicketState(ticket=ticket, subject=subject, company=company)
    output = pipeline.run(state)
    return output.to_dict(), state


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _write_csv(rows: list[dict], path: Path) -> None:
    fieldnames = ["status", "product_area", "response", "justification", "request_type"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _show_result_panel(result: dict, state) -> None:
    """Display a beautifully formatted result panel."""
    status = result.get("status", "").upper()

    if status == "REPLIED":
        status_badge = "[bold white on green] REPLIED [/bold white on green]"
    else:
        status_badge = "[bold white on dark_orange3] ESCALATED [/bold white on dark_orange3]"

    product_area = result.get("product_area", "—")
    request_type = result.get("request_type", "—")
    response_text = result.get("response", "—")
    justification = result.get("justification", "—")

    # Top meta grid — status badge + request type side by side
    meta = Table.grid(padding=(0, 2))
    meta.add_column(min_width=16)
    meta.add_column(min_width=22)
    meta.add_row(status_badge, f"[dim]{request_type}[/dim]")
    meta.add_row("[dim]Status[/dim]", "[dim]Request Type[/dim]")

    lines: list = [
        meta,
        "",
        Text(f"Product Area: {product_area}", style="bright_cyan"),
        "",
        Rule(style="dim"),
        "",
        Text("Response", style="bold white"),
        "",
        Text(response_text, style="white"),
        "",
        Rule(style="dim"),
        "",
        Text("Justification", style="bold white"),
        "",
        Text(justification, style="dim"),
    ]

    panel_content = Group(*lines)

    console.print()
    console.print(Panel(
        panel_content,
        title="[bold bright_white]Triage Result[/bold bright_white]",
        border_style="bright_blue",
        box=box.ROUNDED,
        padding=(1, 2),
    ))


def _validate_api_key(provider: str, api_key: str) -> Optional[str]:
    """Try a minimal call to validate the key. Returns error string or None on success."""
    try:
        if provider == "gemini":
            from google import genai
            client = genai.Client(api_key=api_key)
            list(client.models.list())
        elif provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            client.models.list()
        elif provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            client.models.list()
        return None
    except Exception as exc:
        return str(exc)


def _fetch_models(provider: str, api_key: str) -> list[str]:
    """Fetch real model names from the provider API. Falls back to PROVIDER_DEFAULTS on error."""
    try:
        if provider == "gemini":
            from google import genai
            client = genai.Client(api_key=api_key)
            models = list(client.models.list())
            names = []
            for m in models:
                name = getattr(m, "name", "") or ""
                supported = getattr(m, "supported_generation_methods", []) or []
                if "generateContent" in supported and "embedding" not in name.lower():
                    names.append(name)
            return sorted(names)

        elif provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            response = client.models.list()
            names = [m.id for m in response.data]
            return sorted(names)

        elif provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            response = client.models.list()
            names = [
                m.id for m in response.data
                if any(x in m.id.lower() for x in ["gpt", "o1", "o3", "o4"])
            ]
            return sorted(names, reverse=True)

    except Exception:
        pass

    # Fallback to hardcoded defaults
    p = PROVIDER_DEFAULTS[provider]
    return [p["high"], p["medium"], p["low"]]


def _select_models_from_list(provider: str, models: list[str]) -> Tuple[str, str, str]:
    """Show fetched model list as a numbered menu, let user pick LOW/MEDIUM/HIGH."""
    p = PROVIDER_DEFAULTS[provider]
    label = PROVIDER_DEFAULTS[provider]["label"]

    # Sensible defaults: first=HIGH, second=MEDIUM, third=LOW
    default_high = models[0] if len(models) > 0 else p["high"]
    default_medium = models[1] if len(models) > 1 else p["medium"]
    default_low = models[2] if len(models) > 2 else p["low"]

    default_high_idx = 1
    default_medium_idx = 2 if len(models) > 1 else 1
    default_low_idx = 3 if len(models) > 2 else (2 if len(models) > 1 else 1)

    # Build model list table
    model_table = Table(
        title=f"Available Models (live from {label} API)",
        box=box.ROUNDED,
        title_style="bold bright_white",
        show_header=False,
        padding=(0, 2),
        border_style="bright_blue",
    )
    model_table.add_column("Num", style="bold cyan", width=5)
    model_table.add_column("Model", style="white")

    for idx, name in enumerate(models, 1):
        model_table.add_row(str(idx), name)

    console.print()
    console.print(model_table)
    console.print()

    def _pick(tier: str, agents: str, default_idx: int, default_name: str) -> str:
        raw = Prompt.ask(
            f"  [bold]Select {tier} model[/bold] [dim]({agents})[/dim]",
            default=str(default_idx),
        ).strip()
        # Direct model name (not a number)
        if not raw.isdigit():
            return raw or default_name
        idx = int(raw) - 1
        if 0 <= idx < len(models):
            return models[idx]
        return default_name

    low_model = _pick(
        "LOW   ", "Router · Critic · Compressor", default_low_idx, default_low
    )
    medium_model = _pick(
        "MEDIUM", "Triage · Responder          ", default_medium_idx, default_medium
    )
    high_model = _pick(
        "HIGH  ", "Responder — high-risk only  ", default_high_idx, default_high
    )

    console.print()
    console.print(f"  [bold green]✓[/bold green] LOW    → [bright_cyan]{low_model}[/bright_cyan]")
    console.print(f"  [bold green]✓[/bold green] MEDIUM → [bright_cyan]{medium_model}[/bright_cyan]")
    console.print(f"  [bold green]✓[/bold green] HIGH   → [bright_cyan]{high_model}[/bright_cyan]")
    console.print()

    return low_model, medium_model, high_model


# ── Setup Wizard ───────────────────────────────────────────────────────────────

def _show_banner() -> None:
    title = Text()
    title.append("⚡ ", style="bold yellow")
    title.append("Support Triage Agent", style="bold bright_white")
    title.append(" ⚡", style="bold yellow")

    subtitle = Text("HackerRank Orchestrate · May 2026", style="dim cyan", justify="center")
    tagline = Text(
        "Multi-domain AI triage  ·  HackerRank  ·  Claude  ·  Visa",
        style="italic dim",
        justify="center",
    )

    content = Group(
        Align.center(title),
        Align.center(subtitle),
        Text(""),
        Align.center(tagline),
    )

    console.print()
    console.print(Panel(
        content,
        border_style="bold bright_blue",
        box=box.DOUBLE_EDGE,
        padding=(1, 6),
        expand=False,
    ))
    console.print()


def _select_provider() -> str:
    table = Table(
        title="Select AI Provider",
        box=box.ROUNDED,
        title_style="bold bright_white",
        show_header=False,
        padding=(0, 2),
        border_style="bright_blue",
    )
    table.add_column("Num", style="bold cyan", width=4)
    table.add_column("Provider", style="bold", min_width=20)
    table.add_column("Models", style="dim", min_width=38)
    table.add_column("Badge", min_width=15)

    for idx, key in enumerate(PROVIDER_KEYS, 1):
        p = PROVIDER_DEFAULTS[key]
        table.add_row(str(idx), p["label"], p["description"], p["badge"])

    console.print(table)

    while True:
        choice = Prompt.ask(
            "[bold]  Provider[/bold]",
            choices=["1", "2", "3"],
            show_choices=True,
        ).strip()
        idx = int(choice) - 1
        if 0 <= idx < len(PROVIDER_KEYS):
            selected = PROVIDER_KEYS[idx]
            console.print(f"  [bold green]✓[/bold green] Selected [bold]{PROVIDER_DEFAULTS[selected]['label']}[/bold]\n")
            return selected


def _collect_api_key(provider: str) -> str:
    label = PROVIDER_DEFAULTS[provider]["label"]
    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        console.print(f"  [bold]Enter your {label} API key[/bold] [dim](hidden)[/dim]")
        try:
            api_key = getpass.getpass("  Key: ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Cancelled.[/yellow]")
            sys.exit(0)

        if not api_key:
            console.print("  [red]Key cannot be empty. Please try again.[/red]\n")
            continue

        with console.status("[dim]Validating API key…[/dim]", spinner="aesthetic"):
            error = _validate_api_key(provider, api_key)

        if error is None:
            console.print("  [bold green]✓[/bold green] API key validated successfully.\n")
            return api_key
        else:
            console.print(f"  [red]✗ Validation failed:[/red] {error}")
            if attempt < max_attempts:
                console.print(f"  [dim]({max_attempts - attempt} attempt(s) remaining)[/dim]\n")
            else:
                console.print("\n  [red bold]Too many failed attempts. Exiting.[/red bold]")
                sys.exit(1)

    sys.exit(1)  # unreachable but satisfies type checker


def _select_mode() -> str:
    table = Table(
        title="What would you like to do?",
        box=box.ROUNDED,
        title_style="bold bright_white",
        show_header=False,
        padding=(0, 2),
        border_style="cyan",
    )
    table.add_column("Num", style="bold cyan", width=4)
    table.add_column("Mode", style="bold", min_width=24)
    table.add_column("Description", style="dim")

    table.add_row("1", "⚡ Single ticket", "triage one ticket now")
    table.add_row("2", "📄 Batch CSV", "process support_tickets/support_tickets.csv")
    table.add_row("3", "💬 Interactive REPL", "type tickets one by one")

    console.print(table)

    choice = Prompt.ask(
        "[bold]  Mode[/bold]",
        choices=["1", "2", "3"],
        show_choices=True,
    ).strip()
    console.print()
    return {"1": "single", "2": "batch", "3": "interactive"}[choice]


def run_setup_wizard(
    forced_provider: Optional[str] = None,
    forced_key: Optional[str] = None,
    forced_low: Optional[str] = None,
    forced_medium: Optional[str] = None,
    forced_high: Optional[str] = None,
) -> Tuple[str, str, str, str, str]:
    """Run the interactive setup wizard.

    Returns (provider, api_key, low_model, medium_model, high_model).
    Skips steps where values are supplied via forced_* arguments.
    Order: provider → key → models (key is needed for live model fetch).
    """
    _show_banner()

    # Step 1 — Provider
    if forced_provider and forced_provider.lower() in PROVIDER_KEYS:
        provider = forced_provider.lower()
        console.print(f"  [bold green]✓[/bold green] Provider: [bold]{PROVIDER_DEFAULTS[provider]['label']}[/bold]\n")
    else:
        provider = _select_provider()

    # Step 2 — API Key (before models — needed for live model fetch)
    if forced_key:
        api_key = forced_key
        console.print("  [bold green]✓[/bold green] API key supplied via --key flag.\n")
    else:
        api_key = _collect_api_key(provider)

    # Step 3 — Fetch models live, then let user select
    if forced_low and forced_medium and forced_high:
        low_model, medium_model, high_model = forced_low, forced_medium, forced_high
    else:
        with console.status("[dim]Fetching available models…[/dim]", spinner="aesthetic"):
            model_list = _fetch_models(provider, api_key)
        low_model, medium_model, high_model = _select_models_from_list(provider, model_list)

    return provider, api_key, low_model, medium_model, high_model


# ── Execution Modes ────────────────────────────────────────────────────────────

def _build_pipeline(provider: str, api_key: str, low: str, medium: str, high: str):
    with console.status(
        "[dim cyan]Initializing pipeline agents…[/dim cyan]",
        spinner="bouncingBall",
        spinner_style="bright_blue",
    ):
        pipeline = PipelineFactory.create_with_config(provider, api_key, low, medium, high)
    console.print(
        f"  [bold green]✓[/bold green] Pipeline ready — [dim]{provider.title()} · {low[:28]}[/dim]\n"
    )
    return pipeline


def run_single(pipeline, ticket: str = "", company: str = "", subject: str = "") -> bool:
    """Triage a single ticket. Returns True if user wants to triage another."""
    if not ticket:
        console.print("[bold]  Enter ticket details[/bold]")
        try:
            ticket = Prompt.ask("  Ticket text ").strip()
            if not ticket:
                console.print("  [yellow]Empty ticket. Skipping.[/yellow]")
                return False
            company = Prompt.ask("  Company     ", default="").strip()
            subject = Prompt.ask("  Subject     ", default="").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Cancelled.[/yellow]")
            return False
        console.print()

    result: Optional[dict] = None
    state = None
    with console.status("[dim]Processing ticket…[/dim]", spinner="aesthetic"):
        try:
            result, state = _run_ticket_with_state(pipeline, ticket, company, subject)
        except Exception as exc:
            console.print(Panel(
                f"[red]✗ Error:[/red] {exc}",
                title="[bold red]Pipeline Error[/bold red]",
                border_style="red",
                box=box.ROUNDED,
            ))
            return False

    _show_result_panel(result, state)
    return True


def run_batch(pipeline, input_path: Path, output_path: Path) -> int:
    """Batch mode — process CSV with progress bar. Returns exit code."""
    if not input_path.exists():
        console.print(Panel(
            f"[red]CSV file not found:[/red] {input_path}",
            title="[bold red]Error[/bold red]",
            border_style="red",
            box=box.ROUNDED,
        ))
        return 1

    rows = _read_csv(input_path)
    total = len(rows)

    results: list[dict] = []
    replied = escalated = errors = 0

    console.print(f"  [bold]Processing {total} tickets…[/bold]\n")

    with Progress(
        SpinnerColumn("aesthetic"),
        TextColumn("[progress.description]{task.description}", table_column=Column(ratio=2)),
        BarColumn(bar_width=None, style="bright_blue", complete_style="bright_green", finished_style="green"),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        expand=True,
    ) as progress:
        task = progress.add_task("Triaging…", total=total)

        for idx, row in enumerate(rows, start=1):
            ticket = (row.get("ticket") or row.get("Issue") or "").strip()
            subject = (row.get("subject") or row.get("Subject") or "").strip()
            company = (row.get("company") or row.get("Company") or "").strip()
            label = (subject or ticket)[:55]

            progress.update(task, description=f"[dim][{idx:02d}/{total}][/dim] {label}")

            try:
                result, _ = _run_ticket_with_state(pipeline, ticket, company, subject)
                results.append(result)
                status = result.get("status", "")
                if status == "replied":
                    replied += 1
                    progress.console.print(
                        f"  [{idx:02d}/{total}] {label[:50]!r:<55} [green]✓ replied[/green]"
                    )
                else:
                    escalated += 1
                    progress.console.print(
                        f"  [{idx:02d}/{total}] {label[:50]!r:<55} [yellow]↑ escalated[/yellow]"
                    )
            except Exception as exc:
                errors += 1
                progress.console.print(
                    f"  [{idx:02d}/{total}] {label[:50]!r:<55} [red]✗ error: {exc}[/red]"
                )
                results.append({
                    "status": "escalated",
                    "product_area": "error",
                    "response": "An internal error occurred. Your ticket has been escalated.",
                    "justification": f"Pipeline error: {exc}",
                    "request_type": "product_issue",
                })

            progress.advance(task)

            if idx < total:
                time.sleep(0.5)

    _write_csv(results, output_path)

    # Summary panel
    summary_grid = Table.grid(padding=(0, 3))
    summary_grid.add_column()
    summary_grid.add_column()
    summary_grid.add_column()
    summary_grid.add_column()
    summary_grid.add_row(
        f"[bold]Total[/bold]  [bright_cyan]{total}[/bright_cyan]",
        f"[bold]Replied[/bold]  [green]{replied}[/green]",
        f"[bold]Escalated[/bold]  [yellow]{escalated}[/yellow]",
        f"[bold]Errors[/bold]  [red]{errors}[/red]",
    )

    console.print()
    console.print(Panel(
        Group(
            summary_grid,
            "",
            Text(f"Output written to: {output_path}", style="dim"),
        ),
        title="[bold bright_white]Batch Complete[/bold bright_white]",
        border_style="green",
        box=box.ROUNDED,
        padding=(1, 2),
    ))
    return 0


def run_interactive(pipeline) -> int:
    """Interactive REPL — type tickets one by one."""
    console.print(Panel(
        "[bold]Interactive REPL[/bold]\nType [bright_cyan]exit[/bright_cyan] or press [bold]Ctrl-C[/bold] to quit.",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(0, 2),
    ))
    console.print()

    while True:
        try:
            ticket = Prompt.ask("  [bold]Ticket text[/bold]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Bye.[/yellow]")
            return 0

        if ticket.lower() in {"exit", "quit", "q", ""}:
            if not ticket:
                continue
            console.print("[yellow]Bye.[/yellow]")
            return 0

        try:
            company = Prompt.ask("  Company    ", default="").strip()
            subject = Prompt.ask("  Subject    ", default="").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Bye.[/yellow]")
            return 0

        console.print()
        with console.status("[dim]Processing ticket…[/dim]", spinner="aesthetic"):
            try:
                result, state = _run_ticket_with_state(pipeline, ticket, company, subject)
            except Exception as exc:
                console.print(Panel(
                    f"[red]✗ Error:[/red] {exc}",
                    title="[bold red]Pipeline Error[/bold red]",
                    border_style="red",
                    box=box.ROUNDED,
                ))
                continue

        _show_result_panel(result, state)

        try:
            again = Confirm.ask("  [bold]Next ticket?[/bold]", default=True)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Bye.[/yellow]")
            return 0

        if not again:
            console.print("[yellow]Bye.[/yellow]")
            return 0
        console.print()

    return 0


# ── Argument Parser ────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="HackerRank Support Triage Agent — CLI interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python code/cli.py                                         # full interactive wizard
  python code/cli.py --ticket "Can't log in" --company HackerRank
  python code/cli.py --csv support_tickets/support_tickets.csv
  python code/cli.py --interactive
  python code/cli.py --provider gemini --key AIza... --ticket "..."
        """,
    )

    # Mode flags (optional — wizard selects mode if none given)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--ticket", "-t", metavar="TEXT", help="Single ticket text.")
    mode.add_argument("--csv", "-f", metavar="FILE", help="Batch mode: process a CSV file.")
    mode.add_argument("--interactive", "-i", action="store_true", help="Interactive REPL mode.")

    # Ticket options
    parser.add_argument("--company", "-c", metavar="NAME", default="", help="Company name.")
    parser.add_argument("--subject", "-s", metavar="TEXT", default="", help="Ticket subject.")
    parser.add_argument("--output", "-o", metavar="FILE", default="", help="Output CSV path.")

    # Provider / key / model overrides (skip wizard steps)
    parser.add_argument("--provider", metavar="PROVIDER", default="", help="gemini | anthropic | openai")
    parser.add_argument("--key", metavar="KEY", default="", help="API key (skips key prompt).")
    parser.add_argument("--model-low", metavar="MODEL", default="", help="LOW-tier model name.")
    parser.add_argument("--model-medium", metavar="MODEL", default="", help="MEDIUM-tier model name.")
    parser.add_argument("--model-high", metavar="MODEL", default="", help="HIGH-tier model name.")

    return parser


# ── Entry Point ────────────────────────────────────────────────────────────────

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # Run setup wizard (skipping steps for which flags were provided)
    try:
        provider, api_key, low_model, medium_model, high_model = run_setup_wizard(
            forced_provider=args.provider or None,
            forced_key=args.key or None,
            forced_low=args.model_low or None,
            forced_medium=args.model_medium or None,
            forced_high=args.model_high or None,
        )
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Cancelled.[/yellow]")
        return 0

    # Build pipeline from wizard output
    try:
        pipeline = _build_pipeline(provider, api_key, low_model, medium_model, high_model)
    except Exception as exc:
        console.print(Panel(
            f"[red]Failed to initialise pipeline:[/red] {exc}",
            title="[bold red]Startup Error[/bold red]",
            border_style="red",
            box=box.ROUNDED,
        ))
        return 1

    # Determine mode (from flag or wizard)
    if args.ticket:
        run_single(pipeline, ticket=args.ticket, company=args.company, subject=args.subject)
        return 0

    if args.csv:
        input_path = Path(args.csv).resolve()
        output_path = Path(args.output).resolve() if args.output else settings.paths.output_csv
        return run_batch(pipeline, input_path, output_path)

    if args.interactive:
        return run_interactive(pipeline)

    # No mode flag — ask user
    try:
        mode = _select_mode()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Cancelled.[/yellow]")
        return 0

    if mode == "single":
        while True:
            try:
                run_single(pipeline)
                again = Confirm.ask("  [bold]Triage another ticket?[/bold]", default=False)
            except (KeyboardInterrupt, EOFError):
                break
            if not again:
                break
        return 0

    if mode == "batch":
        input_path = settings.paths.input_csv
        output_path = settings.paths.output_csv
        return run_batch(pipeline, input_path, output_path)

    if mode == "interactive":
        return run_interactive(pipeline)

    return 0


if __name__ == "__main__":
    sys.exit(main())
