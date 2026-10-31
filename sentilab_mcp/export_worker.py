"""One cancellable recorded-data export; receives only public verification keys."""
import json
import sys

from sentilab_core.dataset import export


def main():
    request = json.load(sys.stdin)
    result = export(request['root'], public_keys={key: bytes.fromhex(value)
                    for key, value in request['public_keys'].items()}, **request['arguments'])
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
