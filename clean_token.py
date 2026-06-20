import os
target = "tools/github_sync.py"
if os.path.exists(target):
    with open(target, "r", encoding="utf-8") as f:
        c = f.read()
    if "ghp_" in c:
        c2 = c.replace("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", "__TOKEN_REMOVED__")
        with open(target, "w", encoding="utf-8") as f:
            f.write(c2)
