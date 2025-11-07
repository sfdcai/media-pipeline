#!/usr/bin/env python3
"""Interactive workflow helper for operators."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Callable, Coroutine

from modules.workflow import (
    PipelineRunResult,
    PipelineStepResult,
    WorkflowOrchestrator,
)
from utils.config_loader import load_config
from utils.service_container import build_service_container


class WorkflowCLI:
    """Simple terminal menu for running pipeline operations."""

    def __init__(self, orchestrator: WorkflowOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def run(self) -> None:
        actions: dict[str, tuple[str, Callable[[], Coroutine[Any, Any, None]]]] = {
            "1": ("Run full workflow", self._run_pipeline),
            "2": ("Run dedup", self._run_dedup),
            "3": ("Create batch", self._run_batch),
            "4": ("Start sync", self._run_sync),
            "5": ("Run sort", self._run_sort),
            "6": ("Run cleanup", self._run_cleanup),
            "7": ("Show overview", self._show_overview),
            "q": ("Quit", None),
        }

        while True:
            print("\nMedia Pipeline Workflow CLI")
            for key, (label, _) in actions.items():
                print(f"  {key}) {label}")
            choice = input("Select an option: ").strip().lower()
            if choice == "q":
                print("Goodbye!")
                return
            action = actions.get(choice)
            if not action:
                print("Unknown option. Please try again.")
                continue
            label, handler = action
            print(f"\n==> {label}")
            await handler()

    async def _run_pipeline(self) -> None:
        result = await self._orchestrator.run_pipeline()
        self._print_run_result(result)

    async def _run_dedup(self) -> None:
        result = await self._orchestrator.run_dedup()
        self._print_step(result)

    async def _run_batch(self) -> None:
        result = self._orchestrator.run_batch()
        self._print_step(result)

    async def _run_sync(self) -> None:
        batch = input("Batch name to sync: ").strip()
        if not batch:
            print("Batch name required")
            return
        result = await self._orchestrator.run_sync(batch)
        self._print_step(result)

    async def _run_sort(self) -> None:
        batch = input("Batch name to sort: ").strip()
        if not batch:
            print("Batch name required")
            return
        result = self._orchestrator.run_sort(batch)
        self._print_step(result)

    async def _run_cleanup(self) -> None:
        result = self._orchestrator.run_cleanup()
        self._print_step(result)

    async def _show_overview(self) -> None:
        overview = self._orchestrator.build_overview(last_run=None, running=False)
        print(json.dumps(overview, indent=2, sort_keys=True))

    @staticmethod
    def _print_step(step: PipelineStepResult) -> None:
        print(f"Status: {step.status}")
        if step.message:
            print(f"Message: {step.message}")
        if step.data:
            print(json.dumps(step.data, indent=2, sort_keys=True))

    def _print_run_result(self, result: PipelineRunResult) -> None:
        print(f"Started: {result.started_at}")
        print(f"Finished: {result.finished_at}")
        for step in result.steps:
            print("-" * 40)
            self._print_step(step)
        if result.errors:
            print("Errors:")
            for err in result.errors:
                print(f"  - {err}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Media pipeline workflow helper")
    parser.add_argument(
        "--config",
        type=Path,
        help="Optional path to configuration file to load",
    )
    args = parser.parse_args()

    if args.config:
        config_data = load_config(args.config)
        container = build_service_container(config_data)
    else:
        container = build_service_container()

    orchestrator = WorkflowOrchestrator(container)
    cli = WorkflowCLI(orchestrator)
    try:
        asyncio.run(cli.run())
    except KeyboardInterrupt:  # pragma: no cover - user interaction
        print("\nInterrupted")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
