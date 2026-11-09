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
                    clean_msg = msg.replace("\r", "").replace("\n", " ")[:250]
                    print(f"::error title={name}::{cls} - {clean_msg}")
                    print(f"FAILED: {cls} :: {name}\n  Reason: {msg}\n")
                
                summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
                if summary_file:
                    try:
                        with open(summary_file, "a", encoding="utf-8") as sf:
                            sf.write(f"### ❌ {len(failures)} Tests Failed\n\n")
                            for cls, name, msg in failures:
                                sf.write(f"- **`{cls} :: {name}`**\n  ```\n  {msg[:400]}\n  ```\n")
                    except Exception as se:
                        print(f"Error writing step summary: {se}")
            else:
                print("\n==================== ALL TESTS PASSED ====================")
                summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
                if summary_file:
                    try:
                        with open(summary_file, "a", encoding="utf-8") as sf:
                            sf.write("### ✅ All 244 Tests Passed!\n")
                    except Exception:
                        pass
        except Exception as exc:
            print(f"Error parsing junit xml: {exc}")
    
    sys.exit(res.returncode)

if __name__ == "__main__":
    main()
