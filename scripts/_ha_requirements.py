"""
Print the pip requirements of the Home Assistant integrations used by config/.

Walks the dependency closure of the domains named in configuration.yaml
(plus the ones Home Assistant always loads) so they can be installed into
the venv up front. That lets scripts/develop pass --skip-pip and boot fast.
"""

import json
import sys
from pathlib import Path

from homeassistant import components

COMPONENTS = Path(components.__file__).parent
CORE_DOMAINS = {
    "homeassistant",
    "persistent_notification",
    "backup",
    "frontend",
    "http",
}
DOMAINS = set(sys.argv[1:]) | CORE_DOMAINS

seen: set[str] = set()
requirements: set[str] = set()
queue = list(DOMAINS)
while queue:
    domain = queue.pop()
    if domain in seen:
        continue
    seen.add(domain)
    manifest = COMPONENTS / domain / "manifest.json"
    if not manifest.exists():
        continue
    data = json.loads(manifest.read_text())
    requirements.update(data.get("requirements", []))
    queue.extend(data.get("dependencies", []))
    queue.extend(data.get("after_dependencies", []))

print("\n".join(sorted(requirements)))
