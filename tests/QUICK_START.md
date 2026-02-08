# Test Suite Quick Start Guide

## Installation (One-Time Setup)

```bash
# Install Python test dependencies
pip install -r requirements-test.txt

# Install Node dependencies for Playwright
npm install

# Install Playwright browsers
npx playwright install --with-deps
```

## Running Tests

### Unit Tests (Fastest - Run These First)

```bash
# All unit tests
pytest tests/unit -v

# Specific test file
pytest tests/unit/test_storage_manager.py -v

# Specific test
pytest tests/unit/test_storage_manager.py::TestStorageManager::test_cleanup_old_files_retention_policy -v

# Skip slow tests
pytest tests/unit -m "not slow" -v
```

### API Tests

```bash
# All API tests
pytest tests/api -v -m api

# Note: Some tests require running NVR instance on localhost:8080
```

### E2E Tests (Comprehensive UI Testing)

```bash
# All E2E tests (all browsers)
npm run test:e2e

# Single browser
npm run test:e2e:chromium
npm run test:e2e:firefox
npm run test:e2e:webkit

# Interactive debugging
npm run test:e2e:ui

# See browser (headed mode)
npm run test:e2e:headed
```

### All Tests

```bash
# Python tests
pytest tests/ -v

# E2E tests
npm run test:e2e

# Everything
pytest tests/ -v && npm run test:e2e
```

## Coverage

```bash
# Generate coverage report
pytest tests/unit --cov=nvr --cov-report=html

# Open report in browser
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## Common Commands

```bash
# Test with output visible
pytest tests/unit -v -s

# Stop on first failure
pytest tests/unit -x

# Run only failed tests from last run
pytest --lf

# Run tests matching pattern
pytest -k "storage" -v

# Generate JUnit XML report
pytest tests/unit --junit-xml=results.xml
```

## Debugging

```bash
# Drop into debugger on failure
pytest tests/unit --pdb

# Playwright debug mode
PWDEBUG=1 npm run test:e2e

# View Playwright trace
npx playwright show-trace test-results/path-to-trace.zip
```

## Before Committing

```bash
# Run fast tests
pytest tests/unit -m "not slow" -v

# Check code formatting
black --check nvr/

# Format code
black nvr/

# Run linting
flake8 nvr/ --max-line-length=120
```

## CI/CD

Tests run automatically on:
- Every push
- Every pull request
- Nightly at 2 AM UTC

View results in GitHub Actions tab.

## Help

For detailed documentation, see:
- `tests/README.md` - Comprehensive testing guide
- `TESTING.md` - Testing strategy and best practices
- `TEST_SUITE_SUMMARY.md` - Implementation summary
