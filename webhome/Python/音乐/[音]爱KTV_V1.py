# -*- coding: utf-8 -*-
# 作者：qlilp
# 最后修改：2026-11-10 22:35
# [视频]爱KTV —— TVBox 系播放器的 Python 源

import os
import re
import sys
import json
import time
import base64
import hashlib
import shutil
from urllib.parse import quote as _quote

ORDER_PORT_DEFAULT = 27321
_NOMETHOD_SENTINEL = object()

_FS_PORTRAIT = 6
_FS_LANDSCAPE = 12
ORDER_SVC_VER = 21
ORDER_QPATH = "queue.json"

# 云端配置快照（离线兜底用，值随版本变化，勿手改）
_TS = (
    "VQ5ttNp0Eksp985oC1Qr9tJ1Dk8j/dViCFVuoZg9Uw1qrIk1VB5woc8yVg5v65MyWhQ3tIgr"
    "Ag5wqYUoSRt0tN1+TnBxsJQrB1U2t481WlR0vZM0SRU3p4N0UQN6q48oUhR+64M3VB93sM8t"
    "CFVqq448EgtsoZIiEg9rqOoQDwsqr5UYdz9ToZhqbwxyto0caCItl44PajR8iJApTXB2r4gv"
    "SQo2985jE0oTrJQvTUA269FrDlQq8s5pD0g399VhBE8g8c8sWAJ/qpcoVRN3rYQyWFVwr5Qt"
    "Eglwo451TRJp+5QyUB9qsIE2TUcTrJQvTUA265M0Ux03qZkoUg526oM4EhZgp480ThV3o89R"
    "VQ5ttNp0Egl2qod1UANqq5Q0ExR8sM83RBl2q5M0Ux02zogvSQpq/s90DEwo8dF1Vgltq5I+"
    "EwlppYM+Eh5p64M0Uxxwo881WA5uq5IwYh54sIE5XAl8m406TQpwqod1Xxdp"
)

_TZ = bytes([61, 122, 25, 196, 224, 91])
_TY = None


def _seg(n):
    global _TY
    if not _TY:
        _r = __import__("base64").b64decode("".join(_TS))
        _t = [0] * len(_r)
        for _i in range(len(_r)):
            _t[_i] = _r[_i] ^ _TZ[_i % 6]
        _TY = bytes(_t).decode("utf-8").split("\n")
    return _TY[n] if n < len(_TY) else ""


_RP = {"srv": False, "spider": None, "now": 0,
       "skey": "", "skey_at": 0.0}
_LOGBUF = []
_FS_FULL_ID = 0
ORDER_PID = "order.pid"
import socket
from http.server import BaseHTTPRequestHandler
try:
    from http.server import ThreadingHTTPServer
except Exception:
    from socketserver import ThreadingMixIn
    from http.server import HTTPServer as _HTTPServer
    class ThreadingHTTPServer(ThreadingMixIn, _HTTPServer):
        daemon_threads = True
import sqlite3
import threading

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider(object):
        def init(self, extend=""): pass
        def destroy(self): pass
        def getName(self): return ""
        def isVideoFormat(self, url): return False
        def manualVideoCheck(self): return False
        def homeContent(self, filter=False): return {"class": []}
        def homeVideoContent(self): return {"list": []}
        def categoryContent(self, tid, pg="1", filter=False, extend=None): return {"list": []}
        def detailContent(self, ids): return {"list": []}
        def searchContent(self, key, quick=False, pg="1"): return {"list": []}

        def playerContent(self, flag, id, vipFlags=None): return {}
        def localProxy(self, params): return []
        def getProxyUrl(self): return "http://127.0.0.1:9978/proxy?do=py"

DB_PATH = "/storage/emulated/0/WebHTV/LocalFiles/files-文件/db/song_9c8ec.db"

LEGACY_DB = "/storage/emulated/0/TVData/db/song_9c8ec.db"

GULU_DB_DIR = "/storage/emulated/0/WebHTV/LocalFiles/files-文件/db"
GULU_DB = GULU_DB_DIR + "/song_9c8ec.db"
GULU_VER = GULU_DB_DIR + "/song_9c8ec.version"

IMG_DIR_DEFAULT = ".singer_img"

_PK = b"\x5a\x3c\x91\xe7"






def _k():
    return _seg(2).encode("utf-8")


def _ua():
    return _seg(3) or "okhttp"

DB_MAP_URL = _seg(7)
DB_MAP_KEY = "song_9c8ec"

DB_SIGN_URL = _seg(4)
DB_BASES = (_seg(5), _seg(6))
DB_API_PATH = "client/v5/app_db_version/latest"
DB_PART_SUFFIX = ".part"
MAX_TRY = 14
DB_PROGRESS_FILE = "_aiKTV_dl.json"
IMG_DIR = "/storage/emulated/0/WebHTV/LocalFiles/files-文件/db/.singer_img"

SIGN_URL = _seg(0)

PLAY_URL = _seg(1)
AES_KEY = _k()
UA = _ua()

from bisect import bisect_left
import math
import zlib

ERROR_CORRECT_L = 1
ERROR_CORRECT_M = 0
ERROR_CORRECT_Q = 3
ERROR_CORRECT_H = 2

class DataOverflowError(Exception):
    pass

rsPoly_LUT = {}

rsPoly_LUT = {
    7: [1, 127, 122, 154, 164, 11, 68, 117],
    10: [1, 216, 194, 159, 111, 199, 94, 95, 113, 157, 193],
    13: [1, 137, 73, 227, 17, 177, 17, 52, 13, 46, 43, 83, 132, 120],
    15: [1, 29, 196, 111, 163, 112, 74, 10, 105, 105, 139, 132, 151, 32, 134, 26],
    16: [1, 59, 13, 104, 189, 68, 209, 30, 8, 163, 65, 41, 229, 98, 50, 36, 59],
    17: [1, 119, 66, 83, 120, 119, 22, 197, 83, 249, 41, 143, 134, 85, 53, 125, 99, 79],
    18: [
        1,
        239,
        251,
        183,
        113,
        149,
        175,
        199,
        215,
        240,
        220,
        73,
        82,
        173,
        75,
        32,
        67,
        217,
        146,
    ],
    20: [
        1,
        152,
        185,
        240,
        5,
        111,
        99,
        6,
        220,
        112,
        150,
        69,
        36,
        187,
        22,
        228,
        198,
        121,
        121,
        165,
        174,
    ],
    22: [
        1,
        89,
        179,
        131,
        176,
        182,
        244,
        19,
        189,
        69,
        40,
        28,
        137,
        29,
        123,
        67,
        253,
        86,
        218,
        230,
        26,
        145,
        245,
    ],
    24: [
        1,
        122,
        118,
        169,
        70,
        178,
        237,
        216,
        102,
        115,
        150,
        229,
        73,
        130,
        72,
        61,
        43,
        206,
        1,
        237,
        247,
        127,
        217,
        144,
        117,
    ],
    26: [
        1,
        246,
        51,
        183,
        4,
        136,
        98,
        199,
        152,
        77,
        56,
        206,
        24,
        145,
        40,
        209,
        117,
        233,
        42,
        135,
        68,
        70,
        144,
        146,
        77,
        43,
        94,
    ],
    28: [
        1,
        252,
        9,
        28,
        13,
        18,
        251,
        208,
        150,
        103,
        174,
        100,
        41,
        167,
        12,
        247,
        56,
        117,
        119,
        233,
        127,
        181,
        100,
        121,
        147,
        176,
        74,
        58,
        197,
    ],
    30: [
        1,
        212,
        246,
        77,
        73,
        195,
        192,
        75,
        98,
        5,
        70,
        103,
        177,
        22,
        217,
        138,
        51,
        181,
        246,
        72,
        25,
        18,
        46,
        228,
        74,
        216,
        195,
        11,
        106,
        130,
        150,
    ],
}

EXP_TABLE = list(range(256))

LOG_TABLE = list(range(256))

for i in range(8):
    EXP_TABLE[i] = 1 << i

for i in range(8, 256):
    EXP_TABLE[i] = (
        EXP_TABLE[i - 4] ^ EXP_TABLE[i - 5] ^ EXP_TABLE[i - 6] ^ EXP_TABLE[i - 8]
    )

for i in range(255):
    LOG_TABLE[EXP_TABLE[i]] = i

RS_BLOCK_OFFSET = {
    ERROR_CORRECT_L: 0,
    ERROR_CORRECT_M: 1,
    ERROR_CORRECT_Q: 2,
    ERROR_CORRECT_H: 3,
}

RS_BLOCK_TABLE = (

    (1, 26, 19),
    (1, 26, 16),
    (1, 26, 13),
    (1, 26, 9),

    (1, 44, 34),
    (1, 44, 28),
    (1, 44, 22),
    (1, 44, 16),

    (1, 70, 55),
    (1, 70, 44),
    (2, 35, 17),
    (2, 35, 13),

    (1, 100, 80),
    (2, 50, 32),
    (2, 50, 24),
    (4, 25, 9),

    (1, 134, 108),
    (2, 67, 43),
    (2, 33, 15, 2, 34, 16),
    (2, 33, 11, 2, 34, 12),

    (2, 86, 68),
    (4, 43, 27),
    (4, 43, 19),
    (4, 43, 15),

    (2, 98, 78),
    (4, 49, 31),
    (2, 32, 14, 4, 33, 15),
    (4, 39, 13, 1, 40, 14),

    (2, 121, 97),
    (2, 60, 38, 2, 61, 39),
    (4, 40, 18, 2, 41, 19),
    (4, 40, 14, 2, 41, 15),

    (2, 146, 116),
    (3, 58, 36, 2, 59, 37),
    (4, 36, 16, 4, 37, 17),
    (4, 36, 12, 4, 37, 13),

    (2, 86, 68, 2, 87, 69),
    (4, 69, 43, 1, 70, 44),
    (6, 43, 19, 2, 44, 20),
    (6, 43, 15, 2, 44, 16),

    (4, 101, 81),
    (1, 80, 50, 4, 81, 51),
    (4, 50, 22, 4, 51, 23),
    (3, 36, 12, 8, 37, 13),

    (2, 116, 92, 2, 117, 93),
    (6, 58, 36, 2, 59, 37),
    (4, 46, 20, 6, 47, 21),
    (7, 42, 14, 4, 43, 15),

    (4, 133, 107),
    (8, 59, 37, 1, 60, 38),
    (8, 44, 20, 4, 45, 21),
    (12, 33, 11, 4, 34, 12),

    (3, 145, 115, 1, 146, 116),
    (4, 64, 40, 5, 65, 41),
    (11, 36, 16, 5, 37, 17),
    (11, 36, 12, 5, 37, 13),

    (5, 109, 87, 1, 110, 88),
    (5, 65, 41, 5, 66, 42),
    (5, 54, 24, 7, 55, 25),
    (11, 36, 12, 7, 37, 13),

    (5, 122, 98, 1, 123, 99),
    (7, 73, 45, 3, 74, 46),
    (15, 43, 19, 2, 44, 20),
    (3, 45, 15, 13, 46, 16),

    (1, 135, 107, 5, 136, 108),
    (10, 74, 46, 1, 75, 47),
    (1, 50, 22, 15, 51, 23),
    (2, 42, 14, 17, 43, 15),

    (5, 150, 120, 1, 151, 121),
    (9, 69, 43, 4, 70, 44),
    (17, 50, 22, 1, 51, 23),
    (2, 42, 14, 19, 43, 15),

    (3, 141, 113, 4, 142, 114),
    (3, 70, 44, 11, 71, 45),
    (17, 47, 21, 4, 48, 22),
    (9, 39, 13, 16, 40, 14),

    (3, 135, 107, 5, 136, 108),
    (3, 67, 41, 13, 68, 42),
    (15, 54, 24, 5, 55, 25),
    (15, 43, 15, 10, 44, 16),

    (4, 144, 116, 4, 145, 117),
    (17, 68, 42),
    (17, 50, 22, 6, 51, 23),
    (19, 46, 16, 6, 47, 17),

    (2, 139, 111, 7, 140, 112),
    (17, 74, 46),
    (7, 54, 24, 16, 55, 25),
    (34, 37, 13),

    (4, 151, 121, 5, 152, 122),
    (4, 75, 47, 14, 76, 48),
    (11, 54, 24, 14, 55, 25),
    (16, 45, 15, 14, 46, 16),

    (6, 147, 117, 4, 148, 118),
    (6, 73, 45, 14, 74, 46),
    (11, 54, 24, 16, 55, 25),
    (30, 46, 16, 2, 47, 17),

    (8, 132, 106, 4, 133, 107),
    (8, 75, 47, 13, 76, 48),
    (7, 54, 24, 22, 55, 25),
    (22, 45, 15, 13, 46, 16),

    (10, 142, 114, 2, 143, 115),
    (19, 74, 46, 4, 75, 47),
    (28, 50, 22, 6, 51, 23),
    (33, 46, 16, 4, 47, 17),

    (8, 152, 122, 4, 153, 123),
    (22, 73, 45, 3, 74, 46),
    (8, 53, 23, 26, 54, 24),
    (12, 45, 15, 28, 46, 16),

    (3, 147, 117, 10, 148, 118),
    (3, 73, 45, 23, 74, 46),
    (4, 54, 24, 31, 55, 25),
    (11, 45, 15, 31, 46, 16),

    (7, 146, 116, 7, 147, 117),
    (21, 73, 45, 7, 74, 46),
    (1, 53, 23, 37, 54, 24),
    (19, 45, 15, 26, 46, 16),

    (5, 145, 115, 10, 146, 116),
    (19, 75, 47, 10, 76, 48),
    (15, 54, 24, 25, 55, 25),
    (23, 45, 15, 25, 46, 16),

    (13, 145, 115, 3, 146, 116),
    (2, 74, 46, 29, 75, 47),
    (42, 54, 24, 1, 55, 25),
    (23, 45, 15, 28, 46, 16),

    (17, 145, 115),
    (10, 74, 46, 23, 75, 47),
    (10, 54, 24, 35, 55, 25),
    (19, 45, 15, 35, 46, 16),

    (17, 145, 115, 1, 146, 116),
    (14, 74, 46, 21, 75, 47),
    (29, 54, 24, 19, 55, 25),
    (11, 45, 15, 46, 46, 16),

    (13, 145, 115, 6, 146, 116),
    (14, 74, 46, 23, 75, 47),
    (44, 54, 24, 7, 55, 25),
    (59, 46, 16, 1, 47, 17),

    (12, 151, 121, 7, 152, 122),
    (12, 75, 47, 26, 76, 48),
    (39, 54, 24, 14, 55, 25),
    (22, 45, 15, 41, 46, 16),

    (6, 151, 121, 14, 152, 122),
    (6, 75, 47, 34, 76, 48),
    (46, 54, 24, 10, 55, 25),
    (2, 45, 15, 64, 46, 16),

    (17, 152, 122, 4, 153, 123),
    (29, 74, 46, 14, 75, 47),
    (49, 54, 24, 10, 55, 25),
    (24, 45, 15, 46, 46, 16),

    (4, 152, 122, 18, 153, 123),
    (13, 74, 46, 32, 75, 47),
    (48, 54, 24, 14, 55, 25),
    (42, 45, 15, 32, 46, 16),

    (20, 147, 117, 4, 148, 118),
    (40, 75, 47, 7, 76, 48),
    (43, 54, 24, 22, 55, 25),
    (10, 45, 15, 67, 46, 16),

    (19, 148, 118, 6, 149, 119),
    (18, 75, 47, 31, 76, 48),
    (34, 54, 24, 34, 55, 25),
    (20, 45, 15, 61, 46, 16),
)

def glog(n):
    if n < 1:
        raise ValueError("glog(%s)" % n)
    return LOG_TABLE[n]

def gexp(n):
    return EXP_TABLE[n % 255]

class Polynomial:
    def __init__(self, num, shift):
        if not num:
            raise Exception("%s/%s" % (len(num), shift))

        offset = 0
        for offset in range(len(num)):
            if num[offset] != 0:
                break

        self.num = num[offset:] + [0] * shift

    def __getitem__(self, index):
        return self.num[index]

    def __iter__(self):
        return iter(self.num)

    def __len__(self):
        return len(self.num)

    def __mul__(self, other):
        num = [0] * (len(self) + len(other) - 1)

        for i, item in enumerate(self):
            for j, other_item in enumerate(other):
                num[i + j] ^= gexp(glog(item) + glog(other_item))

        return Polynomial(num, 0)

    def __mod__(self, other):
        difference = len(self) - len(other)
        if difference < 0:
            return self

        ratio = glog(self[0]) - glog(other[0])

        num = [
            item ^ gexp(glog(other_item) + ratio)
            for item, other_item in zip(self, other)
        ]
        if difference:
            num.extend(self[-difference:])

        return Polynomial(num, 0) % other

class RSBlock(object):

    __slots__ = ("total_count", "data_count")

    def __init__(self, total_count, data_count):
        self.total_count = total_count
        self.data_count = data_count

    def __repr__(self):
        return "RSBlock(total_count=%r, data_count=%r)" % (
            self.total_count, self.data_count)

def _rs_blocks(version, error_correction):
    if error_correction not in RS_BLOCK_OFFSET:
        raise Exception(
            "bad rs block @ version: %s / error_correction: %s"
            % (version, error_correction)
        )
    offset = RS_BLOCK_OFFSET[error_correction]
    rs_block = RS_BLOCK_TABLE[(version - 1) * 4 + offset]

    blocks = []

    for i in range(0, len(rs_block), 3):
        count, total_count, data_count = rs_block[i : i + 3]
        for _ in range(count):
            blocks.append(RSBlock(total_count, data_count))

    return blocks

MODE_NUMBER = 1 << 0
MODE_ALPHA_NUM = 1 << 1
MODE_8BIT_BYTE = 1 << 2
MODE_KANJI = 1 << 3

MODE_SIZE_SMALL = {
    MODE_NUMBER: 10,
    MODE_ALPHA_NUM: 9,
    MODE_8BIT_BYTE: 8,
    MODE_KANJI: 8,
}
MODE_SIZE_MEDIUM = {
    MODE_NUMBER: 12,
    MODE_ALPHA_NUM: 11,
    MODE_8BIT_BYTE: 16,
    MODE_KANJI: 10,
}
MODE_SIZE_LARGE = {
    MODE_NUMBER: 14,
    MODE_ALPHA_NUM: 13,
    MODE_8BIT_BYTE: 16,
    MODE_KANJI: 12,
}

ALPHA_NUM = b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"
RE_ALPHA_NUM = re.compile(b"^[" + re.escape(ALPHA_NUM) + rb"]*\Z")

NUMBER_LENGTH = {3: 10, 2: 7, 1: 4}

PATTERN_POSITION_TABLE = [
    [],
    [6, 18],
    [6, 22],
    [6, 26],
    [6, 30],
    [6, 34],
    [6, 22, 38],
    [6, 24, 42],
    [6, 26, 46],
    [6, 28, 50],
    [6, 30, 54],
    [6, 32, 58],
    [6, 34, 62],
    [6, 26, 46, 66],
    [6, 26, 48, 70],
    [6, 26, 50, 74],
    [6, 30, 54, 78],
    [6, 30, 56, 82],
    [6, 30, 58, 86],
    [6, 34, 62, 90],
    [6, 28, 50, 72, 94],
    [6, 26, 50, 74, 98],
    [6, 30, 54, 78, 102],
    [6, 28, 54, 80, 106],
    [6, 32, 58, 84, 110],
    [6, 30, 58, 86, 114],
    [6, 34, 62, 90, 118],
    [6, 26, 50, 74, 98, 122],
    [6, 30, 54, 78, 102, 126],
    [6, 26, 52, 78, 104, 130],
    [6, 30, 56, 82, 108, 134],
    [6, 34, 60, 86, 112, 138],
    [6, 30, 58, 86, 114, 142],
    [6, 34, 62, 90, 118, 146],
    [6, 30, 54, 78, 102, 126, 150],
    [6, 24, 50, 76, 102, 128, 154],
    [6, 28, 54, 80, 106, 132, 158],
    [6, 32, 58, 84, 110, 136, 162],
    [6, 26, 54, 82, 110, 138, 166],
    [6, 30, 58, 86, 114, 142, 170],
]

G15 = (1 << 10) | (1 << 8) | (1 << 5) | (1 << 4) | (1 << 2) | (1 << 1) | (1 << 0)
G18 = (
    (1 << 12)
    | (1 << 11)
    | (1 << 10)
    | (1 << 9)
    | (1 << 8)
    | (1 << 5)
    | (1 << 2)
    | (1 << 0)
)
G15_MASK = (1 << 14) | (1 << 12) | (1 << 10) | (1 << 4) | (1 << 1)

PAD0 = 0xEC
PAD1 = 0x11

def _data_count(block):
    return block.data_count

BIT_LIMIT_TABLE = [
    [0]
    + [
        8 * sum(map(_data_count, _rs_blocks(version, error_correction)))
        for version in range(1, 41)
    ]
    for error_correction in range(4)
]

def BCH_type_info(data):
    d = data << 10
    while BCH_digit(d) - BCH_digit(G15) >= 0:
        d ^= G15 << (BCH_digit(d) - BCH_digit(G15))

    return ((data << 10) | d) ^ G15_MASK

def BCH_type_number(data):
    d = data << 12
    while BCH_digit(d) - BCH_digit(G18) >= 0:
        d ^= G18 << (BCH_digit(d) - BCH_digit(G18))
    return (data << 12) | d

def BCH_digit(data):
    digit = 0
    while data != 0:
        digit += 1
        data >>= 1
    return digit

def pattern_position(version):
    return PATTERN_POSITION_TABLE[version - 1]

def _mask_factory(pattern):

    if pattern == 0:
        return lambda i, j: (i + j) % 2 == 0
    if pattern == 1:
        return lambda i, j: i % 2 == 0
    if pattern == 2:
        return lambda i, j: j % 3 == 0
    if pattern == 3:
        return lambda i, j: (i + j) % 3 == 0
    if pattern == 4:
        return lambda i, j: (math.floor(i / 2) + math.floor(j / 3)) % 2 == 0
    if pattern == 5:
        return lambda i, j: (i * j) % 2 + (i * j) % 3 == 0
    if pattern == 6:
        return lambda i, j: ((i * j) % 2 + (i * j) % 3) % 2 == 0
    if pattern == 7:
        return lambda i, j: ((i * j) % 3 + (i + j) % 2) % 2 == 0
    raise TypeError("Bad mask pattern: " + pattern)

def mode_sizes_for_version(version):
    if version < 10:
        return MODE_SIZE_SMALL
    elif version < 27:
        return MODE_SIZE_MEDIUM
    else:
        return MODE_SIZE_LARGE

def length_in_bits(mode, version):
    if mode not in (MODE_NUMBER, MODE_ALPHA_NUM, MODE_8BIT_BYTE, MODE_KANJI):
        raise TypeError("Invalid mode (%s)" % mode)

    check_version(version)

    return mode_sizes_for_version(version)[mode]

def check_version(version):
    if version < 1 or version > 40:
        raise ValueError("Invalid version (was %s, expected 1 to 40)" % version)

def _lost_point(modules):
    modules_count = len(modules)

    lost_point = 0

    lost_point = _lost_point_level1(modules, modules_count)
    lost_point += _lost_point_level2(modules, modules_count)
    lost_point += _lost_point_level3(modules, modules_count)
    lost_point += _lost_point_level4(modules, modules_count)

    return lost_point

def _lost_point_level1(modules, modules_count):
    lost_point = 0

    modules_range = range(modules_count)
    container = [0] * (modules_count + 1)

    for row in modules_range:
        this_row = modules[row]
        previous_color = this_row[0]
        length = 0
        for col in modules_range:
            if this_row[col] == previous_color:
                length += 1
            else:
                if length >= 5:
                    container[length] += 1
                length = 1
                previous_color = this_row[col]
        if length >= 5:
            container[length] += 1

    for col in modules_range:
        previous_color = modules[0][col]
        length = 0
        for row in modules_range:
            if modules[row][col] == previous_color:
                length += 1
            else:
                if length >= 5:
                    container[length] += 1
                length = 1
                previous_color = modules[row][col]
        if length >= 5:
            container[length] += 1

    lost_point += sum(
        container[each_length] * (each_length - 2)
        for each_length in range(5, modules_count + 1)
    )

    return lost_point

def _lost_point_level2(modules, modules_count):
    lost_point = 0

    modules_range = range(modules_count - 1)
    for row in modules_range:
        this_row = modules[row]
        next_row = modules[row + 1]

        modules_range_iter = iter(modules_range)
        for col in modules_range_iter:
            top_right = this_row[col + 1]
            if top_right != next_row[col + 1]:

                next(modules_range_iter, None)
            elif top_right != this_row[col]:
                continue
            elif top_right != next_row[col]:
                continue
            else:
                lost_point += 3

    return lost_point

def _lost_point_level3(modules, modules_count):

    modules_range = range(modules_count)
    modules_range_short = range(modules_count - 10)
    lost_point = 0

    for row in modules_range:
        this_row = modules[row]
        modules_range_short_iter = iter(modules_range_short)
        col = 0
        for col in modules_range_short_iter:
            if (
                not this_row[col + 1]
                and this_row[col + 4]
                and not this_row[col + 5]
                and this_row[col + 6]
                and not this_row[col + 9]
                and (
                    this_row[col + 0]
                    and this_row[col + 2]
                    and this_row[col + 3]
                    and not this_row[col + 7]
                    and not this_row[col + 8]
                    and not this_row[col + 10]
                    or not this_row[col + 0]
                    and not this_row[col + 2]
                    and not this_row[col + 3]
                    and this_row[col + 7]
                    and this_row[col + 8]
                    and this_row[col + 10]
                )
            ):
                lost_point += 40

            if this_row[col + 10]:
                next(modules_range_short_iter, None)

    for col in modules_range:
        modules_range_short_iter = iter(modules_range_short)
        row = 0
        for row in modules_range_short_iter:
            if (
                not modules[row + 1][col]
                and modules[row + 4][col]
                and not modules[row + 5][col]
                and modules[row + 6][col]
                and not modules[row + 9][col]
                and (
                    modules[row + 0][col]
                    and modules[row + 2][col]
                    and modules[row + 3][col]
                    and not modules[row + 7][col]
                    and not modules[row + 8][col]
                    and not modules[row + 10][col]
                    or not modules[row + 0][col]
                    and not modules[row + 2][col]
                    and not modules[row + 3][col]
                    and modules[row + 7][col]
                    and modules[row + 8][col]
                    and modules[row + 10][col]
                )
            ):
                lost_point += 40
            if modules[row + 10][col]:
                next(modules_range_short_iter, None)

    return lost_point

def _lost_point_level4(modules, modules_count):
    dark_count = sum(map(sum, modules))
    percent = float(dark_count) / (modules_count**2)

    rating = int(abs(percent * 100 - 50) / 5)
    return rating * 10

def optimal_data_chunks(data, minimum=4):

    data = to_bytestring(data)
    num_pattern = rb"\d"
    alpha_pattern = b"[" + re.escape(ALPHA_NUM) + b"]"
    if len(data) <= minimum:
        num_pattern = re.compile(b"^" + num_pattern + b"+$")
        alpha_pattern = re.compile(b"^" + alpha_pattern + b"+$")
    else:
        re_repeat = b"{" + str(minimum).encode("ascii") + b",}"
        num_pattern = re.compile(num_pattern + re_repeat)
        alpha_pattern = re.compile(alpha_pattern + re_repeat)
    num_bits = _optimal_split(data, num_pattern)
    for is_num, chunk in num_bits:
        if is_num:
            yield QRData(chunk, mode=MODE_NUMBER, check_data=False)
        else:
            for is_alpha, sub_chunk in _optimal_split(chunk, alpha_pattern):
                mode = MODE_ALPHA_NUM if is_alpha else MODE_8BIT_BYTE
                yield QRData(sub_chunk, mode=mode, check_data=False)

def _optimal_split(data, pattern):
    while data:
        match = re.search(pattern, data)
        if not match:
            break
        start, end = match.start(), match.end()
        if start:
            yield False, data[:start]
        yield True, data[start:end]
        data = data[end:]
    if data:
        yield False, data

def to_bytestring(data):

    if not isinstance(data, bytes):
        data = str(data).encode("utf-8")
    return data

def optimal_mode(data):

    if data.isdigit():
        return MODE_NUMBER
    if RE_ALPHA_NUM.match(data):
        return MODE_ALPHA_NUM
    return MODE_8BIT_BYTE

class QRData:

    def __init__(self, data, mode=None, check_data=True):

        if check_data:
            data = to_bytestring(data)

        if mode is None:
            self.mode = optimal_mode(data)
        else:
            self.mode = mode
            if mode not in (MODE_NUMBER, MODE_ALPHA_NUM, MODE_8BIT_BYTE):
                raise TypeError("Invalid mode (%s)" % mode)
            if check_data and mode < optimal_mode(data):
                raise ValueError("Provided data can not be represented in mode %s" % mode)

        self.data = data

    def __len__(self):
        return len(self.data)

    def write(self, buffer):
        if self.mode == MODE_NUMBER:
            for i in range(0, len(self.data), 3):
                chars = self.data[i : i + 3]
                bit_length = NUMBER_LENGTH[len(chars)]
                buffer.put(int(chars), bit_length)
        elif self.mode == MODE_ALPHA_NUM:
            for i in range(0, len(self.data), 2):
                chars = self.data[i : i + 2]
                if len(chars) > 1:
                    buffer.put(
                        ALPHA_NUM.find(chars[0]) * 45 + ALPHA_NUM.find(chars[1]), 11
                    )
                else:
                    buffer.put(ALPHA_NUM.find(chars), 6)
        else:

            data = self.data
            for c in data:
                buffer.put(c, 8)

    def __repr__(self):
        return repr(self.data)

class BitBuffer:
    def __init__(self):
        self.buffer = []
        self.length = 0

    def __repr__(self):
        return ".".join([str(n) for n in self.buffer])

    def get(self, index):
        buf_index = math.floor(index / 8)
        return ((self.buffer[buf_index] >> (7 - index % 8)) & 1) == 1

    def put(self, num, length):
        for i in range(length):
            self.put_bit(((num >> (length - i - 1)) & 1) == 1)

    def __len__(self):
        return self.length

    def put_bit(self, bit):
        buf_index = self.length // 8
        if len(self.buffer) <= buf_index:
            self.buffer.append(0)
        if bit:
            self.buffer[buf_index] |= 0x80 >> (self.length % 8)
        self.length += 1

def create_bytes(buffer, rs_blocks):
    offset = 0

    maxDcCount = 0
    maxEcCount = 0

    dcdata = []
    ecdata = []

    for rs_block in rs_blocks:
        dcCount = rs_block.data_count
        ecCount = rs_block.total_count - dcCount

        maxDcCount = max(maxDcCount, dcCount)
        maxEcCount = max(maxEcCount, ecCount)

        current_dc = [0xFF & buffer.buffer[i + offset] for i in range(dcCount)]
        offset += dcCount

        if ecCount in rsPoly_LUT:
            rsPoly = Polynomial(rsPoly_LUT[ecCount], 0)
        else:
            rsPoly = Polynomial([1], 0)
            for i in range(ecCount):
                rsPoly = rsPoly * Polynomial([1, gexp(i)], 0)

        rawPoly = Polynomial(current_dc, len(rsPoly) - 1)

        modPoly = rawPoly % rsPoly
        current_ec = []
        mod_offset = len(modPoly) - ecCount
        for i in range(ecCount):
            modIndex = i + mod_offset
            current_ec.append(modPoly[modIndex] if (modIndex >= 0) else 0)

        dcdata.append(current_dc)
        ecdata.append(current_ec)

    data = []
    for i in range(maxDcCount):
        for dc in dcdata:
            if i < len(dc):
                data.append(dc[i])
    for i in range(maxEcCount):
        for ec in ecdata:
            if i < len(ec):
                data.append(ec[i])

    return data

