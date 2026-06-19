"""Model discovery — queries the live Gemini API for available models.

Run this before setting up .env to see which models are actually available
on your API key tier. Optionally writes recommended settings to .env.

Usage:
    cd code
    python discover_models.py                  # list and recommend
    python discover_models.py --write-env      # also write to ../.env
    python discover_models.py --provider all   # check all providers
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "code"))

from dotenv import load_dotenv

load_dotenv(_REPO_ROOT / ".env")


# ── Gemini ─────────────────────────────────────────────────────────────────────

def _query_gemini() -> dict:
    """Query the Gemini API and return categorised model lists."""
    try:
        from google import genai
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            return {"error": "GEMINI_API_KEY not set"}

        client = genai.Client(api_key=api_key)
        raw = list(client.models.list())

        generate_models: list[str] = []
        embed_models: list[str] = []

        for m in raw:
            name = getattr(m, "name", "")
            if not name:
                continue
            supported = [a.value if hasattr(a, "value") else str(a)
                         for a in getattr(m, "supported_actions", [])]
            if "generateContent" in supported or not supported:
                if "gemini" in name.lower() and "embedding" not in name:
                    generate_models.append(name)
            if "embedContent" in supported or "embedding" in name:
                embed_models.append(name)

        return {"generate": sorted(generate_models), "embed": sorted(embed_models)}
    except Exception as exc:
        return {"error": str(exc)}


def _recommend_gemini(models: list[str]) -> dict[str, str]:
    """Pick the best tier model from the actual available list."""
    def pick(keywords: list[str]) -> Optional[str]:
        for kw in keywords:
            for m in models:
                if kw in m:
                    return m
        return None

    low = pick(["3.1-flash-lite", "2.5-flash-lite", "2.0-flash-lite", "gemini-flash-lite"])
    medium = pick(["3-flash-preview", "3.1-flash", "2.5-flash-preview", "2.5-flash"])
    high = pick(["3.1-pro-preview", "3-pro-preview", "2.5-pro-preview", "2.5-pro", "gemini-pro-latest"])
    embed = None  # handled separately

    return {k: v for k, v in {"low": low, "medium": medium, "high": high}.items() if v}


def _recommend_embed(embed_models: list[str]) -> Optional[str]:
    """Pick the best embedding model."""
    preferences = ["gemini-embedding-2", "gemini-embedding-001"]
    for pref in preferences:
        for m in embed_models:
            if pref in m:
                return m
    return embed_models[0] if embed_models else None


# ── Anthropic ──────────────────────────────────────────────────────────────────

def _query_anthropic() -> dict:
    """Query the Anthropic API for available models."""
    try:
        import anthropic  # type: ignore
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            return {"error": "ANTHROPIC_API_KEY not set"}
        client = anthropic.Anthropic(api_key=api_key)
        models = [m.id for m in client.models.list().data]
        return {"models": sorted(models)}
    except ImportError:
        return {"error": "anthropic package not installed (pip install anthropic)"}
    except Exception as exc:
        return {"error": str(exc)}


# ── OpenAI ─────────────────────────────────────────────────────────────────────

def _query_openai() -> dict:
    """Query the OpenAI API for available models."""
    try:
        import openai  # type: ignore
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            return {"error": "OPENAI_API_KEY not set"}
        client = openai.OpenAI(api_key=api_key)
        models = sorted([m.id for m in client.models.list().data
                         if "gpt" in m.id or "o1" in m.id or "o3" in m.id or "o4" in m.id])
        return {"models": models}
    except ImportError:
        return {"error": "openai package not installed (pip install openai)"}
    except Exception as exc:
        return {"error": str(exc)}


# ── Report ─────────────────────────────────────────────────────────────────────

def _print_gemini_report(result: dict) -> Optional[dict]:
    print("\n=== Gemini (Google AI) ===")
    if "error" in result:
        print(f"  Error: {result['error']}")
        return None

    gen_models = result.get("generate", [])
    emb_models = result.get("embed", [])

    print(f"  Text generation models: {len(gen_models)}")
    for m in gen_models:
        print(f"    {m}")

    print(f"\n  Embedding models: {len(emb_models)}")
    for m in emb_models:
        print(f"    {m}")

    rec = _recommend_gemini(gen_models)
    embed_rec = _recommend_embed(emb_models)
    print("\n  Recommended tier mapping:")
    for tier, model in rec.items():
        print(f"    MODEL_{tier.upper()}={model!r}")
    if embed_rec:
        print(f"    EMBEDDING_MODEL={embed_rec!r}")

    return {**rec, "embed": embed_rec}


def _write_env_recommendations(rec: dict, env_path: Path) -> None:
    lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
    updates = {
        "MODEL_LOW": rec.get("low"),
        "MODEL_MEDIUM": rec.get("medium"),
        "MODEL_HIGH": rec.get("high"),
        "EMBEDDING_MODEL": rec.get("embed"),
    }

    new_lines = []
    updated: set[str] = set()
    for line in lines:
        key = line.split("=")[0].strip()
        if key in updates and updates[key]:
            new_lines.append(f"{key}={updates[key]}\n")
            updated.add(key)
        else:
            new_lines.append(line)

    for key, val in updates.items():
        if key not in updated and val:
            new_lines.append(f"{key}={val}\n")

    env_path.write_text("".join(new_lines), encoding="utf-8")
    print(f"\n  Written to {env_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover available models from AI APIs")
    parser.add_argument(
        "--provider",
        choices=["gemini", "anthropic", "openai", "all"],
        default="gemini",
        help="Which provider to query (default: gemini)",
    )
    parser.add_argument(
        "--write-env",
        action="store_true",
        help="Write recommended Gemini model names to ../.env",
    )
    args = parser.parse_args()

    gemini_rec: Optional[dict] = None

    if args.provider in ("gemini", "all"):
        result = _query_gemini()
        gemini_rec = _print_gemini_report(result)

    if args.provider in ("anthropic", "all"):
        result = _query_anthropic()
        print("\n=== Anthropic (Claude) ===")
        if "error" in result:
            print(f"  Error: {result['error']}")
        else:
            for m in result.get("models", []):
                print(f"  {m}")

    if args.provider in ("openai", "all"):
        result = _query_openai()
        print("\n=== OpenAI ===")
        if "error" in result:
            print(f"  Error: {result['error']}")
        else:
            for m in result.get("models", []):
                print(f"  {m}")

    if args.write_env and gemini_rec:
        env_path = _REPO_ROOT / ".env"
        if env_path.exists():
            _write_env_recommendations(gemini_rec, env_path)
        else:
            print(f"\n  .env not found at {env_path} — create it first from .env.example")

    return 0


if __name__ == "__main__":
    sys.exit(main())
