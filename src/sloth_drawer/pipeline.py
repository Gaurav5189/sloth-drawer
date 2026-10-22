"""The pipeline: manuals in, verified intervals out.

The order of the stages is the argument of the project:

1.  **ingest** — read the pages, skip what cannot be read, record why;
2.  **chunk** — split pages into chunks that remember their page and section;
3.  **prefilter** — deterministic regex scoring; most chunks never reach the
    model at all;
4.  **triage** (optional) — a 291 MB model answers "is there an interval here?";
5.  **extract** — an 806 MB model points at one candidate sentence;
6.  **verify** — the code locates the quote in the cited page, expands it to the
    sentence, re-parses the interval and compares.

Nothing after step 5 can put a wrong date on a card. A model failure can only
produce a missing card (ARCHITECTURE.md 1).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sloth_drawer.config import Config
from sloth_drawer.corpus import prefilter
from sloth_drawer.corpus.chunk import candidate_excerpts, chunk_manual
from sloth_drawer.corpus.ingest import Manual, Skipped, ingest_directory
from sloth_drawer.errors import (
    ModelError,
    ModelOutputError,
    ModelSchemaError,
    OllamaUnavailableError,
)
from sloth_drawer.extract.extractor import extract
from sloth_drawer.extract.prompts import PROMPT_VERSION
from sloth_drawer.extract.triage import triage
from sloth_drawer.extract.verify import SKIP, Verdict, verify
from sloth_drawer.models import DEFAULT_EXTRACTOR, DEFAULT_TRIAGE

LOGGER = logging.getLogger("sloth_drawer.pipeline")


@dataclass(frozen=True)
class Candidate:
    """One model answer and the verdict the verifier gave it."""

    manual_slug: str
    manual_path: str
    page: int
    section: str | None
    excerpt: str
    task: str
    quote: str
    verdict: Verdict
    model_id: str
    elapsed: float = 0.0
    tokens: int = 0
    retries: int = 0

    @property
    def status(self) -> str:
        return self.verdict.status


@dataclass
class ScanResult:
    """Everything one scan produced."""

    candidates: list[Candidate] = field(default_factory=list)
    manuals: list[Manual] = field(default_factory=list)
    skipped: list[Skipped] = field(default_factory=list)
    seconds: float = 0.0
    tokens: int = 0
    model_calls: int = 0

    @property
    def accepted(self) -> list[Candidate]:
        return [c for c in self.candidates if c.verdict.accepted]

    @property
    def rejected(self) -> list[Candidate]:
        return [c for c in self.candidates if c.verdict.status == "REJECT"]

    @property
    def skipped_candidates(self) -> list[Candidate]:
        return [c for c in self.candidates if c.verdict.status == SKIP]

    def counts(self) -> dict[str, int]:
        """The tally the report prints."""
        tally: dict[str, int] = {}
        for candidate in self.candidates:
            tally[candidate.status] = tally.get(candidate.status, 0) + 1
        return tally

    def rejection_reasons(self) -> dict[str, int]:
        """Why candidates were rejected, broken down by reason code."""
        reasons: dict[str, int] = {}
        for candidate in self.candidates:
            reason = candidate.verdict.reason
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1
        return reasons


def _page_texts(manual: Manual) -> dict[int, str]:
    return {page.number: page.text for page in manual.pages}


def scan_manual(
    manual: Manual,
    *,
    config: Config,
    model: str = DEFAULT_EXTRACTOR,
    triage_model: str | None = DEFAULT_TRIAGE,
    use_triage: bool = False,
    threshold: int = prefilter.DEFAULT_THRESHOLD,
    keep_alive: str | int | None = None,
) -> list[Candidate]:
    """Read one manual and return a candidate per model answer."""
    candidates: list[Candidate] = []
    pages = _page_texts(manual)

    for chunk in chunk_manual(manual.pages):
        if not prefilter.is_candidate(chunk.text, threshold):
            continue
        for excerpt in candidate_excerpts(chunk):
            if use_triage and triage_model:
                # The gate is an optimisation, not a decision. If the small
                # model fails to answer, the candidate still goes to the
                # extractor — a broken gate must not lose an interval.
                try:
                    gate = triage(
                        excerpt,
                        model=triage_model,
                        host=config.ollama_host,
                        timeout=config.ollama_timeout,
                        section=chunk.section,
                        keep_alive=keep_alive,
                    )
                except OllamaUnavailableError:
                    raise
                except ModelError as exc:
                    LOGGER.warning(
                        "%s p.%s: triage failed (%s); extracting anyway",
                        manual.path.name,
                        chunk.page,
                        exc,
                    )
                else:
                    if not gate.has_interval:
                        candidates.append(
                            Candidate(
                                manual_slug=manual.slug,
                                manual_path=manual.path.name,
                                page=chunk.page,
                                section=chunk.section,
                                excerpt=excerpt,
                                task=gate.task,
                                quote="",
                                verdict=Verdict(
                                    status=SKIP,
                                    reason="no_interval_stated",
                                    page=chunk.page,
                                    section=chunk.section,
                                ),
                                model_id=triage_model,
                                elapsed=gate.reply.elapsed,
                                tokens=gate.reply.total_tokens,
                            )
                        )
                        continue

            try:
                extraction = extract(
                    excerpt,
                    model=model,
                    host=config.ollama_host,
                    timeout=config.ollama_timeout,
                    section=chunk.section,
                    keep_alive=keep_alive,
                )
            except (ModelSchemaError, ModelOutputError) as exc:
                LOGGER.warning("%s p.%s: %s", manual.path.name, chunk.page, exc)
                candidates.append(
                    Candidate(
                        manual_slug=manual.slug,
                        manual_path=manual.path.name,
                        page=chunk.page,
                        section=chunk.section,
                        excerpt=excerpt,
                        task="",
                        quote="",
                        verdict=Verdict(
                            status="REJECT",
                            reason="schema_invalid",
                            page=chunk.page,
                            section=chunk.section,
                        ),
                        model_id=model,
                    )
                )
                continue
            except OllamaUnavailableError:
                raise
            except ModelError as exc:
                LOGGER.warning("%s p.%s: %s", manual.path.name, chunk.page, exc)
                candidates.append(
                    Candidate(
                        manual_slug=manual.slug,
                        manual_path=manual.path.name,
                        page=chunk.page,
                        section=chunk.section,
                        excerpt=excerpt,
                        task="",
                        quote="",
                        verdict=Verdict(
                            status="REJECT",
                            reason="model_timeout",
                            page=chunk.page,
                            section=chunk.section,
                        ),
                        model_id=model,
                    )
                )
                continue

            output = extraction.output
            verdict = verify(
                output,
                pages.get(chunk.page, chunk.text),
                page=chunk.page,
                section=chunk.section,
            )
            candidates.append(
                Candidate(
                    manual_slug=manual.slug,
                    manual_path=manual.path.name,
                    page=chunk.page,
                    section=chunk.section,
                    excerpt=excerpt,
                    task=str(output.get("task") or ""),
                    quote=str(output.get("quote") or ""),
                    verdict=verdict,
                    model_id=model,
                    elapsed=extraction.elapsed,
                    tokens=extraction.tokens,
                    retries=extraction.retries,
                )
            )
    return candidates


def scan_corpus(
    directory: Path,
    *,
    config: Config,
    model: str = DEFAULT_EXTRACTOR,
    triage_model: str | None = DEFAULT_TRIAGE,
    use_triage: bool = False,
    threshold: int = prefilter.DEFAULT_THRESHOLD,
    slugs: dict[str, str] | None = None,
    keep_alive: str | int | None = None,
    on_manual: Callable[[Manual], None] | None = None,
) -> ScanResult:
    """Scan a directory of manuals end to end.

    A manual that fails to read is skipped and recorded. A model call that
    fails becomes a rejected candidate. Neither stops the batch.
    """
    import time

    started = time.monotonic()
    ingested = ingest_directory(Path(directory), slugs=slugs)
    result = ScanResult(manuals=list(ingested.manuals), skipped=list(ingested.skipped))

    for manual in ingested.manuals:
        LOGGER.info("scanning %s (%d pages)", manual.path.name, manual.page_count)
        if on_manual is not None:
            on_manual(manual)
        candidates = scan_manual(
            manual,
            config=config,
            model=model,
            triage_model=triage_model,
            use_triage=use_triage,
            threshold=threshold,
            keep_alive=keep_alive,
        )
        result.candidates.extend(candidates)
        result.tokens += sum(candidate.tokens for candidate in candidates)
        result.model_calls += len(candidates)

    result.seconds = time.monotonic() - started
    LOGGER.info(
        "scan finished: %d manuals, %d candidates, %d tokens, %.1fs",
        len(result.manuals),
        len(result.candidates),
        result.tokens,
        result.seconds,
    )
    return result


__all__ = ["Candidate", "ScanResult", "scan_corpus", "scan_manual", "PROMPT_VERSION"]
