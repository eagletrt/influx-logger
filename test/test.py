from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from unittest import FunctionTestCase, TestLoader, TestSuite, TextTestRunner

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

def main():
    loader = TestLoader()
    suite = TestSuite()

    # Load tests from python files under test/*/ subdirectories.
    for file_path in sorted(Path('test').rglob('test_*.py')):
        if file_path.parent == Path('test') or file_path.name in {'test.py'}:
            continue

        module_name = 'dynamic_' + '_'.join(file_path.with_suffix('').parts)
        spec = spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            continue

        module = module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            def _raise_import_error(err=exc, path=file_path):
                raise RuntimeError(f"Failed to import {path}: {err}") from err

            suite.addTest(FunctionTestCase(_raise_import_error))
            continue

        suite.addTests(loader.loadTestsFromModule(module))

    runner = TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print(f"Tests run: {result.testsRun}")
    print(f"\tPassed: {result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)}")
    print(f"\tFailures: {len(result.failures)}")
    print(f"\tErrors: {len(result.errors)}")
    print(f"\tSkipped: {len(result.skipped)}")
    print()
    if result.wasSuccessful():
        print("All tests passed successfully.")
    else:
        print("Some tests failed or encountered errors.")
        exit(1)  # Exit with a non-zero status to indicate failure

if __name__ == '__main__':
    main()
