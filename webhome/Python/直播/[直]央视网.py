import sys
import re
import json
import time
import random
import struct
import requests
from base64 import b64encode, b64decode
from urllib.parse import urlencode
from urllib3 import disable_warnings
from base.spider import Spider

disable_warnings()


class Spider(Spider):
    # ==================== 加密常量 ====================
    DELTA = 0x9e3779b9
    ROUNDS = 16
    LOG_ROUNDS = 4
    SALT_LEN = 2
    ZERO_LEN = 7
    TEA_CKEY = bytes.fromhex('59b2f7cf725ef43c34fdd7c123411ed3')
    GUARD_TEA_KEY = bytes.fromhex('110DBEC10C23E7D2E56A1CAD6914EF1B')

    XOR_KEY = [0x84, 0x2E, 0xED, 0x08, 0xF0, 0x66, 0xE6, 0xEA,
               0x48, 0xB4, 0xCA, 0xA9, 0x91, 0xED, 0x6F, 0xF3]
    GUARD_XOR_KEY = [0xB3, 0xC9, 0x53, 0xA0, 0x69, 0x13, 0xAD, 0x4D]

    STANDARD_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/='
    CUSTOM_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-='

    # ==================== 频道数据 ====================
    # {key: [cnlid, livepid, defn, display_name]}
    CHANNELS = {
        'cctv1': ['2024078201', '600001859', 'fhd', 'CCTV-1'],
        'cctv2': ['2024075401', '600001800', 'fhd', 'CCTV-2'],
        'cctv3': ['2024068501', '600001801', 'fhd', 'CCTV-3'],
        'cctv4': ['2029797101', '600001814', 'fhd', 'CCTV-4'],
        'cctv5': ['2024078401', '600001818', 'fhd', 'CCTV-5'],
        'cctv5p': ['2024078001', '600001817', 'fhd', 'CCTV-5+'],
        'cctv6': ['2013693901', '600108442', 'fhd', 'CCTV-6'],
        'cctv7': ['2024072001', '600004092', 'fhd', 'CCTV-7'],
        'cctv8': ['2029793001', '600001803', 'fhd', 'CCTV-8'],
        'cctv9': ['2024078601', '600004078', 'fhd', 'CCTV-9'],
        'cctv10': ['2024078701', '600001805', 'fhd', 'CCTV-10'],
        'cctv11': ['2027248701', '600001806', 'fhd', 'CCTV-11'],
        'cctv12': ['2027248801', '600001807', 'fhd', 'CCTV-12'],
        'cctv13': ['2029797201', '600001811', 'fhd', 'CCTV-13'],
        'cctv14': ['2027248901', '600001809', 'fhd', 'CCTV-14'],
        'cctv15': ['2027249001', '600001815', 'fhd', 'CCTV-15'],
        'cctv16': ['2027249101', '600098637', 'fhd', 'CCTV-16'],
        'cctv164k': ['2027249301', '600099502', 'fhd', 'CCTV-16(4K)'],
        'cctv17': ['2027249401', '600001810', 'fhd', 'CCTV-17'],
        'cctv4k': ['2029810301', '600002264', 'fhd', 'CCTV-4K'],
        'cctv8k': ['2026774101', '600156816', 'fhd', 'CCTV-8K'],
        'cgtn': ['2024181701', '600014550', 'fhd', 'CGTN'],
        'cgtnfy': ['2024181801', '600084704', 'fhd', 'CGTN法语'],
        'cgtney': ['2024181901', '600084758', 'fhd', 'CGTN俄语'],
        'cgtnalby': ['2024182001', '600084782', 'fhd', 'CGTN阿拉伯语'],
        'cgtnxby': ['2024182101', '600084744', 'fhd', 'CGTN西班牙语'],
        'cgtnwyjl': ['2024182301', '600084781', 'fhd', 'CGTN外语纪录'],
        'cctvfyjc': ['2025637103', '600099658', 'shd', '风云剧场'],
        'cctvdyjc': ['2026874203', '600099655', 'shd', '第一剧场'],
        'cctvhjjc': ['2026874303', '600099620', 'shd', '怀旧剧场'],
        'cctvsjdl': ['2026874403', '600099637', 'shd', '世界地理'],
        'cctvfyyy': ['2026874503', '600099660', 'shd', '风云音乐'],
        'cctvbqkj': ['2026874603', '600099649', 'shd', '兵器科技'],
        'cctvfyzq': ['2026966203', '600099636', 'shd', '风云足球'],
        'cctvgeqwq': ['2026874703', '600099659', 'shd', '高尔夫·网球'],
        'cctvnxss': ['2026874803', '600099650', 'shd', '女性时尚'],
        'cctvyswhjp': ['2026874903', '600099653', 'shd', '央视文化精品'],
        'cctvystq': ['2026875003', '600099652', 'shd', '央视台球'],
        'cctvdszn': ['2026875103', '600099656', 'shd', '电视指南'],
        'cctvwsjk': ['2025637003', '600099651', 'shd', '卫生健康'],
        'bjws': ['2024052703', '600002309', 'fhd', '北京卫视'],
        'jsws': ['2024171103', '600002521', 'fhd', '江苏卫视'],
        'dfws': ['2024054503', '600002483', 'fhd', '东方卫视'],
        'zjws': ['2024054703', '600002520', 'fhd', '浙江卫视'],
        'hnws': ['2024054803', '600002475', 'fhd', '湖南卫视'],
        'hbws': ['2024171203', '600002508', 'fhd', '湖北卫视'],
        'gdws': ['2024060903', '600002485', 'fhd', '广东卫视'],
        'gxws': ['2024060703', '600002509', 'fhd', '广西卫视'],
        'hljws': ['2029797003', '600002498', 'fhd', '黑龙江卫视'],
        'hnws2': ['2024055603', '600002506', 'fhd', '海南卫视'],
        'cqws': ['2024061103', '600002531', 'fhd', '重庆卫视'],
        'szws': ['2024061303', '600002481', 'fhd', '深圳卫视'],
        'scws': ['2024061403', '600002516', 'fhd', '四川卫视'],
        'henanws': ['2029797303', '600002525', 'fhd', '河南卫视'],
        'fjdnhz': ['2024061503', '600002484', 'fhd', '福建东南卫视'],
        'gzhws': ['2024061603', '600002490', 'fhd', '贵州卫视'],
        'jxws': ['2024061703', '600002503', 'fhd', '江西卫视'],
        'lnws': ['2024171303', '600002505', 'fhd', '辽宁卫视'],
        'ahws': ['2024171403', '600002532', 'fhd', '安徽卫视'],
        'hbws2': ['2024171503', '600002493', 'fhd', '河北卫视'],
        'sdws': ['2029787903', '600002513', 'fhd', '山东卫视'],
        'tjws': ['2019927003', '600152137', 'fhd', '天津卫视'],
        'jlws': ['2025561503', '600190405', 'fhd', '吉林卫视'],
        'shanxiws': ['2029795103', '600190400', 'fhd', '陕西卫视'],
        'nxws': ['2025608503', '600190737', 'fhd', '宁夏卫视'],
        'nmgws': ['2025561203', '600190401', 'fhd', '内蒙古卫视'],
        'ynws': ['2025561303', '600190402', 'fhd', '云南卫视'],
        'shanxiws2': ['2025560803', '600190407', 'fhd', '山西卫视'],
        'qhws': ['2025559103', '600190406', 'fhd', '青海卫视'],
        'xzws': ['2025558003', '600190403', 'fhd', '西藏卫视'],
        'xjws': ['2019927403', '600152138', 'fhd', '新疆卫视'],
        'cetv1': ['2022823801', '600171827', 'fhd', '中国教育电视台'],
        'gxpd': ['2029360403', '600213139', 'fhd', '国学频道'],
    }

    # ==================== 分类定义 ====================
    CATS = [
        {
            'name': '央视',
            'ids': [
                'cctv1', 'cctv2', 'cctv3', 'cctv4', 'cctv5', 'cctv5p',
                'cctv6', 'cctv7', 'cctv8', 'cctv9', 'cctv10', 'cctv11',
                'cctv12', 'cctv13', 'cctv14', 'cctv15', 'cctv16', 'cctv164k',
                'cctv17', 'cctv4k', 'cctv8k',
            ]
        },
        {
            'name': 'CGTN',
            'ids': ['cgtn', 'cgtnfy', 'cgtney', 'cgtnalby', 'cgtnxby', 'cgtnwyjl']
        },
        {
            'name': '央视付费',
            'ids': [
                'cctvfyjc', 'cctvdyjc', 'cctvhjjc', 'cctvsjdl', 'cctvfyyy',
                'cctvbqkj', 'cctvfyzq', 'cctvgeqwq', 'cctvnxss', 'cctvyswhjp',
                'cctvystq', 'cctvdszn', 'cctvwsjk',
            ]
        },
        {
            'name': '卫视',
            'ids': [
                'bjws', 'jsws', 'dfws', 'zjws', 'hnws', 'hbws', 'gdws',
                'gxws', 'hljws', 'hnws2', 'cqws', 'szws', 'scws', 'henanws',
                'fjdnhz', 'gzhws', 'jxws', 'lnws', 'ahws', 'hbws2', 'sdws',
                'tjws', 'jlws', 'shanxiws', 'nxws', 'nmgws', 'ynws',
                'shanxiws2', 'qhws', 'xzws', 'xjws',
            ]
        },
        {
            'name': '其他',
            'ids': ['cetv1', 'gxpd']
        },
    ]

    # ==================== 初始化 ====================

    def init(self, extend=""):
        self.guid = self._gen_guid()
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            'User-Agent': 'qqlive',
            'Connection': 'Keep-Alive',
            'Accept': 'application/json',
        })

    def getName(self):
        return "央视频"

    # ==================== 蜘蛛壳接口 ====================

    def homeContent(self, filter):
        classes = [
            {'type_id': str(i), 'type_name': c['name']}
            for i, c in enumerate(self.CATS)
        ]
        return {'class': classes}

    def categoryContent(self, tid, pg, filter, extend):
        cat = self.CATS[int(tid)]
        vod_list = []
        for cid in cat['ids']:
            ch = self.CHANNELS.get(cid)
            if ch:
                vod_list.append({
                    'vod_id': cid,
                    'vod_name': ch[3],
                    'vod_pic': '',
                    'vod_remarks': ch[2].upper(),
                })
        return {
            'page': 1,
            'pagecount': 1,
            'limit': len(vod_list),
            'total': len(vod_list),
            'list': vod_list,
        }

    def detailContent(self, ids):
        cid = ids[0]
        ch = self.CHANNELS.get(cid)
        if not ch:
            return {'list': []}
        vod = {
            'vod_id': cid,
            'vod_name': ch[3],
            'vod_pic': '',
            'vod_play_from': '央视频',
            'vod_play_url': f'直播${cid}',
            'vod_content': f'{ch[3]} 高清直播',
        }
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        ch = self.CHANNELS.get(id)
        if not ch:
            return {'parse': 0, 'url': '', 'header': ''}
        play_url = self._get_play_url(ch[0], ch[1], ch[2])
        if play_url:
            return {'parse': 0, 'url': play_url, 'header': ''}
        return {'parse': 0, 'url': '', 'header': ''}

    # ==================== 播放地址获取 ====================

    def _get_play_url(self, cnlid, livepid, defn):
        try:
            self.guid = self._gen_guid()
            ck = self._gen_ckey(cnlid)
            flowid = self._gen_flowid()

            params = {
                "atime": "120",
                "livepid": livepid,
                "cnlid": cnlid,
                "appVer": "V8.22.1035.3031",
                "app_version": "300090",
                "caplv": "1",
                "cmd": "2",
                "defn": defn,
                "device": "iPhone",
                "encryptVer": "4.2",
                "getpreviewinfo": "0",
                "hevclv": "33",
                "lang": "zh-Hans_JP",
                "livequeue": "0",
                "logintype": "1",
                "nettype": "1",
                "newnettype": "1",
                "newplatform": "4330403",
                "platform": "4330403",
                "sdtfrom": "v3021",
                "spacode": "23",
                "spaudio": "1",
                "spdemuxer": "6",
                "spdrm": "2",
                "spdynamicrange": "7",
                "spflv": "1",
                "spflvaudio": "1",
                "sphdrfps": "60",
                "sphttps": "0",
                "spvcode": "MSgzMDoyMTYwLDYwOjIxNjB8MzA6MjE2MCw2MDoyMTYwKTsyKDMwOjIxNjAsNjA6MjE2MHwzMDoyMTYwLDYwOjIxNjAp",
                "spvideo": "4",
                "stream": "1",
                "system": "1",
                "sysver": "ios18.2.1",
                "uhd_flag": "4",
                "cKey": ck['ckey'],
                "guid": self.guid,
                "fntick": ck['params']['Timestamp'],
                "flowid": flowid,
                "playbacktime": "0",
            }

            resp = self.session.get(
                "https://bkliveinfo.ysp.cctv.cn",
                params=params,
                timeout=15,
            )
            data = resp.json()
            if data.get('iretcode') == 0 and data.get('playurl'):
                return data['playurl']
        except Exception as e:
            print(f"[央视频] 获取播放地址失败: {e}")
        return None

    # ==================== GUID / FlowID ====================

    def _gen_guid(self):
        return '{:08x}{:04x}{:04x}{:04x}{:012x}'.format(
            random.randint(0, 0xffffffff),
            random.randint(0, 0xffff),
            random.randint(0, 0xffff),
            random.randint(0, 0xffff),
            random.randint(0, 0xffffffffffff),
        )

    def _gen_flowid(self):
        p = [
            random.randint(0, 0xffff), random.randint(0, 0xffff),
            random.randint(0, 0xffff),
            random.randint(0, 0x0fff) | 0x4000,
            random.randint(0, 0x3fff) | 0x8000,
            random.randint(0, 0xffff), random.randint(0, 0xffff),
            random.randint(0, 0xffff),
        ]
        return '{:04X}{:04X}-{:04X}-{:04X}-{:04X}-{:04X}{:04X}{:04X}_4330403'.format(*p)

    # ==================== 签名 ====================

    def _calc_sig(self, buf):
        s = 0
        for b in buf:
            s = (0x83 * s + (b & 0xFF)) & 0x7FFFFFFF
        return s

    # ==================== 自定义 Base64 ====================

    def _b64enc(self, data):
        enc = b64encode(data).decode()
        return enc.translate(str.maketrans(self.STANDARD_ALPHABET, self.CUSTOM_ALPHABET)).rstrip('=')

    def _b64dec(self, text):
        text = text.rstrip('=')
        if len(text) % 4:
            text += '=' * (4 - len(text) % 4)
        return b64decode(text.translate(str.maketrans(self.CUSTOM_ALPHABET, self.STANDARD_ALPHABET)))

    # ==================== XOR ====================

    def _xor(self, arr):
        return [arr[i] ^ self.XOR_KEY[i & 0xF] for i in range(len(arr))]

    # ==================== TEA ====================

    def _tea_enc(self, data, key):
        if len(data) < 8:
            data = data.ljust(8, b'\0')
        y, z = struct.unpack('>II', data[:8])
        k = struct.unpack('>4I', key[:16])
        s = 0
        for _ in range(self.ROUNDS):
            s = (s + self.DELTA) & 0xFFFFFFFF
            y = (y + (((z << 4) + k[0]) ^ (z + s) ^ ((z >> 5) + k[1]))) & 0xFFFFFFFF
            z = (z + (((y << 4) + k[2]) ^ (y + s) ^ ((y >> 5) + k[3]))) & 0xFFFFFFFF
        return struct.pack('>II', y, z)

    def _tea_dec(self, data, key):
        y, z = struct.unpack('>II', data[:8])
        k = struct.unpack('>4I', key[:16])
        s = (self.DELTA << self.LOG_ROUNDS) & 0xFFFFFFFF
        for _ in range(self.ROUNDS):
            z = (z - (((y << 4) + k[2]) ^ (y + s) ^ ((y >> 5) + k[3]))) & 0xFFFFFFFF
            y = (y - (((z << 4) + k[0]) ^ (z + s) ^ ((z >> 5) + k[1]))) & 0xFFFFFFFF
            s = (s - self.DELTA) & 0xFFFFFFFF
        return struct.pack('>II', y, z)

    # ==================== CBC 加密 ====================

    def _cbc_enc(self, p_in, n_len, p_key):
        pad_salt_zero = n_len + 1 + self.SALT_LEN + self.ZERO_LEN
        n_pad = pad_salt_zero % 8
        if n_pad:
            n_pad = 8 - n_pad

        out = b''
        src = [0] * 8
        src[0] = (random.randint(0, 255) & 0xF8) | n_pad
        si = 1

        while n_pad:
            src[si] = random.randint(0, 255)
            si += 1
            n_pad -= 1

        iv_p = [0] * 8
        iv_c = [0] * 8

        # salt
        i = 0
        while i < self.SALT_LEN:
            if si < 8:
                src[si] = random.randint(0, 255)
                si += 1
                i += 1
            if si == 8:
                for j in range(8):
                    src[j] ^= iv_c[j]
                tb = list(self._tea_enc(bytes(src), p_key))
                for j in range(8):
                    tb[j] ^= iv_p[j]
                iv_p = list(src)
                iv_c = list(tb)
                out += bytes(tb)
                si = 0

        # body
        pi = 0
        while n_len:
            if si < 8:
                src[si] = p_in[pi]
                pi += 1
                si += 1
                n_len -= 1
            if si == 8:
                for j in range(8):
                    src[j] ^= iv_c[j]
                tb = list(self._tea_enc(bytes(src), p_key))
                for j in range(8):
                    tb[j] ^= iv_p[j]
                iv_p = list(src)
                iv_c = list(tb)
                out += bytes(tb)
                si = 0

        # zero
        i = 0
        while i < self.ZERO_LEN:
            if si < 8:
                src[si] = 0
                si += 1
                i += 1
            if si == 8:
                for j in range(8):
                    src[j] ^= iv_c[j]
                tb = list(self._tea_enc(bytes(src), p_key))
                for j in range(8):
                    tb[j] ^= iv_p[j]
                iv_p = list(src)
                iv_c = list(tb)
                out += bytes(tb)
                si = 0

        # last
        if si > 0:
            for j in range(si, 8):
                src[j] = 0
            for j in range(8):
                src[j] ^= iv_c[j]
            tb = list(self._tea_enc(bytes(src), p_key))
            for j in range(8):
                tb[j] ^= iv_p[j]
            out += bytes(tb)

        return out

    # ==================== CBC 解密 ====================

    def _cbc_dec(self, p_in, n_len, p_key):
        if n_len % 8 != 0 or n_len < 16:
            return None
        dest = list(self._tea_dec(p_in[:8], p_key))
        n_pad = dest[0] & 0x07
        out_len = n_len - 1 - n_pad - self.SALT_LEN - self.ZERO_LEN
        if out_len < 0:
            return None

        iv_pre = [0] * 8
        iv_cur = list(p_in[:8])
        off = 8
        di = 1 + n_pad

        # skip salt
        sc = 1
        while sc <= self.SALT_LEN:
            if di < 8:
                di += 1
                sc += 1
            elif di == 8:
                iv_pre = list(iv_cur)
                if off + 8 > n_len:
                    return None
                iv_cur = list(p_in[off:off + 8])
                for j in range(8):
                    dest[j] ^= iv_cur[j]
                dest = list(self._tea_dec(bytes(dest), p_key))
                off += 8
                di = 0

        # copy plain
        plain = []
        rem = out_len
        while rem > 0:
            if di < 8:
                plain.append(dest[di] ^ iv_pre[di])
                di += 1
                rem -= 1
            elif di == 8:
                iv_pre = list(iv_cur)
                if off + 8 > n_len:
                    return None
                iv_cur = list(p_in[off:off + 8])
                for j in range(8):
                    dest[j] ^= iv_cur[j]
                dest = list(self._tea_dec(bytes(dest), p_key))
                off += 8
                di = 0
        return bytes(plain)

    # ==================== Guard Time ====================

    def _last5(self, v):
        v = str(v)
        return v[-5:] if len(v) >= 5 else ''

    def _gen_guard_time(self, ts, guid):
        body = struct.pack('>I', ts)
        for part in [self._last5(guid), self._last5('null'), self._last5('null'), '-1']:
            pb = part.encode()
            body += struct.pack('>H', len(pb)) + pb

        plain = struct.pack('>H', len(body)) + body
        chk = self._calc_sig(list(plain))

        enc = self._cbc_enc(plain, len(plain), self.GUARD_TEA_KEY) + struct.pack('>I', chk)
        el = list(enc)
        for i in range(len(el)):
            el[i] ^= self.GUARD_XOR_KEY[i & 7]
        return bytes(el).hex().upper()

    # ==================== CKey ====================

    def _encrypt_ckey(self, data):
        chk = self._calc_sig(list(data))
        enc = self._cbc_enc(data, len(data), self.TEA_CKEY) + struct.pack('>I', chk)
        return '--01' + self._b64enc(bytes(self._xor(list(enc))))

    def _build_pkt(self, params):
        d = b''
        d += bytes.fromhex('0000004200000004000004d2')  # 12-byte header
        d += struct.pack('>I', params['Platform'])
        d += struct.pack('>I', 0)  # sig placeholder
        d += struct.pack('>I', params['Timestamp'])

        for k in ['Sdtfrom', 'randFlag', 'appVer', 'vid', 'guid']:
            v = params[k].encode()
            d += struct.pack('>H', len(v)) + v

        d += struct.pack('>I', 1)  # part1
        d += struct.pack('>I', 1)  # isDlna

        for v in [b'2622783A', b'nil']:
            d += struct.pack('>H', len(v)) + v

        uuid4 = params['uuid4'].encode()
        d += struct.pack('>H', len(uuid4)) + uuid4

        d += struct.pack('>H', 3) + b'nil'  # bundleID1

        for v in [b'v0.1.000', b'com.cctv.yangshipin.app.iphone',
                  b'4330403', b'ex_json_bus', b'ex_json_vs']:
            d += struct.pack('>H', len(v)) + v

        cgt = params['ck_guard_time'].encode()
        d += struct.pack('>H', len(cgt)) + cgt

        buf = struct.pack('>H', len(d)) + d
        sig = self._calc_sig(list(buf))
        return buf[:18] + struct.pack('>I', sig) + buf[22:]

    def _gen_ckey(self, cnlid):
        ts = int(time.time())
        cgt = self._gen_guard_time(ts, self.guid)
        params = {
            'Platform': 4330403,
            'Timestamp': ts,
            'Sdtfrom': 'dcgh',
            'vid': cnlid,
            'guid': self.guid,
            'appVer': 'V8.22.1035.3031',
            'randFlag': '_zj1A5Gh6QYcxWjIUGos2w==',
            'uuid4': '57eab0c4-2c58-44c6-8ae9-dd2757525dc5',
            'ck_guard_time': cgt,
        }
        pkt = self._build_pkt(params)
        return {'ckey': self._encrypt_ckey(pkt), 'params': params}