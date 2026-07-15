import build


def test_hash_password_is_sha512_crypt():
    h = build.hash_password("michaems", salt="testsalt")
    assert h.startswith("$6$testsalt$")
    # crypt format: $6$<salt>$<86-char hash>
    assert len(h.split("$")[3]) == 86


def test_hash_password_deterministic_with_salt():
    a = build.hash_password("michaems", salt="testsalt")
    b = build.hash_password("michaems", salt="testsalt")
    assert a == b


def test_hash_password_random_salt():
    h = build.hash_password("michaems")
    assert h.startswith("$6$")


def test_netmask_to_prefix():
    assert build.netmask_to_prefix("255.255.255.0") == 24
    assert build.netmask_to_prefix("255.255.0.0") == 16
    assert build.netmask_to_prefix("255.255.255.255") == 32