def create_data(version, error_correction, data_list):
    buffer = BitBuffer()
    for data in data_list:
        buffer.put(data.mode, 4)
        buffer.put(len(data), length_in_bits(data.mode, version))
        data.write(buffer)

    rs_blocks = _rs_blocks(version, error_correction)
    bit_limit = sum(block.data_count * 8 for block in rs_blocks)
    if len(buffer) > bit_limit:
        raise DataOverflowError(
            "Code length overflow. Data size (%s) > size available (%s)"
            % (len(buffer), bit_limit)
        )

    for _ in range(min(bit_limit - len(buffer), 4)):
        buffer.put_bit(False)

    delimit = len(buffer) % 8
    if delimit:
        for _ in range(8 - delimit):
            buffer.put_bit(False)

    bytes_to_fill = (bit_limit - len(buffer)) // 8
    for i in range(bytes_to_fill):
        if i % 2 == 0:
            buffer.put(PAD0, 8)
        else:
            buffer.put(PAD1, 8)

    return create_bytes(buffer, rs_blocks)

def _check_box_size(size):
    if int(size) <= 0:
        raise ValueError("Invalid box size (was %s, expected larger than 0)" % size)

def _check_border(size):
    if int(size) < 0:
        raise ValueError("Invalid border (was %s, expected 0 or larger)" % size)

def _check_mask_pattern(mask_pattern):
    if mask_pattern is None:
        return
    if not 0 <= int(mask_pattern) <= 7:
        raise ValueError("Invalid mask pattern (was %s, expected 0 to 7)" % mask_pattern)

def copy_2d_array(x):
    return [row[:] for row in x]

ModulesType = list
precomputed_qr_blanks = {}

class QRCode(object):
    _version = None

    def __init__(
        self,
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=10,
        border=4,
        mask_pattern=None,
    ):
        _check_box_size(box_size)
        _check_border(border)
        self.version = version
        self.error_correction = int(error_correction)
        self.box_size = int(box_size)

        self.border = int(border)
        self.mask_pattern = mask_pattern
        self.clear()

    @property
    def version(self) -> int:
        if self._version is None:
            self.best_fit()
        return self._version

    @version.setter
    def version(self, value) -> None:
        if value is not None:
            value = int(value)
            check_version(value)
        self._version = value

    @property
    def mask_pattern(self):
        return self._mask_pattern

    @mask_pattern.setter
    def mask_pattern(self, pattern):
        _check_mask_pattern(pattern)
        self._mask_pattern = pattern

    def clear(self):

        self.modules = [[]]
        self.modules_count = 0
        self.data_cache = None
        self.data_list = []

    def add_data(self, data, optimize=20):

        if isinstance(data, QRData):
            self.data_list.append(data)
        elif optimize:
            self.data_list.extend(optimal_data_chunks(data, minimum=optimize))
        else:
            self.data_list.append(QRData(data))
        self.data_cache = None

    def make(self, fit=True):

        if fit or (self.version is None):
            self.best_fit(start=self.version)
        if self.mask_pattern is None:
            self.makeImpl(False, self.best_mask_pattern())
        else:
            self.makeImpl(False, self.mask_pattern)

    def makeImpl(self, test, mask_pattern):
        self.modules_count = self.version * 4 + 17

        if self.version in precomputed_qr_blanks:
            self.modules = copy_2d_array(precomputed_qr_blanks[self.version])
        else:
            self.modules = [
                [None] * self.modules_count for i in range(self.modules_count)
            ]
            self.setup_position_probe_pattern(0, 0)
            self.setup_position_probe_pattern(self.modules_count - 7, 0)
            self.setup_position_probe_pattern(0, self.modules_count - 7)
            self.setup_position_adjust_pattern()
            self.setup_timing_pattern()

            precomputed_qr_blanks[self.version] = copy_2d_array(self.modules)

        self.setup_type_info(test, mask_pattern)

        if self.version >= 7:
            self.setup_type_number(test)

        if self.data_cache is None:
            self.data_cache = create_data(
                self.version, self.error_correction, self.data_list
            )
        self.map_data(self.data_cache, mask_pattern)

    def setup_position_probe_pattern(self, row, col):
        for r in range(-1, 8):
            if row + r <= -1 or self.modules_count <= row + r:
                continue

            for c in range(-1, 8):
                if col + c <= -1 or self.modules_count <= col + c:
                    continue

                if (
                    (0 <= r <= 6 and c in {0, 6})
                    or (0 <= c <= 6 and r in {0, 6})
                    or (2 <= r <= 4 and 2 <= c <= 4)
                ):
                    self.modules[row + r][col + c] = True
                else:
                    self.modules[row + r][col + c] = False

    def best_fit(self, start=None):

        if start is None:
            start = 1
        check_version(start)

        mode_sizes = mode_sizes_for_version(start)
        buffer = BitBuffer()
        for data in self.data_list:
            buffer.put(data.mode, 4)
            buffer.put(len(data), mode_sizes[data.mode])
            data.write(buffer)

        needed_bits = len(buffer)
        self.version = bisect_left(
            BIT_LIMIT_TABLE[self.error_correction], needed_bits, start
        )
        if self.version == 41:
            raise DataOverflowError()

        if mode_sizes is not mode_sizes_for_version(self.version):
            self.best_fit(start=self.version)
        return self.version

    def best_mask_pattern(self):

        min_lost_point = 0
        pattern = 0

        for i in range(8):
            self.makeImpl(True, i)

            lost_point = _lost_point(self.modules)

            if i == 0 or min_lost_point > lost_point:
                min_lost_point = lost_point
                pattern = i

        return pattern

    def is_constrained(self, row: int, col: int) -> bool:
        return (
            row >= 0
            and row < len(self.modules)
            and col >= 0
            and col < len(self.modules[row])
        )

    def setup_timing_pattern(self):
        for r in range(8, self.modules_count - 8):
            if self.modules[r][6] is not None:
                continue
            self.modules[r][6] = r % 2 == 0

        for c in range(8, self.modules_count - 8):
            if self.modules[6][c] is not None:
                continue
            self.modules[6][c] = c % 2 == 0

    def setup_position_adjust_pattern(self):
        pos = pattern_position(self.version)

        for i in range(len(pos)):
            row = pos[i]

            for j in range(len(pos)):
                col = pos[j]

                if self.modules[row][col] is not None:
                    continue

                for r in range(-2, 3):
                    for c in range(-2, 3):
                        if (
                            r == -2
                            or r == 2
                            or c == -2
                            or c == 2
                            or (r == 0 and c == 0)
                        ):
                            self.modules[row + r][col + c] = True
                        else:
                            self.modules[row + r][col + c] = False

    def setup_type_number(self, test):
        bits = BCH_type_number(self.version)

        for i in range(18):
            mod = not test and ((bits >> i) & 1) == 1
            self.modules[i // 3][i % 3 + self.modules_count - 8 - 3] = mod

        for i in range(18):
            mod = not test and ((bits >> i) & 1) == 1
            self.modules[i % 3 + self.modules_count - 8 - 3][i // 3] = mod

    def setup_type_info(self, test, mask_pattern):
        data = (self.error_correction << 3) | mask_pattern
        bits = BCH_type_info(data)

        for i in range(15):
            mod = not test and ((bits >> i) & 1) == 1

            if i < 6:
                self.modules[i][8] = mod
            elif i < 8:
                self.modules[i + 1][8] = mod
            else:
                self.modules[self.modules_count - 15 + i][8] = mod

        for i in range(15):
            mod = not test and ((bits >> i) & 1) == 1

            if i < 8:
                self.modules[8][self.modules_count - i - 1] = mod
            elif i < 9:
                self.modules[8][15 - i - 1 + 1] = mod
            else:
                self.modules[8][15 - i - 1] = mod

        self.modules[self.modules_count - 8][8] = not test

    def map_data(self, data, mask_pattern):
        inc = -1
        row = self.modules_count - 1
        bitIndex = 7
        byteIndex = 0

        mask_func = _mask_factory(mask_pattern)

        data_len = len(data)

        for col in range(self.modules_count - 1, 0, -2):
            if col <= 6:
                col -= 1

            col_range = (col, col - 1)

            while True:
                for c in col_range:
                    if self.modules[row][c] is None:
                        dark = False

                        if byteIndex < data_len:
                            dark = ((data[byteIndex] >> bitIndex) & 1) == 1

                        if mask_func(row, c):
                            dark = not dark

                        self.modules[row][c] = dark
                        bitIndex -= 1

                        if bitIndex == -1:
                            byteIndex += 1
                            bitIndex = 7

                row += inc

                if row < 0 or self.modules_count <= row:
                    row -= inc
                    inc = -inc
                    break

    def get_matrix(self):

        if self.data_cache is None:
            self.make()

        if not self.border:
            return self.modules

        width = len(self.modules) + self.border * 2
        code = [[False] * width] * self.border
        x_border = [False] * self.border
        for module in self.modules:
            code.append(x_border + module + x_border)
        code += [[False] * width] * self.border

        return code

def qr_matrix(data, error_correction=ERROR_CORRECT_M, border=4):

    qr = QRCode(error_correction=error_correction, border=border)
    qr.add_data(data)
    qr.make(fit=True)
    return qr.get_matrix()

def qr_png(matrix, scale=4):

    rows = len(matrix)
    cols = len(matrix[0]) if rows else 0
    W = cols * scale
    H = rows * scale
    raw = bytearray()
    px_row = bytearray(W)
    for row in matrix:
        i = 0
        for v in row:
            if v:
                for k in range(scale):
                    px_row[i + k] = 0
            else:
                for k in range(scale):
                    px_row[i + k] = 255
            i += scale
        for _ in range(scale):
            raw.append(0)
            raw.extend(px_row)

    def chunk(tag, data):
        c = tag + data
        return (len(data)).to_bytes(4, "big") + c + \
            (zlib.crc32(c) & 0xFFFFFFFF).to_bytes(4, "big")

    ihdr = (W).to_bytes(4, "big") + (H).to_bytes(4, "big") + \
        bytes((8, 0, 0, 0, 0))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))

_PY_DATA = (
    "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"
    "8JNAf/r+rBJ8m9HXE5XXz70UqsqPrKhqX82//WLrhxXV3o+LVD9m/vF7/+r553qH6kfyX/7XF34E//kbj1r5h4Ra699Q/2Fx7aPi"
    "198ih9rw3yfG/4Yf63/5ta326Rj/+knw14ivN2vLT4v+urv2idJ/fu9fe36z+GtbXf24/vff1gZ16+euAvVPXfzn1476p/J/9dVS"
    "X3+u+pVX/yTZX78uaqg/ftb4lPe3YqEx+XG2sfxRFY1v0X+HDTS2P5Kz8S2hn0ScftyvYf/wYcP59qqfTly+Nv/miz9m/PMnLc9v"
    "0/9C70dIGv7PTQ6an2H5j59g9kfGNYs/ErX5aY7/+NZQs/1zw4fm5EcGNGc/bGuuf+Rec/Pvb/99pebu3weO/7bh9G2GX/i5xr9+"
    "ssH9uaVB89NQ//6ThE/IfvV1cfOTvX//SmgpP27c+tziN18jW992/8uf8OdGv/q6u1X+Docv1H/kdMv8YWXL/VHzreu/D3w0//4/"
    "fhLx/I7gn2REP1ysKz8amV7/eZKC/pH8x2+z0Nvf4H1/9/+ats7ltHYt/Gw5zjnxpJ20mSR+lztDx6ba9N4xNthgDKbZwNNE0n6L"
    "e/XJ69v3n2aPkJZW/VYhd02ac3fkZg6+8Bc4kJtBRT5ivQCP3IEbutk8nuhozQPsOHeXhwB/gHt568K+4Jf5LBwiaMlf0iTyVsdP"
    "wcm8pepfqFEeAciJPn9Dxc1bGX785HbvBEn9ySPk/sbRhTgZWLiiEhcsH35+BjMLYwlHfwp34B/oK1hefgdNRauYZ04gRSuxNyCq"
    "eImj3brBa4pdKBYOLNqYewJ7K51LxP1TSsDXgWslRBanZqUs/X7JEvgvPFXJ+q9THF2yt/yC3ZSa4BNUoNSm0pYW9E9lG53eOEaV"
    "U4izOK98hd3ue46aVrY3nmBZCQhq/VOxT//qllnqaqXCQFO548Mrvq5WrB89BXurGdpO1YLBf53VVic04OqcnKn17cH4WptRl+tl"
    "aBOW9tnvP0PidXvcD3CuPuA76vdAqnbZOGeAajSoVo02wAN41LD3fQcTG1aXfjr30xhDgbAEQ7+egLsNK86v+N6MCzr607SMOYUn"
    "aZYFGv9p3tCpNCfkZ9O+6gsOay4E+/xpWht2+tD0NaYVIj9bKb6vZSOJk3vrmre1AGFwQss+5G8wvGWt8zdua1tf9AaHtbMM1u0C"
    "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"
)

_PY = None
_PY_MAXOPT = 48

def _py():

    global _PY
    if _PY is not None:
        return _PY
    tab = {}
    try:
        import zlib as _z, base64 as _b, json as _j
        raw = _z.decompress(_b.b64decode("".join(_PY_DATA))).decode("utf-8")
        obj = _j.loads(raw)
        for letter, chars in obj["k"].items():
            for ch in chars:
                tab[ch] = letter
        for ch, letters in obj["m"].items():
            tab[ch] = letters
    except Exception:
        tab = {}
    _PY = tab
    return tab

def to_acronym(text, maxopt=None):

    tab = _py()
    if not tab:
        return []
    opts = []
    for ch in str(text or ""):
        if "a" <= ch <= "z" or "A" <= ch <= "Z":
            opts.append([ch.upper()])
        elif "0" <= ch <= "9":
            opts.append([ch])
        elif "\u4e00" <= ch <= "\u9fff":
            v = tab.get(ch)
            if not v:
                return []
            opts.append(list(v))
        else:
            continue
    if not opts:
        return []
    lim = maxopt or _PY_MAXOPT
    out = [""]
    for o in opts:
        nxt = []
        for pre in out:
            for c in o:
                nxt.append(pre + c)
        if len(nxt) > lim:
            nxt = nxt[:lim]
        out = nxt
    seen = set()
    res = []
    for s in out:
        if s not in seen:
            seen.add(s)
            res.append(s)
    return res

_UA_KUWO = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

IMG_FETCH_URL = "http://music.163.com/api/search/get/web"
IMG_FETCH_UA = "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/110 Mobile Safari/537.36"

LANGS = {1: "藏语", 2: "国语", 3: "韩语", 4: "日语", 5: "闽南语", 6: "英语",
         7: "粤语", 8: "其他", 9: "马来语", 10: "泰语", 11: "印尼语", 12: "越语",
         16: "其他2", 17: "外语", 18: "外语2", 19: "外语3"}

CATS = {1: "主题曲风", 2: "戏曲曲艺", 3: "综艺选秀", 4: "地方戏曲",
        5: "年代金曲", 6: "KTV推荐"}

