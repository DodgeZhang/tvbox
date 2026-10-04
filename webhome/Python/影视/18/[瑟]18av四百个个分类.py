# -*- coding: utf-8 -*-
import sys
import re
import json
import base64
import threading
import requests
import urllib3
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import unquote, quote

urllib3.disable_warnings()
sys.path.append('..')
from base.spider import Spider

# ===== 纯 Python AES-128 工具（保留原有） =====
_sbox = bytes([
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16])
_inv_sbox = bytes([
    0x52,0x09,0x6a,0xd5,0x30,0x36,0xa5,0x38,0xbf,0x40,0xa3,0x9e,0x81,0xf3,0xd7,0xfb,
    0x7c,0xe3,0x39,0x82,0x9b,0x2f,0xff,0x87,0x34,0x8e,0x43,0x44,0xc4,0xde,0xe9,0xcb,
    0x54,0x7b,0x94,0x32,0xa6,0xc2,0x23,0x3d,0xee,0x4c,0x95,0x0b,0x42,0xfa,0xc3,0x4e,
    0x08,0x2e,0xa1,0x66,0x28,0xd9,0x24,0xb2,0x76,0x5b,0xa2,0x49,0x6d,0x8b,0xd1,0x25,
    0x72,0xf8,0xf6,0x64,0x86,0x68,0x98,0x16,0xd4,0xa4,0x5c,0xcc,0x5d,0x65,0xb6,0x92,
    0x6c,0x70,0x48,0x50,0xfd,0xed,0xb9,0xda,0x5e,0x15,0x46,0x57,0xa7,0x8d,0x9d,0x84,
    0x90,0xd8,0xab,0x00,0x8c,0xbc,0xd3,0x0a,0xf7,0xe4,0x58,0x05,0xb8,0xb3,0x45,0x06,
    0xd0,0x2c,0x1e,0x8f,0xca,0x3f,0x0f,0x02,0xc1,0xaf,0xbd,0x03,0x01,0x13,0x8a,0x6b,
    0x3a,0x91,0x11,0x41,0x4f,0x67,0xdc,0xea,0x97,0xf2,0xcf,0xce,0xf0,0xb4,0xe6,0x73,
    0x96,0xac,0x74,0x22,0xe7,0xad,0x35,0x85,0xe2,0xf9,0x37,0xe8,0x1c,0x75,0xdf,0x6e,
    0x47,0xf1,0x1a,0x71,0x1d,0x29,0xc5,0x89,0x6f,0xb7,0x62,0x0e,0xaa,0x18,0xbe,0x1b,
    0xfc,0x56,0x3e,0x4b,0xc6,0xd2,0x79,0x20,0x9a,0xdb,0xc0,0xfe,0x78,0xcd,0x5a,0xf4,
    0x1f,0xdd,0xa8,0x33,0x88,0x07,0xc7,0x31,0xb1,0x12,0x10,0x59,0x27,0x80,0xec,0x5f,
    0x60,0x51,0x7f,0xa9,0x19,0xb5,0x4a,0x0d,0x2d,0xe5,0x7a,0x9f,0x93,0xc9,0x9c,0xef,
    0xa0,0xe0,0x3b,0x4d,0xae,0x2a,0xf5,0xb0,0xc8,0xeb,0xbb,0x3c,0x83,0x53,0x99,0x61,
    0x17,0x2b,0x04,0x7e,0xba,0x77,0xd6,0x26,0xe1,0x69,0x14,0x63,0x55,0x21,0x0c,0x7d])
_rcon = [0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36]
def _xtime(a):
    return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else (a << 1) & 0xff
def _gf_mul(a, b):
    r = 0
    for _ in range(8):
        if b & 1: r ^= a
        a = _xtime(a)
        b >>= 1
    return r
_mul_e = bytes(_gf_mul(0x0e, i) for i in range(256))
_mul_b = bytes(_gf_mul(0x0b, i) for i in range(256))
_mul_d = bytes(_gf_mul(0x0d, i) for i in range(256))
_mul_9 = bytes(_gf_mul(0x09, i) for i in range(256))
_key_schedules = {}
def _key_schedule(key):
    k = bytes(key)
    if k in _key_schedules: return _key_schedules[k]
    w = []
    for i in range(4):
        w.append([key[4*i], key[4*i+1], key[4*i+2], key[4*i+3]])
    for i in range(4, 44):
        temp = w[i-1][:]
        if i % 4 == 0:
            temp = temp[1:] + temp[:1]
            temp = [_sbox[b] for b in temp]
            temp[0] ^= _rcon[i//4 - 1]
        w.append([w[i-4][j] ^ temp[j] for j in range(4)])
    _key_schedules[k] = w
    return w
def _dec_block(block, w):
    s0,s1,s2,s3,s4,s5,s6,s7,s8,s9,s10,s11,s12,s13,s14,s15 = block
    s0 ^= w[40][0]; s1 ^= w[40][1]; s2 ^= w[40][2]; s3 ^= w[40][3]
    s4 ^= w[41][0]; s5 ^= w[41][1]; s6 ^= w[41][2]; s7 ^= w[41][3]
    s8 ^= w[42][0]; s9 ^= w[42][1]; s10^= w[42][2]; s11^= w[42][3]
    s12^= w[43][0]; s13^= w[43][1]; s14^= w[43][2]; s15^= w[43][3]
    box = _inv_sbox
    for rnd in range(9, 0, -1):
        t0=box[s0]; t1=box[s13]; t2=box[s10]; t3=box[s7]
        t4=box[s4]; t5=box[s1]; t6=box[s14]; t7=box[s11]
        t8=box[s8]; t9=box[s5]; t10=box[s2]; t11=box[s15]
        t12=box[s12]; t13=box[s9]; t14=box[s6]; t15=box[s3]
        rk=w[rnd*4]; t0^=rk[0]; t1^=rk[1]; t2^=rk[2]; t3^=rk[3]
        rk=w[rnd*4+1]; t4^=rk[0]; t5^=rk[1]; t6^=rk[2]; t7^=rk[3]
        rk=w[rnd*4+2]; t8^=rk[0]; t9^=rk[1]; t10^=rk[2]; t11^=rk[3]
        rk=w[rnd*4+3]; t12^=rk[0]; t13^=rk[1]; t14^=rk[2]; t15^=rk[3]
        s0 =_mul_e[t0]^_mul_b[t1]^_mul_d[t2]^_mul_9[t3]
        s1 =_mul_9[t0]^_mul_e[t1]^_mul_b[t2]^_mul_d[t3]
        s2 =_mul_d[t0]^_mul_9[t1]^_mul_e[t2]^_mul_b[t3]
        s3 =_mul_b[t0]^_mul_d[t1]^_mul_9[t2]^_mul_e[t3]
        s4 =_mul_e[t4]^_mul_b[t5]^_mul_d[t6]^_mul_9[t7]
        s5 =_mul_9[t4]^_mul_e[t5]^_mul_b[t6]^_mul_d[t7]
        s6 =_mul_d[t4]^_mul_9[t5]^_mul_e[t6]^_mul_b[t7]
        s7 =_mul_b[t4]^_mul_d[t5]^_mul_9[t6]^_mul_e[t7]
        s8 =_mul_e[t8]^_mul_b[t9]^_mul_d[t10]^_mul_9[t11]
        s9 =_mul_9[t8]^_mul_e[t9]^_mul_b[t10]^_mul_d[t11]
        s10=_mul_d[t8]^_mul_9[t9]^_mul_e[t10]^_mul_b[t11]
        s11=_mul_b[t8]^_mul_d[t9]^_mul_9[t10]^_mul_e[t11]
        s12=_mul_e[t12]^_mul_b[t13]^_mul_d[t14]^_mul_9[t15]
        s13=_mul_9[t12]^_mul_e[t13]^_mul_b[t14]^_mul_d[t15]
        s14=_mul_d[t12]^_mul_9[t13]^_mul_e[t14]^_mul_b[t15]
        s15=_mul_b[t12]^_mul_d[t13]^_mul_9[t14]^_mul_e[t15]
    t0=box[s0]; t1=box[s13]; t2=box[s10]; t3=box[s7]
    t4=box[s4]; t5=box[s1]; t6=box[s14]; t7=box[s11]
    t8=box[s8]; t9=box[s5]; t10=box[s2]; t11=box[s15]
    t12=box[s12]; t13=box[s9]; t14=box[s6]; t15=box[s3]
    rk=w[0]; t0^=rk[0]; t1^=rk[1]; t2^=rk[2]; t3^=rk[3]
    rk=w[1]; t4^=rk[0]; t5^=rk[1]; t6^=rk[2]; t7^=rk[3]
    rk=w[2]; t8^=rk[0]; t9^=rk[1]; t10^=rk[2]; t11^=rk[3]
    rk=w[3]; t12^=rk[0]; t13^=rk[1]; t14^=rk[2]; t15^=rk[3]
    return bytes([t0,t1,t2,t3,t4,t5,t6,t7,t8,t9,t10,t11,t12,t13,t14,t15])
def _aes_cbc_decrypt(data, key, iv):
    if not data or len(data) % 16: return data
    n = len(data) // 16
    w = _key_schedule(key)
    out = bytearray(len(data))
    prev = iv
    for i in range(n):
        block = data[i*16:(i+1)*16]
        dec = _dec_block(block, w)
        for j in range(16):
            out[i*16+j] = dec[j] ^ prev[j]
        prev = block
    pad = out[-1]
    if 1 <= pad <= 16:
        return bytes(out[:-pad])
    return bytes(out)

# ===== 全局代理服务（封面图走代理绕过 SSL） =====
_proxy_port = 0
_proxy_started = False
_proxy_session = requests.Session()
_proxy_session.verify = False
_proxy_headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://mjv011.com/',
}
class _ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
class _ProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            real_url = unquote(self.path[1:])
            if not real_url or not real_url.startswith('http'):
                self.send_response(404); self.end_headers(); return
            r = _proxy_session.get(real_url, headers=_proxy_headers, timeout=20, verify=False)
            ct = r.headers.get('Content-Type', 'image/jpeg')
            self.send_response(200)
            self.send_header('Content-Type', ct)
            self.send_header('Content-Length', len(r.content))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(r.content)
        except BrokenPipeError:
            pass
        except Exception:
            self.send_response(404); self.end_headers()
    def log_message(self, format, *args): pass
