"""Export compiled DSC artifacts for external integrations.

Currently supports:
- OpenClaw ContextEngine plugin format
"""

from __future__ import annotations

import json
from pathlib import Path

from dsc.storage.filesystem import FileSystemStorage


def export_for_openclaw(
    storage: FileSystemStorage,
    project_id: str,
    output_dir: Path,
) -> list[Path]:
    """Export all compiled artifacts in a project for the OpenClaw plugin.

    Reads compiled artifacts from storage and writes them to output_dir
    in the format expected by the DSC OpenClaw ContextEngine plugin.

    Returns list of exported file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    exported = []

    scenarios = storage.list_scenarios(project_id)

    for scenario in scenarios:
        if scenario.compiled_version is None:
            continue

        artifact_data = storage.load_compiled(
            project_id, scenario.id, scenario.compiled_version
        )

        # The OpenClaw plugin expects the standard compiled artifact JSON
        # with scenario_name added for identification
        if "scenario_name" not in artifact_data:
            artifact_data["scenario_name"] = scenario.name

        filename = f"{scenario.id}_v{scenario.compiled_version}.json"
        out_path = output_dir / filename
        out_path.write_text(json.dumps(artifact_data, indent=2), encoding="utf-8")
        exported.append(out_path)

    return exported
