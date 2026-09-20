# -*- coding: utf-8 -*-
import sys
import re
import json
import time
import base64
import random
import string
from datetime import datetime
from urllib.parse import quote

sys.path.append('..')
try:
    from base.spider import Spider
except ImportError:
    class Spider:
        def fetch(self, url, headers=None, **kw):
            import requests as rq
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r

import requests as _rq

# AES 依赖：优先 pycryptodome，其次 cryptography
try:
    from Crypto.Cipher import AES as _AES
    from Crypto.Util.Padding import pad as _pad, unpad as _unpad
    _AES_MODE = 'pycryptodome'
except ImportError:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher as _Cipher, algorithms as _algo, modes as _modes
        from cryptography.hazmat.primitives import padding as _padmod
        _AES_MODE = 'cryptography'
    except ImportError:
        _AES_MODE = None

HOST = "https://fktv.me"
API = HOST + "/ysapi"
API_KEY = "9ed1a661a6ab787a"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
DEVICE_ID = "4a90c25a1fc9905def6117d5af752bcf"

CATEGORIES = [
    {"type_id": "6", "type_name": "电影"},
    {"type_id": "5", "type_name": "连续剧"},
    {"type_id": "9", "type_name": "短剧"},
    {"type_id": "4", "type_name": "综艺"},
    {"type_id": "7", "type_name": "动漫"},
    {"type_id": "11", "type_name": "电影解说"},
]

_SES = _rq.Session()


def _aes_encrypt(plaintext):
    key = API_KEY.encode('utf-8')
    if isinstance(plaintext, str):
        plaintext = plaintext.encode('utf-8')
    if _AES_MODE == 'pycryptodome':
        cipher = _AES.new(key, _AES.MODE_ECB)
        ct = cipher.encrypt(_pad(plaintext, 16))
    elif _AES_MODE == 'cryptography':
        padder = _padmod.PKCS7(128).padder()
        padded = padder.update(plaintext) + padder.finalize()
        enc = _Cipher(_algo.AES(key), _modes.ECB()).encryptor()
        ct = enc.update(padded) + enc.finalize()
    else:
        raise RuntimeError("no AES library available")
    return base64.b64encode(ct).decode()


def _aes_decrypt(b64ct):
    key = API_KEY.encode('utf-8')
    ct = base64.b64decode(b64ct.strip())
    if _AES_MODE == 'pycryptodome':
        cipher = _AES.new(key, _AES.MODE_ECB)
        pt = _unpad(cipher.decrypt(ct), 16)
    elif _AES_MODE == 'cryptography':
        dec = _Cipher(_algo.AES(key), _modes.ECB()).decryptor()
        pt = dec.update(ct) + dec.finalize()
        unpadder = _padmod.PKCS7(128).unpadder()
        pt = unpadder.update(pt) + unpadder.finalize()
    else:
        raise RuntimeError("no AES library available")
    return pt.decode('utf-8')


def _api_call(endpoint, data):
    body = {
        "deviceId": DEVICE_ID,
        "token": "",
        "domain": "fktv.me",
        "referer": "",
        "user_agent": UA,
        "shareCode": "",
        "channel": "",
        "ip": "",
        "data": data,
    }
    enc = _aes_encrypt(json.dumps(body, separators=(',', ':')))
    headers = {
        "version": "1.0",
        "deviceType": "pc",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "shareCode": "",
        "channel": "",
        "ip": "",
        "Content-Type": "application/octet-stream",
        "User-Agent": UA,
        "Referer": HOST + "/",
    }
    r = _SES.post(API + "/" + endpoint, data=enc, headers=headers, timeout=20)
    text = r.text.strip()
    if not text:
        return None
    try:
        return json.loads(_aes_decrypt(text))
    except Exception:
        try:
            return json.loads(text)
        except Exception:
            return None


CDN_HOST = "https://cdn.g3ejjm8m.com"


def _fmt_score(score):
    # "7.00" -> "7.0"，"5.00" -> "5.0"，无效 -> ""
    try:
        v = float(score or 0)
        return ("%.1f" % v) if v > 0 else ""
    except Exception:
        return ""


def _make_remarks(item):
    # 官网卡片角标实际展示：年份 + 评分（列表接口不提供集数/清晰度）
    year = str(item.get("release_at", "") or "").strip()
    score = _fmt_score(item.get("score"))
    parts = []
    if year and year != "0":
        parts.append(year)
    if score:
        parts.append(score + "分")
    if parts:
        return " · ".join(parts)
    # 搜索联想接口字段较少，退回到分类名
    return item.get("child_title", "") or item.get("category", "") or ""


def _parse_item(item):
    pic = item.get("img_x_source") or item.get("img_x") or item.get("img") or ""
    if pic and pic.startswith("/"):
        pic = CDN_HOST + pic
    vod = {
        "vod_id": item.get("id", ""),
        "vod_name": item.get("name", "") or "",
        "vod_pic": pic,
        "vod_remarks": _make_remarks(item),
    }
    return vod


