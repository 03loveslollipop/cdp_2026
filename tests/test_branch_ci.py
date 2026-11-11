"""Older branch layouts must reach their tests without requiring model files."""
import pytest

from ci.validate_structure import validate


@pytest.mark.parametrize('source_path', ['src', 'mlops_pipeline/src'])
def test_feature_branches_accept_both_historical_source_layouts(tmp_path, source_path):
    (tmp_path / 'README.md').write_text('Branch project')
    (tmp_path / 'tests').mkdir()
    (tmp_path / source_path).mkdir(parents=True)
    validate(tmp_path, mode='tests', ci_files=False)


def test_feature_branch_without_test_suite_fails_structure_check(tmp_path):
    (tmp_path / 'README.md').write_text('Branch project')
    with pytest.raises(ValueError, match='tests'):
        validate(tmp_path, mode='tests', ci_files=False)
