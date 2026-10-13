from data_sim import CHAIN_IDS, open_chain_db
from data_sim.auth import hash_password, verify_password


def test_hash_and_verify_roundtrip():
    h = hash_password("demo123")
    assert h.startswith("pbkdf2_sha256$")
    assert verify_password("demo123", h)
    assert not verify_password("demo124", h)


def test_random_salt_differs_but_given_salt_is_stable():
    assert hash_password("x") != hash_password("x")
    assert hash_password("x", salt=b"s" * 16) == hash_password("x", salt=b"s" * 16)


def test_malformed_hash_is_rejected():
    assert not verify_password("demo123", "")
    assert not verify_password("demo123", "md5$1$00$00")
    assert not verify_password("demo123", "pbkdf2_sha256$abc$zz$zz")


def test_demo_users_per_chain(data_dir):
    for chain_id in CHAIN_IDS:
        letter = chain_id[-1].lower()
        conn = open_chain_db(data_dir, chain_id, readonly=True)
        users = {r["username"]: r for r in conn.execute("SELECT * FROM users")}
        assert set(users) == {f"owner_{letter}", f"manager_{letter}1"}
        owner, manager = users[f"owner_{letter}"], users[f"manager_{letter}1"]
        assert owner["role"] == "owner" and owner["store_id"] is None
        assert manager["role"] == "store_manager"
        assert manager["store_id"] == f"{letter.upper()}-CH1"
        for u in users.values():
            assert u["chain_id"] == chain_id
            assert verify_password("demo123", u["password_hash"])
            assert not verify_password("wrong", u["password_hash"])
