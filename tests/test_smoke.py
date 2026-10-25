import retrobake


def test_package_imports_and_has_version():
    assert isinstance(retrobake.__version__, str)
    assert retrobake.__version__.count(".") == 2