def _find_free_port():
    import socket
    sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sk.bind(('127.0.0.1', 0))
    port = sk.getsockname()[1]
    sk.close()
    return port
def _start_proxy():
    global _proxy_port, _proxy_started
    if _proxy_started: return
    _proxy_port = _find_free_port()
    server = _ThreadedHTTPServer(('127.0.0.1', _proxy_port), _ProxyHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _proxy_started = True

# ===== 内容类型判断 =====
def _is_novel(tid_or_vid):
    if not tid_or_vid: return False
    return tid_or_vid.startswith('novel')
def _is_image(tid_or_vid):
    if not tid_or_vid: return False
    return any(tid_or_vid.startswith(p) for p in ['18H', 'doujin', 'cg', 'cwp'])

# ===== 静态中文类别清单（硬编码） =====
_CHINESE_CATEGORIES = [
    {'n': '企畫', 'v': 'chinese_category/1/企畫'},
    {'n': '女同性戀', 'v': 'chinese_category/2/女同性戀'},
    {'n': '獵豔、搭訕', 'v': 'chinese_category/3/獵豔、搭訕'},
    {'n': '野外・露出', 'v': 'chinese_category/4/野外・露出'},
    {'n': '偶像藝人', 'v': 'chinese_category/5/偶像藝人'},
    {'n': '其他戀物癖', 'v': 'chinese_category/6/其他戀物癖'},
    {'n': '近親相姦', 'v': 'chinese_category/7/近親相姦'},
    {'n': '巨乳癖', 'v': 'chinese_category/8/巨乳癖'},
    {'n': '情侶', 'v': 'chinese_category/9/情侶'},
    {'n': '男同性恋', 'v': 'chinese_category/10/男同性恋'},
    {'n': '花癡', 'v': 'chinese_category/11/花癡'},
    {'n': '偷窥', 'v': 'chinese_category/12/偷窥'},
    {'n': '戀腿癖', 'v': 'chinese_category/13/戀腿癖'},
    {'n': '其他', 'v': 'chinese_category/14/其他'},
    {'n': '癡漢', 'v': 'chinese_category/15/癡漢'},
    {'n': '倒追', 'v': 'chinese_category/16/倒追'},
    {'n': '奴隷', 'v': 'chinese_category/17/奴隷'},
    {'n': '跳舞', 'v': 'chinese_category/18/跳舞'},
    {'n': '雙性人', 'v': 'chinese_category/19/雙性人'},
    {'n': '姐妹', 'v': 'chinese_category/20/姐妹'},
    {'n': '通姦', 'v': 'chinese_category/21/通姦'},
    {'n': '鬼畜', 'v': 'chinese_category/22/鬼畜'},
    {'n': '學校作品', 'v': 'chinese_category/23/學校作品'},
    {'n': '惡作劇', 'v': 'chinese_category/24/惡作劇'},
    {'n': '妄想', 'v': 'chinese_category/25/妄想'},
    {'n': '殘忍畫面', 'v': 'chinese_category/26/殘忍畫面'},
    {'n': '爛醉如泥的', 'v': 'chinese_category/27/爛醉如泥的'},
    {'n': '處女', 'v': 'chinese_category/28/處女'},
    {'n': '美容院', 'v': 'chinese_category/29/美容院'},
    {'n': '性感的', 'v': 'chinese_category/30/性感的'},
    {'n': '女同接吻', 'v': 'chinese_category/31/女同接吻'},
    {'n': '運動', 'v': 'chinese_category/32/運動'},
    {'n': '瘙癢', 'v': 'chinese_category/33/瘙癢'},
    {'n': '出軌', 'v': 'chinese_category/34/出軌'},
    {'n': '正太控', 'v': 'chinese_category/35/正太控'},
    {'n': '處男', 'v': 'chinese_category/36/處男'},
    {'n': '蠻橫嬌羞', 'v': 'chinese_category/37/蠻橫嬌羞'},
    {'n': '觸手', 'v': 'chinese_category/38/觸手'},
    {'n': '嘔吐', 'v': 'chinese_category/39/嘔吐'},
    {'n': '拷問', 'v': 'chinese_category/40/拷問'},
    {'n': '10枚組', 'v': 'chinese_category/41/10枚組'},
    {'n': '女優合集', 'v': 'chinese_category/42/女優合集'},
    {'n': '温泉', 'v': 'chinese_category/43/温泉'},
    {'n': 'M男', 'v': 'chinese_category/44/M男'},
    {'n': '原作コラボ', 'v': 'chinese_category/45/原作コラボ'},
    {'n': '16時間以上作品', 'v': 'chinese_category/46/16時間以上作品'},
    {'n': 'デカチン・巨根', 'v': 'chinese_category/47/デカチン・巨根'},
    {'n': 'ファン感謝・訪問', 'v': 'chinese_category/48/ファン感謝・訪問'},
    {'n': '動画', 'v': 'chinese_category/49/動画'},
    {'n': '巨尻', 'v': 'chinese_category/50/巨尻'},
    {'n': 'ハーレム', 'v': 'chinese_category/51/ハーレム'},
    {'n': '日焼け', 'v': 'chinese_category/52/日焼け'},
    {'n': '早漏', 'v': 'chinese_category/53/早漏'},
    {'n': 'キス・接吻', 'v': 'chinese_category/54/キス・接吻'},
    {'n': '汗だく', 'v': 'chinese_category/55/汗だく'},
    {'n': '服務生', 'v': 'chinese_category/56/服務生'},
    {'n': '高中女生', 'v': 'chinese_category/57/高中女生'},
    {'n': '女主播', 'v': 'chinese_category/58/女主播'},
    {'n': '女生', 'v': 'chinese_category/59/女生'},
    {'n': '黑人演員', 'v': 'chinese_category/60/黑人演員'},
    {'n': '痴女', 'v': 'chinese_category/61/痴女'},
    {'n': '護士', 'v': 'chinese_category/62/護士'},
    {'n': '家庭教師', 'v': 'chinese_category/63/家庭教師'},
    {'n': '母親', 'v': 'chinese_category/64/母親'},
    {'n': '女教師', 'v': 'chinese_category/65/女教師'},
    {'n': '展場女孩', 'v': 'chinese_category/66/展場女孩'},
    {'n': '女大學生', 'v': 'chinese_category/67/女大學生'},
    {'n': '賽車女郎', 'v': 'chinese_category/68/賽車女郎'},
    {'n': '妓女', 'v': 'chinese_category/69/妓女'},
    {'n': '各種職業', 'v': 'chinese_category/70/各種職業'},
    {'n': '女醫生', 'v': 'chinese_category/71/女醫生'},
    {'n': '人妻', 'v': 'chinese_category/72/人妻'},
    {'n': '白人', 'v': 'chinese_category/73/白人'},
    {'n': '千金小姐', 'v': 'chinese_category/74/千金小姐'},
    {'n': '寡婦', 'v': 'chinese_category/75/寡婦'},
    {'n': '車掌小姐', 'v': 'chinese_category/76/車掌小姐'},
    {'n': '格鬥家', 'v': 'chinese_category/77/格鬥家'},
    {'n': '姐姐', 'v': 'chinese_category/78/姐姐'},
    {'n': '新娘、嫩妻', 'v': 'chinese_category/79/新娘、嫩妻'},
    {'n': '美少女', 'v': 'chinese_category/80/美少女'},
    {'n': '秘書', 'v': 'chinese_category/81/秘書'},
    {'n': '模特兒', 'v': 'chinese_category/82/模特兒'},
    {'n': '女主人、女老板', 'v': 'chinese_category/83/女主人、女老板'},
    {'n': '明星臉', 'v': 'chinese_category/84/明星臉'},
    {'n': '女檢察官', 'v': 'chinese_category/85/女檢察官'},
    {'n': '格鬥家', 'v': 'chinese_category/86/格鬥家'},
    {'n': '義母', 'v': 'chinese_category/87/義母'},
    {'n': '教練', 'v': 'chinese_category/88/教練'},
    {'n': '伴侶', 'v': 'chinese_category/89/伴侶'},
    {'n': '亞洲女演員', 'v': 'chinese_category/90/亞洲女演員'},
    {'n': '公主', 'v': 'chinese_category/91/公主'},
    {'n': '童年朋友', 'v': 'chinese_category/92/童年朋友'},
    {'n': '黑幫成員', 'v': 'chinese_category/93/黑幫成員'},
    {'n': '角色扮演', 'v': 'chinese_category/94/角色扮演'},
    {'n': '眼鏡', 'v': 'chinese_category/95/眼鏡'},
    {'n': '泳裝', 'v': 'chinese_category/96/泳裝'},
    {'n': '校服', 'v': 'chinese_category/97/校服'},
    {'n': '迷你裙', 'v': 'chinese_category/98/迷你裙'},
    {'n': '女僕', 'v': 'chinese_category/99/女僕'},
    {'n': '旗袍', 'v': 'chinese_category/100/旗袍'},
    {'n': '學校泳裝', 'v': 'chinese_category/101/學校泳裝'},
    {'n': '水手服', 'v': 'chinese_category/102/水手服'},
    {'n': '內衣', 'v': 'chinese_category/103/內衣'},
    {'n': '體育服', 'v': 'chinese_category/104/體育服'},
    {'n': '和服・喪服', 'v': 'chinese_category/105/和服・喪服'},
    {'n': 'OL', 'v': 'chinese_category/106/OL'},
    {'n': '身體意識', 'v': 'chinese_category/107/身體意識'},
    {'n': '連褲襪', 'v': 'chinese_category/108/連褲襪'},
    {'n': '空姐', 'v': 'chinese_category/109/空姐'},
    {'n': '迷你裙警察', 'v': 'chinese_category/110/迷你裙警察'},
    {'n': '裸體圍裙', 'v': 'chinese_category/111/裸體圍裙'},
    {'n': '緊身衣', 'v': 'chinese_category/112/緊身衣'},
    {'n': '制服', 'v': 'chinese_category/113/制服'},
    {'n': '泡泡襪', 'v': 'chinese_category/114/泡泡襪'},
    {'n': '女祭司', 'v': 'chinese_category/115/女祭司'},
    {'n': '貓耳女', 'v': 'chinese_category/116/貓耳女'},
    {'n': '兔女郎', 'v': 'chinese_category/117/兔女郎'},
    {'n': '猥褻穿著', 'v': 'chinese_category/118/猥褻穿著'},
    {'n': '偷看內褲', 'v': 'chinese_category/119/偷看內褲'},
    {'n': '女裝人妖', 'v': 'chinese_category/120/女裝人妖'},
    {'n': '女忍者', 'v': 'chinese_category/121/女忍者'},
    {'n': '娃娃', 'v': 'chinese_category/122/娃娃'},
    {'n': '及膝襪', 'v': 'chinese_category/123/及膝襪'},
    {'n': '女戰士', 'v': 'chinese_category/124/女戰士'},
    {'n': '巨乳', 'v': 'chinese_category/127/巨乳'},
    {'n': '貧乳・微乳', 'v': 'chinese_category/128/貧乳・微乳'},
    {'n': '蘿莉塔', 'v': 'chinese_category/129/蘿莉塔'},
    {'n': '熟女', 'v': 'chinese_category/130/熟女'},
    {'n': '孕婦', 'v': 'chinese_category/131/孕婦'},
    {'n': '苗條', 'v': 'chinese_category/132/苗條'},
    {'n': '胖女人', 'v': 'chinese_category/133/胖女人'},
    {'n': '無毛', 'v': 'chinese_category/134/無毛'},
    {'n': '變性者', 'v': 'chinese_category/135/變性者'},
    {'n': '高', 'v': 'chinese_category/136/高'},
    {'n': '屁股', 'v': 'chinese_category/137/屁股'},
    {'n': '嬌小的', 'v': 'chinese_category/138/嬌小的'},
    {'n': '乳房', 'v': 'chinese_category/139/乳房'},
    {'n': '肌肉', 'v': 'chinese_category/140/肌肉'},
    {'n': '超乳', 'v': 'chinese_category/141/超乳'},
    {'n': '中出', 'v': 'chinese_category/142/中出'},
    {'n': '顏射', 'v': 'chinese_category/143/顏射'},
    {'n': '自慰', 'v': 'chinese_category/144/自慰'},
    {'n': '顏射', 'v': 'chinese_category/145/顏射'},
    {'n': '肛交', 'v': 'chinese_category/146/肛交'},
    {'n': '吞精', 'v': 'chinese_category/147/吞精'},
    {'n': '打手槍', 'v': 'chinese_category/148/打手槍'},
    {'n': '放尿', 'v': 'chinese_category/149/放尿'},
    {'n': '亂交', 'v': 'chinese_category/150/亂交'},
    {'n': '口交', 'v': 'chinese_category/151/口交'},
    {'n': '飲尿', 'v': 'chinese_category/152/飲尿'},
    {'n': '排便', 'v': 'chinese_category/153/排便'},
    {'n': '乳交', 'v': 'chinese_category/154/乳交'},
    {'n': '潮吹', 'v': 'chinese_category/155/潮吹'},
    {'n': '淫語', 'v': 'chinese_category/156/淫語'},
    {'n': '69', 'v': 'chinese_category/157/69'},
    {'n': '深喉', 'v': 'chinese_category/158/深喉'},
    {'n': '拳交', 'v': 'chinese_category/159/拳交'},
    {'n': '舔陰', 'v': 'chinese_category/160/舔陰'},
    {'n': '騎乗位', 'v': 'chinese_category/161/騎乗位'},
    {'n': '按摩', 'v': 'chinese_category/162/按摩'},
    {'n': '手指插入', 'v': 'chinese_category/163/手指插入'},
    {'n': '母乳', 'v': 'chinese_category/164/母乳'},
    {'n': '足交', 'v': 'chinese_category/165/足交'},
    {'n': '食糞', 'v': 'chinese_category/166/食糞'},
    {'n': '顏面騎乘', 'v': 'chinese_category/167/顏面騎乘'},
    {'n': '肛内中出', 'v': 'chinese_category/168/肛内中出'},
    {'n': '多P', 'v': 'chinese_category/169/多P'},
    {'n': '按摩棒', 'v': 'chinese_category/170/按摩棒'},
    {'n': '緊縛', 'v': 'chinese_category/171/緊縛'},
    {'n': '跳蛋', 'v': 'chinese_category/172/跳蛋'},
    {'n': '玩具', 'v': 'chinese_category/173/玩具'},
    {'n': '糞便', 'v': 'chinese_category/174/糞便'},
    {'n': 'SM', 'v': 'chinese_category/175/SM'},
    {'n': '車震', 'v': 'chinese_category/176/車震'},
    {'n': '藥物', 'v': 'chinese_category/177/藥物'},
    {'n': '強姦', 'v': 'chinese_category/178/強姦'},
    {'n': '緊縛', 'v': 'chinese_category/179/緊縛'},
    {'n': '監禁', 'v': 'chinese_category/180/監禁'},
    {'n': '灌腸', 'v': 'chinese_category/181/灌腸'},
    {'n': '鴨嘴', 'v': 'chinese_category/182/鴨嘴'},
    {'n': '插入異物', 'v': 'chinese_category/183/插入異物'},
    {'n': '輪姦', 'v': 'chinese_category/184/輪姦'},
    {'n': '拘束', 'v': 'chinese_category/185/拘束'},
    {'n': '凌辱', 'v': 'chinese_category/186/凌辱'},
    {'n': '羞恥', 'v': 'chinese_category/187/羞恥'},
    {'n': '乳液', 'v': 'chinese_category/188/乳液'},
    {'n': '催眠', 'v': 'chinese_category/189/催眠'},
    {'n': '子宮頸', 'v': 'chinese_category/190/子宮頸'},
    {'n': '女優按摩棒', 'v': 'chinese_category/191/女優按摩棒'},
    {'n': '立即口交', 'v': 'chinese_category/192/立即口交'},
    {'n': '合集', 'v': 'chinese_category/193/合集'},
    {'n': '單體作品', 'v': 'chinese_category/194/單體作品'},
    {'n': 'DMM獨家', 'v': 'chinese_category/195/DMM獨家'},
    {'n': '獨立製作', 'v': 'chinese_category/196/獨立製作'},
    {'n': '局部特寫', 'v': 'chinese_category/197/局部特寫'},
    {'n': '素人', 'v': 'chinese_category/198/素人'},
    {'n': '第一人稱攝影', 'v': 'chinese_category/199/第一人稱攝影'},
    {'n': '國外進口', 'v': 'chinese_category/200/國外進口'},
    {'n': '纪录片', 'v': 'chinese_category/201/纪录片'},
    {'n': '投稿', 'v': 'chinese_category/202/投稿'},
    {'n': '數位馬賽克', 'v': 'chinese_category/203/數位馬賽克'},
    {'n': '首次亮相', 'v': 'chinese_category/204/首次亮相'},
    {'n': '經典', 'v': 'chinese_category/205/經典'},
    {'n': '薄馬賽克', 'v': 'chinese_category/206/薄馬賽克'},
    {'n': '4小時以上作品', 'v': 'chinese_category/207/4小時以上作品'},
    {'n': '介紹影片', 'v': 'chinese_category/208/介紹影片'},
    {'n': '主觀視角', 'v': 'chinese_category/209/主觀視角'},
    {'n': '高畫質', 'v': 'chinese_category/210/高畫質'},
    {'n': '戀愛', 'v': 'chinese_category/211/戀愛'},
    {'n': '戲劇', 'v': 'chinese_category/212/戲劇'},
    {'n': '複刻版', 'v': 'chinese_category/213/複刻版'},
    {'n': '限時降價', 'v': 'chinese_category/214/限時降價'},
    {'n': '故事集', 'v': 'chinese_category/215/故事集'},
    {'n': '特效', 'v': 'chinese_category/216/特效'},
    {'n': '3D', 'v': 'chinese_category/217/3D'},
    {'n': 'R-18', 'v': 'chinese_category/219/R-18'},
    {'n': 'R-15', 'v': 'chinese_category/220/R-15'},
    {'n': 'DMM專屬', 'v': 'chinese_category/221/DMM專屬'},
    {'n': '教學', 'v': 'chinese_category/222/教學'},
    {'n': '給女性觀眾', 'v': 'chinese_category/223/給女性觀眾'},
    {'n': '恐怖', 'v': 'chinese_category/224/恐怖'},
    {'n': '合作作品', 'v': 'chinese_category/225/合作作品'},
    {'n': 'パラダイスTV', 'v': 'chinese_category/226/パラダイスTV'},
    {'n': 'DVDトースター', 'v': 'chinese_category/227/DVDトースター'},
    {'n': '魔法少女', 'v': 'chinese_category/228/魔法少女'},
    {'n': '假陽具', 'v': 'chinese_category/229/假陽具'},
    {'n': '順豐', 'v': 'chinese_category/230/順豐'},
    {'n': '圖片視頻（男）', 'v': 'chinese_category/231/圖片視頻（男）'},
    {'n': 'AV OPEN 2014 中量級', 'v': 'chinese_category/232/AV OPEN 2014 中量級'},
    {'n': 'AV OPEN 2014 超重量級', 'v': 'chinese_category/233/AV OPEN 2014 超重量級'},
    {'n': '遊戲實況', 'v': 'chinese_category/234/遊戲實況'},
    {'n': 'AV OPEN 2014 ヘビー級', 'v': 'chinese_category/235/AV OPEN 2014 ヘビー級'},
    {'n': '變身女主角', 'v': 'chinese_category/236/變身女主角'},
    {'n': 'AV OPEN 2015 SM/ハード部門', 'v': 'chinese_category/237/AV OPEN 2015 SM/ハード部門'},
    {'n': 'AV OPEN 2015 企画部門', 'v': 'chinese_category/238/AV OPEN 2015 企画部門'},
    {'n': 'AV OPEN 2015 女優部門', 'v': 'chinese_category/239/AV OPEN 2015 女優部門'},
    {'n': 'AV OPEN 2015 素人部門', 'v': 'chinese_category/240/AV OPEN 2015 素人部門'},
    {'n': 'AV OPEN 2015 乙女部門', 'v': 'chinese_category/241/AV OPEN 2015 乙女部門'},
    {'n': 'AV OPEN 2015 熟女部門', 'v': 'chinese_category/242/AV OPEN 2015 熟女部門'},
    {'n': 'AV OPEN 2015 瘋狂/戀物癖部', 'v': 'chinese_category/243/AV OPEN 2015 瘋狂/戀物癖部'},
    {'n': '推薦用於智能手機的垂直視頻', 'v': 'chinese_category/244/推薦用於智能手機的垂直視頻'},
    {'n': 'V影院', 'v': 'chinese_category/245/V影院'},
    {'n': '動畫', 'v': 'chinese_category/246/動畫'},
    {'n': '行動', 'v': 'chinese_category/247/行動'},
    {'n': '黑暗系統', 'v': 'chinese_category/248/黑暗系統'},
    {'n': '迷你係列', 'v': 'chinese_category/249/迷你係列'},
    {'n': '嬌小的', 'v': 'chinese_category/250/嬌小的'},
    {'n': '浸漬', 'v': 'chinese_category/251/浸漬'},
    {'n': 'AV OPEN 2016 女優部門', 'v': 'chinese_category/252/AV OPEN 2016 女優部門'},
    {'n': 'AV OPEN 2016 素人部門', 'v': 'chinese_category/253/AV OPEN 2016 素人部門'},
    {'n': 'AV OPEN 2016 バラエティ部門', 'v': 'chinese_category/254/AV OPEN 2016 バラエティ部門'},
    {'n': 'AV OPEN 2016 劇情/紀錄片部門', 'v': 'chinese_category/255/AV OPEN 2016 劇情/紀錄片部門'},
    {'n': 'AV OPEN 2016 ハード部門', 'v': 'chinese_category/256/AV OPEN 2016 ハード部門'},
    {'n': 'AV OPEN 2016 瘋狂/戀物癖部門', 'v': 'chinese_category/257/AV OPEN 2016 瘋狂/戀物癖部門'},
    {'n': 'AV OPEN 2016 乙女部門', 'v': 'chinese_category/258/AV OPEN 2016 乙女部門'},
    {'n': 'AV OPEN 2016 企画部門', 'v': 'chinese_category/259/AV OPEN 2016 企画部門'},
    {'n': 'AV OPEN 2016 人妻・熟女部門', 'v': 'chinese_category/260/AV OPEN 2016 人妻・熟女部門'},
    {'n': '婊子', 'v': 'chinese_category/261/婊子'},
    {'n': '僅限虛擬現實', 'v': 'chinese_category/262/僅限虛擬現實'},
    {'n': 'AV 棒球福利', 'v': 'chinese_category/263/AV 棒球福利'},
    {'n': '時間停止', 'v': 'chinese_category/264/時間停止'},
    {'n': '漫畫雜誌', 'v': 'chinese_category/265/漫畫雜誌'},
    {'n': '搞笑喜劇', 'v': 'chinese_category/266/搞笑喜劇'},
    {'n': '男子的愛', 'v': 'chinese_category/267/男子的愛'},
    {'n': '幻想', 'v': 'chinese_category/268/幻想'},
    {'n': 'AV OPEN 2017 女優部門', 'v': 'chinese_category/269/AV OPEN 2017 女優部門'},
    {'n': 'AV OPEN 2017紀錄片部', 'v': 'chinese_category/270/AV OPEN 2017紀錄片部'},
    {'n': 'AV OPEN 2017 フェチ部門', 'v': 'chinese_category/271/AV OPEN 2017 フェチ部門'},
    {'n': 'AV OPEN 2017 乙女部門', 'v': 'chinese_category/272/AV OPEN 2017 乙女部門'},
    {'n': 'AV OPEN 2017 人妻・熟女部門', 'v': 'chinese_category/273/AV OPEN 2017 人妻・熟女部門'},
    {'n': 'AV OPEN 2017 マニア部門', 'v': 'chinese_category/274/AV OPEN 2017 マニア部門'},
    {'n': 'AV OPEN 2017 企画部門', 'v': 'chinese_category/275/AV OPEN 2017 企画部門'},
    {'n': 'AV OPEN 2017 ハード部門', 'v': 'chinese_category/276/AV OPEN 2017 ハード部門'},
    {'n': 'AV OPEN 2017 素人部門', 'v': 'chinese_category/277/AV OPEN 2017 素人部門'},
    {'n': 'AV OPEN 2017 ドラマ部門', 'v': 'chinese_category/278/AV OPEN 2017 ドラマ部門'},
    {'n': '經歷的告白', 'v': 'chinese_category/279/經歷的告白'},
    {'n': '變性/女性化', 'v': 'chinese_category/280/變性/女性化'},
    {'n': '集產品', 'v': 'chinese_category/281/集產品'},
    {'n': '反向強姦', 'v': 'chinese_category/282/反向強姦'},
    {'n': '反向強姦', 'v': 'chinese_category/283/反向強姦'},
    {'n': '名人朋友【特典C】合格作品', 'v': 'chinese_category/284/名人朋友【特典C】合格作品'},
    {'n': '名人朋友【特典A】合格作品', 'v': 'chinese_category/285/名人朋友【特典A】合格作品'},
    {'n': '愛情喜劇', 'v': 'chinese_category/286/愛情喜劇'},
    {'n': '僅限 FANZA 發行', 'v': 'chinese_category/287/僅限 FANZA 發行'},
    {'n': '有資格參加名人朋友活動的作品', 'v': 'chinese_category/288/有資格參加名人朋友活動的作品'},
    {'n': '愛欲', 'v': 'chinese_category/289/愛欲'},
    {'n': '高品質虛擬現實', 'v': 'chinese_category/290/高品質虛擬現實'},
    {'n': '同性戀', 'v': 'chinese_category/291/同性戀'},
    {'n': 'AV OPEN 2018 女優部門', 'v': 'chinese_category/292/AV OPEN 2018 女優部門'},
    {'n': 'AV OPEN 2018 企画部門', 'v': 'chinese_category/293/AV OPEN 2018 企画部門'},
    {'n': 'AV OPEN 2018 素人部門', 'v': 'chinese_category/294/AV OPEN 2018 素人部門'},
    {'n': 'AV OPEN 2018 瘋狂/戀物癖部門', 'v': 'chinese_category/295/AV OPEN 2018 瘋狂/戀物癖部門'},
    {'n': 'AV OPEN 2018 人妻・熟女部門', 'v': 'chinese_category/296/AV OPEN 2018 人妻・熟女部門'},
    {'n': 'AV OPEN 2018 ハード部門', 'v': 'chinese_category/297/AV OPEN 2018 ハード部門'},
    {'n': 'AV OPEN 2018 乙女部門', 'v': 'chinese_category/298/AV OPEN 2018 乙女部門'},
    {'n': '已婚婦女/家庭主婦', 'v': 'chinese_category/299/已婚婦女/家庭主婦'},
    {'n': '連褲襪', 'v': 'chinese_category/300/連褲襪'},
    {'n': '按摩/茶點', 'v': 'chinese_category/301/按摩/茶點'},
    {'n': '乳液油', 'v': 'chinese_category/302/乳液油'},
    {'n': '年輕的妻子', 'v': 'chinese_category/303/年輕的妻子'},
    {'n': '小便/洩漏', 'v': 'chinese_category/304/小便/洩漏'},
    {'n': '保健皂', 'v': 'chinese_category/305/保健皂'},
    {'n': '極致高潮', 'v': 'chinese_category/306/極致高潮'},
    {'n': '虐待', 'v': 'chinese_category/307/虐待'},
    {'n': 'M女', 'v': 'chinese_category/308/M女'},
    {'n': '職業裝', 'v': 'chinese_category/309/職業裝'},
    {'n': '背部', 'v': 'chinese_category/310/背部'},
    {'n': '不戴胸罩', 'v': 'chinese_category/311/不戴胸罩'},
    {'n': '女上司', 'v': 'chinese_category/312/女上司'},
    {'n': '洗澡', 'v': 'chinese_category/313/洗澡'},
    {'n': '乳頭滑落', 'v': 'chinese_category/314/乳頭滑落'},
    {'n': '旅行', 'v': 'chinese_category/315/旅行'},
    {'n': '奧納薩波', 'v': 'chinese_category/316/奧納薩波'},
    {'n': '蠟燭', 'v': 'chinese_category/317/蠟燭'},
    {'n': '男人噴', 'v': 'chinese_category/318/男人噴'},
    {'n': '娘・養女', 'v': 'chinese_category/319/娘・養女'},
    {'n': '面具，面具', 'v': 'chinese_category/320/面具，面具'},
    {'n': '軟體', 'v': 'chinese_category/321/軟體'},
    {'n': '面試', 'v': 'chinese_category/322/面試'},
    {'n': '宅男', 'v': 'chinese_category/323/宅男'},
    {'n': '接待員', 'v': 'chinese_category/324/接待員'},
    {'n': '沒有內褲', 'v': 'chinese_category/325/沒有內褲'},
    {'n': '酒會', 'v': 'chinese_category/326/酒會'},
    {'n': '部下・同僚', 'v': 'chinese_category/327/部下・同僚'},
    {'n': '名人', 'v': 'chinese_category/328/名人'},
    {'n': '戴綠帽子 / 戴綠帽子 / NTR', 'v': 'chinese_category/329/戴綠帽子 / 戴綠帽子 / NTR'},
    {'n': '戴綠帽子 / 戴綠帽子 / NTR', 'v': 'chinese_category/330/戴綠帽子 / 戴綠帽子 / NTR'},
    {'n': '約會', 'v': 'chinese_category/331/約會'},
    {'n': '花嫁', 'v': 'chinese_category/332/花嫁'},
    {'n': '交換/情侶交換', 'v': 'chinese_category/333/交換/情侶交換'},
    {'n': '祖父', 'v': 'chinese_category/334/祖父'},
    {'n': '姨', 'v': 'chinese_category/335/姨'},
    {'n': '鼻鉤', 'v': 'chinese_category/336/鼻鉤'},
    {'n': '運動員', 'v': 'chinese_category/337/運動員'},
    {'n': '醫院/診所', 'v': 'chinese_category/338/醫院/診所'},
    {'n': '打屁股', 'v': 'chinese_category/339/打屁股'},
    {'n': '酒店', 'v': 'chinese_category/340/酒店'},
    {'n': '女王', 'v': 'chinese_category/341/女王'},
    {'n': '瑜伽', 'v': 'chinese_category/342/瑜伽'},
    {'n': '新人陸續登場', 'v': 'chinese_category/343/新人陸續登場'},
    {'n': '白目・失神', 'v': 'chinese_category/344/白目・失神'},
    {'n': '媽媽朋友', 'v': 'chinese_category/345/媽媽朋友'},
    {'n': '啦啦隊長', 'v': 'chinese_category/346/啦啦隊長'},
    {'n': '奶奶', 'v': 'chinese_category/347/奶奶'},
    {'n': '社團活動經理', 'v': 'chinese_category/348/社團活動經理'},
    {'n': '妄想族', 'v': 'chinese_category/349/妄想族'},
    {'n': '艾曼紐', 'v': 'chinese_category/350/艾曼紐'},
    {'n': '艾曼紐', 'v': 'chinese_category/351/艾曼紐'},
    {'n': '放置', 'v': 'chinese_category/352/放置'},
    {'n': '心理驚悚片', 'v': 'chinese_category/353/心理驚悚片'},
    {'n': '切卡', 'v': 'chinese_category/354/切卡'},
    {'n': '福袋', 'v': 'chinese_category/355/福袋'},
    {'n': '最好的，綜合性的', 'v': 'chinese_category/356/最好的，綜合性的'},
    {'n': '3P、4P', 'v': 'chinese_category/357/3P、4P'},
    {'n': '女優', 'v': 'chinese_category/358/女優'},
    {'n': '藝人', 'v': 'chinese_category/359/藝人'},
    {'n': '強姦', 'v': 'chinese_category/360/強姦'},
    {'n': '湯', 'v': 'chinese_category/361/湯'},
    {'n': '凌辱', 'v': 'chinese_category/362/凌辱'},
    {'n': '偶像', 'v': 'chinese_category/363/偶像'},
    {'n': '看護師', 'v': 'chinese_category/364/看護師'},
    {'n': '奴隸', 'v': 'chinese_category/365/奴隸'},
    {'n': '風俗', 'v': 'chinese_category/366/風俗'},
    {'n': '處女之物', 'v': 'chinese_category/367/處女之物'},
    {'n': '小乳房', 'v': 'chinese_category/368/小乳房'},
    {'n': '大公雞', 'v': 'chinese_category/369/大公雞'},
    {'n': '妹', 'v': 'chinese_category/370/妹'},
    {'n': '戀物癖', 'v': 'chinese_category/371/戀物癖'},
    {'n': '示例視頻', 'v': 'chinese_category/372/示例視頻'},
    {'n': '秋季大甩賣', 'v': 'chinese_category/373/秋季大甩賣'},
    {'n': '藍光', 'v': 'chinese_category/374/藍光'},
    {'n': '出口', 'v': 'chinese_category/375/出口'},
    {'n': '動漫人物', 'v': 'chinese_category/376/動漫人物'},
    {'n': 'DOD 秋季促銷第 2 部分', 'v': 'chinese_category/377/DOD 秋季促銷第 2 部分'},
    {'n': '2010年代前半（DOD）', 'v': 'chinese_category/378/2010年代前半（DOD）'},
    {'n': '光盤點播銷售', 'v': 'chinese_category/379/光盤點播銷售'},
    {'n': 'AV女優', 'v': 'chinese_category/380/AV女優'},
    {'n': '設置有好處的產品', 'v': 'chinese_category/381/設置有好處的產品'},
    {'n': 'Triple HAPPY 活動', 'v': 'chinese_category/382/Triple HAPPY 活動'},
    {'n': 'Rena 桃園 JOKER 禮品活動', 'v': 'chinese_category/383/Rena 桃園 JOKER 禮品活動'},
    {'n': '時代劇', 'v': 'chinese_category/384/時代劇'},
    {'n': '全球媒體 40% 折扣銷售', 'v': 'chinese_category/385/全球媒體 40% 折扣銷售'},
    {'n': 'Mousozoku 2021上半年進入TOP 100', 'v': 'chinese_category/386/Mousozoku 2021上半年進入TOP 100'},
    {'n': 'レズビアン', 'v': 'chinese_category/387/レズビアン'},
    {'n': 'BL（ボーイズラブ）', 'v': 'chinese_category/388/BL（ボーイズラブ）'},
    {'n': '8KVR', 'v': 'chinese_category/389/8KVR'},
    {'n': '妄想族30％OFF第1弾', 'v': 'chinese_category/390/妄想族30％OFF第1弾'},
    {'n': 'ブランドストア30％OFF☆', 'v': 'chinese_category/391/ブランドストア30％OFF☆'},
    {'n': 'ながえスタイル30％OFF', 'v': 'chinese_category/392/ながえスタイル30％OFF'},
    {'n': 'MERCURY（マーキュリー）他30％OFF', 'v': 'chinese_category/393/MERCURY（マーキュリー）他30％OFF'},
    {'n': 'ブランドストア30％OFF！', 'v': 'chinese_category/394/ブランドストア30％OFF！'},
    {'n': '妄想族30％OFF', 'v': 'chinese_category/395/妄想族30％OFF'},
    {'n': 'BALTAN＜バルタン＞他30％OFF', 'v': 'chinese_category/396/BALTAN＜バルタン＞他30％OFF'},
    {'n': 'ながえスタイル他30％OFF', 'v': 'chinese_category/397/ながえスタイル他30％OFF'},
    {'n': '台湾モデル', 'v': 'chinese_category/398/台湾モデル'},
    {'n': 'AI生成作品', 'v': 'chinese_category/399/AI生成作品'},
    {'n': 'アナルセックス（男の娘）', 'v': 'chinese_category/400/アナルセックス（男の娘）'},
]

# ===== Spider =====
class Spider(Spider):
    session = requests.Session()
    host = 'https://mjv011.com'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://mjv011.com/',
    }

    _tag_cache = {}

    def getName(self): return "mjv011"
    def isVideoFormat(self, url):
        if not url: return False
        return '.m3u8' in url or '.mp4' in url or '.ts' in url
    def manualVideoCheck(self): return False
    def destroy(self): pass

    def localProxy(self, param):
        return [404, 'text/plain', '']

    def init(self, extend=""):
        self.session.verify = False
        _start_proxy()
        try:
            self.session.get(
                f'{self.host}/zh/chinese_IamOverEighteenYearsOld/19/index.html',
                headers=self.headers, timeout=15, verify=False)
        except Exception:
            pass

    def _proxy_url(self, url):
        if not url: return ''
        if url.startswith('http://127.0.0.1'):
            return url
        return f'http://127.0.0.1:{_proxy_port}/{quote(url, safe="")}'

    def _fetch(self, url):
        try:
            r = self.session.get(url, headers=self.headers, timeout=20, verify=False)
            r.encoding = 'utf-8'
            if r.status_code == 200:
                text = r.text
                if len(text) < 3000 and ('同意(enter)' in text or 'IamOverEighteenYearsOld' in text):
                    self.session.get(
                        f'{self.host}/zh/chinese_IamOverEighteenYearsOld/19/index.html',
                        headers=self.headers, timeout=20, verify=False)
                    r = self.session.get(url, headers=self.headers, timeout=20, verify=False)
                    r.encoding = 'utf-8'
                    if r.status_code == 200:
                        return r.text
                    return ''
                return text
            return ''
        except Exception:
            return ''

    def _parse_posts(self, text, tid=''):
        if _is_novel(tid):
            return self._parse_text_posts(text)

        items = []
        pattern1 = r"<div class='post'>\s*<a[^>]*href=\"([^\"]+)\"[^>]*><img[^>]*src='([^']+)'[^>]*>\s*</a>\s*<div class='con'>\s*<h3[^>]*><a[^>]*>([^<]+)</a></h3>(?:\s*<div class='meta'>([^<]*)</div>)?"
        matches = re.findall(pattern1, text, re.S)
        if matches:
            for href, pic, title, date in matches:
                if href.startswith(self.host):
                    href = href[len(self.host):]
                if not href or not href.startswith('/'):
                    continue
                mm = re.search(r'/([^/]+)_content/(\d+)/([^/]+)\.html', href)
                if not mm:
                    continue
                ctype, vid, slug = mm.group(1), mm.group(2), mm.group(3)
                items.append({
                    'vod_id': f'{ctype}#{vid}#{slug}',
                    'vod_name': title.strip(),
                    'vod_pic': self._proxy_url(pic),
                    'vod_remarks': date.strip() if date else '',
                })
            return items

        pattern2 = r'<a[^>]+href="([^"]*zh/[^"]*_content/[^"]*)"[^>]*>.*?<img[^>]+src="([^"]+)"[^>]*>.*?<(?:h3|h2|h4|div\s+class="title")[^>]*>(.*?)</'
        matches = re.findall(pattern2, text, re.S | re.I)
        for href, pic, title in matches:
            if href.startswith(self.host):
                href = href[len(self.host):]
            if not href or not href.startswith('/'):
                continue
            mm = re.search(r'/([^/]+)_content/(\d+)/([^/]+)\.html', href)
            if not mm:
                continue
            ctype, vid, slug = mm.group(1), mm.group(2), mm.group(3)
            title = re.sub(r'<[^>]+>', '', title).strip()
            items.append({
                'vod_id': f'{ctype}#{vid}#{slug}',
                'vod_name': title,
                'vod_pic': self._proxy_url(pic),
                'vod_remarks': '',
            })
        return items

    def _parse_text_posts(self, text):
        items = []
        for m in re.finditer(r"<div class='post'>\s*<div class='con'>\s*<h3[^>]*><a[^>]*href=\"([^\"]+)\"[^>]*>([^<]+)</a></h3>", text):
            href, title = m.groups()
            mm = re.search(r'/([^/]+)_content/(\d+)/([^/]+)\.html', href)
            if not mm: continue
            ctype, vid, slug = mm.group(1), mm.group(2), mm.group(3)
            items.append({
                'vod_id': f'{ctype}#{vid}#{slug}',
                'vod_name': title.strip(),
                'vod_pic': '',
                'vod_remarks': '',
            })
        return items

    def _get_chinese_categories(self):
        return _CHINESE_CATEGORIES

    def _get_category_tags(self, tid):
        if tid in self._tag_cache:
            return self._tag_cache[tid]
        if _is_novel(tid) or _is_image(tid):
            return []
        base_tid = tid
        if base_tid.endswith('_random/all'):
            base_tid = base_tid[:-11]
        elif base_tid.endswith('_random'):
            base_tid = base_tid[:-7]
        urls_to_try = [
            f'{self.host}/zh/{base_tid}_random/all/index.html',
            f'{self.host}/zh/{base_tid}_list/all/index.html',
            f'{self.host}/zh/{base_tid}/index.html',
        ]
        text = None
        for u in urls_to_try:
            text = self._fetch(u)
            if text:
                break
        if not text:
            self._tag_cache[tid] = []
            return []
        tags = []
        seen = set()
        for match in re.finditer(r'href=[\'"](/zh/((?:' + re.escape(base_tid) + r')_(?:search|tag)/all/[^/\'"]+)/)[\'"]', text, re.I):
            path = match.group(1)
            label = path.rsplit('/', 2)[0].split('/')[-1]
            label = unquote(label)
            if not label or label in seen:
                continue
            seen.add(label)
            tags.append({'n': label, 'v': path})
        self._tag_cache[tid] = tags
        return tags

    def _build_filters(self):
        filters = {}

        chinese_tags = self._get_chinese_categories()
        dynamic_chinese = self._get_category_tags('chinese_random/all')
        all_chinese_opts = [{'n': '全部', 'v': ''}]
        seen_names = set()
        for t in dynamic_chinese:
            if t['n'] not in seen_names:
                seen_names.add(t['n'])
                all_chinese_opts.append(t)
        for t in chinese_tags:
            if t['n'] not in seen_names:
                seen_names.add(t['n'])
                all_chinese_opts.append(t)
        filters['chinese_random/all'] = [{'key': 'sub', 'name': '分类', 'value': all_chinese_opts}]

        video_tids = [
            'censored_random/all',
            'uncensored_random/all',
            'amateurjav_random/all',
            'reducing-mosaic_random/all',
        ]
        for tid in video_tids:
            dynamic = self._get_category_tags(tid)
            if tid == 'uncensored_random/all':
                static_opts = [
                    {'n': '一本道(1pondo)', 'v': 'uncensored_makersr/32/一本道(1pondo)'},
                    {'n': 'カリビアンコム(Caribbeancom)', 'v': 'uncensored_makersr/30/カリビアンコム(Caribbeancom)'},
                    {'n': 'カリビアンコムPPV', 'v': 'uncensored_makersr/40/カリビアンコムPPV(Caribbeancompr)'},
                    {'n': '天然むすめ(10musume)', 'v': 'uncensored_makersr/31/天然むすめ(10musume)'},
                    {'n': 'HEYZO', 'v': 'uncensored_makersr/17/HEYZO'},
                    {'n': '東京熱(Tokyo Hot)', 'v': 'uncensored_makersr/29/東京熱(Tokyo Hot)'},
                    {'n': 'ガチん娘！(Gachinco)', 'v': 'uncensored_makersr/35/ガチん娘！(Gachinco)'},
                    {'n': 'パコパコママ(pacopacomama)', 'v': 'uncensored_makersr/36/パコパコママ(pacopacomama)'},
                    {'n': 'エッチな4610', 'v': 'uncensored_makersr/34/エッチな4610'},
                    {'n': '人妻斬り0930', 'v': 'uncensored_makersr/38/人妻斬り0930'},
                    {'n': 'エッチな0930', 'v': 'uncensored_makersr/39/エッチな0930'},
                    {'n': 'トリプルエックス(XXX-AV)', 'v': 'uncensored_makersr/126/トリプルエックス (XXX-AV)'},
                ]
                opts = [{'n': '全部', 'v': ''}]
                opts.extend(dynamic)
                opts.append({'n': '——厂商筛选——', 'v': ''})
                opts.extend(static_opts)
                filters[tid] = [{'key': 'sub', 'name': '筛选', 'value': opts}]
            else:
                if dynamic:
                    opts = [{'n': '全部', 'v': ''}]
                    opts.extend(dynamic)
                    filters[tid] = [{'key': 'sub', 'name': '标签', 'value': opts}]

        cg_opts = [
            {'n': '全部', 'v': ''},
            {'n': 'Bejean On Line', 'v': 'cg_search/all/Bejean On Line'},
            {'n': 'Bomb.tv', 'v': 'cg_search/all/Bomb.tv'},
            {'n': 'DGC', 'v': 'cg_search/all/DGC'},
            {'n': 'Graphis Gals', 'v': 'cg_search/all/Graphis Gals'},
            {'n': 'Graphis Hatsunugi', 'v': 'cg_search/all/Graphis Hatsunugi'},
            {'n': 'image.tv', 'v': 'cg_search/all/image.tv'},
            {'n': 'Sabra.net', 'v': 'cg_search/all/Sabra.net'},
            {'n': 'S-Cute', 'v': 'cg_search/all/S-Cute'},
            {'n': 'X-City', 'v': 'cg_search/all/X-City'},
            {'n': 'YS Web', 'v': 'cg_search/all/YS Web'},
        ]
        filters['cg_random/all'] = [{'key': 'sub', 'name': '系列', 'value': cg_opts}]
        cwp_opts = [
            {'n': '全部', 'v': ''},
            {'n': '3AGirl AAA女郎', 'v': 'cwp_search/all/3AGirl AAA女郎'},
            {'n': 'ROSI寫真', 'v': 'cwp_search/all/ROSI寫真'},
            {'n': 'RU1MM 如壹寫真', 'v': 'cwp_search/all/RU1MM 如壹寫真'},
            {'n': 'DISI第四印象', 'v': 'cwp_search/all/DISI第四印象'},
        ]
        filters['cwp_random/all'] = [{'key': 'sub', 'name': '系列', 'value': cwp_opts}]
        novel_opts = [
            {'n': '全部', 'v': ''},
            {'n': '學生校園', 'v': 'novel_search/all/學生校園'},
            {'n': '職場激情', 'v': 'novel_search/all/職場激情'},
            {'n': '經驗故事', 'v': 'novel_search/all/經驗故事'},
            {'n': '暴力虐待', 'v': 'novel_search/all/暴力虐待'},
            {'n': '不倫戀情', 'v': 'novel_search/all/不倫戀情'},
            {'n': '群體換伴', 'v': 'novel_search/all/群體換伴'},
            {'n': '人妻熟女', 'v': 'novel_search/all/人妻熟女'},
            {'n': '科學幻想', 'v': 'novel_search/all/科學幻想'},
            {'n': '其他故事', 'v': 'novel_search/all/其他故事'},
            {'n': '玄幻仙俠', 'v': 'novel_search/all/玄幻仙俠'},
            {'n': '動漫修改', 'v': 'novel_search/all/動漫修改'},
            {'n': '長篇連載', 'v': 'novel_search/all/長篇連載'},
        ]
        filters['novel_random/all'] = [{'key': 'sub', 'name': '主题', 'value': novel_opts}]
        return filters

    def homeContent(self, filter):
        try:
            return self._homeContent_inner(filter)
        except Exception:
            return {'class': [], 'filters': {}, 'type': '影视', 'list': [],
                    'page': 1, 'pagecount': 1, 'limit': 0, 'total': 0}

    def _load_classes(self, text):
        classes = []
        seen = set()
        for href, key, name in re.findall(r'href=[\'\"](https://mjv011\.com/zh/([^\'\"/_]+)_random/all/index\.html)[\'\"][^>]*>([^<]+)</a>', text):
            name = re.sub(r'\s*\(\d+\)\s*$', '', name.strip())
            if any(x in name for x in ['random', '隨機', '随机', '近作']):
                continue
            tid = f'{key}_random/all'
            if tid in seen:
                continue
            seen.add(tid)
            classes.append({'type_id': tid, 'type_name': name})
        return classes

    def _homeContent_inner(self, filter):
        text = self._fetch(f'{self.host}/zh/chinese_IamOverEighteenYearsOld/19/index.html')
        classes = self._load_classes(text)
        if not classes:
            classes = [
                {'type_id': 'chinese_random/all', 'type_name': '中文字幕'},
                {'type_id': 'censored_random/all', 'type_name': '有码'},
                {'type_id': 'uncensored_random/all', 'type_name': '无码'},
                {'type_id': 'amateurjav_random/all', 'type_name': '素人'},
                {'type_id': 'reducing-mosaic_random/all', 'type_name': '无码破解'},
                {'type_id': 'animation_random/all', 'type_name': 'H动画'},
                {'type_id': 'CensoredAnimation_random/all', 'type_name': 'H有码动画'},
                {'type_id': 'UncensoredAnimation_random/all', 'type_name': 'H无码动画'},
                {'type_id': 'tdAnimation_random/all', 'type_name': 'H_3D动画'},
                {'type_id': 'dt_random/all', 'type_name': '国产自拍'},
                {'type_id': '18H_random/all', 'type_name': '18H漫画'},
                {'type_id': 'doujin_random/all', 'type_name': '18H短篇同人'},
                {'type_id': 'cg_random/all', 'type_name': '写真图集'},
                {'type_id': 'cwp_random/all', 'type_name': '国产写真'},
                {'type_id': 'novel_random/all', 'type_name': '小说'},
            ]
        new_classes = []
        new_classes.append({'type_id': 'home', 'type_name': '首页'})
        new_classes.append({'type_id': 'content_news/all', 'type_name': '每日更新'})
        for c in classes:
            if c['type_id'] not in ['home', 'content_news/all']:
                new_classes.append(c)
        classes = new_classes
        items = self._parse_posts(text, 'chinese_random/all')
        filters = self._build_filters()
        return {'class': classes, 'filters': filters, 'type': '影视', 'list': items,
                'page': 1, 'pagecount': 1, 'limit': len(items), 'total': len(items)}

    def homeVideoContent(self):
        try:
            text = self._fetch(f'{self.host}/zh/chinese_IamOverEighteenYearsOld/19/index.html')
            return {'list': self._parse_posts(text, 'chinese_random/all')}
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            return self._categoryContent_inner(tid, pg, filter, extend)
        except Exception as e:
            return {'list': [], 'page': int(pg) if pg else 1, 'pagecount': 1, 'limit': 0, 'total': 0}

    def _categoryContent_inner(self, tid, pg, filter, extend):
        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if not extend:
            extend = {}
        page = int(pg) if pg else 1

        if tid == 'home':
            text = self._fetch(f'{self.host}/zh/chinese_IamOverEighteenYearsOld/19/index.html')
            if text:
                items = self._parse_posts(text, 'chinese_random/all')
                per_page = 20
                total = len(items)
                start = (page - 1) * per_page
                end = start + per_page
                page_items = items[start:end]
                return {'list': page_items, 'page': page,
                        'pagecount': (total + per_page - 1) // per_page,
                        'limit': len(page_items), 'total': total}
            return {'list': [], 'page': 1, 'pagecount': 1, 'limit': 0, 'total': 0}

        if tid == 'content_news/all':
            today = datetime.now().strftime('%Y-%m-%d')
            url = f'{self.host}/zh/content_news/all/{today}.html'
            text = self._fetch(url)
            if text:
                items = self._parse_posts(text, tid)
                if items:
                    return {'list': items, 'page': 1, 'pagecount': 1, 'limit': len(items), 'total': len(items)}
            return {'list': [], 'page': 1, 'pagecount': 1, 'limit': 0, 'total': 0}

        candidates = []
        if extend and extend.get('sub'):
            sub = quote(unquote(extend['sub']), safe='/()')
            candidates.append(f'{self.host}/zh/{sub}/{page}.html')
        if tid.startswith('search_'):
            kw = tid[7:]
            candidates.append(f'{self.host}/zh/chinese_search/all/{kw}/{page}.html')
        else:
            base_tid = tid
            if base_tid.endswith('_random/all'):
                base_tid = base_tid[:-11]
            elif base_tid.endswith('_random'):
                base_tid = base_tid[:-7]
            elif base_tid.endswith('_list/all'):
                base_tid = base_tid[:-10]
            if page == 1:
                candidates.append(f'{self.host}/zh/{base_tid}_list/all/index.html')
                candidates.append(f'{self.host}/zh/{base_tid}_random/all/index.html')
            candidates.append(f'{self.host}/zh/{base_tid}_list/all/{page}.html')
            candidates.append(f'{self.host}/zh/{base_tid}_list/index_{page}.html')
            candidates.append(f'{self.host}/zh/{base_tid}/{page}.html')
            candidates.append(f'{self.host}/zh/{base_tid}/page/{page}.html')
            candidates.append(f'{self.host}/zh/{base_tid}_random/all/{page}.html')
            if page > 1:
                candidates.append(f'{self.host}/zh/{base_tid}_list/index_{page}.html')

        items = []
        for url in candidates:
            text = self._fetch(url)
            if text:
                parse_tid = tid
                if extend and extend.get('sub'):
                    sub = extend['sub']
                    if _is_novel(sub):
                        parse_tid = 'novel_random/all'
                    elif _is_image(sub):
                        parse_tid = sub.split('_')[0] + '_random/all' if '_' in sub else 'cg_random/all'
                items = self._parse_posts(text, parse_tid)
                if items:
                    break

        return {'list': items, 'page': page, 'pagecount': page + 1,
                'limit': len(items), 'total': page * len(items) + 1}

    # ===== 详情接口 =====
    def detailContent(self, ids):
        try:
            return self._detailContent_inner(ids)
        except Exception:
            return {'list': []}

    def _detailContent_inner(self, ids):
        vid = str(ids[0] if isinstance(ids, list) else ids)
        ctype, num, slug = vid.split('#', 2)
        if _is_novel(ctype):
            return self._novel_detail(vid, ctype, num, slug)
        elif _is_image(ctype):
            return self._image_detail(vid, ctype, num, slug)
        else:
            return self._video_detail(vid, ctype, num, slug)

    def _video_detail(self, vid, ctype, num, slug):
        url = f'{self.host}/zh/{ctype}_content/{num}/{slug}.html'
        text = self._fetch(url)
        if not text: return {'list': []}
        title = ''
        m = re.search(r'<h1[^>]*>(.*?)</h1>', text, re.S)
        if m: title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if not title:
            m = re.search(r'<title>([^<]+)</title>', text)
            if m: title = m.group(1).strip()
        cover = ''
        m = re.search(r'"thumbnailUrl"\s*:\s*"([^"]+)"', text)
        if m: cover = m.group(1)
        if not cover:
            m = re.search(r"<meta[^>]*property=\"og:image\"[^>]*content=\"([^\"]+)\"", text)
            if m: cover = m.group(1)
        if not cover:
            m = re.search(r"<div class='post'>.*?<img[^>]*src='([^']+)'", text, re.S)
            if m: cover = m.group(1)

        m = re.search(r'hadeedg252=(\d+)', text)
        if not m: return {'list': []}
        hadeedg252 = int(m.group(1))
        m = re.search(r'hcdeedg252=(\d+)', text)
        if not m: return {'list': []}
        hcdeedg252 = int(m.group(1))
        m = re.search(r"var argdeqweqweqwe = '([^']+)'", text)
        if not m: return {'list': []}
        aes_key = m.group(1)
        m = re.search(r"var hdddedg252 = '([^']+)'", text)
        if not m: return {'list': []}
        aes_iv = m.group(1)

        mm = re.search(r"mvarr\['10_1'\]=(\[.*?\]);", text, re.S)
        if not mm: return {'list': []}
        mvarr_str = mm.group(1)
        items = re.findall(r"\['([^']*)','([^']*)','([^']*)','([^']*)','([^']*)','([^']*)'\]", mvarr_str)
        if not items: return {'list': []}

        urls = []
        for iframe_id, enc, html, prefix, empty, label in items:
            if not enc or not prefix: continue
            pid = self._decrypt_id(enc, hadeedg252, hcdeedg252, aes_key, aes_iv)
            if not pid: continue
            for res, label_name in [('480', '480P'), ('720', '720P'), ('1080', '1080P')]:
                urls.append(f'{label_name}${num}|{slug}|{pid}|{res}')

        if not urls: return {'list': []}
        vod = {
            'vod_id': vid,
            'vod_name': title,
            'vod_pic': self._proxy_url(cover),
            'vod_content': '',
            'vod_remarks': '',
            'vod_play_from': 'mjv011',
            'vod_play_url': '#'.join(urls),
        }
        return {'list': [vod]}

    def _novel_detail(self, vid, ctype, num, slug):
        url = f'{self.host}/zh/{ctype}_content/{num}/{slug}.html'
        text = self._fetch(url)
        if not text: return {'list': []}
        title = ''
        m = re.search(r'<h1[^>]*>(.*?)</h1>', text, re.S)
        if m: title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        content = ''
        m = re.search(r"id=['\"]novel_content_txtsize['\"][^>]*>(.*?)</div>", text, re.S)
        if m:
            raw = m.group(1)
            content = re.sub(r'<[^>]+>', '', raw)
            content = re.sub(r'&nbsp;', ' ', content)
            content = re.sub(r'\s+', ' ', content).strip()
        if not content:
            m = re.search(r"<span class='content_18h_wpcg'>([\s\S]*?)</span>\s*<div class='contents'", text)
            if m:
                raw = m.group(1)
                content = re.sub(r'<[^>]+>', '', raw)
                content = re.sub(r'&nbsp;', ' ', content)
                content = re.sub(r'\s+', ' ', content).strip()
        if len(content) > 3000:
            content = content[:3000] + '...'
        novel_json = json.dumps({'title': title, 'content': content}, ensure_ascii=False)
        play_url = f'阅读$novel://{novel_json}'
        vod = {
            'vod_id': vid,
            'vod_name': title,
            'vod_pic': '',
            'vod_content': '',
            'vod_remarks': '',
            'vod_play_from': '小说',
            'vod_play_url': play_url,
            'vod_tag': 'text',
            'vod_player': '书',
        }
        return {'list': [vod]}

    def _image_detail(self, vid, ctype, num, slug):
        url = f'{self.host}/zh/{ctype}_content/{num}/{slug}.html'
        text = self._fetch(url)
        if not text: return {'list': []}
        title = ''
        m = re.search(r'<h1[^>]*>(.*?)</h1>', text, re.S)
        if m: title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        cover = ''
        m = re.search(r'"thumbnailUrl"\s*:\s*"([^"]+)"', text)
        if m: cover = m.group(1)
        all_imgs = re.findall(r"src=['\"]([^'\"]*eemmhh02\.com/[^'\"]+\.(?:jpg|png|webp))['\"]", text, re.I)
        big_imgs = []
        seen = set()
        for img in all_imgs:
            if img in seen:
                continue
            seen.add(img)
            big_imgs.append(self._proxy_url(img))
        if not big_imgs:
            return {'list': []}
        pics = '&&'.join(big_imgs)
        play_url = f'查看$pics://{pics}'
        vod = {
            'vod_id': vid,
            'vod_name': title,
            'vod_pic': self._proxy_url(cover),
            'vod_content': f'共 {len(big_imgs)} 张图片',
            'vod_remarks': str(len(big_imgs)) + 'P',
            'vod_play_from': '图片',
            'vod_play_url': play_url,
            'vod_tag': 'image',
            'vod_player': '画',
        }
        return {'list': [vod]}

    def _decrypt_id(self, enc, xor_key, base, aes_key, aes_iv):
        try:
            sep = chr(base + 97)
            parts = enc.split(sep)
            s1 = ''.join(chr(int(p, base) ^ xor_key) for p in parts if p)
            data = base64.b64decode(s1)
            plain = _aes_cbc_decrypt(data, aes_key.encode(), aes_iv.encode())
            return plain.decode('utf-8')
        except Exception:
            return ''

    def searchContent(self, key, quick, pg="1"):
        try:
            return self._searchContent_inner(key, quick, pg)
        except Exception:
            return {'list': [], 'page': int(pg) if pg else 1, 'pagecount': 1, 'limit': 0, 'total': 0}

    def _searchContent_inner(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        return self._categoryContent_inner(f'search_{key}', page, False, {})

    def playerContent(self, flag, id, vipFlags=None):
        try:
            return self._playerContent_inner(flag, id, vipFlags)
        except Exception:
            return {'parse': 0, 'url': '', 'header': {}, 'position': '0'}

    def _playerContent_inner(self, flag, id, vipFlags=None):
        if id.startswith('novel://'):
            return {'parse': 0, 'url': id, 'header': '', 'vod_player': '书'}
        if id.startswith('pics://'):
            return {'parse': 0, 'playUrl': '', 'url': id, 'header': self.headers}
        try:
            num, slug, pid, res = id.split('|', 3)
        except ValueError:
            return {'parse': 1, 'url': id, 'header': self.headers}
        url = f'{self.host}/js/player/play.php?numresolution={res}&lo=on&id={pid}'
        text = self._fetch(url)
        m3u8 = ''
        if text:
            mm = re.search(r'videoSources\s*=\s*(\[.*?\]);', text, re.S)
            if mm:
                arr = mm.group(1)
                sources = re.findall(r"src:\s*'([^']+)'[^}]*?size:\s*(\d+)", arr, re.S)
                if sources:
                    target = int(res) if str(res).isdigit() else 0
                    for u, s in sources:
                        if int(s) == target:
                            m3u8 = u
                            break
                    if not m3u8:
                        m3u8 = sources[0][0]
            if not m3u8:
                mm = re.search(r'https?://[^\s"<>\']+?\.m3u8', text)
                if mm: m3u8 = mm.group(0)
        if m3u8:
            return {'parse': 0, 'url': m3u8, 'header': {'Referer': self.host + '/'}, 'position': '0'}
        else:
            return {'parse': 1, 'url': id, 'header': self.headers}