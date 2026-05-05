from langchain_core.tools import tool
from pathlib import Path

@tool
def send_report_to_user(directory: str) -> str:
    """Sends the generated report to shared file for user viewing.

    Input params: 
        directory: The folder in which all generated section files of the report are present.
            Example: `workspace/sections`
    """
    directory = directory[1:] if directory.startswith('/') else directory
    folder_path = Path("agent_folder") / directory
    output_path = Path("agent_folder/output/output.md")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    md_files = sorted(folder_path.glob("*.md"))

    combined_content = []
    for file in md_files:
        with open(file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                combined_content.append(content)

    final_content = "\n\n".join(combined_content)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_content)
    return f"Report successfully written to {output_path}"