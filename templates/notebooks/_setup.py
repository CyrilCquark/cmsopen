import json
import os
import re
from pathlib import Path

import cmsopen
from cmsopen.fitting import pdg_mass_width
from cmsopen.pipeline import CHANNELS
from IPython.display import Image, Markdown, display

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "examples" / "data" / "cmsopen_sample.root").exists())
SAMPLE = ROOT / "examples" / "data" / "cmsopen_sample.root"
FIGURES = ROOT / "docs" / "figures"
PRODUCTION = json.loads((ROOT / "results" / "production.json").read_text())
print(f"cmsopen {cmsopen.__version__} imported from: {cmsopen.__file__}")


class Checks:
    """Collects self-check results and prints one OK/FAIL line each."""

    def __init__(self):
        self.failures = []

    def check(self, name, ok, detail=""):
        """Print one OK or FAIL line and remember failures."""
        print(f"{'OK' if ok else 'FAIL'}: {name}" + (f" ({detail})" if detail else ""))
        if not ok:
            self.failures.append(name)


checks = Checks()
