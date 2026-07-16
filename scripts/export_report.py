import sys
from r4_autolab.cli import main

if len(sys.argv) != 2:
    raise SystemExit("usage: export_report.py RUN_ID")
raise SystemExit(main(["report", sys.argv[1]]))
