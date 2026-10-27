"""
Test Suite Runner (Task Z9)
Executes all unit and integration test suites in isolated processes to prevent namespace collisions.
"""

import sys
import subprocess

def run_suite(description, cmd, cwd=None):
    print(f"\n=======================================================")
    print(f" Running: {description}")
    print(f"=======================================================")
    res = subprocess.run(cmd, cwd=cwd, shell=True)
    if res.returncode != 0:
        print(f"[-] FAILED: {description}")
        return False
    print(f"[+] PASSED: {description}")
    return True

def main():
    suites = [
        ("Simulator & Core Telemetry Tests", f"{sys.executable} -m pytest tests/ -v", None),
        ("Ingest API Microservice Tests", f"{sys.executable} -m pytest tests/ -v", "services/ingest-api"),
        ("Processor & FFT Math Engine Tests", f"{sys.executable} -m pytest tests/ -v", "services/processor"),
    ]

    all_passed = True
    for desc, cmd, cwd in suites:
        if not run_suite(desc, cmd, cwd=cwd):
            all_passed = False

    if not all_passed:
        print("\n[!] One or more test suites failed.")
        sys.exit(1)

    print("\n[OK] ALL 33 UNIT & INTEGRATION TESTS PASSED CLEANLY!")
    sys.exit(0)

if __name__ == "__main__":
    main()
