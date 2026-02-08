# SF-NVR Testing Guide

This document provides a comprehensive overview of the testing strategy for the SF-NVR application, designed to ensure commercial-grade quality and reliability.

## Quick Start

```bash
# Install test dependencies
pip install -r requirements-test.txt
npm install

# Run unit tests
pytest tests/unit -v

# Run E2E tests
npm run test:e2e
```

## Test Suite Overview

The SF-NVR test suite includes **7 types of tests** across **4 testing frameworks**:

| Test Type | Framework | Files | Coverage |
|-----------|-----------|-------|----------|
| Unit Tests | pytest | tests/unit/ | 90%+ |
| Integration Tests | pytest | tests/integration/ | 85%+ |
| API Tests | pytest + httpx | tests/api/ | 85%+ |
| E2E Tests | Playwright | tests/e2e/ | N/A |
| Performance Tests | pytest-benchmark | tests/performance/ | N/A |
| Visual Regression | Playwright | tests/visual/ | N/A |
| Security Scans | Safety, Bandit | N/A | N/A |

## Architecture

### Test Directory Structure

```
tests/
├── __init__.py
├── conftest.py                 # Shared fixtures
├── README.md                   # Detailed testing docs
├── fixtures/                   # Test data
│   ├── sample_videos/          # Test video files
│   ├── config_samples/         # Test configurations
│   └── mock_rtsp_streams/      # Mock RTSP servers
├── unit/                       # Unit tests (pytest)
│   ├── test_storage_manager.py
│   ├── test_alert_system.py
│   ├── test_motion_heatmap.py
│   ├── test_playback_db.py
│   └── test_recorder.py
├── integration/                # Integration tests
│   ├── test_camera_lifecycle.py
│   ├── test_recording_pipeline.py
│   └── test_storage_cleanup.py
├── api/                        # API tests
│   ├── test_camera_endpoints.py
│   ├── test_playback_endpoints.py
│   └── test_storage_endpoints.py
├── e2e/                        # E2E tests (Playwright)
│   ├── test_live_view.spec.ts
│   ├── test_playback.spec.ts
│   └── test_settings.spec.ts
├── performance/                # Performance tests
│   ├── test_streaming_load.py
│   └── test_database_queries.py
└── visual/                     # Visual regression
    └── test_ui_snapshots.spec.ts
```

## Test Coverage Goals

### Overall Target: 85%

#### Critical Modules (90%+ required):
- `nvr/core/storage_manager.py` - Automatic cleanup logic
- `nvr/core/alert_system.py` - Alert generation and delivery
- `nvr/core/playback_db.py` - Database operations
- `nvr/core/recorder.py` - Recording logic

#### Standard Modules (75%+ required):
- `nvr/web/api.py` - API endpoints
- `nvr/core/motion_heatmap.py` - Heatmap generation
- `nvr/core/config.py` - Configuration management

## CI/CD Pipeline

### GitHub Actions Workflow

The test suite runs automatically on:

**Pull Requests to main/develop:**
- Code quality checks (Black, Pylint, Flake8)
- Unit tests (Python 3.9, 3.10, 3.11)
- Integration tests
- API tests
- E2E tests (Chromium, Firefox, WebKit)

**Push to main:**
- All above tests
- Performance benchmarks
- Security scans

**Nightly (2 AM UTC):**
- Full test suite
- Visual regression tests
- Extended performance tests

### Passing Criteria

For a PR to be merged:

✅ All unit tests pass
✅ All integration tests pass
✅ All API tests pass
✅ All E2E tests pass (3 browsers)
✅ Code coverage ≥ 75%
✅ No critical security vulnerabilities
✅ Code formatting passes (Black)

## Testing Best Practices

### 1. Test Isolation

Each test must be independent:

```python
# Good - uses fixtures for isolation
def test_cleanup(storage_manager, temp_dir):
    # Fresh storage manager and temp dir for each test
    stats = storage_manager.check_and_cleanup()
    assert stats['cleanup_triggered'] is False

# Bad - relies on global state
def test_cleanup():
    # Assumes specific state from previous tests
    storage_manager.cleanup()
```

