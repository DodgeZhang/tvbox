import re
import sys
import json
import time
import base64
import hashlib
import logging
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from base.spider import Spider

sys.path.append('..')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Spider(Spider):
    def __init__(self):
        self.name = "瓜子"
        self.host = 'https://apinew.uozvr.com'
        self.token = 'bc2f1d031b3eb444d84528b4dcce5e07.3e091c3550c1cb09899ac4013a76a7731f946f4461c9dd7c7c2ca1f9090dc4841c7e0168fed38d3312a8a38650edeef2e2d47f24c884bb3bd7005e1280f3b6eb2d36829134992c0ece8748ae5b85fa57a94d3d6e38faa44168d7f24e4a588424a6bee7779c18ade979353688e3c56fbdcf1d5590385f5f7ef6e01d1850974aa220eb5178c89e61c24411af9b9a19435e.ca9d8de0fa2798b5695845f64adbabeee3d38f39506170d5deda14add46d37f0'
        self.aes_key = 'tOEryzJxZ8T385vS'
        self.aes_iv = 'uqPY6IFCoiLOjA5M'
        self.rsa_private_key = """-----BEGIN PRIVATE KEY-----
MIICdgIBADANBgkqhkiG9w0BAQEFAASCAmAwggJcAgEAAoGAe6hKrWLi1zQmjTT1
ozbE4QdFeJGNxubxld6GrFGximxfMsMB6BpJhpcTouAqywAFppiKetUBBbXwYsYU
1wNr648XVmPmCMCy4rY8vdliFnbMUj086DU6Z+/oXBdWU3/b1G0DN3E9wULRSwcK
ZT3wj/cCI1vsCm3gj2R5SqkA9Y0CAwEAAQKBgAJH+4CxV0/zBVcLiBCHvSANm0l7
HetybTh/j2p0Y1sTXro4ALwAaCTUeqdBjWiLSo9lNwDHFyq8zX90+gNxa7c5EqcW
V9FmlVXr8VhfBzcZo1nXeNdXFT7tQ2yah/odtdcx+vRMSGJd1t/5k5bDd9wAvYdI
DblMAg+wiKKZ5KcdAkEA1cCakEN4NexkF5tHPRrR6XOY/XHfkqXxEhMqmNbB9U34
saTJnLWIHC8IXys6Qmzz30TtzCjuOqKRRy+FMM4TdwJBAJQZFPjsGC+RqcG5UvVM
iMPhnwe/bXEehShK86yJK/g/UiKrO87h3aEu5gcJqBygTq3BBBoH2md3pr/W+hUM
WBsCQQChfhTIrdDinKi6lRxrdBnn0Ohjg2cwuqK5zzU9p/N+S9x7Ck8wUI53DKm8
jUJE8WAG7WLj/oCOWEh+ic6NIwTdAkEAj0X8nhx6AXsgCYRql1klbqtVmL8+95KZ
K7PnLWG/IfjQUy3pPGoSaZ7fdquG8bq8oyf5+dzjE/oTXcByS+6XRQJAP/5ciy1b
L3NhUhsaOVy55MHXnPjdcTX0FaLi+ybXZIfIQ2P4rb19mVq1feMbCXhz+L1rG8oa
t5lYKfpe8k83ZA==
-----END PRIVATE KEY-----"""
        self.sign_keys = "QS9HiIvlxGT3HDFcXpj2M2+DC+yJxR3m/5sIQGLNISEQNSs6z+PzHCtC3IGpey72DBQ8cxLklnOMgqZUgPycruySDW0e7qWyyNlYPMw0Uc6PnSITLVvG8mRA+06QwhRr4qdY7pQfYVfSFd/bfn7d7UmM+SxnSwT+8uqF74r1lK4="

        self.header = {
            'Cache-Control': 'no-cache',
            'Version': '2406025',
            'PackageName': 'com.uf076bf0c246.qe439f0d5e.m8aaf56b725a.ifeb647346f',
            'Ver': '1.9.2',
            'Referer': self.host,
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'okhttp/3.12.0'
        }

        self.cache = OrderedDict()
        self.cache_maxsize = 500
        self.cache_timeout = 300

    def getName(self):
        return self.name

    def init(self, extend=''):
        pass

    def homeContent(self, filter):
        result = {}
        classes = [
            {"type_name": "电影", "type_id": "1"},
            {"type_name": "电视剧", "type_id": "2"},
            {"type_name": "动漫", "type_id": "4"},
            {"type_name": "综艺", "type_id": "3"},
            {"type_name": "短剧", "type_id": "64"}
        ]
        result['class'] = classes

        filters = {}
        for cate in classes:
            tid = cate['type_id']
            filters[tid] = [
                {"key": "area", "name": "地区", "value": [
                    {"n": "全部", "v": "0"}, {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"},
                    {"n": "台湾", "v": "台湾"}, {"n": "美国", "v": "美国"}, {"n": "韩国", "v": "韩国"},
                    {"n": "日本", "v": "日本"}, {"n": "英国", "v": "英国"}, {"n": "法国", "v": "法国"},
                    {"n": "泰国", "v": "泰国"}, {"n": "印度", "v": "印度"}, {"n": "其他", "v": "其他"}
                ]},
                {"key": "year", "name": "年份", "value": [
                    {"n": "全部", "v": "0"}, {"n": "2025", "v": "2025"}, {"n": "2024", "v": "2024"},
                    {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"}, {"n": "2021", "v": "2021"},
                    {"n": "2020", "v": "2020"}, {"n": "2019", "v": "2019"}, {"n": "2018", "v": "2018"},
                    {"n": "2017", "v": "2017"}, {"n": "2016", "v": "2016"}, {"n": "2015", "v": "2015"},
                    {"n": "2014", "v": "2014"}, {"n": "2013", "v": "2013"}, {"n": "2012", "v": "2012"},
                    {"n": "2011", "v": "2011"}, {"n": "2010", "v": "2010"}, {"n": "2009", "v": "2009"},
                    {"n": "2008", "v": "2008"}, {"n": "2007", "v": "2007"}, {"n": "2006", "v": "2006"},
                    {"n": "2005", "v": "2005"}, {"n": "更早", "v": "2004"}
                ]},
                {"key": "sort", "name": "排序", "value": [
                    {"n": "最新", "v": "d_id"}, {"n": "最热", "v": "d_hits"}, {"n": "推荐", "v": "d_score"}
                ]}
            ]
        result['filters'] = filters
        return result

    def homeVideoContent(self):
        return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        videos = []
        try:
            body = {
                "area": extend.get('area', '0'),
                "year": extend.get('year', '0'),
                "pageSize": "30",
                "sort": extend.get('sort', 'd_id'),
                "page": str(pg),
                "tid": tid
            }
            data = self.get_data(body, '/App/IndexList/indexList')
            if data and 'list' in data:
                for item in data['list']:
                    vod_continu = item.get('vod_continu', 0)
                    remarks = '电影' if vod_continu == 0 else f'更新至{vod_continu}集'
                    videos.append({
                        "vod_id": f"{item.get('vod_id', '')}|{vod_continu}",
                        "vod_name": item.get('vod_name', ''),
                        "vod_pic": item.get('vod_pic', ''),
                        "vod_remarks": remarks
                    })
        except Exception:
            logger.exception("获取分类内容失败")
        return {
            'list': videos,
            'page': int(pg),
            'pagecount': 9999,
            'limit': 30,
            'total': 999999
        }

    def detailContent(self, ids):
        try:
            vod_id, vod_continu = ids[0].split('|', 1)
        except ValueError:
            vod_id = ids[0]
            vod_continu = ''

        try:
            t = str(int(time.time()))
            body1 = {
                "token_id": "1649412",
                "vod_id": vod_id,
                "mobile_time": t,
                "token": self.token
            }
            body2 = {
                "vurl_cloud_id": "2",
                "vod_d_id": vod_id
            }

            with ThreadPoolExecutor(max_workers=2) as executor:
                future_q = executor.submit(self.get_data, body1, '/App/IndexPlay/playInfo')
                future_j = executor.submit(self.get_data, body2, '/App/Resource/Vurl/show')
                try:
                    qdata = future_q.result(timeout=10)
                    jdata = future_j.result(timeout=10)
                except TimeoutError:
                    logger.error("获取详情超时")
                    return {'list': []}
                except Exception as e:
                    logger.exception("并发获取详情异常")
                    return {'list': []}

            if not qdata or 'vodInfo' not in qdata:
                return {'list': []}

            vod = qdata['vodInfo']
            video_detail = {
                "vod_id": vod_id,
                "vod_name": vod.get('vod_name', ''),
                "vod_pic": vod.get('vod_pic', ''),
                "vod_year": vod.get('vod_year', ''),
                "vod_area": vod.get('vod_area', ''),
                "vod_actor": vod.get('vod_actor', ''),
                "vod_director": vod.get('vod_director', ''),
                "vod_content": vod.get('vod_use_content', '').strip(),
                "vod_play_from": "瓜子专线"
            }

            play_list = []
            if jdata and 'list' in jdata:
                for index, item in enumerate(jdata['list']):
                    if 'play' in item:
                        names, params = [], []
                        for k, v in item['play'].items():
                            if 'param' in v and v['param']:
                                names.append(k)
                                params.append(v['param'])
                        if params:
                            play_name = str(index + 1) if len(jdata['list']) > 1 else vod.get('vod_name', '')
                            play_url = f"{params[-1]}||{'@'.join(names)}"
                            play_list.append(f"{play_name}${play_url}")

            video_detail["vod_play_url"] = "#".join(play_list)
            return {'list': [video_detail]}

        except Exception:
            logger.exception("获取详情失败")
            return {'list': []}

    def searchContent(self, key, quick, pg=1):
        videos = []
        try:
            body = {
                "keywords": key,
                "order_val": "1",
                "page": str(pg)
            }
            data = self.get_data(body, '/App/Index/findMoreVod', use_cache=False)
            if data and 'list' in data:
                for item in data['list']:
                    vod_continu = item.get('vod_continu', 0)
                    remarks = '电影' if vod_continu == 0 else f'更新至{vod_continu}集'
                    videos.append({
                        "vod_id": f"{item.get('vod_id', '')}|{vod_continu}",
                        "vod_name": item.get('vod_name', ''),
                        "vod_pic": item.get('vod_pic', ''),
                        "vod_remarks": remarks
                    })
        except Exception:
            logger.exception("搜索失败")
        return {
            'list': videos,
            'page': int(pg),
            'pagecount': 9999,
            'limit': 30,
            'total': 999999
        }

    def playerContent(self, flag, id, vipFlags):
        try:
            parts = id.split('||')
            if len(parts) < 2:
                return {"parse": 0, "playUrl": "", "url": ""}
            param_str = parts[0]
            resolutions = parts[1].split('@') if len(parts) > 1 else []

            params = {}
            for pair in param_str.split('&'):
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    params[key] = value

            if resolutions:
                def safe_int(s):
                    try:
                        return int(s)
                    except ValueError:
                        return 0
                resolutions.sort(key=safe_int, reverse=True)
                params['resolution'] = resolutions[0]

                data = self.get_data(params, '/App/Resource/VurlDetail/showOne', use_cache=False)
                if data and 'url' in data:
                    return {
                        "parse": 0,
                        "playUrl": "",
                        "url": data['url'],
                        "header": json.dumps({"User-Agent": "Lavf/57.83.100"})
                    }
            return {"parse": 0, "playUrl": "", "url": ""}
        except Exception:
            logger.exception("播放解析失败")
            return {"parse": 0, "playUrl": "", "url": ""}

    def isVideoFormat(self, url):
        video_formats = ['.m3u8', '.mp4', '.avi', '.mkv', '.flv', '.ts']
        return any(url.lower().endswith(fmt) for fmt in video_formats)

    def manualVideoCheck(self):
        pass

    def localProxy(self, params):
        return None

    def aes_encrypt(self, text):
        try:
            cipher = AES.new(self.aes_key.encode('utf-8'), AES.MODE_CBC, self.aes_iv.encode('utf-8'))
            encrypted = cipher.encrypt(pad(text.encode('utf-8'), AES.block_size))
            return encrypted.hex().upper()
        except Exception:
            logger.exception("AES加密失败")
            return ""

    def aes_decrypt(self, hex_text, key, iv):
        try:
            cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
            decrypted = unpad(cipher.decrypt(bytes.fromhex(hex_text)), AES.block_size)
            return decrypted.decode('utf-8')
        except Exception:
            logger.exception("AES解密失败")
            return ""

    def rsa_decrypt(self, encrypted_data):
        try:
            encrypted_bytes = base64.b64decode(encrypted_data)
            rsa_key = RSA.import_key(self.rsa_private_key)
            cipher = PKCS1_v1_5.new(rsa_key)
            decrypted = cipher.decrypt(encrypted_bytes, None)
            return decrypted.decode('utf-8') if decrypted else ""
        except Exception:
            logger.exception("RSA解密失败")
            return ""

    def _generate_sign(self, request_key, timestamp):
        sign_str = (
            f"token_id=,token={self.token},phone_type=1,"
            f"request_key={request_key},app_id=1,time={timestamp},"
            f"keys={self.sign_keys}*&zvdvdvddbfikkkumtmdwqppp?|4Y!s!2br"
        )
        return hashlib.md5(sign_str.encode()).hexdigest()

    def _cache_cleanup(self):
        now = time.time()
        expired = [k for k, (_, ts) in self.cache.items() if now - ts > self.cache_timeout]
        for k in expired:
            del self.cache[k]
        while len(self.cache) > self.cache_maxsize:
            self.cache.popitem(last=False)

    def get_data(self, data, path, use_cache=True):
        cache_key = None
        if use_cache:
            raw = json.dumps(data, sort_keys=True)
            cache_key = f"{path}:{hashlib.md5(raw.encode()).hexdigest()}"
            self._cache_cleanup()
            if cache_key in self.cache:
                cached_result, timestamp = self.cache[cache_key]
                if time.time() - timestamp < self.cache_timeout:
                    return cached_result

        try:
            start_time = time.time()

            request_key = self.aes_encrypt(json.dumps(data))
            if not request_key:
                return None

            timestamp = str(int(time.time()))
            signature = self._generate_sign(request_key, timestamp)

            body = {
                'token': self.token,
                'token_id': '',
                'phone_type': '1',
                'time': timestamp,
                'phone_model': 'xiaomi-22021211rc',
                'keys': self.sign_keys,
                'request_key': request_key,
                'signature': signature,
                'app_id': '1',
                'ad_version': '1'
            }

            url = f"{self.host}{path}"
            response = self.post(url, headers=self.header, data=body, timeout=10)
            if response.status_code != 200:
                logger.error(f"API请求失败: {response.status_code}, 路径: {path}")
                return None

            try:
                response_data = response.json()
            except ValueError:
                logger.error(f"响应非JSON格式, 路径: {path}")
                return None

            if 'data' not in response_data:
                logger.error(f"API返回数据缺少'data'字段, 路径: {path}")
                return None

            data_resp = response_data['data']

            bodyki_json = self.rsa_decrypt(data_resp['keys'])
            if not bodyki_json:
                logger.error("RSA解密响应密钥失败")
                return None
            bodyki = json.loads(bodyki_json)

            decrypted = self.aes_decrypt(data_resp['response_key'], bodyki['key'], bodyki['iv'])
            if not decrypted:
                logger.error("AES解密响应数据失败")
                return None
            result = json.loads(decrypted)

            elapsed = time.time() - start_time
            logger.info(f"数据获取成功, 耗时: {elapsed:.2f}s, 路径: {path}")

            if use_cache and cache_key:
                self.cache[cache_key] = (result, time.time())
                self.cache.move_to_end(cache_key)
                self._cache_cleanup()

            return result

        except Exception:
            logger.exception(f"获取数据异常, 路径: {path}")
            return None

    def get_md5(self, text):
        return hashlib.md5(text.encode()).hexdigest()


if __name__ == '__main__':
    pass