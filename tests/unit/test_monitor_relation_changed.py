import monitors_relation_changed


def test_has_main():
    # THIS IS A REALLY LAME TEST -- but it's a start for where there was nothing
    # if you add tests later, please do better than me
    assert hasattr(monitors_relation_changed, 'main')
