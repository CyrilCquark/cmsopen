if checks.failures:
    raise AssertionError(f"{len(checks.failures)} check(s) failed: {', '.join(checks.failures)}")
print("All checks passed")
