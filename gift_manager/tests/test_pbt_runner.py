"""Property-Based Test Runner.

This module provides utilities for running and managing property-based tests
for the modern UX interface feature.
"""

import json
import time
from datetime import datetime
from datetime import timezone
from pathlib import Path

import pytest

from .test_pbt_config import PBT_COMPREHENSIVE_SETTINGS
from .test_pbt_config import PBT_FAST_SETTINGS
from .test_pbt_config import PBT_PR_SETTINGS
from .test_pbt_config import PBT_SETTINGS
from .test_pbt_config import PROPERTY_METADATA


class PropertyTestResult:
    """Container for property test results."""

    def __init__(
        self, property_number, property_name, status, duration=0, error=None, examples_run=0
    ):
        self.property_number = property_number
        self.property_name = property_name
        self.status = status  # 'passed', 'failed', 'skipped', 'error'
        self.duration = duration
        self.error = error
        self.examples_run = examples_run
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self):
        """Convert result to dictionary for serialization."""
        return {
            "property_number": self.property_number,
            "property_name": self.property_name,
            "status": self.status,
            "duration": self.duration,
            "error": str(self.error) if self.error else None,
            "examples_run": self.examples_run,
            "timestamp": self.timestamp.isoformat(),
        }


class PropertyTestRunner:
    """Runner for property-based tests with reporting and management."""

    def __init__(self, test_mode="normal"):
        """Initialize the test runner.

        Args:
            test_mode: 'fast', 'pr', 'normal', or 'comprehensive'
        """
        self.test_mode = test_mode
        self.results = []
        self.start_time = None
        self.end_time = None

        # Configure Hypothesis settings based on test mode
        if test_mode == "fast":
            self.hypothesis_settings = PBT_FAST_SETTINGS
        elif test_mode == "pr":
            self.hypothesis_settings = PBT_PR_SETTINGS
        elif test_mode == "comprehensive":
            self.hypothesis_settings = PBT_COMPREHENSIVE_SETTINGS
        else:
            self.hypothesis_settings = PBT_SETTINGS

    def run_all_properties(self):
        """Run all property-based tests."""
        self.start_time = time.time()

        print(f"Running property-based tests in {self.test_mode} mode...")
        print(f"Hypothesis settings: max_examples={self.hypothesis_settings.max_examples}")
        print("-" * 60)

        for property_number, metadata in PROPERTY_METADATA.items():
            result = self.run_property_test(property_number, metadata)
            self.results.append(result)
            self._print_result(result)

        self.end_time = time.time()
        self._print_summary()

        return self.results

    def run_property_test(self, property_number, metadata):
        """Run a single property test."""
        property_name = metadata["name"]
        test_method = metadata["test_method"]

        print(f"Running Property {property_number}: {property_name}...")

        start_time = time.time()

        try:
            # Run the property test using pytest
            test_file = "gift_manager/tests/test_property_based_suite.py"
            test_name = f"{test_file}::TestPropertyBasedSuite::{test_method}"

            # Configure pytest arguments
            pytest_args = [
                test_name,
                "-v",
                "--tb=short",
                "--hypothesis-show-statistics",
            ]

            # Run the test
            exit_code = pytest.main(pytest_args)

            duration = time.time() - start_time

            if exit_code == 0:
                status = "passed"
                error = None
            else:
                status = "failed"
                error = f"Test failed with exit code {exit_code}"

            # Estimate examples run based on settings
            examples_run = self.hypothesis_settings.max_examples

        except Exception as e:
            duration = time.time() - start_time
            status = "error"
            error = str(e)
            examples_run = 0

        return PropertyTestResult(
            property_number=property_number,
            property_name=property_name,
            status=status,
            duration=duration,
            error=error,
            examples_run=examples_run,
        )

    def run_specific_properties(self, property_numbers):
        """Run specific property tests by number."""
        self.start_time = time.time()

        print(f"Running specific property tests: {property_numbers}")
        print(f"Test mode: {self.test_mode}")
        print("-" * 60)

        for property_number in property_numbers:
            if property_number in PROPERTY_METADATA:
                metadata = PROPERTY_METADATA[property_number]
                result = self.run_property_test(property_number, metadata)
                self.results.append(result)
                self._print_result(result)
            else:
                print(f"Warning: Property {property_number} not found")

        self.end_time = time.time()
        self._print_summary()

        return self.results

    def _print_result(self, result):
        """Print individual test result."""
        status_symbol = {
            "passed": "✓",
            "failed": "✗",
            "skipped": "⊝",
            "error": "⚠",
        }.get(result.status, "?")

        print(
            f"  {status_symbol} Property {result.property_number}: {result.status.upper()} "
            f"({result.duration:.2f}s, {result.examples_run} examples)"
        )

        if result.error:
            print(f"    Error: {result.error}")

    def _print_summary(self):
        """Print test run summary."""
        if not self.results:
            return

        total_duration = self.end_time - self.start_time if self.end_time and self.start_time else 0
        print(f"\nTotal duration: {total_duration:.2f}s")

        status_counts = {}
        for result in self.results:
            status_counts[result.status] = status_counts.get(result.status, 0) + 1

        if status_counts.get("failed", 0) > 0:
            print("\nFAILED PROPERTIES:")
            for result in self.results:
                if result.status == "failed":
                    print(f"  - Property {result.property_number}: {result.property_name}")
                    if result.error:
                        print(f"    {result.error}")

    def save_results(self, output_file="pbt_results.json"):
        """Save test results to JSON file."""
        results_data = {
            "test_mode": self.test_mode,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_duration": self.end_time - self.start_time
            if self.end_time and self.start_time
            else 0,
            "hypothesis_settings": {
                "max_examples": self.hypothesis_settings.max_examples,
                "deadline": self.hypothesis_settings.deadline,
            },
            "results": [result.to_dict() for result in self.results],
        }

        output_path = Path(output_file)
        with open(output_path, "w") as f:
            json.dump(results_data, f, indent=2)

        print(f"\nResults saved to: {output_path.absolute()}")

    def get_failed_properties(self):
        """Get list of failed property numbers."""
        return [result.property_number for result in self.results if result.status == "failed"]

    def get_passed_properties(self):
        """Get list of passed property numbers."""
        return [result.property_number for result in self.results if result.status == "passed"]


