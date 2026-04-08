"""pipeline.py — end-to-end runner voor de content agent.

Stappen:
  1. research  (optioneel: --skip-research)
  2. plan      (kies volgend artikel)
  3. write     (Claude API)
  4. audit     (SEO check, fail < threshold)
  5. publish   (Shopify draft; --dry-run schrijft alleen payload weg)
  6. log       (append aan published.json)

CLI:
  python -m src.pipeline --count 1 --dry-run
  python -m src.pipeline --count 1
  python -m src.pipeline --count 1 --skip-research
  python -m src.pipeline --resume output/<slug>

Idempotent: als een artikel al in published.json staat wordt het overgeslagen.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from .planner import Brief, pick_next
from .publisher import log_published, publish_article
from .research import run as research_run
from .seo_audit import audit_path
from .utils import OUTPUT_DIR, RunContext, env, get_logger

log = get_logger("pipeline")


def _run_one(ctx: RunContext) -> Path | None:
    # 2. PLAN
    log.info("[bold cyan]stap 2/5: plannen[/bold cyan]")
    brief: Brief | None = pick_next()
    if not brief:
        log.warning("Geen brief — alle clusters al gedaan? Stop.")
        return None

    # 3. WRITE
    log.info("[bold cyan]stap 3/5: schrijven (Claude)[/bold cyan]")
    from .writer import write_article

    article_dir = write_article(brief, model=ctx.model)

    # 4. AUDIT
    log.info("[bold cyan]stap 4/5: SEO audit[/bold cyan]")
    result = audit_path(article_dir, threshold=ctx.min_seo_score)
    if not result.passed:
        log.error(
            f"Audit gefaald ({result.score}/100 < {ctx.min_seo_score}). "
            f"Zie {article_dir / 'audit.md'}. Geen publicatie."
        )
        return article_dir

    # 5. PUBLISH
    log.info("[bold cyan]stap 5/5: publiceren (draft)[/bold cyan]")
    try:
        publish_result = publish_article(article_dir, dry_run=ctx.dry_run)
    except Exception as exc:
        log.error(f"Publicatie fout: {exc}")
        publish_result = {"error": str(exc), "dry_run": ctx.dry_run}

    log_published(article_dir, publish_result, dry_run=ctx.dry_run)
    return article_dir


def run_pipeline(
    *,
    count: int,
    dry_run: bool,
    skip_research: bool,
    resume: Path | None = None,
) -> list[Path]:
    ctx = RunContext.from_env(dry_run=dry_run, count=count)
    log.info(
        f"[bold]Vonkel content agent[/bold] — start {ctx.started_at}  "
        f"model={ctx.model}  dry_run={ctx.dry_run}  min_score={ctx.min_seo_score}"
    )

    if resume:
        log.info(f"[bold cyan]resume[/bold cyan] -> audit+publish van {resume}")
        result = audit_path(resume, threshold=ctx.min_seo_score)
        if result.passed:
            publish_result = publish_article(resume, dry_run=ctx.dry_run)
            log_published(resume, publish_result, dry_run=ctx.dry_run)
        return [resume]

    # 1. RESEARCH
    if not skip_research:
        log.info("[bold cyan]stap 1/5: research[/bold cyan]")
        try:
            research_run()
        except Exception as exc:
            log.warning(f"Research stap faalde ({exc}); ga door met bestaande keyword_bank.")
    else:
        log.info("[bold cyan]stap 1/5: research[/bold cyan] (overgeslagen)")

    produced: list[Path] = []
    for i in range(count):
        log.info(f"\n=== Artikel {i + 1}/{count} ===")
        try:
            out = _run_one(ctx)
            if out:
                produced.append(out)
        except Exception as exc:
            log.error(f"Artikel {i + 1} gefaald: {exc}")
            traceback.print_exc()
            continue

    log.info(f"\n[bold green]klaar[/bold green] — {len(produced)} artikel(en) in {OUTPUT_DIR}")
    return produced


def main() -> None:
    parser = argparse.ArgumentParser(description="Vonkel content agent pipeline")
    parser.add_argument("--count", type=int, default=1, help="aantal artikelen deze run")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=(env("AGENT_DEFAULT_DRY_RUN", "true") or "true").lower() == "true",
        help="nooit publiceren, alleen lokaal",
    )
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    parser.add_argument("--skip-research", action="store_true")
    parser.add_argument(
        "--resume", type=Path, default=None, help="hervat met audit+publish van een bestaande output/<slug>"
    )
    args = parser.parse_args()

    try:
        run_pipeline(
            count=args.count,
            dry_run=args.dry_run,
            skip_research=args.skip_research,
            resume=args.resume,
        )
    except KeyboardInterrupt:
        log.warning("interrupt — stop.")
        sys.exit(130)


if __name__ == "__main__":
    main()
