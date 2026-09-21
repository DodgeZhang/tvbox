# -*- coding: utf-8 -*-
# 本资源来源于互联网公开渠道，仅可用于个人学习爬虫技术。
# 严禁将其用于任何商业用途，下载后请于 24 小时内删除，搜索结果均来自源站，本人不承担任何责任。

import sys,random,urllib3
from base.spider import Spider
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.path.append('..')

class Spider(Spider):
    headers,host,pic_domain = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 12; SM-S9080 Build/V417IR; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/101.0.4951.61 Safari/537.36;webank/h5face;webank/1.0;netType:NETWORK_WIFI;appVersion:815;packageName:com.jp3.pluginxg3',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Encoding': 'gzip, deflate',
        'x-requested-with': 'com.jp3.pluginxg3',
        'sec-fetch-site': 'cross-site',
        'sec-fetch-mode': 'cors',
        'sec-fetch-dest': 'empty',
        'accept-language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7'
    },'',''

    def init(self, extend=''):
        try:
            dns_name = 'swrdsfeiujo25sw.cc'
            response = self.fetch(f'https://dns.alidns.com/resolve?name={dns_name}&type=16', headers={**self.headers,'Accept':'application/dns-json'} ,verify=False).json()
            answer = response['Answer'][0]['data']
            domamins = answer.replace('"', '').split(',')
            random_string = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=6))
            for domain in domamins:
                try:
                    host = f'https://{random_string}.{domain}'
                    appAuthConfig = self.fetch(f'{host}/api/appAuthConfig',headers=self.headers ,verify=False).json()
                    self.host = host
                except Exception:
                    continue
                pic_domain = appAuthConfig['data']['imgDomain'].strip()
                if not pic_domain.startswith('http'): pic_domain = f"https://{pic_domain}"
                self.pic_domain = pic_domain
                break
        except Exception:
            self.host = ''

    def homeContent(self, filter):
        try:
            res = self.fetch(f'{self.host}/api/term/home_fenlei',headers=self.headers ,verify=False).json()
            classes = []
            tj_id = 88
            for i in res['data']:
                if i['name'] == '推荐':
                    tj_id = i['id']
                else:
                    classes.append({'type_id': i['id'], 'type_name': i['name']})
            res2 = self.fetch(f'{self.host}/api/dyTag/list?category_id={tj_id}', headers=self.headers ,verify=False).json()
            videos = []
            for category in res2['data']:
                videos.extend(self.arr2vods(category['dataList']))
            return {"class": classes,"list": videos}
        except Exception:
            return None

    def categoryContent(self, tid, pg, filter, ext):
        videos = []
        if  tid == '99':
            if str(pg) == '2': return
            res = self.fetch(f'{self.host}/api/dyTag/list?category_id={tid}', headers=self.headers, verify=False).json()
            for i in res['data']:
                videos.extend(self.arr2vods(i.get('dataList',[]), tid))
        else:
            if tid == '67':
                path = f'/api/crumb/shortList?fcate_pid={tid}&category_id=&sort=&page={pg}'
            else:
                path = f'/api/crumb/list?fcate_pid={tid}&category_id=&area=&year=&type=&sort=&page={pg}'
            res = self.fetch(f'{self.host}{path}', headers=self.headers ,verify=False).json()
            videos.extend(self.arr2vods(res['data'], tid))
        return {'list': videos, 'page': pg}

    def searchContent(self, key, quick, pg='1'):
        res = self.fetch(f'{self.host}/api/v2/search/videoV2?key={key}&page={pg}&pageSize=20', headers=self.headers ,verify=False).json()
        videos = self.arr2vods(res['data'])
        return {'list': videos, 'page': pg, 'total': res['total']}

    def detailContent(self, ids):
        tid, vid = ids[0].split('@',1)
        show, play_urls = [], []
        if tid == '67':
            res = self.fetch(f'{self.host}/api/detail?token=&vid={vid}', headers=self.headers ,verify=False).json()
            data = res['data']
            name = ''
            for i in data['playlist']:
                if not name: name  = i.get('source_config_name')
                play_urls.append(f"{i['title']}${i['url']}")
            if not name: name = '荐片'
            show.append(name)
            img_url = data.get('thumbnail', data.get('cover_image', data.get('path', '')))
            video = {
                'vod_id': ids[0],
                'vod_name': data['title'],
                'vod_pic': self.pic(img_url),
                'vod_remarks': data.get('mask'),
                'vod_year': data.get('year'),
                'type_name': ','.join(k['name'] for k in data.get('types',[])) or None,
                'vod_actor': ','.join(k['name'] for k in data.get('actors',[])) or None,
                'vod_director': ','.join(k['name'] for k in data.get('directors',[])) or None,
                'vod_area': ','.join(k['title'] for k in data.get('category',[])) or None,
                'vod_content': data.get('description'),
                'vod_play_from': '$$$'.join(show),
                'vod_play_url': '#'.join(play_urls)
            }
        else:
            res = self.fetch(f'{self.host}/api/video/detailv2?id={vid}', headers=self.headers ,verify=False).json()
            data = res['data']
            for i in data['source_list_source']:
                urls = []
                for j in i['source_list']:
                    urls.append(f"{j.get('source_name',j.get('weight'))}${j['url']}")
                play_urls.append('#'.join(urls))
                show.append(i['name'])
            img_url = data.get('thumbnail', data.get('cover_image', data.get('path', '')))
            video = {
                'vod_id': ids[0],
                'vod_name': data['title'],
                'vod_pic': self.pic(img_url),
                'vod_remarks': data['mask'],
                'vod_year': data['year'],
                'type_name': ','.join(k['name'] for k in data['types']),
                'vod_actor': ','.join(k['name'] for k in data['actors']),
                'vod_director': ','.join(k['name'] for k in data['directors']),
                'vod_area': ','.join(k['title'] for k in data['category']),
                'vod_content': data['description'],
                'vod_play_from': '$$$'.join(show),
                'vod_play_url': '$$$'.join(play_urls)
            }
        return {'list': [video]}

    def playerContent(self, flag, url, vip_flags):
        headers = {
            'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 15)",
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'token': ""
        }
        return {'parse': 0, 'jx': 0, 'url': url, 'header': headers}

    def arr2vods(self, arr, tid=None):
        videos = []
        for i in arr:
            img_url = i.get('thumbnail', i.get('cover_image', i.get('path', '')))
            videos.append({
                'vod_id': f"{tid or i.get('top_category', {}).get('id') or i.get('source_type') or i.get('definition') or 'Unknown'}@{i['id']}",
                'vod_name': i['title'],
                'vod_pic': self.pic(img_url),
                'vod_remarks': i.get('mask'),
                'vod_year': i.get('score'),
            })
        return videos

    def pic(self,url):
        if isinstance(url,str) and not url.startswith(('http:', 'https:')):
            url = self.pic_domain + url
        return url

    def homeVideoContent(self):
        pass

    def localProxy(self, params):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def getName(self):
        pass