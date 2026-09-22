# coding = utf-8
#!/usr/bin/python
import re
import sys
import json
import time
import base64
import hashlib
import random
import string
import urllib.parse
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from base.spider import Spider

sys.path.append('..')

class Spider(Spider):
    def __init__(self):
        self.name = "瓜子"
        self.hosts = [
            'https://apinew.uozvr.com',
            'https://api.w32z7vtd.com',
            'https://api.6a7nnf7.com',
            'https://api.umygrx3.com',
            'https://api.rmedphk.com',
            'https://apinew.qksov.com',
            'https://apinew.qwepe.com',
            'https://gzapi.45366fut.com',
            'https://gzapi.n55zw7th.com',
            'https://gzapi.tt9butrf.com',
            'https://gzapi.unggfd5u.com',
            'https://api.27yyukw.com',
            'https://api.2xvd33x.com',
            'https://api.wsz9yan.com'
        ]
        self.host_index = 0
        self.host = self.hosts[self.host_index]

        # AES 固定密钥（与Java版一致）
        self.AES_KEY = 'OITxa5OqAYjhswxx'
        self.AES_IV = 'rCMNwZASNBKZ8mXV'

        # RSA 公钥/私钥
        self.RSA_PUBLIC_KEY = "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDUM5+/y8sPsWkd1/RQS64X259EUwxFXFE5HlA65MqrxnPs0JqoSRojSDy5QhwvROlaD6TwRQHKMY2OAZ6SnQeUJsChTEFIR9qUkwrs3/MVUMxjsv6JS6Oe/juclyJGTgVmDhB55EafXsD0SQYVj/QXXsxR6ewR5E2kL52yAAD4yQIDAQAB"
        self.RSA_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
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
-----END RSA PRIVATE KEY-----"""

        self.DEVICE_OLD_KEY = "aLFBMWpxBrIDAD1Si/KVvm41"

        # 设备信息（随机生成）
        self.deviceId = str(864150060000000 + random.randint(0, 9999))
        self.deviceKey = ''.join(random.choices('0123456789ABCDEF', k=40))  # 20字节hex大写
        self.token = ""
        self.token_id = ""
        self.registered = False

        self.header = {
            'User-Agent': 'Lavf/57.83.100',
            'code': 'GZ0369',
            'deviceId': self.deviceId,
            'lang': 'zh_cn',
            'Cache-Control': 'no-cache',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Version': '2604028',
            'PackageName': 'com.ae06aebdbb.y286327f5a.ofe849883320260517',
            'Ver': '3.0.3.2',
            'api-ver': '3.0.3.2',
            'Referer': self.host
        }

        self.cache = {}
        self.cache_timeout = 300
        self._authed = False
        # token 懒加载: 不在构造内联网, 首次业务请求时 ensure_token() 自动注册

    def getName(self):
        return self.name

    def init(self, extend=''):
        pass

    def destroy(self):
        pass

    # ---------- 设备注册与认证 ----------
    def init_token(self):
        """初始化token：注册设备 -> 刷新(已废弃，保留兼容；新逻辑走 ensure_token 懒加载)"""
        print("===== 初始化设备认证 =====")
        try:
            if not self.registered:
                self.sign_up()
            # 刷新获取最终token
            self.refresh_token()
        except Exception as e:
            # 不再写入硬编码兜底 token，避免用过期 token 掩盖 502 真因
            print(f"初始化token失败: {e}")

    def sign_up(self):
        """注册设备"""
        print("注册新设备...")
        params = {
            "new_key": self.deviceKey,
            "old_key": self.DEVICE_OLD_KEY,
            "phone_type": 1,
            "code": ""
        }
        result = self._auth_request('/App/Authentication/Device/signUp', params)
        if not result:
            raise Exception("注册设备无响应(服务端502/网络不通)")
        self._apply_auth(result)
        self.registered = True

    def sign_in(self):
        """登录设备"""
        print("设备登录...")
        params = {
            "new_key": self.deviceKey,
            "old_key": self.DEVICE_OLD_KEY
        }
        result = self._auth_request('/App/Authentication/Device/signIn', params)
        if not result:
            raise Exception("设备登录无响应(服务端502/网络不通)")
        self._apply_auth(result)

    def _apply_auth(self, result):
        """从认证响应中提取token"""
        if not isinstance(result, dict):
            raise Exception("认证失败，无token返回: {}".format(result))
        new_token = result.get('token', '')
        if not new_token:
            raise Exception("认证失败，无token返回: {}".format(result))
        self.token = new_token
        new_token_id = result.get('app_user_id', '')
        if new_token_id:
            self.token_id = new_token_id
        print(f"获取token成功, token前缀: {self.token[:30]}...")

    def refresh_token(self):
        """刷新token"""
        print("刷新token...")
        result = self._auth_request('/App/Authentication/Authenticator/refresh', {})
        if not result:
            raise Exception("刷新token无响应(服务端502/网络不通)")
        self._apply_auth(result)
        self._authed = True

    def _auth_request(self, path, params):
        """认证类请求（不需要ensure_token）"""
        return self._send_encrypted_request(params, path, is_auth=True)

    # ---------- 业务请求核心（修复加密与签名） ----------
    def ensure_token(self):
        """确保token有效，懒加载：首次业务请求时才联网注册"""
        if self._authed and self.token and self.token_id:
            return
        if not self.token or not self.token_id:
            if self.registered:
                self.sign_in()
            else:
                self.sign_up()
            self.refresh_token()

    def _send_encrypted_request(self, data, path, is_auth=False):
        """
        发送加密请求，返回解密后的字典
        :param data: 业务参数字典
        :param path: 请求路径
        :param is_auth: 是否为认证类请求（signUp/signIn/refresh），此时不使用ensure_token
        """
        try:
            if not is_auth:
                self.ensure_token()

            # 1. 将参数转为JSON并AES加密
            json_params = json.dumps(data)
            encrypted = self.aes_encrypt(json_params, self.AES_KEY, self.AES_IV)
            request_key = encrypted.upper()  # Java中是bytesToHex(encrypted).toUpperCase()

            # 2. 生成keys (RSA加密 iv/key JSON)
            key_json = json.dumps({"iv": self.AES_IV, "key": self.AES_KEY})
            keys = self.rsa_encrypt(key_json, self.RSA_PUBLIC_KEY)
            if not keys:
                raise Exception("RSA加密失败，无法生成keys")

            # 3. 生成签名
            t = str(int(time.time()))
            sign_str = f"token_id=,token={self.token},phone_type=1,request_key={request_key},app_id=1,time={t},keys={keys}*&zvdvdvddbfikkkumtmdwqppp?|4Y!s!2br"
            signature = self.get_md5(sign_str)  # 已改为大写

            # 4. 构建请求体
            body = {
                'token': self.token,
                'token_id': '',
                'phone_type': '1',
                'time': t,
                'phone_model': 'xiaomi-25031',  # 与Java版保持一致
                'keys': keys,
                'request_key': request_key,
                'signature': signature,
                'app_id': '1',
                'ad_version': '1'
            }

            # 5. 发送请求
            url = f"{self.host}{path}"
            response = self.post(url, headers=self.header, data=body, timeout=10)

            if response.status_code != 200:
                # 502 网关HTML会走到这里，避免 response.json() 抛错掩盖状态码
                raise Exception(f"HTTP {response.status_code} body={response.text[:200]!r}")

            try:
                resp_json = response.json()
            except Exception as je:
                raise Exception(f"响应非JSON(疑似502网关页): {response.text[:200]!r} err={je}")

            # 检查业务code（若不为200可能token过期）
            if 'code' in resp_json and resp_json['code'] != 200:
                print(f"业务错误码: {resp_json['code']}, 信息: {str(resp_json)[:500]}")
                # 如果不是认证请求，尝试重新获取token后重试一次（这里简单处理，外层get_data已有重试）
                raise Exception("业务错误")

            data_section = resp_json.get('data')
            if not data_section:
                raise Exception("响应缺少data字段")

            encrypted_response = data_section.get('response_key', '')
            encrypted_keys = data_section.get('keys', '')
            if not encrypted_response or not encrypted_keys:
                raise Exception("响应缺少response_key/keys字段")

            # 6. 解密响应
            decrypted_keys_json = self.rsa_decrypt(encrypted_keys, self.RSA_PRIVATE_KEY)
            if not decrypted_keys_json:
                raise Exception("响应keys解密失败(内置私钥与服务端公钥不匹配)")
            try:
                key_info = json.loads(decrypted_keys_json)
            except Exception as je:
                raise Exception(f"keys JSON解析失败: {decrypted_keys_json[:200]!r} err={je}")
            resp_key = key_info.get('key', '')
            resp_iv = key_info.get('iv', '')
            if not resp_key or not resp_iv:
                raise Exception(f"keys缺少key/iv: {key_info}")
            decrypted_data = self.aes_decrypt(encrypted_response, resp_key, resp_iv)
            if not decrypted_data:
                raise Exception("响应体AES解密失败")
            return json.loads(decrypted_data)

        except Exception as e:
            print(f"请求失败 [{path}]: {e}")
            return None

    def get_data(self, data, path, use_cache=True):
        """带重试和域名轮询的数据获取（保持原框架）。
        注意：认证类路径(signUp/signIn/refresh)由 _auth_request 直调 _send_encrypted_request，
        不走本方法，因此这里不再触发 ensure_token，避免 signUp 失败时无限递归。"""
        try:
            cache_key = f"{path}_{hash(str(data))}" if use_cache else None
            if use_cache and cache_key in self.cache:
                cached_data, timestamp = self.cache[cache_key]
                if time.time() - timestamp < self.cache_timeout:
                    return cached_data

            for attempt in range(3):
                tried = 0
                while tried < len(self.hosts):
                    self.host = self.hosts[self.host_index]
                    self.header['Referer'] = self.host
                    result = self._send_encrypted_request(data, path)
                    if result is not None:
                        print(f"请求成功: {path}, 域名: {self.host}")
                        if use_cache and cache_key:
                            self.cache[cache_key] = (result, time.time())
                        return result

                    # 切换到下一个域名
                    self.host_index = (self.host_index + 1) % len(self.hosts)
                    tried += 1

                # 所有域名失败，尝试重新认证并重试
                if attempt < 2:
                    print("所有域名失败，尝试重新认证...")
                    try:
                        self.ensure_token()
                    except:
                        pass
                    self.host_index = 0
                else:
                    break
            return None
        except Exception as e:
            print(f"get_data异常: {e}")
            return None

    # ---------- 加解密工具 ----------
    def aes_encrypt(self, text, key, iv):
        try:
            key_bytes = key.encode('utf-8')
            iv_bytes = iv.encode('utf-8')
            cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
            encrypted = cipher.encrypt(pad(text.encode('utf-8'), AES.block_size))
            return encrypted.hex().upper()
        except Exception as e:
            print(f"AES加密失败: {e}")
            return ""

    def aes_decrypt(self, text, key, iv):
        try:
            key_bytes = key.encode('utf-8')
            iv_bytes = iv.encode('utf-8')
            cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
            encrypted_bytes = bytes.fromhex(text)
            decrypted = unpad(cipher.decrypt(encrypted_bytes), AES.block_size)
            return decrypted.decode('utf-8')
        except Exception as e:
            print(f"AES解密失败: {e}")
            return ""

    def rsa_encrypt(self, text, public_key_str):
        """RSA公钥加密（PKCS1v1.5）"""
        try:
            key = RSA.import_key("-----BEGIN PUBLIC KEY-----\n" + public_key_str + "\n-----END PUBLIC KEY-----")
            cipher = PKCS1_v1_5.new(key)
            encrypted = cipher.encrypt(text.encode('utf-8'))
            return base64.b64encode(encrypted).decode('utf-8')
        except Exception as e:
            print(f"RSA加密失败: {e}")
            return ""

    def rsa_decrypt(self, encrypted_data, private_key_str):
        """RSA私钥解密(服务端keys字段返回的响应密钥)。
        注意：内置 RSA_PRIVATE_KEY 与 RSA_PUBLIC_KEY 并非同一对(经 openssl/pycryptodome 双重验证)，
        故服务端用公钥加密的 keys 无法用内置私钥解出 —— 这是服务端502之外的第二处致命伤。
        此处如解密失败返回空串，由调用方判空后抛错，避免 json.loads('') 掩盖根因。"""
        try:
            encrypted_bytes = base64.b64decode(encrypted_data)
            rsa_key = RSA.import_key(private_key_str)
            cipher = PKCS1_v1_5.new(rsa_key)
            decrypted = cipher.decrypt(encrypted_bytes, None)
            if not decrypted:
                print("RSA解密失败: 私钥与服务端公钥不匹配(内置密钥对不一致)")
                return ""
            return decrypted.decode('utf-8')
        except Exception as e:
            print(f"RSA解密失败: {e}")
            return ""

    def get_md5(self, text):
        return hashlib.md5(text.encode()).hexdigest().upper()  # 与Java一致大写

    # ---------- 业务方法（不变） ----------
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
            extend = extend or {}
            body = {
                "area": extend.get('area', '0'),
                "year": extend.get('year', '0'),
                "pageSize": "30",
                "sort": extend.get('sort', 'd_id'),
                "page": str(pg),
                "tid": tid
            }
            cache_key = f"category_{tid}_{pg}_{hash(str(body))}"
            data = self.get_cached_data(cache_key, body, '/App/IndexList/indexList')
            if data and 'list' in data:
                for item in data['list']:
                    vod_continu = item.get('vod_continu', 0)
                    remarks = '电影' if vod_continu == 0 else f'更新至{vod_continu}集'
                    video = {
                        "vod_id": f"{item.get('vod_id', '')}/{vod_continu}",
                        "vod_name": item.get('vod_name', ''),
                        "vod_pic": item.get('vod_pic', ''),
                        "vod_remarks": remarks
                    }
                    videos.append(video)
        except Exception as e:
            print(f"获取分类内容失败: {e}")
        return {'list': videos, 'page': int(pg), 'pagecount': 9999, 'limit': 30, 'total': 999999}

    def detailContent(self, ids):
        try:
            if not ids:
                return {'list': []}
            vod_id = ids[0].split('/')[0]
            t = str(int(time.time()))
            body1 = {"token_id": self.token_id, "vod_id": vod_id, "mobile_time": t, "token": self.token}
            qdata = self.get_data(body1, '/App/IndexPlay/playInfo')
            body2 = {"vurl_cloud_id": "2", "vod_d_id": vod_id}
            jdata = self.get_data(body2, '/App/Resource/Vurl/show')
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
                "vod_play_from": "瓜子影视"
            }
            play_list = []
            if jdata and 'list' in jdata:
                for index, item in enumerate(jdata['list']):
                    if 'play' in item:
                        n, p = [], []
                        for key, value in item['play'].items():
                            if 'param' in value and value['param']:
                                n.append(key)
                                p.append(value['param'])
                        if p:
                            play_name = str(index + 1) if len(jdata['list']) != 1 else vod.get('vod_name', '')
                            play_url = f"{p[-1]}||{'@'.join(n)}"
                            play_list.append(f"{play_name}${play_url}")
            video_detail["vod_play_url"] = "#".join(play_list)
            return {'list': [video_detail]}
        except Exception as e:
            print(f"获取详情失败: {e}")
            return {'list': []}

    def searchContent(self, key, quick, pg=1):
        videos = []
        try:
            body = {"keywords": key, "order_val": "1", "page": str(pg)}
            data = self.get_data(body, '/App/Index/findMoreVod', use_cache=False)
            if data and 'list' in data:
                for item in data['list']:
                    vod_continu = item.get('vod_continu', 0)
                    remarks = '电影' if vod_continu == 0 else f'更新至{vod_continu}集'
                    videos.append({
                        "vod_id": f"{item.get('vod_id', '')}/{vod_continu}",
                        "vod_name": item.get('vod_name', ''),
                        "vod_pic": item.get('vod_pic', ''),
                        "vod_remarks": remarks
                    })
        except Exception as e:
            print(f"搜索失败: {e}")
        return {'list': videos, 'page': int(pg), 'pagecount': 9999, 'limit': 30, 'total': 999999}

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
                resolutions.sort(key=lambda x: int(x) if x.isdigit() else 0, reverse=True)
                params['resolution'] = resolutions[0]
                data = self.get_data(params, '/App/Resource/VurlDetail/showOne', use_cache=False)
                if data and 'url' in data:
                    return {"parse": 0, "playUrl": "", "url": data['url'],
                            "header": {"User-Agent": "Lavf/57.83.100", "Referer": "http://WJiZxLXA2.com/"}, 'danmaku': 'http://127.0.0.1:9978/proxy?do=diydanmu'}
            return {"parse": 0, "playUrl": "", "url": ""}
        except Exception as e:
            print(f"播放解析失败: {e}")
            return {"parse": 0, "playUrl": "", "url": ""}

    def isVideoFormat(self, url):
        video_formats = ['.m3u8', '.mp4', '.avi', '.mkv', '.flv', '.ts']
        return any(url.lower().endswith(fmt) for fmt in video_formats)

    def manualVideoCheck(self):
        pass

    def localProxy(self, params):
        return None

    def get_cached_data(self, cache_key, data, path):
        current_time = time.time()
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if current_time - timestamp < self.cache_timeout:
                return cached_data
        result = self.get_data(data, path)
        if result:
            self.cache[cache_key] = (result, current_time)
        return result

if __name__ == '__main__':
    pass