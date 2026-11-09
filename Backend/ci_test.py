"""
ci_test.py — Helper script for GitHub Actions CI runner.
Runs pytest, prints all failures with full traceback, and writes a markdown summary.
"""
import subprocess
import sys
import xml.etree.ElementTree as ET
import os

def main():
    # Run pytest
    print("=== Running Pytest in CI ===")
    cmd = [
        sys.executable, "-m", "pytest", "tests/",
        "-v",
        "--tb=short",
        "-ra",
        "--junitxml=pytest-report.xml"
    ]
    res = subprocess.run(cmd)
    
    # Parse junit xml report if generated
    if os.path.exists("pytest-report.xml"):
        try:
            tree = ET.parse("pytest-report.xml")
            root = tree.getroot()
            failures = []
            for tc in root.iter("testcase"):
                for f in tc.iter("failure"):
                    msg = f.attrib.get("message", "") or f.text or ""
                    failures.append((tc.attrib.get("classname", ""), tc.attrib.get("name", ""), msg[:300]))
                for e in tc.iter("error"):
                    msg = e.attrib.get("message", "") or e.text or ""
                    failures.append(("ERROR: " + tc.attrib.get("classname", ""), tc.attrib.get("name", ""), msg[:300]))
            
            if failures:
                print(f"\n==================== {len(failures)} FAILED TESTS ====================")
                for cls, name, msg in failures:
                    print(f"FAILED: {cls} :: {name}\n  Reason: {msg}\n")
            else:
                print("\n==================== ALL TESTS PASSED ====================")
        except Exception as exc:
            print(f"Error parsing junit xml: {exc}")
    
    sys.exit(res.returncode)

if __name__ == "__main__":
    main()
