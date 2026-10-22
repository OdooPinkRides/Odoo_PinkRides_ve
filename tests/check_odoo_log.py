"""Fail CI if Odoo did not actually collect the module's test suite."""

import re
import sys
from pathlib import Path


log = Path(sys.argv[1]).read_text(encoding="utf-8")
print(
    "\n".join(
        line
        for line in log.splitlines()
        if "tests" in line.lower() or "ERROR" in line or "CRITICAL" in line
    )
)
if not re.search(r"0 failed, 0 error\(s\) of [1-9][0-9]* tests", log):
    raise SystemExit(
        "Odoo tests did not finish successfully or no tests were collected."
    )
if re.search(r" (ERROR|CRITICAL) ", log):
    raise SystemExit("Unexpected Odoo ERROR/CRITICAL log; inspect the CI artifact.")
