"""
Runs all verification scripts and prints a summary table.
Run: python scripts/verify_all.py
"""
import subprocess
import sys

checks = [
    ("Apify", "scripts/verify_apify.py"),
    ("Anthropic", "scripts/verify_anthropic.py"),
]

results = []
for name, script in checks:
    result = subprocess.run([sys.executable, script], capture_output=True, text=True)
    ok = result.returncode == 0
    msg = (result.stdout or result.stderr).strip().splitlines()[0] if (result.stdout or result.stderr) else "no output"
    results.append((name, ok, msg))

print("\n=== Service Verification ===")
for name, ok, msg in results:
    status = "OK " if ok else "FAIL"
    print(f"  [{status}] {name:<15} {msg}")
print()

if not all(ok for _, ok, _ in results):
    print("Some services failed. Fill in the missing keys in .env and re-run.")
    raise SystemExit(1)
print("All required services connected.")
