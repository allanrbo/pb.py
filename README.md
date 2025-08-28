# pb.py

A tiny, dependency-free, practical protobuf (proto3) encoder/decoder. For those situations where you need just a little bit of protobuf in your project, and don't want to bother with the whole proto ecosystem of codegen and deps.

Author: Allan Riordan Boll

## Overview

- Proto3 binary encoding with schemas literally embedded in your code (no codegen).
- Supports common scalars, nested messages, repeated fields, and oneof.


## Installation

This is seriously tiny, so I'd suggest you just copy the `pb.py` file into your project. I'm not going to bother with pip here.


## Supported scalar types

- Integers: `varint`/`uint64`, `uint32`, `int64`, `int32`, `sint`/`sint64`, `sint32`
- Fixed-width (unsigned): `fixed32`, `fixed64`
- Fixed-width (signed): `sfixed32`, `sfixed64`
- Floating-point: `float`, `double`
- Other: `bool`, `string` (UTF‑8), `bytes`


## Examples

1) Basic

```python
from pb import pb_encode, pb_decode

schema = [
  ("varint", "id", 1),
  ("string", "name", 2),
]
data = {"id": 7, "name": "ok"}
encoded_bytes = pb_encode(data, schema)

assert pb_decode(b'\x08\x07\x12\x02ok', schema) == data
```

2) Repeated + nested

```python

child_schema = [
  ("sint", "x", 1),
  ("fixed32", "y", 2),
]
parent_schema = [
  ("repeated", "pts", 1, child_schema),
]
data = {
  "pts": [
    {"x": -1, "y": 10},
    {"x": 2, "y": 20},
  ],
}
encoded_bytes = pb_encode(data, parent_schema)

assert pb_decode(b'\n\x07\x08\x01\x15\n\x00\x00\x00\n\x07\x08\x04\x15\x14\x00\x00\x00', parent_schema) == data
```

3) Oneof

```python

schema = [
    ("oneof", "my_choice", [
      ("varint", "a", 1),
      ("string", "s", 2),
    ]),
    ("varint", "tail", 3),
]
data = {"a": 7, "tail": 1}
encoded_bytes = pb_encode(data, schema)
# Encoding with both set raises ValueError.

assert pb_decode(b'\x08\x07\x18\x01', schema) == data
```


## Recursion in your protos

Alternatively to the tuple based schemas, you may pass in your schema in a
special dict form. See test_pb.py for examples of this. You only really need
this if your have recursive/circular protos.


## AI

Written with support from GPT-5.
