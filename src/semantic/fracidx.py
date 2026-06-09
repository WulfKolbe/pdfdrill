"""
fracidx — order keys you can insert *between* without renumbering anything.

A faithful pure-stdlib port of rocicorp/fractional-indexing (CC0). Keys are
plain strings; lexicographic string comparison == logical order, so they work
directly in `sorted()`, SQL `ORDER BY`, and any TiddlyWiki filter. The whole
point: to put an item between two neighbours you generate ONE new key from their
two keys — no other row changes. That is the "insert without large re-org"
requirement from the original brief.

Public API:
    key_between(a, b)            -> a key strictly between a and b (None = open end)
    key_after(a)  / key_before(b)
    n_keys_between(a, b, n)      -> n evenly spaced keys (shorter than repeated calls)
"""
from __future__ import annotations

from typing import List, Optional

DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_SMALLEST_INT = "A" + DIGITS[0] * 26


def _int_len(head: str) -> int:
    if "a" <= head <= "z":
        return ord(head) - ord("a") + 2
    if "A" <= head <= "Z":
        return ord("Z") - ord(head) + 2
    raise ValueError(f"invalid order-key head: {head!r}")


def _int_part(key: str) -> str:
    n = _int_len(key[0])
    if n > len(key):
        raise ValueError(f"invalid order key: {key!r}")
    return key[:n]


def _validate(key: str, digits: str) -> None:
    if key == "":
        raise ValueError("empty order key")
    ip = _int_part(key)
    fp = key[len(ip):]
    if fp.endswith(digits[0]):
        raise ValueError(f"order key has trailing zero: {key!r}")
    for c in ip[1:] + fp:
        if c not in digits:
            raise ValueError(f"order key has invalid digit: {key!r}")


def _incr_int(x: str, digits: str) -> Optional[str]:
    head, digs = x[0], list(x[1:])
    carry = True
    for i in range(len(digs) - 1, -1, -1):
        if not carry:
            break
        d = digits.index(digs[i]) + 1
        if d == len(digits):
            digs[i] = digits[0]
        else:
            digs[i] = digits[d]
            carry = False
    if carry:
        if head == "Z":
            return "a" + digits[0]
        if head == "z":
            return None
        h = chr(ord(head) + 1)
        if h > "a":
            digs.append(digits[0])
        else:
            digs.pop()
        return h + "".join(digs)
    return head + "".join(digs)


def _decr_int(x: str, digits: str) -> Optional[str]:
    head, digs = x[0], list(x[1:])
    borrow = True
    for i in range(len(digs) - 1, -1, -1):
        if not borrow:
            break
        d = digits.index(digs[i]) - 1
        if d == -1:
            digs[i] = digits[-1]
        else:
            digs[i] = digits[d]
            borrow = False
    if borrow:
        if head == "a":
            return "Z" + digits[-1]
        if head == "A":
            return None
        h = chr(ord(head) - 1)
        if h < "Z":
            digs.append(digits[-1])
        else:
            digs.pop()
        return h + "".join(digs)
    return head + "".join(digs)


def _midpoint(a: str, b: Optional[str], digits: str) -> str:
    zero = digits[0]
    if b is not None and a >= b:
        raise ValueError(f"{a!r} >= {b!r}")
    if a.endswith(zero) or (b is not None and b.endswith(zero)):
        raise ValueError("trailing zero")
    if b is not None:
        n = 0
        while (a[n] if n < len(a) else zero) == (b[n] if n < len(b) else None):
            n += 1
        if n > 0:
            return b[:n] + _midpoint(a[n:], b[n:], digits)
    digit_a = digits.index(a[0]) if a else 0
    digit_b = digits.index(b[0]) if (b is not None and b) else len(digits)
    if digit_b - digit_a > 1:
        return digits[round(0.5 * (digit_a + digit_b))]
    if b is not None and len(b) > 1:
        return b[:1]
    return digits[digit_a] + _midpoint(a[1:] if a else "", None, digits)


def key_between(a: Optional[str], b: Optional[str], digits: str = DIGITS) -> str:
    if a is not None:
        _validate(a, digits)
    if b is not None:
        _validate(b, digits)
    if a is not None and b is not None and a >= b:
        raise ValueError(f"{a!r} >= {b!r}")
    if a is None:
        if b is None:
            return "a" + digits[0]
        ib, fb = _int_part(b), b[len(_int_part(b)):]
        if ib == _SMALLEST_INT:
            return ib + _midpoint("", fb, digits)
        if ib < b:
            return ib
        res = _decr_int(ib, digits)
        if res is None:
            raise ValueError("cannot decrement any more")
        return res
    if b is None:
        ia, fa = _int_part(a), a[len(_int_part(a)):]
        i = _incr_int(ia, digits)
        return ia + _midpoint(fa, None, digits) if i is None else i
    ia, fa = _int_part(a), a[len(_int_part(a)):]
    ib, fb = _int_part(b), b[len(_int_part(b)):]
    if ia == ib:
        return ia + _midpoint(fa, fb, digits)
    i = _incr_int(ia, digits)
    if i is None:
        raise ValueError("cannot increment any more")
    if i < b:
        return i
    return ia + _midpoint(fa, None, digits)


def key_after(a: Optional[str]) -> str:
    return key_between(a, None)


def key_before(b: Optional[str]) -> str:
    return key_between(None, b)


def n_keys_between(a: Optional[str], b: Optional[str], n: int,
                   digits: str = DIGITS) -> List[str]:
    if n <= 0:
        return []
    if n == 1:
        return [key_between(a, b, digits)]
    if b is None:
        out = []
        for _ in range(n):
            a = key_between(a, None, digits)
            out.append(a)
        return out
    if a is None:
        out = []
        for _ in range(n):
            b = key_between(None, b, digits)
            out.append(b)
        return list(reversed(out))
    mid = n // 2
    c = key_between(a, b, digits)
    return (n_keys_between(a, c, mid, digits) + [c]
            + n_keys_between(c, b, n - mid - 1, digits))