### 2. Use Appropriate Markers

Mark tests for selective execution:

```python
@pytest.mark.unit
def test_basic_function():
    pass

@pytest.mark.slow
def test_expensive_operation():
    pass

@pytest.mark.integration
async def test_full_workflow():
    pass
```

Run specific tests:
```bash
pytest -m unit          # Only unit tests
pytest -m "not slow"    # Skip slow tests
pytest -m integration   # Only integration tests
```

### 3. Descriptive Test Names

```python
# Good - clear what's being tested
def test_cleanup_deletes_files_older_than_retention_period():
    pass

def test_alert_cooldown_prevents_spam_within_5_minutes():
    pass

# Bad - unclear what's tested
def test_cleanup():
    pass

def test_alerts():
    pass
```

### 4. Arrange-Act-Assert Pattern

```python
def test_storage_cleanup():
    # Arrange - set up test data
    old_file = create_aged_file(path, days_old=10)

    # Act - execute the operation
    stats = storage_manager.check_and_cleanup()

    # Assert - verify results
    assert not old_file.exists()
    assert stats['files_deleted'] == 1
```

### 5. Mock External Dependencies

```python
# Mock RTSP streams instead of using real cameras
@pytest.fixture
def mock_rtsp_server():
    server = MockRTSPServer(video_file='test.mp4', port=8554)
    server.start()
    yield f"rtsp://localhost:8554/test"
    server.stop()

# Mock webhook endpoints
@responses.activate
def test_webhook_alert():
    responses.add(
        responses.POST,
        'http://webhook.test/alerts',
        json={'success': True},
        status=200
    )
    # Test webhook delivery
```

## Key Test Scenarios

### Unit Tests

**Storage Manager:**
- ✅ Files older than retention deleted
- ✅ Recent files preserved
- ✅ Cleanup targets correct disk usage
- ✅ Database entries synchronized
- ✅ Retention statistics accurate

**Alert System:**
- ✅ Camera state transitions trigger alerts
- ✅ Cooldown prevents alert spam
- ✅ Multiple alert handlers work
- ✅ Storage thresholds trigger alerts
- ✅ Alert history capped at max

**Motion Heatmap:**
- ✅ Coordinate scaling correct
- ✅ Motion data accumulated
- ✅ Heatmap normalized to 0-255
- ✅ Daily heatmaps cached
- ✅ Colormap applied correctly

### E2E Tests

**Live View:**
- ✅ Page loads successfully
- ✅ All cameras displayed
- ✅ Live streams show video
- ✅ Health indicators accurate
- ✅ Navigation works
- ✅ Camera rename functional

**Playback:**
- ✅ Date/time selection works
- ✅ Timeline displays recordings
- ✅ Video plays from timeline click
- ✅ Keyboard shortcuts functional
- ✅ Playback controls work
- ✅ Multi-camera synchronization
- ✅ Export functionality works

### Performance Tests

**Benchmarks:**
- ✅ Storage cleanup (10K files) < 5s
- ✅ Heatmap generation (1K events) < 2s
- ✅ Time range query (1 week) < 100ms
- ✅ 10 concurrent MJPEG streams stable

## Debugging Failed Tests

### Pytest Debugging

```bash
# Show print statements
pytest tests/unit -v -s

# Drop into debugger on failure
pytest tests/unit --pdb

# Run only failed tests from last run
pytest --lf

# Step through test execution
pytest --trace
```

### Playwright Debugging

```bash
# Run in headed mode (see browser)
npm run test:e2e:headed

# Run in UI mode (step through)
npm run test:e2e:ui

# Run in debug mode
PWDEBUG=1 npm run test:e2e

# View trace after failure
npx playwright show-trace test-results/trace.zip
```

### Common Issues

