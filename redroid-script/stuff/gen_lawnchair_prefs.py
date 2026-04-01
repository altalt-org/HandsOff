#!/usr/bin/env python3
"""
Generate a Lawnchair DataStore preferences protobuf file.

The generated file disables the dock search bar and the Smartspace
widget, giving a clean homescreen with all apps accessible via swipe-up.

Output: preferences.preferences_pb (binary protobuf)

DataStore schema (from androidx.datastore.preferences):
  message PreferenceMap { map<string, Value> preferences = 1; }
  message Value { oneof { bool boolean=1; float float_=2; int32 integer=3;
                          int64 long=4; string string=5; StringSet string_set=6;
                          double double_=7; } }
  message StringSet { repeated string strings = 1; }

We build the protobuf manually (no .proto compilation needed) since
the wire format is simple.
"""

import struct
import sys


def encode_varint(value):
    """Encode an unsigned integer as a protobuf varint."""
    result = b""
    while value > 0x7F:
        result += bytes([(value & 0x7F) | 0x80])
        value >>= 7
    result += bytes([value])
    return result


def encode_length_delimited(field_number, data):
    """Encode a length-delimited field (wire type 2)."""
    tag = encode_varint((field_number << 3) | 2)
    return tag + encode_varint(len(data)) + data


def encode_varint_field(field_number, value):
    """Encode a varint field (wire type 0)."""
    tag = encode_varint((field_number << 3) | 0)
    return tag + encode_varint(value)


def encode_string_value(s):
    """Encode a Value message with string field (field 5)."""
    return encode_length_delimited(5, s.encode("utf-8"))


def encode_bool_value(b):
    """Encode a Value message with boolean field (field 1)."""
    return encode_varint_field(1, 1 if b else 0)


def encode_map_entry(key, value_bytes):
    """Encode a map<string, Value> entry as a submessage.

    In protobuf, map<K,V> is serialized as repeated message { K key=1; V value=2; }
    The outer field number is 1 (PreferenceMap.preferences).
    """
    key_field = encode_length_delimited(1, key.encode("utf-8"))
    value_field = encode_length_delimited(2, value_bytes)
    entry = key_field + value_field
    return encode_length_delimited(1, entry)


def generate_preferences():
    """Build the full PreferenceMap protobuf bytes."""
    prefs = {
        "hotseat_mode": encode_string_value("disabled"),
        "enable_smartspace": encode_bool_value(False),
        "hide_app_drawer_search_bar": encode_bool_value(True),
    }

    result = b""
    for key, value_bytes in prefs.items():
        result += encode_map_entry(key, value_bytes)
    return result


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "preferences.preferences_pb"
    data = generate_preferences()
    with open(output, "wb") as f:
        f.write(data)
    print(f"Written {len(data)} bytes to {output}")
