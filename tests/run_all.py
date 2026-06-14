"""
Run every TRACE-AI test module.

Run from the project root:  python3 -m tests.run_all
"""

import importlib

MODULES = [
    "tests.test_metadata",
    "tests.test_chart_noise",
    "tests.test_definition_filter",
    "tests.test_verification",
    "tests.test_smoke",
]


def main():
    """Import and run each test module's checks; report a combined result."""
    failures = 0
    for name in MODULES:
        print(f"\n=== {name} ===")
        try:
            mod = importlib.import_module(name)
            if hasattr(mod, "ALL"):
                for t in mod.ALL:
                    t()
                    print(f"  {t.__name__}: OK")
            else:
                # test_smoke runs itself under __main__; call its functions
                for attr in dir(mod):
                    if attr.startswith("test_"):
                        getattr(mod, attr)()
                        print(f"  {attr}: OK")
        except AssertionError as e:
            failures += 1
            print(f"  FAILED: {e}")
        except Exception as e:
            failures += 1
            print(f"  ERROR: {e}")
    print("\n" + ("ALL TEST MODULES PASSED" if failures == 0
                  else f"{failures} failure(s)"))
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
