"""Is the notebook actually well formed? Checks the things Colab shows and the JSON hides."""
import ast
import json
import sys

nb = json.load(open(sys.argv[1], encoding="utf-8"))
bad_newlines, bad_syntax, bad_cr = 0, 0, 0
for i, c in enumerate(nb["cells"]):
    src = c["source"]
    for line in src[:-1]:
        if not line.endswith("\n"):
            bad_newlines += 1
        if "\r" in line:
            bad_cr += 1
    if c["cell_type"] != "code":
        continue
    out = []
    for line in src:
        stripped = line.lstrip()
        if stripped.startswith(("!", "%")):
            out.append(" " * (len(line) - len(stripped)) + "pass\n")
        else:
            out.append(line)
    try:
        ast.parse("".join(out))
    except SyntaxError as e:
        bad_syntax += 1
        print(f"  CELL {i} SYNTAX: {e}")

print(f"cells {len(nb['cells'])} | lines missing a newline {bad_newlines} | "
      f"carriage returns {bad_cr} | code cells that will not parse {bad_syntax}")

blob = json.dumps(nb)
for must in ("RealVisXL_V5.0_Lightning", "userdata.get", "symlink_to",
             "Runtime > Change runtime type", "trycloudflare"):
    print(("  ok      " if must in blob else "  MISSING ") + must)
if "hf_" in blob and "HF_TOKEN" not in blob.replace("hf_hub_download", ""):
    print("  !! something that looks like a token is in this notebook")
else:
    print("  ok      no token in the notebook")

first = next(c for c in nb["cells"] if c["cell_type"] == "markdown")
print("\n--- how the first cell will read ---")
print("".join(first["source"])[:260])
sys.exit(1 if (bad_newlines or bad_syntax or bad_cr) else 0)