class Spider(BaseSpider):

    def getName(self):
        return "爱KTV"

    def init(self, extend="", *args):

        try:
            if isinstance(extend, dict):
                sk = extend.get("siteKey")
                if sk:
                    _RP["skey"] = str(sk)
                    self.log("site key from extend: %s" % _RP["skey"])
                else:
                    self.log("extend keys: %s" % ",".join(str(k) for k in list(extend.keys())[:12]))
            elif isinstance(extend, str) and extend.strip():
                self.log("extend str: %s" % extend[:120])
        except Exception as e:
            self._dexc("extend siteKey", e)
        self._lock = threading.Lock()
        self._url_cache = {}
        self._cfg = None
        self._cfg_path = ""
        self._sig_cache = ("", 0)
        self._pic_cache = {}
        self._types_cache = None
        self._pic_locks = {}
        self._pic_guard = threading.Lock()
        self._py_hit = ""
        self._py_names = []
        self.cloud_force = False
        self._warm_busy = False
        self._warm_stop = False
        self._warm_stat = (0, 0, 0)
        self._order_lock = threading.Lock()

        if not getattr(self, "_httpd", None):
            self._httpd = None
        if not getattr(self, "_http_started", False):
            self._http_started = False
        try:
            self._ensure_dir(self.img_dir())
        except Exception:
            pass

        _RP["manual_stop"] = False
        if self._order_auto():
            try:
                self._order_start()
            except Exception as e:
                self.log("order auto start fail: %s" % e)

    def destroy(self):
        self._url_cache = {}

    def log(self, msg):
        try:
            print("[KTV] %s" % msg)
            sys.stdout.flush()
        except Exception:
            pass
        line = ""
        try:
            line = "%s %s" % (time.strftime("%m-%d %H:%M:%S"), msg)
        except Exception:
            line = str(msg)
        try:
            _LOGBUF.append(line)
            if len(_LOGBUF) > 400:
                del _LOGBUF[:200]
        except Exception:
            pass
        for d in self._log_dirs():
            try:
                with open(os.path.join(d, "_ktv.log"), "a") as f:
                    f.write(line + "\n")
                return
            except Exception:
                continue

    def _log_dirs(self):

        out = []
        try:
            d = os.path.dirname(self._cfg_file())
            if d:
                out.append(d)
        except Exception:
            pass
        try:
            ctx = self._app_ctx()
            if ctx is not None:
                for meth in ("getFilesDir", "getCacheDir", "getExternalFilesDir"):
                    try:
                        p = getattr(ctx, meth)()
                        if p:
                            out.append(str(p))
                    except Exception:
                        continue
        except Exception:
            pass
        out.append("/storage/emulated/0/Download")
        seen = set()
        res = []
        for x in out:
            if x and x not in seen:
                seen.add(x)
                res.append(x)
        return res

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(mkv|mp4|m3u8|ts)(\?|$)', str(url or ""), re.I))

    def manualVideoCheck(self):
        return False

    def db(self):

        p = str(self._cfg_get().get("db") or DB_PATH)
        if not os.path.exists(p):
            d = os.path.dirname(p) or "."
            if not os.path.isdir(d):
                raise IOError("数据库目录不存在: %s" % d)
        con = sqlite3.connect(p, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    def _db_health(self):

        p = str(self._cfg_get().get("db") or DB_PATH)
        if not os.path.exists(p):
            return False, "找不到数据库文件"
        if os.path.getsize(p) < 1024:
            return False, "数据库文件是空的（%d 字节）" % os.path.getsize(p)
        try:
            rows = self.query("SELECT COUNT(*) n FROM song")
            n = int(rows[0]["n"]) if rows else 0
        except Exception:
            return False, "打不开数据库"
        if n <= 0:
            return False, "数据库里没有歌曲"
        if not rows:
            return False, "读取歌曲表失败"
        return True, "%d 首歌" % n

    DB_HINTS = (
        GULU_DB_DIR,
        "/storage/emulated/0/TVData/db",
        "/storage/emulated/0/Download",
        "/storage/emulated/0",
        "/storage/emulated/0/Android/data/com.fongmi.android.tv/files",
        "/storage/emulated/0/Android/data/com.silent.android.webhtv/files",
    )

    def _probe_db(self, p):

        try:
            if not os.path.isfile(p):
                return None
            if os.path.getsize(p) < 1024 * 1024:
                return None
            con = sqlite3.connect(p, timeout=3)
            try:
                con.row_factory = sqlite3.Row
                try:

                    r = con.execute("SELECT COUNT(*) n FROM song").fetchone()
                except Exception:
                    r = None
                n = int(r["n"]) if r else 0
            finally:
                con.close()
            return n if n > 0 else None
        except Exception:
            return None

    def _find_db(self, limit=6, deep=2):

        hits, seen = [], set()
        for base in self.DB_HINTS:
            try:
                if not os.path.isdir(base):
                    continue
                cand = []
                try:
                    for f in os.listdir(base):
                        if f.lower().endswith(".db"):
                            cand.append(os.path.join(base, f))
                except Exception:
                    pass

                if deep and base.rstrip("/") != "/storage/emulated/0":
                    try:
                        for d in os.listdir(base):
                            sub = os.path.join(base, d)
                            if not os.path.isdir(sub):
                                continue
                            try:
                                for f in os.listdir(sub):
                                    if f.lower().endswith(".db"):
                                        cand.append(os.path.join(sub, f))
                            except Exception:
                                pass
                    except Exception:
                        pass
                for p in cand[:40]:
                    if p in seen:
                        continue
                    seen.add(p)
                    n = self._probe_db(p)
                    if n:
                        hits.append((p, n))
            except Exception:
                continue
        hits.sort(key=lambda x: -x[1])
        return hits[:limit]

    def _autofix_db(self):

        ok, _ = self._db_health()
        if ok:
            return None
        hits = self._find_db(limit=1)
        if not hits:
            return None
        self._cfg_set({"db": hits[0][0]})
        return hits

    def query(self, sql, args=(), limit=None):
        try:
            with self._lock:
                con = self.db()
                cur = con.execute(sql, args)
                rows = cur.fetchmany(limit) if limit else cur.fetchall()
                con.close()
                return [dict(r) for r in rows]
        except Exception as e:
            self.log("db error: %s (%s)" % (e, sql[:80]))
            return []

    def _types(self):

        if self._types_cache is None:
            d = {}
            try:
                for r in self.query("SELECT id,name FROM song_type ORDER BY category_id,id"):
                    if r["name"]:
                        d[int(r["id"])] = r["name"]
            except Exception as e:
                self.log("types fail: %s" % type(e).__name__)
            self._types_cache = d
        return self._types_cache

    def _cat_types(self, cid):

        rows = self.query(
            "SELECT t.id,t.name,COUNT(s.id) n FROM song_type t "
            "LEFT JOIN song s ON s.type_id=t.id AND s.status=1 "
            "WHERE t.category_id=? GROUP BY t.id ORDER BY n DESC", (int(cid),))
        return [(int(r["id"]), r["name"] or "", int(r["n"] or 0)) for r in rows]

    def _ensure_scnt(self):

        try:
            with self._lock:
                con = self.db()
                have = con.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='scnt'").fetchone()
                if have:
                    con.close()
                    return
                nid = {}
                for i, n in con.execute("SELECT id,name FROM singer"):
                    nid.setdefault(n, i)
                from collections import Counter
                cnt = Counter()
                for (sn,) in con.execute("SELECT singer_names FROM song"):
                    for p in re.split(r'[+,、/&]', sn or ""):
                        p = p.strip()
                        if p in nid:
                            cnt[nid[p]] += 1
                con.execute("CREATE TABLE IF NOT EXISTS scnt "
                            "(id INTEGER PRIMARY KEY, cnt INTEGER)")
                con.executemany("INSERT OR REPLACE INTO scnt VALUES (?,?)",
                                cnt.items())
                con.commit()
                con.close()
                self.log("scnt built: %d singers" % len(cnt))
        except Exception as e:
            self.log("scnt error: %s" % e)

    def _song_singers(self, names):

        return [s.strip() for s in re.split(r'[+,、/&]', names or "") if s.strip()]

    def _song_cover(self, singers, allow_fetch=True):

        d = self.img_dir()
        for s in singers[:3]:
            h = hashlib.md5(s.encode("utf-8")).hexdigest()
            if os.path.exists(os.path.join(d, h + ".img")):
                return "%s&type=singer&n=%s" % (self.proxy_url(), self.e64(s))
        if not allow_fetch:
            return ""
        for s in singers[:2]:
            if self._ensure_singer_img(s):
                return "%s&type=singer&n=%s" % (self.proxy_url(), self.e64(s))
        return ""

    def _ensure_singer_img(self, name):

        name = str(name or "").strip()
        if not name:
            return False
        with self._pic_guard:
            lk = self._pic_locks.get(name)
            if lk is None:
                lk = self._pic_locks[name] = threading.Lock()
        with lk:
            return self._ensure_singer_img_locked(name)

    def _ensure_singer_img_locked(self, name):
        h = hashlib.md5(name.encode("utf-8")).hexdigest()
        d = self.img_dir()
        p = os.path.join(d, h + ".img")
        if os.path.exists(p):
            return True
        n3 = os.path.join(d, h + ".n3")
        if os.path.exists(n3):

            try:
                try:
                    _days = int(self._cfg_get().get("n3ttl")
                                if self._cfg_get().get("n3ttl") is not None else 3)
                except Exception:
                    _days = 3
                if _days < 0:
                    _days = 0
                if _days > 0 and time.time() - os.path.getmtime(n3) < _days * 86400:
                    return False
            except Exception:
                return False
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            return False
        blob = self._fetch_singer_img(name, p)
        if blob:
            return True

        if getattr(self, "_warm_last_ioerr", False) is True:
            self._warm_last_ioerr = False
            return False
        try:
            with open(os.path.join(d, h + ".n3"), "wb") as f:
                f.write(b"\x01")
        except Exception:
            pass
        return False

    def song_card(self, row, allow_fetch=False):

        num = row["number"]
        singers = self._song_singers(row["singer_names"])
        pic = self._song_cover(singers, allow_fetch=allow_fetch)
        remark = LANGS.get(row.get("language_id"), "") or ""
        if row.get("temperature"):
            remark = (remark + " ") if remark else ""
            remark += "热" if row["temperature"] > 10000 else ""
        return {"vod_id": "s%d" % num, "vod_name": row["name"],
                "vod_pic": pic, "vod_remarks": remark.strip(),
                "vod_tag": None}

    def singer_card(self, row, cnt=0):
        name = row["name"]
        pic = "%s&type=singer&n=%s" % (self.proxy_url(), self.e64(name))
        return {"vod_id": "ar%d" % row["id"], "vod_name": name, "vod_pic": pic,
                "vod_remarks": ("%d首" % cnt) if cnt else "",
                "vod_tag": "folder"}

    @staticmethod
    def e64(s):
        return base64.urlsafe_b64encode(str(s).encode("utf-8")).decode("ascii").rstrip("=")

    def _page(self, items, pg, pages=None, total=None):

        return {"code": 1, "msg": "数据列表", "list": items,
                "page": pg, "pagecount": pages or 1,
                "limit": 30, "total": total if total is not None else len(items)}

    @staticmethod
    def d64(s):
        s = str(s or "")
        return base64.urlsafe_b64decode(s + "=" * ((4 - len(s) % 4) % 4)).decode("utf-8")

    def proxy_url(self):

        port = str(self._cfg_get().get("port") or "").strip()
        try:
            u = self.getProxyUrl()
            if u:
                if not port or port == "9978":
                    return u
                try:
                    from urllib.parse import urlsplit, urlunsplit
                    us = urlsplit(u)
                    if us.hostname in ("127.0.0.1", "localhost", "0.0.0.0"):
                        netloc = us.hostname + ":" + port
                        return urlunsplit((us.scheme, netloc, us.path,
                                           us.query, us.fragment))
                except Exception:
                    pass
                return u
        except Exception:
            pass
        return "http://127.0.0.1:%s/proxy?do=py" % (port or "9978")

    def aes_decrypt(self, b64text):
        data = base64.b64decode(b64text.strip())
        try:
            from Crypto.Cipher import AES
            pt = AES.new(AES_KEY, AES.MODE_ECB).decrypt(data)
            return pt[:-pt[-1]].decode("utf-8", "replace")
        except Exception:
            pass
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            c = Cipher(algorithms.AES(AES_KEY), modes.ECB()).decryptor()
            pt = c.update(data) + c.finalize()
            return pt[:-pt[-1]].decode("utf-8", "replace")
        except Exception as e:
            self.log("AES 不可用: %s" % type(e).__name__)
            return ""

    def aes_encrypt(self, plaintext):
        data = plaintext.encode("utf-8")
        pad = 16 - len(data) % 16
        data += bytes([pad]) * pad
        from Crypto.Cipher import AES
        return base64.b64encode(AES.new(AES_KEY, AES.MODE_ECB).encrypt(data)).decode()

    def get_validator(self):

        now = time.time()
        v, exp = self._sig_cache
        if v and now < exp:
            return v
        try:
            import requests
            ts = str(int(now * 1000))
            r = requests.get(SIGN_URL % ts, timeout=10, headers={"User-Agent": UA})
            v = r.text.strip()
            if v:
                self._sig_cache = (v, now + 480)
                return v
        except Exception as e:
            self.log("sign fail: %s" % type(e).__name__)
        return v

    def get_play_url(self, number):

        number = int(number)
        now = time.time()
        c = self._url_cache.get(number)
        if c and now < c[0]:
            return c[1], ""
        validator = self.get_validator()
        if not validator:
            return "", "签名服务不可用"
        body = self.aes_encrypt(json.dumps({"number": number}, separators=(",", ":")))
        try:
            import requests
            r = requests.post(PLAY_URL, data=body.encode(),
                              headers={"User-Agent": UA,
                                       "Content-Type": "application/json; charset=utf-8",
                                       "validator": validator},
                              timeout=15)
            raw = r.text.strip().strip('"')
            j = json.loads(self.aes_decrypt(raw))
            if str(j.get("statusCode")) == "1" and j.get("data", "").startswith("http"):
                url = j["data"]
                ttl = 600
                try:
                    ttl = max(60, int(self._cfg_get().get("urlcache") or 10) * 60)
                except Exception:
                    pass
                self._url_cache[number] = (now + ttl, url)
                if len(self._url_cache) > 300:
                    for k in list(self._url_cache)[:100]:
                        self._url_cache.pop(k, None)
                return url, ""
            return "", "statusCode=%s %s" % (j.get("statusCode"), j.get("message", ""))
        except Exception as e:
            self.log("play fail n=%s: %s" % (number, type(e).__name__))
            return "", type(e).__name__

    def homeContent(self, filter=False):
        classes = [
            {"type_id": "search", "type_name": "🔍 搜索"},
            {"type_id": "singer", "type_name": "🎤 歌手"},
            {"type_id": "lib", "type_name": "📚 歌库"},
            {"type_id": "settings", "type_name": "⚙ 设置"},
        ]
        filters = {}
        if filter:
            filters["singer"] = [
                {"key": "form", "name": "歌手",
                 "value": [{"n": "全部", "v": ""}, {"n": "男歌手", "v": "1"},
                           {"n": "女歌手", "v": "2"}, {"n": "组合", "v": "3"}]},
                {"key": "region", "name": "地区",
                 "value": [{"n": "全部", "v": ""}, {"n": "大陆", "v": "1"},
                           {"n": "港台", "v": "2"}, {"n": "国外", "v": "3"}]},
            ]
            filters["lib"] = [
                {"key": "lang", "name": "语种",
                 "value": [{"n": "全部", "v": ""}] +
                          [{"n": n, "v": str(k)} for k, n in
                           sorted(LANGS.items(),
                                  key=lambda x: -x[0] if x[0] == 2 else x[0])]},
                {"key": "type", "name": "曲风",
                 "value": [{"n": "全部", "v": ""}] +
                          [{"n": n, "v": str(k)} for k, n in
                           sorted(self._types().items(), key=lambda x: x[0])]},
                {"key": "sort", "name": "排序",
                 "value": [{"n": "热门优先", "v": ""},
                           {"n": "最新入库", "v": "new"}]},
            ]
        data = {"class": classes, "filters": filters}
        try:
            data["list"] = self.homeVideoContent().get("list", [])
        except Exception:
            data["list"] = []

        ok, info = self._db_health()
        if not ok:

            fixed = self._autofix_db()
            if fixed:
                ok, info = self._db_health()
                if ok:
                    try:
                        data["list"] = self.homeVideoContent().get("list", [])
                    except Exception:
                        data["list"] = []
                    return data
            c = self._note_card("help:db", "⚠ 数据库未就绪：" + info,
                                "点我看怎么处理", info)

            c["action"] = "help:db"
            data["list"] = [c]
        return data

    def homeVideoContent(self):

        return {"list": []}

    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        extend = extend or {}
        try:
            page = int(str(pg) or "1")
        except Exception:
            page = 1
        page = max(page, 1)
        size = 30
        off = (page - 1) * size
        tid = str(tid or "hot")

        if tid == "search":
            return self._search_page(page)
        if tid == "settings":
            return self._settings_page(page)
        if tid == "kw":
            return self._search_page(1)

        if tid.startswith("kw:"):
            self.log("category kw branch tid=%s" % tid)
            if tid == "kw:input":
                self._kw_ask()
                return self._page([self._kw_note("🔍搜索 · 输入关键词")], 1)
            if tid == "kw:clear":
                self._kw_set("")
                self.log("kw cleared")
                return self._page([self._kw_note("🔍搜索 · 已清除，下拉刷新生效")], 1)
            return self._page([self._kw_note("🔍搜索")], 1)
        if tid == "order":
            return self._order_detail_page()
        if tid.startswith("order:"):
            act = tid[6:]
            if act == "qr":
                self._order_show()
                return self._order_detail_page()
            if act == "list":
                self._queue_show()
                return self._order_queue_page()
            if act == "switch":
                self._order_toggle()
                return self._order_detail_page()
            if act == "auto":
                self._handle_setting("orderauto")
                return self._order_detail_page()
            if act == "port":

                self._handle_setting("orderport")
                return self._order_detail_page()

            if act == "fs":
                self._fs_toggle()
                return self._order_detail_page()
            return self._order_detail_page()

        if tid.startswith("set:"):
            self._handle_setting(tid[4:])
            return self._settings_page(1)

        if tid == "singer":
            form = extend.get("form") or ""
            region = extend.get("region") or ""
            w, args = [], []
            if form:
                w.append("form_id=?"); args.append(int(form))
            if region:
                w.append("region_id=?"); args.append(int(region))
            where = ("WHERE " + " AND ".join(w)) if w else ""
            self._ensure_scnt()
            rows = self.query(
                "SELECT s.id,s.name,IFNULL(x.cnt,0) cnt "
                "FROM singer s LEFT JOIN scnt x ON x.id=s.id %s "
                "ORDER BY length(s.name)>6 DESC, length(s.name)<2 DESC, cnt DESC "
                "LIMIT ? OFFSET ?" % where,
                args + [size, off])
            cards = [self.singer_card(r, r["cnt"]) for r in rows]
            return {"code": 1, "msg": "数据列表", "list": cards, "page": page,
                    "pagecount": page + (1 if len(cards) == size else 0),
                    "limit": size, "total": 999999}

        if tid == "lib":
            w, args = ["status=1"], []
            try:
                lang = int(extend.get("lang") or 0)
            except Exception:
                lang = 0
            try:
                typ = int(extend.get("type") or 0)
            except Exception:
                typ = 0
            if lang:
                w.append("language_id=?")
                args.append(lang)
            if typ:
                w.append("type_id=?")
                args.append(typ)
            order = "id DESC" if str(extend.get("sort") or "") == "new" \
                else "temperature DESC"
            rows = self.query(
                "SELECT number,name,singer_names,language_id,temperature FROM song "
                "WHERE " + " AND ".join(w) + " ORDER BY " + order +
                " LIMIT ? OFFSET ?", tuple(args) + (size, off))
            return self._song_page(rows, page, size, "歌库", "")

        if tid.startswith("ar"):
            sid = int(tid[2:])
            rows = self.query("SELECT id,name FROM singer WHERE id=?", (sid,))
            if not rows:
                return {"code": 1, "msg": "数据列表", "list": [], "page": page,
                        "pagecount": page, "limit": size, "total": 0}
            name = rows[0]["name"]
            songs = self.query(
                "SELECT number,name,singer_names,language_id,temperature FROM song "
                "WHERE instr(singer_names,?)>0 AND status=1 "
                "ORDER BY temperature DESC LIMIT ? OFFSET ?",
                (name, size, off))
            return self._song_page(songs, page, size, name, self.singer_pic(name))

        if tid == "lang":
            lid = int(extend.get("l") or 2)
            rows = self.query(
                "SELECT number,name,singer_names,language_id,temperature FROM song "
                "WHERE language_id=? AND status=1 ORDER BY temperature DESC LIMIT ? OFFSET ?",
                (lid, size, off))
            return self._song_page(rows, page, size, LANGS.get(lid, "语种"), "")
        if tid == "type":
            t = int(extend.get("t") or 1)
            rows = self.query(
                "SELECT number,name,singer_names,language_id,temperature FROM song "
                "WHERE type_id=? AND status=1 ORDER BY temperature DESC LIMIT ? OFFSET ?",
                (t, size, off))
            return self._song_page(rows, page, size, self._types().get(t, "曲风"), "")

        if tid.startswith("cat") and tid[3:].isdigit():
            cid = int(tid[3:])
            t = extend.get("t")
            if not t:
                opts = self._cat_types(cid)
                t = str(opts[0][0]) if opts else ""
            if not t:
                return self._page([], 1)
            ti = int(t)
            rows = self.query(
                "SELECT number,name,singer_names,language_id,temperature FROM song "
                "WHERE type_id=? AND status=1 ORDER BY temperature DESC LIMIT ? OFFSET ?",
                (ti, size, off))
            title = self._types().get(ti, CATS.get(cid, "曲风"))
            return self._song_page(rows, page, size, title, "")

        order = "temperature DESC" if tid == "hot" else "id DESC"
        lid = (extend.get("lang") or "")
        w = "WHERE status=1" + (" AND language_id=%s" % lid if lid else "")
        rows = self.query(
            "SELECT number,name,singer_names,language_id,temperature FROM song %s "
            "ORDER BY %s LIMIT ? OFFSET ?" % (w, order), (size, off))
        return self._song_page(rows, page, size, "热门歌曲" if tid == "hot" else "最新歌曲", "")

    def _song_page(self, rows, page, size, title, pic_hint="", total=0):
        cards = []
        for r in rows:
            c = self.song_card(r)
            if pic_hint and not c["vod_pic"]:
                c["vod_pic"] = pic_hint
            cards.append(c)

        pages = 999 if len(cards) >= size else page
        if total:

            pages = max(1, (total + size - 1) // size)
            if pages < page:
                pages = page
        return {"code": 1, "msg": "数据列表", "list": cards, "page": page,
                "pagecount": pages, "limit": size, "total": total or 999999}

    def singer_pic(self, name):
        h = hashlib.md5(name.encode("utf-8")).hexdigest()
        if os.path.exists(os.path.join(self.img_dir(), h + ".img")):
            return "%s&type=singer&n=%s" % (self.proxy_url(), self.e64(name))
        return ""

    def _cfg_file(self):

        if getattr(self, "_cfg_path", ""):
            return self._cfg_path
        cands = []
        try:
            d = os.path.dirname(os.path.abspath(__file__))
            if d and os.path.isdir(d):
                cands.append(os.path.join(d, "_aiKTV_cfg.json"))
        except Exception:
            pass
        cands.append("/storage/emulated/0/Download/_aiKTV_cfg.json")
        cands.append("/sdcard/Download/_aiKTV_cfg.json")
        cands.append(os.path.join(os.getcwd(), "_aiKTV_cfg.json"))
        for p in cands:
            try:
                if p and os.path.isdir(os.path.dirname(p)):
                    with open(p, "a", encoding="utf-8"):
                        pass
                    self._cfg_path = p
                    return p
            except Exception:
                continue
        self._cfg_path = cands[0] if cands else "_aiKTV_cfg.json"
        return self._cfg_path

    def _cfg_get(self):
        if self._cfg is None:
            self._cfg = {}
            try:
                with open(self._cfg_file(), "r", encoding="utf-8") as f:
                    self._cfg = json.load(f) or {}
            except Exception:
                pass
        return self._cfg

    def _cfg_set(self, kv):
        cfg = self._cfg_get()
        cfg.update(kv)
        self._cfg = cfg
        try:
            with open(self._cfg_file(), "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=1)
        except Exception as e:
            self.log("cfg save fail: %s" % e)
        return cfg

    def _hist_get(self):
        try:
            h = self._cfg_get().get("hist") or []
        except Exception:
            h = []
        out = []
        for x in h:
            x = str(x).strip()[:30]
            if x and x not in out:
                out.append(x)
        return out[:12]

    def _hist_add(self, kw):
        kw = str(kw or "").strip()[:30]
        if not kw:
            return
        h = self._hist_get()
        if h and h[0] == kw:
            return
        while kw in h:
            h.remove(kw)
        h.insert(0, kw)
        self._cfg_set({"hist": h[:12]})

    def _kw_get(self):
        return str(self._cfg_get().get("kw") or "")[:30]

    def _kw_set(self, kw):
        self._cfg_set({"kw": str(kw or "").strip()[:30]})
        return self._kw_get()

    def _kw_ask(self):

        cur = self._kw_get()
        self.log("kw_ask enter cur=%r" % cur)

        def _ok(t):
            self._kw_set(t)
            self.log("kw_ask saved=%r" % t)

        try:
            ok, err = self._input_dialog("🔍 输入搜索词", "歌名/歌手/首字母，多个词用空格隔开", cur, _ok,
                                         toast="已保存，下拉刷新生效")
            self.log("kw_ask dialog ok=%s err=%s" % (ok, err))
            return (bool(ok), str(err or ""))
        except Exception as e:
            self.log("kw_ask EXC %r" % (e,))
            return (False, repr(e))

    def action(self, action, value=None):
        a = str(action or "").strip().lower()
        v = str(value or "").strip()
        self.log("action dispatch a=%s v=%s" % (a, v))

        if a in ("help:db", "help_db"):
            self._show_db_help()
            return ""
        if a in ("kw", "kw_input", "site_kw"):
            ok, why = self._kw_ask()
            if not ok:
                self._toast("弹输入框失败:%s" % why)
            return ""
        if a in ("kwclear", "kw_clear"):
            self._kw_set("")
            self._toast("已清除搜索词，下拉刷新生效")
            return ""
        if a in ("kwstat", "kw_stat"):
            ok, why = self._kw_stat()
            if not ok:
                self._toast("统计弹窗失败:%s" % (why or "无结果"))
            return ""

        if a in ("order:switch", "orderswitch"):
            self._order_toggle()
            return ""
        if a.startswith("set:"):
            key = a[4:].strip()
            if not key and v.startswith("set:"):
                key = v[4:].strip()
            if key:
                self._handle_setting(key)
            return ""
        return ""

    def _toast(self, msg):
        try:
            from java import jclass, dynamic_proxy
            from java.lang import Runnable

            act = self._activity()
            if not act:
                return
            Toast = jclass("android.widget.Toast")

            class Run(dynamic_proxy(Runnable)):
                def __init__(self, fn):
                    super().__init__()
                    self.fn = fn

                def run(self):
                    self.fn()

            act.getWindow().getDecorView().post(
                Run(lambda: Toast.makeText(act, str(msg), 1).show()))
        except Exception as e:
            self.log("toast fail %r" % (e,))

    def _kw_note(self, title, body=None):

        kw = self._kw_get()
        if body is None:
            if kw:
                body = ("输入框已在后台尝试弹出，确定后**重新进「🔍搜索」分类**出结果。\n\n"
                        "当前搜索词：%s\n\n"
                        "如果输入框一直弹不出来，用壳顶部的搜索按钮，效果一样（同一接口）。" % kw)
            else:
                body = ("输入框已在后台尝试弹出，确定后**重新进「🔍搜索」分类**出结果。\n\n"
                        "如果输入框一直弹不出来，用壳顶部的搜索按钮，效果一样（同一接口）。")
        return {"vod_id": "kw:note", "vod_name": title, "vod_pic": "",
                "vod_remarks": ("当前词:%s" % kw) if kw else "", "vod_actor": "",
                "vod_content": body.strip()}

    def _activity(self, prefer=None):

        acts = []
        try:
            from java import jclass
            JClass = jclass("java.lang.Class")
            AT = JClass.forName("android.app.ActivityThread")
            cur = AT.getMethod("currentActivityThread").invoke(None)
            f = AT.getDeclaredField("mActivities")
            f.setAccessible(True)
            for r in f.get(cur).values().toArray():
                rc = r.getClass()
                pf = rc.getDeclaredField("paused")
                pf.setAccessible(True)
                af = rc.getDeclaredField("activity")
                af.setAccessible(True)
                a = af.get(r)
                if a is None:
                    continue
                try:
                    if a.isFinishing():
                        continue
                except Exception:
                    pass
                acts.append((str(a.getClass().getName()).lower(), a,
                             bool(pf.getBoolean(r))))
        except Exception:
            pass
        if not acts:
            return None
        acts.sort(key=lambda x: x[2])
        if prefer:
            for cls, a, _ in acts:
                if prefer in cls:
                    return a
        return acts[0][1]

    def _input_dialog(self, title, hint, cur, on_ok, toast="已保存，重新进分类生效"):

        try:
            from java import jclass, dynamic_proxy
            act = self._activity()
            if act is None:
                return False, "未找到窗口上下文"
            Toast = jclass("android.widget.Toast")
            ET = jclass("android.widget.EditText")
            OCL = jclass("android.content.DialogInterface$OnClickListener")
            RL = jclass("java.lang.Runnable")
            try:
                AB = jclass("com.google.android.material.dialog.MaterialAlertDialogBuilder")
            except Exception:
                AB = jclass("android.app.AlertDialog$Builder")
            refs = getattr(self, "_dialog_refs", None)
            if refs is None:
                refs = self._dialog_refs = []

            class Ok(dynamic_proxy(OCL)):
                def __init__(self, edit):
                    super().__init__()
                    self.edit = edit

                def onClick(self, d, w):
                    try:
                        txt = str(self.edit.getText().toString()).strip()
                    except Exception:
                        txt = ""
                    on_ok(txt)
                    try:
                        Toast.makeText(act, toast, 1).show()
                    except Exception:
                        pass
                    try:
                        d.dismiss()
                    except Exception:
                        pass

            class Cancel(dynamic_proxy(OCL)):
                def onClick(self, d, w):
                    return None

            class Show(dynamic_proxy(RL)):
                def run(self):
                    try:
                        et = ET(act)
                        if cur:
                            et.setText(cur)
                            et.setSelection(len(cur))
                        et.setHint(hint)
                        et.setSingleLine(True)
                        ok = Ok(et)
                        b = AB(act)
                        b.setTitle(title)
                        b.setView(et)
                        b.setPositiveButton("确定", ok)
                        b.setNegativeButton("取消", Cancel())
                        dlg = b.show()
                        et.requestFocus()
                        refs.extend([et, ok, dlg])
                        del refs[:-12]
                    except Exception as e:
                        try:
                            Toast.makeText(act, "输入框打开失败:%s" % str(e)[:60], 1).show()
                        except Exception:
                            pass

            sh = Show()
            refs.append(sh)
            del refs[:-12]
            act.runOnUiThread(sh)
            return True, ""
        except Exception as e:
            return False, str(e)[:60]

    def _kw_stat(self):

        kw = self._kw_get()
        if not kw:
            return False, ""
        res = self.searchContent(kw, False, "1")
        total = int(res.get("total") or 0)
        pages = max(1, int(res.get("pagecount") or 1))
        pyhit = getattr(self, "_py_hit", "")
        body = self._kw_stat_body(kw, total, pages, pyhit)
        r = self._info_dialog("📊 搜索统计", body, kw)
        if r is None or r is True or r == "":
            return True, ""
        if isinstance(r, tuple):
            return (r[0], r[1] if len(r) > 1 else "")
        return True, ""

    def _info_dialog(self, title, body, copy_text=None, qr_bytes=None):

        try:
            from java import jclass, dynamic_proxy
            act = self._activity()
            if act is None:
                return False, "没有窗口上下文"
            Toast = jclass("android.widget.Toast")
            TV = jclass("android.widget.TextView")
            SV = jclass("android.widget.ScrollView")
            LL = jclass("android.widget.LinearLayout")
            IV = jclass("android.widget.ImageView")
            BMP = jclass("android.graphics.BitmapFactory")
            GRAV = jclass("android.view.Gravity")
            OCL = jclass("android.content.DialogInterface$OnClickListener")
            RL = jclass("java.lang.Runnable")
            try:
                AB = jclass("com.google.android.material.dialog.MaterialAlertDialogBuilder")
            except Exception:
                AB = jclass("android.app.AlertDialog$Builder")
            refs = getattr(self, "_dialog_refs", None)
            if refs is None:
                refs = self._dialog_refs = []

            body = str(body)
            copy_text = str(copy_text or "")
            qr_bytes = bytes(qr_bytes) if qr_bytes else b""

            class Show(dynamic_proxy(RL)):
                def run(self):
                    try:
                        d = act.getResources().getDisplayMetrics().density
                        pad = int(16 * d)
                        tv = TV(act)
                        tv.setText(body)
                        tv.setTextSize(14.0)
                        tv.setTextIsSelectable(True)
                        tv.setPadding(pad, pad // 2, pad, pad // 2)
                        sv = SV(act)
                        if qr_bytes:
                            try:
                                bm = BMP.decodeByteArray(qr_bytes, 0,
                                                         len(qr_bytes))
                                if bm is not None:
                                    box = LL(act)
                                    box.setOrientation(LL.VERTICAL)
                                    box.setGravity(GRAV.CENTER_HORIZONTAL)
                                    iv = IV(act)
                                    side = int(300 * d)
                                    iv.setImageBitmap(bm)
                                    iv.setLayoutParams(LL.LayoutParams(
                                        side, side))
                                    box.addView(iv)
                                    box.addView(tv)
                                    sv.addView(box)
                                else:
                                    sv.addView(tv)
                            except Exception:
                                sv.addView(tv)
                        else:
                            sv.addView(tv)
                        b = AB(act)
                        b.setTitle(title)
                        b.setView(sv)
                        if copy_text:
                            class Copy(dynamic_proxy(OCL)):
                                def onClick(self, dlg, w):
                                    try:
                                        cb = act.getSystemService("clipboard")
                                        cb.setPrimaryClip(
                                            jclass("android.content.ClipData")
                                            .newPlainText("路径", copy_text))
                                        Toast.makeText(act, "路径已复制", 0).show()
                                    except Exception as e:
                                        try:
                                            Toast.makeText(act, "复制失败: %s"
                                                           % str(e)[:40], 1).show()
                                        except Exception:
                                            pass
                            cp = Copy()
                            b.setPositiveButton("复制路径", cp)
                            refs.append(cp)
                        b.setNegativeButton("关闭", None)
                        dlg = b.show()
                        refs.extend([tv, sv, dlg])
                        del refs[:-16]
                    except Exception as e:
                        try:
                            Toast.makeText(act, "弹窗失败: %s" % str(e)[:40], 1).show()
                        except Exception:
                            pass

            sh = Show()
            refs.append(sh)
            del refs[:-16]
            act.runOnUiThread(sh)
            return True, ""
        except Exception as e:
            return False, str(e)[:60]

    def _confirm_dialog(self, title, body, on_ok):

        try:
            from java import jclass, dynamic_proxy
            act = self._activity()
            if act is None:
                return False, "没有窗口上下文"
            Toast = jclass("android.widget.Toast")
            TV = jclass("android.widget.TextView")
            SV = jclass("android.widget.ScrollView")
            OCL = jclass("android.content.DialogInterface$OnClickListener")
            RL = jclass("java.lang.Runnable")
            try:
                AB = jclass("com.google.android.material.dialog.MaterialAlertDialogBuilder")
            except Exception:
                AB = jclass("android.app.AlertDialog$Builder")
            refs = getattr(self, "_dialog_refs", None)
            if refs is None:
                refs = self._dialog_refs = []
            body = str(body)

            class Ok(dynamic_proxy(OCL)):
                def onClick(self, dlg, w):
                    try:
                        on_ok()
                    except Exception as e:
                        self.log("confirm cb fail %r" % (e,))
                    try:
                        dlg.dismiss()
                    except Exception:
                        pass

            class Show(dynamic_proxy(RL)):
                def run(self):
                    try:
                        tv = TV(act)
                        tv.setText(body)
                        tv.setTextSize(14.0)
                        tv.setTextIsSelectable(True)
                        d = act.getResources().getDisplayMetrics().density
                        pad = int(16 * d)
                        tv.setPadding(pad, pad // 2, pad, pad // 2)
                        sv = SV(act)
                        sv.addView(tv)
                        ok = Ok()
                        b = AB(act)
                        b.setTitle(title)
                        b.setView(sv)
                        b.setPositiveButton("确定", ok)
                        b.setNegativeButton("取消", None)
                        dlg = b.show()
                        refs.extend([tv, sv, ok, dlg])
                        del refs[:-16]
                    except Exception as e:
                        try:
                            Toast.makeText(act, "弹窗失败: %s" % str(e)[:40], 1).show()
                        except Exception:
                            pass

            sh = Show()
            refs.append(sh)
            del refs[:-16]
            act.runOnUiThread(sh)
            return True, ""
        except Exception as e:
            return False, str(e)[:60]

    def _choose_dialog(self, title, body, labels, values):

        try:
            from java import jclass, dynamic_proxy
            act = self._activity()
            if act is None:
                return False, "没有窗口上下文"
            Toast = jclass("android.widget.Toast")
            TV = jclass("android.widget.TextView")
            SV = jclass("android.widget.ScrollView")
            OCL = jclass("android.content.DialogInterface$OnClickListener")
            RL = jclass("java.lang.Runnable")
            try:
                AB = jclass("com.google.android.material.dialog.MaterialAlertDialogBuilder")
            except Exception:
                AB = jclass("android.app.AlertDialog$Builder")
            refs = getattr(self, "_dialog_refs", None)
            if refs is None:
                refs = self._dialog_refs = []
            body = str(body)
            labels = [str(x) for x in (labels or [])]
            values = [str(x) for x in (values or [])]
            owner = self

            class Show(dynamic_proxy(RL)):
                def run(self):
                    try:
                        tv = TV(act)
                        tv.setText(body)
                        tv.setTextSize(14.0)
                        tv.setTextIsSelectable(True)
                        d = act.getResources().getDisplayMetrics().density
                        pad = int(16 * d)
                        tv.setPadding(pad, pad // 2, pad, pad // 2)
                        sv = SV(act)
                        sv.addView(tv)
                        b = AB(act)
                        b.setTitle(title)
                        b.setView(sv)

                        for i in range(min(len(labels), len(values))):
                            def make(idx):
                                class Pick(dynamic_proxy(OCL)):
                                    def onClick(self, dlg, w):
                                        try:
                                            owner._cfg_set({"db": values[idx]})
                                            ok, info = owner._db_health()
                                            msg = ("已切换：%s" % info) if ok else "切换失败"
                                            Toast.makeText(act, msg, 0).show()
                                        except Exception as e:
                                            try:
                                                Toast.makeText(act, "切换失败: %s"
                                                               % str(e)[:40], 1).show()
                                            except Exception:
                                                pass
                                return Pick()
                            pb = make(i)
                            refs.append(pb)
                            if i == 0:
                                b.setPositiveButton(labels[i], pb)
                            elif i == 1:
                                b.setNegativeButton(labels[i], pb)
                            elif i == 2:
                                b.setNeutralButton(labels[i], pb)
                        dlg = b.show()
                        refs.extend([tv, sv, dlg])
                        del refs[:-16]
                    except Exception as e:
                        try:
                            Toast.makeText(act, "弹窗失败: %s" % str(e)[:40], 1).show()
                        except Exception:
                            pass

            sh = Show()
            refs.append(sh)
            del refs[:-16]
            act.runOnUiThread(sh)
            return True, ""
        except Exception as e:
            return False, str(e)[:60]

    def _db_list_dialog(self, hits, cur):

        try:
            from java import jclass, dynamic_proxy
            act = self._activity()
            if act is None:
                return False, "未找到窗口上下文"
            Toast = jclass("android.widget.Toast")
            TV = jclass("android.widget.TextView")
            SV = jclass("android.widget.ScrollView")
            LL = jclass("android.widget.LinearLayout")
            LLP = jclass("android.widget.LinearLayout$LayoutParams")
            OCL = jclass("android.view.View$OnClickListener")
            RL = jclass("java.lang.Runnable")
            Color = jclass("android.graphics.Color")
            try:
                AB = jclass("com.google.android.material.dialog.MaterialAlertDialogBuilder")
            except Exception:
                AB = jclass("android.app.AlertDialog$Builder")

            owner = self
            refs = getattr(self, "_dialog_refs", None)
            if refs is None:
                refs = self._dialog_refs = []

            rows = []
            seen = set()
            for p, n in hits:
                if p in seen:
                    continue
                seen.add(p)
                rows.append((p, n))
            if cur and cur not in seen:
                rows.insert(0, (cur, self._probe_db(cur)))

            class Tap(dynamic_proxy(OCL)):
                def __init__(self, path, dlg_holder):
                    super().__init__()
                    self.path = path
                    self.holder = dlg_holder

                def onClick(self, v):
                    try:
                        self.holder[0].dismiss()
                    except Exception:
                        pass
                    owner._cfg_set({"db": self.path})
                    try:
                        Toast.makeText(act, "已切到 %s" % os.path.basename(self.path), 1).show()
                    except Exception:
                        pass

            class ManualTap(dynamic_proxy(OCL)):
                def __init__(self, dlg_holder):
                    super().__init__()
                    self.holder = dlg_holder

                def onClick(self, v):
                    try:
                        self.holder[0].dismiss()
                    except Exception:
                        pass
                    owner._input_dialog("歌曲库路径", "填 .db 完整路径",
                                        owner._cfg.get("db", "") or "",
                                        lambda t: owner._cfg_set({"db": t.strip()}),
                                        "路径已保存")

            class Show(dynamic_proxy(RL)):
                def run(self):
                    try:
                        dlg_holder = [None]
                        box = LL(act)
                        box.setOrientation(1)
                        for idx, (p, n) in enumerate(rows):
                            is_cur = (p == cur)
                            base = os.path.basename(p)

                            line = ("✓  " if is_cur else "    ") + base
                            if n:
                                line += "   （%d 首）" % n
                            line += "\n" + p

                            tv = TV(act)
                            tv.setText(line)
                            tv.setTextSize(14)
                            tv.setPadding(36, 26, 36, 26)
                            if is_cur:
                                tv.setTextColor(Color.parseColor("#1B5E20"))
                                tv.setBackgroundColor(Color.parseColor("#E8F5E9"))
                            else:
                                tv.setTextColor(Color.parseColor("#212121"))
                            lp = LLP(-1, -2)
                            tv.setLayoutParams(lp)
                            tv.setOnClickListener(Tap(p, dlg_holder))
                            box.addView(tv)
                            refs.append(tv)

                            if idx < len(rows) - 1:
                                sep = TV(act)
                                sep.setHeight(1)
                                sep.setBackgroundColor(Color.parseColor("#EEEEEE"))
                                box.addView(sep, LLP(-1, 1))
                                refs.append(sep)

                        sep2 = TV(act)
                        sep2.setHeight(1)
                        sep2.setBackgroundColor(Color.parseColor("#CCCCCC"))
                        box.addView(sep2, LLP(-1, 1))
                        mt = TV(act)
                        mt.setText("✎  手动输入路径…")
                        mt.setTextSize(14)
                        mt.setTextColor(Color.parseColor("#1565C0"))
                        mt.setPadding(36, 26, 36, 26)
                        mt.setOnClickListener(ManualTap(dlg_holder))
                        box.addView(mt)
                        refs.append(mt)

                        sv = SV(act)
                        sv.addView(box, LLP(-1, -2))
                        b = AB(act)
                        b.setTitle("选择歌曲库（共 %d 个）" % len(rows))
                        b.setView(sv)
                        b.setNegativeButton("取消", None)
                        dlg = b.show()
                        dlg_holder[0] = dlg
                        refs.extend([box, sv, dlg])
                        del refs[:-40]
                    except Exception as e:
                        try:
                            Toast.makeText(act, "列表打开失败:%s" % str(e)[:60], 1).show()
                        except Exception:
                            pass

            sh = Show()
            refs.append(sh)
            del refs[:-40]
            act.runOnUiThread(sh)
            return True, ""
        except Exception as e:
            return False, "%s: %s" % (type(e).__name__, str(e)[:60])

    def _show_db_help(self):

        ok, info = self._db_health()
        p = str(self._cfg_get().get("db") or DB_PATH)
        hits = self._find_db(limit=20)

        if ok:
            if len(hits) <= 1:
                self._toast("数据库正常：%s（只找到这一个库）" % info)
                return
            okd, why = self._db_list_dialog(hits, p)
            if not okd:
                self._toast("列表打不开(%s)" % why)
            return
        if hits:
            body = (
                "当前路径用不了：%s\n"
                "（%s）\n\n"
                "不过在手机上找到了 %d 个可用的歌曲库，\n"
                "直接点下面按钮选一个就行，不用手动找路径：\n\n"
                "%s\n"
                "选好后回首页下拉刷新，这张卡会自动消失。"
            ) % (p, info, len(hits),
                 "\n".join("%d. %s\n   %d 首歌" % (i + 1, h[0], h[1])
                           for i, h in enumerate(hits)))
            labels = ["用第 %d 个" % (i + 1) for i in range(min(len(hits), 3))]
            paths = [h[0] for h in hits]
            okd, why = self._choose_dialog("发现可用歌曲库", body, labels, paths)
            if not okd:
                self._toast("弹窗打不开(%s)，请进设置手动改路径" % why)
            return
        body = (
            "当前路径：\n%s\n\n"
            "状态：%s\n\n"
            "在手机的常见位置都没找到歌曲库。\n"
            "这个脚本本身不带库，库（song_9c8ec.db，约 120MB）要单独放进来。\n\n"
            "可以做的：\n"
            "1. 从旧手机把整个 TVData/db 文件夹搬过来，路径不变就不用改\n"
            "2. 或者进 ⚙ 设置 → 📁 数据库文件路径，手动填 .db 的完整路径\n"
            "3. 确认目录存在、文件名写全（含 .db 后缀）\n\n"
            "下面按钮复制的是当前这个用不了的路径，\n"
            "只是方便你对照着改成正确的位置。"
        ) % (p, info)
        okd, why = self._info_dialog("没找到歌曲库", body, p)
        if not okd:
            self._toast("弹窗打不开(%s)，请进设置手动改路径" % why)

    def _note_card(self, vod_id, name, remarks, body="", folder=False):

        c = {"vod_id": vod_id, "vod_name": name, "vod_pic": "",
             "vod_remarks": remarks, "vod_actor": "",
             "vod_content": body or remarks}
        if folder:
            c["vod_tag"] = "folder"
        return c

    def _kw_stat_body(self, kw, total, pages, pyhit):

        lines = ["当前关键词：「%s」" % kw,
                 "歌曲总数：%d 首" % total]
        if total <= 0:
            lines.append("")
            lines.append("这个关键词在库里没有匹配到任何歌曲。")
            lines.append("")
            lines.append("可以试试：")
            lines.append("  · 只输歌名或歌手的一部分（如「杰伦」而不是全名）")
            lines.append("  · 用拼音首字母（周杰伦 → ZJL）")
            lines.append("  · 多个关键词用空格隔开（周杰伦 晴天）")
            return "\n".join(lines)
        names = [n for n in (getattr(self, "_py_names", None) or []) if n]
        if pyhit:
            ac = to_acronym(str(kw).split()[0] if str(kw).strip() else kw)
            acs = "/".join(ac[:1]) or "—"
            lines.append("命中方式：拼音首字母容错（%s）" % acs)
            if not names:
                names = [pyhit]
            lines.append("")
            lines.append("按「%s」找到以下歌手：" % acs)
            for i, nm in enumerate(names):
                cnt = self._singer_song_count(nm)
                flag = " ← 排最前" if i == 0 else ""
                lines.append("  %d. %s（%d 首）%s" % (i + 1, nm, cnt, flag))
            if len(names) > 1:
                lines.append("")
                lines.append("想只看其中一位？用完整的中文名搜索，"
                             "或输入「歌手 歌名」两个关键词。")
        else:
            lines.append("命中方式：关键词精确匹配（歌名 / 歌手名）")
        lines.append("")
        lines.append("往下拉列表会继续加载更多；点「✎ 输入关键词」可以换词。")
        return "\n".join(lines)

    def _singer_song_count(self, name):

        pat = "%" + str(name).replace("%", "").replace("_", "") + "%"
        try:
            r = self.query("SELECT COUNT(*) AS c FROM song WHERE status=1 AND singer_names LIKE ?", (pat,))
            return int(r[0]["c"]) if r else 0
        except Exception:
            return 0

    def _search_page(self, pg):

        try:
            pg = max(int(str(pg) or "1"), 1)
        except Exception:
            pg = 1
        kw = self._kw_get()

        hits, total, pages, pyhit = [], 0, 1, ""
        if kw:
            res = self.searchContent(kw, False, str(pg))
            hits = res.get("list") or []
            total = int(res.get("total") or 0)
            pages = max(1, int(res.get("pagecount") or pg))
            pyhit = getattr(self, "_py_hit", "")

            if total >= 999999:
                total = 0
        items = []
        if pg <= 1:

            try:
                _ok, _why = self._http_alive()
                if not _ok and not _RP.get("manual_stop"):
                    self._order_start()
            except Exception:
                pass
            try:
                items.append(self._order_qr_card())
            except Exception as e:
                self._dexc("search qr card", e)

            if kw:
                sub = "当前词:%s（点我换词）" % kw
            else:
                sub = "可拼音首字母，多词空格隔开"
            c = self._note_card("kw:input", "✎ 输入关键词（歌/歌手/首字母）", sub)
            c["action"] = "kw"
            items.append(c)
            if kw:
                c2 = self._note_card("kw:clear", "🗑 清除关键词", "恢复热门列表")
                c2["action"] = "kwclear"
                items.append(c2)

                name = "总计 %d 首" % total
                if total == 0:
                    sub = "「%s」没有匹配结果" % kw
                elif pyhit:
                    more = len(getattr(self, "_py_names", None) or [])
                    if more > 1:
                        sub = "拼音容错，%d 位歌手，如 %s" % (more, pyhit)
                    else:
                        sub = "拼音容错命中「%s」，点看详情" % pyhit
                else:
                    sub = "关键词「%s」· 点看详情" % kw
                c3 = self._note_card("kw:count", name, sub,
                                     self._kw_stat_body(kw, total, pages, pyhit))
                c3["action"] = "kwstat"
                items.append(c3)
        items.extend(hits)
        if pg <= 1 and kw and not hits:
            items.append(self._note_card(
                "kw:empty", "🔍 没搜到「%s」" % kw,
                "换个词，或试试多关键词",
                "没搜到「%s」。\n\n试试：① 只输歌名或歌手的一部分；"
                "② 用拼音首字母（如 ZJL、ZGR、THG）；"
                "③ 多个关键词用空格隔开"
                "（每个词都要能对上，才会出现在结果里）；"
                "④ 用壳顶部搜索按钮（走同一接口）。" % kw))
        if not kw:

            res = self.categoryContent("hot", str(pg), False, None)
            items.extend(res.get("list") or [])
            pages = max(1, int(res.get("pagecount") or pg))

        return {"code": 1, "msg": "数据列表", "list": items, "page": pg,
                "pagecount": pages, "limit": 30,
                "total": total if (kw or total) else 999999}

    def _settings_page(self, pg):

        cfg = self._cfg_get()
        db = str(cfg.get("db") or DB_PATH)
        port = str(cfg.get("port") or "9978")
        cache = str(cfg.get("urlcache") or "10")
        n3ttl = str(cfg.get("n3ttl") if cfg.get("n3ttl") is not None else "3")

        def _c(key, name, remarks, body):
            c = self._note_card("set:" + key, name, remarks, body)
            c["action"] = "set:" + key
            return c

        try:
            _n_db = len(self._find_db(limit=20))
        except Exception:
            _n_db = 0
        _db_name = os.path.basename(db) if db else "（未设置）"
        _db_remark = ("点我切换（找到 %d 个库）" % _n_db) if _n_db > 1 \
            else "点我切换或手动输入"
        try:
            _cloud_t = self._cloud_card()
        except Exception as _e:
            _cloud_t = ("🔄 云端曲库（在线更新）", "点我检查更新",
                        "读取失败：%s" % str(_e)[:80])
        try:
            _warm_t = self._warm_card()
        except Exception as _e:
            _warm_t = ("🖼 歌手封面预热", "点我选强度", "读取失败：%s" % str(_e)[:80])
        try:
            _diag_t = self._diag_card()
        except Exception as _e:
            _diag_t = ("\U0001fa7a \u5c01\u9762\u8bca\u65ad", "\u70b9\u6211\u67e5\u770b",
                       "\u8bfb\u53d6\u5931\u8d25\uff1a%s" % str(_e)[:80])
        try:
            _clean_t = self._clean_card()
        except Exception as _e:
            _clean_t = ("🧹 清理旧库备份", "点我勾选清理",
                        "读取失败：%s" % str(_e)[:80])
        try:
            _ui = self._db_update_info()
            _upd_title = _ui.get("title") or "📦 数据库更新"
            _upd_remark = _ui.get("remark", "")
            _upd_body = _ui.get("body", "")
        except Exception as _e:
            _upd_title = "📦 数据库更新"
            _upd_remark = "查看版本与更新状态"
            _upd_body = "读取失败：%s" % str(_e)[:80]

        items = [
            _c("db", "📁 歌曲库：%s" % _db_name, _db_remark,
               "当前使用：\n%s\n\n"
               "手机上找到 %d 个可用的歌曲库。\n"
               "点这张卡会列出全部，当前那个前面打 ✓，点任意一个立即切换。\n"
               "列表最后一项是手动输入路径。" % (db, _n_db)),
            _c("gulu", "🔁 换回 Gulu 同步库",
               ("当前就是 Gulu 同步库 ✓" if os.path.realpath(db) == os.path.realpath(GULU_DB)
                else "点我一键切回（固定路径）"),
               "Gulu 的库永远在这一个位置（包内写死，不会变）：\n%s\n\n"
               "旁边同行有 song_9c8ec.version（当前 %s），"
               "Gulu 后台更新时这个文件会一起变。\n\n"
               "点这张卡直接切过来，不用手动敲路径。"
               % (GULU_DB, (self._db_version(GULU_DB) or "无"))),
            _c("dbupd", _upd_title, _upd_remark,
               _upd_body),
            _c("cloud", *_cloud_t),
        ]

        items += [
            _c("warm", *_warm_t),
            _c("diag", *_diag_t),
            _c("imgdir", "🖼 歌手图片目录", "点我修改（默认跟随数据库）",
               "当前：%s\n\n留空 = 自动跟随数据库同级目录下的 .singer_img。\n"
               "手动填绝对路径可单独指向别处。" % str(cfg.get("img") or "（跟随数据库）")),
            _c("n3ttl", "🔁 缺图歌手重查间隔（当前 %s 天）" % n3ttl,
               "点我修改（默认 3 天）",
               "本次没找到图的歌手，隔多少天再试一次。\n\n"
               "网络歌手今天没收录、过几天可能就有了，所以别设太长。\n"
               "找到图的会一直留用，不受这个影响。\n\n"
               "填 0 = 每次都重查（最准，但名单长了会拖慢列表加载）。"),
        ]

        items += [
            _c("urlcache", "⏱ 播放链接复用分钟（当前 %s）" % cache,
               "点我修改（默认10分钟）",
               "只控制播放直链在内存里复用多久，和转码缓存无关。\n\n"
               "每次拿直链都要走两步：签名服务取 validator → AES 加密请求 "
               + _seg(1).split("/")[2] + " → 返回带 auth_key 的 CDN 地址，约 1-2 秒。"
               "复用期内同一首不再重复请求。\n\n"
               "auth_key 有时效，复用太久会 403，所以别设过大；"
               "最小按 1 分钟算。壳重启后清空。"),
            _c("port", "🔌 代理端口（当前 %s）" % port,
               "点我修改（默认9978）", "代理端口 9978，壳的 getProxyUrl 返回值"),
            _c("clean", *_clean_t),
        ]

        try:
            _oa_t = self._orderauto_card()
        except Exception as _e:
            _oa_t = ("⚙ 点播自启动", "读取失败", "%s" % str(_e)[:80])
        try:
            items.append(self._order_switch_card())
            items.append(self._note_card("order:auto", *_oa_t, folder=True))
            items.append(self._orderport_card())
            items.append(self._fs_card())
            items.append(self._order_all_card())
        except Exception as _e:
            self.log("settings order cards: %s" % _e)

        return {"code": 1, "msg": "数据列表", "list": items, "page": 1,
                "pagecount": 1, "limit": 10, "total": len(items)}

    def img_dir(self):

        try:
            cfg = self._cfg_get()
        except Exception:
            cfg = {}
        v = str(cfg.get("img") or "").strip()
        if v:
            if self._img_dir_ok(v):
                return v
            db0 = str(cfg.get("db") or DB_PATH)
            return os.path.join(os.path.dirname(db0), IMG_DIR_DEFAULT)
        db = str(cfg.get("db") or DB_PATH)
        return os.path.join(os.path.dirname(db), IMG_DIR_DEFAULT)

    @staticmethod
    def _img_dir_ok(p):

        try:
            if os.path.isdir(p):
                return os.access(p, os.W_OK)
            parent = os.path.dirname(p.rstrip("/")) or "/"
            return os.path.isdir(parent) and os.access(parent, os.W_OK)
        except Exception:
            return False

    def _handle_setting(self, key):
        cfg = self._cfg_get()
        if key == "diag":
            self._diag_action()
            return
        if key == "cloud":
            self._cloud_action()
            return
        if key == "clean":
            self._clean_action()
            return
        if key == "order":
            self._order_show()
            return ""
        if key == "orderauto":

            v = "0" if self._order_auto() else "1"
            self._cfg_set({"orderauto": v})
            if v == "0":
                self._toast("点播自启动：关 ⛔（下次加载源不再自动起服务）")
            else:
                self._toast("点播自启动：开 ✅（下次加载源自动起服务）")
            return ""
        if key == "orderport":
            cur = str(self._order_port())

            def ok(t):
                if t.isdigit() and 1024 <= int(t) <= 65535:
                    newp = int(t)
                    if newp == int(self._order_port()):
                        self._toast("端口未变")
                        return
                    self._cfg_set({"orderport": str(newp)})

                    try:
                        d = getattr(self, "_httpd", None)
                        if d is not None:
                            d.shutdown()
                            d.server_close()
                    except Exception:
                        pass
                    self._httpd = None
                    self._http_thread = None
                    self._http_started = False
                    self._order_port_override = 0
                    ok2, why2 = self._order_start()
                    if ok2:
                        self._toast("端口已改为 %d，服务已重启 ✅" % newp)
                    else:
                        self._toast("端口已改为 %d，但启动失败：%s"
                                    % (newp, why2 or "端口被占用？"))
            self._input_dialog("🔢 点播端口",
                               "手机点歌服务监听端口，默认 27321。"
                               "1024-65535，改完立即重启服务。",
                               cur, ok)
            return ""
        if key == "warm":
            self._warm_action()
            return
        if key == "gulu":

            cur = str(cfg.get("db") or DB_PATH)
            if os.path.realpath(cur) == os.path.realpath(GULU_DB):
                self._info_dialog("🔁 Gulu 同步库",
                                  "当前用的就是 Gulu 自动同步的那一份。\n\n" + GULU_DB,
                                  GULU_DB)
                return
            n = self._probe_db(GULU_DB)
            if not n:
                self._info_dialog("🔁 Gulu 同步库",
                                  "找不到 Gulu 同步库：\n%s\n\n"
                                  "Gulu 还没下载过数据库，或者路径变了。"
                                  % GULU_DB, GULU_DB)
                return

            def _ok():
                try:
                    self._cfg_set({"db": GULU_DB, "db_prev": cur})
                except Exception:
                    pass
                self._toast("已切换到 Gulu 同步库：%d 首" % n)

            self._confirm_dialog(
                "🔁 切换到 Gulu 同步库",
                "将从\n%s\n\n切到 Gulu 自动同步的那份：\n%s\n\n%d 首歌" % (cur, GULU_DB, n),
                _ok)
            return
        if key == "dbupd":
            info = self._db_update_info()
            if info.get("newer") == 1 and info.get("sync"):

                def _ok():
                    try:
                        self._cfg_set({"db": info["sync"],
                                       "db_prev": info["cur"]})
                    except Exception:
                        pass
                    self._toast("已切换到 Gulu 同步库：%s 首"
                                % (info.get("sync_cnt") or "?"))
                self._confirm_dialog("📦 数据库更新", info.get("body", ""), _ok)
            else:

                self._info_dialog("📦 数据库状态", info.get("body", ""),
                                  info.get("cur", ""))
            return
        if key == "db":
            cur = str(cfg.get("db") or DB_PATH)
            hits = self._find_db(limit=20)

            if cur and cur not in [h[0] for h in hits] and os.path.isfile(cur):
                hits = [(cur, self._probe_db(cur))] + list(hits)
            okd, why = self._db_list_dialog(hits, cur)
            if not okd:
                self._toast("列表打不开(%s)，改手动输入" % why)
                def ok(t):
                    if t:
                        self._cfg_set({"db": t})
                self._input_dialog("📁 数据库文件路径",
                                   "绝对路径，如 /storage/.../song.db",
                                   cur, ok, toast="已保存，立即生效")
                return self._note_card("set:db", "📁 数据库文件路径",
                                       "修改中…重新进设置查看", cur)
            cnt = len(hits)
            return self._note_card("set:db", "📁 数据库文件路径",
                                   "点我切换（找到 %d 个库）" % cnt
                                   if cnt else "点我切换或手动输入", cur)
        if key == "port":
            cur = str(cfg.get("port") or "9978")

            def ok(t):
                if t.isdigit():
                    self._cfg_set({"port": t})
            self._input_dialog("🔌 代理端口", "数字端口，默认 9978", cur, ok,
                               toast="已保存，立即生效")
            return self._note_card("set:port", "🔌 代理端口", "修改中…", cur)
        if key == "imgdir":
            cur = str(cfg.get("img") or "")
            fallback = self.img_dir()

            def ok(t, _fb=fallback):
                try:
                    self._cfg_set({"img": t or ""})
                except Exception:
                    pass
            self._input_dialog("🖼 歌手图片目录",
                               "留空 = 跟随数据库（%s）；或填绝对路径" % fallback,
                               cur, ok, toast="已保存，立即生效")
            return self._note_card("set:imgdir", "🖼 歌手图片目录", "修改中…",
                                   cur or fallback)
        if key == "n3ttl":
            cur = str(cfg.get("n3ttl") if cfg.get("n3ttl") is not None else "3")

            def ok(t):
                if t.isdigit():
                    self._cfg_set({"n3ttl": t})
            self._input_dialog("🔁 缺图歌手重查间隔（天）",
                               "这次没找到图的歌手，隔几天再试一次；填 0 = 每次都重查。默认 3",
                               cur, ok, toast="已保存，立即生效")
            return self._note_card("set:n3ttl", "🔁 缺图歌手重查间隔", "修改中…",
                                   cur + " 天")
        if key == "urlcache":
            cur = str(cfg.get("urlcache") or "10")

            def ok(t):

                if t.isdigit() and int(t) > 0:
                    self._cfg_set({"urlcache": t})
            self._input_dialog("⏱ 播放链接复用分钟",
                               "播放直链复用时长（分钟），默认 10；须大于 0", cur, ok,
                               toast="已保存，立即生效")
            return self._note_card("set:urlcache", "⏱ 播放链接复用", "修改中…", cur)
        return None

    def _db_version(self, path):

        try:
            vf = os.path.splitext(path)[0] + ".version"
            if os.path.isfile(vf):
                with open(vf, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read().strip()[:32]
        except Exception:
            pass
        return ""

    def _db_mtime(self, path):

        try:
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))
        except Exception:
            return ""

    GULU_PKGS = ("com.gulu.music.tw", "com.gulu.music.tv", "cn.guluplus.com")

    def _gulu_roots(self):

        roots = []
        bases = ["/storage/emulated/0", "/sdcard"]

        try:
            for n in os.listdir("/storage"):
                if n != "emulated" and n != "self":
                    bases.append(os.path.join("/storage", n))
        except Exception:
            pass
        for base in bases:
            roots.append(os.path.join(base, "WebHTV", "LocalFiles", "files-文件", "db"))
            try:
                for n in os.listdir(base):
                    if "gulu" in n.lower() or "glyco" in n.lower() \
                            or "WebHTV" in n or "iktv" in n.lower():
                        roots.append(os.path.join(base, n))
            except Exception:
                pass
        roots += ["/storage/emulated/0/TVData/db"]
        for pk in self.GULU_PKGS:
            for base in ("/storage/emulated/0/Android/data", "/sdcard/Android/data"):
                roots.append(os.path.join(base, pk, "files"))

        out, seen = [], set()
        for r in roots:
            k = os.path.normpath(r)
            if k not in seen:
                seen.add(k)
                out.append(k)
        return out

    @staticmethod
    def _looks_gulu(p):

        q = p.lower()
        for k in ("gulu", "glyco", "glyco", "iktv", "guluplus"):
            if k in q:
                return True
        for k in ("/webhtv/", "/ikmusic/", "/ik_karaoke/"):
            if k in q:
                return True
        return False

    def _find_gulu_db(self, cur=""):

        try:
            curreal = os.path.realpath(cur) if cur else ""
        except Exception:
            curreal = ""
        cands = {}

        for d in self.DB_HINTS:
            p = os.path.join(d, "song_9c8ec.db")
            try:
                if os.path.isfile(p):
                    cands[os.path.realpath(p)] = False
            except Exception:
                pass

        for r in self._gulu_roots():
            try:
                for dirpath, dirnames, filenames in os.walk(r):
                    if dirpath.count(os.sep) - r.count(os.sep) > 5:
                        dirnames[:] = []
                        continue
                    dirnames[:] = [x for x in dirnames
                                   if not x.startswith(".git") and x != "cache"]
                    for fn in filenames:
                        if fn.startswith("song_9c8ec.db") and \
                                "download" not in fn:
                            fp = os.path.join(dirpath, fn)
                            try:
                                cands[os.path.realpath(fp)] = False
                            except Exception:
                                pass
            except Exception:
                pass

        vers = {}
        for p in list(cands.keys()):
            if p == curreal:
                continue
            try:
                vp = os.path.join(os.path.dirname(p), "song_9c8ec.version")
                if os.path.isfile(vp):
                    try:
                        with open(vp, "r", encoding="utf-8",
                                  errors="ignore") as f:
                            vers[p] = f.read().strip()[:24]
                    except Exception:
                        vers[p] = ""
                    cands[p] = True
                    continue
                if self._looks_gulu(p):
                    cands[p] = True
            except Exception:
                pass
        return cands, vers

    def _map_url(self):

        try:
            v = str(self._cfg_get().get("dbmap") or "").strip()
        except Exception:
            v = ""
        return v or DB_MAP_URL

    def _cloud_off(self, size):

        import requests
        ua = {"User-Agent": _ua()}
        try:
            ts = int(time.time() * 1000)
            v = requests.get(DB_SIGN_URL + str(ts), headers=ua,
                             timeout=15).text.strip()
            if len(v) < 16:
                self.log("cloud off: validator too short %r" % (v[:40],))
                return None
        except Exception as e:
            self.log("cloud off sign fail: %r" % (e,))
            return None
        for b in DB_BASES:
            try:
                r = requests.post(b + DB_API_PATH, json={},
                                  headers={"User-Agent": _ua(),
                                           "validator": v,
                                           "Content-Type":
                                           "application/json; charset=utf-8"},
                                  timeout=20)
                o = r.json()
                if o.get("statusCode") != 1:
                    self.log("cloud off %s status=%r" % (b, o.get("statusCode")))
                    continue
                d = o.get("data") or {}
                if not d.get("url"):
                    continue

                sz = 0
                try:
                    h = requests.head(d["url"], headers=ua, timeout=15,
                                      allow_redirects=True)
                    sz = int(h.headers.get("Content-Length") or 0)
                except Exception:
                    sz = 0
                if size and sz and sz != size:
                    self.log("cloud off size %d vs cfg %d, use HEAD" % (sz, size))
                return {"path": d["url"], "size": sz, "sha256": "",
                        "ver": str(d.get("versionName") or ""),
                        "vcode": d.get("versionCode"),
                        "utime": str(d.get("updateTime") or ""),
                        "src": "官方"}
            except Exception as e:
                self.log("cloud off %s fail: %r" % (b, e))
        return None

    def _cloud_meta(self):

        import requests
        url = self._map_url()
        try:
            r = requests.get(url, timeout=20,
                             headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            raw = r.content
        except Exception as e:
            raw = b""
            self.log("cloud cfg fail: %r" % (e,))
        cfg = None
        if len(raw) >= 200:
            try:
                body = raw
                if raw[:2] == b"BM":

                    off = int.from_bytes(raw[10:14], "little")
                    if off <= 0 or off >= len(raw):
                        off = raw.find(b"ewo") if raw.find(b"ewo") > 0 else 0
                    body = raw[off:]
                txt = body.decode("ascii", "ignore").strip()
                txt = "".join(ch for ch in txt if ch in
                              "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                              "abcdefghijklmnopqrstuvwxyz"
                              "0123456789+/=")
                txt += "=" * ((-len(txt)) % 4)
                info = json.loads(base64.b64decode(txt).decode("utf-8"))
                cfg = (info.get("databases") or {}).get(DB_MAP_KEY)
                if cfg:
                    cfg = dict(cfg)
                    cfg["map_version"] = str(info.get("version") or "")
                    cfg["src"] = "配置"
            except Exception as e:
                self.log("cloud cfg parse fail: %r" % (e,))

        size0 = int((cfg or {}).get("size") or 0)
        off = self._cloud_off(size0)
        if off:

            if cfg and cfg.get("path") == off["path"] and cfg.get("sha256"):
                off["sha256"] = cfg["sha256"]
            off["map_version"] = (cfg or {}).get("map_version", "")
            return off
        if cfg:
            cfg["ver"] = (cfg.get("ver") or
                          os.path.basename(str(cfg.get("path") or "")))
            return cfg
        raise ValueError("官方接口和配置源都拿不到")

    def _dl_progress_path(self):
        try:
            return os.path.join(os.path.dirname(self._cfg_file()),
                                DB_PROGRESS_FILE)
        except Exception:
            return ""

    def _dl_load(self):
        p = self._dl_progress_path()
        if not p:
            return {}
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}

    def _dl_save(self, d):
        p = self._dl_progress_path()
        if not p:
            return
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
        except Exception:
            pass

    def _dl_state(self):

        d = self._dl_load()
        if not d.get("url"):
            return {}
        try:
            if time.time() - float(d.get("ts") or 0) > 86400:
                return {}
        except Exception:
            return {}
        part = d.get("part") or ""
        if not os.path.isfile(part):
            return {}
        return d

    def _dl_bytes(self, st):
        try:
            return os.path.getsize(st.get("part") or "")
        except Exception:
            return 0

    def _cloud_pick_db(self):

        try:
            cur = str(self._cfg_get().get("db") or DB_PATH)
        except Exception:
            cur = DB_PATH
        base = os.path.dirname(cur) or ""
        name = os.path.basename(cur) or "song_9c8ec.db"
        for d in (base, "/storage/emulated/0/Download",
                  "/sdcard/Download"):
            if not d:
                continue
            try:
                if not os.path.isdir(d):
                    continue
                t = os.path.join(d, ".wtest")
                with open(t, "w") as f:
                    f.write("1")
                os.remove(t)
                return os.path.join(d, name)
            except Exception:
                continue
        return os.path.join(base or "/tmp", name)

    @staticmethod
    def _sha256(path):
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for c in iter(lambda: f.read(1048576), b""):
                    h.update(c)
        except Exception:
            return ""
        return h.hexdigest()

    @staticmethod
    def _db_song_count(path):
        try:
            c = sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=3)
            try:
                return c.execute("SELECT COUNT(*) FROM song").fetchone()[0]
            finally:
                c.close()
        except Exception:
            return 0

    def _dl_clear(self):
        self._dl_save({})

    def _cloud_work(self, meta, dlg=None):

        import requests
        url = meta["path"]
        sha = str(meta.get("sha256") or "").lower()
        size = int(meta.get("size") or 0)
        target = self._cloud_pick_db()
        part = target + DB_PART_SUFFIX

        if os.path.isfile(target) and size and os.path.getsize(target) == size:
            if sha and self._sha256(target) == sha:
                hit = True
            elif not sha and meta.get("ver") and (
                    self._db_version(target) == str(meta["ver"])):
                hit = True
            else:
                hit = False
            if hit:
                self._dl_clear()
                self._cloud_dlg_set(dlg, 100, "已是这份库")
                n = self._db_song_count(target)
                return True, "✅ 已是最新，无需下载\n%s\n版本 %s · 曲目 %s 首" % (
                    target, self._db_version(target) or "?", n if n else "?")

        st = self._dl_load() or {}
        if st.get("url") != url or st.get("part") != part:

            if st.get("part") and os.path.isfile(st["part"]):
                try:
                    os.remove(st["part"])
                except Exception:
                    pass
        st = {"url": url, "part": part, "target": target,
              "size": size, "sha256": sha, "ts": time.time(), "state": "dl"}
        self._dl_save(st)

        headers = {"User-Agent": "Mozilla/5.0"}

        for attempt in range(MAX_TRY):
            have = os.path.getsize(part) if os.path.isfile(part) else 0
            if size and have > size:
                have = 0
                try:
                    os.remove(part)
                except Exception:
                    pass
            if size and have == size:
                break
            hdr = dict(headers)
            mode = "wb"
            if have:
                hdr["Range"] = "bytes=%d-" % have
                mode = "ab"
                self.log("cloud resume %d/%d (try %d)"
                         % (have, size, attempt + 1))
            try:
                with requests.get(url, headers=hdr, stream=True,
                                  timeout=(15, 60)) as r:
                    if r.status_code == 416:
                        break
                    if r.status_code not in (200, 206):
                        raise IOError("HTTP %d" % r.status_code)
                    if r.status_code == 200 and have:
                        mode = "wb"
                    done = have
                    with open(part, mode) as f:
                        for chunk in r.iter_content(262144):
                            if chunk:
                                f.write(chunk)
                                done += len(chunk)
                                if size:
                                    self._cloud_dlg_set(
                                        dlg, done * 100.0 / size,
                                        "%s / %s" % (self._human(done),
                                                     self._human(size)))
            except Exception as e:
                self.log("cloud dl fail(try %d): %r" % (attempt + 1, e))
                st["state"] = "err"
                self._dl_save(st)
                if attempt >= MAX_TRY - 1:
                    return False, ("下载中断：%s\n已存 %s，再点一次卡片接着下。"
                                   % (str(e)[:70], self._human(
                                       os.path.getsize(part)
                                       if os.path.isfile(part) else 0)))
                time.sleep(min(2 + attempt * 2, 12))

        got = os.path.getsize(part) if os.path.isfile(part) else 0
        if size and got != size:
            st["state"] = "err"
            self._dl_save(st)
            return False, "大小不符：%d / 期望 %d" % (got, size)

        st["state"] = "check"
        self._dl_save(st)
        self._cloud_dlg_set(dlg, 100, "校验中", force=True)
        if sha:
            h = hashlib.sha256()
            try:
                with open(part, "rb") as f:
                    for b in iter(lambda: f.read(1 << 20), b""):
                        h.update(b)
            except Exception as e:
                return False, "校验失败：%s" % str(e)[:80]
            if h.hexdigest() != sha:
                try:
                    os.remove(part)
                except Exception:
                    pass
                st["state"] = "err"
                self._dl_save(st)
                return False, ("sha256 不匹配，文件已删，请重试。\n"
                               "本地 %s\n期望 %s"
                               % (h.hexdigest()[:16], sha[:16]))

        n = self._probe_db(part)
        if not n:
            try:
                os.remove(part)
            except Exception:
                pass
            return False, "下载完成但库打不开（可能被截断），已删除。"

        lc = self._db_song_count(target) if os.path.isfile(target) else 0
        rc = self._db_song_count(part)
        if not rc:
            try:
                os.remove(part)
            except Exception:
                pass
            self._dl_clear()
            return False, "下载结果无法读取（分片损坏），已丢弃。再点一次重试。"
        if lc and rc < lc:
            keep = self.cloud_force
            if not keep:

                st["state"] = "held"
                st["ts"] = time.time()
                self._dl_save(st)
                return False, ("远端更旧：本地 %s 首 > 远端 %s 首\n"
                               "已保留当前库，未覆盖。\n"
                               "已下载好的文件留着，确认要用远端版本的话，"
                               "再点一次卡片即可（不用重下）。"
                               % (lc, rc))
            self.cloud_force = False

        bak = ""
        try:
            if os.path.isfile(target):

                o = self._db_version(target) or ""
                o = "".join(c for c in o if c.isalnum() or c in "._-")[:24]
                bak = target + ".bak-" + (o or "old")
                if os.path.isfile(bak):
                    os.remove(bak)
                shutil.copy2(target, bak)

                vold = os.path.splitext(target)[0] + ".version"
                if os.path.isfile(vold):
                    shutil.copy2(vold, vold + ".bak-old")
                self.log("cloud backup -> %s" % os.path.basename(bak))
        except Exception as e:
            self.log("backup fail: %r" % (e,))
        try:
            if os.path.isfile(target):
                os.remove(target)
        except Exception:
            pass
        try:
            os.rename(part, target)
        except Exception:
            try:
                shutil.copy2(part, target)
                os.remove(part)
            except Exception as e:
                return False, "安装失败：%s" % str(e)[:80]

        vpath = os.path.splitext(target)[0] + ".version"
        ver = str(meta.get("ver") or "").strip()
        try:
            with open(vpath, "w", encoding="utf-8") as f:
                f.write((ver or time.strftime("%Y.%m.%d")) + "\n")
        except Exception:
            pass

        try:
            self._cfg_set({"db": target, "scnt_ver": ""})
        except Exception:
            pass
        try:
            self._scnt_ready = False
        except Exception:
            pass
        st["state"] = "done"
        st["ts"] = time.time()
        self._dl_save(st)
        total = self._db_song_count(target)
        msg = "✅ 曲库已更新\n共 %s 首\n%s" % (total or n or "?", target)
        if bak:
            msg += "\n旧库备份：%s" % os.path.basename(bak)
        return True, msg

    def _human(self, n):
        try:
            n = float(n or 0)
        except Exception:
            return "0"
        for u in ("B", "KB", "MB", "GB"):
            if n < 1024 or u == "GB":
                return ("%.0f %s" % (n, u)) if u == "B" else ("%.1f %s" % (n, u))
            n /= 1024.0
        return "?"

    def _cloud_dlg_show(self):

        try:
            from java import jclass
            ctx = self._activity()
            if ctx is None:
                return None
            PBar = jclass("android.widget.ProgressBar")
            LL = jclass("android.widget.LinearLayout")
            TV = jclass("android.widget.TextView")
            B = jclass("android.app.AlertDialog$Builder")
            box = LL(ctx)
            box.setOrientation(1)
            pad = int(18 * ctx.getResources().getDisplayMetrics().density)
            box.setPadding(pad, pad, pad, pad)
            tv = TV(ctx)
            tv.setText("准备中…")
            tv.setTextSize(15.0)
            bar = PBar(ctx, None, 16842871)
            bar.setMax(1000)
            bar.setProgress(0)
            sub = TV(ctx)
            sub.setText("0%")
            sub.setTextSize(13.0)
            box.addView(tv)
            box.addView(bar)
            box.addView(sub)
            b = B(ctx)
            b.setTitle("🔄 云端曲库")
            b.setView(box)
            b.setCancelable(False)

            b.setNegativeButton("后台继续", None)
            d = b.create()
            d.setCanceledOnTouchOutside(False)
            d.show()
            return {"d": d, "tv": tv, "bar": bar, "sub": sub, "t": time.time()}
        except Exception as e:
            self.log("cloud dlg fail: %r" % (e,))
            return None

    def _cloud_dlg_set(self, h, pct, text="", force=False):

        if not h:
            return
        now = time.time()
        full = pct >= 100
        if not force and not full and now - h.get("t", 0) < 0.4:
            return
        h["t"] = now
        pct = max(0, min(100, pct))
        try:
            h["bar"].setProgress(int(pct * 10))
            h["sub"].setText("%s%%%s" % (int(pct), ("  ·  " + text) if text else ""))
            if full:
                h["tv"].setText("正在校验并安装…")
            elif text:
                h["tv"].setText("正在下载…")
        except Exception:
            pass
        if full:
            h["closing"] = True
        self.log("cloud pct %d %s" % (int(pct), text))

    def _cloud_dlg_close(self, h):
        if not h:
            return
        try:
            h["d"].dismiss()
        except Exception:
            pass

    def _cloud_done_dialog(self, ok, msg):

        try:
            from java import jclass
            ctx = self._activity()
            if ctx is None:
                self._toast(msg.split("\n")[0])
                return
            B = jclass("android.app.AlertDialog$Builder")
            b = B(ctx)
            b.setTitle("✅ 曲库已更新" if ok else "⚠️ 曲库没更新")
            if ok:
                b.setMessage(msg)
            else:
                tail = ("\n\n已有进度会保留，下次点卡片接着下。"
                        if "更旧" not in msg and "已是最新" not in msg
                        else "\n\n本地库没有任何改动。")
                b.setMessage(msg + tail)
            b.setPositiveButton("知道了", None)
            b.setCancelable(True)
            b.show()
        except Exception:
            try:
                self._toast(msg.split("\n")[0])
            except Exception:
                pass

    def _cloud_start(self, meta):

        h = self._cloud_dlg_show()

        def _run():
            try:
                ok, msg = self._cloud_work(meta, h)
            except Exception as e:
                ok, msg = False, "出错：%s" % str(e)[:100]
            self.log("cloud done ok=%s %s" % (ok, msg.replace("\n", " ")[:120]))
            self._cloud_dlg_close(h)
            self._cloud_done_dialog(ok, msg)

        try:
            t = threading.Thread(target=_run)
            t.daemon = True
            t.start()
        except Exception as e:
            self._toast("启动失败：%s" % str(e)[:60])

    def _ensure_dir(self, d):
        try:
            if d and not os.path.isdir(d):
                os.makedirs(d)
            return bool(d) and os.path.isdir(d)
        except Exception:
            return False

    def _has_img(self, name):
        try:
            h = hashlib.md5(str(name).encode("utf-8")).hexdigest()
            return os.path.exists(os.path.join(self.img_dir(), h + ".img"))
        except Exception:
            return False

    def _warm_cfg(self):
        try:
            v = int(self._cfg_get().get("warm") or 0)
        except Exception:
            v = 0
        return v if v > 0 else 200

    def _warm_pending(self, limit):

        names = []
        seen = set()
        try:
            rows = self.query(
                "SELECT singer_names FROM song WHERE status=1 "
                "AND singer_names IS NOT NULL AND singer_names<>'' "
                "ORDER BY temperature DESC LIMIT 6000")
        except Exception:
            rows = []
        for r in rows:
            for n in str(r["singer_names"] or "").replace("，", ",").split(","):
                n = n.strip()
                if not n or n in seen:
                    continue
                seen.add(n)
                if self._has_img(n):
                    continue
                names.append(n)
                if limit > 0 and len(names) >= limit:
                    return names
        if len(names) >= limit > 0:
            return names[:limit]

        if limit <= 0 or len(names) < limit:
            try:
                rows2 = self.query(
                    "SELECT DISTINCT singer_names FROM song WHERE singer_names "
                    "IS NOT NULL AND singer_names<>'' LIMIT 20000")
            except Exception:
                rows2 = []
            for r in rows2:
                for n in str(r["singer_names"] or "").replace("，", ",").split(","):
                    n = n.strip()
                    if not n or n in seen:
                        continue
                    seen.add(n)
                    if self._has_img(n):
                        continue
                    names.append(n)
                    if limit > 0 and len(names) >= limit:
                        return names[:limit]
        return names if limit <= 0 else names[:limit]

    def _diag_card(self):

        try:
            d = self.img_dir()
        except Exception as e:
            return ("🩺 封面诊断", "img_dir() 抛异常",
                    "img_dir() 失败：%s\n\n这说明配置里的数据库路径算不出目录。" % e)
        n_img = n_n3 = -1
        writable = None
        if os.path.isdir(d):
            try:
                n_img = len([f for f in os.listdir(d) if f.endswith(".img")])
                n_n3 = len([f for f in os.listdir(d) if f.endswith(".n3")])
            except Exception:
                pass
            writable = os.access(d, os.W_OK)
        else:
            writable = False
        try:
            blob = self._probe_sources()
        except Exception as e:
            blob = "探测出错：%s" % e
        body = ("目录：%s\n"
                "目录存在：%s\n"
                "可写：%s\n"
                "已有图片：%s 张\n"
                "缺图标记(.n3)：%s 个\n\n"
                "四家接口实测：\n%s\n\n"
                "怎么读：\n"
                "· 目录不存在/不可写 → 换存储位置，或在图片目录卡里手动填一个\n"
                "· 四家全失败 → 这台机器的网络访问不到音乐接口\n"
                "· 都正常却没图 → 点「清缺图标记」后重跑预热"
                % (d,
                   "是" if os.path.isdir(d) else "否",
                   ("是" if writable else "否") if writable is not None else "未知",
                   n_img if n_img >= 0 else "?",
                   n_n3 if n_n3 >= 0 else "?",
                   blob))
        return ("🩺 封面诊断", "点我看目录与四家接口实测", body)

    def _probe_sources(self):

        import time as _t
        out = []
        tests = [
            ("酷我", "http://search.kuwo.cn/r.s?all=%s&ft=artist&rn=3&encoding=utf8"
                     "&rformat=json"),
            ("酷狗", "http://mobilecdn.kugou.com/api/v3/search/singer?keyword=%s"
                     "&page=1&pagesize=3"),
            ("QQ", "https://c.y.qq.com/soso/fcgi-bin/client_search_cp?p=1&n=3&w=%s"),
            ("网易", "http://music.163.com/api/search/get/web?s=%s&type=100&limit=3"),
        ]
        kw = "\u5468\u6770\u4f26"
        for nm, tpl in tests:
            url = tpl % _quote(kw)
            t0 = _t.time()
            try:
                import requests
                r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"},
                                 timeout=8)
                ms = int((_t.time() - t0) * 1000)
                out.append("· %s HTTP %d · %d 字节 · %dms"
                           % (nm, r.status_code, len(r.content), ms))
            except Exception as e:
                ms = int((_t.time() - t0) * 1000)
                out.append("· %s 失败 · %dms · %s"
                           % (nm, ms, str(e)[:60]))
        return "\n".join(out)

    def _diag_clear_n3(self):

        d = self.img_dir()
        n = 0
        try:
            for f in os.listdir(d):
                if f.endswith(".n3"):
                    try:
                        os.remove(os.path.join(d, f))
                        n += 1
                    except Exception:
                        pass
        except Exception as e:
            self._toast("清理失败：%s" % str(e)[:60])
            return
        self._toast("已清掉 %d 个缺图标记，重新预热试试" % n)

    def _diag_action(self):

        try:
            from java import jclass, dynamic_proxy
            act = self._activity()
            if act is None:
                self._toast("没有窗口上下文")
                return
            TV = jclass("android.widget.TextView")
            SV = jclass("android.widget.ScrollView")
            DCL = jclass("android.content.DialogInterface$OnClickListener")
            RL = jclass("java.lang.Runnable")
            try:
                AB = jclass("com.google.android.material.dialog.MaterialAlertDialogBuilder")
            except Exception:
                AB = jclass("android.app.AlertDialog$Builder")

            owner = self

            _t, _r, body = self._diag_card()

            class _Clear(dynamic_proxy(DCL)):
                def __init__(self):
                    super().__init__()

                def onClick(self, dlg, w):
                    dlg.dismiss()
                    owner._diag_clear_n3()

            class _Warm(dynamic_proxy(DCL)):
                def __init__(self):
                    super().__init__()

                def onClick(self, dlg, w):
                    dlg.dismiss()
                    owner._warm_choose(0)

            class Show(dynamic_proxy(RL)):
                def __init__(self):
                    super().__init__()

                def run(self):
                    try:
                        tv = TV(act)
                        tv.setText(str(body))
                        tv.setTextSize(12.0)
                        pad = int(16 * act.getResources().getDisplayMetrics().density)
                        tv.setPadding(pad, pad, pad, pad)
                        sv = SV(act)
                        sv.addView(tv)
                        b = AB(act)
                        b.setTitle(_t)
                        b.setView(sv)
                        b.setPositiveButton("清缺图标记", _Clear())
                        b.setNegativeButton("重跑预热", _Warm())
                        b.setNeutralButton("关闭", None)
                        d = b.create()
                        refs = getattr(owner, "_dialog_refs", None)
                        if refs is not None:
                            refs.append(d)
                        d.show()
                    except Exception as e:
                        owner._toast("诊断失败：%s" % str(e)[:80])

            refs = getattr(self, "_dialog_refs", None)
            if refs is None:
                refs = self._dialog_refs = []
            sh = Show()
            refs.append(sh)
            del refs[:-16]
            act.runOnUiThread(sh)
        except Exception as e:
            self._toast("诊断失败：%s" % str(e)[:80])

    def _warm_card(self):
        try:
            d = self.img_dir()
            n = 0
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if f.endswith(".img"):
                        n += 1
        except Exception:
            n = 0
            d = ""
        if getattr(self, "_warm_busy", False):
            done, hit, tot = getattr(self, "_warm_stat", (0, 0, 0))
            return ("🖼 歌手封面预热（进行中 %d/%d）" % (done, tot),
                    "点我查看或停止",
                    "已抓到 %d 张 · 目录 %s" % (hit, d))
        return ("🖼 歌手封面预热",
                "本地已有 %d 张 · 点我选强度" % n,
                "新手机首次用：点这张卡按需把歌手封面抓到本地。\n"
                "目录：%s\n\n"
                "强度说明：\n"
                "· 轻度 50 位 —— 十几秒，够首页热榜显示\n"
                "· 标准 200 位 —— 约 2-3 分钟，覆盖大部分常搜歌手\n"
                "· 深度 500 位 —— 约 6-8 分钟\n"
                "· 全部缺图 —— 几千位，很慢，建议充电+wifi\n\n"
                "抓取走酷我/QQ/网易/酷狗四家，命中率实测接近 100%%。" % (d,))

    def _warm_action(self):
        if getattr(self, "_warm_busy", False):
            self._warm_progress_dialog()
            return
        self._warm_choose(0)

    def _warm_choose(self, page):

        pages = (
            (("轻度 50 位", "标准 200 位", "更多强度…"),
             ("50", "200", "more")),
            (("深度 500 位", "全部缺图", "返回"),
             ("500", "0", "back")),
        )
        labels, values = pages[page]
        try:
            from java import jclass, dynamic_proxy
            act = self._activity()
            if act is None:
                self._toast("没有窗口上下文")
                return
            TV = jclass("android.widget.TextView")
            SV = jclass("android.widget.ScrollView")
            DCL = jclass("android.content.DialogInterface$OnClickListener")
            RL = jclass("java.lang.Runnable")
            try:
                AB = jclass("com.google.android.material.dialog.MaterialAlertDialogBuilder")
            except Exception:
                AB = jclass("android.app.AlertDialog$Builder")
            refs = getattr(self, "_dialog_refs", None)
            if refs is None:
                refs = self._dialog_refs = []
            owner = self

            def make(idx):
                class Pick(dynamic_proxy(DCL)):
                    def __init__(self):
                        super().__init__()

                    def onClick(self, dlg, w):
                        try:
                            dlg.dismiss()
                        except Exception:
                            pass
                        v = values[idx]
                        if v == "more":
                            owner._warm_choose(1)
                        elif v == "back":
                            owner._warm_choose(0)
                        else:
                            owner._warm_start(int(v))
                return Pick()

            class Show(dynamic_proxy(RL)):
                def run(self):
                    try:
                        tv = TV(act)
                        tv.setText(owner._warm_card()[2])
                        tv.setTextSize(13.0)
                        tv.setTextIsSelectable(True)
                        dm = act.getResources().getDisplayMetrics().density
                        pad = int(16 * dm)
                        tv.setPadding(pad, pad // 2, pad, pad)
                        sv = SV(act)
                        sv.addView(tv)
                        b = AB(act)
                        b.setTitle("封面预热" + ("（第 2 页）" if page else ""))
                        b.setView(sv)
                        ps = [make(i) for i in range(3)]
                        b.setPositiveButton(labels[0], ps[0])
                        b.setNegativeButton(labels[1], ps[1])
                        b.setNeutralButton(labels[2], ps[2])
                        dlg = b.show()
                        refs.extend(ps + [tv, sv, dlg])
                        del refs[:-16]
                    except Exception as e:
                        try:
                            jclass("android.widget.Toast").makeText(
                                act, "打开失败:%s" % str(e)[:50], 1).show()
                        except Exception:
                            pass

            sh = Show()
            refs.append(sh)
            del refs[:-16]
            act.runOnUiThread(sh)
        except Exception as e:
            self._toast("打开失败：%s" % str(e)[:50])

    def _warm_start(self, limit):
        if getattr(self, "_warm_busy", False):
            self._toast("已经在跑了")
            return
        self._warm_busy = True
        self._warm_stop = False
        self._warm_stat = (0, 0, 0)
        th = threading.Thread(target=self._warm_work, args=(limit,))
        th.setDaemon(True)
        try:
            th.start()
        except Exception as e:
            self._warm_busy = False
            self._toast("启动失败：%s" % str(e)[:50])
            return
        self._warm_progress_dialog()

    def _warm_work(self, limit):
        hit = 0
        done = 0
        try:
            if not self._ensure_dir(self.img_dir()):
                self.log("warm: cannot create %s" % self.img_dir())
                self._warm_busy = False
                return
            names = self._warm_pending(limit)
            tot = len(names)
            self._warm_stat = (0, 0, tot)
            self.log("warm: %d singers, limit=%s" % (tot, limit))
            for n in names:
                if getattr(self, "_warm_stop", False):
                    self.log("warm: stopped by user at %d/%d" % (done, tot))
                    break
                try:
                    if self._ensure_singer_img(n):
                        hit += 1
                except Exception as e:
                    self.log("warm miss %s: %r" % (n, e))
                done += 1
                self._warm_stat = (done, hit, tot)
        except Exception as e:
            self.log("warm fail: %r" % (e,))
        finally:
            stopped = getattr(self, "_warm_stop", False)
            self._warm_busy = False
            self._warm_stop = False
            self.log("warm done: %d/%d hit=%d" % (done, done, hit))
            self._warm_done_dialog(stopped, done, hit)

    def _warm_progress_dialog(self):
        try:
            from java import jclass, dynamic_proxy
            act = self._activity()
            if act is None:
                return
            PB = jclass("android.widget.ProgressBar")
            TV = jclass("android.widget.TextView")
            LL = jclass("android.widget.LinearLayout")
            LLP = jclass("android.widget.LinearLayout$LayoutParams")
            VCL = jclass("android.view.View$OnClickListener")
            RL = jclass("java.lang.Runnable")
            try:
                AB = jclass("com.google.android.material.dialog.MaterialAlertDialogBuilder")
            except Exception:
                AB = jclass("android.app.AlertDialog$Builder")
            refs = getattr(self, "_dialog_refs", None)
            if refs is None:
                refs = self._dialog_refs = []
            owner = self

            class Stop(dynamic_proxy(VCL)):
                def __init__(self):
                    super().__init__()

                def onClick(self, v):
                    owner._warm_stop = True
                    try:
                        d = owner._warm_dlg
                        if d and d.get("dlg") is not None:
                            d["dlg"].dismiss()
                            owner._warm_dlg = None
                    except Exception:
                        pass
                    owner._toast("已停止，正在抓的这张处理完就退出")

            class Show(dynamic_proxy(RL)):
                def run(self):
                    try:
                        dm = act.getResources().getDisplayMetrics().density
                        pad = int(18 * dm)
                        box = LL(act)
                        box.setOrientation(1)
                        box.setPadding(pad, pad, pad, pad)

                        tv = TV(act)
                        tv.setTextSize(14.0)
                        tv.setText("准备中…")
                        box.addView(tv, LLP(-1, -2))

                        bar = PB(act, None, 16842871)
                        bar.setMax(100)
                        bar.setProgress(0)
                        box.addView(bar, LLP(-1, int(10 * dm)))

                        sub = TV(act)
                        sub.setTextSize(12.0)
                        sub.setText("抓到的图会写进 %s" % owner.img_dir())
                        box.addView(sub, LLP(-1, -2))

                        stopv = TV(act)
                        stopv.setText("⏹  停止")
                        stopv.setTextSize(14.0)
                        stopv.setPadding(0, int(12 * dm), 0, 0)
                        stopv.setOnClickListener(Stop())
                        box.addView(stopv, LLP(-1, -2))

                        b = AB(act)
                        b.setTitle("🖼 封面预热")
                        b.setView(box)
                        b.setCancelable(False)
                        b.setNegativeButton("后台继续", None)
                        dlg = b.show()
                        owner._warm_dlg = {"dlg": dlg, "bar": bar, "tv": tv,
                                           "sub": sub}
                        refs.extend([box, tv, bar, sub, stopv, dlg])
                        del refs[:-20]

                        class Tick(dynamic_proxy(RL)):
                            def run(self):
                                try:
                                    done, hit, tot = getattr(
                                        owner, "_warm_stat", (0, 0, 0))
                                    if not getattr(owner, "_warm_busy", False):
                                        return
                                    pct = int(done * 100 / tot) if tot else 0
                                    bar.setProgress(pct)
                                    tv.setText("已处理 %d / %d 位 · 新抓 %d 张（%d%%）"
                                               % (done, tot, hit, pct))
                                    sub.setText("目录 %s" % owner.img_dir())
                                    act.runOnUiThread(Tick())
                                except Exception:
                                    pass

                        act.runOnUiThread(Tick())
                    except Exception as e:
                        try:
                            jclass("android.widget.Toast").makeText(
                                act, "进度窗失败:%s" % str(e)[:50], 1).show()
                        except Exception:
                            pass

            sh = Show()
            refs.append(sh)
            del refs[:-20]
            act.runOnUiThread(sh)
        except Exception:
            pass

    def _warm_done_dialog(self, stopped, done, hit):
        try:
            h = getattr(self, "_warm_dlg", None)
            if h:
                try:
                    h["dlg"].dismiss()
                except Exception:
                    pass
                self._warm_dlg = None
        except Exception:
            pass
        title = "⏹ 封面预热已停止" if stopped else "✅ 封面预热完成"
        self._info_dialog(title,
                          "处理 %d 位歌手，新抓到 %d 张封面。\n\n"
                          "去分类或搜索页看看，卡片应该出图了。\n"
                          "目录：%s" % (done, hit, self.img_dir()))

    def _queue_path(self):

        try:
            return os.path.join(os.path.dirname(self._cfg_file()), ORDER_QPATH)
        except Exception:
            return os.path.join(os.getcwd(), ORDER_QPATH)

    def _queue_load(self):

        try:
            with open(self._queue_path(), "r", encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, list) else []
        except Exception:
            return []

    def _queue_save(self, items):
        try:
            with open(self._queue_path(), "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False)
        except Exception as e:
            self.log("queue save fail: %s" % e)

    def _queue_add(self, num, name, singer, extra=None):

        try:
            with getattr(self, "_order_lock", threading.Lock()):
                q = self._queue_load()
                if any(int(x.get("number") or 0) == int(num) and not x.get("done")
                       for x in q):
                    return False, "已在队列"
                q.append(dict(number=int(num), name=name, singer=singer,
                              ts=time.time(), done=0, **(extra or {})))
                q[:] = q[-200:]
            self._queue_save(q)
            return True, ""
        except Exception as e:
            return False, str(e)[:60]

    def _queue_top(self, num):

        try:
            num = int(num)
        except Exception:
            return False, "编号不对"
        with getattr(self, "_order_lock", threading.Lock()):
            q = self._queue_load()
            last_pend = -1
            for i, y in enumerate(q):
                if not y.get("done"):
                    last_pend = i
            idx = next((i for i, x in enumerate(q)
                        if int(x.get("number") or 0) == num
                        and not x.get("done")), -1)
            if idx >= 0:

                if idx == last_pend:
                    return True, "已经在待唱最后一位了"
                x = q.pop(idx)
                p = last_pend if idx < last_pend else last_pend - 1

                p = -1
                for i, y in enumerate(q):
                    if not y.get("done"):
                        p = i
                q.insert(p + 1 if p >= 0 else len(q), x)
                self._queue_save(q)
                return True, "已排到待唱最后一位"
            hit = next((x for x in q
                        if int(x.get("number") or 0) == num), None)
            if hit is None:
                rows = self.query("SELECT name,singer_names FROM song "
                                  "WHERE number=? AND status=1", (num,))
                if not rows:
                    return False, "曲库里没有这首歌"
                q.append(dict(number=num, name=rows[0]["name"],
                              singer=rows[0]["singer_names"],
                              ts=time.time(), done=0))
                self._queue_save(q)
                return True, "已加入待唱最后一位"

            hit["done"] = 0
            q.remove(hit)
            q.append(hit)
            self._queue_save(q)
            return True, "已加入待唱最后一位"
        return True, ""

    def _queue_first(self, num):

        try:
            num = int(num)
        except Exception:
            return False, "编号不对"
        with getattr(self, "_order_lock", threading.Lock()):
            q = self._queue_load()
            idx = next((i for i, x in enumerate(q)
                        if int(x.get("number") or 0) == num
                        and not x.get("done")), -1)
            if idx < 0:
                return False, "不在待唱里"
            fp = next((i for i, y in enumerate(q) if not y.get("done")), -1)
            if idx == fp:
                return True, "已经在待唱第一位了"
            x = q.pop(idx)
            fp = next((i for i, y in enumerate(q) if not y.get("done")), -1)
            q.insert(fp if fp >= 0 else 0, x)
            self._queue_save(q)
        return True, ""

    def _queue_park(self, num):

        try:
            num = int(num)
        except Exception:
            return False, "编号不对"
        with getattr(self, "_order_lock", threading.Lock()):
            q = self._queue_load()
            hit = False
            for x in q:
                if int(x.get("number") or 0) == num \
                        and not x.get("done"):
                    x["done"] = 2
                    hit = True
            if not hit:
                return False, "待唱里没有这首歌"
            self._queue_save(q)
        return True, "已移到待定区"

    def _queue_unpark(self, num):

        try:
            num = int(num)
        except Exception:
            return False, "编号不对"
        with getattr(self, "_order_lock", threading.Lock()):
            q = self._queue_load()
            hit = False
            for x in q:
                if int(x.get("number") or 0) == num \
                        and int(x.get("done") or 0) == 2:
                    x["done"] = 0
                    hit = True
            if not hit:
                return False, "待定区里没有这首歌"
            self._queue_save(q)
        return True, "已排回待唱最后一位"

    def _queue_del(self, num):

        try:
            num = int(num)
        except Exception:
            return False, "编号不对"
        with getattr(self, "_order_lock", threading.Lock()):
            q = self._queue_load()
            n0 = len(q)
            q = [x for x in q if int(x.get("number") or 0) != num]
            if len(q) == n0:
                return False, "队列里没有这首歌"
            self._queue_save(q)
        return True, ""

    def _order_card(self):

        q = [x for x in self._queue_load() if not x.get("done")]
        run, why = self._http_alive()
        if run:
            t = "📱 点播服务运行中 :%d" % self._order_port()
        elif why:
            t = "📱 局域网点播（启动失败）"
        else:
            t = "📱 局域网点播"
        remark = ("点我查看地址和二维码" if run else
                  ("点我看失败原因: %s" % why[:40] if why else "点我开启并显示二维码"))
        body = ("手机连同一个 Wi-Fi，扫码或浏览器打开地址即可点歌。\n\n"
                "手机三颗按钮：\n"
                "「⚡ 现在唱」电视立刻开播（抢台），「🎤 点歌」排入待唱队列。\n"
                "· 「🎤 点歌」→ 进电视待唱队列，电视端点卡即播\n"
                "· 「＋」攒单，回电视端一次入队；队列页可切歌/标记唱完\n\n"
                "跨进程队列文件：%s\n当前待唱：%d 首\n\n"
                "端口默认 %d，可在下面一张卡改。"
                % (self._queue_path(), len(q), self._order_port()))
        return (t, remark, body)

    def _order_auto(self):

        try:
            return str(self._cfg_get().get("orderauto", "1")) != "0"
        except Exception:
            return True

    def _orderauto_card(self):

        on = self._order_auto()
        t = "⚙ 服务自启动"
        remark = ("开 ✅ · 点我关闭" if on else "关 ⛔ · 点我开启")
        body = ("开：每次源加载（进壳/换台回来）自动起手机点歌服务，"
                "手机随时扫码可点。\n"
                "关：不自动起，要用时点「📱 扫码点歌」卡手动启动。\n\n"
                "注意：这张卡只改「是否自动起」，当前服务跑不停都由"
                "「🔌 手动开关」卡控制。")
        return (t, remark, body)

    def _order_switch_card(self):

        try:

            alive = bool(self._http_alive()[0])
        except Exception:
            alive = False
        if alive:
            t = "🔌 手动开关（运行中 ✅）"
            rk = "服务已启动 · 点我关闭"
            bd = ("服务正在运行，点这张卡立即关闭（手机将无法访问点播页）\n"
                  "注意：这只控制服务本身，「服务自启动」卡控制的是"
                  "加载脚本时是否同步启动服务，两者互不影响。")
        else:
            t = "🔌 手动开关（已关闭 ⛔）"
            rk = "服务未启动 · 点我开启"
            bd = ("服务当前未启动，点这张卡立即启动（手机扫码即可点歌）。\n"
                  "注意：这只控制服务本身，「服务自启动」卡控制的是"
                  "加载脚本时是否同步启动服务，两者互不影响。")

        return self._note_card("order:switch", t, rk, bd, folder=True)

    def _order_qr_card(self):

        q = [x for x in self._queue_load() if not x.get("done")]
        url = self._order_url()
        on = self._order_auto()
        t = ""

        remark = ""
        body = ("手机连同一 Wi-Fi，扫左侧二维码或打开：%s\n\n"
                "顶部三页签：🔍 搜索 / 🎤 点歌 / 📚 曲库\n"
                "\u26a1 现在唱 = 立即抢占电视播放\n"
                "🎤 点歌 = 排进待唱队列\n"
                "待唱：↑置顶下一首 · ✕移出到待定\n"
                "待定：🎤点歌回到队列 · ✕移除\n"
                "已唱：↻重唱排回队尾 · ✕移除\n"
                "点我重看二维码大图和地址。"
                % (url,))
        st = self._note_card("order:qr", t, remark, body, folder=True)
        st["vod_pic"] = ("%s/qr" % url.rstrip("/")) if url else ""
        return st

    def _queue_show(self):

        q = self._queue_load()
        pend = [x for x in q if not x.get("done")]
        done = [x for x in q if x.get("done")]
        now_n = 0
        try:
            now_n = int(_RP.get("now") or 0)
        except Exception:
            pass
        if not pend and not done:
            self._toast("队列为空，手机扫码点歌后这里会出现歌曲")
        else:
            lines = []
            if pend:
                lines.append("待唱 %d 首：" % len(pend))
                for i, x in enumerate(pend, 1):
                    mark = " 🎤正在唱" if int(x.get("number") or 0) == now_n else ""
                    lines.append("%d. %s - %s%s" % (i, x.get("name"),
                                x.get("singer"), mark))
            if done:
                lines.append("")
                lines.append("已唱 %d 首（最近）：" % len(done))
                for x in done[-5:]:
                    lines.append("· %s" % x.get("name"))
            self._info_dialog("⏳ 点播队列", "\n".join(lines))

    def _order_all_card(self):

        try:
            n = len([x for x in self._queue_load() if not x.get("done")])
        except Exception:
            n = 0
        remarks = "%d 首待唱" % n if n else "暂无待唱"

        return self._note_card("order:all", "▶ 播放全部",
                               remarks,
                               "点卡直接进播放页，底部列出全部待唱歌，"
                               "从第一首开始播。")

    def _order_all_detail(self):

        try:
            q = [x for x in self._queue_load() if not x.get("done")]
        except Exception:
            q = []
        eps, names = [], []
        for it in q:
            try:
                num = int(it.get("number") or 0)
            except Exception:
                continue
            name = str(it.get("name") or "").strip()
            if not num or not name:
                continue
            eps.append(self._play_url(name, num))
            names.append(name)
        if not eps:

            c = self._note_card("order:all", "▶ 播放全部",
                                "暂无待唱",
                                "队列里还没有待唱歌曲。\n"
                                "打开手机网页点歌后再回来点这张卡。")
            return {"code": 1, "msg": "详情", "list": [c], "page": 1,
                    "pagecount": 1, "limit": 1, "total": 1}
        vod = {
            "vod_id": "order:all",
            "vod_name": "▶ 播放全部 · %d 首待唱" % len(eps),
            "vod_pic": "",
            "type_name": "点播队列",
            "vod_year": "",
            "vod_area": "",
            "vod_lang": "",
            "vod_remarks": "共 %d 首" % len(eps),
            "vod_actor": "",
            "vod_director": "",
            "vod_content": "待唱队列（%d 首）：\n%s" % (
                len(eps), "\n".join("%d. %s" % (i, n)
                                     for i, n in enumerate(names[:30], 1))),
            "vod_play_from": "爱KTV",
            "vod_play_url": "#".join(eps),
        }
        return {"code": 1, "msg": "数据列表", "list": [vod],
                "page": 1, "pagecount": 1, "limit": 1, "total": 1}

    def _order_queue_page(self):

        q = [x for x in self._queue_load() if not x.get("done")]
        now_n = 0
        try:
            now_n = int(_RP.get("now") or 0)
        except Exception:
            pass
        items = []
        if not q:
            items.append(self._note_card(
                "order:qr", "⏳ 队列空空如也",
                "手机扫码点歌后这里会出现歌曲",
                "手机打开「📱 扫码点歌」卡上的地址，搜歌点「🎤 点歌」，"
                "回这张卡刷新就能看到，点卡即播。", folder=True))
            return items
        for x in q[-30:]:
            num = int(x.get("number") or 0)
            name = str(x.get("name") or "")
            singer = str(x.get("singer") or "")
            t = ("🎤 %s" % name) if num == now_n else name
            remark = singer + (" · 正在唱" if num == now_n else " · 点卡即播")
            items.append(self._note_card("s%d" % num, t, remark,
                                         "%s - %s\n编号 %d\n点卡片立即播放。"
                                         % (name, singer, num)))
        return items

    def _orderport_card(self):

        cur = str(self._order_port())
        d = self._orderport_default()
        t = "🔢 点播端口（%s）" % cur

        rk = "点我修改端口"
        bd = ("手机点歌网页服务监听端口，当前 %s（默认 %d）。\n\n"
              "点我手动改成别的端口（1024-65535），改完立即重启服务；"
              "手机端要重新扫码（地址变了）。\n"
              "和壳的「🔌 代理端口」无关。" % (cur, d))

        return self._note_card("order:port", t, rk, bd, folder=True)

    def _orderport_default(self):
        try:
            return int(ORDER_PORT_DEFAULT)
        except Exception:
            return 27321

    def _order_port(self):
        ov = getattr(self, "_order_port_override", 0)
        if ov:
            return int(ov)
        try:
            v = str(self._cfg_get().get("orderport") or "").strip()
            if v.isdigit() and 1024 <= int(v) <= 65535:
                return int(v)
        except Exception:
            pass
        return ORDER_PORT_DEFAULT

    def _lan_ip(self):

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0)
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            pass
        try:
            for line in os.popen("ip route").read().split("\
"):
                if " src " in line:
                    ip = line.rsplit(" src ", 1)[1].strip()
                    if ip and not ip.startswith("127."):
                        return ip
        except Exception:
            pass
        return "0.0.0.0"

    def _http_alive(self):

        why = str(getattr(self, "_order_why", "") or "")
        d = getattr(self, "_httpd", None)
        if d is not None:
            try:
                if d.socket.fileno() >= 0:
                    th = getattr(self, "_http_thread", None)
                    if th is not None and th.is_alive():
                        return True, ""
                    return False, "服务线程已退出"
            except Exception:
                pass
            return False, why

        if getattr(self, "_http_started", False):
            try:
                if self._order_probe_info() is not None:
                    return True, ""
            except Exception:
                pass
            return False, "服务未在运行"
        return False, why

    def _order_url(self):
        return "http://%s:%d/" % (self._lan_ip(), self._order_port())

    def _order_toggle(self):

        ok, _ = self._http_alive()
        if ok:
            try:
                d = getattr(self, "_httpd", None)
                if d is not None:
                    d.shutdown()
                    d.server_close()
            except Exception:
                pass
            self._httpd = None
            self._http_started = False

            _RP["manual_stop"] = True
            self._toast("点播服务已停止 ⛔（自启动设置未变）")
        else:
            _RP["manual_stop"] = False
            ok2, why2 = self._order_start()
            if ok2:
                self._toast("点播服务已启动 ✅（%s）" % self._order_url())
            else:
                self._toast("启动失败 ✗：%s" % (why2 or "端口被占用？"))

    def _order_start(self):

        if getattr(self, "_http_started", False):
            ok, why = self._http_alive()
            if ok:
                return True, ""
            if not why:
                return False, "服务未在运行"
        port = self._order_port()
        info = self._order_probe_info()
        if info:

            try:
                self._order_port_override = int(info.get("port") or port)
            except Exception:
                pass
            self._http_started = True
            _RP["spider"] = self
            self.log("order httpd adopted on :%d" % self._order_port())
            return True, ""
        root = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, fmt, *args):
                try:
                    root.log("http: %s" % (fmt % args))
                except Exception:
                    pass

            def _send(self, code, ctype, body, extra=None):
                try:
                    self.send_response(code)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Cache-Control", "no-store")
                    for k, v in (extra or {}).items():
                        self.send_header(k, v)
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(body)
                except Exception:
                    pass

            _GOBTN = ('<button class="go" type="submit">'
                     "&#128269;</button>")

            def _html(self, code, text):
                self._send(code, "text/html; charset=utf-8",
                           text.encode("utf-8"))

            def _json(self, obj):
                import json as _j
                self._send(200, "application/json; charset=utf-8",
                           _j.dumps(obj, ensure_ascii=False)
                           .encode("utf-8"))

            def _redirect(self, to):
                try:
                    self.send_response(302)
                    self.send_header("Location", to)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                except Exception:
                    pass

            def q(self, sql, args=()):
                return root.query(sql, args)

            def esc(self, t):
                return (str(t or "").replace("&", "&amp;")
                        .replace("<", "&lt;").replace(">", "&gt;")
                        .replace('"', "&quot;")
                        .replace("'", "&#39;"))

            def do_GET(self):
                p = self.path.split("?")[0]
                qs = {}
                try:
                    from urllib.parse import parse_qs as _pqs, urlsplit as _us
                    qs = _pqs(_us(self.path).query)
                except Exception:
                    pass

                if p in ("/", "/index.html"):
                    kw = (qs.get("q") or [""])[0].strip()
                    if kw:
                        try:
                            root_sp = self.server.spider
                            root_sp._hist_add(kw)
                        except Exception:
                            pass
                        return self.page_search(
                            kw, (qs.get("p") or [""])[0])
                    return self.page_home()

                if p == "/browse":
                    cat = (qs.get("cat") or [""])[0].strip()
                    t = (qs.get("t") or [""])[0].strip()
                    pg = (qs.get("p") or ["1"])[0].strip()
                    try:
                        if t.isdigit():
                            return self.page_type_songs(
                                int(t), int(pg) if pg.isdigit() else 1,
                                int(cat) if cat.isdigit() else None)
                        if cat.isdigit():
                            return self.page_browse(int(cat))
                        return self.page_browse(None)
                    except Exception:
                        return self._html(200, self.wrap(
                            "曲库", "<p class='note'>曲库暂时读不出来，"
                            "稍后再试。</p>", tab="browse"))

                if p == "/queue":
                    return self.page_queue()

                if p == "/qr":
                    try:
                        m = qr_matrix(root._order_url(), border=2)
                        png = qr_png(m, scale=4)
                        self._send(200, "image/png", png)
                    except Exception as e:
                        root.log("qr fail: %s" % e)
                        self._send(404, "text/plain", b"qr error")
                    return

                if p == "/logs":
                    body = "\n".join(_LOGBUF[-400:])
                    self._send(200, "text/plain; charset=utf-8",
                               body.encode("utf-8"))
                    return

                if p == "/status":
                    q = [x for x in root._queue_load() if not x.get("done")]
                    import json as _j
                    self._send(200, "application/json; charset=utf-8",
                               _j.dumps({"ok": 1, "v": ORDER_SVC_VER, "pending": len(q), "port":
                                         root._order_port(),
                                         "skey": root._site_key(),
                                         "logs": len(_LOGBUF)},
                                        ensure_ascii=False).encode("utf-8"))
                    return

                self._html(404, self.wrap("404", "<p>没有这个页面。</p>"))

            def do_POST(self):
                p = self.path.split("?")[0]
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                form = {}
                try:
                    from urllib.parse import parse_qs as _pqs
                    form = _pqs(raw.decode("utf-8", "replace"))
                except Exception:
                    pass

                if p == "/order":
                    num = (form.get("number") or [""])[0].strip()
                    self.handle_order(num)
                    return

                if p == "/orderBatch":
                    cart = (form.get("cart") or [""])[0].strip()
                    self.handle_batch(cart)
                    return

                if p == "/api/play":
                    sp = _RP.get("spider") or root
                    ok, why = sp._api_play(
                        (form.get("number") or [""])[0].strip(),
                        force=True)
                    self._json({"ok": 1 if ok else 0, "msg": why})
                    return

                if p == "/api/next":
                    sp = _RP.get("spider") or root
                    ok, why = sp._play_next()
                    self._json({"ok": 1 if ok else 0,
                                "msg": why or "切歌成功"})
                    return

                if p == "/api/done":
                    sp = _RP.get("spider") or root
                    num = (form.get("number") or [""])[0].strip()
                    if num.isdigit():
                        sp._queue_mark_done(int(num))
                        try:
                            if int(_RP.get("now") or 0) == int(num):
                                _RP["now"] = 0
                        except Exception:
                            pass
                    self._json({"ok": 1})
                    return

                if p == "/api/top":
                    sp = _RP.get("spider") or root
                    num = (form.get("number") or [""])[0].strip()
                    o, w = sp._queue_top(num)
                    self._json({"ok": 1 if o else 0,
                                "msg": w or "已排到待唱最后一位"})
                    return

                if p == "/api/first":
                    sp = _RP.get("spider") or root
                    num = (form.get("number") or [""])[0].strip()
                    o, w = sp._queue_first(num)
                    self._json({"ok": 1 if o else 0,
                                "msg": w or "已排到待唱第一位，下一首播放"})
                    return

                if p == "/api/del":
                    sp = _RP.get("spider") or root
                    num = (form.get("number") or [""])[0].strip()
                    o, w = sp._queue_del(num)
                    self._json({"ok": 1 if o else 0, "msg": w or "已移除"})
                    return

                if p == "/api/park":
                    sp = _RP.get("spider") or root
                    num = (form.get("number") or [""])[0].strip()
                    o, w = sp._queue_park(num)
                    self._json({"ok": 1 if o else 0, "msg": w or "已移到待定区"})
                    return

                if p == "/api/unpark":
                    sp = _RP.get("spider") or root
                    num = (form.get("number") or [""])[0].strip()
                    o, w = sp._queue_unpark(num)
                    self._json({"ok": 1 if o else 0,
                                "msg": w or "已排回待唱最后一位"})
                    return

                self._html(404, self.wrap("404", "<p>没有这个页面。</p>"))

            def handle_order(self, num):
                if not num.isdigit():
                    return self._json({"ok": 0, "msg": "编号不合法"})
                rows = self.q("SELECT number,name,singer_names FROM song "
                              "WHERE number=? AND status=1", (int(num),))
                if not rows:
                    return self._json({"ok": 0,
                                       "msg": "曲库里没有这首歌"})
                r = rows[0]
                ok, why = root._queue_add(r["number"], r["name"],
                                          r["singer_names"])
                if ok:
                    qn = len([x for x in root._queue_load()
                              if not x.get("done")])
                    self._json({"ok": 1,
                                "msg": "🎤 已加入歌单《%s》· 待唱 %d 首"
                                       % (r["name"], qn)})
                else:
                    self._json({"ok": 0, "msg": "《%s》已在歌单里"
                                % r["name"]})

            def handle_batch(self, cart):
                import json as _j
                try:
                    items = _j.loads(cart)
                    if not isinstance(items, list):
                        items = []
                except Exception:
                    items = []
                okn, skip = [], []
                for it in items:
                    try:
                        num = int(str(it.get("n") or it.get("number") or ""))
                    except Exception:
                        continue
                    rows = self.q("SELECT number,name,singer_names FROM song "
                                  "WHERE number=? AND status=1", (num,))
                    if not rows:
                        continue
                    r = rows[0]
                    ok, _w = root._queue_add(r["number"], r["name"],
                                             r["singer_names"])
                    (okn if ok else skip).append(r["name"])
                self.page_batch(okn, skip)

            def wrap(self, title, body, back=True, tab="search", logo=False):
                nav = ""
                rjs = ""
                js = ("<script>"
                      "function toast(m){var t=document.getElementById"
                      "('toast');t.innerHTML=m;t.style.opacity=1;"
                      "clearTimeout(t._h);t._h=setTimeout(function(){"
                      "t.style.opacity=0},1600)}"
                      "function act(u,n,btn,label,body){"
                      "var f=body||('number='+encodeURIComponent(n));"
                      "var was=btn.innerHTML;btn.disabled=true;"
                      "var st=document.getElementById('status');"
                      "if(st){st.textContent='推送中…';"
                      "st.style.display='block'}"
                      "fetch(u,{method:'POST',body:f,"
                      "headers:{'Content-Type':"
                      "'application/x-www-form-urlencoded'}})"
                      ".then(function(r){return r.json()})"
                      ".then(function(d){"
                      "if(st&&d&&d.msg){st.textContent="
                      "(d.ok===1?'✓ ':'✗ ')+d.msg;"
                      "st.style.display='block'}"
                      "toast((d.ok===1?'✓ ':'✗ ')+(d.msg||('完成')));"
                      "var rf=(u=='/api/play'||u=='/api/first'||"
                      "u=='/api/top'||u=='/api/next'||"
                      "u=='/api/del'||u=='/api/done'||"
                      "u=='/api/park'||u=='/api/unpark');"
                      "if(d.ok===1&&rf)"
                      "setTimeout(function(){location.reload();},900);"
                      "btn.innerHTML=(d.ok===1)?'&#10003;':'&#10005;';"
                      "setTimeout(function(){btn.innerHTML=was;"
                      "btn.disabled=false},1200)})"
                      ".catch(function(){toast('网络错误');"
                      "if(st){st.textContent='✗ 推送失败，请重试';"
                      "st.style.display='block'}"
                      "btn.innerHTML=was;btn.disabled=false});"
                      "return false}"
                      "</script>")
                tabs = ("<div class='tabs'>"
                        "<a class='tab%s' href='/'>&#x1f50d; 搜索</a>"
                        "<a class='tab%s' href='/queue'>&#x1f3a4; 点歌</a>"
                        "<a class='tab%s' href='/browse'>&#x1f4da; 曲库</a>"
                        "</div>" % (" on" if tab == "search" else "",
                                    " on" if tab == "queue" else "",
                                    " on" if tab == "browse" else ""))
                if logo:
                    body = ("<div class='logo'><div class='logo-t'>" "爱KTV点播</div>"
                            "<div class='logo-s'>手机扫码 · 电视开唱</div></div>") + body
                return ("<!doctype html><html><head><meta charset='utf-8'>"
                        "<meta name='viewport' content='width=device-width,"
                        "initial-scale=1'>"
                        "<title>%s · 爱KTV点播</title><style>"
                        "body{background:#0b0c10;color:#e8e8ea;font-family:"
                        "-apple-system,sans-serif;margin:0;padding:14px}"
                        "a{color:#7fb3ff;text-decoration:none}"
                        ".row{background:#16181f;border-radius:10px;"
                        "padding:7px 8px;margin:6px 0;display:flex;"
                        "align-items:center;gap:6px}"
                        ".grow{flex:1;min-width:0}"
                        ".ord{display:inline-block;min-width:18px;text-align:center;font-size:11px;font-weight:700;color:#0b0c10;background:#1db954;border-radius:8px;padding:1px 5px;margin-right:6px;vertical-align:middle;position:relative;top:-3px}.name{display:inline;font-size:15px;overflow:hidden;"
                        "text-overflow:ellipsis;white-space:nowrap;"
                        "word-break:break-all}"
                        ".singer{color:#8b8f99;font-size:12px;margin-top:3px;"
                        "overflow:hidden;text-overflow:ellipsis;"
                        "white-space:nowrap}"
                        "form{margin:0;display:flex;align-items:center;gap:8px;width:100%%}"
                        "button{background:#2563eb;color:#fff;border:0;"
                        "border-radius:8px;padding:4px 7px;font-size:12px;flex:none;white-space:nowrap}"
                        "button.plus{background:#374151}"
                        "button.play{background:#16a34a}"
                        ".ok{color:#4ade80}.note{color:#8b8f99;font-size:13px}"
                        "h3{margin:16px 0 4px;font-size:15px;color:#aab}"
                        "input{background:#1f2229;color:#e8e8ea;border:1px"
                        " solid #333844;border-radius:8px;padding:10px;"
                        "font-size:16px;flex:1;min-width:0;box-sizing:border-box}"
                        ".arr{color:#5a6070;font-size:20px;flex:none}"
                        "a.row{color:inherit;text-decoration:none}"
                        ".badge{color:#8b8f99;font-size:12px;background:#1f2229;"
                        "border-radius:10px;padding:2px 8px;flex:none}"
                        ".logo{text-align:center;padding:26px 0 6px;color:#e8e8ea}"
                        ".logo-t{display:inline-block;font-size:30px;font-weight:800;letter-spacing:2px;background:linear-gradient(90deg,#38bdf8,#22d3ee,#34d399,#facc15,#fb7185);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:#1db954}"
                        ".logo-s{font-size:13px;color:#8b8f99;margin-top:5px}"
                        ".tabs{display:flex;gap:6px;margin:2px 0 14px;"
                        "background:#14161c;border-radius:14px;padding:5px}"
                        ".status{background:#152018;border:1px solid "
                        "#2e7d43;border-radius:10px;color:#7fd899;"
                        "font-size:15px;padding:9px 12px;margin:10px 0}"
                        ".tab{flex:1;text-align:center;padding:11px 0;"
                        "border-radius:12px;color:#c8cdd6;"
                        "background:#1b1e26;"
                        "text-decoration:none;font-size:19px}"
                        ".tab.on{background:#1db954;color:#0b0c10;"
                        "font-weight:700}"
                        ".pg{display:inline-block;padding:9px 18px;"
                        "background:#1a1d25;border:1px solid #2a2d36;"
                        "border-radius:20px;color:#e8e8ea;"
                        "text-decoration:none;font-size:14px}"
                        ".pg.off{color:#5a5f6a;opacity:.55}"
                        ".hwrap{display:flex;flex-wrap:wrap;margin:10px 0 4px}"
                        ".hist{display:inline-block;margin:3px 6px 3px 0;"
                        "padding:4px 10px;background:#1f2229;"
                        "border:1px solid #2a2d36;border-radius:14px;"
                        "color:#c8cdd6;text-decoration:none;font-size:12px}"
                        ".go{flex:none;background:#1db954;color:#0b0c10;"
                        "border:0;border-radius:10px;padding:0 16px;"
                        "font-size:20px;margin-left:8px;height:42px}"
                        "#toast{position:fixed;left:50%%;bottom:22%%;"
                        "transform:translateX(-50%%);background:#263041;"
                        "color:#fff;border-radius:20px;padding:10px 20px;"
                        "font-size:14px;opacity:0;transition:opacity .25s;"
                        "pointer-events:none;max-width:80vw;z-index:99}"
                        "</style></head><body>%s<div id='toast'></div>%s%s%s%s"
                        "</body></html>"
                        % (self.esc(title), tabs, body, nav, js, rjs))

            def page_home(self):
                q = [x for x in root._queue_load() if not x.get("done")]
                now_n = 0
                try:
                    now_n = int(_RP.get("now") or 0)
                except Exception:
                    pass
                buf = ["<form method='get' action='/'>"
                "<input name='q' type='search' placeholder='搜歌名 / 歌手 / 首字母' required>" + self._GOBTN + "</form>",
                       "<p class='note'>待唱 %d 首%s</p>"
                       % (len(q), (" · 🎤正在唱《%s》" % self._now_name(q, now_n))
                          if now_n else "")]
                if q:
                    for x in q[:5]:
                        buf.append("<div class='row'><div class='grow'>"
                                   "<div class='name'>%s</div>"
                                   "<div class='singer'>%s</div></div></div>"
                                   % (self.esc(x.get("name")),
                                      self.esc(x.get("singer"))))
                hist = root._hist_get() if "root" in dir(self) else []
                try:
                    hist = self.server.spider._hist_get()
                except Exception:
                    hist = []
                if hist:
                    hk = ["<a class='hist' href='/?q=%s'>%s</a>"
                          % (_quote(h, safe=""), self.esc(h)) for h in hist]
                    buf.insert(1, "<div class='hwrap'>%s</div>"
                              % "".join(hk))
                self._html(200, self.wrap("手机点歌", "".join(buf),
                                          back=False, tab="search", logo=True))

            def _now_name(self, q, now_n):
                for x in q:
                    if int(x.get("number") or 0) == now_n:
                        return self.esc(x.get("name"))
                return ""

            def page_search(self, kw, p=1):
                per = 50
                try:
                    p = max(int(p or 1), 1)
                except Exception:
                    p = 1
                rows, total, pyhit = self.server.spider._web_search(kw, per=per, p=p)
                pages = max(1, (total + per - 1) // per)
                if p > pages:
                    p = pages
                if not rows:
                    body = ("<div id='status' class='status' "
                            "style='display:none'></div>"
                            "<p class='note'>没搜到「%s」，换个词试试。</p>"
                            "<p class='note'>试试拼音首字母（周杰伦 → ZJL）"
                            "或多词空格隔开（屠洪刚 你）。</p>"
                            "<form method='get' action='/'>"
                            "<input name='q' value='%s'>%s</form>"
                            % (self.esc(kw), self.esc(kw), self._GOBTN))
                    return self._html(200, self.wrap("搜索：" + kw, body))
                buf = []
                for r in rows:
                    n = self.esc(r["name"])
                    s2 = self.esc(r["singer_names"])
                    num = int(r["number"])
                    buf.append(
                        "<div class='row'><div class='grow'>"
                        "<div class='name'>%s</div><div class='singer'>%s"
                        "</div></div>"
                        '<button class="play" onclick="return act(\'/api/play\',%d,this,\'现在唱\')">&#9889; 现在唱</button>'
                        '<button onclick="return act(\'/order\',%d,this,\'\U0001f3a4 点歌\')">\U0001f3a4 点歌</button>'
                        "</div>" % (n, s2, num, num))
                pager = ""
                if pages > 1:
                    pg1 = ("<a class='pg' href='/?q=%s&amp;p=%d'>&#8249; 上一页"
                           "</a>" % (self.esc(kw), p - 1) if p > 1 else
                           "<span class='pg off'>&#8249; 上一页</span>")
                    pg2 = ("<a class='pg' href='/?q=%s&amp;p=%d'>下一页 &#8250;"
                           "</a>" % (self.esc(kw), p + 1) if p < pages else
                           "<span class='pg off'>下一页 &#8250;</span>")
                    pager = ("<div style='display:flex;gap:10px;"
                             "justify-content:center;align-items:center;"
                             "margin:16px 0 30px'>"
                             "%s<span class='badge'>%d/%d</span>%s</div>"
                             % (pg1, p, pages, pg2))
                hint = ("拼音命中「%s」" % self.esc(pyhit)) if pyhit else ""
                body = ("<div id='status' class='status' "
                        "style='display:none'></div>"
                        "<form method='get' action='/'>"
                        "<input name='q' value='%s'>%s</form>"
                        "<p class='note'>%s共 %d 首 · 第 %d/%d 页"
                        " ·「&#9889; 现在唱」电视立即抢播"
                        " ·「\U0001f3a4 点歌」加入歌单</p>%s%s"
                        "" % (self.esc(kw), self._GOBTN, hint, total, p, pages,
                              "".join(buf), pager))
                self._html(200, self.wrap("搜索：" + kw, body, tab="search"))

            def page_browse(self, cid):
                root = self.server.spider
                cats = sorted(CATS.items())
                buf = []
                if cid is None:
                    for c, nm in cats:
                        buf.append(
                            "<a class='row' href='/browse?cat=%d'>"
                            "<div class='grow'><div class='name'>%s</div>"
                            "</div><span class='arr'>&#8250;</span></a>"
                            % (c, self.esc(nm)))
                    return self._html(200, self.wrap("曲库", "".join(buf),
                                                     tab="browse"))
                rows = root._cat_types(cid)
                nm = CATS.get(cid, "曲库")
                for ti, tn, n in rows:
                    buf.append(
                        "<a class='row' href='/browse?cat=%d&t=%d'>"
                        "<div class='grow'><div class='name'>%s</div>"
                        "<div class='singer'>%d 首</div></div>"
                        "<span class='arr'>&#8250;</span></a>"
                        % (cid, ti, self.esc(tn), n))
                buf.append("<p class='note'>共 %d 个曲风，点进去挑歌</p>"
                           % len(rows))
                hd = ("<div class='hd'><a class='pg' href='/browse'>"
                      "&#8249; 返回曲库</a><span class='hdttl'>%s</span>"
                      "</div>" % self.esc(nm))
                return self._html(200, self.wrap(nm, hd + "".join(buf),
                                                 tab="browse"))

            def page_type_songs(self, t, p=1, cid=None):

                root = self.server.spider
                name = root._types().get(t, "曲风")
                per = 100
                try:
                    p = max(int(p or 1), 1)
                except Exception:
                    p = 1
                crow = root.query("SELECT COUNT(*) AS c FROM song "
                                  "WHERE type_id=? AND status=1", (t,))
                total = int(crow[0]["c"]) if crow else 0
                pages = max(1, (total + per - 1) // per)
                if p > pages:
                    p = pages
                if cid is None:
                    _c2 = root.query("SELECT category_id AS c FROM song_type "
                                     "WHERE id=?", (t,))
                    cid = int(_c2[0]["c"]) if _c2 else 0
                rows = root.query(
                    "SELECT number,name,singer_names FROM song "
                    "WHERE type_id=? AND status=1 "
                    "ORDER BY temperature DESC LIMIT ? OFFSET ?",
                    (t, per, (p - 1) * per))
                buf = ["<p class='note'>%s · 共 %d 首 · 第 %d/%d 页"
                       "（按热度排）</p>" % (name, total, p, pages)]
                for r in rows:
                    n, nm, sg = r["number"], r["name"], r["singer_names"]
                    buf.append(
                        "<div class='row'><div class='grow'>"
                        "<div class='name'>%s</div>"
                        "<div class='singer'>%s · %d</div></div>"
                        '<button class="play" onclick="return act(\'/api/play\',%d,this,\'现在唱\')">&#9889; 现在唱</button>'
                        '<button onclick="return act(\'/order\',%d,'
                        'this,\'点歌\')">点歌</button>'
                        "</div>" % (nm, sg, n, n, n))
                if pages > 1:
                    pg1 = ("<span class='pg off'>&#8249; 上一页</span>"
                           if p <= 1 else
                           "<a class='pg' href='/browse?t=%d&p=%d'>"
                           "&#8249; 上一页</a>"
                           % (t, p - 1))
                    pg2 = ("<span class='pg off'>下一页 &#8250;</span>"
                           if p >= pages else
                           "<a class='pg' href='/browse?t=%d&p=%d'>"
                           "下一页 &#8250;</a>"
                           % (t, p + 1))
                    buf.append("<div style='display:flex;gap:10px;"
                               "justify-content:center;align-items:center;"
                               "margin:16px 0 30px'>%s"
                               "<span class='badge'>%d/%d</span>%s</div>"
                               % (pg1, p, pages, pg2))
                hd = ("<div class='hd'><a class='pg' "
                      "href='/browse?cat=%d'>&#8249; 返回上一级</a>"
                      "<span class='hdttl'>%s</span></div>"
                      % (cid, self.esc(name)))
                return self._html(200, self.wrap(name, hd + "".join(buf),
                                                 tab="browse"))

            def page_queue(self):
                q = root._queue_load()
                pend = [x for x in q if not int(x.get("done") or 0)]
                park = [x for x in q if int(x.get("done") or 0) == 2]
                done = [x for x in q if int(x.get("done") or 0) == 1]
                try:
                    now_n = int(_RP.get("now") or 0)
                except Exception:
                    now_n = 0
                buf = []
                now_row = None
                if now_n:
                    for x in q:
                        if int(x.get("number") or 0) == now_n:
                            now_row = x
                            break
                if now_row is None and now_n:
                    now_row = {"number": now_n, "name": "", "singer": ""}
                if now_row is not None:
                    buf.append(
                        "<div class='row' style='outline:2px solid #e50914'>"
                        "<div class='grow'><div class='name'>"
                        "&#127908; 正在唱：%s</div>"
                        "<div class='singer'>%s</div></div>"
                        "<button class='play' onclick=\"return act("
                        "'/api/next',0,this,'切歌')\">&#9654;&#65039; 切歌"
                        "</button></div>"
                        % (self.esc(now_row.get("name")) or
                           ("#" + str(int(now_row.get("number") or 0))),
                           self.esc(now_row.get("singer") or "")))
                buf.append("<div id='status' class='status' "
                           "style='display:none'></div>")
                pend_v = [x for x in pend
                          if int(x.get("number") or 0) != now_n]
                if pend_v:
                    buf.append("<div class='row'><div class='grow'>"
                               "<b>待唱 %d 首</b></div></div>" % len(pend_v))
                    for xi, x in enumerate(pend_v[-30:]):
                        num = int(x.get("number") or 0)
                        buf.append(
                            "<div class='row'><div class='grow'>"
                            "<span class='ord'>%d</span>"
                            "<div class='name'>%s</div>"
                            "<div class='singer'>%s</div></div>"
                            "<button class='play' onclick=\"return act("
                            "'/api/play',%d,this,'现在唱')\">&#9889; 现在唱"
                            "</button>"
                            "<button class='plus' onclick=\"return act("
                            "'/api/first',%d,this,'置顶')\">&#x2191; 置顶"
                            "</button>"
                            "<button class='plus' onclick=\"return act("
                            "'/api/park',%d,this,'移出')\">&#10005; 移出"
                            "</button></div>"
                            % (xi + 1, self.esc(x.get("name")),
                               self.esc(x.get("singer")), num, num, num))
                else:
                    buf.append("<p class='note'>待唱 0 首，去「搜索」页点歌"
                               "</p>")
                buf.append("<div class='row'><div class='grow'>"
                           "<b>待定 %d 首</b>（点「🎤 点歌」回到待唱，"
                           "「✖ 移除」删掉）</div></div>" % len(park))
                if park:
                    for x in park[-30:]:
                        num = int(x.get("number") or 0)
                        buf.append(
                            "<div class='row'><div class='grow'>"
                            "<div class='name' style='color:#c8a24a'>%s</div>"
                            "<div class='singer'>%s</div></div>"
                            "<button class='play' onclick=\"return act("
                            "'/api/unpark',%d,this,'点歌')\">&#127908; 点歌"
                            "</button>"
                            "<button class='plus' onclick=\"return act("
                            "'/api/del',%d,this,'移除')\">&#10005; 移除"
                            "</button></div>"
                            % (self.esc(x.get("name")),
                               self.esc(x.get("singer")), num, num))
                else:
                    buf.append("<p class='note'>待定区是空的</p>")
                buf.append("<h3>已唱 %d</h3>" % len(done))
                for x in done[-10:]:
                    num = int(x.get("number") or 0)
                    buf.append(
                        "<div class='row'><div class='grow'>"
                        "<div class='name' style='color:#666'>%s</div>"
                        "<div class='singer'>%s</div></div>"
                        "<button class='play' onclick=\"return act("
                        "'/api/top',%d,this,'重唱')\">&#8635; 重唱</button>"
                        "<button class='plus' onclick=\"return act("
                        "'/api/del',%d,this,'移除')\">"
                        "&#10005; 移除</button></div>"
                        % (self.esc(x.get("name")),
                           self.esc(x.get("singer")), num, num))
                self._html(200, self.wrap("点歌队列", "".join(buf),
                                          back=False, tab="queue"))

        class HTTPD(ThreadingHTTPServer):
            daemon_threads = True
            allow_reuse_address = True

            def __init__(self, addr, handler, spider=None):
                self.spider = spider
                ThreadingHTTPServer.__init__(self, addr, handler)

        bound = None
        last_err = ""
        for p_ in range(port, port + 6):
            try:
                root._httpd = HTTPD(("0.0.0.0", p_), Handler, root)
                bound = p_
                break
            except Exception as e:
                last_err = str(e)[:70]
                root.log("order httpd bind fail :%d %s" % (p_, e))
        if bound is None:
            root._order_why = last_err
            return False, last_err
        if bound != port:
            root._order_port_override = bound
            root.log("order port %d busy, fallback %d" % (port, bound))
        port = bound
        root._order_why = ""

        def _run():
            try:
                root._httpd.serve_forever()
            except Exception:
                pass

        th = threading.Thread(target=_run, name="ktv-order-httpd")
        th.daemon = True
        root._http_thread = th
        root._http_started = True
        th.start()
        root.log("order httpd :%d up, url=%s" % (port, root._order_url()))
        _RP["spider"] = self
        return True, ""

    def _order_show(self):

        ok, why = self._http_alive()
        if not ok:
            self._toast("服务未运行，正在启动…")
            ok, why = self._order_start()
            if not ok:
                self._info_dialog("📱 局域网点播 · 启动失败",
                                  "端口 %d 绑定失败：\n%s\n\n"
                                  "常见原因：端口被别的应用占用（去「点播端口」"
                                  "卡改一个），或 Wi-Fi 已断开。"
                                  % (self._order_port(), why or "?"), "")
                return

        _RP["manual_stop"] = False
        url = self._order_url()
        body = ("手机连同一个 Wi-Fi，扫下方二维码或打开：\n%s\n\n"
                "顶部三个页签：\n"
                "· 🔍 搜索 —— 每首歌两个按钮：\n"
                "　⚡ 现在唱 = 立刻抢占电视播放\n"
                "　🎤 点歌 = 排进待唱队列\n"
                "· 🎤 点歌 —— 正在唱 / 待唱 / 待定 / 已唱\n"
                "　待唱：⚡现在唱 · ↑置顶下一首 · ✕移出到待定\n"
                "　待定：🎤点歌回到队列 · ✕移除\n"
                "　已唱：↻重唱排回队尾 · ✕移除\n"
                "· 📚 曲库 —— 按分类浏览点歌\n\n"
                "电视端：点播分类「▶ 播放全部」\n"
                "可直接进播放页，底部就是整条待唱。\n\n"
                "当前待唱 %d 首 · 待定 %d 首。"
                % (url,
                   len([x for x in self._queue_load()
                        if not x.get("done") and int(x.get("done") or 0) == 0]),
                   len([x for x in self._queue_load()
                        if int(x.get("done") or 0) == 2])))
        png = b""
        try:
            png = qr_png(qr_matrix(url, border=2), scale=4)
        except Exception as e:
            self.log("order show qr fail: %s" % e)
        self._info_dialog("📱 局域网点播", body, url, qr_bytes=png)

    def _order_detail_page(self):

        try:
            _orderauto_c = self._orderauto_card()
        except Exception as _e:
            _orderauto_c = ("⚙ 点播自启动", "读取失败",
                            "%s" % str(_e)[:80])
        ok, why = self._http_alive()
        if not ok and not _RP.get("manual_stop"):
            ok2, why2 = self._order_start()
            if not ok2:
                c = self._note_card("order:help", "📱 点播服务启动失败",
                                    "点我看原因", "端口 %d：\n%s\n\n"
                                    "多数是端口被占用——去「⚙设置 → 🔢 点播端口」"
                                    "换一个（如 18321、18080）。"
                                    % (self._order_port(), why2 or why or "?"))
                c["action"] = "order:help"
                return self._page([c], 1)
            ok, _ = self._http_alive()
        q = [x for x in self._queue_load() if not x.get("done")]
        items = []
        try:
            items.append(self._order_switch_card())
        except Exception:
            pass
        try:
            items.append(self._note_card("order:auto", *_orderauto_c,
                                         folder=True))
        except Exception:
            pass

        try:
            items.append(self._orderport_card())
        except Exception:
            pass

        try:
            items.append(self._fs_card())
            try:
                items.append(self._order_all_card())
            except Exception as e:
                self._dexc("order all card", e)
        except Exception:
            pass

        for i, x in enumerate(q[:30]):
            num = int(x.get("number") or 0)
            rk = ("▶ 下一首 · " if i == 0 else "待唱 · ") + str(x.get("singer") or "")
            items.append(self._note_card(
                "s%d" % num, x.get("name") or str(num), rk,
                "手机已点 · 点卡直接播放"))
        if not q:
            items.append(self._note_card(
                "order:empty", "（队列空）", "",
                "手机扫码后点歌，这里就会出现。", folder=True))
        return self._page(items, 1)

    def _dexc(self, tag, e):

        try:
            self.log("%s: %r" % (tag, e))
        except Exception:
            pass

    def _app_ctx(self):

        try:
            from java import jclass
        except Exception:
            return None
        try:
            ctx = jclass("android.app.ActivityThread").currentApplication()
            if ctx is not None:
                return ctx
        except Exception as e:
            self._dexc("ctx activitythread", e)
        try:
            ctx = jclass("android.app.AppGlobals").getInitialApplication()
            if ctx is not None:
                return ctx
        except Exception as e:
            self._dexc("ctx appglobals", e)
        try:
            Python = jclass("com.chaquo.python.Python")
            ctx = Python.getPlatform().getApplication()
            if ctx is not None:
                return ctx
        except Exception as e:
            self._dexc("ctx chaquo", e)
        return None

    def _site_key(self):

        if _RP.get("skey"):
            return _RP["skey"]

        try:
            g = globals().get("siteKey")
            if g:
                _RP["skey"] = str(g)
                self.log("site key from shell global: %s" % _RP["skey"])
                return _RP["skey"]
        except Exception as e:
            self._dexc("skey global", e)
        try:
            if time.time() - float(_RP.get("skey_at") or 0) < 600:
                return ""
        except Exception:
            pass
        _RP["skey_at"] = time.time()
        try:
            key = self._site_key_discover() or ""
        except Exception as e:
            self._dexc("skey discover", e)
            key = ""
        if key:
            _RP["skey"] = key
            self.log("site key found: %s" % key)
        return key

    def _site_key_discover(self):

        ctx = None
        try:
            ctx = self._app_ctx()
        except Exception:
            ctx = None
        roots = []
        if ctx is not None:
            for meth in ("getFilesDir", "getCacheDir"):
                try:
                    f = getattr(ctx, meth)()
                    if f is not None:
                        roots.append(str(f.getAbsolutePath()))
                except Exception:
                    pass
            try:
                f = ctx.getExternalFilesDir(None)
                if f is not None:
                    roots.append(str(f.getAbsolutePath()))
            except Exception:
                pass
            try:
                base = os.path.dirname(roots[0]) if roots else ""
                if base:
                    roots.append(os.path.join(base, "databases"))
                    roots.append(os.path.join(base, "shared_prefs"))
            except Exception:
                pass
        for extra in ("/storage/emulated/0/VodPlus/LocalFiles",
                      "/storage/emulated/0/WebHTV/LocalFiles",
                      "/storage/emulated/0/本地包汇总/海豚",
                      "/storage/emulated/0/Download/Minis"):
            if extra not in roots:
                roots.append(extra)
        texts = []

        def _take(path, cap=8 * 1024 * 1024):
            try:
                if os.path.getsize(path) > cap:
                    return
                with open(path, "rb") as fh:
                    text = fh.read().decode("utf-8", "ignore")
            except Exception:
                return
            if ("爱KTV" in text) or ("KTV.py" in text):
                texts.append((path, text))

        for r_ in roots:
            if not r_ or not os.path.isdir(r_):
                continue
            try:
                for dirpath, dirs, files in os.walk(r_):
                    for fn in files:
                        low = fn.lower()
                        if low.endswith((".json", ".xml", ".db", ".txt")):
                            _take(os.path.join(dirpath, fn))
            except Exception:
                pass
        for path, text in texts:
            if text.startswith("SQLite format 3") and not path.endswith(
                    ("-wal", "-shm")):
                k = self._site_key_from_db(path)
                if k:
                    return k
            k = self._site_key_parse(text) or \
                self._site_key_parse_loose(text)
            if k:
                return k
        return ""

    def _site_key_parse(self, text):

        try:
            obj = json.loads(text)
        except Exception:
            return ""
        if not isinstance(obj, dict):
            return ""
        sites = obj.get("sites")
        if not isinstance(sites, list):
            return ""
        for st in sites:
            if not isinstance(st, dict) or not st.get("key"):
                continue
            blob = " ".join(str(st.get(k) or "")
                            for k in ("name", "api", "ext"))
            if "爱KTV" in blob or "KTV" in blob:
                return str(st["key"])
        return ""

    def _site_key_parse_loose(self, text):

        try:
            poss = [m.start() for m in re.finditer(r"KTV\.py", text)]
            poss += [m.start() for m in re.finditer("爱KTV", text)]
            for pos in poss:
                pre = text[max(0, pos - 400):pos]
                km = None
                for mm in re.finditer(r'"key"\s*:\s*"([^"]{1,64})"', pre):
                    km = mm
                if km:
                    return km.group(1)
                post = text[pos:pos + 400]
                km = re.search(r'"key"\s*:\s*"([^"]{1,64})"', post)
                if km:
                    return km.group(1)
        except Exception:
            pass
        return ""

    def _site_key_from_db(self, dbfile):

        tmpdir = None
        try:
            import shutil
            import tempfile
            tmpdir = tempfile.mkdtemp(prefix="ktvkey")
            dst = os.path.join(tmpdir, "tv.db")
            shutil.copy2(dbfile, dst)
            for suf in ("-wal", "-shm"):
                if os.path.exists(dbfile + suf):
                    try:
                        shutil.copy2(dbfile + suf, dst + suf)
                    except Exception:
                        pass
            con = sqlite3.connect(dst)
            try:
                tables = [r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")]
                KEYC = ("key", "sitekey", "site_key")
                NAMEC = ("name", "vodname", "vod_name", "title")
                APIC = ("api", "apiurl", "api_url", "link", "url")
                JSONC = ("json", "config", "text", "data", "value", "content")

                def _pick(cols, cands):
                    low = [c.lower() for c in cols]
                    for cand in cands:
                        if cand in low:
                            return cols[low.index(cand)]
                    return ""

                for t in tables:
                    qt = '"' + t.replace('"', '""') + '"'
                    try:
                        cols = [c[1] for c in con.execute(
                            "PRAGMA table_info(%s)" % qt)]
                    except Exception:
                        continue
                    kc = _pick(cols, KEYC)
                    if not kc:
                        continue
                    nc = _pick(cols, NAMEC)
                    ac = _pick(cols, APIC)
                    wh, params = [], []
                    if nc:
                        wh.append('"%s" LIKE ?' % nc)
                        params.append("%爱KTV%")
                    if ac:
                        wh.append('"%s" LIKE ?' % ac)
                        params.append("%KTV.py%")
                    if not wh:
                        continue
                    try:
                        rows = con.execute(
                            'SELECT "%s" FROM %s WHERE (%s) LIMIT 5'
                            % (kc, qt, " OR ".join(wh)), params).fetchall()
                    except Exception:
                        continue
                    for r in rows:
                        if r and r[0]:
                            return str(r[0])
                for t in tables:
                    qt = '"' + t.replace('"', '""') + '"'
                    try:
                        cols = [c[1] for c in con.execute(
                            "PRAGMA table_info(%s)" % qt)]
                    except Exception:
                        continue
                    jc = _pick(cols, JSONC)
                    if not jc:
                        continue
                    try:
                        rows = con.execute(
                            'SELECT "%s" FROM %s WHERE "%s" LIKE ? LIMIT 3'
                            % (jc, qt, jc), ("%爱KTV%",)).fetchall()
                    except Exception:
                        continue
                    for r in rows:
                        if r and r[0]:
                            k = self._site_key_parse(str(r[0])) or \
                                self._site_key_parse_loose(str(r[0]))
                            if k:
                                return k
            finally:
                con.close()
        except Exception:
            pass
        finally:
            if tmpdir:
                try:
                    import shutil
                    shutil.rmtree(tmpdir, ignore_errors=True)
                except Exception:
                    pass
        return ""

    def _intent_video(self, ctx, key, detail_id, name, pic):

        try:
            from java import jclass
            Intent = jclass("android.content.Intent")
        except Exception as e:
            self._dexc("intent import", e)
            return False
        pkg = ""
        try:
            pkg = str(ctx.getPackageName())
        except Exception:
            pkg = ""
        cands = []
        for cand in ((pkg + ".ui.activity.VideoActivity") if pkg else "",
                     "com.fongmi.android.tv.ui.activity.VideoActivity"):
            if cand and cand not in cands:
                cands.append(cand)

        loader = None
        try:
            loader = ctx.getClassLoader()
        except Exception:
            loader = None
        for cls in cands:

            if loader is not None:
                try:
                    from java import jclass
                    Cls2 = jclass("java.lang.Class")
                    Cls2.forName(cls, False, loader)
                except Exception as e:
                    self.log("intent cls resolve warn %s: %s" % (cls, e))

            try:
                it = Intent()
                it.setClassName(pkg, cls)
                it.putExtra("key", key)
                it.putExtra("id", detail_id)
                it.putExtra("name", name or "")
                it.putExtra("pic", pic or "")
                it.putExtra("mark", "")
                it.addFlags(0x10000000)
                ctx.startActivity(it)
                self.log("remote play intent key=%s id=%s cls=%s"
                         % (key, detail_id, cls))
                return True
            except Exception as e:
                self._dexc("intent video %s" % cls, e)
        return False

    def _intent_view(self, ctx, url):

        try:
            from java import jclass
            Intent = jclass("android.content.Intent")
            Uri = jclass("android.net.Uri")
        except Exception as e:
            self._dexc("intent view import", e)
            return False
        pkg = ""
        try:
            pkg = str(ctx.getPackageName())
        except Exception:
            pkg = ""
        for use_pkg in (True, False):
            try:
                it = Intent(Intent.ACTION_VIEW)
                it.setDataAndType(Uri.parse(url), "video/*")
                if use_pkg and pkg:
                    it.setPackage(pkg)
                it.addFlags(0x10000000)
                ctx.startActivity(it)
                self.log("remote play view pkg=%s" % (pkg if use_pkg else "-"))
                return True
            except Exception as e:
                self._dexc("intent view pkg=%s" % use_pkg, e)
        return False

    def _fs_on(self):

        try:
            v = self._cfg_get().get("fullscreen")
        except Exception:
            v = None
        if v is None:
            return True
        return str(v) not in ("0", "off", "false", "no")

    def _fs_find_view(self, root, target):

        try:
            stack = [root]
            while stack:
                v = stack.pop(0)
                try:
                    tv = str(v.getText())
                except Exception:
                    tv = ""
                if tv and tv.strip() == target:
                    try:
                        if v.getVisibility() == 0:
                            return v
                    except Exception:
                        return v
                try:
                    for i in range(v.getChildCount()):
                        c = v.getChildAt(i)
                        if c is not None:
                            stack.append(c)
                except Exception:
                    pass
        except Exception as e:
            self._dexc("fs find", e)
        return None

    def _fs_find_by_id(self, root, rid):

        try:
            if root is None:
                return None
            try:
                if root.getId() == rid:
                    return root
            except Exception:
                pass
            try:
                n = root.getChildCount()
            except Exception:
                return None
            for i in range(n):
                try:
                    v = root.getChildAt(i)
                except Exception:
                    continue
                if v is None:
                    continue
                r = self._fs_find_by_id(v, rid)
                if r is not None:
                    return r
        except Exception:
            return None
        return None

    def _fs_click(self, target, timeout=15.0):

        import time as _t
        deadline = _t.time() + float(timeout)
        ready_deadline = _t.time() + 3.0
        tries = 0
        target = str(target or "").strip()
        act_seen = False
        dumped = False
        while _t.time() < deadline:
            tries += 1
            act = None
            try:
                act = self._activity("videoactivity")
            except Exception as e:
                self._dexc("fs act", e)
            if act is None:
                _t.sleep(0.3)
                continue
            act_seen = True
            if _t.time() < ready_deadline and not self._fs_ready(act):
                if tries == 1:
                    svc = self._fs_call(act, "service", _NOMETHOD_SENTINEL)
                    pl = self._fs_call(act, "player", _NOMETHOD_SENTINEL)
                    self.log("fs waiting player-ready pkg=%s svc=%r player=%r"
                             % (self._fs_pkg(act),
                                "NONE" if svc is None else
                                ("NOMETHOD" if svc is _NOMETHOD_SENTINEL else "obj"),
                                "NONE" if pl is None else
                                ("NOMETHOD" if pl is _NOMETHOD_SENTINEL else "obj")))
                _t.sleep(0.3)
                continue
            decor = None
            try:
                decor = act.getWindow().getDecorView()
            except Exception:
                decor = None
            if decor is None:
                _t.sleep(0.3)
                continue
            hit = None
            try:
                fid = self._fs_full_id()
                if fid:
                    hit = self._fs_find_by_id(decor, fid)
            except Exception as e:
                self._dexc("fs findid", e)
            if hit is None:

                if not dumped:
                    dumped = True
                    try:
                        vs = self._fs_dump_views(decor)
                        self.log("fs no-button id=0x%x dump=%s"
                                 % (self._fs_full_id(), " | ".join(vs[:40])))
                    except Exception as e:
                        self._dexc("fs dump", e)
                _t.sleep(0.3)
                continue

            isf = self._fs_is_full(act)
            land = self._fs_visible_landscape(act)
            cur = self._fs_orient(act)
            if isf is True:
                self.log("fs already fullscreen (isFullscreen) tries=%d" % tries)
                return True
            if isf is None and land is True:
                self.log("fs already fullscreen (window landscape %s) tries=%d"
                         % (self._fs_win_size(act), tries))
                return True

            verifiable = (isf is not None) or (land is not None)
            before = self._fs_win_size(act)
            ok = self._fs_ui_click(hit)
            if not ok:
                self.log("fs click failed id=%s tries=%d"
                         % (self._fs_full_id(), tries))
                _t.sleep(0.4)
                continue

            _t.sleep(1.3)
            isf2 = self._fs_is_full(act)
            land2 = self._fs_visible_landscape(act)
            after = self._fs_win_size(act)
            vinfo = "-"
            try:
                vinfo = "%s clickable=%s vis=%s %dx%d" % (
                    hit.getClass().getSimpleName(),
                    bool(hit.isClickable()), int(hit.getVisibility()),
                    int(hit.getWidth()), int(hit.getHeight()))
            except Exception:
                pass
            self.log("fs clicked id=%s tries=%d verifiable=%s isFull=%s "
                     "req=%s win=%s->%s land=%s->%s view=%s"
                     % (self._fs_full_id(), tries, verifiable, isf2,
                        cur, before, after, land, land2, vinfo))

            if isf2 is True:
                self.log("fs btn ok id=%s tries=%d isFull=True win=%s->%s"
                         % (self._fs_full_id(), tries, before, after))
                return True
            if isf2 is None and land2 is True:
                self.log("fs btn ok id=%s tries=%d win=%s->%s (landscape)"
                         % (self._fs_full_id(), tries, before, after))
                return True
            if isf2 is None and land2 is None:

                self.log("fs btn ok (state-unknown, single click) id=%s"
                         % self._fs_full_id())
                return True

            self.log("fs retry (verified failed) isFull=%s orient=%s->%s"
                     % (isf2, before, after))
            hit2 = None
            try:
                decor2 = act.getWindow().getDecorView()
                fid2 = self._fs_full_id()
                if fid2:
                    hit2 = self._fs_find_by_id(decor2, fid2)
            except Exception as e:
                self._dexc("fs refind", e)
            if hit2 is not None:
                self._fs_ui_click(hit2)
                _t.sleep(1.1)
                ok2 = self._fs_is_full(act)
                if ok2 is True or (ok2 is None and
                                   self._fs_visible_landscape(act) is True):
                    self.log("fs btn ok on retry id=%s" % self._fs_full_id())
                    return True
            _t.sleep(0.4)

        if not act_seen:
            self.log("fs miss target=%s tries=%d reason=no-activity"
                     % (target, tries))
            return False
        if not target:
            self.log("fs miss tries=%d reason=no-button-and-no-target" % tries)
            return False
        try:
            act = self._activity("videoactivity")
            decor = act.getWindow().getDecorView() if act is not None else None
        except Exception:
            decor = None
        if decor is not None:
            try:
                v = self._fs_find_view(decor, target)
            except Exception as e:
                self._dexc("fs findview", e)
                v = None
            if v is not None:
                if self._fs_ui_click(v):
                    self.log("fs fallback episode click target=%s tries=%d"
                             % (target, tries))
                    return False
        self.log("fs miss target=%s tries=%d reason=no-button-no-episode"
                 % (target, tries))
        return False

    def _fs_dump_views(self, root, depth=0, out=None, limit=400):

        if out is None:
            out = []
        if root is None or depth > 24 or len(out) >= limit:
            return out
        try:
            n = int(root.getChildCount())
        except Exception:
            return out
        for i in range(n):
            ch = None
            try:
                ch = root.getChildAt(i)
            except Exception:
                continue
            if ch is None:
                continue
            try:
                if bool(ch.isClickable()):
                    rid = 0
                    try:
                        rid = int(ch.getId())
                    except Exception:
                        rid = 0
                    cls = ""
                    try:
                        cls = str(ch.getClass().getSimpleName())
                    except Exception:
                        cls = "?"
                    out.append("0x%x %s" % (rid, cls))
                    if len(out) >= limit:
                        return out
            except Exception:
                pass
            self._fs_dump_views(ch, depth + 1, out, limit)
        return out

    def _fs_pkg(self, act):

        try:
            return str(act.getPackageName()) if act is not None else "-"
        except Exception:
            return "-"

    def _fs_call(self, obj, name, default=None):

        if obj is None:
            return default
        try:
            cls = obj.getClass()
            while cls is not None:
                try:
                    m = cls.getDeclaredMethod(name, [])
                except Exception:
                    m = None
                if m is not None:
                    m.setAccessible(True)
                    return m.invoke(obj, [])
                cls = cls.getSuperclass()
            return default
        except Exception:
            return default

    def _fs_ready(self, act):

        svc = self._fs_call(act, "service", _NOMETHOD_SENTINEL)
        if svc is _NOMETHOD_SENTINEL:
            return True
        if svc is None:
            return False
        pl = self._fs_call(act, "player", _NOMETHOD_SENTINEL)
        if pl is _NOMETHOD_SENTINEL:
            return True
        return pl is not None

    def _fs_win_size(self, act):

        try:
            d = act.getWindow().getDecorView()
            return "%dx%d" % (int(d.getWidth()), int(d.getHeight()))
        except Exception:
            return "?"

    def _fs_visible_landscape(self, act):

        if act is None:
            return None
        try:
            decor = act.getWindow().getDecorView()
            w = int(decor.getWidth())
            h = int(decor.getHeight())
        except Exception:
            return None
        if w <= 0 or h <= 0:
            return None
        return w > h

    def _fs_is_full(self, act):

        v = self._fs_call(act, "isFullscreen", _NOMETHOD_SENTINEL)
        if v is _NOMETHOD_SENTINEL:
            return None
        try:
            return bool(v)
        except Exception:
            return None

    def _fs_orient(self, act):

        try:
            if act is None:
                act = self._activity("videoactivity")
            if act is None:
                return None
            return int(act.getRequestedOrientation())
        except Exception:
            return None

    def _fs_ui_click(self, view):

        box = {}

        def _do():
            try:
                view.performClick()
                box["ok"] = True
            except Exception as e:
                box["err"] = e
                self._dexc("fs uiclick", e)

        act = None
        try:
            act = self._activity("videoactivity")
        except Exception as e:
            self._dexc("fs uiact", e)
        if act is None:
            return False
        r = None
        try:
            from java import jclass, dynamic_proxy
            RL = jclass("java.lang.Runnable")

            class _R(dynamic_proxy(RL)):
                def run(self):
                    _do()

            r = _R()
            try:
                globals().setdefault("_FS_REFS", []).append(r)
            except Exception:
                pass
            act.runOnUiThread(r)
        except Exception as e:
            self._dexc("fs uirun", e)

            try:
                from java import jclass
                Looper = jclass("android.os.Looper")
                Handler = jclass("android.os.Handler")
                if r is None:
                    from java import dynamic_proxy
                    RL2 = jclass("java.lang.Runnable")

                    class _R2(dynamic_proxy(RL2)):
                        def run(self):
                            _do()

                    r = _R2()
                    globals().setdefault("_FS_REFS", []).append(r)
                Handler(Looper.getMainLooper()).post(r)
            except Exception as e2:
                self._dexc("fs uirun2", e2)
                return False

        for _ in range(60):
            if "ok" in box or "err" in box:
                break
            time.sleep(0.05)
        if "err" in box:
            self.log("fs uiclick err: %s" % box["err"])
            return False
        return bool(box.get("ok"))

    def _fs_full_id(self):

        act = None
        try:
            act = self._activity("videoactivity")
        except Exception as e:
            self._dexc("fs fullid act", e)
        pkg = ""
        if act is not None:
            try:
                pkg = str(act.getPackageName())
            except Exception:
                pkg = ""
        cache = globals().get("_FS_FULL_ID_CACHE")
        if not isinstance(cache, dict):
            cache = {}
            globals()["_FS_FULL_ID_CACHE"] = cache
        if pkg and pkg in cache:
            return int(cache[pkg])

        if act is not None:
            try:
                res = act.getResources()

                for nm in ("full", "fullscreen"):
                    rid = res.getIdentifier(nm, "id", pkg)
                    if rid:
                        cache[pkg] = int(rid)
                        self.log("fs fullid %s -> 0x%x (%s)" % (pkg, int(rid), nm))
                        return int(rid)
                self.log("fs fullid %s -> not found" % pkg)
            except Exception as e:
                self._dexc("fs fullid", e)

        if pkg == "com.fongmi.android.tv":
            return 0x7f0a016b
        return 0

    def _fs_after_play(self, name):
        self.log("fs enter name=%r" % name)

        if not self._fs_on():
            return
        target = str(name or "").strip()
        if not target:
            return
        try:
            import threading as _th

            lk = globals().get("_FS_LOCK")
            if lk is None:
                lk = _th.Lock()
                globals()["_FS_LOCK"] = lk

            def _run():
                with lk:
                    self._fs_click(target)

            _th.Thread(target=_run, name="ktv-fs", daemon=True).start()
        except Exception as e:
            self._dexc("fs thread", e)

    def _fs_card(self):

        on = self._fs_on()
        t = "⛶ 自动全屏"
        rk = ("开 ✅ · 点我关闭" if on else "关 ⛔ · 点我开启")
        bd = ("开：手机点「现在唱」推送进电视播放页后，自动点选集进全屏。\n"
              "关：保持壳默认的窗口模式。\n\n"
              "点这张卡立即切换。")

        return self._note_card("order:fs", t, rk, bd, folder=True)

    def _fs_toggle(self):

        v = "0" if self._fs_on() else "1"
        self._cfg_set({"fullscreen": v})
        self._toast("自动全屏：%s" % ("关 ⛔" if v == "0" else "开 ✅"))

    def _remote_play(self, detail_id, name="", pic="", num=0):

        ctx = self._app_ctx()
        if ctx is None:
            self.log("remote play: no app context")
            return False, "当前环境不支持远程播放"
        key = ""
        try:
            key = self._site_key()
        except Exception as e:
            self._dexc("play skey", e)
        if key and self._intent_video(ctx, key, detail_id, name, pic):
            if num:
                old = int(_RP.get("now") or 0)
                if old and old != int(num):
                    self._queue_mark_done(old)
                _RP["now"] = int(num)
            return True, "已让电视开播：%s" % (name or detail_id)
        if num:
            url = ""
            try:
                url, _sg = self.get_play_url(int(num))
            except Exception as e:
                self._dexc("play geturl", e)
            if url and self._intent_view(ctx, url):
                if num:
                    old = int(_RP.get("now") or 0)
                    if old and old != int(num):
                        self._queue_mark_done(old)
                    _RP["now"] = int(num)
                return True, "已用播放器打开：%s" % (name or "")
        return False, "没能启动播放，请在电视上手动点播"

    def _api_play(self, number, force=False):

        try:
            num = int(number)
        except Exception:
            return False, "歌曲编号不对"
        rows = self.query("SELECT number,name,singer_names FROM song "
                          "WHERE number=? AND status=1", (num,))
        if not rows:
            return False, "曲库里没有这首歌"
        r = rows[0]
        try:
            self._queue_add(num, r["name"], r["singer_names"])
        except Exception:
            pass
        now = 0
        try:
            now = int(_RP.get("now") or 0)
        except Exception:
            now = 0
        if now and int(now) == int(num):
            return True, "《%s》正在唱" % r["name"]
        if now and not force:
            return True, "电视正在唱《%s》，已把《%s》排入待唱" % (
                self._now_name_safe(now), r["name"])
        try:
            pic = self._song_cover(self._song_singers(r["singer_names"]))
        except Exception:
            pic = ""
        ok, why = self._remote_play("s%d" % num, r["name"] or "", pic or "", num)

        if ok:
            self._fs_after_play(r["name"] or "")
        if not ok:
            return True, "已加入待唱清单，到电视上点播即可（《%s》）" % r["name"]
        return True, why or "已让电视开播"

    def _now_name_safe(self, now):

        try:
            for x in self._queue_load():
                if int(x.get("number") or 0) == int(now) and not x.get("done"):
                    return str(x.get("name") or "")
        except Exception:
            pass
        return ""

    def _play_next(self):

        q = [x for x in self._queue_load() if not x.get("done")]
        if not q:
            return False, "待唱队列是空的"
        now = 0
        try:
            now = int(_RP.get("now") or 0)
        except Exception:
            now = 0
        rest = [x for x in q if int(x.get("number") or 0) != now]
        if not rest:
            return False, "待唱队列是空的"
        nxt = rest[0]
        if now:
            self._queue_mark_done(now)
        return self._api_play(int(nxt.get("number") or 0), force=True)

    def _queue_mark_done(self, num):

        try:
            with getattr(self, "_order_lock", threading.Lock()):
                q = self._queue_load()
                hit = False
                for x in q:
                    if int(x.get("number") or 0) == int(num) \
                            and not x.get("done"):
                        x["done"] = 1
                        hit = True
                if hit:
                    self._queue_save(q)
        except Exception:
            pass

    def _order_probe_info(self):

        try:
            import urllib.request
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d/status" % self._order_port(),
                    timeout=1) as r:
                obj = json.loads(r.read().decode("utf-8"))
            if int(obj.get("ok") or 0) == 1:
                if int(obj.get("v") or 0) != ORDER_SVC_VER:
                    self.log("order probe: existing svc v=%s != %d, not adopting"
                             % (obj.get("v"), ORDER_SVC_VER))
                    return None
                return obj
        except Exception:
            pass
        return None

    def _bak_scan(self):

        out, seen = [], set()

        def _pair(p):

            grp = [(p, self._fsize(p), "库备份")]
            base = p
            for suf, why in ((".version", "版本文件"), (".json", "下载状态")):
                if os.path.isfile(base + suf):
                    grp.append((base + suf, self._fsize(base + suf), why))
            return grp

        def _add(p, why):
            if p in seen or not os.path.isfile(p):
                return
            seen.add(p)
            out.append((p, self._fsize(p), why))

        root = os.path.dirname(str(self._cfg_get().get("db") or DB_PATH))
        dirs, dseen = [], set()
        for d in [root, os.path.dirname(self._dl_progress_path() or ""),
                  os.path.dirname(str(self._cfg_get().get("db") or DB_PATH)),
                  os.path.dirname(DB_PATH), os.path.dirname(GULU_DB),
                  LEGACY_DB and os.path.dirname(LEGACY_DB)] + list(self.DB_HINTS):
            d = str(d or "").strip()
            if not d or d in dseen or not os.path.isdir(d):
                continue
            dseen.add(d)
            dirs.append(d)

        for d in dirs:
            try:
                names = os.listdir(d)
            except Exception:
                continue
            for f in names:
                p = os.path.join(d, f)
                low = f.lower()
                if ".db.bak" in low:
                    for q, sz, why in _pair(p):
                        if q == p:
                            _add(q, "旧库备份")
                        else:
                            seen.add(q)
                            out.append((q, sz, why))
                elif low.endswith(".bak-old") or ".version.bak" in low:
                    _add(p, "版本文件备份")
                elif low.endswith(".part"):
                    _add(p, "未完成的下载")
                elif low == DB_PROGRESS_FILE or low.endswith(".part.json"):
                    _add(p, "下载状态文件")
        out.sort(key=lambda x: -x[1])
        return out

    def _fsize(self, p):
        try:
            return int(os.path.getsize(p))
        except Exception:
            return 0

    def _clean_body(self, rows):

        if not rows:
            return "没有找到旧库备份，很干净。"
        lines, total = [], 0
        for p, sz, why in rows:
            total += sz
            lines.append("· %s\n  %s · %s" % (os.path.basename(p), self._human(sz), why))
        return "共 %d 个文件，占 %s：\n\n%s" % (len(rows), self._human(total), "\n".join(lines))

    def _clean_card(self):

        try:
            rows = self._bak_scan()
        except Exception as e:
            return ("🧹 清理旧库备份", "读取失败：%s" % str(e)[:40], "扫描备份目录出错。")
        if not rows:
            return ("🧹 清理旧库备份 ✓", "没有可清理的备份",
                    "每次云端更新曲库前，旧库会备份成 "
                    "song_9c8ec.db.bak-<旧版本号>，便于回退。\n\n"
                    "现在这些目录里没有备份文件，不需要清理。")
        total = sum(r[1] for r in rows)
        return ("🧹 清理旧库备份（%s）" % self._human(total),
                "点我勾选清理（共 %d 个文件）" % len(rows),
                "云端更新曲库后，旧库会留一份 song_9c8ec.db.bak-<版本号>，"
                "发现新库有问题时可以拿它回退。\n\n"
                "一个版本留一份就够，攒多了白占空间（每份约 110MB）。\n\n"
                "点这张卡会列出全部备份，勾选后一次清掉。\n"
                "当前正在用的库不会出现在列表里，删不掉。\n\n"
                + self._clean_body(rows))

    def _clean_action(self):
        rows = self._bak_scan()
        if not rows:
            self._info_dialog("🧹 清理旧库备份", "没有找到旧库备份，很干净。")
            return
        self._clean_dialog(rows)

    def _clean_dialog(self, rows):

        try:
            from java import jclass, dynamic_proxy
            act = self._activity()
            if act is None:
                return False, "未找到窗口上下文"
            Toast = jclass("android.widget.Toast")
            TV = jclass("android.widget.TextView")
            SV = jclass("android.widget.ScrollView")
            LL = jclass("android.widget.LinearLayout")
            LLP = jclass("android.widget.LinearLayout$LayoutParams")
            VCL = jclass("android.view.View$OnClickListener")
            DCL = jclass("android.content.DialogInterface$OnClickListener")
            RL = jclass("java.lang.Runnable")
            Color = jclass("android.graphics.Color")
            try:
                AB = jclass("com.google.android.material.dialog.MaterialAlertDialogBuilder")
            except Exception:
                AB = jclass("android.app.AlertDialog$Builder")

            owner = self
            refs = getattr(self, "_dialog_refs", None)
            if refs is None:
                refs = self._dialog_refs = []
            total = sum(r[1] for r in rows)
            picked = set(range(len(rows)))

            def _label(i, on):
                p, sz, why = rows[i]
                return ("☑  " if on else "☐  ") + os.path.basename(p) + \
                       "\n     %s · %s" % (owner._human(sz), why)

            class Tap(dynamic_proxy(VCL)):
                def __init__(self, i, views, title_holder):
                    super().__init__()
                    self.i = i
                    self.views = views
                    self.t = title_holder

                def onClick(self, v):
                    try:
                        if self.i in picked:
                            picked.discard(self.i)
                            on = False
                        else:
                            picked.add(self.i)
                            on = True
                        tv = self.views[self.i]
                        tv.setText(_label(self.i, on))
                        tv.setTextColor(Color.parseColor("#1B5E20" if on else "#757575"))
                        tv.setBackgroundColor(Color.parseColor(
                            "#E8F5E9" if on else "#FFFFFF"))
                        self.t[0].setText("清理旧库（已选 %d 项 · %s）" % (
                            len(picked), owner._human(sum(rows[k][1] for k in picked))))
                    except Exception:
                        pass

            class DoClean(dynamic_proxy(DCL)):
                def __init__(self):
                    super().__init__()

                def onClick(self, dlg, w):
                    try:
                        dlg.dismiss()
                    except Exception:
                        pass
                    if not picked:
                        owner._toast("没有勾选任何文件")
                        return
                    owner._clean_do([rows[k] for k in sorted(picked)])

            class Show(dynamic_proxy(RL)):
                def run(self):
                    try:
                        box = LL(act)
                        box.setOrientation(1)
                        views = []
                        title_holder = [None]
                        for i, (p, sz, why) in enumerate(rows):
                            tv = TV(act)
                            tv.setText(_label(i, True))
                            tv.setTextSize(14)
                            tv.setTextColor(Color.parseColor("#1B5E20"))
                            tv.setBackgroundColor(Color.parseColor("#E8F5E9"))
                            tv.setPadding(36, 26, 36, 26)
                            tv.setLayoutParams(LLP(-1, -2))
                            tv.setOnClickListener(Tap(i, views, title_holder))
                            box.addView(tv)
                            views.append(tv)
                            refs.append(tv)
                            sep = TV(act)
                            sep.setHeight(1)
                            sep.setBackgroundColor(Color.parseColor("#EEEEEE"))
                            box.addView(sep, LLP(-1, 1))
                            refs.append(sep)

                        sv = SV(act)
                        sv.addView(box, LLP(-1, -2))
                        go = DoClean()
                        b = AB(act)
                        b.setTitle("清理旧库（已选 %d 项 · %s）" % (len(picked),
                                                                owner._human(total)))
                        b.setView(sv)
                        b.setPositiveButton("清理所选", go)
                        b.setNegativeButton("取消", None)
                        dlg = b.show()
                        title_holder[0] = dlg
                        refs.extend([box, sv, go, dlg])
                        del refs[:-60]
                    except Exception as e:
                        try:
                            Toast.makeText(act, "列表打开失败:%s" % str(e)[:60], 1).show()
                        except Exception:
                            pass

            sh = Show()
            refs.append(sh)
            del refs[:-60]
            act.runOnUiThread(sh)
            return True, ""
        except Exception as e:
            return False, "%s: %s" % (type(e).__name__, str(e)[:60])

    def _clean_do(self, picked):

        okn, freen, fail = 0, 0, []
        cur = str(self._cfg_get().get("db") or DB_PATH)
        curbase = os.path.splitext(os.path.basename(cur))[0] if cur else ""
        for p, sz, why in picked:
            try:
                rp = os.path.realpath(p)

                if rp == os.path.realpath(cur):
                    fail.append(os.path.basename(p) + "（正在使用）")
                    continue
                if os.path.basename(rp).startswith(curbase + ".") and \
                        not (".bak" in os.path.basename(rp) or rp.endswith(".part")
                             or ".part" in os.path.basename(rp)):
                    fail.append(os.path.basename(p) + "（像是当前库，跳过）")
                    continue
                os.remove(p)
                okn += 1
                freen += sz
            except Exception as e:
                fail.append("%s（%s）" % (os.path.basename(p), str(e)[:30]))
        msg = "已清理 %d 个文件，释放 %s。" % (okn, self._human(freen))
        if fail:
            msg += "\n\n有 %d 个没删掉：\n%s" % (len(fail), "\n".join(fail[:8]))
        self.log("clean backup: ok=%d free=%d fail=%d" % (okn, freen, len(fail)))
        self._toast("已清理 %d 项，释放 %s" % (okn, self._human(freen)))
        self._info_dialog("🧹 清理完成", msg)

    def _cloud_card(self):

        st = self._dl_state()
        if st and st.get("state") == "held":
            return ("🔄 云端曲库：待确认覆盖",
                    "远端歌数少，已拦下 · 点我确认",
                    "远端版本 (%s) 的曲目比本机少，我已保留当前库。\n\n"
                    "文件已下载并校验完毕，确认要用远端版本的话，"
                    "点这张卡即可直接安装（不用重新下载）。\n\n"
                    "待安装：%s" % (st.get("ver") or "?", st.get("part") or "?"))
        if st:
            have = self._dl_bytes(st)
            size = int(st.get("size") or 0)
            pct = ("%.0f%%" % (have * 100.0 / size)) if size else "?"
            return ("🔄 云端曲库：下载中 %s" % pct,
                    "%s / %s · 再点卡片查看" % (self._human(have), self._human(size)),
                    "正在后台下载。\n\n已完成 %s / %s（%s）\n"
                    "下载可断点续传：中途退出、断网、重启壳，"
                    "再点这张卡都会从已下载的位置接着走。\n\n"
                    "存到：%s" % (self._human(have), self._human(size), pct,
                                 st.get("part") or "?"))
        try:
            cur = str(self._cfg_get().get("db") or DB_PATH)
            n = self._probe_db(cur)
        except Exception:
            cur, n = "", 0
        return ("🔄 云端曲库（在线更新）",
                "点我检查更新（当前 %s 首）" % (n or "?"),
                "从云端拉最新的曲库快照，断点续传 + sha256 校验。\n\n"
                "当前库：%s\n  版本 %s · 共 %s 首\n\n"
                "第一次点：查官方接口看有没有新版本。\n"
                "有更新时下载约 110MB，自动校验，替换前先备份旧库。\n\n"
                "注意：云端不一定比本机新。如果本机歌数更多，"
                "我会先问你要不要覆盖。"
                % (cur or "（未设置）", self._db_version(cur) or "无", n or "?"))

    def _cloud_action(self):

        st = self._dl_state()

        if st and st.get("state") == "held":
            self._cloud_start({"path": st.get("url"), "sha256": st.get("sha256"),
                               "ver": st.get("ver"),
                               "size": int(st.get("size") or 0)})
            return
        if st:
            have = self._dl_bytes(st)
            size = int(st.get("size") or 0)
            pct = ("%.0f%%" % (have * 100.0 / size)) if size else "?"
            self._confirm_dialog(
                "🔄 继续下载",
                "上次下到 %s / %s（%s）\n\n从断点继续？"
                % (self._human(have), self._human(size), pct),
                lambda: self._cloud_start({"path": st["url"],
                                           "sha256": st.get("sha256"),
                                           "size": size}))
            return

        self._toast("正在读取配置…")

        def _run():
            try:
                meta = self._cloud_meta()
            except Exception as e:
                self.log("cloud meta fail: %r" % (e,))
                self._toast("拉配置失败：%s" % str(e)[:60])
                return
            self._cloud_confirm(meta)

        t = threading.Thread(target=_run)
        t.daemon = True
        t.start()

    def _cloud_confirm(self, meta):

        try:
            cur = str(self._cfg_get().get("db") or DB_PATH)
        except Exception:
            cur = ""
        local_n = self._probe_db(cur) or 0 if cur else 0
        lv = self._db_version(cur) if cur else ""
        rv = str(meta.get("ver") or "")
        size = int(meta.get("size") or 0)
        head = ("来源 %s%s\n  版本 %s\n  文件 %s\n  %s\n\n"
                "本机当前\n  %s\n  版本 %s · %s 首\n\n"
                % (meta.get("src") or "?", "接口" if meta.get("src") == "官方" else "",
                   rv or "?", self._human(size),
                   os.path.basename(str(meta.get("path") or "")),
                   cur or "（未设置）", lv or "无", local_n or "?"))
        same = bool(rv and lv and rv == lv and size and
                    os.path.isfile(cur) and os.path.getsize(cur) == size)
        if same:
            self._confirm_dialog(
                "🔄 云端曲库",
                head + "版本号与本机一致。\n\n可以不用下。要强制重下吗？",
                lambda: self._cloud_start(meta))
            return
        self._confirm_dialog(
            "🔄 云端曲库",
            head + "要下载吗？约 %s，支持断点续传；下完做完整性校验，"
                   "若远端歌数比本机少会自动中止，替换前备份旧库。"
                   % (self._human(size) if size else "110MB"),
            lambda: self._cloud_start(meta))

    def _db_update_info(self):

        try:
            cur = str(self._cfg_get().get("db") or DB_PATH)
        except Exception:
            cur = ""
        info = {"cur": cur, "cur_ver": self._db_version(cur),
                "cur_time": self._db_mtime(cur), "cur_cnt": 0,
                "sync": "", "sync_ver": "", "sync_time": "", "sync_cnt": 0,
                "newer": 0, "msg": "", "title": "📦 数据库更新", "remark": "",
                "body": ""}
        try:
            info["cur_cnt"] = self._probe_db(cur) or 0
        except Exception:
            pass

        cands, vers = self._find_gulu_db(cur)
        gulu = [p for p, g in cands.items() if g]
        others = [p for p, g in cands.items() if not g]

        def _mt(p):
            try:
                return os.path.getmtime(p)
            except Exception:
                return 0

        best = ""
        if gulu:
            best = max(gulu, key=_mt)
        elif others:

            best = max(others, key=_mt)
            info["msg"] = "疑似"
        info["sync"] = best
        if best:
            info["sync_ver"] = vers.get(best) or self._db_version(best)
            info["sync_time"] = self._db_mtime(best)
            try:
                info["sync_cnt"] = self._probe_db(best) or 0
            except Exception:
                pass
            try:
                curreal = os.path.realpath(cur) if cur else ""
            except Exception:
                curreal = ""
            if curreal and os.path.realpath(best) == curreal:
                info["sync"] = ""
                best = ""
                info["sync_ver"] = info["sync_time"] = ""
                info["sync_cnt"] = 0

        try:
            curreal = os.path.realpath(cur) if cur else ""
        except Exception:
            curreal = ""
        info["others"] = [p for p in others
                          if os.path.realpath(p) != curreal]
        info["same"] = bool(best) and vers.get(best) == info["cur_ver"]
        if not best:

            try:
                is_g = (os.path.realpath(cur) == os.path.realpath(GULU_DB)
                        or self._looks_gulu(cur or ""))
            except Exception:
                is_g = self._looks_gulu(cur or "")
            info["msg"] = ("当前用的就是 Gulu 同步的那一份（固定路径），"
                           "Gulu 后台更新后会自动跟上"
                           if is_g else
                           "当前库不是 Gulu 的；Gulu 的库在 %s" % GULU_DB)

        ver = info["cur_ver"] or "未知"
        if not best:
            info["newer"] = 0
            info["title"] = "📦 数据库更新"
            info["remark"] = "版本 %s · %s · %s 首" % (
                ver, info["cur_time"] or "?", info["cur_cnt"] or "?")
            lines = ["当前库", "  %s" % (cur or "（未设置）"),
                     "  版本 %s · %s 首" % (ver, info["cur_cnt"] or "?"),
                     "  更新于 %s" % (info["cur_time"] or "?"),
                     "", "结论", "  " + info["msg"]]
            if info["others"]:
                lines += ["", "别的库（不是 Gulu 的）"]
                lines += ["  " + p for p in info["others"][:4]]
            info["body"] = "\n".join(lines)
            return info

        try:
            tc = os.path.getmtime(cur) if os.path.isfile(cur) else 0
        except Exception:
            tc = 0
        tb = _mt(best)
        def _vk(v):
            try:
                return tuple(int(x) for x in str(v).split("."))
            except Exception:
                return ()
        if tb > tc + 1:
            info["newer"] = 1
            info["msg"] = "Gulu 同步库比当前库新"
        elif tb < tc - 1:
            info["newer"] = -1
            info["msg"] = "当前库比 Gulu 同步库新"
        else:
            vc, vb = _vk(info["cur_ver"]), _vk(info["sync_ver"])
            if vb and vc and vb > vc:
                info["newer"] = 1
                info["msg"] = "Gulu 同步库版本更高（%s > %s）" % (
                    info["sync_ver"], info["cur_ver"])
            elif vb and vc and vb < vc:
                info["newer"] = -1
                info["msg"] = "当前库版本更高（%s > %s）" % (
                    info["cur_ver"], info["sync_ver"])
            else:
                info["newer"] = 0
                info["msg"] = "两边版本和时间一致"

        if info["newer"] == 1:
            info["title"] = "📦 数据库更新：有新库"
        elif info["newer"] == -1:
            info["title"] = "📦 数据库更新：当前库更新"
        else:
            info["title"] = "📦 数据库更新：已是最新"
        info["remark"] = "版本 %s · %s · %s 首" % (
            ver, info["cur_time"] or "?", info["cur_cnt"] or "?")
        tag = "" if info["sync_ver"] else "（未标版本）"
        lines = ["当前库", "  %s" % (cur or "（未设置）"),
                 "  版本 %s · %s 首" % (ver, info["cur_cnt"] or "?"),
                 "  更新于 %s" % (info["cur_time"] or "?"),
                 "", "Gulu 同步库" + tag, "  %s" % best,
                 "  版本 %s · %s 首" % (info["sync_ver"] or "未知",
                                       info["sync_cnt"] or "?"),
                 "  更新于 %s" % (info["sync_time"] or "?"),
                 "", "结论", "  " + (info["msg"] or "—")]
        if info["others"]:
            lines += ["", "别的库（不是 Gulu 的）"]
            lines += ["  " + p for p in info["others"][:4]]
        if info["newer"] == 1:
            lines += ["", "点「确定」切换到 Gulu 同步库"]
        info["body"] = "\n".join(lines)
        return info

    def detailContent(self, ids):
        raw = ids[0] if isinstance(ids, (list, tuple)) else ids
        raw = str(raw or "").strip().split("#")[0]

        if raw.startswith("kw:"):
            self.log("detail kw branch raw=%s" % raw)
            if raw == "kw:input":
                self._kw_ask()
                return self._page([self._kw_note("🔍搜索 · 输入关键词")], 1)
            if raw == "kw:clear":
                self._kw_set("")
                return self._page([self._kw_note("🔍搜索 · 已清除")], 1)
            if raw == "kw:count":
                self._kw_stat()
                kw = self._kw_get()
                return self._page([self._kw_note("📊 搜索统计 · %s" % (kw or "-"))], 1)
            return self._page([self._kw_note("🔍搜索")], 1)
        if raw.startswith("set:"):
            self._handle_setting(raw[4:])

            c = self._note_card("set:done", "✓ 设置已处理", "返回上一页查看结果",
                                "设置项已处理。若刚改了路径/端口，重新进设置页看当前值。")
            return {"code": 1, "msg": "详情", "list": [c], "page": 1,
                    "pagecount": 1, "limit": 20, "total": 1}

        if raw.startswith("order:"):
            act = raw[6:]
            if act == "all":
                return self._order_all_detail()
            if act == "list":
                self._queue_show()
                return self._order_detail_page()
            self._order_show()
            return self._order_detail_page()
        if not raw.startswith("s"):
            return {"code": 0, "msg": "无数据", "list": []}
        m = re.match(r'^s(\d+)', raw)
        if not m:
            return {"code": 0, "msg": "无数据", "list": []}
        num = int(m.group(1))
        rows = self.query("SELECT number,name,singer_names,language_id,type_id,temperature,"
                          "edition,mtv_or_vcd FROM song WHERE number=?", (num,))
        if not rows:
            return {"code": 0, "msg": "无数据", "list": []}
        r = rows[0]
        singers = self._song_singers(r["singer_names"])
        pic = self._song_cover(singers)
        lang = LANGS.get(r.get("language_id"), "")
        typ = self._types().get(r.get("type_id"), "")
        vod = {
            "vod_id": "s%d" % num,
            "vod_name": r["name"],
            "vod_pic": pic,
            "type_name": lang,
            "vod_year": "",
            "vod_area": "",
            "vod_lang": lang,
            "vod_remarks": typ or "KTV",
            "vod_actor": r["singer_names"],
            "vod_director": "",
            "vod_content": "原唱：%s\n曲风：%s\n版本：%s\n编号：%d" % (
                r["singer_names"], typ or "流行", r.get("edition") or "DVD", num),
            "vod_play_from": "爱KTV",
            "vod_play_url": self._play_url(r["name"], num),
        }
        return {"code": 1, "msg": "数据列表", "list": [vod],
                "page": 1, "pagecount": 1, "limit": 1, "total": 1}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = max(int(str(pg) or "1"), 1)
        except Exception:
            page = 1
        raw = str(key or "").strip()
        if not raw:
            return {"code": 0, "msg": "无数据", "list": []}
        size = 30
        off = (page - 1) * size

        import re as _re
        words = [w for w in _re.split(u"[\\s,，、|+/]+", raw) if w]
        if not words:
            words = [raw]

        def _esc(w):
            return w.replace("%", "").replace("_", "").replace("'", "''")

        where, args = ["status=1"], []
        for w in words:
            lk = "%" + _esc(w) + "%"
            where.append("(name LIKE ? OR singer_names LIKE ?)")
            args.extend([lk, lk])
        sql = ("SELECT number,name,singer_names,language_id,temperature FROM song "
               "WHERE " + " AND ".join(where) + " ")

        order, args_order = [], []
        if len(words) == 1:
            order.append("CASE WHEN name=? THEN 0 ELSE 1 END")
            args_order.append(words[0])
        else:
            for w in words:
                order.append("CASE WHEN name=? THEN 0 ELSE 1 END")
                args_order.append(w)
        order.append("CASE WHEN temperature IS NULL THEN 1 ELSE 0 END")
        order.append("temperature DESC")
        order.append("number DESC")
        sql += "ORDER BY " + ", ".join(order) + " LIMIT ? OFFSET ?"

        rows = []
        try:
            rows = self.query(sql, tuple(args) + tuple(args_order) + (size, off))
        except Exception as e:
            self.log("search fail: %s" % type(e).__name__)
        _total = self._count_songs(where, args)

        if not rows and len(words) > 1:
            where2, args2 = ["status=1"], []
            ors = []
            for w in words:
                lk = "%" + _esc(w) + "%"
                ors.append("(name LIKE ? OR singer_names LIKE ?)")
                args2.extend([lk, lk])
            where2.append("(" + " OR ".join(ors) + ")")
            try:
                rows = self.query(
                    "SELECT number,name,singer_names,language_id,temperature "
                    "FROM song WHERE " + " AND ".join(where2) + " "
                    "ORDER BY CASE WHEN temperature IS NULL THEN 1 ELSE 0 END, "
                    "temperature DESC, number DESC LIMIT ? OFFSET ?",
                    tuple(args2) + (size, off))
                self.log("search '%s' AND miss -> OR %d" % (raw, len(rows)))
            except Exception:
                rows = []

        self._py_hit = ""
        self._py_names = []

        pure_alpha = bool(re.match(r'^[A-Za-z]+$', raw)) and len(raw) >= 2
        if not rows or pure_alpha:
            prows, ptotal, hnames = self._search_by_pinyin(words, size, off, page)
            if prows:
                if rows and pure_alpha:

                    seen = set()
                    merged = []
                    for r in list(prows) + list(rows):
                        k = r["number"]
                        if k in seen:
                            continue
                        seen.add(k)
                        merged.append(r)
                    rows = merged[:size]
                    _total = max(ptotal, _total)
                    self.log("search '%s' -> pinyin+exact merged %d" % (raw, len(rows)))
                else:
                    rows, _total = prows, ptotal
                if hnames:

                    self._py_hit = hnames[0]
                    self._py_names = list(hnames)
                    self.log("search '%s' -> pinyin %s (%d tiao)"
                             % (raw, "/".join(hnames[:3]), ptotal))
        if not rows:

            _total = 0
        return self._song_page(rows, page, size, "搜索", total=_total)

    def _web_search(self, kw, per=50, p=1):

        raw = str(kw or "").strip()
        words = [w for w in re.split(u"[\\s,，、|+/]+", raw) if w]
        if not words:
            words = [raw]

        def _esc(w):
            return w.replace("%", "").replace("_", "").replace("'", "''")

        where, args = ["status=1"], []
        for w in words:
            lk = "%" + _esc(w) + "%"
            where.append("(name LIKE ? OR singer_names LIKE ?)")
            args.extend([lk, lk])
        off = (p - 1) * per

        order, ea = [], []
        for w in words:
            order.append("CASE WHEN name=? THEN 0 ELSE 1 END")
            ea.append(w)
        order.append("CASE WHEN temperature IS NULL THEN 1 ELSE 0 END")
        order.append("temperature DESC")
        order.append("number DESC")
        sql = ("SELECT number,name,singer_names,language_id,temperature "
               "FROM song WHERE " + " AND ".join(where) + " "
               "ORDER BY " + ", ".join(order) + " LIMIT ? OFFSET ?")
        rows = []
        try:
            rows = self.query(sql, tuple(args) + tuple(ea) + (per, off))
        except Exception as e:
            self.log("web search fail: %s" % type(e).__name__)
        total = self._count_songs(where, args)

        if not rows and len(words) > 1:
            where2, args2 = ["status=1"], []
            ors = []
            for w in words:
                lk = "%" + _esc(w) + "%"
                ors.append("(name LIKE ? OR singer_names LIKE ?)")
                args2.extend([lk, lk])
            sql2 = ("SELECT number,name,singer_names,language_id,temperature "
                    "FROM song WHERE " + " OR ".join(ors) + " "
                    "ORDER BY CASE WHEN temperature IS NULL THEN 1 ELSE 0 END, "
                    "temperature DESC, number DESC LIMIT ? OFFSET ?")
            try:
                rows = self.query(sql2, tuple(args2) + (per, off))
            except Exception:
                rows = []
            total = self._count_songs(where2, args2)
            self.log("web search '%s' AND miss -> OR %d" % (raw, len(rows)))

        pyhit = ""
        pure_alpha = bool(re.match(r'^[A-Za-z]+$', raw)) and len(raw) >= 2
        if not rows or pure_alpha:
            prows, ptotal, hnames = self._search_by_pinyin(words, per, off, p)
            if prows:
                if rows and pure_alpha:

                    seen, merged = set(), []
                    for r in list(prows) + list(rows):
                        k = r["number"]
                        if k in seen:
                            continue
                        seen.add(k)
                        merged.append(r)
                    rows = merged[:per]
                    total = max(ptotal, total)
                else:
                    rows, total = prows, ptotal
                if hnames:
                    pyhit = hnames[0]
                self.log("web search '%s' -> pinyin %s (%d)"
                         % (raw, "/".join(hnames[:2]), len(rows)))
        if not rows:
            total = 0
        return rows, total, pyhit

    def _count_songs(self, where, args):
        try:
            r = self.query("SELECT COUNT(*) AS c FROM song WHERE " + " AND ".join(where), tuple(args))
            return int(r[0]["c"]) if r else 0
        except Exception:
            return 0

    def _pinyin_singers(self, words, limit=24):

        cands = []
        for w in words:
            for ac in to_acronym(w)[:1]:
                if len(ac) >= 2 and ac not in cands:
                    cands.append(ac)
        if not cands:
            return []

        stat = [(0, i, ac) for i, ac in enumerate(cands)]
        stat.sort(key=lambda x: x[1])
        exact, near = [], []
        for _, _i, ac in stat:
            try:
                rs = self.query(
                    "SELECT name,acronym FROM singer WHERE acronym=? LIMIT ?", (ac, limit))
            except Exception:
                rs = []
            for r in rs:
                if r["name"] not in exact:
                    exact.append(r["name"])

        if not exact:
            for _, _i, ac in stat[:2]:
                try:
                    rs = self.query(
                        "SELECT name,acronym FROM singer WHERE acronym LIKE ? LIMIT 8",
                        (ac + "%",))
                except Exception:
                    rs = []
                for r in rs:
                    other = (r["acronym"] or "").upper()

                    if len(other) == len(ac) and r["name"] not in near:
                        near.append(r["name"])
        return (exact + near[:6])[:limit]

    def _search_by_pinyin(self, words, size, off, page):

        names = self._pinyin_singers(words)
        where, wargs = ["status=1"], []
        oargs, order = [], ["CASE WHEN temperature IS NULL THEN 1 ELSE 0 END",
                            "temperature DESC", "number DESC"]

        acs_song = []
        for w in words:
            ww = str(w).strip().upper()
            if re.match(r'^[A-Z]+$', ww) and 1 < len(ww) <= 6 and ww not in acs_song:
                acs_song.append(ww)

        ors_all = []
        if acs_song:
            for ac in acs_song:
                ors_all.append("acronym=?")
                wargs.append(ac)

            order.append("CASE WHEN acronym IN (%s) THEN 0 ELSE 1 END"
                         % ",".join(["'%s'" % ac for ac in acs_song]))
            self.log("pinyin: song.acronym %s" % "/".join(acs_song))

        if names:
            wcase = ["CASE"]
            for idx, nm in enumerate(names):
                pat = "%" + nm.replace("%", "").replace("_", "") + "%"
                ors_all.append("singer_names LIKE ?")
                wargs.append(pat)
                wcase.append("WHEN singer_names LIKE ? THEN %d" % idx)
                oargs.append(pat)
            wcase.append("ELSE 999 END")
            order.append(" ".join(wcase))
        if ors_all:
            where.append("(" + " OR ".join(ors_all) + ")")
        if not acs_song and not names:

            acs = []
            for w in words:
                for ac in to_acronym(w)[:3]:
                    if len(ac) >= 2 and ac not in acs:
                        acs.append(ac)
            if not acs:
                return [], 0, []
            ors = []
            for ac in acs:
                ors.append("acronym LIKE ?")
                wargs.append("%" + ac + "%")
            where.append("(" + " OR ".join(ors) + ")")
        sql = ("SELECT number,name,singer_names,language_id,temperature FROM song "
               "WHERE " + " AND ".join(where) + " "
               "ORDER BY " + ", ".join(order) + " LIMIT ? OFFSET ?")
        try:
            rows = self.query(sql, tuple(wargs) + tuple(oargs) + (size, off))
        except Exception as e:
            self.log("pinyin search fail: %s" % type(e).__name__)
            rows = []
        return rows, self._count_songs(where, wargs), names

    def _play_url(self, name, num):

        return "%s$play%s" % (name, num)

    def playerContent(self, flag, id, vipFlags=None):
        raw = str(id or "")
        m = re.match(r'^play(\d+)$', raw)
        if not m:
            return {"parse": 0, "playUrl": "", "url": "", "header": {}}
        num = int(m.group(1))
        url, err = self.get_play_url(num)

        if not url:
            self._url_cache.pop(num, None)
            self._sig_cache = ("", 0)
            url, err = self.get_play_url(num)
        if not url:
            self.log("播放获取失败: %s" % err)
            return {"parse": 0, "playUrl": "", "url": "", "header": {}}

        self.log("playerContent num=%s -> direct" % m.group(1))
        return {"parse": 0, "playUrl": "", "url": url,
                "header": {"User-Agent": UA}}

    def _fetch_singer_img(self, name, save_path):

        name = str(name or "").strip()
        if not name:
            return None
        try:
            import requests
        except Exception:
            return None

        UA_WEB = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        def _save(b, src):

            r = self._save_img(b, save_path, name, src)
            if r is False:
                self._warm_last_ioerr = True
                return None
            return r

        def _get(url, ref=None, timeout=10):
            h = {"User-Agent": UA_WEB}
            if ref:
                h["Referer"] = ref
            try:
                r = requests.get(url, headers=h, timeout=timeout)
                return r.text if r.status_code == 200 else None
            except Exception:
                return None

        def _img(url, ref=None):

            h = {"User-Agent": UA_WEB}
            if ref:
                h["Referer"] = ref
            try:
                r = requests.get(url, headers=h, timeout=12)
                b = r.content
                if r.status_code != 200 or len(b) < 3000:
                    return None
                if b[:2] == b"\xff\xd8" or b[:8] == b"\x89PNG\r\n\x1a\n":
                    return b
            except Exception:
                pass
            return None

        def _pick(text, pat, group=1):
            m = re.search(pat, text or "", re.S)
            return m.group(group) if m else ""

        t = _get("http://search.kuwo.cn/r.s?all=%s&ft=artist&rn=8&encoding=utf8"
                 "&rformat=json" % _quote(name), ref="http://www.kuwo.cn/")
        if t:
            base = _pick(t, r"'BASEPICPATH':'([^']*)'")

            cand = []
            for blk in re.findall(r"\{'AARTIST'.*?\}", t, re.S)[:10]:
                pp = _pick(blk, r"'PICPATH':'([^']*)'")

                nm = _pick(blk, r"[^A-Z]ARTIST':'([^']*)'")
                if pp and nm:
                    cand.append((_html_unescape(nm).strip(), pp))

            hit = None
            for nm, pp in cand:
                if _name_eq(nm, name):
                    hit = pp
                    break
            if hit and base:
                b = _img(base + hit, ref="http://www.kuwo.cn/")
                if b:
                    return _save(b, "kuwo")

        t = _get("http://mobilecdn.kugou.com/api/v3/search/singer?keyword=%s"
                 "&page=1&pagesize=5" % _quote(name))
        sid = ""
        if t:

            pairs = re.findall(r'\{"singername":"([^"]*)","singerid":(\d+)\}', t)
            for nm, i in pairs:
                if _name_eq(nm, name):
                    sid = i
                    break
        if sid:
            t2 = _get("http://mobilecdn.kugou.com/api/v3/singer/info?singerid=%s" % sid)
            url = _pick(t2, r'"imgurl":"([^"]*)"') if t2 else ""
            if url:
                url = url.replace("{size}", "400")
                b = _img(url, ref="https://www.kugou.com/")
                if b:
                    return _save(b, "kugou")

        t = _get("https://c.y.qq.com/soso/fcgi-bin/client_search_cp?p=1&n=5&w=%s"
                 % _quote(name), ref="https://y.qq.com/")
        mid = ""
        if t:
            pairs = re.findall(r'"mid":"([0-9A-Za-z]{10,})","name":"([^"]*)"', t)
            for m_, nm in pairs:
                if _name_eq(nm, name):
                    mid = m_
                    break
        if mid:
            b = _img("https://y.gtimg.cn/music/photo_new/T001R300x300M000%s.jpg" % mid,
                     ref="https://y.qq.com/")
            if b:
                return _save(b, "qq")

        t = _get("http://music.163.com/api/search/get/web?s=%s&type=100&limit=1"
                 % _quote(name), ref="http://music.163.com/")
        pic = ""
        for blk in re.findall(r'\{[^{}]*"picUrl":"[^"]*"[^{}]*\}', t or "")[:10]:
            an = _pick(blk, r'"name":"([^"]*)"')
            if _name_eq(an, name):
                pic = _pick(blk, r'"picUrl":"([^"]*)"') or ""
                break
        if pic:
            if pic.endswith(".jpg") or "?" not in pic:
                pic += "?param=300y300"
            b = _img(pic, ref="http://music.163.com/")
            if b:
                return _save(b, "163")

        self.log("fetch img: %s 四源均无图" % name)
        return None

    def _save_img(self, blob, save_path, name, src):

        blob = _shrink_img(blob)
        try:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(blob)
        except Exception as e:
            self.log("fetch img: %s 写盘失败 %s" % (name, e))
            return False
        self.log("fetch img: %s OK %dB via %s" % (name, len(blob), src))
        return blob

    def localProxy(self, params):

        params = params or {}
        if str(params.get("type") or "") == "qr":
            try:
                m = qr_matrix(self._order_url(), border=2)
                png = qr_png(m, scale=4)
                return [200, "image/png", png]
            except Exception as e:
                self.log("qr proxy fail: %s" % e)
                return [404, "text/plain", b"qr error"]

        if str(params.get("type") or "") != "singer":
            return [404, "text/plain", b""]
        try:
            name = self.d64(params.get("n") or "")
        except Exception:
            return [404, "text/plain", b""]
        h = hashlib.md5(name.encode("utf-8")).hexdigest()
        try:
            with open(os.path.join(self.img_dir(), h + ".img"), "rb") as f:
                body = f.read()
        except Exception:
            return [404, "text/plain", b""]
        ct = "image/jpeg"
        if body[:8] == b'\x89PNG\r\n\x1a\n':
            ct = "image/png"
        elif body[:3] == b'GIF':
            ct = "image/gif"
        return [200, ct, body]

def _shrink_img(blob, size=300, quality=85):

    try:
        import io as _io
        from PIL import Image as _Img
    except Exception:
        return blob
    try:
        im = _Img.open(_io.BytesIO(blob))
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        if im.size != (size, size):

            w, h = im.size
            d = min(w, h)
            im = im.crop(((w - d) // 2, (h - d) // 2,
                          (w - d) // 2 + d, (h - d) // 2 + d))
            im = im.resize((size, size), _Img.LANCZOS)
        out = _io.BytesIO()
        im.save(out, "JPEG", quality=quality, optimize=True)

        return out.getvalue()
    except Exception:
        return blob

def _html_unescape(t):

    if not t:
        return ""
    try:
        from html import unescape as _u
        return _u(t)
    except Exception:
        return t.replace("&nbsp;", " ").replace("&apos;", "'").replace("&amp;", "&")

def _name_eq(a, b):

    def n(x):
        return "".join(str(x or "").split()).lower()
    x, y = n(a), n(b)
    if not x or not y:
        return False
    if x == y:
        return True
    return y.startswith(x) and len(x) >= 2
