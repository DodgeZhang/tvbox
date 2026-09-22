# coding = utf-8
#!/usr/bin/python

from Crypto.Util.Padding import unpad
from Crypto.Util.Padding import pad
from urllib.parse import unquote
from Crypto.Cipher import ARC4
from urllib.parse import quote
from base.spider import Spider
from Crypto.Cipher import AES
from datetime import datetime
from bs4 import BeautifulSoup
from base64 import b64decode
import urllib.request
import urllib.parse
import datetime
import binascii
import requests
import base64
import json
import time
import sys
import re
import os

sys.path.append('..')

xurl = "https://api.bilibili.com"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0',
    'Referer':'https://search.bilibili.com',
    'cookie':'bili_ticket=eyJhbGciOiJIUzI1NiIsImtpZCI6InMwMyIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NDgxODAyOTMsImlhdCI6MTc0NzkyMTAzMywicGx0IjotMX0.ZfghPjVRcNtRwu_40_NbkLYZYaZd2r5YgjGNjPy4MV8'
          }
headerx = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0',
    'Referer': 'https://www.bilibili.com',
}

pm = ''


class Spider(Spider):
    global xurl
    global headerx
    global headers

    def getName(self):
        return "B站影视"

    def init(self, extend):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def homeContent(self, filter):
        result = {}
        result = {"class": [
            {"type_id": "热门", "type_name": "热门"},
            {"type_id": "8K", "type_name": "8K"},
            {"type_id": "12K", "type_name": "12K"},
            {"type_id": "演唱会", "type_name": "演唱会"},
            {"type_id": "纪录片", "type_name": "纪录片"},
            {"type_id": "美食", "type_name": "美食"},
            {"type_id": "食谱", "type_name": "食谱"},
            {"type_id": "体育", "type_name": "体育"},
            {"type_id": "球星", "type_name": "球星"},
            {"type_id": "旅游出行", "type_name": "旅游出行"},
            {"type_id": "风景", "type_name": "风景"},
            {"type_id": "电影", "type_name": "电影"},
            {"type_id": "电视剧", "type_name": "电视剧"},
            {"type_id": "综艺", "type_name": "综艺"},
            {"type_id": "番剧", "type_name": "番剧"},
            {"type_id": "国创", "type_name": "国创"},
            {"type_id": "沙雕动漫", "type_name": "沙雕动漫"},
            {"type_id": "沙雕动画", "type_name": "沙雕动画"},
            {"type_id": "短剧", "type_name": "短剧"},
            {"type_id": "影视", "type_name": "影视"},
            {"type_id": "娱乐", "type_name": "娱乐"},
            {"type_id": "舞蹈", "type_name": "舞蹈"},
            {"type_id": "小剧场", "type_name": "小剧场"},
            {"type_id": "动画", "type_name": "动画"},
            {"type_id": "直播", "type_name": "直播"},
            {"type_id": "音乐", "type_name": "音乐"},
            {"type_id": "MV", "type_name": "MV"},
            {"type_id": "舞曲", "type_name": "舞曲"},
            {"type_id": "教育", "type_name": "教育"},
            {"type_id": "游戏", "type_name": "游戏"},
            {"type_id": "生活", "type_name": "生活"},
            {"type_id": "说案", "type_name": "说案"},
            {"type_id": "演讲", "type_name": "演讲"},
            {"type_id": "知名up主", "type_name": "知名up主"},
            {"type_id": "探索发现", "type_name": "探索发现"},
            {"type_id": "鬼畜", "type_name": "鬼畜"},
            {"type_id": "搞笑", "type_name": "搞笑"},
            {"type_id": "儿童", "type_name": "儿童"},
            {"type_id": "动物世界", "type_name": "动物世界"},
            {"type_id": "相声", "type_name": "相声"},
            {"type_id": "小品", "type_name": "小品"},
            {"type_id": "戏曲", "type_name": "戏曲"},
            {"type_id": "解说", "type_name": "解说"},
            {"type_id": "健身", "type_name": "健身"},
            {"type_id": "小姐姐", "type_name": "小姐姐"},
            {"type_id": "荒野求生", "type_name": "荒野求生"},
            {"type_id": "帕梅拉", "type_name": "帕梅拉"},
            {"type_id": "资讯", "type_name": "资讯"},
            {"type_id": "汽车", "type_name": "汽车"},
            {"type_id": "时尚美妆", "type_name": "时尚美妆"},
            {"type_id": "户外", "type_name": "户外"},
            {"type_id": "家装房产", "type_name": "家装房产"},
            {"type_id": "科技数码", "type_name": "科技数码"},
            {"type_id": "白噪音", "type_name": "白噪音"},
            {"type_id": "软件教程", "type_name": "软件教程"},
            {"type_id": "windows", "type_name": "windows"}
        ]}
        return result

    def homeVideoContent(self):
        pass

    def format_views(self, num):
        if num >= 10000:
            return f"{num / 10000:.1f}万"
        else:
            return str(num)

    def format_number(self, num):
        """格式化数字显示"""
        try:
            num = int(num)
            if num >= 100000000:
                return f"{num / 100000000:.1f}亿"
            elif num >= 10000:
                return f"{num / 10000:.1f}万"
            else:
                return str(num)
        except:
            return str(num)

    def categoryContent(self, cid, pg, filter, ext):
        result = {}
        videos = []
        
        # 直接使用cid作为搜索关键词，不映射
        keyword = cid
        
        url = f'{xurl}/x/web-interface/wbi/search/type?search_type=video&__refresh__=true&page={pg}&page_size=42&keyword={keyword}'
        res = requests.get(url=url, headers=headers)
        res.encoding = "utf-8"
        kjson = json.loads(res.text)
        for i in kjson['data']['result']:
            if str(i['bvid']) == '':
                continue
            id = str(i['bvid'])
            name = i['title']
            pic = i['pic']
            if 'http' not in pic:
                pic = 'http:' + pic
            else:
                pic = pic
            remark = i['play']
            num_str = str(remark).strip()

            num = float(num_str)
            if num >= 100_000_000:
                remarks = f"{num / 100_000_000:.1f}亿播放量"
            elif num >= 10_000:
                remarks = f"{num / 10_000:.1f}万播放量"
            else:
                remarks = f"{num:.1f}播放量"

            video = {
                "vod_id": id,
                "vod_name": name.replace('<em class="keyword">', '').replace('</em>', ''),
                "vod_pic": pic,
                "vod_remarks": remarks
            }
            videos.append(video)

        result['list'] = videos
        result['page'] = pg
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        return result

    def detailContent(self, ids):
        result = {}
        videos = []
        did = ids[0]
        url = f'https://www.bilibili.com/video/{did}'
        res = requests.get(url=url, headers=headerx)
        res.encoding = "utf-8"
        res_text = res.text

        start_str, end_str = 'window.__INITIAL_STATE__=', '}};'
        s_idx = res_text.find(start_str)
        if s_idx > -1:
            s_idx += len(start_str)
            e_idx = res_text.find(end_str, s_idx)
            if e_idx > -1:
                kjson_text = res_text[s_idx:e_idx] + '}}'
        kjson = json.loads(kjson_text)

        video_data = kjson.get('videoData', {})
        name = video_data.get('title', '未知标题')
        remarks = video_data.get('tname', '')
        director = video_data.get('owner', {}).get('name', '未知作者')
        content = video_data.get('desc', '')
        
        # 获取更多视频信息
        stat = video_data.get('stat', {})
        view_count = stat.get('view', 0)  # 播放量
        danmaku_count = stat.get('danmaku', 0)  # 弹幕数
        reply_count = stat.get('reply', 0)  # 评论数
        favorite_count = stat.get('favorite', 0)  # 收藏数
        coin_count = stat.get('coin', 0)  # 硬币数
        share_count = stat.get('share', 0)  # 分享数
        like_count = stat.get('like', 0)  # 点赞数
        
        # 格式化时间
        pubdate = video_data.get('pubdate', 0)
        if pubdate:
            pub_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(pubdate))
        else:
            pub_time = "未知时间"
        
        # 获取UP主信息
        owner = video_data.get('owner', {})
        up_name = owner.get('name', '')
        up_face = owner.get('face', '')
        up_mid = owner.get('mid', '')
        
        # 构建详细信息内容
        detail_info = f"视频简介：{content}\n\n"
        detail_info += f"▷ 播放量：{self.format_number(view_count)}\n"
        detail_info += f"▷ 弹幕数：{self.format_number(danmaku_count)}\n"
        detail_info += f"▷ 点赞数：{self.format_number(like_count)}\n"
        detail_info += f"▷ 投币数：{self.format_number(coin_count)}\n"
        detail_info += f"▷ 收藏数：{self.format_number(favorite_count)}\n"
        detail_info += f"▷ 评论数：{self.format_number(reply_count)}\n"
        detail_info += f"▷ 分享数：{self.format_number(share_count)}\n"
        detail_info += f"▷ 发布时间：{pub_time}\n"
        detail_info += f"▷ UP主：{up_name}\n"
        detail_info += f"▷ 分区：{remarks}\n"
        
        # 构建封面图片（如果有的话）
        pic_url = video_data.get('pic', '')
        if pic_url and 'http' not in pic_url:
            pic_url = 'http:' + pic_url

        play_url = ""
        # 处理多P视频
        available_video_list = kjson.get('availableVideoList', [])
        if available_video_list and len(available_video_list) > 0:
            for i in available_video_list[0]['list']:
                play_url += i['title'] + '$' + f'https://www.bilibili.com/video/{did}?p=' + str(i['p']) + '#'
            play_url = play_url[:-1]
        else:
            # 单P视频
            play_url = f"正片$https://www.bilibili.com/video/{did}"

        # 获取相关推荐视频
        related_play_url = ""
        aid = video_data.get('aid', '')
        if aid:
            try:
                # 使用B站相关推荐API
                related_api = f"https://api.bilibili.com/x/web-interface/archive/related?aid={aid}"
                related_res = requests.get(related_api, headers=headerx).json()
                
                if related_res.get("code") == 0:
                    related_data = related_res.get("data", [])
                    for i, related_video in enumerate(related_data[:99999]):  # 取前99999个相关视频
                        related_title = related_video.get("title", f"相关视频{i+1}")
                        related_bvid = related_video.get("bvid", "")
                        
                        if not related_title or related_title == f"相关视频{i+1}":
                            related_title = f"相关推荐{i+1}"
                        
                        # 清理标题中的特殊字符
                        related_title = related_title.replace('#', '﹟').replace('$', '﹩')
                        
                        # 获取相关视频的播放量
                        related_stat = related_video.get('stat', {})
                        related_views = related_stat.get('view', 0)
                        
                        # 构建完整的播放地址
                        if related_bvid:
                            related_video_url = f"https://www.bilibili.com/video/{related_bvid}"
                            related_play_url += f"{related_title}【{self.format_number(related_views)}】${related_video_url}#"
                    
                    related_play_url = related_play_url.rstrip("#")
                    
            except Exception:
                pass

        # 构建播放来源和播放地址
        if related_play_url:
            vod_play_from = "B站影视$$$相关推荐"
            vod_play_url = f"{play_url}$$${related_play_url}"
        else:
            vod_play_from = 'B站影视'
            vod_play_url = play_url
        
        # 构建备注信息（显示更丰富的信息）
        remark_info = f"播放:{self.format_number(view_count)} · 弹幕:{self.format_number(danmaku_count)} · 点赞:{self.format_number(like_count)} · 投币:{self.format_number(coin_count)}"

        video = {
            "vod_id": did,
            "vod_name": name,
            "vod_pic": pic_url,
            "vod_actor": f"UP主：{up_name}",
            "vod_director": director,
            "vod_content": detail_info,
            "vod_remarks": remark_info,
            "vod_year": pub_time.split('-')[0] if pub_time != "未知时间" else '',
            "vod_area": remarks,
            "vod_play_from": vod_play_from,
            "vod_play_url": vod_play_url
        }
        videos.append(video)

        result['list'] = videos
        return result

    def playerContent(self, flag, id, vipFlags):
        """播放器内容，添加弹幕接口支持"""
        try:
            # 解析URL获取bvid
            from urllib.parse import parse_qs, urlparse
            
            # 如果是相关推荐视频，需要提取bvid
            if "bilibili.com/video/" in id:
                # 从URL中提取bvid
                match = re.search(r'bilibili\.com/video/(BV[0-9A-Za-z]+)', id)
                if match:
                    bvid = match.group(1)
                else:
                    # 从查询参数中提取
                    parsed = urlparse(id)
                    params = parse_qs(parsed.query)
                    if 'bvid' in params:
                        bvid = params['bvid'][0]
                    else:
                        # 尝试从路径中提取
                        path_parts = parsed.path.split('/')
                        for part in path_parts:
                            if part.startswith('BV'):
                                bvid = part
                                break
                        else:
                            bvid = None
            else:
                bvid = None
            
            # 获取视频的cid（弹幕ID）
            cid = None
            if bvid:
                try:
                    # 获取视频信息获取cid
                    video_api = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
                    video_res = requests.get(video_api, headers=headerx).json()
                    if video_res.get("code") == 0:
                        cid = video_res["data"].get("cid")
                except:
                    pass
            
            # 构建弹幕URL
            danmaku_url = ""
            if cid:
                # 使用提供的弹幕接口
                danmaku_url = f"https://183933.xyz/dm/dm.php?url=https://www.bilibili.com/video/{bvid}"
            
            # 返回播放器配置
            player_config = {
                'jx': 1, 
                'parse': 1, 
                'url': id, 
                'header': headerx
            }
            
            # 如果有弹幕URL，添加到配置中
            if danmaku_url:
                player_config['danmaku'] = danmaku_url
                
            return player_config
            
        except Exception:
            # 出错时返回基础配置
            return {'jx': 1, 'parse': 1, 'url': id, 'header': headerx}

    def searchContentPage(self, key, quick, page):
        result = {}
        videos = []
        if not page:
            page = 1
        url = f'{xurl}/x/web-interface/wbi/search/type?search_type=video&__refresh__=true&page={page}&page_size=42&keyword={key}'
        res = requests.get(url=url, headers=headers)
        res.encoding = "utf-8"
        kjson = json.loads(res.text)
        for i in kjson['data']['result']:
            if str(i['bvid']) == '':
                continue
            id = str(i['bvid'])
            name = i['title']
            pic = i['pic']
            if 'http' not in pic:
                pic = 'http:'+pic
            else:
                pic = pic
            remark = i['play']
            num_str = str(remark).strip()

            num = float(num_str)
            if num >= 100_000_000:
                remarks = f"{num / 100_000_000:.1f}亿播放量"
            elif num >= 10_000:
                remarks = f"{num / 10_000:.1f}万播放量"
            else:
                remarks = f"{num:.1f}播放量"

            video = {
                "vod_id": id,
                "vod_name": name.replace('<em class="keyword">', '').replace('</em>', ''),
                "vod_pic": pic,
                "vod_remarks": remarks
            }
            videos.append(video)

        result['list'] = videos
        result['page'] = page
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        return result

    def searchContent(self, key, quick, pg="1"):
        return self.searchContentPage(key, quick, '1')

    def localProxy(self, params):
        if params['type'] == "m3u8":
            return self.proxyM3u8(params)
        elif params['type'] == "media":
            return self.proxyMedia(params)
        elif params['type'] == "ts":
            return self.proxyTs(params)
        return None