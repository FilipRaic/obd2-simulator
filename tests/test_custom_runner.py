# PlatformIO custom test runner (used by `pio test -e native` from
# firmware/platformio.ini). test_simulator.cpp is a self-contained test
# program printing one "[PASS] name" / "[FAIL] name" line per check and a
# final "=== Results: N passed, M failed ===" summary. This runner maps
# those lines onto PlatformIO test cases. The CMake/ctest flow is unaffected.
import click

from platformio.public import TestCase, TestRunnerBase, TestStatus


class CustomTestRunner(TestRunnerBase):
    def on_testing_line_output(self, line):
        click.echo(line, nl=False)
        stripped = line.strip()
        if stripped.startswith("[PASS] "):
            self.test_suite.add_case(
                TestCase(name=stripped[len("[PASS] "):],
                         status=TestStatus.PASSED))
        elif stripped.startswith("[FAIL] "):
            self.test_suite.add_case(
                TestCase(name=stripped[len("[FAIL] "):],
                         status=TestStatus.FAILED))
        elif stripped.startswith("=== Results"):
            self.test_suite.on_finish()
