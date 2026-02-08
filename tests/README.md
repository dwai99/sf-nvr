# SF-NVR Test Suite

Comprehensive regression test suite for the SF-NVR application using Playwright, pytest, and other testing tools to ensure commercial-grade quality.

## Table of Contents

- [Overview](#overview)
- [Test Types](#test-types)
- [Setup](#setup)
- [Running Tests](#running-tests)
- [Test Coverage](#test-coverage)
- [CI/CD Integration](#cicd-integration)
- [Writing Tests](#writing-tests)

## Overview

The SF-NVR test suite includes:

- **Unit Tests**: Core business logic and algorithms
- **Integration Tests**: Component interaction and workflows
- **API Tests**: REST API endpoints and responses
- **E2E Tests**: Full user workflows with Playwright
- **Performance Tests**: Load testing and benchmarks
- **Visual Regression Tests**: UI consistency checks

## Test Types

### Unit Tests (`tests/unit/`)

Test individual components in isolation:

- Storage manager (cleanup, retention)
- Alert system (notifications, cooldowns)
- Motion heatmap generation
- Playback database operations
- Recording logic

**Coverage Target**: 90%+

### Integration Tests (`tests/integration/`)

Test component interactions:

- Camera lifecycle (add/remove/rename)
- Recording pipeline (RTSP → disk)
- Storage cleanup with database sync
- Alert webhook delivery
- Motion detection workflow

### API Tests (`tests/api/`)

Test REST API endpoints:

- Camera health and control endpoints
- Playback video streaming
- Storage statistics and cleanup
- Motion heatmap generation
- Settings updates

### E2E Tests (`tests/e2e/`)

Test complete user workflows:

- Live view page (camera grid, health indicators)
- Playback page (timeline, seeking, controls)
- Keyboard shortcuts
- Settings configuration
- Export functionality

**Browsers Tested**: Chromium, Firefox, WebKit

### Performance Tests (`tests/performance/`)

Test system performance:

- Concurrent streaming load
- Multi-camera recording
- Database query speed
- Storage cleanup efficiency

### Visual Regression Tests (`tests/visual/`)

Test UI consistency:

- Screenshot comparison
- Layout verification
- Responsive design

## Setup

### Prerequisites

```bash
# Python 3.9+
python --version

# Node.js 18+
node --version

# System dependencies (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install -y ffmpeg libopencv-dev python3-opencv
```

### Install Test Dependencies

```bash
# Python test dependencies
pip install -r requirements-test.txt

# Node dependencies for Playwright
npm install

# Install Playwright browsers
npx playwright install --with-deps
```

## Running Tests

### Unit Tests

```bash
# Run all unit tests
pytest tests/unit -v

# Run specific test file
pytest tests/unit/test_storage_manager.py -v

# Run with coverage
pytest tests/unit --cov=nvr --cov-report=html

# Run fast tests only (skip slow)
pytest tests/unit -m "not slow"
```

### Integration Tests

```bash
# Run all integration tests
pytest tests/integration -v -m integration

# Run specific integration test
pytest tests/integration/test_camera_lifecycle.py -v
```

### API Tests

```bash
# Run all API tests
pytest tests/api -v -m api

# Run with test server
# Note: Requires running SF-NVR instance on localhost:8080
```

### E2E Tests (Playwright)

```bash
# Run all E2E tests
npm run test:e2e

# Run in UI mode (debug)
npm run test:e2e:ui

# Run specific browser
npm run test:e2e:chromium
npm run test:e2e:firefox
npm run test:e2e:webkit

# Run with headed browser (see what's happening)
npm run test:e2e:headed

# Update visual snapshots
npm run test:update-snapshots
```

### Performance Tests

```bash
# Run performance benchmarks
pytest tests/performance -v -m performance --benchmark-only

# Save benchmark results
pytest tests/performance --benchmark-save=baseline
```

### All Tests

```bash
# Run everything (takes 15-30 minutes)
pytest tests/ -v
npm run test:e2e
```

## Test Coverage

### Current Coverage

Check coverage report:

```bash
pytest tests/unit --cov=nvr --cov-report=html
open htmlcov/index.html
```

### Coverage Requirements

| Module | Minimum | Target |
|--------|---------|--------|
| Overall | 75% | 85% |
| storage_manager.py | 90% | 95% |
| alert_system.py | 90% | 95% |
| playback_db.py | 90% | 95% |
| recorder.py | 85% | 90% |

## CI/CD Integration

### GitHub Actions

The CI pipeline runs automatically on:

- **Pull Requests**: Unit + Integration + API tests
- **Push to main/develop**: All tests including E2E
- **Nightly**: Full suite including performance tests

### Workflow Jobs

1. **Code Quality**: Black, Pylint, Flake8
2. **Unit Tests**: Python 3.9, 3.10, 3.11
3. **Integration Tests**: Component workflows
4. **API Tests**: Endpoint validation
5. **E2E Tests**: Chromium, Firefox, WebKit
6. **Performance Tests**: Benchmarks (main branch only)
7. **Security Scan**: Safety, Bandit

### View Results

- GitHub Actions: `.github/workflows/ci.yml`
- Coverage Reports: Uploaded to Codecov
- Playwright Reports: Artifacts in GitHub Actions

## Writing Tests

### Unit Test Template

```python
import pytest
from nvr.core.your_module import YourClass

@pytest.mark.unit
class TestYourClass:
    """Test cases for YourClass"""

    def test_basic_functionality(self):
        """Test basic functionality"""
        obj = YourClass()
        assert obj.method() == expected_value

    def test_edge_case(self):
        """Test edge case behavior"""
        obj = YourClass()
        result = obj.method(edge_case_input)
        assert result is not None
```

### E2E Test Template

```typescript
import { test, expect } from '@playwright/test';

test.describe('Feature Name', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/your-page');
  });

  test('should do something', async ({ page }) => {
    await page.locator('#element').click();
    await expect(page.locator('.result')).toBeVisible();
  });
});
```

### Best Practices

1. **Use fixtures**: Leverage pytest/Playwright fixtures for setup
2. **Mark tests**: Use `@pytest.mark.unit`, `@pytest.mark.slow`, etc.
3. **Test isolation**: Each test should be independent
4. **Clear assertions**: Make failures easy to understand
5. **Mock external dependencies**: Don't rely on real RTSP cameras
6. **Document tests**: Add docstrings explaining what's being tested

## Test Fixtures

### Common Fixtures (conftest.py)

- `temp_dir`: Temporary directory for test files
- `test_config`: Test configuration (YAML)
- `playback_db`: Temporary SQLite database
- `storage_manager`: Storage manager instance
- `alert_system`: Alert system instance
- `sample_recording_segments`: Pre-populated test segments
- `sample_motion_events`: Test motion event data

### Using Fixtures

```python
def test_with_fixtures(temp_dir, playback_db):
    """Test using shared fixtures"""
    # temp_dir and playback_db are automatically set up
    # and cleaned up after the test
    pass
```

## Debugging Tests

### Pytest Debugging

```bash
# Run with print statements visible
pytest tests/unit -v -s

# Run single test
pytest tests/unit/test_storage_manager.py::TestStorageManager::test_init_storage_manager -v

# Drop into debugger on failure
pytest tests/unit --pdb
```

### Playwright Debugging

```bash
# Run in headed mode
npm run test:e2e:headed

# Run in UI mode (step through)
npm run test:e2e:ui

# Run in debug mode
npm run test:e2e:debug
```

### Viewing Playwright Traces

```bash
# After test failure, view trace
npx playwright show-trace test-results/path-to-trace.zip
```

## Continuous Improvement

### Adding New Tests

1. Identify untested code paths
2. Write failing test first (TDD)
3. Implement feature/fix
4. Verify test passes
5. Check coverage increased

### Maintaining Tests

- Review and update tests when features change
- Remove obsolete tests
- Refactor duplicated test code
- Keep fixtures up to date

## Test Data

### Sample Videos

Located in `tests/fixtures/sample_videos/`:

- `test_stream.mp4`: 30-second test video
- `motion_test.mp4`: Video with motion events
- `long_recording.mp4`: 5-minute test recording

### Mock RTSP Streams

Use `tests/fixtures/mock_rtsp_server.py` to serve test videos as RTSP streams during testing.

## Performance Benchmarks

### Running Benchmarks

```bash
# Run with baseline
pytest tests/performance --benchmark-only

# Compare with baseline
pytest tests/performance --benchmark-compare=baseline

# Generate histogram
pytest tests/performance --benchmark-histogram
```

### Benchmark Targets

- Storage cleanup (10,000 files): < 5 seconds
- Heatmap generation (1,000 events): < 2 seconds
- Time range query (1 week): < 100ms
- Concurrent streams (10 clients): < 10% frame drop

## Troubleshooting

### Common Issues

**Import errors**:
```bash
# Ensure project root is in PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

**Database locked errors**:
```bash
# Ensure tests clean up properly
pytest tests/unit -v --setup-show
```

**Playwright browser not found**:
```bash
# Reinstall browsers
npx playwright install --with-deps
```

**Coverage not working**:
```bash
# Install coverage tools
pip install pytest-cov coverage
```

## Contributing

When adding new features:

1. Write tests first (TDD)
2. Ensure all tests pass
3. Maintain >75% coverage
4. Update this documentation
5. Add test to CI pipeline if needed

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Playwright Documentation](https://playwright.dev/)
- [Coverage.py Documentation](https://coverage.readthedocs.io/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)

## License

Same as SF-NVR project license.
