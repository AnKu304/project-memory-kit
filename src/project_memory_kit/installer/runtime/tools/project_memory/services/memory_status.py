from __future__ import annotations

import re


def with_record_status(content: str, status: str) -> str:
    """Change lifecycle metadata without rerendering historic text or links."""
    match = re.match(r"\A---\n(.*?)\n---(?=\n|\Z)", content, re.DOTALL)
    if not match:
        return f"---\nstatus: {status}\n---\n" + content
    header = match.group(1)
    if re.search(r"(?m)^status:", header):
        header = re.sub(r"(?m)^status:[^\n]*", f"status: {status}", header)
    else:
        header += f"\nstatus: {status}"
    return "---\n" + header + "\n---" + content[match.end():]
