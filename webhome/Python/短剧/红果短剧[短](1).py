
import sys
import os
import re
import json
import time
import struct
import base64
import random
import hashlib
import binascii
import socket
import threading
import zlib
from pathlib import Path
from urllib.parse import (quote, urlencode, parse_qs, urlparse,
                          urlsplit, parse_qsl, unquote)
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any, List, Tuple

sys.path.append('..')

try:
    import requests
except ImportError:
    requests = None

try:
    from Crypto.Cipher import AES
    from Crypto.Util import Counter
except ImportError:
    AES = None
    Counter = None

try:
    from base.spider import Spider
except ImportError:
    class Spider:
        pass

try:
    import warnings
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    warnings.filterwarnings('ignore', message='Unverified HTTPS request')
except Exception:
    pass


CONFIG_DEVICE_ID = '829902912863503360'
CONFIG_INSTALL_ID = '250404579274111008'
CONFIG_PLATFORM = 'android'
CONFIG_CACHE_SECONDS = 3600

_CURRENT_DOMAIN = 'http://127.0.0.1:9877'
_EMBEDDED_SERVER = None
_EMBEDDED_PORT = 0

def _pkcs7_pad(data, block_size=16):
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)


def _sm3_rotl(x, n, bits=32):
    n = n % bits
    return ((x << n) | (x >> (bits - n))) & ((1 << bits) - 1)

def _sm3_p0(x):
    return x ^ _sm3_rotl(x, 9) ^ _sm3_rotl(x, 17)

def _sm3_p1(x):
    return x ^ _sm3_rotl(x, 15) ^ _sm3_rotl(x, 23)

def _sm3_ff(x, y, z, j):
    if j < 16:
        return x ^ y ^ z
    return (x & y) | (x & z) | (y & z)

def _sm3_gg(x, y, z, j):
    if j < 16:
        return x ^ y ^ z
    return (x & y) | ((~x) & z)

def _sm3_hash(msg_list):
    IV = [0x7380166f, 0x4914b2b9, 0x172442d7, 0xda8a0600,
          0xa96f30bc, 0x163138aa, 0xe38dee4d, 0xb0fb0e4e]
    msg = bytes(msg_list)
    length = len(msg)
    msg += b'\x80'
    while len(msg) % 64 != 56:
        msg += b'\x00'
    msg += (length * 8).to_bytes(8, 'big')
    V = list(IV)
    for i in range(0, len(msg), 64):
        block = msg[i:i+64]
        W = [int.from_bytes(block[j*4:j*4+4], 'big') for j in range(16)]
        for j in range(16, 68):
            w = _sm3_p1(W[j-16] ^ W[j-9] ^ _sm3_rotl(W[j-3], 15)) ^ _sm3_rotl(W[j-13], 7) ^ W[j-6]
            W.append(w)
        W_prime = [W[j] ^ W[j+4] for j in range(64)]
        A, B, C, D, E, F, G, H = V
        for j in range(64):
            t_j = 0x79cc4519 if j < 16 else 0x7a879d8a
            SS1 = _sm3_rotl((_sm3_rotl(A, 12) + E + _sm3_rotl(t_j, j % 32)) & 0xFFFFFFFF, 7)
            SS2 = SS1 ^ _sm3_rotl(A, 12)
            TT1 = (_sm3_ff(A, B, C, j) + D + SS2 + W_prime[j]) & 0xFFFFFFFF
            TT2 = (_sm3_gg(E, F, G, j) + H + SS1 + W[j]) & 0xFFFFFFFF
            D = C
            C = _sm3_rotl(B, 9)
            B = A
            A = TT1
            H = G
            G = _sm3_rotl(F, 19)
            F = E
            E = _sm3_p0(TT2)
        V = [(V[k] ^ [A, B, C, D, E, F, G, H][k]) & 0xFFFFFFFF for k in range(8)]
    return ''.join('%08x' % x for x in V)


class SM3:
    def __init__(self, data=b''):
        if isinstance(data, str):
            data = data.encode("utf-8")
        self._data = bytearray(data)
    def update(self, data):
        self._data.extend(data)
    def digest(self):
        h = _sm3_hash([b for b in self._data])
        return bytes.fromhex(h)


def _enc_varint(value):
    buf = bytearray()
    while value > 0x7F:
        buf.append((value & 0x7F) | 0x80)
        value >>= 7
    buf.append(value & 0x7F)
    return bytes(buf)

def _zigzag32(n):
    return ((n << 1) ^ (n >> 31)) & 0xFFFFFFFF

def _zigzag64(n):
    return ((n << 1) ^ (n >> 63)) & 0xFFFFFFFFFFFFFFFF

def _enc_sint32(field, value):
    if value == 0:
        return b''
    return _enc_varint(field << 3) + _enc_varint(_zigzag32(value))

def _enc_sint64(field, value):
    if value == 0:
        return b''
    return _enc_varint(field << 3) + _enc_varint(_zigzag64(value))

def _enc_string(field, value):
    if not value:
        return b''
    data = value.encode('utf-8')
    return _enc_varint((field << 3) | 2) + _enc_varint(len(data)) + data

def _enc_bytes(field, value):
    if not value:
        return b''
    data = bytes(value)
    return _enc_varint((field << 3) | 2) + _enc_varint(len(data)) + data

def _enc_float(field, value):
    if value == 0.0:
        return b''
    return _enc_varint((field << 3) | 5) + struct.pack('<f', value)

def _enc_msg(field, data):
    if not data:
        return b''
    return _enc_varint((field << 3) | 2) + _enc_varint(len(data)) + data

class MedushaAlgorithmCount:
    def __init__(self, sign_count=0, report_count=0, setting_count=0, unknown4=0, unknown5=0):
        self.sign_count = sign_count
        self.report_count = report_count
        self.setting_count = setting_count
        self.unknown4 = unknown4
        self.unknown5 = unknown5
    def __bytes__(self):
        return b''.join([
            _enc_sint32(1, self.sign_count),
            _enc_sint32(2, self.report_count),
            _enc_sint32(3, self.setting_count),
            _enc_sint32(4, self.unknown4),
            _enc_sint32(5, self.unknown5),
        ])

class Report:
    def __init__(self, time=0, state=0, code=0, times=0, unknown6=0):
        self.time = time
        self.state = state
        self.code = code
        self.times = times
        self.unknown6 = unknown6
    def __bytes__(self):
        return b''.join([
            _enc_sint64(1, self.time),
            _enc_sint32(2, self.state),
            _enc_sint32(4, self.code),
            _enc_sint32(5, self.times),
            _enc_sint32(6, self.unknown6),
        ])

class Device:
    def __init__(self, **kw):
        self.__dict__.update({
            'd1': 0, 'collect_stat': 0, 'aid': '', 'device_id': '',
            'sec_device_token': '', 'app_version': '', 'battery': 0,
            'battery2': 0, 'battery_health': 0, 'battery_changed': 0,
            'network': '', 'tz': '', 'lan': '', 'cpu': 0, 'resolution': '',
            'sdcard': 0.0, 'sdcard_used': 0.0, 'memory': 0.0, 'memory2': 0.0,
            'data': 0.0, 'data_used': 0.0, 'os_version': '', 'brightness': 0,
            'volume': 0, 'ts': 0, 'ts2': 0, 'ts3': 0, 'ts4': 0, 'usb': 0,
            'hw_version': '', 'brand': '', 'board': '', 'product_name': '',
            'product_device': '', 'product_manufacturer': '', 'hardware': '',
            'unknown38': 0, 'unknown40': 0,
        })
        self.__dict__.update(kw)
    def __bytes__(self):
        return b''.join([
            _enc_sint32(1, self.d1), _enc_sint32(2, self.collect_stat),
            _enc_string(3, self.aid), _enc_string(4, self.device_id),
            _enc_string(5, self.sec_device_token), _enc_string(6, self.app_version),
            _enc_sint32(7, self.battery), _enc_sint32(8, self.battery2),
            _enc_sint32(9, self.battery_health), _enc_sint32(10, self.battery_changed),
            _enc_string(11, self.network), _enc_string(12, self.tz),
            _enc_string(13, self.lan), _enc_sint32(14, self.cpu),
            _enc_string(15, self.resolution),
            _enc_float(16, self.sdcard), _enc_float(17, self.sdcard_used),
            _enc_float(18, self.memory), _enc_float(19, self.memory2),
            _enc_float(20, self.data), _enc_float(21, self.data_used),
            _enc_string(22, self.os_version),
            _enc_sint32(23, self.brightness), _enc_sint32(24, self.volume),
            _enc_sint64(25, self.ts), _enc_sint64(26, self.ts2),
            _enc_sint64(27, self.ts3), _enc_sint64(28, self.ts4),
            _enc_sint32(29, self.usb), _enc_string(30, self.hw_version),
            _enc_string(31, self.brand), _enc_string(32, self.board),
            _enc_string(33, self.product_name), _enc_string(34, self.product_device),
            _enc_string(35, self.product_manufacturer), _enc_string(36, self.hardware),
            _enc_sint32(38, self.unknown38), _enc_sint32(40, self.unknown40),
        ])

class Env:
    def __init__(self, **kw):
        self.launch_time = kw.get('launch_time', 0)
        self.unknown2 = kw.get('unknown2', 0)
        self.unknown3 = kw.get('unknown3', 0)
        self.unknown5 = kw.get('unknown5', 0)
        self.version = kw.get('version', '')
        self.pid = kw.get('pid', 0)
        self.device = kw.get('device', None)
        self.report = kw.get('report', None)
        self.app_version = kw.get('app_version', '')
        self.unknown15 = kw.get('unknown15', 0)
        self.unknown16 = kw.get('unknown16', 0)
        self.unknown18 = kw.get('unknown18', 0)
        self.unknown19 = kw.get('unknown19', 0)
        self.unknown20 = kw.get('unknown20', 0)
        self.unknown21 = kw.get('unknown21', 0)
    def __bytes__(self):
        parts = [
            _enc_sint32(1, self.launch_time),
            _enc_sint32(2, self.unknown2),
            _enc_sint32(3, self.unknown3),
            _enc_sint32(5, self.unknown5),
            _enc_string(6, self.version),
            _enc_sint32(7, self.pid),
        ]
        if self.device is not None:
            parts.append(_enc_msg(12, bytes(self.device)))
        if self.report is not None:
            parts.append(_enc_msg(13, bytes(self.report)))
        parts.append(_enc_string(14, self.app_version))
        parts.extend([
            _enc_sint32(15, self.unknown15), _enc_sint32(16, self.unknown16),
            _enc_sint32(18, self.unknown18), _enc_sint32(19, self.unknown19),
            _enc_sint32(20, self.unknown20), _enc_sint32(21, self.unknown21),
        ])
        return b''.join(parts)

class Medusa:
    def __init__(self, **kw):
        self.magic = kw.get('magic', b'')
        self.version = kw.get('version', 0)
        self.rand = kw.get('rand', 0)
        self.ms_app_id = kw.get('ms_app_id', '')
        self.device_id = kw.get('device_id', '')
        self.license_id = kw.get('license_id', '')
        self.app_version = kw.get('app_version', '')
        self.sdk_version_str = kw.get('sdk_version_str', '')
        self.sdk_version = kw.get('sdk_version', 0)
        self.xg_seed_bytes = kw.get('xg_seed_bytes', b'')
        self.time = kw.get('time', 0)
        self.query_body_ts_hash = kw.get('query_body_ts_hash', b'')
        self.query_sm3 = kw.get('query_sm3', b'')
        self.request = kw.get('request', None)
        self.sec_device_token = kw.get('sec_device_token', '')
        self.time2 = kw.get('time2', 0)
        self.lanusk_hash = kw.get('lanusk_hash', b'')
        self.query_body_hash_sm3 = kw.get('query_body_hash_sm3', b'')
        self.psk_version = kw.get('psk_version', '')
        self.call_type = kw.get('call_type', 0)
        self.env = kw.get('env', None)
        self.unknown24 = kw.get('unknown24', '')
        self.original = kw.get('original', '')
    def __bytes__(self):
        parts = [
            _enc_bytes(1, self.magic),
            _enc_sint32(2, self.version),
            _enc_sint32(3, self.rand),
            _enc_string(4, self.ms_app_id),
            _enc_string(5, self.device_id),
            _enc_string(6, self.license_id),
            _enc_string(7, self.app_version),
            _enc_string(8, self.sdk_version_str),
            _enc_sint32(9, self.sdk_version),
            _enc_bytes(10, self.xg_seed_bytes),
            _enc_sint32(12, self.time),
            _enc_bytes(13, self.query_body_ts_hash),
            _enc_bytes(14, self.query_sm3),
        ]
        if self.request is not None:
            parts.append(_enc_msg(15, bytes(self.request)))
        parts.extend([
            _enc_string(16, self.sec_device_token),
            _enc_sint32(17, self.time2),
            _enc_bytes(18, self.lanusk_hash),
            _enc_bytes(19, self.query_body_hash_sm3),
            _enc_string(20, self.psk_version),
            _enc_sint32(21, self.call_type),
        ])
        if self.env is not None:
            parts.append(_enc_msg(23, bytes(self.env)))
        parts.append(_enc_string(24, self.unknown24))
        parts.append(_enc_string(26, self.original))
        return b''.join(parts)

class EecryptParams:
    def __init__(self):
        self.khronos = ''
        self.argus = ''
        self.medusa = ''
        self.gorgon = ''
        self.ladon = ''
        self.helios = ''

_BRANCH_ONE_B64 = (
        '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'
        'DfozaEg6sMIrVto1fQki/5PgVwSRS45gD4EVeorz0O7SCvz60tbyCIx76i/lWDeBcWIwgQ2JkBNMZgfs8ojTetL+CmVwMuEwX4cpCtTSjvvy6HqSxBuYWl/eCijtapgMuD4JCJi8bjjpKg1aH8BblpwK2txansILGliXCWjoui6dDDgPmloe2MKTXD25nuwKaAgo4xhB'
        'dfFVSmZP+W2tlvNbBQlH3AbF8XV49kUdUeJwYUtIVnIZYUP15YljZy8R9pjNZXNRQk0e4fDOKfFgn2WPE7RAXxGN1c3k1RrwYlfbRXp0/4XrmthDDoxdQde1EOXMyNQVRedcibXelIWaQv+Jn+UU1V3JRLeIn576gYqX3URToHOMqwyUA/G87Vn1w3uEg1nF63m89fSr'
        'dKQLVIgDk5ALjKMDc6xUgOftVVhYDnIEiwt0lKNTqHBQWO4N4oVf5T59Y9D5Ww0EI6jDcHx3VC2doalkNiIs1Xk7/eNmCF1e/WM4DX3T4YJhLHQ80ZWZCWX4e1s95daZctQtlGGEOQCI9b9uJNkQOFGJ4zFI8ZNLvkhW5bkC2uyVw0ftS2L02CC5jhXwbwSpisQIOJX4'
        'm2VMQpXzxO/rYcqoTWwjNnP/arsD0vuozBBqo1DARDvY1XRMiKLRBX9aKjP83tyGvar8AGrLv9P7NrqWVFf7wAyiZHDLSl3YhJdsfrn4bUM2RXqgWDa61stRB60qrUOBlsgQrtJbIFKQIvjM8Qf87qnXxIsKzM+Tk9puQBZsSTt1g90v78yGQ7G+VdOuyKiNLBLMFN1c'
        'h4kGYtIqRaiP9xPi5vsedSuhzyvhdqMfzfrmLN52wopd/UKOY6r3RxAq0c0Eil4XEdyEziod+aLnd+MlyMAkjv7Vgl3qbjDdIN7hgJO/nAn1ba/3gQttn628kJGvbAu9gJ/1gP0lwtTKjCbJgNWOwiQk/q/0nb1skwuBPhgr3dPF3bbHPdDd3rcqGZaW6OWpQJFWQJWq'
        'kOZV6pWVVJKq6JXmQbTG3SvdGtM9Gbfe0ik93MdWQuXpkZaolLdNysrVDh9fDrfVHstdy057Wf1OFXgrOXl7FShNOf9ak7Xh1QBfa19dD8vJHk/Wtk9eH9fKtskNOXtP/SpZFXjNa5eBZisTFivPZxOCFpVpZbgms9Gz4L6yZNDjsr0lu7i+4dInZ7CxFymDlhFqZ89r'
        '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'
    )

def _get_branch_one_table():
    raw = zlib.decompress(base64.b64decode(_BRANCH_ONE_B64))
    return [list(raw[i:i+24]) for i in range(0, len(raw), 24)]


import hashlib
import json
import random
import time
from urllib.parse import urlencode, unquote


def extract_url_params(url) -> dict:
    params = {}
    parsed_url_list = url.split("?")[1].split("&") if "?" in url else url.split("&")
    for param in parsed_url_list:
        splited_param = param.split("=")
        params[splited_param[0]] = unquote(splited_param[1] if len(splited_param) == 2 else "")
    return params

def url_encode(data):
    param = urlencode(data)
    param = param.replace("+", "%20")
    param = param.replace("%2A", "*")
    return param


def get_params_encrypturl(url, params:dict=None, devices={}, common=None, rticket_override=None, ts_override=None):
    x_common = {}
    if params:
        x_params = params.copy()
        if common:
            x_params.update(extract_url_params(common))
            x_common = extract_url_params(common)
        if devices:
            for k, v in devices.items():
                if k in x_params:
                    x_params[k] = v
                if k in x_common:
                    x_common[k] = v
                elif "did" in x_params and k == "device_id":
                    x_params["did"] = v
    else:
        x_params: dict = extract_url_params(url) if ("?" in url and len(url.split("?")) == 2 and url.split("?")[1]) else params
        if common:
            x_common = extract_url_params(common)
            x_params.update(x_common)
        if devices:
            for k, v in devices.items():
                if k in x_params:
                    x_params[k] = v
                if k in x_common:
                    x_common[k] = v
                elif "did" in x_params and k == "device_id":
                    x_params["did"] = v

    x_params["ts"] = ts_override if ts_override is not None else int(time.time())
    x_params["_rticket"] = rticket_override if rticket_override is not None else int(time.time() * 1e3)
    if x_common:
        x_common["ts"] = int(time.time())
        x_common["_rticket"] = int(time.time() * 1e3)
    eurl = url.split("?")[0] + "?" + url_encode(x_params) if "?" in url else url + "?" + url_encode(x_params)
    url_params: dict = x_params

    return eurl, url_params, url_encode(x_common)

