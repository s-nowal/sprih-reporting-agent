import base64
import os
from langchain.tools import tool
from pathlib import Path
import requests

_BINARY_EXTENSIONS = {".xlsx", ".xls", ".pdf", ".docx", ".pptx", ".zip", ".png", ".jpg", ".jpeg", ".gif"}

HOST_PORT = 8001
API_KEY = "your-secret-key"
CONTAINER_NAME = "open-terminal"
IMAGE = "ghcr.io/open-webui/open-terminal"
BASE_URL = "http://localhost:8080"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

base_dir = Path(__file__).resolve().parent.parent.parent.parent
root_folder = base_dir / "agent_folder"

MAX_OUTPUT_CHARS = 8_000

def _truncate_output(output: str, label: str = "Output") -> str:
    if len(output) <= MAX_OUTPUT_CHARS:
        return output
    half = MAX_OUTPUT_CHARS // 2
    return (
        output[:half]
        + f"\n\n... [{label} truncated — {len(output):,} chars total, showing first and last {half}] ...\n\n"
        + output[-half:]
    )

@tool
def upload_full_directory(root_dir: str = root_folder, remote_dir: str = "/") -> dict:
    """Upload all files inside root_dir (input, output, workspace, reference) into the open-terminal container, preserving folder structure.

        :param root_dir: DO NOT MODIFY.
        :type root_dir: str

        :param remote_dir: DO NOT MODIFY.
        :type remote_dir: str

        :return: Summary with lists of uploaded and failed file paths.
        :rtype: dict
    """
    root_path = Path(root_dir)
    subdirs = ["input", "output", "workspace", "reference"]

    uploaded = []
    failed = []

    for subdir in subdirs:
        subdir_path = root_path / subdir
        if not subdir_path.exists():
            continue

        for file_path in subdir_path.rglob("*"):
            if not file_path.is_file() or file_path.name.startswith("~$"):
                continue

            rel_path = file_path.relative_to(root_path)
            remote_file_dir = (Path(remote_dir) / rel_path.parent).as_posix()

            try:
                with open(file_path, "rb") as f:
                    response = requests.post(
                        f"{BASE_URL}/files/upload",
                        headers={"Authorization": f"Bearer {API_KEY}"},
                        params={"directory": remote_file_dir},
                        files={"file": (file_path.name, f, "application/octet-stream")},
                        timeout=60,
                    )
                response.raise_for_status()
                uploaded.append(f"{remote_file_dir}/{file_path.name}")
            except Exception:
                failed.append(rel_path.as_posix())

    return {"uploaded": uploaded, "failed": failed, "total_uploaded": len(uploaded), "total_failed": len(failed)}

def run_terminal(command: str, wait: int = 900) -> str:
    resp = requests.post(
        f"{BASE_URL}/execute",
        headers=HEADERS,
        params={"wait": wait},
        json={"command": command},
        timeout=wait + 10,
    )
    resp.raise_for_status()
    return resp.json().get("output", "")

@tool
def run_terminal_command(command: str, wait: int = 300) -> str:
    """Execute any shell command inside the open-terminal container and return its output.

        :param command: Shell command to run, e.g. "ls /tmp", "cat /tmp/output.csv", "bash /tmp/run.sh"
        :type command: str

        :param wait: Max seconds to wait for the command to finish.
        :type wait: int

        :return: stdout/stderr output from the command.
        :rtype: str
    """
    output = run_terminal(command, wait)
    return _truncate_output(output, label='Terminal output')

@tool
def add_file_to_local (env_path:str, local_filename:str, local_path:str):
    '''
    Saves file to the local environment.
    
    :param env_path: Path in the isolated environment. Eg: "/{filename}.md"
    :type env_path: str
    :param local_filename: Filename for the local environment.
    :type local_filename: str
    :param local_path: Path to 
    :type local_path: str
    '''
    resp = requests.get(f"{BASE_URL}/files/read", headers=HEADERS, params={"path" : env_path})
    try:
        data = resp.json()
    except Exception:
        return f"Error: Invalid JSON response | status={resp.status_code} | body={resp.text}"

    if resp.status_code != 200:
        return f"Error: Request failed | status={resp.status_code} | response={data}"
    
    if "content" not in data:
        return f"Error: 'content' missing in response | response={data}"

    content = data["content"]
    save_dir = root_folder / local_path
    save_dir.mkdir(parents=True, exist_ok=True)

    file_path = save_dir / local_filename
    if Path(local_filename).suffix.lower() in _BINARY_EXTENSIONS:
        try:
            raw = base64.b64decode(content)
        except ValueError:
            # API returned raw binary as a string rather than base64
            raw = content.encode("latin-1")
        with open(file_path, "wb") as f:
            f.write(raw)
    else:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

    path_for_llm = '/' + local_path.split('/')[-1]
    return f"Success: File saved to {path_for_llm}/{local_filename}"