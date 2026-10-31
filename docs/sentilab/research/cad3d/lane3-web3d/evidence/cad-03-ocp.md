# cad-03: OCP (Python bindings to OCCT)

## PyPI cadquery-ocp

- URL: https://pypi.org/pypi/cadquery-ocp/json ; retrieved 2026-10-31T19:11:32Z; HTTP 200; SHA-256 `8ec25055c0b501dff11a42d4816f696502e5ea27201fcefc847f73b0163afe4b`
- info.version: `8.0.1.1.0`; info.license: `Apache-2.0`

## Releases (GitHub API https://api.github.com/repos/CadQuery/OCP/releases?per_page=5), body SHA-256 `15b97a4e2df81c5fc5bf33f04b8d810df272828f395ce79f831633bb1ec1dce0`

- 8.0.1.1 published 2026-09-24T09:19:03Z
- 8.0.1.0 published 2026-09-04T07:33:55Z
- 8.0.0.1 published 2026-08-29T16:23:26Z

## LICENSE at tag 8.0.1.1

### Source: https://raw.githubusercontent.com/CadQuery/OCP/8.0.1.1/LICENSE

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:12:27Z
- HTTP status: 200
- SHA-256 of the downloaded body: `a13caea71627202ad33cc4cafafdd18e667e16716488f8d9c568127121fb89fd`
- Bytes: 11346

Lines 1,3 (verbatim, line-numbered):

```text
    1                                   Apache License
    2                             Version 2.0, January 2004
    3                          http://www.apache.org/licenses/
```

## OCCT version pin at tag 8.0.1.1

### Source: https://raw.githubusercontent.com/CadQuery/OCP/8.0.1.1/conda/meta.yaml

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:12:36Z
- HTTP status: 200
- SHA-256 of the downloaded body: `a6624449bc66ebdf9b7d3d1023c47e63aa12599673870e98b9d2aff948ffbe2e`
- Bytes: 798

Lines 1,6 (verbatim, line-numbered):

```text
    1  {% set OCCT_VER = "8.0.1" %}
    2  {% set OCP_TWEAK = "1" %}
    3  
    4  package:
    5    name: ocp
    6    version: {{OCCT_VER}}.{{OCP_TWEAK}}
```

Lines 24,27 (verbatim, line-numbered):

```text
   24      - occt={{ OCCT_VER }}=all*
   25    run:
   26      - python {{ environ.get('PYTHON_VERSION') }}
   27      - occt={{ OCCT_VER }}=all*
```

### Source: https://raw.githubusercontent.com/CadQuery/OCP/8.0.1.1/environment.devenv.yml

- Retrieved (UTC, file mtime of the download): 2026-10-31T19:12:34Z
- HTTP status: 200
- SHA-256 of the downloaded body: `9555014dc2bfb55ed7cd2f3e6d3fe778786f82dc313c22acae7e5a38f6c1f0a8`
- Bytes: 587

Lines 1,8 (verbatim, line-numbered):

```text
    1  name: bindgen
    2  channels:
    3    - conda-forge
    4  dependencies:
    5    - occt=8.0.1=all*
    6    - pybind11=2.13.*
    7    - python={{ get_env("PYTHON_VERSION", default="3.13") }}
    8    - cmake >3.24
```

## Reading: OCP 8.0.1.1 is Apache-2.0 and its conda recipe pins OCCT 8.0.1.
