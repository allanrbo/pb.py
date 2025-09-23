"""
https://github.com/allanrbo/pb.py
"""

import struct


_MAX_VARINT_BYTES = 10  # uint64 max
_MAX_NESTING_DEPTH = 100


def _read_varint(b, i):
    shift = 0
    n = 0
    read = 0
    blen = len(b)
    while True:
        if i >= blen:
            raise ValueError("truncated varint")
        c = b[i]
        i += 1
        read += 1
        n |= (c & 0x7F) << shift
        if not (c & 0x80):
            break
        if read >= _MAX_VARINT_BYTES:
            raise ValueError("varint too long")
        shift += 7
    return n, i


def _write_varint(n):
    if n < 0:
        raise ValueError("varint requires non-negative integer; use 'sint' for signed")
    out = bytearray()
    while True:
        to_write = n & 0x7F
        n >>= 7
        if n:
            out.append(to_write | 0x80)
        else:
            out.append(to_write)
            break
    return bytes(out)


def zigzag_encode(n):
    return (n << 1) ^ (n >> 63)


def zigzag_decode(n):
    return (n >> 1) ^ -(n & 1)


def _zz32(n):
    # zigzag for 32-bit signed
    n = int(n)
    if n < -0x80000000 or n > 0x7FFFFFFF:
        raise ValueError("sint32 out of range")
    v = (n << 1) ^ (n >> 31)
    return v & 0xFFFFFFFF


