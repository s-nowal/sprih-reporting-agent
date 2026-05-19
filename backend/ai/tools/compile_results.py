"""compile_results — agent-callable tool to aggregate section drafts and data requirements."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from backend.ai.tools.terminal_tools import get_workspace_path
from backend.infra.registry import get_storage

_MARKER = "# Data Required"


@tool
async def compile_results(section_dir: str = "workspace/sections", output_path: str = "workspace", *, config: RunnableConfig) -> str:
    """Compile section draft files into three aggregate output files.
    Call this after all section subagents have finished writing their files. Do NOT \
    manually concatenate sections yourself — always use this tool.

    Args:
        section_dir: Workspace-relative path to the directory containing section
            markdown files. Leading ``/`` is stripped. Defaults to ``workspace/sections``.
        output_path: Workspace-relative directory where the three output files are
            written. Leading ``/`` is stripped. Defaults to ``workspace``.
        config: LangGraph runnable config carrying ``thread_id``.

    Returns:
        Summary message listing the three saved files. Appends a warning for any
        section file missing the ``# Data Required`` marker.
    """
    thread_id: str = config["configurable"]["thread_id"]
    base_prefix = await get_workspace_path(thread_id)
    if base_prefix is None:
        return f"Error: thread '{thread_id}' not found."

    storage = get_storage()

    # --- Resolve storage-key prefixes (strip leading "/" so keys stay relative) ---
    section_prefix = f"{base_prefix}/{section_dir.lstrip('/')}"
    out_prefix = f"{base_prefix}/{output_path.lstrip('/')}"

    # --- List all .md files in section_dir, sorted by filename ---
    objects = storage.list_objects(section_prefix)
    md_keys = sorted(
        obj["key"] for obj in objects if obj["key"].endswith(".md")
    )

    final_report: list[str] = []
    final_report_without_dr: list[str] = []
    final_dr_sheet: list[str] = []
    missing_dr: list[str] = []

    # --- Process each section file ---
    for key in md_keys:
        filename = key.rsplit("/", 1)[-1]
        content = storage.read_text(key)

        final_report.append(content)

        if _MARKER in content:
            idx = content.index(_MARKER)
            first_part = content[:idx].rstrip()
            second_part = content[idx + len(_MARKER):].lstrip("\n")
            final_report_without_dr.append(first_part)
            # Head the data-requirements block with the section filename
            final_dr_sheet.append(f"# {filename}\n\n{second_part}")
        else:
            missing_dr.append(filename)
            # No marker — include full content in the draft-only file
            final_report_without_dr.append(content)

    # --- Write the three output files ---
    storage.write_text(f"{out_prefix}/draft.md", "\n\n".join(final_report))
    storage.write_text(f"{out_prefix}/report.md", "\n\n".join(final_report_without_dr))
    storage.write_text(f"{out_prefix}/data_requirements.md", "\n\n".join(final_dr_sheet))

    # --- Build return message ---
    return_msg = (
        f"Full compiled draft (report + data requirements) saved in {output_path}/draft.md. "
        f"Compiled full report (without data requirements) saved in {output_path}/report.md. "
        f"Data requirements saved in {output_path}/data_requirements.md."
    )
    if missing_dr:
        filenames_str = ", ".join(missing_dr)
        return_msg += (
            f" IMPORTANT: The phrase '{_MARKER}' was not found in these files: "
            f"{filenames_str}. Add manually or modify files so they contain this "
            "phrase where needed."
        )
    return return_msg
