import sys
from r4_autolab.cli import main

proposal = sys.argv[1] if len(sys.argv) > 1 else "config/fake_candidate.example.json"
raise SystemExit(main(["experiment", "--proposal", proposal]))

