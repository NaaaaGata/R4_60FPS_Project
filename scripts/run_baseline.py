import sys
from r4_autolab.cli import main

raise SystemExit(main(["baseline", "--scenario", sys.argv[1] if len(sys.argv) > 1 else "fake-straight"]))