class PropertyTestManager:
    """Manager for organizing and running property-based test suites."""

    @staticmethod
    def run_smoke_tests():
        """Run a quick smoke test of all properties with minimal examples."""
        runner = PropertyTestRunner(test_mode="fast")
        return runner.run_all_properties()

    @staticmethod
    def run_full_suite():
        """Run the full property-based test suite with standard settings."""
        runner = PropertyTestRunner(test_mode="normal")
        return runner.run_all_properties()

    @staticmethod
    def run_comprehensive_suite():
        """Run comprehensive property tests with maximum examples."""
        runner = PropertyTestRunner(test_mode="comprehensive")
        return runner.run_all_properties()

    @staticmethod
    def run_ui_properties():
        """Run UI-related properties (1, 2, 5, 7, 12, 13)."""
        ui_properties = [1, 2, 5, 7, 12, 13]
        runner = PropertyTestRunner(test_mode="normal")
        return runner.run_specific_properties(ui_properties)

    @staticmethod
    def run_crud_properties():
        """Run CRUD operation properties (3, 4, 6, 8, 9)."""
        crud_properties = [3, 4, 6, 8, 9]
        runner = PropertyTestRunner(test_mode="normal")
        return runner.run_specific_properties(crud_properties)

    @staticmethod
    def run_performance_properties():
        """Run performance-related properties (10, 11)."""
        performance_properties = [10, 11]
        runner = PropertyTestRunner(test_mode="normal")
        return runner.run_specific_properties(performance_properties)

    @staticmethod
    def run_accessibility_properties():
        """Run accessibility-related properties (12, 13, 14)."""
        accessibility_properties = [12, 13, 14]
        runner = PropertyTestRunner(test_mode="normal")
        return runner.run_specific_properties(accessibility_properties)


# CLI interface for running property tests
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python test_pbt_runner.py <command> [options]")
        print("Commands:")
        print("  smoke     - Run smoke tests (fast)")
        print("  full      - Run full test suite")
        print("  comprehensive - Run comprehensive tests")
        print("  ui        - Run UI properties")
        print("  crud      - Run CRUD properties")
        print("  performance - Run performance properties")
        print("  accessibility - Run accessibility properties")
        print("  property <numbers> - Run specific properties (e.g., 1,2,3)")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "smoke":
        results = PropertyTestManager.run_smoke_tests()
    elif command == "full":
        results = PropertyTestManager.run_full_suite()
    elif command == "comprehensive":
        results = PropertyTestManager.run_comprehensive_suite()
    elif command == "ui":
        results = PropertyTestManager.run_ui_properties()
    elif command == "crud":
        results = PropertyTestManager.run_crud_properties()
    elif command == "performance":
        results = PropertyTestManager.run_performance_properties()
    elif command == "accessibility":
        results = PropertyTestManager.run_accessibility_properties()
    elif command == "property" and len(sys.argv) > 2:
        try:
            property_numbers = [int(x.strip()) for x in sys.argv[2].split(",")]
            runner = PropertyTestRunner(test_mode="normal")
            results = runner.run_specific_properties(property_numbers)
        except ValueError:
            print("Error: Invalid property numbers. Use comma-separated integers.")
            sys.exit(1)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

    # Save results
    runner = PropertyTestRunner()
    runner.results = results
    runner.save_results(
        f"pbt_results_{command}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    )