def xssstub_hash_md5_hex(data, dataType:str=None):
    if not data:
        return str()
    if dataType == "md5":
        return data
    md5 = hashlib.md5()
    if isinstance(data, str):
        md5.update(data.encode('utf-8'))
    elif isinstance(data, bytes):
        md5.update(data)
    else:
        if dataType == "application/json; charset=UTF-8":
            md5.update(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
        else:
            md5.update(urlencode(data).encode('utf-8'))
    xt = md5.hexdigest()
    return xt.upper()

import binascii


xtime = lambda a: (((a << 1) ^ 0x1B) & 0xFF) if (a & 0x80) else (a << 1)


def rol(num, shift):
    shift %= 32
    return ((num << shift) | (num >> (32 - shift))) & 0xFFFFFFFF


def rl8(x: int, k: int) -> int:
    n = 8
    s = k & (n - 1)
    return ((x << s) | (x >> (n - s))) & 0xff


def ror32(value, count):
    count %= 32
    low = value << (32 - count)
    value >>= count
    value |= low
    value &= 0xFFFFFFFF
    return value


def ror(value, count):
    count %= 64
    low = value << (64 - count)
    value >>= count
    value |= low
    value &= 0xFFFFFFFFFFFFFFFF
    return value


def get_key_hash(key, rand):
    to_hash = bytearray(68)
    to_hash[:32] = key
    to_hash[32:36] = rand.to_bytes(4, byteorder='little')
    to_hash[36:] = key

    d1 = (rand >> 16) & 0x000000ff
    d2 = (d1 << 11) | (rand >> 24)
    d2 ^= (d1 >> 5) ^ d1
    d2 = ~d2 & 0xffffffff

    return SM3(to_hash).digest(), d2.to_bytes(4, "little")


def split_blocks(message, block_size=16, require_padding=True):
    assert len(message) % block_size == 0 or not require_padding
    return [message[i:i + 16] for i in range(0, len(message), block_size)]


def add_round_key(s, k):
    for i in range(4):
        for j in range(4):
            s[i][j] ^= k[i][j]


def add_round_key_con(s, k, con):
    for i in range(4):
        for j in range(4):
            s[i][j] ^= k[i][con[j]]


def bytes2matrix(text):
    return [list(text[i:i + 4]) for i in range(0, len(text), 4)]


def xor_bytes(a, b):
    return bytearray(i ^ j for i, j in zip(a, b))


def matrix2bytes(matrix):
    return bytearray(sum(matrix, []))


def mix_single_column(a, i):
    t = a[0][i] ^ a[1][i] ^ a[2][i] ^ a[3][i]
    u = a[0][i]
    a[0][i] ^= t ^ xtime(a[0][i] ^ a[1][i])
    a[1][i] ^= t ^ xtime(a[1][i] ^ a[2][i])
    a[2][i] ^= t ^ xtime(a[2][i] ^ a[3][i])
    a[3][i] ^= t ^ xtime(a[3][i] ^ u)


def mix_columns(s):
    for i in range(4):
        mix_single_column(s, i)


def inv_mix_columns(s):
    for i in range(0, 4):
        inv_mix_single_column(s, i)


def inv_mix_single_column(a, i):
    u = xtime(xtime(a[0][i] ^ a[2][i]))
    v = xtime(xtime(a[1][i] ^ a[3][i]))
    a[0][i] ^= u
    a[1][i] ^= v
    a[2][i] ^= u
    a[3][i] ^= v

    mix_single_column(a, i)


s_box = b''.join([
    b'\xFA\x7D\x08\x6B\x9C\x59\xB3\x4B\x04\x5F\x39\xD0\x38\x4A\x91\x99',
    b'\x00\x67\xA6\x20\x9F\xF5\x4D\x82\x73\x26\xEE\xDF\x18\x66\x83\x33',
    b'\x80\x03\x19\xFB\xD9\xFE\xAE\xAA\xA9\xB0\x52\xC6\x0B\xF3\x79\x25',
    b'\x4E\x78\xB4\x36\xAC\x5D\x1A\x27\x9E\x88\xDB\xBD\x3C\x63\xEC\x49',
    b'\x15\xC1\x30\x1F\xDC\xB8\x56\xD4\x6C\xCD\xCA\x09\x43\xC8\x35\xA3',
    b'\xEF\x1E\xF4\x96\xD2\xFC\x0E\x72\x7B\x94\x84\xD1\xEA\x45\x5A\x62',
    b'\x02\x3F\xD3\x12\x81\x34\x2B\xDD\x7E\xE6\x28\xF2\xA5\x46\x13\x01',
    b'\x3B\x21\xF6\x61\x37\x29\x2A\x0D\xED\x8C\xAF\xBF\x9D\x5C\xBB\x24',
    b'\x76\x0F\x75\xE4\x53\x89\xE1\x98\x8D\xB1\x9A\x65\x70\x4F\x54\x4C',
    b'\x58\xAB\x6E\x6F\x8B\x23\xC4\x07\x11\x0C\xBA\xCF\xA0\xA4\x8E\xD8',
    b'\x05\x3D\x14\xB2\xDA\x74\xC3\xD7\xE7\xBE\xD6\x7F\xDE\x48\x16\x3E',
    b'\x85\x90\xA1\x55\xB7\x77\x42\x22\xC9\x86\x50\x2E\x17\xF9\x64\x31',
    b'\x2C\x9B\xF1\x6D\x1C\x44\x68\xE3\xE9\xA8\x93\x97\xCB\x32\x57\xEB',
    b'\xE5\x71\x6A\xAD\xC0\xCC\xC7\xC5\xFD\x60\x1D\xA2\x2D\x47\xA7\xE2',
    b'\x51\x69\x5E\x7A\xCE\x0A\x41\xB6\x95\x8F\xF7\xB9\x87\xE0\x3A\x06',
    b'\x10\x8A\xB5\xF8\x5B\xD5\xF0\xBC\x92\xFF\x7C\x2F\xC2\xE8\x1B\x40',
    b'\xEC\x1B\xDA\xBD\xBA\x98\x91\x0C\xB2\x2B\x83\x41\x34\x67\xFB\x0A',
    b'\xD8\x76\xB5\x46\x05\x59\x61\x23\x75\x90\x87\x2A\xE3\x50\x15\x4C',
    b'\xAC\xB1\x79\xEB\xAE\xE5\x95\x47\x04\x68\xF0\x86\x3D\x51\x8B\x0F',
    b'\xCA\x8E\xE4\xB9\x4E\xF2\x12\x82\xBC\x0E\xD5\xF7\xEF\x28\x25\xCF',
    b'\x5B\x5D\xE9\x6A\x55\x02\xE1\x33\xBE\x93\xE7\xF5\xAD\x9D\x3E\x39',
    b'\x24\xA8\xE2\xFA\x17\x57\xD0\x7A\x0D\x08\x30\xD6\xB8\xA3\x8D\xFD',
    b'\x07\x9A\xC4\x1E\x6E\x22\x64\x97\xD2\x1D\xB0\xBF\x45\x66\x3F\x6C',
    b'\xDD\xDB\x27\x80\xA7\x11\xDC\xA6\xC5\x52\xF8\xC0\xB6\xC8\x5C\x00',
    b'\x73\x60\x7B\xA0\x19\x13\xAA\xC9\x35\x48\x4B\xD3\xA4\xCD\x9F\x99',
    b'\xF3\x10\x44\x40\x54\x7E\x29\xF4\x06\x1F\xA2\xAB\xA1\x2F\x3C\xF6',
    b'\xAF\x85\x62\x36\x21\x7F\x5E\xDF\x20\x1A\xB3\xB4\xE6\xFF\x72\x84',
    b'\x8F\x65\x26\x94\x5A\x77\xEA\x43\x78\xC7\x4A\xCC\x2C\x14\x6B\xC6',
    b'\xE8\x74\x53\xFC\xD4\x1C\xCE\x31\x70\x03\x18\x8C\x96\x38\x32\x89',
    b'\xF1\x3A\x5F\xD7\xF9\xA9\x69\xB7\x63\x37\x58\xC2\x3B\xC3\x71\xCB',
    b'\x9E\x92\x01\x8A\x0B\x4D\x88\x9B\xBB\x4F\x6D\x6F\xE0\xFE\xA5\x49',
    b'\xDE\x56\x16\x09\xED\x9C\xC1\x2D\xEE\x81\x7D\xD9\x7C\xD1\x2E\x42',
    b'\x5B\x4D\xC1\xA6\x5D\xEA\x44\xFD\x45\x4E\x1B\xA1\x3F\xD1\x89\xE1',
    b'\x7D\x2F\xAA\xDB\xAB\xAD\x59\xCB\xB1\xCE\x9A\x28\xC9\xE0\xF6\x70',
    b'\x39\x4A\xD7\xFF\x30\xF5\xDD\xBC\x57\x3B\x11\x8D\xB2\xEE\x00\xB6',
    b'\xE6\x1A\x5A\x7C\xF9\xDE\xC4\xCD\x2E\x80\xBB\xB9\x4C\xA5\x9F\x84',
    b'\x08\xC6\x6F\x42\x6C\xF0\x27\xE7\x8B\x3A\x9C\x51\xFB\x67\x21\x75',
    b'\x41\x31\xA7\xCA\x20\x43\x2A\xB7\xBF\xD9\x7A\xF2\xB5\xF8\x8C\x2C',
    b'\x23\x83\x4F\x8F\x60\xA0\x04\x13\x37\x14\xE3\x01\xC5\x63\x66\x5C',
    b'\x74\x81\xDF\x58\xBD\x68\x90\x3D\xD2\xB3\x34\xF4\x19\x93\x32\x29',
    b'\xD6\x49\xAE\x0D\x4B\xD8\x07\x9E\xAC\x1E\x2D\x0B\x40\xB8\x72\xBA',
    b'\x76\x10\x71\xA8\xE4\x56\x1D\x48\xFE\xE5\xC2\x47\x91\xDA\x87\x26',
    b'\x9D\x1F\x88\x6B\xC0\x98\xBE\x25\x09\x97\x33\xA3\x85\x16\x5E\x7F',
    b'\xDC\x6E\x54\xE9\xF7\xA9\xC8\xE8\xC3\x77\xD0\x82\x2B\xEC\x02\x62',
    b'\x8A\x92\x0E\x3E\xB0\x0F\x05\xF3\xF1\x96\x78\x38\x86\x36\x18\x3C',
    b'\x24\xCF\x0A\xB4\x53\xCC\x61\x65\xA4\xC7\x94\xD5\x15\x7E\x6D\xEF',
    b'\x79\x22\x35\x12\x6A\x8E\x52\x06\x55\x7B\x46\x64\x50\x95\xE2\x0C',
    b'\xED\xD3\x17\x03\xA2\x9B\x99\xEB\x1C\xFC\xAF\xD4\x73\x69\xFA\x5F',
    b'\xF7\x2C\x1E\xBF\xC8\xE1\xF3\x9F\x76\x80\x71\x48\xAA\x94\xAD\x64',
    b'\xFB\x89\xC6\x60\xC3\x32\xB3\x4D\xD2\xE0\x44\xDD\x5F\xA8\xB1\xC7',
    b'\x68\x23\x34\xC9\x6D\x12\x7F\xB7\xEB\x15\xBE\xA9\xD1\x78\x93\xA0',
    b'\x0C\x92\xA4\xD7\x47\xE3\x8A\xC2\x70\xAB\x26\x41\x9A\x79\xA7\xD8',
    b'\x14\x85\x8F\xC0\x6F\x56\xD0\x8C\x11\xB9\x2E\x3C\xE2\x9D\xCF\x0E',
    b'\xDE\x03\x5D\x46\x3E\xCD\x38\x43\x0F\x33\x5A\xD9\x1A\x65\x6C\x22',
    b'\x3B\xFC\x30\xA6\x88\xEA\x37\xA2\xB4\x8D\x8E\x51\x9C\xD6\x40\xEE',
    b'\xF9\xF8\x84\xF4\xAE\x97\xE9\xCA\x0A\x45\x67\x57\x04\x2F\x83\x5C',
    b'\xD5\xC5\xC4\x82\xB6\xA3\x91\x98\x1F\x4A\xAC\x96\x81\x6E\xCB\x1B',
    b'\x09\x08\xAF\x18\x95\x49\x7D\x54\xED\xFA\x16\x31\x3A\xDA\xB8\x66',
    b'\xF5\xA5\xF1\xFE\x10\x01\x06\x74\xCC\x63\xDF\x7C\x28\x25\xF6\xCE',
    b'\xB2\x4F\x8B\xE5\xBC\x87\x69\xBB\x86\x21\x07\x00\x36\xE7\x0B\x50',
    b'\x59\x9B\x1C\xE8\x62\x58\x19\x61\xF2\xBD\x27\x5E\xBA\x1D\xE6\x99',
    b'\x42\x3D\x0D\x2A\xB5\xDC\x5B\x29\xF0\x2D\x4C\x53\x7B\x6A\x73\x4E',
    b'\x3F\x75\xFF\x4B\xA1\x35\x17\x55\x72\x39\x20\xD3\xB0\xFD\xEF\x02',
    b'\xEC\x77\x7E\xE4\x2B\xDB\x90\xC1\x05\x9E\x7A\xD4\x52\x6B\x24\x13'])

inv_s_box = bytearray(1024)

for i in range(4):
    idx = i * 256
    for j in range(256):
        inv_s_box[idx + s_box[idx + j]] = j


class AES_V3():
    r_con = [[1, 0, 2, 3], [1, 3, 0, 2], [0, 1, 3, 2], [1, 0, 2, 3]]
    r_con2 = [[1, 0, 2, 3], [2, 0, 3, 1], [0, 1, 3, 2], [1, 0, 2, 3]]
    r_orders = [[0, 9, 14, 11, 4, 13, 2, 7, 8, 1, 6, 15, 12, 5, 10, 3],
                [0, 9, 14, 15, 4, 13, 2, 7, 8, 1, 6, 3, 12, 5, 10, 11],
                [0, 9, 14, 7, 4, 13, 2, 11, 8, 1, 6, 3, 12, 5, 10, 15],
                [0, 9, 14, 11, 4, 13, 2, 7, 8, 1, 6, 15, 12, 5, 10, 3]]

    def __init__(self, aes_key, khronos):
        self.word_size = khronos & 3
        self.aes_key = aes_key

        self.s_box = s_box[self.word_size << 8:]
        self.inv_s_box = inv_s_box[self.word_size << 8:]

        self.master_key = self._expand_key()
        self._key_matrices = bytes2matrix(self.master_key)
        self.con = self.r_con[self.word_size]
        self.con2 = self.r_con2[self.word_size]

        self.order = self.r_orders[self.word_size]

    def _expand_key(self):
        init_values = [0xca025ddc, 0x823dc546, 0xc9420583, 0xc298225f]
        init_value = init_values[self.word_size]
        mk = bytearray(init_value.to_bytes(4, "little"))
        mk = mk * 4

        mk = xor_bytes(mk, self.aes_key)
        mk += bytearray(32)

        rounds = 8

        for i in range(4, 12):
            idx = 4 * (i - 1)
            k0, k1, k2, k3 = mk[idx], mk[idx + 1], mk[idx + 2], mk[idx + 3]

            if i & 3 == 0:
                k00 = (init_value >> (rounds & 24)) ^ self.s_box[k1]
                k1 = self.s_box[k2]
                k2 = self.s_box[k3]
                k3 = self.s_box[k0]
                k0 = k00 & 0xff
            rounds += 2

            mk[idx + 4] = k0 ^ mk[idx - 12]
            mk[idx + 5] = k1 ^ mk[idx - 11]
            mk[idx + 6] = k2 ^ mk[idx - 10]
            mk[idx + 7] = k3 ^ mk[idx - 9]
        return mk

    @staticmethod
    def sum_data(data):
        key = bytearray(32)
        for i in range(31):
            idx = i * 8
            n0 = (data[idx] >> 4) & 2
            n1 = n0 | data[idx + 1] & 64
            n2 = n1 | (data[idx + 2] >> 2) & 1
            n3 = n2 | (data[idx + 3] << 3) & -128
            n4 = n3 | (data[idx + 4] >> 1) & 4
            n5 = n4 | (data[idx + 5] << 3) & 16
            n6 = n5 | (data[idx + 6] << 5) & 32
            n7 = n6 | (data[idx + 7] >> 4) & 8
            key[i] = (n7 & 0xff)

        key[31] = 1
        return key

    @staticmethod
    def mix_columns(data, key):
        data = bytearray(data)

        for i in range(31):
            kk = key[i]
            idx = i * 8
            data[idx + 0] = (data[idx + 0] & -33) | ((kk << 4) & 0xff & 32)
            data[idx + 1] = (data[idx + 1] & -65) | (kk & 64)
            data[idx + 2] = (data[idx + 2] & -5) | ((kk * 4) & 4)
            data[idx + 3] = (data[idx + 3] & -17) | ((kk >> 3) & 16)
            data[idx + 4] = (data[idx + 4] & -9) | ((kk + kk) & 8)
            data[idx + 5] = (data[idx + 5] & -3) | ((kk >> 3) & 2)
            data[idx + 6] = (data[idx + 6] & -2) | ((kk >> 5) & 1)
            data[idx + 7] = (data[idx + 7] & 127) | ((kk << 4) & 0xff & -128)

        return data

    def encrypt(self, data, iv):
        plaintext = self.sum_data(data)
        blocks = []
        previous = iv
        for plaintext_block in split_blocks(plaintext):
            x = xor_bytes(plaintext_block, previous)
            block = self.encrypt_block(x)
            blocks.append(block)
            previous = block

        key = b''.join(blocks)
        data = self.mix_columns(data, key)
        return key[-1:] + data

    def encrypt_block(self, plaintext):
        plain_state = bytes2matrix(plaintext)

        add_round_key_con(plain_state, self._key_matrices[0:4], self.con2)

        for i in range(1, 3):
            self.sub_bytes(plain_state)
            self.shift_rows(plain_state)
            if i == 1:
                self.shift_rows_con(plain_state, self.con2)
                mix_columns(plain_state)

            add_round_key_con(plain_state, self._key_matrices[i * 4:], self.con2)

        add_round_key(plain_state, self._key_matrices[4:])

        return matrix2bytes(plain_state)

    def decrypt(self, ciphertext, iv, data):
        assert len(iv) == 16

        blocks = []
        previous = iv

        for ciphertext_block in split_blocks(ciphertext):
            dc = xor_bytes(previous, self.decrypt_block(ciphertext_block))
            blocks.append(dc)
            previous = ciphertext_block

        key = b''.join(blocks)
        data = self.mix_columns(data, key)
        return data

    def decrypt_block(self, ciphertext):
        assert len(ciphertext) == 16
        cipher_state = bytes2matrix(ciphertext)

        add_round_key(cipher_state, self._key_matrices[4:])

        for i in range(2, 0, -1):
            add_round_key_con(cipher_state, self._key_matrices[i * 4:], self.con2)

            if i == 1:
                inv_mix_columns(cipher_state)
                self.shift_rows_con(cipher_state, self.con)

            self.inv_shift_rows(cipher_state)
            self.inv_sub_bytes(cipher_state)

        add_round_key_con(cipher_state, self._key_matrices[0:4], self.con2)

        return matrix2bytes(cipher_state)

    def shift_rows_con(self, s, c):
        for i in range(4):
            s[i][0], s[i][1], s[i][2], s[i][3] = s[i][c[0]], s[i][c[1]], s[i][c[2]], s[i][c[3]]

    def shift_rows(self, s):
        bs = matrix2bytes(s)
        for i in range(4):
            for j in range(4):
                s[i][j] = bs[self.order[i * 4 + j]]

    def inv_shift_rows(self, s):
        order = bytearray(16)
        for i in range(16):
            order[self.order[i]] = i

        bs = matrix2bytes(s)
        for i in range(4):
            for j in range(4):
                s[i][j] = bs[order[i * 4 + j]]

    def sub_bytes(self, s):
        for i in range(4):
            for j in range(4):
                s[i][j] = self.s_box[s[i][j]]

        s[0], s[1], s[2], s[3] = s[self.con2[0]], s[self.con2[1]], s[self.con2[2]], s[self.con2[3]]

    def inv_sub_bytes(self, s):
        for i in range(4):
            for j in range(4):
                s[i][j] = self.inv_s_box[s[i][j]]
        s[0], s[1], s[2], s[3] = s[self.con[0]], s[self.con[1]], s[self.con[2]], s[self.con[3]]


SV = [0xa7aefe20, 0x7149f1d6, 0x47e4ca07, 0xe9b58f67, 0x93b924de, 0xc614d0f5, 0x38afe0ef, 0xb2bbad73,
      0xe24444c3, 0x9d3aec9b, 0xdf7b37e4, 0xd8b16d40, 0xf8ac31b8, 0x76b9a90b, 0x31d833ee, 0x953fce64,
      0x6a6b2b48, 0x8c138276, 0x6d24a010, 0x18da124b, 0xbbeb82ee, 0x39f7ea56, 0x149f4fe1, 0x229946bc,
      0x327f309, 0xf4f50e66, 0x62d569aa, 0x78419f92, 0x4db088a7, 0x7430a018, 0xf31d88f4, 0x2f4ed651,
      0x9b13fe59, 0x45c5910d, 0x374bf0ec, 0xd5a5b69e, 0xefaceb16, 0x714f4811, 0x4c98233b, 0xc9e6e7b1,
      0xd0623b3f, 0xdf5e4f6f, 0xccb31244, 0xaddab856, 0x6faf9c9e, 0x62804e10, 0x6fa7e29d, 0x7e429d51,
      0xcdb31e01, 0xb339e419, 0xe497a8a3, 0xebeca6bc, 0x1746cd57, 0xfbf4f54a, 0xd5ea2a8b, 0xb4f02ed2,
      0x512b192, 0xefad4d29, 0xd59bec05, 0x2a1436e2, 0xfaea73c1, 0x1ebdbae8, 0x8ff257bd, 0x2d59351d]


def leftCircularShift(k, bits):
    bits = bits % 32
    k = k % (2 ** 32)
    upper = (k << bits) % (2 ** 32)
    result = upper | (k >> (32 - (bits)))
    return (result)


def blockDivide(block, chunks):
    result = []
    size = len(block) // chunks
    for i in range(0, chunks):
        result.append(int.from_bytes(block[i * size:(i + 1) * size], byteorder="little"))
    return (result)


def F(X, Y, Z):
    return ((X & Y) | ((~X) & Z))


def G(X, Y, Z):
    return ((X & Z) | (Y & (~Z)))


def H(X, Y, Z):
    return (X ^ Y ^ Z)


def I(X, Y, Z):
    return (Y ^ (X | (~Z))) & 0xffffffff


def FF(a, b, c, d, M, s, t):
    result = b + leftCircularShift((a + F(b, c, d) + M + t), s)

    return (result)


def GG(a, b, c, d, M, s, t):
    result = b + leftCircularShift((a + G(b, c, d) + M + t), s)
    return (result)


def HH(a, b, c, d, M, s, t):
    result = b + leftCircularShift((a + H(b, c, d) + M + t), s)
    return (result)


def II(a, b, c, d, M, s, t):
    result = b + leftCircularShift((a + I(b, c, d) + M + t), s)
    return (result)


def md5sum(msg, n=0):
    A = 0x79e0f2fb
    B = 0xc8b52570
    C = 0xebc2f8cd
    D = 0x7c104d93

    a = A
    b = B
    c = C
    d = D
    block = msg[:64]
    M = blockDivide(block, 16)
    a = FF(a, b, c, d, M[0], 7, SV[0])
    d = FF(d, a, b, c, M[13], 12, SV[1])
    c = FF(c, d, a, b, M[14], 17, SV[2])
    b = FF(b, c, d, a, M[12], 22, SV[3])
    a = FF(a, b, c, d, M[11], 7, SV[4])
    d = FF(d, a, b, c, M[10], 12, SV[5])
    c = FF(c, d, a, b, M[9], 17, SV[6])
    b = FF(b, c, d, a, M[7], 22, SV[7])
    a = FF(a, b, c, d, M[8], 7, SV[8])
    d = FF(d, a, b, c, M[6], 12, SV[9])
    c = FF(c, d, a, b, M[5], 17, SV[10])
    b = FF(b, c, d, a, M[4], 22, SV[11])
    a = FF(a, b, c, d, M[3], 7, SV[12])
    d = FF(d, a, b, c, M[2], 12, SV[13])
    c = FF(c, d, a, b, M[1], 17, SV[14])
    b = FF(b, c, d, a, M[15], 22, SV[15])

    a = GG(a, b, c, d, M[0], 5, SV[16])
    d = GG(d, a, b, c, M[5], 9, SV[17])
    c = GG(c, d, a, b, M[10], 14, SV[18])
    b = GG(b, c, d, a, M[1], 20, SV[19])
    a = GG(a, b, c, d, M[12], 5, SV[20])
    d = GG(d, a, b, c, M[11], 9, SV[21])
    c = GG(c, d, a, b, M[15], 14, SV[22])
    b = GG(b, c, d, a, M[2], 20, SV[23])
    a = GG(a, b, c, d, M[9], 5, SV[24])
    d = GG(d, a, b, c, M[13], 9, SV[25])
    c = GG(c, d, a, b, M[3], 14, SV[26])
    b = GG(b, c, d, a, M[8], 20, SV[27])
    a = GG(a, b, c, d, M[6], 5, SV[28])
    d = GG(d, a, b, c, M[7], 9, SV[29])
    c = GG(c, d, a, b, M[4], 14, SV[30])
    b = GG(b, c, d, a, M[14], 20, SV[31])

    a = HH(a, b, c, d, M[8], 4, SV[32])
    d = HH(d, a, b, c, M[5], 11, SV[33])
    c = HH(c, d, a, b, M[12], 16, SV[34])
    b = HH(b, c, d, a, M[13], 23, SV[35])
    a = HH(a, b, c, d, M[1], 4, SV[36])
    d = HH(d, a, b, c, M[12], 11, SV[37])
    c = HH(c, d, a, b, M[7], 16, SV[38])
    b = HH(b, c, d, a, M[14], 23, SV[39])
    a = HH(a, b, c, d, M[10], 4, SV[40])
    d = HH(d, a, b, c, M[0], 11, SV[41])
    c = HH(c, d, a, b, M[2], 16, SV[42])
    b = HH(b, c, d, a, M[6], 23, SV[43])
    a = HH(a, b, c, d, M[4], 4, SV[44])
    d = HH(d, a, b, c, M[11], 11, SV[45])
    c = HH(c, d, a, b, M[15], 16, SV[46])
    b = HH(b, c, d, a, M[3], 23, SV[47])

    a = II(a, b, c, d, M[8], 6, SV[48])
    d = II(d, a, b, c, M[6], 10, SV[49])
    c = II(c, d, a, b, M[15], 15, SV[50])
    b = II(b, c, d, a, M[5], 21, SV[51])
    a = II(a, b, c, d, M[14], 6, SV[52])
    d = II(d, a, b, c, M[9], 10, SV[53])
    c = II(c, d, a, b, M[10], 15, SV[54])
    b = II(b, c, d, a, M[2], 21, SV[55])
    a = II(a, b, c, d, M[2], 6, SV[56])
    d = II(d, a, b, c, M[13], 10, SV[57])
    c = II(c, d, a, b, M[7], 15, SV[58])
    b = II(b, c, d, a, M[12], 21, SV[59])
    a = II(a, b, c, d, M[4], 6, SV[60])
    d = II(d, a, b, c, M[1], 10, SV[61])
    c = II(c, d, a, b, M[11], 15, SV[62])
    b = II(b, c, d, a, M[3], 21, SV[63])
    A = (A + a) % (2 ** 32) ^ 0x19be4866
    B = (B + b) % (2 ** 32) ^ 0xe85986b4
    C = (C + c) % (2 ** 32) ^ 0xe19b326e
    D = (D + d) % (2 ** 32) ^ 0x71d1d7d4

    result = bytearray(
        A.to_bytes(4, "little") + B.to_bytes(4, "little") + C.to_bytes(4, "little") + D.to_bytes(4, "little"))

    result += sum_md5(result).to_bytes(4, "little")
    return result


def sum_md5(data):
    check_sum = 0x20220420
    for i in range(12):
        if i % 2 == 0:
            temp = (check_sum >> 3) ^ check_sum
            check_sum = data[i] ^ (check_sum << 7)
        else:
            temp = (check_sum >> 5) ^ check_sum
            check_sum = data[i] | (check_sum << 11)
            check_sum ^= 0xffffffff

        check_sum ^= temp
        check_sum &= 0xffffffff

    check_sum |= 4
    check_sum ^= 0x1000000
    return check_sum


SV2 = [0xa7aefe20, 0x7149f1d6, 0x47e4ca07, 0xe9b58f67, 0x93b924de, 0xc614d0f5, 0x38afe0ef, 0xb2bbad73,
       0xe24444c3, 0x9d3aec9b, 0xdf7b37e4, 0xd8b16d40, 0xf8ac31b8, 0x76b9a90b, 0x31d833ee, 0x953fce64,
       0x353595a4, 0x4609c13b, 0x36925008, 0x8c6d0925, 0x5df5c177, 0x1cfbf52b, 0x8a4fa7f0, 0x114ca35e,
       0x8193f984, 0x7a7a8733, 0x316ab4d5, 0x3c20cfc9, 0xa6d84453, 0x3a18500c, 0x798ec47a, 0x97a76b28,
       0x66c4ff96, 0x51716443, 0xdd2fc3b, 0xb5696da7, 0xbbeb3ac5, 0x5c53d204, 0xd32608ce, 0x7279b9ec,
       0xf4188ecf, 0xf7d793db, 0x332cc491, 0xab76ae15, 0x9bebe727, 0x18a01384, 0x5be9f8a7, 0x5f90a754,
       0x39b663c0, 0x36673c83, 0x7c92f514, 0x9d7d94d7, 0xe2e8d9aa, 0x5f7e9ea9, 0x7abd4551, 0x569e05da,
       0x40a25632, 0x3df5a9a5, 0xbab37d80, 0x454286dc, 0x3f5d4e78, 0x3d7b75d, 0xb1fe4af7, 0xa5ab26a3]


def md5sum_v3(msg, count_v2, orders, count_v1, n=0):
    count = count_v2 & 0xff

    sv = [0] * 64
    for i in range(64):
        sv[i] = ror32(SV2[i], count_v1)

    start = [
        ror32(0x79e0f2fb, count),
        ror32(0xc8b52570, count),
        ror32(0xebc2f8cd, count),
        ror32(0x7c104d93, count)
    ]

    count = (count_v2 + 6) & 0xff
    end = [
        ror32(0x19be4866, count),
        ror32(0xe85986b4, count),
        ror32(0xe19b326e, count),
        ror32(0x71d1d7d4, count)
    ]
    A = start[0]
    B = start[1]
    C = start[2]
    D = start[3]

    a = A
    b = B
    c = C
    d = D
    block = msg[:64]
    M = blockDivide(block, 16)

    order1 = orders[:16]
    order2 = orders[16:32]
    order3 = orders[32:48]
    order4 = orders[48:]
    a = FF(a, b, c, d, M[order1[0]], 7, sv[0])
    d = FF(d, a, b, c, M[order1[1]], 12, sv[1])
    c = FF(c, d, a, b, M[order1[2]], 17, sv[2])
    b = FF(b, c, d, a, M[order1[3]], 22, sv[3])
    a = FF(a, b, c, d, M[order1[4]], 7, sv[4])
    d = FF(d, a, b, c, M[order1[5]], 12, sv[5])
    c = FF(c, d, a, b, M[order1[6]], 17, sv[6])
    b = FF(b, c, d, a, M[order1[7]], 22, sv[7])
    a = FF(a, b, c, d, M[order1[8]], 7, sv[8])
    d = FF(d, a, b, c, M[order1[9]], 12, sv[9])
    c = FF(c, d, a, b, M[order1[10]], 17, sv[10])
    b = FF(b, c, d, a, M[order1[11]], 22, sv[11])
    a = FF(a, b, c, d, M[order1[12]], 7, sv[12])
    d = FF(d, a, b, c, M[order1[13]], 12, sv[13])
    c = FF(c, d, a, b, M[order1[14]], 17, sv[14])
    b = FF(b, c, d, a, M[order1[15]], 22, sv[15])

    a = GG(a, b, c, d, M[order2[0]], 5, sv[16])
    d = GG(d, a, b, c, M[order2[1]], 9, sv[17])
    c = GG(c, d, a, b, M[order2[2]], 14, sv[18])
    b = GG(b, c, d, a, M[order2[3]], 20, sv[19])
    a = GG(a, b, c, d, M[order2[4]], 5, sv[20])
    d = GG(d, a, b, c, M[order2[5]], 9, sv[21])
    c = GG(c, d, a, b, M[order2[6]], 14, sv[22])
    b = GG(b, c, d, a, M[order2[7]], 20, sv[23])
    a = GG(a, b, c, d, M[order2[8]], 5, sv[24])
    d = GG(d, a, b, c, M[order2[9]], 9, sv[25])
    c = GG(c, d, a, b, M[order2[10]], 14, sv[26])
    b = GG(b, c, d, a, M[order2[11]], 20, sv[27])
    a = GG(a, b, c, d, M[order2[12]], 5, sv[28])
    d = GG(d, a, b, c, M[order2[13]], 9, sv[29])
    c = GG(c, d, a, b, M[order2[14]], 14, sv[30])
    b = GG(b, c, d, a, M[order2[15]], 20, sv[31])

    a = HH(a, b, c, d, M[order3[0]], 4, sv[32])
    d = HH(d, a, b, c, M[order3[1]], 11, sv[33])
    c = HH(c, d, a, b, M[order3[2]], 16, sv[34])
    b = HH(b, c, d, a, M[order3[3]], 23, sv[35])
    a = HH(a, b, c, d, M[order3[4]], 4, sv[36])
    d = HH(d, a, b, c, M[order3[5]], 11, sv[37])
    c = HH(c, d, a, b, M[order3[6]], 16, sv[38])
    b = HH(b, c, d, a, M[order3[7]], 23, sv[39])
    a = HH(a, b, c, d, M[order3[8]], 4, sv[40])
    d = HH(d, a, b, c, M[order3[9]], 11, sv[41])
    c = HH(c, d, a, b, M[order3[10]], 16, sv[42])
    b = HH(b, c, d, a, M[order3[11]], 23, sv[43])
    a = HH(a, b, c, d, M[order3[12]], 4, sv[44])
    d = HH(d, a, b, c, M[order3[13]], 11, sv[45])
    c = HH(c, d, a, b, M[order3[14]], 16, sv[46])
    b = HH(b, c, d, a, M[order3[15]], 23, sv[47])

    a = II(a, b, c, d, M[order4[0]], 6, sv[48])
    d = II(d, a, b, c, M[order4[1]], 10, sv[49])
    c = II(c, d, a, b, M[order4[2]], 15, sv[50])
    b = II(b, c, d, a, M[order4[3]], 21, sv[51])
    a = II(a, b, c, d, M[order4[4]], 6, sv[52])
    d = II(d, a, b, c, M[order4[5]], 10, sv[53])
    c = II(c, d, a, b, M[order4[6]], 15, sv[54])
    b = II(b, c, d, a, M[order4[7]], 21, sv[55])
    a = II(a, b, c, d, M[order4[8]], 6, sv[56])
    d = II(d, a, b, c, M[order4[9]], 10, sv[57])
    c = II(c, d, a, b, M[order4[10]], 15, sv[58])
    b = II(b, c, d, a, M[order4[11]], 21, sv[59])
    a = II(a, b, c, d, M[order4[12]], 6, sv[60])
    d = II(d, a, b, c, M[order4[13]], 10, sv[61])
    c = II(c, d, a, b, M[order4[14]], 15, sv[62])
    b = II(b, c, d, a, M[order4[15]], 21, sv[63])

    A = (A + a) % (2 ** 32) ^ end[0]
    B = (B + b) % (2 ** 32) ^ end[1]
    C = (C + c) % (2 ** 32) ^ end[2]
    D = (D + d) % (2 ** 32) ^ end[3]

    result = bytearray(
        A.to_bytes(4, "little") + B.to_bytes(4, "little") + C.to_bytes(4, "little") + D.to_bytes(4, "little"))

    result += sum_md5(result).to_bytes(4, "little")
    return result


def bxor(b1, b2):
    b3 = bytearray(len(b1))
    for i in range(len(b1)):
        b3[i] = b1[i] ^ b2[i]
    return b3


def get_iv(iv, data):
    for i in range(len(data)):
        if i & 1 == 0:
            iv = (iv >> 4) ^ iv ^ (iv << 6) ^ data[i]
        else:
            iv = ~((iv >> 7) ^ iv ^ (data[i] | iv << 12))
        iv = iv & 0xffffffff
    return iv


def hash_f13(query_sm3, body_md5_bytes, ts_bytes, khronos):
    iv = get_iv(0x20230928, query_sm3)
    iv = get_iv(iv, body_md5_bytes)
    iv = get_iv(iv, ts_bytes)

    iv_v0 = ((iv & 15) * 171) >> 9
    branch = (iv & 15) - ((iv_v0 * 3) & 0xff)
    if branch == 0:
        return branch_0(iv_v0, khronos, query_sm3, body_md5_bytes, ts_bytes)
    elif branch == 1:
        return branch_1(iv_v0, khronos, query_sm3, body_md5_bytes, ts_bytes)
    elif branch == 2:
        return branch_2(iv, khronos, query_sm3, body_md5_bytes, ts_bytes)
    else:
        raise Exception("no branch: " + str(branch))


def branch_0(iv_v0, khronos, query_sm3, body_md5_bytes, ts_bytes):
    tt01 = [0xc4a78580, 0xb3c0fd39, 0xc58c5686, 0xc9aa3ba7, 0xf5a7adf2, 0x963c2ed1]
    iv_v1 = tt01[iv_v0]

    count_v1 = (iv_v1 + khronos + 1) & 0xff
    count_v2 = (iv_v1 + khronos) & 0xffffffff

    tt02 = [0xebb64faf, 0x7aadcc2, 0xcf3187bf, 0xe01138ff, 0x6d0bfcff, 0x5a30a3be, 0xb41ad638, 0x34180eb8, 0xf233eb6f,
            0xb1a584cc, 0xccc30dc7, 0x47d1db51, 0xd55653de, 0x70a84fa1, 0x57473c12, 0xf76f0288, 0x2c077f0a, 0xda0dcad0,
            0xfbb86f6c, 0xfdc4cf00, 0x688a020d, 0xe676c6a6, 0x8cd6338b, 0x1a3c8d0e, 0xcce8b06b, 0x6ad0ed0b, 0xa0522717,
            0xdc71ac83, 0x2285db71, 0xd5b4dda6, 0x736f8650, 0x6560306c, 0x617ce2a6, 0xe423417e, 0xa40e143, 0x544e4032,
            0x88dffb2a, 0x716c1ae0, 0x4c467a88, 0x5b23bb3, 0xe1d0b866, 0xbaa3dcb8, 0xae3374d3, 0xc3381a50, 0x1702f75b,
            0xfe6da368, 0xf0b4cf48, 0x4e0ffbb8, 0x72aad10d, 0x26c53a3d, 0xf2bce0f6, 0xb4557581, 0x4a257fdd, 0x8c3182a2,
            0xab0b3b86, 0x3d5dfb14, 0x4f103634, 0xd37b52d7, 0x444eff16, 0xeb0a33d1, 0x6ca86f6e, 0x284ba7, 0x8387cfa,
            0x5fb37586]

    tt03 = [0] * 64
    for i in range(0, 64):
        tt03[i] = ror32(tt02[i], count_v1) & 0xffffffff

    n0 = (count_v2 + 2) & 7

    pad = bytearray(4)
    seed = bytes([0xfa, 0x45, 0x61, 0xd7])
    for i in range(4):
        v = int.from_bytes(bytes([seed[i], seed[i]]), 'little')
        v = v >> n0
        pad[i] = v & 0xff

    count_v2 = count_v2 & 0xff
    init_value = [
        ror32(0x7aba4fc8, count_v2), ror32(0x67166507, count_v2),
        ror32(0x6403fa00, count_v2), ror32(0x340f512f, count_v2),
        ror32(984304912, count_v2), ror32(3005047866, count_v2),
        ror32(2874125293, count_v2), ror32(2152413264, count_v2)
    ]

    data = query_sm3 + body_md5_bytes + ts_bytes + pad + bytes.fromhex(' 00 00 00 00 00 00 01 a0')
    di = [0] * (len(data) // 4)
    for i in range(len(data) // 4):
        di[i] = int.from_bytes(data[i * 4:i * 4 + 4], "big")

    di0 = di[0]
    for i in range(112):
        di1, di14 = di[i + 1], di[i + 14]
        r_di1 = rol(di1, 14) ^ rol(di1, 25) ^ (di1 >> 3)
        r_di2 = rol(di14, 13) ^ rol(di14, 15) ^ (di14 >> 10)
        di0 = di0 + di[i + 9] + r_di1 + r_di2
        di.append(di0 & 0xffffffff)
        di0 = di1

    if iv_v0 == 5:
        v_j = branch0_xor(init_value, iv_v1, di, tt03, 100, 2, 0, 3, 5, 4, 6, 7, 2, 1, 5)
    elif iv_v0 == 4:
        v_j = branch0_xor(init_value, iv_v1, di, tt03, 96, 0, 5, 6, 7, 3, 1, 2, 5, 4, 4)
    elif iv_v0 == 3:
        v_j = branch0_xor(init_value, iv_v1, di, tt03, 99, 3, 6, 2, 4, 5, 1, 0, 0, 7, 6)
    elif iv_v0 == 2:
        v_j = branch0_xor(init_value, iv_v1, di, tt03, 96, 7, 6, 2, 1, 4, 0, 5, 4, 3, 5)
    elif iv_v0 == 1:
        v_j = branch0_xor(init_value, iv_v1, di, tt03, 96, 0, 6, 7, 5, 3, 2, 1, 5, 4, 4)
    elif iv_v0 == 0:
        v_j = branch0_xor(init_value, iv_v1, di, tt03, 101, 5, 7, 6, 3, 2, 1, 0, 5, 4, 3)

    ret = bytearray(32)
    for i in range(8):
        ret[i * 4:i * 4 + 4] = ((v_j[i] + init_value[i]) & 0xffffffff).to_bytes(4, 'big')

    ret = bxor(ret[:16], ret[16:])
    sum = sum_md5(ret)
    ret += sum.to_bytes(4, "little")
    return ret


def swap_v0(src, src_xor, tt2, table_f, order1, typ=None):
    da0 = [0] * 8
    ha0 = src_xor[:]
    for i in range(8):
        da0[i] = src[order1[i]] ^ src_xor[i]

    for round in range(10):
        rr_0 = r00(ha0[0], ha0[1], ha0[2], ha0[3], ha0[4], ha0[5], ha0[6], ha0[7], 0, table_f)
        rr_1 = r00(ha0[1], ha0[2], ha0[3], ha0[4], ha0[5], ha0[6], ha0[7], ha0[0], 0, table_f)
        rr_2 = r00(ha0[2], ha0[3], ha0[4], ha0[5], ha0[6], ha0[7], ha0[0], ha0[1], 0, table_f)
        rr_3 = r00(ha0[3], ha0[4], ha0[5], ha0[6], ha0[7], ha0[0], ha0[1], ha0[2], 0, table_f)
        rr_4 = r00(ha0[4], ha0[5], ha0[6], ha0[7], ha0[0], ha0[1], ha0[2], ha0[3], 0, table_f)
        rr_5 = r00(ha0[5], ha0[6], ha0[7], ha0[0], ha0[1], ha0[2], ha0[3], ha0[4], 0, table_f)
        rr_6 = r00(ha0[6], ha0[7], ha0[0], ha0[1], ha0[2], ha0[3], ha0[4], ha0[5], 0, table_f)
        rr_7 = r00(ha0[7], ha0[0], ha0[1], ha0[2], ha0[3], ha0[4], ha0[5], ha0[6], 0, table_f)
        rr_7 = rr_7 ^ tt2[round + 1]

        d0, d1, d2, d3, d4, d5, d6, d7 = da0[0], da0[1], da0[2], da0[3], da0[4], da0[5], da0[6], da0[7]

        da0[0] = r00(d0, d1, d2, d3, d4, d5, d6, d7, rr_0, table_f)
        da0[1] = r00(d1, d2, d3, d4, d5, d6, d7, d0, rr_1, table_f)
        da0[2] = r00(d2, d3, d4, d5, d6, d7, d0, d1, rr_2, table_f)
        da0[3] = r00(d3, d4, d5, d6, d7, d0, d1, d2, rr_3, table_f)
        da0[4] = r00(d4, d5, d6, d7, d0, d1, d2, d3, rr_4, table_f)
        da0[5] = r00(d5, d6, d7, d0, d1, d2, d3, d4, rr_5, table_f)
        da0[6] = r00(d6, d7, d0, d1, d2, d3, d4, d5, rr_6, table_f)
        da0[7] = r00(d7, d0, d1, d2, d3, d4, d5, d6, rr_7, table_f)

        ha0[0], ha0[1], ha0[2], ha0[3], ha0[4], ha0[5], ha0[6], ha0[7] = rr_0, rr_1, rr_2, rr_3, rr_4, rr_5, rr_6, rr_7

    if typ is None:
        src[0] = da0[0] ^ src_xor[0] ^ src[0]
        src[1] = da0[7] ^ src_xor[1] ^ src[1]
        src[2] = da0[6] ^ src_xor[2] ^ src[2]
        src[3] = da0[5] ^ src_xor[3] ^ src[3]
        src[4] = da0[4] ^ src_xor[4] ^ src[4]
        src[5] = da0[3] ^ src_xor[5] ^ src[5]
        src[6] = da0[2] ^ src_xor[6] ^ src[6]
        src[7] = da0[1] ^ src_xor[7] ^ src[7]
    else:
        src[0] = da0[7] ^ typ[1]
        src[1] = da0[6] ^ typ[2]
        src[2] = da0[5] ^ typ[3]
        src[3] = da0[4] ^ typ[4]
        src[4] = da0[3] ^ typ[5]
        src[5] = da0[2] ^ typ[6]
        src[6] = da0[1] ^ typ[7] ^ src[7]
        src[7] = da0[0] ^ typ[0]
    return src


def branch_1(iv_v0, khronos, query_sm3, body_md5_bytes, ts_bytes):
    tt1 = [0x808a9c79, 0xf079807e, 0xbadf79c5, 0xa785d3ff, 0x82d8438c]
    iv_v1 = tt1[iv_v0]

    c_v1 = (iv_v1 + khronos) & 0xff
    c_v1 = ror(khronos, c_v1)

    orders = bytes.fromhex('''05 07 01 02 04 00 06 03 00 05 02 04 01 03 07 06
    05 07 02 04 01 06 03 00 03 00 02 04 06 07 01 05
    04 05 00 03 06 02 01 07 00 00 00 00 00 00 00 00''')

    order1 = orders[iv_v0 * 8:iv_v0 * 8 + 8]

    iv_v1 = (iv_v1 + khronos + 1) & 63
    tt1 = [0x87aeea5dab37cd6b, 0x7ff48becb4f54087, 0xb0724c06706bbd5d, 0x1fe5dfb1143e328d,
           0x1a2331d00af4f1f2, 0xcaff7131bb1e71ba, 0x33385e1042752218, 0xff01ed65d4a441fb,
           0xadb1ec8828c80e8, 0x62475d12f4e06fe7, 0xbd0b238da4fe72]

    tt2 = [0] * 11
    for i in range(0, 11):
        tt2[i] = ror(tt1[i], iv_v1)

    to_sign = bytearray(query_sm3 + body_md5_bytes + ts_bytes + bytes([0x80, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]))

    src = [0] * (len(to_sign) // 8)
    for i in range(len(to_sign) // 8):
        src[i] = int.from_bytes(to_sign[i * 8:i * 8 + 8], 'big')

    src_xor = [c_v1, c_v1, c_v1, c_v1, c_v1, c_v1, c_v1, c_v1]

    table_f = get_branch_1_table_f(iv_v0)
    swap = swap_v0(src, src_xor, tt2, table_f, order1)
    data = [0] * 8
    data[7] = 416

    src_xor = [swap[4], swap[3], swap[2], swap[1], swap[0], swap[7], swap[6], swap[5]]
    swap = swap_v0(data, src_xor, tt2, table_f, order1, swap)

    ret = bytearray(32)
    n = 0
    for i in range(7, -1, -1):
        pp = swap[i].to_bytes(8, "little")
        ret[n + 0], ret[n + 1], ret[n + 2], ret[n + 3] = pp[1], pp[3], pp[5], pp[6]
        n += 4

    for i in range(16):
        ret[i] ^= ret[i + 16]
    ret = ret[:16]
    sum = sum_md5(ret)
    ret += sum.to_bytes(4, "little")
    return ret


def r00(r0, r1, r2, r3, r4, r5, r6, r7, tt, table_f, v=0):
    x = table_f(8 * (r0 >> 56))
    r1 = (r1 >> 45) & 2040

    if tt > 0:
        x = x ^ tt
    x = x ^ table_f(r1 + 2048)

    r2 = (r2 >> 37) & 2040
    x = x ^ table_f(r2 + 4096)

    r3 = (r3 >> 29) & 2040
    x = x ^ table_f(r3 + 6144)

    r4 = (r4 >> 21) & 2040
    x = x ^ table_f(r4 + 8192)

    r5 = (r5 >> 13) & 2040
    x = x ^ table_f(r5 + 10240)

    r6 = (r6 >> 8) & 255
    x = x ^ table_f(8 * r6 + 12288)

    r7 = r7 & 255
    x = x ^ table_f(8 * r7 + 14336)

    return x


branch_2_orders = bytes.fromhex('''
    0f 07 04 00 09 08 03 0a 06 0b 05 0d 0e 01 0c 02 0f 05 08 0c 00 09 02 01 03 07 0e 06 0b 0a 0d 04 06 05 00 07 0c 00 0a 04 08 0f 01 0b 0d 09 02 0e 06 0b 02 05 04 03 08 01 01 07 0a 00 0d 0c 09 0e
    0d 07 0e 0f 0b 02 08 03 0c 05 09 01 00 04 06 0a 0d 09 02 06 0f 0b 0a 04 08 07 00 0c 05 03 01 0e 0c 09 0f 07 06 0f 03 0e 02 0d 04 05 01 0b 0a 00 0c 05 0a 09 0e 08 02 04 04 07 03 0f 01 06 0b 00
    0b 0f 04 08 02 0a 07 00 09 0d 06 01 0e 03 05 0c 0b 06 0a 05 08 02 0c 03 07 0f 0e 09 0d 00 01 04 09 06 08 0f 05 08 00 04 0a 0b 03 0d 01 02 0c 0e 09 0d 0c 06 04 07 0a 03 03 0f 00 08 01 05 02 0e
    01 00 0d 0f 09 0a 0b 0e 04 02 08 07 03 06 0c 05 01 08 0a 0c 0f 09 05 06 0b 00 03 04 02 0e 07 0d 04 08 0f 00 0c 0f 0e 0d 0a 01 06 02 07 09 05 03 04 02 05 08 0d 0b 0a 06 06 00 0e 0f 07 0c 09 03
    0a 08 04 0f 00 0b 01 06 0d 0c 07 09 03 0e 05 02 0a 07 0b 05 0f 00 02 0e 01 08 03 0d 0c 06 09 04 0d 07 0f 08 05 0f 06 04 0b 0a 0e 0c 09 00 02 03 0d 0c 02 07 04 01 0b 0e 0e 08 06 0f 09 05 00 03
    ''')


def branch_2(iv, khronos, query_sm3, body_md5_bytes, ts_bytes):
    n0 = (iv & 15 - 2) * 86
    iv_v0 = (n0 >> 15 & 0xff) + (n0 >> 8 & 0xff)

    t001 = [0x8980f29b, 0xeb549c7f, 0xb08726db, 0xd40cb5e6, 0xe8f559e4]

    n1 = t001[iv_v0]
    count_v1 = (n1 + khronos + 1) & 0xff
    count_v2 = (n1 + khronos) & 0xffffffff

    n0 = (count_v2 + 5) & 7

    pad = bytearray(8)
    seed = bytes([0x84, 0x96, 0x77, 0x9d, 0xd4, 0x15, 0x0b, 0xf8])
    for i in range(8):
        v = int.from_bytes(bytes([seed[i], seed[i]]), 'little')
        v = v >> n0
        pad[i] = v & 0xff

    data = query_sm3 + body_md5_bytes + ts_bytes + pad + bytes.fromhex('a0 01 00 00')

    idx = iv_v0 << 6
    ret = md5sum_v3(data, count_v2, branch_2_orders[idx:idx + 64], count_v1)

    return ret


def branch0_xor(data, base, di, tt03, round, x1, x2, x3, x4, x5, x6, x7, x8, x9, x10):
    d = data[:]

    for i in range(round):
        offset = base + i
        n0 = di[offset & 127]

        n1 = ((d[x3] ^ d[x4]) & d[x1]) ^ d[x3]

        n2 = rol(d[x1], 26) ^ rol(d[x1], 21) ^ rol(d[x1], 7)
        offset = offset & 63
        n3 = tt03[offset]

        n4 = (n0 + n1 + n2 + n3 + d[x5]) & 0xffffffff

        n5 = rol(d[x2], 30) ^ rol(d[x2], 19) ^ rol(d[x2], 10)
        n6 = (d[x2] & d[x6]) | ((d[x2] | d[x6]) & d[x7])
        n7 = n5 + n6

        o = d[x9]
        d[0], d[1], d[2], d[3], d[4], d[5], d[6], d[7] = d[7], d[0], d[1], d[2], d[3], d[4], d[5], d[6]
        d[x10] = (n7 + n4) & 0xffffffff
        d[x8] = (o + n4) & 0xffffffff
    return d


_BR1_RAW = None


def get_branch_1_table_f(iv_v0):
    global _BR1_RAW
    if _BR1_RAW is None:
        _BR1_RAW = bytes([item for sublist in _get_branch_one_table() for item in sublist])

    table = _BR1_RAW[iv_v0 << 14:]
    def table_f(x):
        return int.from_bytes(table[x:x + 8], 'little')
    return table_f


import hashlib


def rc4_xg(data, key):
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) % 256
        S[i] = S[j]
    i = j = 0

    result = bytearray(len(data))
    for k, v in enumerate(data):
        i += 1
        x = S[i]
        j += x
        y = S[j & 0xff]
        S[i] = y
        result[k] = v ^ S[(y + y) & 0xff]

    return result


def reverse_bits(num):
    bin_num = bin(num)[2:].zfill(8)
    rev_bin_num = bin_num[::-1]
    rev_num = int(rev_bin_num, 2)

    return rev_num


gorgon_84 = bytes([0x4a, 0x16, 0x47, 0x6c, 0x84, 0x04])

def encrypt_gorgon(body, query, khronos, xg_rand, dataType):
    xg_seed = 320
    body_md5 = xssstub_hash_md5_hex(data=body, dataType=dataType).lower() if body else ""

    data = hashlib.md5(query.encode()).digest()[:4]

    if len(body_md5) > 0:
        body_md5 = bytes.fromhex(body_md5)
        data += body_md5[:4]
    else:
        data += bytearray([0, 0, 0, 0])
    data += bytearray([0, 0, 0, 0])
    mssdkVersionInt = 67503104
    data += mssdkVersionInt.to_bytes(4, "little")
    data += khronos.to_bytes(4, "big")
    key = bytes([
        gorgon_84[0],
        320 & 0xff,
        gorgon_84[1],
        (xg_rand >> 8) & 0xff,
        gorgon_84[2],
        gorgon_84[3],
        (320 >> 8) & 0xff,
        xg_rand & 0xff,
    ])

    out = rc4_xg(data, key)
    for i in range(len(out)):
        a = out[i]
        out[i] = (a >> 4 | (a << 4)) & 0xFF
        a = out[0]
        if i + 1 < len(out):
            a = out[i + 1]
        a ^= out[i]
        a = reverse_bits(a)
        out[i] = (~(a ^ 20)) & 0xFF

    ret = gorgon_84[-2:]
    ret += xg_rand.to_bytes(2, "little")
    ret += xg_seed.to_bytes(2, "little")
    ret += out

    return ret.hex()


import base64
import hashlib
import random


def ror(value, count):
    count %= 64
    low = value << (64 - count)
    value >>= count
    value |= low
    value &= 0xFFFFFFFFFFFFFFFF
    return value


HexTable = b"0123456789abcdef"


def _helios_bytes2matrix(text):
    return [int.from_bytes(list(text[i:i + 8]), 'little') for i in range(0, len(text), 8)]


def encrypt_helios_input(hash_table, in_data):
    data0 = int.from_bytes(in_data[:8], 'little')
    data1 = int.from_bytes(in_data[8:], 'little')
    for i in range(0, 0x22):
        hash1 = hash_table[i]
        data1 = hash1 ^ (data0 + ror(data1, 8))
        data1 &= 0xFFFFFFFFFFFFFFFF
        data0 = data1 ^ ror(data0, 61)
        data0 &= 0xFFFFFFFFFFFFFFFF

    return data0.to_bytes(8, 'little') + data1.to_bytes(8, 'little')


def encrypt_helios(khronos, rand=0):
    rand = rand or int(random.randint(0, 0xFFFFFFFF))
    data = rand.to_bytes(4, "little")
    data += str(8662).encode()
    key_sum = hashlib.md5(data).digest()

    keys = bytearray(32)
    for i in range(16):
        v1 = key_sum[i]
        keys[2 * i] = HexTable[v1 >> 4]
        keys[2 * i + 1] = HexTable[v1 & 15]

    hash_table = []
    hash_table.append(int.from_bytes(keys[:8], "little"))

    keys = _helios_bytes2matrix(keys)
    buffer_b0 = keys[0]
    buffer_b8 = keys[1]
    keys.pop(0)
    keys.pop(0)

    for i in range(0, 0x22):
        x9 = buffer_b0
        x8 = buffer_b8

        x8 = ror(x8, 8)
        x8 = x8 + x9
        x8 = (x8 ^ i) & 0xFFFFFFFFFFFFFFFF
        keys.append(x8)

        x8 = x8 ^ ror(x9, 61)
        x8 &= 0xFFFFFFFFFFFFFFFF

        hash_table.append(x8)
        buffer_b0 = x8
        buffer_b8 = keys[0]
        keys.pop(0)

    in_data = _pkcs7_pad(bytes(f"{khronos}-1588093228-8662", 'utf-8'), 16)
    out = bytearray()
    for i in range(len(in_data) // 16):
        out += encrypt_helios_input(hash_table, in_data[i * 16:i * 16 + 16])

    out = data[:4] + out
    return base64.b64encode(out).decode()

import base64
import random
import time


def xmxor(data, key):
    data = xmxor_two(data, key)

    last_flag = data[-1] ^ data[-2]
    data0 = data[0]
    data[0] = (~last_flag + data[0]) & 0xff
    data[1] = ((data[0] ^ data[-1] ^ 254) + data[1]) & 0xff
    data[2] = (data[2] + ((last_flag - data0) ^ rl8(data[1], 3) ^ 2)) & 0xff

    for i in range(len(data) - 4):
        temp = (rl8(data[i + 2], 3)) ^ data[i + 1] ^ (i + 3)
        data[i + 3] = (~temp + data[i + 3]) & 0xff

    data[-1] ^= data[-2]

    sum = 0
    for i in range(len(data) - 1):
        sum += int(data[i + 1])

    data[0] = ((data[0] ^ data[1]) + sum) & 0xff
    return data


def xmxor_two(data, key):
    enc_data = bytearray(len(data))
    for i in range(len(data)):
        index = (i * 4) & 28
        d0 = key[index]
        d1 = key[index + 1]

        d2 = (rl8(data[i], 4) + d0) ^ d1
        d2 = ~d2
        d2 = (rl8(d2 & 0xff, 3)) & 0xff
        d2 += d1
        d2 = (d2 & 0xff) ^ d0
        enc_data[-i - 1] = ~d2 & 0xff
    return enc_data

def gen_medusa(url, url_params, devices, data:dict, khronos:int=None, lanusk=None, hash_rand=0, xm_rand=0, dataType=None):
    config = {
        'fix': bytes([0x35]),
        'aes_key': b'\xf1Y3vvn\xa9\x8d4\xf3\x1b\x05z\x9d[\xe4',
        'aes_iv': b'\x1f\xe1\t\xa4\x12R\x83\xf4\x18\xde\x9e\x05\x1a\x96\x9e\x12',
        'signKey': b'\x8e\xbd\xfa8\x06\xec\xc5\xce\xe7\x94#\xe6\x02\x9e\xd8%@\xbc"\x18\xbb~\xae\xf7\x1c\xb6\x91\xf7\xaa\x8a\xa2\xf5',
    }
    data, query_sm3, body_sm3 = gen_medusa_proto(url, url_params, devices, data, khronos, lanusk, dataType)

    hash_rand = hash_rand or int(random.randint(0, 0xFFFFFFFF))
    xm_rand = xm_rand or int(random.randint(0, 0xFFFFFFFF))
    key, seed = get_key_hash(config['signKey'], hash_rand)
    data = xmxor(data, key)
    xg_seed = 320
    data = xg_seed.to_bytes(8, "little") + data
    data = bytearray(data[::-1])
    for i in range(0, len(data)):
        data[i] = data[i] ^ seed[~i & 3]

    hash_rand_bytes = hash_rand.to_bytes(4, "little")
    check_bit = (query_sm3[0] & 63) << 14
    check_bit |= 0x18000001
    check_bit |= (body_sm3[0] & 63) << 8
    data = config['fix'] + xm_rand.to_bytes(4, 'little') + check_bit.to_bytes(4, 'little') + data + hash_rand_bytes[2:]
    data = AES_V3(config['aes_key'], khronos).encrypt(data, config['aes_iv'])
    version_or = bytes()
    version = bytes.fromhex("03 00 00 00 f7 e8 5f fa d7 d7 dc 3b d6 2a c8 70 57 cf 61 18 ")
    for i in range(0, 20, 4):
        d = int.from_bytes(version[i:i + 4], "little")
        d ^= khronos
        version_or += d.to_bytes(4, "little")

    data = version_or + hash_rand_bytes[:2] + int(256).to_bytes(2, "little") + data

    return base64.b64encode(data).decode()

def gen_medusa_proto(url, url_params, devices, data:dict, khronos:int=None, lanusk=None, dataType=None):
    xg_seed = 320
    body_md5 = xssstub_hash_md5_hex(data=data, dataType=dataType).lower() if data else ""
    if body_md5 != '':
        body_md5_bytes = bytes.fromhex(body_md5)
    else:
        body_md5_bytes = bytes(16)
    ts_bytes = khronos.to_bytes(4, "little")
    query_sm3 = SM3(url.split('?')[1]).digest()
    if len(lanusk) > 0:
        lanusk_sm3 = SM3(bytes.fromhex(lanusk) + ts_bytes).digest()
        lanusk_hash = md5sum(
            lanusk_sm3 + body_md5_bytes + bytes.fromhex("84 96 77 9d db 6d bc b6 d4 15 0b f8 80 01 00 00"))

        lanusk_hash = lanusk_hash
        psk_version = "1"
        query_body_hash_sm3 = SM3(url.split('?')[1].encode() + body_md5_bytes + b"1").digest()
    else:
        lanusk_hash = b''
        psk_version = 'none'
        query_body_hash_sm3 = SM3(url.split('?')[1].encode() + body_md5_bytes + b"none").digest()

    proto_data = Medusa(
        magic=bytearray(b'\xf7\xe8_\xfa\xd7\xd7\xdc;\xd6*\xc8pW\xcfa\x18'),
        version=3,
        rand=int(random.randint(0, 0xFFFFFFFF)),
        ms_app_id='8662',
        device_id=str(devices.get("device_id", url_params.get("device_id", url_params.get("did", "")))),
        license_id='1588093228',
        app_version=devices.get("version_name", url_params.get("version_name")),
        sdk_version_str='v04.06.04-ml-android',
        sdk_version=67503104,
        xg_seed_bytes=xg_seed.to_bytes(8, "little"),
        time=khronos,
        query_body_ts_hash=hash_f13(query_sm3, body_md5_bytes, ts_bytes, khronos),
        query_sm3=bytearray(query_sm3[:6]),
        request=MedushaAlgorithmCount(sign_count=111, report_count=10, setting_count=694367, unknown4=0, unknown5=586952199),
        sec_device_token='AXYQOS6n2m60x1fVZHIrH3iol',
        time2=khronos,
        lanusk_hash=lanusk_hash,
        query_body_hash_sm3=query_body_hash_sm3,
        psk_version=psk_version,
        call_type=312,
        env=Env(
            launch_time=random.randint(100, 120),
            unknown2=146331399,
            unknown3=146331396,
            unknown5=7,
            version='v04.06.04.03-bugfix',
            pid=random.randint(10001, 12000),
            device=Device(
                d1=1,
                collect_stat=2,
                aid='8662',
                device_id=str(devices.get("device_id", url_params.get("device_id", url_params.get("did", "")))),
                sec_device_token='Ai6svO3PyrwDOUSmO6ZcResxu',
                app_version='!noperm!',
                battery=-888888,
                battery2=-888888,
                battery_health=3,
                battery_changed=-888888,
                network='!notset!',
                tz='Asia/Shanghai,8',
                lan='zh_CN',
                cpu=4,
                sdcard=255.24993896484375,
                sdcard_used=35.58599090576172,
                memory=3.467449188232422,
                memory2=3.467449188232422,
                data=255.1754913330078,
                data_used=42.17544174194336,
                os_version=devices.get("os_version", url_params.get("os_version")),
                brightness=41,
                volume=36,
                ts=1728388016635,
                ts2=1728388016635,
                ts3=1728388016635,
                ts4=1728388016637,
                usb=-1,
                hw_version=devices.get("device_model", url_params.get("device_type")),
                brand=devices.get("device_brand", url_params.get("device_brand")),
                board=devices.get("device_model", url_params.get("device_type")),
                product_name=devices.get("device_model", url_params.get("device_type")),
                product_device=devices.get("device_manufacturer", devices.get("device_brand", url_params.get("device_brand"))),
                product_manufacturer=devices.get("device_brand", url_params.get("device_brand")),
                hardware=devices.get("device_brand", url_params.get("device_brand")),
                unknown38=31
            ),
            report=Report(
                time=devices.get("report_time", int(time.time())),
                state=-2,
                code=200,
                times=0,
                unknown6=0
            ),
            app_version=devices.get("version_name", url_params.get("version_name"))
        ),
        unknown24='{"cmr":16777216,"cmr2":16777216,"un_h":1879194040,"vpn":0,"kd":0,"fkd":3672518972,"pd":-1872573247,"dyn":"","do":0,"tk":true}'
    )

    return bytes(proto_data), query_sm3, proto_data.query_body_ts_hash


import base64
import json
import random
import time


def lowerHeader(header: dict):
    new_header = {}
    for key, value in header.items():
        new_header[str(key).lower()] = value
    header.clear()
    header.update(new_header)
    return new_header


def core_sixgod(surl, params, devices, data:dict={},  common=None, header=None, lanusk="", log=False, rticket_override=None, ts_override=None, khronos_override=None):
    if devices:
        for k, v in devices.items():
            if k in data:
                data[k] = v
    dataType = header.get("content-type", header.get("Content-Type"))
    xg_rand = int(random.randint(0, 0xFFFF))
    url, url_params, x_common = get_params_encrypturl(surl, params=params, devices=devices, common=common, rticket_override=rticket_override, ts_override=ts_override)

    khronos = khronos_override if khronos_override is not None else int(time.time())
    params = EecryptParams()
    params.khronos = str(khronos)
    params.ladon = base64.b64encode(khronos.to_bytes(4, 'big')).decode()
    params.argus = base64.b64encode(khronos.to_bytes(4, 'little')).decode()
    params.gorgon = encrypt_gorgon(data, url_encode(url_params), khronos, xg_rand, dataType)
    params.helios = encrypt_helios(khronos, rand=0)
    params.medusa = gen_medusa(
        url,
        url_params,
        devices,
        data,
        khronos,
        lanusk,
        dataType=dataType
    )
    six = result(params, data, url,  common=x_common, dataType=dataType, log=log)

    headers = header.copy()
    lowerHeader(header=headers)
    headers.update(six.get("sign_header"))
    if devices:
        headers["x-tt-dt"] = devices.get("x_tt_dt", "")
        headers["user-agent"] = devices.get("ua", "")
    return headers, six.get("sign_url")


def result(params: EecryptParams, data, eurl,  common=None, sell=False, dataType=None, log=False):

    six = {
        'x-ladon': params.ladon,
        'x-khronos': params.khronos,
        'x-argus': params.argus,
        'x-gorgon': params.gorgon,
        'x-helios': params.helios,
        'x-medusa': params.medusa
    }
    if data:
        six["x-ss-stub"] = xssstub_hash_md5_hex(data=data, dataType=dataType)
    if sell:
        datas: dict = dict()
        datas["api"] = eurl
        datas["sign"] = six
        if common:
            datas["sign"]["x-common-params-v2"] = common
        return datas
    datas: dict = dict()
    datas["sign_url"] = eurl
    datas["sign_header"] = six
    if common:
        datas["sign_header"]["x-common-params-v2"] = common
    if log:
        print(json.dumps(datas, indent=4, ensure_ascii=False))
    return datas


USER_AGENT = (
    "com.phoenix.read/71332 (Linux; U; Android 16; zh_CN; 25053RT47C; "
    "Build/BP2A.250605.031.A3; Cronet/TTNetVersion:04657795 2026-01-23 "
    "QuicVersion:c67e9834 2025-09-08)"
)

VIDEO_MODEL_URL_TEMPLATE = (
    "https://api5-normal-sinfonlineb.fqnovel.com/novel/player/multi_video_model/v1/"
    "?iid={install_id}&device_id={device_id}&ac=wifi&channel=update_64&aid=8662"
    "&app_name=novelread&version_code=71332&version_name=7.1.3.32"
    "&device_platform=android&os=android&ssmix=a&device_type=25053RT47C"
    "&device_brand=Redmi&language=zh&os_api=36&os_version=16"
    "&manifest_version_code=71332&resolution=1280*2772&dpi=520"
    "&update_version_code=71332&host_abi=arm64-v8a&dragon_device_type=phone"
    "&pv_player=71332&compliance_status=0&need_personal_recommend=1"
    "&player_so_load=1&is_android_pad_screen=0"
)


def load_local_config() -> Dict[str, Any]:
    return {"device_id": CONFIG_DEVICE_ID, "install_id": CONFIG_INSTALL_ID, "platform": CONFIG_PLATFORM, "cache_seconds": CONFIG_CACHE_SECONDS}


def get_device_keys() -> Dict[str, str]:
    config = load_local_config()

    device_id = str(config.get("device_id") or "").strip()
    install_id = str(config.get("install_id") or "").strip()
    platform = str(config.get("platform") or "android").strip() or "android"

    if not device_id or not install_id:
        raise RuntimeError(
            "Missing device configuration. Set DUANJU_DEVICE_ID / "
            "DUANJU_INSTALL_ID, or open the web UI and save local config."
        )

    return {
        "device_id": device_id,
        "install_id": install_id,
        "platform": platform,
    }

def build_liushen_device(device_keys: Dict[str, str]) -> Dict[str, str]:
    return {
        "device_id": device_keys.get("device_id", ""),
        "iid": device_keys.get("install_id", ""),
        "install_id": device_keys.get("install_id", ""),
        "device_brand": "Redmi",
        "device_model": "25053RT47C",
        "device_type": "25053RT47C",
        "device_manufacturer": "Xiaomi",
        "os_version": "16",
        "version_name": "7.1.3.32",
        "ua": USER_AGENT,
    }


def _compute_branch(query_string, body_bytes, khronos):
    query_sm3 = SM3(query_string).digest()
    body_md5 = hashlib.md5(body_bytes).digest() if body_bytes else bytes(16)
    ts_bytes = khronos.to_bytes(4, "little")
    iv = get_iv(0x20230928, query_sm3)
    iv = get_iv(iv, body_md5)
    iv = get_iv(iv, ts_bytes)
    low = iv & 15
    iv_v0 = (low * 171) >> 9
    return low - (iv_v0 * 3)


def sign_json_request_with_liushen(
    url: str,
    body_obj: Dict[str, Any],
    device_keys: Dict[str, str],
) -> Tuple[str, Dict[str, str], bytes]:
    body_text = json.dumps(body_obj, ensure_ascii=False, separators=(",", ":"))
    body_data = json.loads(body_text)
    body_bytes = body_text.encode("utf-8")

    ts = str(int(time.time() * 1000))
    base_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json; charset=utf-8,application/x-protobuf",
        "Content-Type": "application/json; charset=UTF-8",
        "x-xs-from-web": "0",
        "x-ss-req-ticket": ts,
        "x-tt-request-tag": "t=0;n=0",
        "sdk-version": "2",
        "passport-sdk-version": "50561",
        "x-vc-bdturing-sdk-version": "3.7.2.cn",
    }

    url_parts = urlsplit(url)
    base_url = f"{url_parts.scheme}://{url_parts.netloc}{url_parts.path}"
    params = dict(parse_qsl(url_parts.query, keep_blank_values=True))
    devices = build_liushen_device(device_keys)

    khronos = int(time.time())
    base_rticket = int(time.time() * 1000)
    safe_rticket = base_rticket
    safe_khronos = khronos

    for offset in range(32):
        rticket = base_rticket + offset
        eurl, _, _ = get_params_encrypturl(
            base_url, params=params, devices=devices,
            rticket_override=rticket, ts_override=khronos,
        )
        query_string = eurl.split("?", 1)[1] if "?" in eurl else ""
        branch = _compute_branch(query_string, body_bytes, khronos)
        if branch != 1:
            safe_rticket = rticket
            safe_khronos = khronos
            break

    sign_headers, sign_url = core_sixgod(
        surl=base_url,
        params=params,
        data=body_data,
        devices=devices,
        header=base_headers,
        log=False,
        rticket_override=safe_rticket,
        ts_override=safe_khronos,
        khronos_override=safe_khronos,
    )
    return sign_url, sign_headers, body_bytes


def _quality_number(value: str) -> int:
    text = str(value or "")
    m = re.match(r".*?(2160|1440|1080|720|576|540|480|360)", text)
    if m:
        return int(m.group(1))
    mapping = {"1920": 1080, "1280": 720, "1024": 576, "854": 480, "640": 360}
    if text in mapping:
        return mapping[text]
    if re.match(r"^\d{3,4}$", text):
        return int(text)
    return 0


def _quality_label(value: str) -> str:
    n = _quality_number(value)
    if n:
        return "%dP" % n
    labels = {
        "low": "\u6d41\u7545",
        "smooth": "\u6d41\u7545",
        "medium": "\u6807\u6e05",
        "normal": "\u9ad8\u6e05",
        "high": "\u8d85\u6e05",
        "original": "\u539f\u753b",
        "uhd": "\u539f\u753b",
        "super_high": "\u539f\u753b",
    }
    return labels.get(str(value or "").lower(), str(value or "\u81ea\u52a8"))


def _quality_rows(video_list: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not video_list or not isinstance(video_list, dict):
        return rows
    for key, value in video_list.items():
        item = value if isinstance(value, dict) else {}
        quality = str(
            item.get("quality_desc")
            or item.get("height")
            or item.get("vheight")
            or item.get("quality")
            or key
        )
        if item.get("main_url") and not any(
            r["key"] == key for r in rows
        ):
            rows.append({"key": key, "quality": quality, "item": item})
    rows.sort(
        key=lambda r: _quality_number(r["quality"] or r["key"]),
        reverse=True,
    )
    return rows


def fetch_quality_rows(vid: str) -> List[Dict[str, Any]]:
    cache_key = str(vid)
    cached = _quality_cache.get(cache_key)
    if cached and time.time() - cached[0] < 300:
        return cached[1]

    rows: List[Dict[str, Any]] = []
    try:
        device_keys = get_device_keys()
        target_url = build_video_model_url(
            device_keys["device_id"], device_keys["install_id"]
        )
        post_payload = {
            "biz_param": {
                "detail_page_version": 0,
                "device_level": 3,
                "disable_digg_stat": False,
                "need_all_video_definition": True,
                "need_mp4_align": False,
                "use_os_player": False,
                "use_server_dns": False,
                "video_platform": 1024,
            },
            "mixed_video_id_map": {"1004": [str(vid)]},
        }
        signed_url, headers, post_body = sign_json_request_with_liushen(
            target_url, post_payload, device_keys
        )
        resp = curl_request(signed_url, headers, post_body, 20)
        data = json.loads(resp)
        fallback_api, video_model = extract_fallback_api(data, str(vid))

        resp2 = curl_request(fallback_api, {"User-Agent": USER_AGENT}, None, 20)
        outer = json.loads(resp2)
        video_data = outer.get("video_info", {}).get("data", {})
        if not isinstance(video_data, dict):
            video_data = {}
        video_list = video_data.get("video_list", {})
        if isinstance(video_list, dict):
            rows = _quality_rows(video_list)
    except Exception:
        pass

    _quality_cache[cache_key] = (time.time(), rows)
    return rows


_quality_cache: Dict[str, Tuple[float, List]] = {}


def replace_failed_device(device_id: str, platform: str) -> None:
    pass


def get_current_domain(request=None) -> str:
    return _CURRENT_DOMAIN


_RUNTIME_BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__))) if "__file__" in dir() else Path.cwd()

def get_runtime_base_dir() -> Path:
    return _RUNTIME_BASE_DIR


DEFAULT_TIMEOUT = 30
VIDEO_WORKER_POOL = ThreadPoolExecutor(max_workers=4)
FFMPEG_BIN = "ffmpeg"
VIDEO_TTL_SECONDS = 300


def schedule_video_cleanup(filepath: Path, delay_seconds: int = VIDEO_TTL_SECONDS) -> None:

    def _delete_file() -> None:
        try:
            filepath.unlink(missing_ok=True)
            print(f"[cleanup] deleted_expired_video={filepath.name}")
        except Exception as exc:
            print(f"[cleanup] delete_failed file={filepath.name} error={exc}")

    timer = threading.Timer(delay_seconds, _delete_file)
    timer.daemon = True
    timer.start()


def curl_request(
    url: str,
    headers: Dict[str, str],
    post_body: Optional[bytes] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> bytes:
    session = requests.Session()
    session.trust_env = False
    if post_body is not None:
        resp = session.post(url, headers=headers, data=post_body, timeout=timeout)
    else:
        resp = session.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def handle_video_request(
    video_id: str,
    request=None,
    max_retries: int = 3,
    stream_mode: bool = False,
    quality_key: Optional[str] = None,
) -> Dict[str, Any]:
    return resolve_video_url(
        video_id, request, max_retries,
        stream_mode=stream_mode, quality_key=quality_key,
    )


def resolve_video_url(
    video_id: str,
    request=None,
    max_retries: int = 3,
    stream_mode: bool = False,
    quality_key: Optional[str] = None,
) -> Dict[str, Any]:
    last_err: Optional[Exception] = None

    for attempt in range(max_retries):
        device_keys = get_device_keys()
        target_url = build_video_model_url(
            device_keys["device_id"], device_keys["install_id"]
        )

        post_payload = {
            "biz_param": {
                "detail_page_version": 0,
                "device_level": 3,
                "disable_digg_stat": False,
                "need_all_video_definition": True,
                "need_mp4_align": False,
                "use_os_player": False,
                "use_server_dns": False,
                "video_platform": 1024,
            },
            "mixed_video_id_map": {
                "1004": [video_id],
            },
        }
        signed_url, headers, post_body = sign_json_request_with_liushen(
            target_url, post_payload, device_keys
        )

        try:
            resp = curl_request(signed_url, headers, post_body, 30)
        except Exception as exc:
            last_err = Exception(f"video_model request failed: {exc}")
            time.sleep(0.1)
            continue

        try:
            data = json.loads(resp)
        except Exception as exc:
            last_err = Exception(f"video_model JSON parse failed: {exc}")
            continue

        if not isinstance(data, dict) or "data" not in data:
            print("video_model raw response:")
            print(json.dumps(data, ensure_ascii=False, indent=2))

        try:
            fallback_api, video_model = extract_fallback_api(data, video_id)
        except Exception as exc:
            last_err = exc
            continue

        try:
            result = download_and_decrypt_video(
                request,
                fallback_api,
                video_model,
                device_keys,
                video_id,
                max_retries=3,
                stream_mode=stream_mode,
                quality_key=quality_key,
            )
            return result
        except Exception as exc:
            last_err = exc
            time.sleep(0.1)
            continue

    raise Exception(f"Video request failed, retried {max_retries} times: {last_err}")


def build_video_model_url(device_id: str, install_id: str) -> str:
    from urllib.parse import quote

    return VIDEO_MODEL_URL_TEMPLATE.format(
        install_id=quote(install_id, safe=""),
        device_id=quote(device_id, safe=""),
    )


def extract_fallback_api(
    data: Dict[str, Any], video_id: str
) -> Tuple[str, Dict[str, Any]]:
    data_map = data.get("data")
    if not isinstance(data_map, dict):
        raise ValueError("Response missing data field")

    video_entry: Optional[Dict[str, Any]] = None

    if video_id in data_map and isinstance(data_map[video_id], dict):
        video_entry = data_map[video_id]

    if video_entry is None:
        for v in data_map.values():
            if isinstance(v, dict):
                video_entry = v
                break
            if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                video_entry = v[0]
                break

    if video_entry is None:
        keys = list(data_map.keys())
        raise ValueError(
            f"video entry not found (looked for {video_id}, available keys: {keys})"
        )

    video_model: Optional[Dict[str, Any]] = None
    vm = video_entry.get("video_model")
    if isinstance(vm, str):
        video_model = json.loads(vm)
    elif isinstance(vm, dict):
        video_model = vm
    else:
        raise ValueError("video_model is empty or unknown format")

    fallback_raw = video_model.get("fallback_api")
    fallback_str = parse_fallback_api(fallback_raw)
    if not fallback_str:
        raise ValueError(f"fallback_api cannot be parsed: {type(fallback_raw)} => {fallback_raw}")

    return fallback_str, video_model


def parse_fallback_api(raw: Any) -> str:
    if isinstance(raw, str):
        if raw.startswith("{"):
            try:
                decoded = json.loads(raw)
                if isinstance(decoded, dict) and "fallback_api" in decoded:
                    return str(decoded["fallback_api"])
            except (json.JSONDecodeError, TypeError):
                pass
        if len(raw) > 10:
            return raw
    elif isinstance(raw, list) and len(raw) > 0:
        if isinstance(raw[0], str):
            return raw[0]
    elif isinstance(raw, dict):
        if "fallback_api" in raw:
            return str(raw["fallback_api"])
    return ""


def download_and_decrypt_video(
    request,
    fallback_api: str,
    video_model: Dict[str, Any],
    device_keys: Dict[str, str],
    video_id: str,
    max_retries: int = 3,
    stream_mode: bool = False,
    quality_key: Optional[str] = None,
) -> Dict[str, Any]:
    current_url = fallback_api
    current_device_keys = device_keys
    last_err: Optional[Exception] = None

    for attempt in range(max_retries):
        headers = {"User-Agent": USER_AGENT}

        try:
            resp = curl_request(current_url, headers, None, 30)
        except Exception as exc:
            last_err = Exception(f"fallback_api request failed: {exc}")
        else:
            try:
                data = json.loads(resp)
            except Exception as exc:
                last_err = Exception(f"fallback_api JSON parse failed: {exc}")
            else:
                video_info = data.get("video_info", {})
                if not isinstance(video_info, dict):
                    video_info = {}
                video_data = video_info.get("data", {})
                if not isinstance(video_data, dict):
                    video_data = {}

                if not video_data:
                    last_err = Exception("fallback_api response structure abnormal")
                else:
                    key_seed_b64 = video_data.get("key_seed", "")
                    key_seed_raw = b64_decode_padded(key_seed_b64)

                    video_list = video_data.get("video_list", {})
                    if isinstance(video_list, dict):
                        best_key, best_item = select_best_quality(video_list, preferred_key=quality_key)
                        if best_key and best_item:
                            spade_a = best_item.get("spade_a", "")
                            content_key = None
                            if spade_a:
                                try:
                                    content_key = derive_content_key(spade_a)
                                except Exception:
                                    pass

                            raw_main_url = best_item.get("main_url", "")
                            if raw_main_url:
                                real_main_url = raw_main_url
                                if key_seed_raw and len(raw_main_url) > 10:
                                    try:
                                        dec = decrypt_spade_url(raw_main_url, key_seed_raw)
                                        if dec:
                                            real_main_url = dec
                                    except Exception as exc:
                                        print(f"[debug] spade_url_decrypt_failed={exc}")

                                backup_urls = []
                                for bk_key in ("backup_url_1", "backup_url_2", "url", "play_addr"):
                                    bk_raw = best_item.get(bk_key, "")
                                    if not bk_raw or not isinstance(bk_raw, str):
                                        continue
                                    bk_real = bk_raw
                                    if key_seed_raw and len(bk_raw) > 10:
                                        try:
                                            bk_dec = decrypt_spade_url(bk_raw, key_seed_raw)
                                            if bk_dec:
                                                bk_real = bk_dec
                                        except Exception:
                                            pass
                                    if bk_real and bk_real != real_main_url:
                                        backup_urls.append(bk_real)

                                if stream_mode:
                                    stream_url = build_stream_url(
                                        request, real_main_url, content_key, backup_urls)
                                    if stream_url:
                                        best_item["main_url"] = stream_url
                                else:
                                    local_url = download_decrypt_and_serve(
                                        request, real_main_url, content_key, backup_urls)
                                    if local_url:
                                        best_item["main_url"] = local_url

                            video_data["video_list"] = {best_key: best_item}

                    video_info["data"] = video_data
                    data["video_info"] = video_info
                    return build_response_payload(video_id, video_model, video_data, best_item)

        if attempt < max_retries - 1 and video_id:
            if current_device_keys:
                replace_failed_device(
                    current_device_keys.get("device_id", ""),
                    current_device_keys.get("platform", ""),
                )
            try:
                new_url, new_keys = refresh_fallback_url(video_id)
                if new_url:
                    current_url = new_url
                    current_device_keys = new_keys
            except Exception:
                pass

    raise Exception(
        f"fallback_api request failed, retried {max_retries} times: {last_err}"
    )


def download_decrypt_and_serve(
    request,
    video_url: str,
    content_key: Optional[bytes],
    backup_urls=None,
) -> Optional[str]:
    pipeline_start = time.perf_counter()
    encrypted_data = download_video_bytes(video_url, backup_urls)
    decrypted_data = decrypt_video_bytes(encrypted_data, content_key)
    local_url = save_video_bytes(request, decrypted_data)
    pipeline_seconds = time.perf_counter() - pipeline_start
    print(f"[timing] video_pipeline_seconds={pipeline_seconds:.3f}")
    return local_url


def download_video_bytes(video_url: str, backup_urls=None) -> bytes:
    download_start = time.perf_counter()
    session = requests.Session()
    session.trust_env = False
    dl_headers = {
        "User-Agent": "com.phoenix.read/71332",
        "Referer": "https://novel.snssdk.com/",
    }
    candidate_urls = [video_url] + (backup_urls or [])
    last_exc = None
    for url in candidate_urls:
        try:
            resp = session.get(url, headers=dl_headers, timeout=(8, 120))
            resp.raise_for_status()
            download_seconds = time.perf_counter() - download_start
            print(f"[timing] download_seconds={download_seconds:.3f}")
            return resp.content
        except Exception as exc:
            print(f"[download] cdn_failed url={url[:80]} error={exc}")
            last_exc = exc
            continue
    raise Exception(f"Failed to download video: all CDN nodes failed: {last_exc}")


def decrypt_video_bytes(encrypted_data: bytes, content_key: Optional[bytes]) -> bytes:
    if content_key is None:
        print("[timing] decrypt_seconds=0.000 content_key_missing=true")
        return encrypted_data

    decrypt_start = time.perf_counter()
    try:
        decrypted_data = decrypt_mp4_cenc(encrypted_data, content_key)
        decrypt_seconds = time.perf_counter() - decrypt_start
        print(f"[timing] decrypt_seconds={decrypt_seconds:.3f}")
        return decrypted_data
    except Exception as exc:
        raise Exception(f"Failed to decrypt video: {exc}")


def save_video_bytes(request, decrypted_data: bytes) -> str:
    save_start = time.perf_counter()
    src_dir = get_runtime_base_dir() / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    filename = f"video_{time.time_ns()}.mp4"
    filepath = src_dir / filename
    filepath.write_bytes(decrypted_data)
    schedule_video_cleanup(filepath)

    current_domain = get_current_domain(request)
    save_seconds = time.perf_counter() - save_start
    print(f"[timing] save_seconds={save_seconds:.3f}")
    return f"{current_domain}/src/{filename}"


def build_stream_url(request, encrypted_url: str, content_key: Optional[bytes],
                     backup_urls=None) -> str:
    current_domain = get_current_domain(request)
    key_b64 = base64.b64encode(content_key).decode('ascii') if content_key else ''
    params_list = [('url', encrypted_url), ('key', key_b64)]
    for bk in (backup_urls or []):
        params_list.append(('bk', bk))
    params = urlencode(params_list)
    return f"{current_domain}/stream?{params}"


def stream_cenc_decrypt_chunk(chunk: bytearray, chunk_start: int,
                              decrypt_map: Dict[int, Tuple[int, bytes]],
                              content_key: bytes) -> bytes:
    chunk_end = chunk_start + len(chunk)

    for sample_off in list(decrypt_map.keys()):
        sample_sz, iv = decrypt_map[sample_off]
        sample_end = sample_off + sample_sz

        if sample_off >= chunk_end or sample_end <= chunk_start:
            continue

        overlap_start = max(sample_off, chunk_start)
        overlap_end = min(sample_end, chunk_end)
        overlap_size = overlap_end - overlap_start
        offset_in_sample = overlap_start - sample_off

        start_block = offset_in_sample // 16
        ctr_int = int.from_bytes(bytes(iv) + b'\x00' * 8, 'big') + start_block
        ctr_bytes = ctr_int.to_bytes(16, 'big')

        cipher = AES.new(content_key, AES.MODE_CTR, nonce=b"", initial_value=ctr_bytes)

        block_offset = offset_in_sample % 16
        if block_offset > 0:
            cipher.decrypt(b'\x00' * block_offset)

        start_in_chunk = overlap_start - chunk_start
        decrypted = cipher.decrypt(bytes(chunk[start_in_chunk:start_in_chunk + overlap_size]))
        chunk[start_in_chunk:start_in_chunk + overlap_size] = decrypted

    return bytes(chunk)


def refresh_fallback_url(video_id: str) -> Tuple[str, Dict[str, str]]:
    device_keys = get_device_keys()
    target_url = build_video_model_url(
        device_keys["device_id"], device_keys["install_id"]
    )

    post_payload = {
        "biz_param": {
            "detail_page_version": 0,
            "device_level": 3,
            "disable_digg_stat": False,
            "need_all_video_definition": True,
            "need_mp4_align": False,
            "use_os_player": False,
            "use_server_dns": False,
            "video_platform": 1024,
        },
        "mixed_video_id_map": {"1004": [video_id]},
    }
    signed_url, headers, post_body = sign_json_request_with_liushen(
        target_url, post_payload, device_keys
    )

    resp = curl_request(signed_url, headers, post_body, 30)
    data = json.loads(resp)

    fallback_api, _ = extract_fallback_api(data, video_id)
    return fallback_api, device_keys


def derive_content_key(spade_b64: str) -> bytes:
    s = spade_b64.strip()
    m = 4 - len(s) % 4
    if m != 4:
        s += "=" * m

    raw = base64.b64decode(s)

    if len(raw) < 3:
        raise ValueError(f"spade_a too short: {len(raw)} bytes")

    v6 = raw[0] ^ raw[1] ^ raw[2]
    v8 = len(raw) - v6 + 47

    if v8 <= 0 or v8 > len(raw) * 2:
        raise ValueError(f"spade_a: computed v8={v8} out of range")
    if 1 + v8 > len(raw):
        v8 = len(raw) - 1
    if v8 < 33:
        raise ValueError(f"spade_a: v8={v8} too small (need >=33)")

    v13 = bytearray(raw[1 : 1 + v8])

    vA, vB = 85, 246
    for i in range(v8):
        popcnt = bin(i).count("1")
        if i & 1:
            v24 = vA
            vA = v13[i]
        else:
            v24 = vB
            vB = v13[i]
        v25 = v24 ^ v13[i]
        v26 = -21 - popcnt
        v13[i] = (v26 + v25) & 0xFF

    hex_str = bytes(v13[1:33]).decode("ascii")
    key = binascii.unhexlify(hex_str)
    return key


def decrypt_mp4_cenc(data: bytes, content_key: bytes) -> bytes:
    data = bytearray(data)

    ftyp_end = struct.unpack(">I", data[0:4])[0]
    if ftyp_end + 8 >= len(data):
        raise ValueError("invalid MP4: ftyp too large")

    moov_size = struct.unpack(">I", data[ftyp_end : ftyp_end + 4])[0]
    if ftyp_end + 8 + moov_size > len(data):
        raise ValueError("invalid MP4: moov out of range")
    moov = data[ftyp_end + 8 : ftyp_end + moov_size]

    t1_off, t1_sz = find_box(moov, "trak", 0)
    t2_off, _ = find_box(moov, "trak", t1_off + t1_sz)

    for t_off in (t1_off, t2_off):
        if t_off < 0:
            continue
        result = parse_track(moov, t_off)
        if result is None:
            continue
        sizes, offsets, cns, aux_off, aux_sz, ns = result
        if ns == 0:
            continue
        if aux_off + aux_sz > len(data):
            continue
        aux = data[aux_off : aux_off + aux_sz]

        si, ap = 0, 0
        for ci, off in enumerate(offsets):
            for k in range(cns[ci]):
                if si >= ns:
                    break
                sz = sizes[si]
                if off + sz > len(data):
                    break

                iv = bytearray(8)
                if ap + 8 <= len(aux):
                    iv[:] = aux[ap : ap + 8]
                ctr_bytes = bytes(iv) + b"\x00" * 8

                cipher = AES.new(content_key, AES.MODE_CTR, nonce=b"", initial_value=ctr_bytes)
                decrypted = cipher.decrypt(bytes(data[off : off + sz]))
                data[off : off + sz] = decrypted

                off += sz
                si += 1
                ap += 8

    for old, new in ((b"encv", b"hvc1"), (b"enca", b"mp4a")):
        _replace_fourcc(data, old, new)

    _replace_sinf(data)

    return bytes(data)


def find_box(data: bytearray, fourcc: str, start: int) -> Tuple[int, int]:
    b = fourcc.encode("ascii")
    for i in range(start, len(data) - 8):
        if data[i : i + 4] == b and i >= 4:
            sz = struct.unpack(">I", data[i - 4 : i])[0]
            if 0 < sz < 5000000:
                return i - 4, sz
    return -1, 0


def get_box(data: bytearray, fourcc: str, stbl_off: int):
    o, sz = find_box(data, fourcc, stbl_off)
    if o >= 0:
        return data[o + 8 : o + sz]
    return None


def parse_track(
    moov: bytearray, t_off: int
) -> Optional[Tuple[List[int], List[int], List[int], int, int, int]]:
    stbl_off, _ = find_box(moov, "stbl", t_off + 8)

    stsz = get_box(moov, "stsz", stbl_off)
    if stsz is None:
        return None
    ds = struct.unpack(">I", stsz[4:8])[0]
    ns = struct.unpack(">I", stsz[8:12])[0]
    sizes: List[int] = []
    if ds == 0:
        for i in range(ns):
            sizes.append(struct.unpack(">I", stsz[12 + i * 4 : 16 + i * 4])[0])
    else:
        sizes = [ds] * ns

    stco = get_box(moov, "stco", stbl_off)
    if stco is None:
        return None
    nc = struct.unpack(">I", stco[4:8])[0]
    offsets = []
    for i in range(nc):
        offsets.append(struct.unpack(">I", stco[8 + i * 4 : 12 + i * 4])[0])

    stsc = get_box(moov, "stsc", stbl_off)
    if stsc is None:
        return None
    nsc = struct.unpack(">I", stsc[4:8])[0]
    entries = []
    for i in range(nsc):
        entries.append((
            struct.unpack(">I", stsc[8 + i * 12 : 12 + i * 12])[0],
            struct.unpack(">I", stsc[12 + i * 12 : 16 + i * 12])[0],
            struct.unpack(">I", stsc[16 + i * 12 : 20 + i * 12])[0],
        ))

    cns = [0] * nc
    for i in range(nsc):
        fc = entries[i][0]
        spc = entries[i][1]
        end = nc
        if i + 1 < nsc:
            end = entries[i + 1][0] - 1
        for c in range(fc - 1, min(end, nc)):
            cns[c] = spc

    saiz = get_box(moov, "saiz", stbl_off)
    if saiz is None:
        return None
    da = saiz[4]
    na = struct.unpack(">I", saiz[5:9])[0]

    saio = get_box(moov, "saio", stbl_off)
    if saio is None:
        return None
    aux_off = struct.unpack(">I", saio[8:12])[0]
    aux_sz = na * max(da, 8)

    return sizes, offsets, cns, aux_off, aux_sz, ns


def select_best_quality(
    video_list: Dict[str, Any], preferred_key: Optional[str] = None
) -> Tuple[str, Dict[str, Any]]:
    if preferred_key and preferred_key in video_list and isinstance(
        video_list[preferred_key], dict
    ):
        return preferred_key, video_list[preferred_key]
    best_key = ""
    best_item: Dict[str, Any] = {}
    best_height = 0
    for k, item in video_list.items():
        if not isinstance(item, dict):
            continue
        h = int(item.get("vheight", 0))
        if h > best_height:
            best_height = h
            best_key = k
            best_item = item
        elif h == best_height and best_item:
            cur_br = int(item.get("bitrate", 0))
            best_br = int(best_item.get("bitrate", 0))
            if cur_br > best_br:
                best_key = k
                best_item = item
    return best_key, best_item


def build_response_payload(
    video_id: str,
    video_model: Dict[str, Any],
    video_data: Dict[str, Any],
    best_item: Dict[str, Any],
) -> Dict[str, Any]:
    pic = first_non_empty(
        best_item.get("cover"),
        best_item.get("poster"),
        video_model.get("origin_cover"),
        video_model.get("cover_url"),
        video_model.get("dynamic_cover"),
        video_model.get("cover"),
        video_data.get("cover"),
        video_data.get("poster"),
    )
    url = first_non_empty(
        best_item.get("main_url"),
        best_item.get("play_addr"),
        best_item.get("backup_url_1"),
        best_item.get("url"),
    )
    height = stringify_int(first_non_empty(best_item.get("vheight"), best_item.get("height")))
    width = stringify_int(first_non_empty(best_item.get("vwidth"), best_item.get("width")))

    return {
        "vid": video_id,
        "pic": normalize_media_url(pic),
        "url": normalize_media_url(url),
        "quality": format_quality(best_item, height),
        "duration": format_duration(first_non_empty(video_model.get("duration"), video_data.get("duration"))),
        "size": format_size(first_non_empty(best_item.get("size"), best_item.get("data_size"), best_item.get("file_size"))),
        "height": height,
        "width": width,
        "create_time": format_create_time(
            first_non_empty(
                video_model.get("create_time"),
                video_model.get("publish_time"),
                video_data.get("create_time"),
                video_data.get("publish_time"),
            )
        ),
    }


def first_non_empty(*values: Any) -> str:
    for value in values:
        normalized = unwrap_media_value(value)
        if normalized:
            return normalized
    return ""


def unwrap_media_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        for item in value:
            normalized = unwrap_media_value(item)
            if normalized:
                return normalized
        return ""
    if isinstance(value, dict):
        for key in ("url", "uri", "src", "download_url"):
            normalized = unwrap_media_value(value.get(key))
            if normalized:
                return normalized
        for key in ("url_list", "urls"):
            normalized = unwrap_media_value(value.get(key))
            if normalized:
                return normalized
    return ""


def normalize_media_url(value: str) -> str:
    if value.startswith("//"):
        return f"https:{value}"
    return value


def stringify_int(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return str(value)


def format_quality(best_item: Dict[str, Any], height: str) -> str:
    label = first_non_empty(
        best_item.get("quality"),
        best_item.get("definition"),
        best_item.get("gear_name"),
        best_item.get("quality_desc"),
    )
    if label:
        return label
    if height:
        return f"{height}p"
    return ""


def format_duration(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        total_seconds = int(float(value))
    except (TypeError, ValueError):
        return str(value)

    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}小时{minutes}分钟{seconds}秒"
    return f"{minutes}分钟{seconds}秒"


def format_size(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        size_bytes = float(value)
    except (TypeError, ValueError):
        return str(value)

    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    while size_bytes >= 1024 and unit_index < len(units) - 1:
        size_bytes /= 1024
        unit_index += 1
    return f"{size_bytes:.2f}{units[unit_index]}"


def format_create_time(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        if text.endswith("Z"):
            return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(
                timezone(timedelta(hours=8))
            ).isoformat()
        try:
            numeric = float(text)
        except ValueError:
            return text
        value = numeric

    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 1e12:
            timestamp /= 1000
        dt = datetime.fromtimestamp(timestamp, tz=timezone(timedelta(hours=8)))
        return dt.isoformat()
    return str(value)


def decrypt_spade_url(b64_str: str, key_seed: bytes) -> str:
    if not b64_str:
        return ""

    raw = b64_decode_padded(b64_str)
    if len(raw) < 5:
        raise ValueError("Ciphertext too short")
    if raw[0] != 0xA8 or raw[2] != 0x01 or raw[3] != 0x00:
        raise ValueError("Ciphertext header format error")

    cipher_data = raw[4:]
    cipher_len = (len(cipher_data) // 16) * 16
    cipher_data = cipher_data[:cipher_len]

    constants = bytes([
        0x4D, 0xD4, 0xC2, 0xE6, 0xB8, 0x31, 0x62, 0x09, 0x0E, 0x52, 0xB3, 0xC7, 0xA6, 0x73, 0x3B, 0xA4,
        0x1C, 0xB2, 0x46, 0x2B, 0x82, 0x9A, 0xB5, 0x8A, 0x19, 0x6B, 0x39, 0xDB, 0x57, 0x17, 0x75, 0x24,
        0xF4, 0x9B, 0xAF, 0x7F, 0x08, 0xE8, 0xD6, 0x8D, 0x26, 0xA7, 0x2E, 0x37, 0xC1, 0xA9, 0x5A, 0x2F,
        0x1F, 0x05, 0xA5, 0x18, 0x92, 0xAE, 0xF2, 0x94, 0x97, 0x32, 0xB6, 0x2A, 0x38, 0xAA, 0xDD, 0x58,
    ])

    h1 = hashlib.sha512(key_seed).digest()
    h2 = hashlib.sha512(h1 + constants).digest()
    aes_key = h2[:16]
    iv = h2[16:32]

    cipher = AES.new(aes_key, AES.MODE_CBC, iv=iv)
    plaintext = cipher.decrypt(cipher_data)

    if plaintext:
        pad = plaintext[-1]
        if 1 <= pad <= 16 and pad <= len(plaintext):
            plaintext = plaintext[:-pad]

    return plaintext.rstrip(b"\x00").decode("utf-8", errors="replace")


def b64_decode_padded(s: str) -> bytes:
    s = s.strip()
    pad = len(s) % 4
    if pad:
        s += "=" * (4 - pad)
    try:
        return base64.b64decode(s)
    except Exception:
        return base64.urlsafe_b64decode(s)


def _replace_fourcc(data: bytearray, old: bytes, new: bytes) -> None:
    old_len = len(old)
    for i in range(len(data) - old_len):
        if data[i : i + old_len] == old:
            data[i : i + len(new)] = new


def _replace_sinf(data: bytearray) -> None:
    i = 0
    while i < len(data) - 4:
        if data[i : i + 4] == b"sinf":
            if i >= 4:
                sz = struct.unpack(">I", data[i - 4 : i])[0]
                if 0 < sz < 50000:
                    data[i : i + 4] = b"free"
                    end = min(i - 4 + sz, len(data))
                    for j in range(i + 4, end):
                        data[j] = 0
                    i = end
                    continue
        i += 1


class _PlayHandler(BaseHTTPRequestHandler):
    parser = None
    src_dir = None
    base_url = ''
    _resolve_cache = {}
    _vid_locks = {}
    _guard = threading.Lock()
    _download_locks = {}
    _download_guard = threading.Lock()
    _RESOLVE_TTL = 300

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        if path == '/play':
            self._handle_play(params)
        elif path == '/stream':
            self._handle_stream(params)
        elif path.startswith('/src/'):
            self._handle_src(path[5:])
        elif path == '/health':
            self._handle_health()
        else:
            self.send_error(404)

    def do_HEAD(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == '/stream':
            params = parse_qs(parsed.query)
            self._handle_stream(params, head_only=True)
        elif path.startswith('/src/'):
            self._handle_src(path[5:], head_only=True)
        else:
            self.send_error(404)

    def _handle_play(self, params):
        vid = params.get('vid', [''])[0].strip()
        if not vid.isdigit():
            self._json(400, {'error': 'vid invalid'})
            return
        try:
            result = self._resolve_cached(vid)
            media_url = str(result.get('url') or '')
            if not media_url:
                self._json(502, {'error': 'no media url'})
                return
            self.send_response(302)
            self.send_header('Location', media_url)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
        except Exception as exc:
            self._json(502, {'error': str(exc)})

    def _resolve_cached(self, vid):
        with self._guard:
            if vid not in self._vid_locks:
                self._vid_locks[vid] = threading.Lock()
            if len(self._resolve_cache) > 1000:
                now = time.time()
                for k in [k for k, v in self._resolve_cache.items()
                          if now - v[0] > self._RESOLVE_TTL]:
                    self._resolve_cache.pop(k, None)
        lock = self._vid_locks[vid]
        with lock:
            hit = self._resolve_cache.get(vid)
            if hit and time.time() - hit[0] < self._RESOLVE_TTL:
                return hit[1]
            result = handle_video_request(vid, None, max_retries=3, stream_mode=True)
            self._resolve_cache[vid] = (time.time(), result)
            return result

    def _handle_src(self, filename, head_only=False):
        if not self.src_dir:
            self.send_error(503, 'src_dir not configured')
            return
        safe_name = Path(filename).name
        filepath = self.src_dir / safe_name
        if not filepath.exists() or not filepath.is_file():
            self.send_error(404)
            return
        file_size = filepath.stat().st_size
        range_header = self.headers.get('Range', '')
        start = 0
        end = file_size - 1
        is_partial = False
        if range_header:
            m = re.match(r'bytes=(\d+)-(\d*)', range_header)
            if m:
                start = int(m.group(1))
                if m.group(2):
                    end = int(m.group(2))
                is_partial = True
        if start > end or start >= file_size:
            self.send_error(416)
            return
        content_length = end - start + 1
        if is_partial:
            self.send_response(206)
            self.send_header('Content-Range',
                             'bytes %d-%d/%d' % (start, end, file_size))
        else:
            self.send_response(200)
        self.send_header('Content-Type', 'video/mp4')
        self.send_header('Content-Length', str(content_length))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Expose-Headers',
                         'Content-Length, Content-Range, Accept-Ranges')
        self.end_headers()
        if head_only:
            return
        with open(filepath, 'rb') as f:
            f.seek(start)
            remaining = content_length
            while remaining > 0:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _handle_health(self):
        self._json(200, {
            'ok': True,
            'service': 'hongguo-embedded',
            'parser': self.parser is not None,
            'src_dir': str(self.src_dir) if self.src_dir else '',
        })

    def _handle_stream(self, params, head_only=False):
        raw_url = params.get('url', [''])[0]
        key_b64 = params.get('key', [''])[0]
        if not raw_url:
            self.send_error(400, 'missing url param')
            return

        backup_urls = [u for u in params.get('bk', []) if u]
        candidate_urls = [raw_url] + backup_urls

        try:
            content_key = base64.b64decode(key_b64) if key_b64 else None
        except Exception:
            content_key = None

        if content_key is not None:
            url_hash = hashlib.md5(raw_url.encode()).hexdigest()[:16]
            filename = 'video_%s.mp4' % url_hash
            if not self.src_dir:
                self.send_error(503, 'src_dir not configured')
                return
            filepath = self.src_dir / filename

            if filepath.exists() and filepath.is_file():
                self._handle_src(filename, head_only)
                return

            range_header = self.headers.get('Range', '')
            is_full = (not range_header
                       or re.match(r'bytes=0-\s*$', range_header) is not None)

            if is_full and not head_only:
                try:
                    with self._download_guard:
                        if filename not in self._download_locks:
                            self._download_locks[filename] = threading.Lock()
                        s_lock = self._download_locks[filename]
                    if s_lock.acquire(blocking=False):
                        try:
                            if filepath.exists() and filepath.is_file():
                                self._handle_src(filename, head_only)
                                return
                            self._stream_cenc_direct(
                                raw_url, backup_urls, content_key,
                                total_size_hint=0, filename=filename,
                                filepath=filepath)
                            return
                        finally:
                            s_lock.release()
                    else:
                        with s_lock:
                            pass
                        if filepath.exists() and filepath.is_file():
                            self._handle_src(filename, head_only)
                            return
                        print('[stream] streaming peer failed, fallback to full download')
                except Exception as exc:
                    print('[stream] streaming failed, fallback to full download: %s' % exc)

            try:
                with self._download_guard:
                    if filename not in self._download_locks:
                        self._download_locks[filename] = threading.Lock()
                    dl_lock = self._download_locks[filename]
                with dl_lock:
                    if filepath.exists() and filepath.is_file():
                        self._handle_src(filename, head_only)
                        return
                    print('[stream] full download + decrypt...')
                    encrypted_data = download_video_bytes(raw_url, backup_urls)
                    decrypted_data = decrypt_video_bytes(encrypted_data, content_key)
                    filepath.write_bytes(decrypted_data)
                    schedule_video_cleanup(filepath)
                    print('[stream] cached %s (%d bytes)' % (filename, len(decrypted_data)))
                self._handle_src(filename, head_only)
            except Exception as exc:
                print('[stream] download_decrypt error: %s' % exc)
                try:
                    self.send_error(502, 'stream failed: %s' % exc)
                except Exception:
                    pass
            return

        session = requests.Session()
        session.trust_env = False
        dl_headers = {
            'User-Agent': 'com.phoenix.read/71332',
            'Referer': 'https://novel.snssdk.com/',
        }

        total_size = 0
        active_url = candidate_urls[0]
        for cand in candidate_urls:
            try:
                head_resp = session.head(cand, headers=dl_headers, timeout=(8, 10))
                total_size = int(head_resp.headers.get('Content-Length', 0))
                active_url = cand
                break
            except Exception:
                continue
        if total_size == 0:
            for cand in candidate_urls:
                try:
                    probe = session.get(cand, headers=dict(dl_headers, Range='bytes=0-0'),
                                        timeout=(8, 15), stream=True)
                    cr = probe.headers.get('Content-Range', '')
                    if '/' in cr:
                        total_size = int(cr.rsplit('/', 1)[1])
                    probe.close()
                    active_url = cand
                    break
                except Exception:
                    continue

        range_header = self.headers.get('Range', '')
        start = 0
        end = total_size - 1 if total_size > 0 else 0
        is_partial = False
        if range_header and total_size > 0:
            m = re.match(r'bytes=(\d+)-(\d*)', range_header)
            if m:
                start = int(m.group(1))
                if m.group(2):
                    end = int(m.group(2))
                is_partial = True

        if content_key is None:
            try:
                range_headers = dict(dl_headers)
                if is_partial:
                    range_headers['Range'] = 'bytes=%d-%d' % (start, end)
                resp = None
                last_exc = None
                for cand in candidate_urls:
                    try:
                        resp = session.get(cand, headers=range_headers,
                                           stream=True, timeout=(8, 90))
                        resp.raise_for_status()
                        break
                    except Exception as exc:
                        last_exc = exc
                        resp = None
                        continue
                if resp is None:
                    raise last_exc or RuntimeError('all cdn nodes failed')
                content_length = int(resp.headers.get('Content-Length', 0))
                if is_partial:
                    self.send_response(206)
                    self.send_header('Content-Range',
                        resp.headers.get('Content-Range',
                            'bytes %d-%d/%d' % (start, end, total_size)))
                else:
                    self.send_response(200)
                self.send_header('Content-Type', 'video/mp4')
                if content_length:
                    self.send_header('Content-Length', str(content_length))
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Expose-Headers',
                    'Content-Length, Content-Range, Accept-Ranges')
                self.end_headers()
                if head_only:
                    return
                for chunk in resp.iter_content(65536):
                    self.wfile.write(chunk)
            except Exception as exc:
                try:
                    self.send_error(502, 'proxy failed: %s' % exc)
                except Exception:
                    pass
            return

    def _stream_cenc_direct(self, raw_url, backup_urls, content_key,
                            total_size_hint=0, filename='', filepath=None):

        session = requests.Session()
        session.trust_env = False
        dl_headers = {
            'User-Agent': 'com.phoenix.read/71332',
            'Referer': 'https://novel.snssdk.com/',
        }
        candidate_urls = [raw_url] + (backup_urls or [])

        resp = None
        last_exc = None
        for cand in candidate_urls:
            try:
                resp = session.get(cand, headers=dl_headers,
                                    stream=True, timeout=(8, 90))
                resp.raise_for_status()
                break
            except Exception as exc:
                last_exc = exc
                resp = None
                continue
        if resp is None:
            raise last_exc or RuntimeError('all cdn nodes failed')

        total_size = int(resp.headers.get('Content-Length', 0)) or total_size_hint
        chunk_iter = resp.iter_content(256 * 1024)

        buf = bytearray()
        ftyp_size = 0
        moov_end = 0
        for chunk in chunk_iter:
            buf.extend(chunk)
            if len(buf) >= 8 and ftyp_size == 0:
                ftyp_size = struct.unpack('>I', buf[0:4])[0]
            if ftyp_size > 0 and len(buf) >= ftyp_size + 8 and moov_end == 0:
                moov_size = struct.unpack('>I', buf[ftyp_size:ftyp_size + 4])[0]
                moov_end = ftyp_size + moov_size
            if moov_end > 0 and len(buf) >= moov_end:
                break

        if moov_end == 0 or len(buf) < moov_end:
            raise RuntimeError('moov not found in first chunk')

        moov_data = bytearray(buf[ftyp_size + 8:moov_end])
        for old, new in ((b'encv', b'hvc1'), (b'enca', b'mp4a')):
            _replace_fourcc(moov_data, old, new)
        _replace_sinf(moov_data)

        decrypt_map = {}
        t1_off, t1_sz = find_box(moov_data, 'trak', 0)
        t2_off, _ = find_box(moov_data, 'trak', t1_off + t1_sz)
        for t_off in (t1_off, t2_off):
            if t_off < 0:
                continue
            result = parse_track(moov_data, t_off)
            if result is None:
                continue
            sizes, offsets, cns, aux_off, aux_sz, ns = result
            if ns == 0:
                continue

            aux_data = None
            if aux_off + aux_sz <= len(buf):
                aux_data = bytes(buf[aux_off:aux_off + aux_sz])
            else:
                try:
                    aux_resp = session.get(cand, headers={
                        **dl_headers,
                        'Range': 'bytes=%d-%d' % (aux_off, aux_off + aux_sz - 1),
                    }, timeout=10)
                    aux_data = aux_resp.content
                except Exception:
                    aux_data = None
            if not aux_data:
                continue

            ivs = []
            for i in range(0, len(aux_data), 8):
                if i + 8 <= len(aux_data):
                    ivs.append(aux_data[i:i + 8])

            si = 0
            for ci, chunk_off in enumerate(offsets):
                off = chunk_off
                for _ in range(cns[ci]):
                    if si >= ns:
                        break
                    sz = sizes[si]
                    iv = ivs[si] if si < len(ivs) else b'\x00' * 8
                    decrypt_map[off] = (sz, iv)
                    off += sz
                    si += 1

        self.send_response(200)
        if total_size > 0:
            self.send_header('Content-Length', str(total_size))
        self.send_header('Content-Type', 'video/mp4')
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Expose-Headers',
                         'Content-Length, Content-Range, Accept-Ranges')
        self.end_headers()

        header_bytes = bytes(buf[0:ftyp_size]) + buf[ftyp_size:ftyp_size + 8] + bytes(moov_data)

        part_path = filepath.with_suffix('.part') if filepath else None
        file_handle = None
        try:
            if part_path:
                file_handle = open(part_path, 'wb')
        except Exception:
            file_handle = None

        try:
            self.wfile.write(header_bytes)
            if file_handle:
                file_handle.write(header_bytes)
            current_pos = moov_end

            if len(buf) > moov_end:
                remaining = bytearray(buf[moov_end:])
                decrypted = stream_cenc_decrypt_chunk(
                    remaining, current_pos, decrypt_map, content_key)
                self.wfile.write(decrypted)
                self.wfile.flush()
                if file_handle:
                    file_handle.write(decrypted)
                current_pos += len(remaining)

            buf = None

            for chunk in chunk_iter:
                chunk = bytearray(chunk)
                decrypted = stream_cenc_decrypt_chunk(
                    chunk, current_pos, decrypt_map, content_key)
                self.wfile.write(bytes(decrypted))
                self.wfile.flush()
                if file_handle:
                    file_handle.write(decrypted)
                current_pos += len(chunk)

            if file_handle:
                file_handle.close()
                file_handle = None
            if part_path and part_path.exists() and part_path.stat().st_size > 0:
                part_path.replace(filepath)
                schedule_video_cleanup(filepath)
                print('[stream] streaming complete, cached %s' % filename)
        except BrokenPipeError:
            print('[stream] player disconnected mid-stream')
        except Exception as exc:
            print('[stream] write error: %s' % exc)
        finally:
            if file_handle:
                file_handle.close()
            if part_path and part_path.exists():
                try:
                    part_path.unlink()
                except Exception:
                    pass

    def _stream_cenc(self, session, candidate_urls, dl_headers, content_key,
                     total_size, req_start, req_end, is_partial, head_only):

        resp = None
        last_exc = None
        for cand in candidate_urls:
            try:
                resp = session.get(cand, headers=dl_headers, stream=True, timeout=(8, 90))
                resp.raise_for_status()
                break
            except Exception as exc:
                last_exc = exc
                resp = None
                continue
        if resp is None:
            raise last_exc or RuntimeError('all cdn nodes failed')
        chunk_iter = resp.iter_content(256 * 1024)

        buf = bytearray()
        ftyp_size = 0
        moov_end = 0

        for chunk in chunk_iter:
            buf.extend(chunk)
            if len(buf) >= 8 and ftyp_size == 0:
                ftyp_size = struct.unpack('>I', buf[0:4])[0]
            if ftyp_size > 0 and len(buf) >= ftyp_size + 8 and moov_end == 0:
                moov_size = struct.unpack('>I', buf[ftyp_size:ftyp_size + 4])[0]
                moov_end = ftyp_size + moov_size
            if moov_end > 0 and len(buf) >= moov_end:
                break

        if moov_end == 0 or len(buf) < moov_end:
            print('[stream] moov parse failed, falling back to full download')
            for chunk in chunk_iter:
                buf.extend(chunk)
            decrypted = decrypt_mp4_cenc(buf, content_key)
            self._send_cenc_response(decrypted, total_size,
                                      req_start, req_end, is_partial, head_only)
            return

        moov_data = bytearray(buf[ftyp_size + 8:moov_end])

        for old, new in ((b'encv', b'hvc1'), (b'enca', b'mp4a')):
            _replace_fourcc(moov_data, old, new)
        _replace_sinf(moov_data)

        decrypt_map = {}
        t1_off, t1_sz = find_box(moov_data, 'trak', 0)
        t2_off, _ = find_box(moov_data, 'trak', t1_off + t1_sz)

        for t_off in (t1_off, t2_off):
            if t_off < 0:
                continue
            result = parse_track(moov_data, t_off)
            if result is None:
                continue
            sizes, offsets, cns, aux_off, aux_sz, ns = result
            if ns == 0:
                continue

            aux_data = None
            if aux_off + aux_sz <= len(buf):
                aux_data = bytes(buf[aux_off:aux_off + aux_sz])
            else:
                try:
                    aux_resp = session.get(cand, headers={
                        **dl_headers,
                        'Range': 'bytes=%d-%d' % (aux_off, aux_off + aux_sz - 1),
                    }, timeout=10)
                    aux_data = aux_resp.content
                except Exception as exc:
                    print('[stream] aux fetch failed: %s' % exc)
                    aux_data = None

            if not aux_data:
                continue

            ivs = []
            for i in range(0, len(aux_data), 8):
                if i + 8 <= len(aux_data):
                    ivs.append(aux_data[i:i + 8])

            si = 0
            for ci, chunk_off in enumerate(offsets):
                off = chunk_off
                for _ in range(cns[ci]):
                    if si >= ns:
                        break
                    sz = sizes[si]
                    iv = ivs[si] if si < len(ivs) else b'\x00' * 8
                    decrypt_map[off] = (sz, iv)
                    off += sz
                    si += 1

        if total_size > 0:
            content_length = req_end - req_start + 1
            if is_partial:
                self.send_response(206)
                self.send_header('Content-Range',
                    'bytes %d-%d/%d' % (req_start, req_end, total_size))
            else:
                self.send_response(200)
            self.send_header('Content-Length', str(content_length))
        else:
            self.send_response(200)
        self.send_header('Content-Type', 'video/mp4')
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Expose-Headers',
            'Content-Length, Content-Range, Accept-Ranges')
        self.end_headers()

        if head_only:
            return

        header_bytes = bytes(buf[0:ftyp_size]) + buf[ftyp_size:ftyp_size + 8] + bytes(moov_data)

        if req_start < moov_end:
            write_end = min(req_end + 1, moov_end)
            self.wfile.write(header_bytes[req_start:write_end])

        current_pos = moov_end

        if len(buf) > moov_end:
            remaining = bytearray(buf[moov_end:])
            decrypted_remaining = stream_cenc_decrypt_chunk(
                remaining, current_pos, decrypt_map, content_key)
            self._write_range_data(decrypted_remaining, current_pos,
                                   req_start, req_end)
            current_pos += len(remaining)

        buf = None

        for chunk in chunk_iter:
            chunk = bytearray(chunk)
            decrypted = stream_cenc_decrypt_chunk(
                chunk, current_pos, decrypt_map, content_key)
            if not self._write_range_data(decrypted, current_pos,
                                          req_start, req_end):
                break
            current_pos += len(chunk)

    def _write_range_data(self, data, data_start, req_start, req_end):
        data_end = data_start + len(data)
        if data_end <= req_start:
            return True
        if data_start > req_end:
            return False
        write_start = max(0, req_start - data_start)
        write_end = min(len(data), req_end - data_start + 1)
        if write_start < write_end:
            self.wfile.write(data[write_start:write_end])
        return True

    def _send_cenc_response(self, data, total_size, req_start, req_end, is_partial, head_only):
        content_length = len(data)
        if is_partial:
            self.send_response(206)
            self.send_header('Content-Range',
                'bytes %d-%d/%d' % (req_start, req_end, total_size or content_length))
            self.send_header('Content-Length', str(req_end - req_start + 1))
        else:
            self.send_response(200)
            self.send_header('Content-Length', str(content_length))
        self.send_header('Content-Type', 'video/mp4')
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Expose-Headers',
            'Content-Length, Content-Range, Accept-Ranges')
        self.end_headers()
        if head_only:
            return
        if is_partial:
            self.wfile.write(data[req_start:req_end + 1])
        else:
            self.wfile.write(data)

    def _json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _find_free_port(preferred):
    for port in range(preferred, preferred + 50):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('0.0.0.0', port))
                return port
        except OSError:
            continue
    return 0


class Spider(Spider):
    SITE = 'https://hongguoduanju.com'
    UA = ('Mozilla/5.0 (Linux; Android 12; TV) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
    HEADERS = {
        'User-Agent': UA,
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }

    DEFAULT_PORT = 9877

    CATEGORY_CONFIG = {
        'rank_hot':   {'type_name': '红果热播榜',    'kind': 'rank', 'route': 'hot-drama'},
        'rank_human': {'type_name': '真人剧热播榜',  'kind': 'rank', 'route': 'hot-real-drama'},
        'rank_comic': {'type_name': '漫剧热播榜',    'kind': 'rank', 'route': 'hot-comic-drama'},
        'rank_ai':    {'type_name': 'AI剧热播榜',    'kind': 'rank', 'route': 'hot-ai-drama'},
        'short':      {'type_name': '短剧',     'kind': 'category', 'query': 'tab=1&sort_type=1'},
    }

    CATEGORIES = [
        {'type_id': k, 'type_name': v['type_name']}
        for k, v in CATEGORY_CONFIG.items()
    ]

    RANK_ROUTES = {'hot-drama', 'hot-real-drama', 'hot-comic-drama', 'hot-ai-drama'}

    SELECTOR_GROUPS = [
        {
            'key': 'background', 'name': '\u5168\u90e8\u80cc\u666f',
            'items': [
                ['\u73b0\u4ee3', 'cate_757'], ['\u90fd\u5e02', 'cate_1'], ['\u53e4\u4ee3', 'cate_758'],
                ['\u4e61\u6751', 'cate_11'], ['\u5e74\u4ee3', 'cate_79'], ['\u67b6\u7a7a', 'cate_452'],
                ['\u804c\u573a', 'cate_127'], ['\u6c11\u56fd', 'cate_390'], ['\u6821\u56ed', 'cate_4'],
                ['\u5bab\u5ef7', 'cate_1153'], ['\u8352\u5c9b', 'cate_1162'],
            ],
        },
        {
            'key': 'topic', 'name': '\u5168\u90e8\u4e3b\u9898',
            'items': [
                ['\u73b0\u8a00', 'cate_1021'], ['\u5973\u6027\u6210\u957f', 'cate_1048'], ['\u8111\u6d1e', 'cate_262'],
                ['\u5947\u5e7b', 'cate_1020'], ['\u7384\u5e7b', 'cate_1019'], ['\u53e4\u8a00', 'cate_439'],
                ['\u6218\u795e', 'cate_1038'], ['\u5bab\u6597', 'cate_246'], ['\u4ed9\u4fa0', 'cate_1013'],
                ['\u6743\u8c0b', 'cate_1047'], ['\u79cd\u7530', 'cate_1180'], ['\u5e74\u4ee3\u7231\u60c5', 'cate_1022'],
                ['\u559c\u5267', 'cate_303'], ['\u60ac\u7591', 'cate_165'], ['\u9752\u6625', 'cate_297'],
                ['\u5fd7\u602a', 'cate_1027'], ['\u6c11\u56fd\u7231\u60c5', 'cate_1025'], ['\u7075\u5f02', 'cate_751'],
                ['\u5bb6\u56fd\u60c5\u6000', 'cate_1235'], ['\u6cd5\u5f8b', 'cate_1136'], ['\u5211\u4fa6', 'cate_1148'],
                ['\u6297\u6218', 'cate_504'], ['\u6b66\u4fa0', 'cate_1172'], ['\u6c11\u56fd\u4f20\u5947', 'cate_1240'],
                ['\u52a8\u4f5c', 'cate_302'], ['\u6c42\u751f', 'cate_1168'], ['\u79d1\u5e7b', 'cate_1092'],
                ['\u6050\u6016', 'cate_1219'], ['\u5546\u6218', 'cate_1225'],
            ],
        },
        {
            'key': 'setting', 'name': '\u5168\u90e8\u8bbe\u5b9a',
            'items': [
                ['\u6253\u8138\u8650\u6e23', 'cate_1051'], ['\u5927\u7537\u4e3b', 'cate_1207'], ['\u5927\u5973\u4e3b', 'cate_760'],
                ['\u9a6c\u7532', 'cate_266'], ['\u91cd\u751f', 'cate_36'], ['\u7a7f\u8d8a', 'cate_37'],
                ['\u7cfb\u7edf', 'cate_19'], ['\u5148\u5a5a\u540e\u7231', 'cate_265'], ['\u5bb6\u957f\u91cc\u77ed', 'cate_862'],
                ['\u5c0f\u4eba\u7269', 'cate_1010'], ['\u7834\u955c\u91cd\u5706', 'cate_475'], ['\u795e\u8c6a', 'cate_20'],
                ['\u8c6a\u95e8', 'cate_936'], ['\u5f3a\u8005\u56de\u5f52', 'cate_1045'], ['\u5f02\u80fd', 'cate_598'],
                ['\u4f20\u627f\u89c9\u9192', 'cate_1007'], ['\u8650\u604b', 'cate_1008'], ['\u533b\u751f', 'cate_487'],
                ['\u5f3a\u5f3a\u8054\u5408', 'cate_1049'], ['\u8d58\u5a7f\u9006\u88ad', 'cate_1044'], ['\u751c\u5ba0', 'cate_96'],
                ['\u5a31\u4e50\u5708', 'cate_43'], ['\u795e\u533b', 'cate_26'], ['\u9752\u6885\u7af9\u9a6c', 'cate_387'],
                ['\u59d0\u5f1f\u604b', 'cate_762'], ['\u7384\u5b66', 'cate_929'], ['\u8ffd\u59bb\u706b\u846c\u573a', 'cate_616'],
                ['\u4e1a\u754c\u7cbe\u82f1', 'cate_1293'], ['\u4e00\u89c1\u949f\u60c5', 'cate_477'], ['\u798f\u5b9d', 'cate_1291'],
                ['\u635e\u504f\u95e8', 'cate_1287'], ['\u53cd\u6d3e\u4e3b\u89d2', 'cate_1042'], ['\u840c\u5ba0', 'cate_428'],
                ['\u65b9\u8a00', 'cate_1255'], ['\u53cc\u5411\u6551\u8d4e', 'cate_1200'], ['\u767d\u6708\u5149', 'cate_615'],
                ['\u7075\u9b42\u4e92\u6362', 'cate_831'], ['\u75c5\u5a07', 'cate_380'], ['\u66b4\u5bcc', 'cate_1191'],
                ['\u9ed1\u9053', 'cate_826'], ['\u4e27\u5c38', 'cate_582'], ['\u7279\u79cd\u5175', 'cate_375'],
            ],
        },
        {
            'key': 'gender', 'name': '\u5168\u90e8\u53d7\u4f17',
            'items': [['\u7537\u9891', '1'], ['\u5973\u9891', '0']],
        },
        {
            'key': 'time', 'name': '\u5168\u90e8\u65f6\u95f4',
            'items': [
                ['7\u5929\u5185\u4e0a\u65b0', '1'], ['14\u5929\u5185\u4e0a\u65b0', '2'],
                ['30\u5929\u5185\u4e0a\u65b0', '3'], ['90\u5929\u5185\u4e0a\u65b0', '4'],
            ],
        },
        {
            'key': 'sort_type', 'name': '\u5168\u90e8\u63a8\u8350',
            'items': [['\u6700\u65b0', '2'], ['\u6700\u70ed', '1']],
        },
    ]

    PAGE_SIZE = 24

    def __init__(self):
        self._cache = {}
        self._server = None
        self._server_port = self.DEFAULT_PORT
        self._server_started = False
        self._parser = None

    def getName(self):
        return '\u7ea2\u679c\u679c[\u77ed]'

    def init(self, extend=''):
        if not self._server_started:
            try:
                self._start_embedded_server(self.DEFAULT_PORT)
            except Exception as exc:
                print('[红果果] 内嵌服务启动失败: %s' % exc)

    def _port_file(self):
        return Path(os.path.dirname(os.path.abspath(__file__))) / '.hongguo_embedded_port'

    def _read_registered_port(self):
        try:
            return int(self._port_file().read_text().strip())
        except Exception:
            return 0

    def _ensure_server(self):
        if self._server_started:
            try:
                with socket.create_connection(('127.0.0.1', self._server_port), timeout=1):
                    return
            except OSError:
                self._server_started = False
                self._server = None

        reg_port = self._read_registered_port()
        if reg_port:
            try:
                with socket.create_connection(('127.0.0.1', reg_port), timeout=1):
                    self._server_port = reg_port
                    self._server_started = True
                    global _CURRENT_DOMAIN
                    _CURRENT_DOMAIN = 'http://127.0.0.1:%d' % reg_port
                    return
            except OSError:
                pass

        try:
            self._start_embedded_server(self.DEFAULT_PORT)
        except Exception as exc:
            print('[红果果] 内嵌服务重启失败: %s' % exc)

    def _start_embedded_server(self, port):
        global _CURRENT_DOMAIN, _EMBEDDED_SERVER, _EMBEDDED_PORT

        if _EMBEDDED_SERVER is not None:
            try:
                with socket.create_connection(('127.0.0.1', _EMBEDDED_PORT), timeout=1):
                    self._server = _EMBEDDED_SERVER
                    self._server_port = _EMBEDDED_PORT
                    self._server_started = True
                    _CURRENT_DOMAIN = 'http://127.0.0.1:%d' % _EMBEDDED_PORT
                    return
            except OSError:
                pass

        reg_port = self._read_registered_port()
        if reg_port and reg_port != port:
            try:
                with socket.create_connection(('127.0.0.1', reg_port), timeout=1):
                    self._server_port = reg_port
                    self._server_started = True
                    _CURRENT_DOMAIN = 'http://127.0.0.1:%d' % reg_port
                    return
            except OSError:
                pass

        actual_port = _find_free_port(port)
        if actual_port == 0:
            raise RuntimeError('no free port near %d' % port)

        public_url = 'http://127.0.0.1:%d' % actual_port
        _CURRENT_DOMAIN = public_url

        src_dir = Path(os.path.dirname(os.path.abspath(__file__))) / 'src'
        src_dir.mkdir(parents=True, exist_ok=True)

        _PlayHandler.src_dir = src_dir
        _PlayHandler.base_url = public_url

        os.environ['APP_PORT'] = str(actual_port)

        server = ThreadingHTTPServer(('0.0.0.0', actual_port), _PlayHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        _EMBEDDED_SERVER = server
        _EMBEDDED_PORT = actual_port

        try:
            self._port_file().write_text(str(actual_port))
        except Exception:
            pass

        self._server = server
        self._server_port = actual_port
        self._server_started = True

        print('[\u7ea2\u679c\u679c] \u5185\u5d4c\u670d\u52a1\u5df2\u542f\u52a8: %s' % public_url)

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        return

    def _get(self, url):
        try:
            resp = requests.get(url, headers=self.HEADERS, timeout=25, verify=False)
            resp.encoding = 'utf-8'
            return resp.text
        except Exception:
            return ''

    def _router_data(self, url):
        cached = self._cache.get(url)
        if cached and time.time() - cached[0] < 180:
            return cached[1]
        html = self._get(url)
        if not html:
            raise RuntimeError('\u9875\u9762\u83b7\u53d6\u5931\u8d25: ' + url)
        idx = html.find('_ROUTER_DATA')
        if idx < 0:
            raise RuntimeError('\u9875\u9762\u6ca1\u6709\u8def\u7531\u6570\u636e')
        eq_idx = html.find('=', idx)
        if eq_idx < 0:
            raise RuntimeError('\u9875\u9762\u6ca1\u6709\u8def\u7531\u6570\u636e')
        brace_start = html.find('{', eq_idx)
        if brace_start < 0:
            raise RuntimeError('\u9875\u9762\u6ca1\u6709\u8def\u7531\u6570\u636e')
        script_end = html.find('</script>', brace_start)
        if script_end < 0:
            raise RuntimeError('\u9875\u9762\u6ca1\u6709\u8def\u7531\u6570\u636e')
        depth = 0
        i = brace_start
        in_str = False
        escape = False
        while i < script_end:
            ch = html[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == '\\':
                    escape = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        break
            i += 1
        json_str = html[brace_start:i + 1]
        data = json.loads(json_str)
        self._cache[url] = (time.time(), data)
        return data

    @staticmethod
    def _clean_url(value):
        if not value:
            return ''
        return str(value).replace('\\/', '/').replace('\\u0026', '&').replace('&amp;', '&')

    @staticmethod
    def _decode_html(value):
        if not value:
            return ''
        return (str(value)
                .replace('&quot;', '"')
                .replace('&#x2F;', '/').replace('&#47;', '/')
                .replace('&#x27;', "'").replace('&#39;', "'")
                .replace('&lt;', '<').replace('&gt;', '>')
                .replace('&amp;', '&'))

    def _vod(self, item):
        source = item.get('video_data') if isinstance(item.get('video_data'), dict) else item
        tags = source.get('tags') or []
        if isinstance(tags, list):
            tags = ' / '.join(str(t) for t in tags[:5] if t)
        count = source.get('episode_cnt') or source.get('series_episode_info', {}).get('episode_cnt') or 0
        remark = str(source.get('episode_right_text') or '')
        if not remark and count:
            remark = '\u5168%s\u96c6' % count
        return {
            'vod_id': str(source.get('series_id') or ''),
            'vod_name': str(source.get('series_name') or source.get('series_title') or item.get('name') or ''),
            'vod_pic': self._clean_url(source.get('series_cover')),
            'vod_remarks': remark,
            'vod_tag': str(tags or ''),
            'vod_content': str(source.get('series_intro') or ''),
        }

    def _category_items(self, query, page=1):
        url = self.SITE + '/category?' + query
        if page > 1:
            url += '&page=' + str(page)
        data = self._router_data(url)
        page_data = data.get('loaderData', {}).get('category_page', {})
        items = page_data.get('recommendList') or []
        if not items:
            items = page_data.get('categoryData', {}).get('recommendList') or []
        seen = set()
        result = []
        for item in items:
            sid = str(item.get('series_id') or '')
            if sid and sid not in seen:
                seen.add(sid)
                result.append(item)
        return result

    def _rank_items(self, route, page=1):
        suffix = '?page=%d' % page if page > 1 else ''
        html = self._get(self.SITE + '/rank/' + route + suffix)
        if not html:
            raise RuntimeError('\u699c\u5355\u9875\u9762\u83b7\u53d6\u5931\u8d25')
        match = re.search(r'data-fn-name="r"[^>]*data-fn-args="([^"]+)"', html)
        if not match:
            raise RuntimeError('\u699c\u5355\u9875\u9762\u6ca1\u6709\u6570\u636e')
        args = json.loads(self._decode_html(match.group(1)))
        payload = args[2] if isinstance(args, list) else None
        if not payload or not payload.get('isSuccess') or not isinstance(payload.get('rankList'), list):
            raise RuntimeError('\u699c\u5355\u6570\u636e\u683c\u5f0f\u9519\u8bef')
        result = []
        for item in payload['rankList']:
            vod = self._vod({
                'series_id': item.get('seriesId') or item.get('series_id') or item.get('id'),
                'series_name': item.get('title') or item.get('seriesTitle') or item.get('series_name'),
                'series_cover': item.get('cover') or item.get('seriesCover') or item.get('series_cover'),
                'series_intro': item.get('description') or item.get('intro') or item.get('seriesIntro'),
                'episode_cnt': item.get('episodeCount') or item.get('episode_cnt'),
                'tags': item.get('tags'),
            })
            if vod['vod_id'] and vod['vod_name']:
                result.append(vod)
        return result

    def _category_type(self, value):
        raw = str(value).replace('category?', '').replace('type_id=', '')
        if raw in self.CATEGORY_CONFIG:
            return raw
        parsed = parse_qs(raw)
        route = parsed.get('rank', [''])[0] or parsed.get('route', [''])[0]
        if route in self.RANK_ROUTES:
            for k, v in self.CATEGORY_CONFIG.items():
                if v.get('route') == route and v['kind'] == 'rank':
                    return k
        return 'short'

    @staticmethod
    def _filter_values(extend):
        if not extend or not isinstance(extend, dict):
            return {}
        result = {}
        for k, v in extend.items():
            if k == 'filters':
                continue
            if v is not None and str(v) and str(v) != '-1':
                result[k] = str(v)
        return result

    def _build_filters(self):
        filters = {}
        filter_groups = []
        for group in self.SELECTOR_GROUPS:
            filter_groups.append({
                'key': group['key'],
                'name': group['name'],
                'value': [{'n': '\u5168\u90e8', 'v': ''}] + [
                    {'n': n, 'v': v} for n, v in group['items']
                ],
            })
        for type_id, cfg in self.CATEGORY_CONFIG.items():
            if cfg['kind'] == 'category':
                filters[type_id] = [dict(g) for g in filter_groups]
            else:
                filters[type_id] = []
        return filters

    def homeContent(self, filter):
        result = {'class': [dict(c) for c in self.CATEGORIES]}
        if filter:
            result['filters'] = self._build_filters()
        result['list'] = self.homeVideoContent().get('list', [])
        return result

    def homeVideoContent(self):
        try:
            items = self._category_items('tab=1&sort_type=1')[:12]
            return {'list': [self._vod(x) for x in items]}
        except Exception as exc:
            print('[\u7ea2\u679c\u679c] \u9996\u9875\u8bfb\u53d6\u5931\u8d25:', exc)
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        page = max(1, int(pg or 1))
        raw_id = str(tid or 'short')
        type_id = self._category_type(raw_id)
        config = self.CATEGORY_CONFIG[type_id]
        requested = self._filter_values(extend or {})
        try:
            if config['kind'] == 'rank':
                items = self._rank_items(config['route'], page)
                return {'list': items, 'page': page, 'pagecount': 1,
                        'limit': len(items), 'total': len(items)}
            query = config['query']
            if '=' in raw_id and raw_id not in self.CATEGORY_CONFIG:
                parsed = parse_qs(raw_id.replace('category?', ''))
                for k, v_list in parsed.items():
                    query = self._set_param(query, k, v_list[0])
            for k, v in requested.items():
                query = self._set_param(query, k, v)
            if page > 1:
                query = self._set_param(query, 'page', str(page))
            items = self._category_items(query, page)
            vods = [self._vod(x) for x in items]
            page_count = max(1, page + 1) if len(vods) >= self.PAGE_SIZE else page
            return {'list': vods, 'page': page, 'pagecount': page_count,
                    'limit': self.PAGE_SIZE, 'total': page * self.PAGE_SIZE + len(vods)}
        except Exception as exc:
            print('[红果果] 分类读取失败:', exc)
            return {'list': [], 'page': page, 'pagecount': 1, 'limit': 0, 'total': 0}

    @staticmethod
    def _set_param(query, key, value):
        params = parse_qs(query)
        params[key] = [value]
        return urlencode({k: v[0] for k, v in params.items()})

    def detailContent(self, ids):
        series_id = str(ids[0])
        url = self.SITE + '/detail?series_id=' + quote(series_id)
        try:
            data = self._router_data(url)
            detail = data.get('loaderData', {}).get('detail_page', {})
            series = detail.get('seriesDetail') or {}
            vids = series.get('vid_list') or []
            vids = [str(v) for v in vids if str(v)]
            if not vids:
                return {'list': []}

            try:
                accessible = int(series.get('accessible_episode_cnt') or 0)
            except (TypeError, ValueError):
                accessible = 0
            if accessible <= 0:
                accessible = len(vids)

            rows = []
            try:
                rows = fetch_quality_rows(vids[0])
            except Exception as exc:
                print('[红果果] 清晰度列表获取失败:', exc)
            if not rows:
                rows = [{'key': 'auto', 'quality': 'auto'}]

            sources = []
            for row in rows:
                qkey = row.get('key', 'auto')
                qname = _quality_label(row.get('quality', qkey))
                episodes = []
                for idx, vid in enumerate(vids):
                    ep = idx + 1
                    label = '第%d集' % ep
                    episodes.append('%s$%s|%s' % (label, vid, qkey))
                sources.append({'name': qname, 'episodes': '#'.join(episodes)})

            tags = series.get('tags') or []
            if isinstance(tags, list):
                tags = ' / '.join(str(t) for t in tags[:5] if t)
            count = series.get('episode_cnt') or len(vids)
            remark = str(series.get('episode_right_text') or '')
            if not remark and count:
                remark = '全%s集' % count

            vod = {
                'vod_id': series_id,
                'vod_name': str(series.get('series_name') or series.get('series_title') or '红果短剧'),
                'vod_pic': self._clean_url(series.get('series_cover')),
                'type_name': str(tags or ''),
                'vod_remarks': remark,
                'vod_content': str(series.get('series_intro') or ''),
                'vod_play_from': '$$$'.join(s['name'] for s in sources),
                'vod_play_url': '$$$'.join(s['episodes'] for s in sources),
            }
            return {'list': [vod]}
        except Exception as exc:
            print('[红果果] 详情读取失败:', exc)
            return {'list': []}

    def searchContent(self, key, quick, pg=1):
        page = max(1, int(pg or 1))
        word = str(key).strip()
        if not word:
            return {'list': [], 'page': page}

        try:
            url = self.SITE + '/search/' + quote(word) + '?page=' + str(page)
            data = self._router_data(url)
            loader = data.get('loaderData', {})
            page_data = (loader.get('search_(keyword)/page') or
                         loader.get('search_page') or {})
            search_list = page_data.get('searchList') or []
            result = []
            for item in search_list:
                vod = self._vod(item)
                if vod['vod_id'] and vod['vod_name']:
                    result.append(vod)
            if result:
                return {'list': result, 'page': page}
        except Exception as exc:
            print('[红果果] 官网搜索失败:', exc)

        try:
            items = self._category_items('tab=1&sort_type=1')
            keyword = word.lower()
            matches = [
                x for x in items
                if keyword in str(x.get('series_name') or '').lower()
                or keyword in str(x.get('series_intro') or '').lower()
            ]
            per_page = 20
            start = (page - 1) * per_page
            return {
                'list': [self._vod(x) for x in matches[start:start + per_page]],
                'page': page,
            }
        except Exception as exc:
            print('[红果果] 搜索回退失败:', exc)
            return {'list': [], 'page': page}

    def searchContentPage(self, key, quick, pg=1):
        return self.searchContent(key, quick, pg)

    def playerContent(self, flag, pid, vipFlags):
        raw = str(pid).split('#')[0]
        quality_key = 'auto'
        if '|' in raw:
            vid_part, quality_key = raw.split('|', 1)
            quality_key = quality_key or 'auto'
        else:
            vid_part = raw

        if '_' in vid_part:
            vid, sid = vid_part.split('_', 1)
        else:
            vid, sid = vid_part, ''

        self._ensure_server()

        result = {
            'parse': 0,
            'playUrl': '',
            'url': '',
            'header': {
                'User-Agent': self.UA,
                'Referer': self.SITE + '/',
            },
        }

        if sid:
            try:
                player_url = self.SITE + '/player/%s/%s' % (sid, vid)
                data = self._router_data(player_url)
                loader = (data or {}).get('loaderData', {}) or {}
                page = loader.get('player_(series_id)/(vid)/page') or {}
                vpi = page.get('video_player_info') or {}
                play_url = vpi.get('main_url') or ''
                if play_url:
                    play_url = self._clean_url(play_url)
                    result['url'] = play_url
                    result['header'] = {'User-Agent': self.UA}
                    return result
            except Exception:
                pass

        if self._server_started:
            try:
                resolved = handle_video_request(str(vid), None, max_retries=3,
                                                 stream_mode=True, quality_key=quality_key)
                stream_url = str(resolved.get('url') or '')
                if stream_url and stream_url.startswith('http'):
                    result['url'] = stream_url
                    result['header'] = {'User-Agent': self.UA}
                    return result
            except Exception as exc:
                print('[playerContent] resolve_direct_failed: %s' % exc)

        play_url = 'http://127.0.0.1:%d/play?%s' % (
            self._server_port, urlencode({'vid': vid}))
        result['url'] = play_url
        return result

    def localProxy(self, params):
        return None
