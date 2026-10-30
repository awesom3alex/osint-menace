"""Parse fetched profile content locally; disable network calls and inferred identities."""
import json
import logging
import socket
import sys


def no_network(*args, **kwargs):
    raise OSError('Network requests are disabled in the profile parser.')


if __name__ == '__main__':
    logging.disable(logging.CRITICAL)
    from socid_extractor import main
    main.POSTPROCESSORS = [processor for processor in main.POSTPROCESSORS if processor.__name__ in ('StripInvalidGravatarUrls', 'NormalizeDates')]
    socket.getaddrinfo = no_network
    socket.create_connection = no_network
    socket.socket.connect = no_network
    socket.socket.connect_ex = no_network
    raw = sys.stdin.buffer.read(1_000_001)
    if len(raw) > 1_000_000:
        raise SystemExit(2)
    try:
        data = main.extract(raw.decode('utf-8', errors='replace'))
        print(json.dumps(data, ensure_ascii=False, default=str))
    except Exception:
        raise SystemExit(3) from None