**1. Database locked errors**
```python
# Solution: Ensure proper cleanup
@pytest.fixture
def playback_db(temp_dir):
    db = PlaybackDatabase(str(temp_dir / "test.db"))
    yield db
    db.close()  # Always close!
```

**2. Flaky E2E tests**
```typescript
// Solution: Use proper waits
await page.waitForSelector('.element', { state: 'visible' });
await expect(page.locator('.element')).toBeVisible();

// Not: await page.waitForTimeout(2000); // Flaky!
```

**3. Import errors in tests**
```bash
# Solution: Add project root to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

## Test Maintenance

### When to Update Tests

1. **Feature added**: Write new tests first (TDD)
2. **Bug fixed**: Add regression test
3. **Code refactored**: Update tests to match
4. **API changed**: Update integration/E2E tests
5. **UI changed**: Update E2E tests and snapshots

### Removing Obsolete Tests

When removing a feature:
1. Delete corresponding tests
2. Update fixtures if needed
3. Check coverage hasn't dropped below threshold
4. Update documentation

### Keeping Fixtures Fresh

Review fixtures quarterly:
- Remove unused fixtures
- Update test data to match production
- Refactor duplicated setup code

## Performance Optimization

### Speeding Up Tests

**1. Use markers to skip slow tests during development**
```bash
pytest -m "not slow"  # Skip slow tests
```

**2. Run tests in parallel**
```bash
pytest -n auto  # Use pytest-xdist
```

**3. Use test fixtures effectively**
```python
# Module-scoped fixtures for expensive setup
@pytest.fixture(scope="module")
def expensive_resource():
    resource = create_expensive_resource()
    yield resource
    cleanup(resource)
```

**4. Mock external services**
```python
# Don't make real HTTP requests
@responses.activate
def test_webhook():
    responses.add(responses.POST, 'http://api.example.com', json={})
    # Test code
```

## Reporting

### Coverage Reports

```bash
# Generate HTML coverage report
pytest --cov=nvr --cov-report=html
open htmlcov/index.html

# Generate XML for CI
pytest --cov=nvr --cov-report=xml

# Show missing lines
pytest --cov=nvr --cov-report=term-missing
```

### Playwright Reports

```bash
# View last test run
npm run test:report

# Reports available at:
# test-results/playwright-report/index.html
```

### Performance Reports

```bash
# Compare with baseline
pytest tests/performance --benchmark-compare=baseline

# Generate histogram
pytest tests/performance --benchmark-histogram
```

## Contributing

### Adding New Tests

1. **Identify what needs testing**
   - New feature?
   - Bug fix?
   - Uncovered code path?

2. **Choose appropriate test type**
   - Logic/algorithm → Unit test
   - Component interaction → Integration test
   - API endpoint → API test
   - User workflow → E2E test

3. **Write the test**
   - Follow existing patterns
   - Use descriptive names
   - Add docstrings
   - Use appropriate markers

4. **Verify test quality**
   - Test fails when it should
   - Test passes when it should
   - Test is isolated
   - Test is deterministic

5. **Update documentation**
   - Add test to appropriate category
   - Update coverage goals if needed

### Code Review Checklist

Before submitting PR:

- [ ] All tests pass locally
- [ ] New features have tests
- [ ] Bug fixes have regression tests
- [ ] Coverage ≥ 75%
- [ ] Tests are isolated
- [ ] Tests have clear names
- [ ] No flaky tests
- [ ] Documentation updated

## Resources

- **Pytest**: https://docs.pytest.org/
- **Playwright**: https://playwright.dev/
- **Coverage.py**: https://coverage.readthedocs.io/
- **pytest-benchmark**: https://pytest-benchmark.readthedocs.io/

## Support

For test-related questions:
1. Check `tests/README.md` for detailed docs
2. Review existing tests for patterns
3. Check CI logs for failure details
4. Ask in project issues/discussions

---

**Remember**: Good tests are the foundation of a reliable, commercial-grade application. Invest time in writing quality tests and they'll pay dividends in confidence and stability.
