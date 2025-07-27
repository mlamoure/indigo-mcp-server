#!/usr/bin/env python3
"""
Test runner script for MCP Server plugin.
"""

import sys
import os
import subprocess
from pathlib import Path


def setup_python_path():
    """Set up Python path to include plugin modules."""
    # Add the plugin directory to Python path
    plugin_dir = Path(__file__).parent / "MCP Server.indigoPlugin/Contents/Server Plugin"
    if str(plugin_dir) not in sys.path:
        sys.path.insert(0, str(plugin_dir))


def install_test_dependencies():
    """Install test dependencies."""
    print("Installing test dependencies...")
    try:
        subprocess.run([
            sys.executable, "-m", "pip", "install", "-r", "test_requirements.txt"
        ], check=True)
        print("✓ Test dependencies installed")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install test dependencies: {e}")
        return False
    return True


def run_tests(test_args=None):
    """Run the test suite."""
    setup_python_path()
    
    # Default test arguments
    if test_args is None:
        test_args = [
            "-v",  # Verbose output
            "--tb=short",  # Short traceback format
            "--color=yes",  # Colored output
            "--durations=10",  # Show 10 slowest tests
        ]
    
    # Add test directory
    test_dir = "tests"
    test_args.append(test_dir)
    
    print("Running MCP Server plugin tests...")
    print(f"Test command: pytest {' '.join(test_args)}")
    print("-" * 60)
    
    try:
        result = subprocess.run([sys.executable, "-m", "pytest"] + test_args)
        return result.returncode == 0
    except FileNotFoundError:
        print("✗ pytest not found. Please install pytest first.")
        return False


def run_coverage_tests():
    """Run tests with coverage reporting."""
    coverage_args = [
        "--cov=mcp_server",
        "--cov=interfaces",
        "--cov-report=html",
        "--cov-report=term-missing",
        "--cov-fail-under=80"
    ]
    
    print("Running tests with coverage...")
    return run_tests(coverage_args)


def main():
    """Main test runner function."""
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "install":
            install_test_dependencies()
        elif command == "coverage":
            if not install_test_dependencies():
                sys.exit(1)
            success = run_coverage_tests()
            sys.exit(0 if success else 1)
        elif command == "help":
            print("Usage: python run_tests.py [command]")
            print("Commands:")
            print("  install   - Install test dependencies")
            print("  coverage  - Run tests with coverage reporting")
            print("  help      - Show this help message")
            print("  (no args) - Run basic tests")
        else:
            print(f"Unknown command: {command}")
            sys.exit(1)
    else:
        # Run basic tests
        if not install_test_dependencies():
            sys.exit(1)
        success = run_tests()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()