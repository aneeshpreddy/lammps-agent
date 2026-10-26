"""Call a tool directly, without any LLM.

  python -m tools list                                   # the tool definitions sent to the API
  python -m tools call get_model_info '{"model": "tob11_unit_cell", "force_field": "pcff"}'
  python -m tools call build_data_file "$(cat spec.json)" --workdir runs/tools_manual
"""
import argparse
import json
import sys

from tools.toolbox import ToolBox, definitions

ap = argparse.ArgumentParser(prog="python -m tools")
sub = ap.add_subparsers(dest="cmd", required=True)
sub.add_parser("list")
c = sub.add_parser("call")
c.add_argument("tool")
c.add_argument("arguments", help="JSON object")
c.add_argument("--workdir", default="runs/tools_manual")
a = ap.parse_args()
if a.cmd == "list":
    print(json.dumps(definitions(), indent=1))
else:
    res = ToolBox(a.workdir).run(a.tool, json.loads(a.arguments))
    print(json.dumps(res, indent=1))
    sys.exit(0 if res["ok"] else 1)
