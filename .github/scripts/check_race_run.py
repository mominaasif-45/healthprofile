"""
CI guard for the PostgreSQL race tests (backend/tests/test_concurrency.py).

pytest counts a skipped test as a success, so a run on SQLite (where every race test skips) would be
green without testing anything. This script reads pytest's JUnit XML report and fails unless exactly
the expected number of race tests ran, and none was skipped, failed or errored.

Usage: python check_race_run.py <junit.xml> <expected count>
"""
import sys
import xml.etree.ElementTree as ET


def main(path, expected):
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    t = {k: sum(int(s.get(k, 0)) for s in suites) for k in ("tests", "skipped", "failures", "errors")}
    ran = t["tests"] - t["skipped"]
    print(f"race tests: expected {expected}, ran {ran}, skipped {t['skipped']}, "
          f"failed {t['failures']}, errors {t['errors']}")

    problems = []
    if t["skipped"]:
        problems.append(f"{t['skipped']} race test(s) were skipped (is the database PostgreSQL?)")
    if ran != expected:
        problems.append(f"expected {expected} race tests to run, but {ran} ran")
    if t["failures"] or t["errors"]:
        problems.append("some race tests failed or errored")

    for problem in problems:
        print("FAIL:", problem)
    if not problems:
        print("OK: every race test ran on PostgreSQL and passed")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], int(sys.argv[2])))
