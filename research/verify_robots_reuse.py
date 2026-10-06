"""Compare two rules using isolated, inspected Protego source in tmp/reuse-research."""
import json
import sys
import urllib.robotparser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tmp/reuse-research'))
from protego import Protego  # noqa: E402

cases = [
    ('wildcard_pdf', ['User-agent: *', 'Disallow: /*.pdf$'], 'https://example.com/jobs.pdf', False),
    ('specific_allow', ['User-agent: *', 'Disallow: /', 'Allow: /jobs/'], 'https://example.com/jobs/1', True),
]
results = []
for name, lines, url, expected in cases:
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(lines)
    old = parser.can_fetch('*', url)
    new = Protego.parse('\n'.join(lines)).can_fetch(url, '*')
    assert new == expected
    results.append({'case': name, 'stdlib_allowed': old, 'protego_allowed': new, 'expected_allowed': expected})
print(json.dumps(results, indent=2))
