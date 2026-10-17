"""The ordinary bot must not load historical evaluation execution modules."""

import json
import subprocess
import sys


def test_development_startup_does_not_import_evaluation_runners():
    script = "import json,sys; import src.commands.run_dev_bot; print(json.dumps([n for n in sys.modules if n.startswith(('src.commands.hf_', 'src.commands.evaluate_', 'src.commands.agent_collection', 'src.services.qualified_pc_api', 'src.services.pc_api', 'src.db.', 'sqlalchemy.orm'))]))"
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, timeout=30, check=True)
    assert json.loads(result.stdout) == []
