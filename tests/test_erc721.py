from nftmeow.indexer import decode_transfer_event


def test_decode_oz_event():
    event = decode_transfer_event([b"\x00", b"\x01", b"\x10", b"\x00"])

    assert event.from_address == 0
    assert event.to_address == 1
    assert event.token_id.id == 16


def test_decode_felt_event():
    pass