def _i32_from_uvarint(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v >= 0x80000000 else v


def _i64_from_uvarint(v):
    return v - 0x10000000000000000 if v >= 0x8000000000000000 else v


def _i32_to_uvarint(n):
    # represent signed 32-bit as 64-bit varint two's complement
    n = int(n)
    if n < 0:
        u = (n & 0xFFFFFFFF) | 0xFFFFFFFF00000000
    else:
        u = n & 0xFFFFFFFF
    return u & 0xFFFFFFFFFFFFFFFF


def _read_fixed32(b, i):
    if i + 4 > len(b):
        raise ValueError("truncated fixed32")
    v = struct.unpack_from("<I", b, i)[0]
    return v, i + 4


def _write_fixed32(v):
    return struct.pack("<I", v)


def _read_fixed64(b, i):
    if i + 8 > len(b):
        raise ValueError("truncated fixed64")
    v = struct.unpack_from("<Q", b, i)[0]
    return v, i + 8


def _write_fixed64(v):
    return struct.pack("<Q", v)


def _write_sfixed32(v):
    return struct.pack("<i", int(v))


def _write_sfixed64(v):
    return struct.pack("<q", int(v))


_ScalarTypes = {
    # integer families
    "varint", "uint64", "uint32", "int64", "int32", "sint", "sint64", "sint32",
    # signed fixed-width integers
    "sfixed32", "sfixed64",
    # fixed-width integer/float
    "fixed32", "fixed64", "float", "double",
    # misc
    "bool", "string", "bytes",
}


def _normalize_schema(schema):
    if not schema:
        return {"fields": {}, "names": {}}
    # Pass through if already normalized
    if isinstance(schema, dict) and "fields" in schema and "names" in schema:
        return schema
    fields, names = {}, {}
    for item in schema:
        if not isinstance(item, tuple):
            raise TypeError("schema must be list of tuples")

        # oneof group: ("oneof", group_name, [ alternatives ])
        if len(item) == 3 and item[0] == "oneof":
            _, group_name, alts = item
            if not isinstance(alts, (list, tuple)):
                raise ValueError("oneof alternatives must be a list")
            # Normalize each alternative and mark with oneof group
            for alt in alts:
                if not isinstance(alt, tuple):
                    raise TypeError("oneof alternative must be a tuple")
                # Allow both 3-tuple and 4-tuple forms for alternatives
                if len(alt) == 3:
                    typ_or_schema, name, fid = alt
                    if isinstance(typ_or_schema, (list, tuple)):
                        fs = {"kind": "message", "schema": _normalize_schema(typ_or_schema), "name": name, "oneof": group_name}
                    else:
                        typ = typ_or_schema
                        if typ not in _ScalarTypes:
                            raise ValueError(f"unknown scalar type {typ}")
                        fs = {"kind": "scalar", "type": typ, "name": name, "oneof": group_name}
                    fields[int(fid)] = fs
                    names[name] = int(fid)
                elif len(alt) == 4:
                    kind, name, fid, spec = alt
                    if kind == "message":
                        fs = {"kind": "message", "schema": _normalize_schema(spec), "name": name, "oneof": group_name}
                    elif kind == "scalar":
                        if spec not in _ScalarTypes:
                            raise ValueError(f"unknown scalar type {spec}")
                        fs = {"kind": "scalar", "type": spec, "name": name, "oneof": group_name}
                    else:
                        raise ValueError("oneof alternatives must be scalar or message singletons")
                    fields[int(fid)] = fs
                    names[name] = int(fid)
                else:
                    raise ValueError("unsupported tuple length in oneof alternative")
            continue

        if len(item) == 3:
            typ_or_schema, name, fid = item
            # Message singletons: first element is a subschema list
            if isinstance(typ_or_schema, (list, tuple)):
                fields[int(fid)] = {"kind": "message", "schema": _normalize_schema(typ_or_schema), "name": name}
            else:
                typ = typ_or_schema
                if typ not in _ScalarTypes:
                    raise ValueError(f"unknown scalar type {typ}")
                fields[int(fid)] = {"kind": "scalar", "type": typ, "name": name}
            names[name] = int(fid)
        elif len(item) == 4:
            kind, name, fid, spec = item
            if kind == "packed":
                if spec not in {"varint", "uint64", "uint32", "int64", "int32", "sint", "sint64", "sint32", "fixed32", "fixed64", "sfixed32", "sfixed64", "float", "double", "bool"}:
                    raise ValueError(f"unsupported packed elem {spec}")
                fields[int(fid)] = {"kind": "packed", "type": spec, "name": name}
            elif kind == "message":
                fields[int(fid)] = {"kind": "message", "schema": _normalize_schema(spec), "name": name}
            elif kind == "repeated":
                # spec can be scalar type or subschema list for repeated message
                if isinstance(spec, (list, tuple)):
                    fields[int(fid)] = {"kind": "repeated", "schema": _normalize_schema(spec), "name": name}
                else:
                    if spec not in _ScalarTypes:
                        raise ValueError(f"unknown scalar type {spec}")
                    fields[int(fid)] = {"kind": "repeated", "type": spec, "name": name}
            elif kind == "scalar":
                # Optional synonym: ("scalar", name, id, type)
                if spec not in _ScalarTypes:
                    raise ValueError(f"unknown scalar type {spec}")
                fields[int(fid)] = {"kind": "scalar", "type": spec, "name": name}
            else:
                raise ValueError(f"unknown field kind {kind}")
            names[name] = int(fid)
        else:
            raise ValueError("unsupported tuple length in schema")

    return {"fields": fields, "names": names}


def _encode_packed(vals, elem_type):
    out = bytearray()
    for v in vals:
        if elem_type in {"varint", "uint64"}:
            out += _write_varint(int(v))
        elif elem_type == "uint32":
            out += _write_varint(int(v) & 0xFFFFFFFF)
        elif elem_type == "int64":
            out += _write_varint(int(v) & 0xFFFFFFFFFFFFFFFF)
        elif elem_type == "int32":
            out += _write_varint(_i32_to_uvarint(v))
        elif elem_type == "sint":
            out += _write_varint(zigzag_encode(int(v)))
        elif elem_type == "sint64":
            out += _write_varint(zigzag_encode(int(v)))
        elif elem_type == "sint32":
            out += _write_varint(_zz32(v))
        elif elem_type == "fixed32":
            out += _write_fixed32(int(v))
        elif elem_type == "sfixed32":
            out += _write_sfixed32(v)
        elif elem_type == "fixed64":
            out += _write_fixed64(int(v))
        elif elem_type == "sfixed64":
            out += _write_sfixed64(v)
        elif elem_type == "float":
            out += struct.pack("<f", float(v))
        elif elem_type == "double":
            out += struct.pack("<d", float(v))
        elif elem_type == "bool":
            out += _write_varint(1 if bool(v) else 0)
        else:
            raise ValueError("unsupported packed elem {}".format(elem_type))

    return bytes(out)


def _write_key(field, wt):
    return _write_varint((field << 3) | wt)


# Encoder (proto3 binary)
def encode(values, schema=None):
    ns = _normalize_schema(schema)
    out = bytearray()

    def _ld_write(field, payload):
        out.extend(_write_key(field, 2))
        out.extend(_write_varint(len(payload)))
        out.extend(payload)

    def _var_write(field, val):
        out.extend(_write_key(field, 0))
        out.extend(_write_varint(val))

    # Pre-scan to enforce oneof constraint: at most one set per group
    groups = {}
    for key in values.keys():
        if isinstance(key, int):
            field = key
        else:
            field = ns["names"].get(key)
        if field is None:
            continue
        spec = ns["fields"].get(field)
        if not spec:
            continue
        grp = spec.get("oneof") if isinstance(spec, dict) else None
        if grp:
            groups.setdefault(grp, []).append(key)

    for grp, ks in groups.items():
        if len(ks) > 1:
            raise ValueError(f"oneof group '{grp}' has multiple fields set: {ks}")

    # Emit fields in caller-provided order
    for key, val in values.items():
        # Allow using field names; map to number if needed
        if isinstance(key, int):
            field = key
        else:
            field = ns["names"].get(key)
            if field is None:
                raise KeyError(f"unknown field name '{key}' in schema")
        spec = ns["fields"].get(field)
        if not spec:
            raise KeyError(f"field {field} not defined in schema")

        if spec["kind"] == "packed":
            seq = val if isinstance(val, list) else [val]
            packed = _encode_packed(seq, spec["type"])
            _ld_write(field, packed)
            continue

        # For repeated, the value must be a list; otherwise wrap singletons
        is_repeated = (spec["kind"] == "repeated")
        vals = val if isinstance(val, list) else ([val] if is_repeated else [val])
        for v in vals:
            t = spec.get("type") if spec else None
            if spec["kind"] == "scalar" and t in {"varint", "uint64"}:
                _var_write(field, int(v))
            elif spec["kind"] == "scalar" and t == "uint32":
                _var_write(field, int(v) & 0xFFFFFFFF)
            elif spec["kind"] == "scalar" and t == "int64":
                _var_write(field, int(v) & 0xFFFFFFFFFFFFFFFF)
            elif spec["kind"] == "scalar" and t == "int32":
                u = _i32_to_uvarint(v)
                _var_write(field, u)
            elif spec["kind"] == "scalar" and t in {"sint", "sint64"}:
                _var_write(field, zigzag_encode(int(v)))
            elif spec["kind"] == "scalar" and t == "sint32":
                zz = _zz32(v)
                _var_write(field, zz)
            elif spec["kind"] == "scalar" and t == "fixed32":
                out += _write_key(field, 5)
                out += _write_fixed32(int(v))
            elif spec["kind"] == "scalar" and t == "sfixed32":
                out += _write_key(field, 5)
                out += _write_sfixed32(v)
            elif spec["kind"] == "scalar" and t == "fixed64":
                out += _write_key(field, 1)
                out += _write_fixed64(int(v))
            elif spec["kind"] == "scalar" and t == "sfixed64":
                out += _write_key(field, 1)
                out += _write_sfixed64(v)
            elif spec["kind"] == "scalar" and t == "float":
                out += _write_key(field, 5)
                out += struct.pack("<f", float(v))
            elif spec["kind"] == "scalar" and t == "double":
                out += _write_key(field, 1)
                out += struct.pack("<d", float(v))
            elif spec["kind"] == "scalar" and t == "bool":
                _var_write(field, 1 if bool(v) else 0)
            elif spec["kind"] == "scalar" and t == "string":
                bs = v.encode("utf-8")
                _ld_write(field, bs)
            elif spec["kind"] == "scalar" and t == "bytes":
                bs = bytes(v)
                _ld_write(field, bs)
            elif spec["kind"] == "message":
                inner = encode(v, spec["schema"])
                _ld_write(field, inner)
            elif spec["kind"] == "repeated" and "type" in spec:
                # Proto3 default: pack eligible numeric types into one segment
                if spec["type"] in {"varint", "uint64", "uint32", "int64", "int32", "sint", "sint64", "sint32", "fixed32", "fixed64", "sfixed32", "sfixed64", "float", "double", "bool"}:
                    packed = _encode_packed(vals, spec["type"])  # use prepared list
                    _ld_write(field, packed)
                    break  # emitted entire list as one segment
                else:
                    # Non-packable types (string/bytes) emit one tag per element
                    if spec["type"] == "string":
                        bs = v.encode("utf-8")
                        _ld_write(field, bs)
                    elif spec["type"] == "bytes":
                        bs = bytes(v)
                        _ld_write(field, bs)
                    else:
                        raise ValueError("unsupported repeated scalar type {}".format(spec["type"]))
            elif spec["kind"] == "repeated" and "schema" in spec:
                # repeated message: each v is a dict for one message instance
                inner = encode(v, spec["schema"])
                _ld_write(field, inner)
            else:
                raise ValueError("unsupported type for field {}".format(field))

    return bytes(out)


def decode(buf, schema=None, _depth=0, _max_depth=_MAX_NESTING_DEPTH):
    if _depth > _max_depth:
        raise ValueError("message nesting too deep")
    ns = _normalize_schema(schema)
    if isinstance(buf, bytearray):
        b = buf
    else:
        b = memoryview(buf).toreadonly()
    out = {}
    oneof_seen = {}
    i = 0
    n = len(b)
    while i < n:
        key, i = _read_varint(b, i)
        field = key >> 3
        wt = key & 7

        spec = ns["fields"].get(field)

        if wt == 0:
            v, i = _read_varint(b, i)
            if spec:
                t = spec.get("type")
                if t in {"sint", "sint64"}:
                    v = zigzag_decode(v)
                elif t == "sint32":
                    v = _i32_from_uvarint(zigzag_decode(v))
                elif t == "int64":
                    v = _i64_from_uvarint(v)
                elif t == "int32":
                    v = _i32_from_uvarint(v)
                elif t == "uint32":
                    v &= 0xFFFFFFFF
                elif t in {"uint64", "varint"}:
                    pass
                elif t == "bool":
                    v = bool(v)
        elif wt == 1:
            v, i = _read_fixed64(b, i)
            if spec:
                tt = spec.get("type")
                if tt == "double":
                    v = struct.unpack("<d", struct.pack("<Q", v))[0]
                elif tt == "sfixed64":
                    v = v - 0x10000000000000000 if v >= 0x8000000000000000 else v
        elif wt == 2:
            length, i = _read_varint(b, i)
            if i + length > n:
                raise ValueError("truncated length-delimited field")
            chunk = bytes(b[i:i+length])
            i += length
            t = spec.get("type") if spec else None
            if spec and spec.get("kind") == "message":
                v = decode(chunk, spec["schema"], _depth=_depth+1, _max_depth=_max_depth)
            elif spec and spec.get("kind") == "repeated" and "type" in spec and t in {"varint", "uint64", "uint32", "int64", "int32", "sint", "sint64", "sint32", "fixed32", "fixed64", "sfixed32", "sfixed64", "float", "double", "bool"}:
                # Proto3 default: repeated numeric are packed; flatten into list
                v = _decode_packed(chunk, t)
            elif spec and spec.get("kind") == "repeated" and "schema" in spec:
                v = decode(chunk, spec["schema"], _depth=_depth+1, _max_depth=_max_depth)
            elif spec and spec.get("kind") == "packed":
                v = _decode_packed(chunk, t)
            elif t == "string":
                v = chunk.decode("utf-8")
            elif t == "bytes" or spec is None:
                v = chunk
            else:
                v = chunk
        elif wt == 5:
            v, i = _read_fixed32(b, i)
            if spec:
                tt = spec.get("type")
                if tt == "float":
                    v = struct.unpack("<f", struct.pack("<I", v))[0]
                elif tt == "sfixed32":
                    v = v - 0x100000000 if v >= 0x80000000 else v
        else:
            raise ValueError("unsupported wire type {}".format(wt))

        out_key = (spec.get("name") if spec else field)
        if spec:
            is_repeated = spec.get("kind") in {"repeated", "packed"}
            if is_repeated:
                # Repeated scalar (numeric packed yields list 'v'), or repeated message (dict 'v')
                seq = v if isinstance(v, list) else [v]
                out.setdefault(out_key, []).extend(seq)
            else:
                # Singleton (scalar or message) — store as value, not list
                grp = spec.get("oneof")
                if grp:
                    prev = oneof_seen.get(grp)
                    if prev and prev in out:
                        try:
                            del out[prev]
                        except Exception:
                            out.pop(prev, None)
                    oneof_seen[grp] = out_key
                out[out_key] = v
        else:
            # Unknown field: if first occurrence, store scalar; if multiple, upgrade to list
            if out_key in out:
                prev = out[out_key]
                if isinstance(prev, list):
                    prev.append(v)
                else:
                    out[out_key] = [prev, v]
            else:
                out[out_key] = v

    return out


# Packed repeated element decode
def _decode_packed(chunk, elem_type):
    b = memoryview(chunk).toreadonly()
    i = 0
    out = []
    while i < len(b):
        if elem_type in {"varint", "uint64"}:
            v, i = _read_varint(b, i)
            out.append(v)
        elif elem_type == "uint32":
            v, i = _read_varint(b, i)
            out.append(v & 0xFFFFFFFF)
        elif elem_type == "int64":
            v, i = _read_varint(b, i)
            out.append(_i64_from_uvarint(v))
        elif elem_type == "int32":
            v, i = _read_varint(b, i)
            out.append(_i32_from_uvarint(v))
        elif elem_type == "sint":
            v, i = _read_varint(b, i)
            out.append(zigzag_decode(v))
        elif elem_type == "sint64":
            v, i = _read_varint(b, i)
            out.append(zigzag_decode(v))
        elif elem_type == "sint32":
            v, i = _read_varint(b, i)
            out.append(_i32_from_uvarint(zigzag_decode(v)))
        elif elem_type == "fixed32":
            v, i = _read_fixed32(b, i)
            out.append(v)
        elif elem_type == "sfixed32":
            v, i = _read_fixed32(b, i)
            v = v - 0x100000000 if v >= 0x80000000 else v
            out.append(v)
        elif elem_type == "fixed64":
            v, i = _read_fixed64(b, i)
            out.append(v)
        elif elem_type == "sfixed64":
            v, i = _read_fixed64(b, i)
            v = v - 0x10000000000000000 if v >= 0x8000000000000000 else v
            out.append(v)
        elif elem_type == "float":
            v, i = _read_fixed32(b, i)
            out.append(struct.unpack("<f", struct.pack("<I", v))[0])
        elif elem_type == "double":
            v, i = _read_fixed64(b, i)
            out.append(struct.unpack("<d", struct.pack("<Q", v))[0])
        elif elem_type == "bool":
            v, i = _read_varint(b, i)
            out.append(bool(v))
        else:
            raise ValueError("unsupported packed elem {}".format(elem_type))
    return out
