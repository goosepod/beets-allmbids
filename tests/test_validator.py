"""The standalone validator remains meaningful with optimized Python."""
import hashlib
import io
from pathlib import Path
import subprocess
import sys

import pytest

# Import by filename: tools is shipped in the sdist, not the plugin wheel.
import importlib.util
spec = importlib.util.spec_from_file_location(
    'validate_copies', Path(__file__).resolve().parents[1] / 'tools' / 'validate_copies.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def test_hashing_large_file_and_pipe_without_file_digest(tmp_path, monkeypatch):
    monkeypatch.delattr(hashlib, 'file_digest', raising=False)
    content = b'example\x00' * 300000
    path = tmp_path / 'input'
    path.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()
    assert validator.hash_file(path) == expected
    assert validator.stream_digest(io.BytesIO(content)) == expected


@pytest.mark.parametrize('optimized', [False, True])
def test_failed_preservation_check_always_raises(optimized):
    script = (
        "import importlib.util; "
        f"s = importlib.util.spec_from_file_location('validator', {str(spec.origin)!r}); "
        "v = importlib.util.module_from_spec(s); s.loader.exec_module(v); "
        "v.require(False, 'Decoded audio changed')"
    )
    args = [sys.executable] + (['-O'] if optimized else []) + ['-c', script]
    result = subprocess.run(args, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'ValueError: Decoded audio changed' in result.stderr


@pytest.mark.parametrize('legacy', [False, True])
def test_validator_accepts_item_records_and_ignores_summary(legacy):
    import json
    item = {'path': 'copy.flac', 'changes': {'TAG': {'before': [], 'after': ['id']}}}
    if not legacy:
        item.update(type='item', status='changed')
    output = '\n'.join(json.dumps(record) for record in
                       (item, {'type': 'summary', 'processed': 1}))
    assert validator.command_changes(output, 1) == {item['path']: item['changes']}


@pytest.mark.parametrize('status', ['skipped', 'failed'])
def test_validator_rejects_missing_or_unsuccessful_items(status):
    import json
    output = json.dumps({'type': 'item', 'path': 'copy.flac', 'status': status, 'changes': {}})
    with pytest.raises(ValueError, match='skipped or failed'):
        validator.command_changes(output, 1)
    with pytest.raises(ValueError, match='every validation item'):
        validator.command_changes('', 1)