class Spider(Spider):
    def init(self, extend=""):
        pass

    def getName(self):
        return "凡客TV"

    def homeContent(self, filter=False):
        result = {"class": CATEGORIES, "filters": {}, "list": []}
        try:
            res = _api_call("movie/search", {"keyword": "", "page": "1"})
            if res and res.get("status") == "y":
                data = res.get("data", {})
                lst = data.get("data", [])
                result["list"] = [_parse_item(it) for it in lst if it.get("id")]
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        return self.homeContent().get("list", [])

    def categoryContent(self, tid, pg=1, filter=False, extend=""):
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1
        result = {"page": pn, "pagecount": 1, "limit": 15, "total": 0, "list": []}
        try:
            data = {"keyword": "", "page": str(pn)}
            if tid and str(tid) != "0":
                data["cat_id"] = str(tid)
            res = _api_call("movie/search", data)
            if res and res.get("status") == "y":
                d = res.get("data", {})
                lst = d.get("data", [])
                total = int(d.get("total", 0) or 0)
                last_page = int(d.get("last_page", 1) or 1)
                result["total"] = total
                result["pagecount"] = max(last_page, pn)
                result["list"] = [_parse_item(it) for it in lst if it.get("id")]
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        if isinstance(ids, list):
            vid = ids[0] if ids else ""
        else:
            vid = str(ids) if ids else ""
        if not vid:
            return {"list": []}
        try:
            res = _api_call("movie/detail", {"id": vid, "link_id": "", "is_simple": "n"})
            if not res:
                return {"list": []}
            data = res.get("data", {}) if isinstance(res, dict) else {}
            links = data.get("links", []) or []
            play_links = data.get("play_links", []) or []
            # 详情角标：多集显示总集数，单片显示 HD
            ep_count = len(links)
            if ep_count > 1:
                remarks = "共%d集" % ep_count
            elif ep_count == 1:
                remarks = "HD"
            else:
                remarks = str(data.get("release_at", "") or "")
            d = {
                "vod_id": vid,
                "vod_name": data.get("name", "") or "",
                "vod_pic": data.get("img_x_source") or data.get("img_x") or "",
                "vod_year": str(data.get("release_at", "") or ""),
                "vod_area": data.get("area", "") or "",
                "vod_class": data.get("categories", "") or "",
                "vod_director": data.get("director", "") or "",
                "vod_actor": data.get("actor", "") or "",
                "vod_content": data.get("description", "") or "",
                "vod_remarks": remarks,
                "vod_play_from": "",
                "vod_play_url": "",
            }
            if links:
                # 用播放线路名作为 vod_play_from
                line_names = [pl.get("name") or "线路%d" % (i + 1) for i, pl in enumerate(play_links)]
                if not line_names:
                    line_names = ["线路1"]
                # 每个线路都用同一组分集（按需在 playerContent 解析）
                from_list = []
                url_list = []
                for ln in line_names:
                    eps = []
                    for lk in links:
                        lid = lk.get("id", "")
                        name = lk.get("name", "") or lid
                        # 编码 movie_id|link_id 供 playerContent 使用
                        eps.append("%s$%s|%s" % (name, vid, lid))
                    from_list.append(ln)
                    url_list.append("#".join(eps))
                d["vod_play_from"] = "$$$".join(from_list)
                d["vod_play_url"] = "$$$".join(url_list)
            return {"list": [d]}
        except Exception:
            return {"list": []}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            pn = 1
            try:
                pn = int(str(pg))
            except Exception:
                pass
            result = {"list": [], "page": pn}
            res = _api_call("movie/smartSearch", {"keywords": key})
            if res and res.get("status") == "y":
                lst = res.get("data", []) or []
                result["list"] = [_parse_item(it) for it in lst if it.get("id")]
            return result
        except Exception:
            return {"list": []}

    def playerContent(self, flag, id, vipFlags=None):
        # id 格式: movie_id|link_id
        try:
            if "|" in str(id):
                movie_id, link_id = str(id).split("|", 1)
            else:
                movie_id, link_id = str(id), ""
            res = _api_call("movie/detail", {"id": movie_id, "link_id": link_id, "is_simple": "n"})
            if not res:
                return {"parse": 0, "url": ""}
            data = res.get("data", {}) if isinstance(res, dict) else {}
            play_links = data.get("play_links", []) or []
            url = ""
            # 优先用 play_links 的 m3u8_url
            for pl in play_links:
                u = pl.get("m3u8_url") or ""
                if u:
                    url = u
                    break
            # 回退到 playback_v2
            if not url:
                pv = data.get("playback_v2") or {}
                lines = pv.get("video_lines") or []
                for ln in lines:
                    h264 = (ln.get("h264") or {})
                    u = h264.get("url") or ""
                    if u:
                        url = HOST + u if u.startswith("/") else u
                        break
            if not url:
                # 最后回退 m3u8_url_source
                url = data.get("m3u8_url_source") or ""
            return {"parse": 0, "url": url, "header": {"User-Agent": UA}}
        except Exception:
            return {"parse": 0, "url": str(id) if str(id).startswith("http") else ""}

    def localProxy(self, param):
        pass
