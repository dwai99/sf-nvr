"""Unit tests for settings_api credential handling (2026-06-02 fix).

Camera passwords / RTSP credentials must be masked in API responses and
restored (write-only) on save so a settings save never wipes secrets.
"""

import pytest

from nvr.web.settings_api import (
    SECRET_MASK,
    _redact_cameras,
    _reapply_rtsp_credentials,
    _restore_camera_secrets,
)


@pytest.mark.unit
class TestRedactCameras:
    def test_password_is_masked(self):
        cams = [{'id': 'c1', 'password': 'hunter2', 'rtsp_url': 'rtsp://admin:hunter2@10.0.0.1:554/s'}]
        out = _redact_cameras(cams)
        assert out[0]['password'] == SECRET_MASK
        assert 'hunter2' not in out[0]['rtsp_url']
        assert out[0]['rtsp_url'] == f'rtsp://admin:{SECRET_MASK}@10.0.0.1:554/s'

    def test_does_not_mutate_input(self):
        cams = [{'id': 'c1', 'password': 'hunter2', 'rtsp_url': 'rtsp://admin:hunter2@10.0.0.1:554/s'}]
        _redact_cameras(cams)
        assert cams[0]['password'] == 'hunter2', "original config must not be mutated"
        assert cams[0]['rtsp_url'] == 'rtsp://admin:hunter2@10.0.0.1:554/s'

    def test_handles_missing_fields(self):
        out = _redact_cameras([{'id': 'c1', 'name': 'Cam'}])
        assert out[0].get('password') in (None, '')  # nothing to mask, no crash


@pytest.mark.unit
class TestReapplyRtspCredentials:
    def test_rebuilds_when_masked(self):
        url = _reapply_rtsp_credentials(
            f'rtsp://admin:{SECRET_MASK}@10.0.0.1:554/s', 'admin', 'realpass',
            'rtsp://admin:realpass@10.0.0.1:554/s')
        assert url == 'rtsp://admin:realpass@10.0.0.1:554/s'

    def test_rebuilds_when_stripped(self):
        url = _reapply_rtsp_credentials(
            'rtsp://10.0.0.1:554/s', 'admin', 'realpass', 'rtsp://admin:realpass@10.0.0.1:554/s')
        assert url == 'rtsp://admin:realpass@10.0.0.1:554/s'

    def test_keeps_new_real_credentials(self):
        # User typed a genuinely new password -> trust the incoming URL
        url = _reapply_rtsp_credentials(
            'rtsp://admin:brandnew@10.0.0.1:554/s', 'admin', 'brandnew',
            'rtsp://admin:oldpass@10.0.0.1:554/s')
        assert url == 'rtsp://admin:brandnew@10.0.0.1:554/s'


@pytest.mark.unit
class TestRestoreCameraSecrets:
    def test_masked_password_restored_from_existing(self):
        existing = [{'id': 'c1', 'username': 'admin', 'password': 'realpass',
                     'rtsp_url': 'rtsp://admin:realpass@10.0.0.1:554/s'}]
        incoming = [{'id': 'c1', 'username': 'admin', 'password': SECRET_MASK,
                     'rtsp_url': f'rtsp://admin:{SECRET_MASK}@10.0.0.1:554/s'}]

        out = _restore_camera_secrets(incoming, existing)

        assert out[0]['password'] == 'realpass'
        assert out[0]['rtsp_url'] == 'rtsp://admin:realpass@10.0.0.1:554/s'

    def test_blank_password_restored(self):
        existing = [{'id': 'c1', 'username': 'admin', 'password': 'realpass',
                     'rtsp_url': 'rtsp://admin:realpass@10.0.0.1:554/s'}]
        incoming = [{'id': 'c1', 'username': 'admin', 'password': '',
                     'rtsp_url': 'rtsp://10.0.0.1:554/s'}]

        out = _restore_camera_secrets(incoming, existing)
        assert out[0]['password'] == 'realpass'
        assert out[0]['rtsp_url'] == 'rtsp://admin:realpass@10.0.0.1:554/s'

    def test_new_password_is_kept(self):
        existing = [{'id': 'c1', 'username': 'admin', 'password': 'oldpass',
                     'rtsp_url': 'rtsp://admin:oldpass@10.0.0.1:554/s'}]
        incoming = [{'id': 'c1', 'username': 'admin', 'password': 'newpass',
                     'rtsp_url': 'rtsp://admin:newpass@10.0.0.1:554/s'}]

        out = _restore_camera_secrets(incoming, existing)
        assert out[0]['password'] == 'newpass'
        assert out[0]['rtsp_url'] == 'rtsp://admin:newpass@10.0.0.1:554/s'

    def test_new_camera_passthrough(self):
        # No matching id in existing -> keep whatever client supplied
        incoming = [{'id': 'c2', 'username': 'admin', 'password': 'fresh',
                     'rtsp_url': 'rtsp://admin:fresh@10.0.0.9:554/s'}]
        out = _restore_camera_secrets(incoming, [])
        assert out[0]['password'] == 'fresh'

    def test_full_roundtrip_preserves_secret(self):
        """GET (redact) -> POST (restore) must yield the original secret."""
        existing = [{'id': 'c1', 'username': 'admin', 'password': 'realpass',
                     'rtsp_url': 'rtsp://admin:realpass@10.0.0.1:554/s'}]
        masked = _redact_cameras(existing)
        restored = _restore_camera_secrets(masked, existing)
        assert restored[0]['password'] == 'realpass'
        assert restored[0]['rtsp_url'] == 'rtsp://admin:realpass@10.0.0.1:554/s'
