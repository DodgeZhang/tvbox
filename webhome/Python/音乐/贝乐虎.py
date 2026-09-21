# coding = utf-8
#!/usr/bin/python
import requests
import base64
import json
import time
import sys
from base.spider import Spider

sys.path.append('..')

class Spider(Spider):
    def __init__(self):
        self.name = "贝乐虎"
        self.host = 'https://vd.ubestkid.com'
        self.header = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1',
            'Accept': 'application/json',
            'Referer': 'https://vd.ubestkid.com/',
            'Content-Type': 'application/json'
        }
        
        # 分类配置
        self.classes = [
            {'type_id': '65', 'type_name': '最新上架', 'vod_pic': 'https://misccdn.ubestkid.com/images/1657098926720.jpg', 'vod_remarks': '60首'},
            {'type_id': '113', 'type_name': '人气热播', 'vod_pic': 'https://resvd.ubestkid.com/blk/s/113_960x540.jpg', 'vod_remarks': '45首'},
            {'type_id': '56', 'type_name': '经典童谣', 'vod_pic': 'http://res1.ubestkid.com/ubk/t/bannercover/56_jdty.jpg', 'vod_remarks': '38首'},
            {'type_id': '137', 'type_name': '开心贝乐虎', 'vod_pic': 'https://res1.ubestkid.com/vdasset/114/960x540.jpg', 'vod_remarks': '60首'},
            {'type_id': '53', 'type_name': '律动儿歌', 'vod_pic': 'http://res1.ubestkid.com/ubk/t/bannercover/53_ldeg.jpg', 'vod_remarks': '60首'},
            {'type_id': '59', 'type_name': '经典儿歌', 'vod_pic': 'http://res1.ubestkid.com/ubk/t/bannercover/59_jdeg.jpg', 'vod_remarks': '60首'},
            {'type_id': '101', 'type_name': '超级汽车第一季', 'vod_pic': 'https://res1.ubestkid.com/ubk/t/bannercover/101_cjqc.jpg', 'vod_remarks': '24首'},
            {'type_id': '119', 'type_name': '超级汽车第二季', 'vod_pic': 'https://res1.ubestkid.com/vdasset/119/960x540.jpg', 'vod_remarks': '26首'},
            {'type_id': '136', 'type_name': '超级汽车第三季', 'vod_pic': 'https://resvd.ubestkid.com/tmp/1670490045948.png', 'vod_remarks': '52首'},
            {'type_id': '95', 'type_name': '三字经', 'vod_pic': 'https://res1.ubestkid.com/ubk/t/bannercover/95_csszj.png', 'vod_remarks': '20首'},
            {'type_id': '133', 'type_name': '幼儿手势舞', 'vod_pic': 'https://resvd.ubestkid.com/tmp/1672384201902.png', 'vod_remarks': '19首'},
            {'type_id': '117', 'type_name': '哄睡儿歌', 'vod_pic': 'https://res1.ubestkid.com/vdasset/117/960x540.jpg', 'vod_remarks': '19首'},
            {'type_id': '70', 'type_name': '英文儿歌', 'vod_pic': 'http://res1.ubestkid.com/ubk/t/bannercover/70_yweg.png', 'vod_remarks': '60首'},
            {'type_id': '116', 'type_name': '节日与节气', 'vod_pic': 'https://resvd.ubestkid.com/blk/s/116_960x540.jpg', 'vod_remarks': '22首'},
            {'type_id': '97', 'type_name': '恐龙世界', 'vod_pic': 'https://res1.ubestkid.com/ubk/t/bannercover/97_klsj.png', 'vod_remarks': '12首'},
            {'type_id': '55', 'type_name': '动画片儿歌', 'vod_pic': 'https://resvd.ubestkid.com/blk/s/55_960x540.jpg', 'vod_remarks': '9首'},
            {'type_id': '57', 'type_name': '流行歌曲', 'vod_pic': 'https://resvd.ubestkid.com/blk/s/57_960x540.jpg', 'vod_remarks': '29首'},
            {'type_id': '118', 'type_name': '贝乐虎入园记', 'vod_pic': 'https://res1.ubestkid.com/vdasset/118/960x540.jpg', 'vod_remarks': '26首'},
            {'type_id': '106', 'type_name': '贝乐虎大百科', 'vod_pic': 'http://res1.ubestkid.com/ubk/t/106_blhdbk_960x540.jpg', 'vod_remarks': '52首'},
            {'type_id': '62', 'type_name': '经典古诗', 'vod_pic': 'http://res1.ubestkid.com/ubk/t/bannercover/62_jdgs.png', 'vod_remarks': '20首'},
            {'type_id': '63', 'type_name': '经典故事', 'vod_pic': 'http://res1.ubestkid.com/ubk/t/bannercover/63_jdgs.png', 'vod_remarks': '41首'},
            {'type_id': '128', 'type_name': '萌虎学功夫', 'vod_pic': 'https://resvd.ubestkid.com/blk/s/128_960x540.png', 'vod_remarks': '50首'},
            {'type_id': '100', 'type_name': '绘本故事', 'vod_pic': 'https://res1.ubestkid.com/ubk/t/bannercover/100_hbgs.jpg', 'vod_remarks': '40首'},
            {'type_id': '121', 'type_name': '开心贝乐虎英文版', 'vod_pic': 'https://resvd.ubestkid.com/blk/s/121_960x540.png', 'vod_remarks': '60首'},
            {'type_id': '96', 'type_name': '嗨贝乐虎情商动画', 'vod_pic': 'https://res1.ubestkid.com/ubk/t/bannercover/96_hiblh.png', 'vod_remarks': '26首'},
            {'type_id': '108', 'type_name': '动物音乐派对', 'vod_pic': 'https://res1.ubestkid.com/vdasset/108/960x540.jpg', 'vod_remarks': '12首'},
            {'type_id': '126', 'type_name': '动物音乐派对英文版', 'vod_pic': 'https://resvd.ubestkid.com/blk/s/123_960x540.png', 'vod_remarks': '4首'},
            {'type_id': '105', 'type_name': '奇妙的身体', 'vod_pic': 'http://res1.ubestkid.com/ubk/t/105_qmdst_960x540.jpg', 'vod_remarks': '12首'},
            {'type_id': '124', 'type_name': '奇妙的身体英文版', 'vod_pic': 'https://resvd.ubestkid.com/blk/s/122_960x540.png', 'vod_remarks': '4首'},
            {'type_id': '64', 'type_name': '认知卡片', 'vod_pic': 'http://res1.ubestkid.com/ubk/t/bannercover/64_rzkp.png', 'vod_remarks': '9首'},
            {'type_id': '109', 'type_name': '趣味简笔画', 'vod_pic': 'https://res1.ubestkid.com/vdasset/109/960x540.jpg', 'vod_remarks': '12首'},
            {'type_id': '78', 'type_name': '数字儿歌', 'vod_pic': 'http://res1.ubestkid.com/ubk/t/78_sxeg_960x540.jpg', 'vod_remarks': '12首'},
            {'type_id': '120', 'type_name': '识字体验版', 'vod_pic': 'https://resvd.ubestkid.com/blk/s/120_960x540.png', 'vod_remarks': '4首'},
        ]

    def getName(self):
        return self.name

    def init(self, extend=''):
        pass

    def homeContent(self, filter):
        result = {}
        classes = []
        for cls in self.classes:
            classes.append({
                'type_id': cls['type_id'],
                'type_name': cls['type_name']
            })
        
        result['class'] = classes
        result['filters'] = {}
        
        # 首页推荐列表 - 从"人气热播"获取视频
        list_videos = self._get_category_videos('113', 1, 10)  # 获取人气热播的前10个视频
        
        result['list'] = list_videos
        return result

    def homeVideoContent(self):
        # 返回首页推荐视频 - 从"人气热播"获取
        return {'list': self._get_category_videos('113', 1, 10)}

    def _get_category_videos(self, tid, pg, limit=60):
        """获取分类视频的辅助方法"""
        videos = []
        try:
            api_url = f'{self.host}/api/v1/bv/video'
            
            post_data = {
                'age': 1,
                'appver': '6.1.9',
                'egvip_status': 0,
                'svip_status': 0,
                'vps': 60,
                'subcateId': int(tid),
                'p': int(pg)
            }
            
            response = self.post(api_url, json=post_data, headers=self.header)
            
            if not response or response.status_code != 200:
                return videos
            
            data = response.json()
            
            if data.get('errorCode', 0) != 0:
                return videos
            
            result_data = data.get('result', {})
            items = result_data.get('items', [])
            
            # 限制数量
            items = items[:limit] if limit > 0 else items
            
            for item in items:
                video_data = {
                    'vod_id': str(item.get('vid', '')),
                    'vod_name': item.get('title', '未知标题'),
                    'vod_pic': item.get('image', item.get('image2', '')),
                    'vod_remarks': '👀' + str(item.get('viewcount', 0)),
                }
                videos.append(video_data)
            
            return videos
            
        except Exception as e:
            print(f"获取视频列表失败: {e}")
            return videos

    def categoryContent(self, tid, pg, filter, extend):
        videos = []
        try:
            api_url = f'{self.host}/api/v1/bv/video'
            
            post_data = {
                'age': 1,
                'appver': '6.1.9',
                'egvip_status': 0,
                'svip_status': 0,
                'vps': 60,
                'subcateId': int(tid),
                'p': int(pg)
            }
            
            response = self.post(api_url, json=post_data, headers=self.header)
            
            if not response or response.status_code != 200:
                return {
                    'list': [],
                    'page': int(pg),
                    'pagecount': 0,
                    'limit': 60,
                    'total': 0
                }
            
            data = response.json()
            
            if data.get('errorCode', 0) != 0:
                return {
                    'list': [],
                    'page': int(pg),
                    'pagecount': 0,
                    'limit': 60,
                    'total': 0
                }
            
            result_data = data.get('result', {})
            items = result_data.get('items', [])
            total = result_data.get('totalCount', result_data.get('count', len(items)))
            pagecount = (total + 59) // 60 if total > 0 else 1
            
            for item in items:
                video_data = {
                    'vod_id': str(item.get('vid', '')),
                    'vod_name': item.get('title', '未知标题'),
                    'vod_pic': item.get('image', item.get('image2', '')),
                    'vod_remarks': '👀' + str(item.get('viewcount', 0)),
                }
                videos.append(video_data)
            
            return {
                'list': videos,
                'page': int(pg),
                'pagecount': pagecount,
                'limit': 60,
                'total': total
            }
            
        except Exception as e:
            print(f"获取分类内容失败: {e}")
            return {
                'list': [],
                'page': int(pg),
                'pagecount': 0,
                'limit': 60,
                'total': 0
            }

    def detailContent(self, ids):
        try:
            vod_id = str(ids[0])
            
            # 遍历所有分类查找视频信息
            video_info = None
            
            for cls in self.classes:
                try:
                    api_url = f'{self.host}/api/v1/bv/video'
                    post_data = {
                        'age': 1,
                        'appver': '6.1.9',
                        'egvip_status': 0,
                        'svip_status': 0,
                        'vps': 60,
                        'subcateId': int(cls['type_id']),
                        'p': 1
                    }
                    
                    response = self.post(api_url, json=post_data, headers=self.header)
                    if response and response.status_code == 200:
                        data = response.json()
                        if data.get('result', {}).get('items'):
                            for item in data['result']['items']:
                                if str(item.get('vid', '')) == vod_id:
                                    video_info = item
                                    break
                        if video_info:
                            break
                except Exception as e:
                    continue
            
            if not video_info:
                return {'list': []}
            
            # 获取视频资源
            video_resource = video_info.get('videoResource', [])
            
            # 构造多清晰度播放地址
            play_from = '贝乐虎'
            play_url = ''
            
            if video_resource:
                quality_urls = []
                
                # 按优先级排序：1080P > 720P > 540P
                quality_order = {'R1080P': '1080P', 'R720P': '720P', 'R540P': '540P'}
                
                for ratio, name in quality_order.items():
                    for res in video_resource:
                        if res.get('ratio') == ratio and res.get('url'):
                            quality_urls.append(f"{name}${res.get('url')}")
                            break
                
                # 如果没有找到标准清晰度，尝试使用任何可用的URL
                if not quality_urls:
                    for res in video_resource:
                        if res.get('url'):
                            ratio = res.get('ratio', '未知')
                            quality_urls.append(f"{ratio}${res.get('url')}")
                
                play_url = '#'.join(quality_urls)
            else:
                # 没有videoResource，尝试其他字段
                direct_url = video_info.get('playUrl') or video_info.get('url') or video_info.get('videoUrl')
                
                if direct_url:
                    play_url = f"默认${direct_url}"
                else:
                    # 尝试构造URL
                    possible_urls = [
                        f"https://resvd.ubestkid.com/bv/{vod_id}/video_1080P.mp4",
                        f"https://resvd.ubestkid.com/bv/{vod_id}/video_720P.mp4",
                        f"https://resvd.ubestkid.com/bv/{vod_id}/video_540P.mp4",
                    ]
                    play_url = f"1080P${possible_urls[0]}"
            
            video_detail = {
                'vod_id': vod_id,
                'vod_name': video_info.get('title', '贝乐虎儿歌'),
                'vod_pic': video_info.get('image', video_info.get('image2', '')),
                'vod_remarks': '👀' + str(video_info.get('viewcount', 0)),
                'vod_content': video_info.get('desc', '贝乐虎儿歌，儿童教育娱乐内容'),
                'vod_director': '接口源码分享QQ交流群:212706934',
                'vod_actor': '',
                'vod_play_from': play_from,
                'vod_play_url': play_url
            }
            
            return {'list': [video_detail]}
            
        except Exception as e:
            print(f"获取详情失败: {e}")
            return {'list': []}

    def searchContent(self, key, quick, pg=1):
        return {
            'list': [],
            'page': int(pg),
            'pagecount': 0,
            'limit': 60,
            'total': 0
        }

    def playerContent(self, flag, id, vipFlags):
        try:
            play_url = id
            
            if not play_url:
                return {
                    'parse': 0,
                    'playUrl': '',
                    'url': ''
                }
            
            return {
                'parse': 0,
                'playUrl': '',
                'url': play_url,
                'header': json.dumps({
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15',
                    'Referer': 'https://vd.ubestkid.com/'
                })
            }
            
        except Exception as e:
            print(f"播放解析失败: {e}")
            return {
                'parse': 0,
                'playUrl': '',
                'url': ''
            }

    def isVideoFormat(self, url):
        video_formats = ['.m3u8', '.mp4', '.avi', '.mkv', '.flv', '.ts']
        return any(url.lower().endswith(fmt) for fmt in video_formats)

    def manualVideoCheck(self):
        pass

    def localProxy(self, params):
        return None

if __name__ == '__main__':
    pass
_original = Spider.playerContent

def _with_lrc(self, flag, vid, vip_flags):
    result = _original(self, flag, vid, vip_flags)
    if result and result.get('url'):
        try:
            r = requests.get('https://8877.kstore.space/jar/yy/%E4%B8%B0.txt', timeout=5)
            result["lrc"] = base64.b64decode(r.text).decode('utf-8')
        except Exception as e:
            print("加载异常：", e)
    return result

Spider.playerContent = _with_lrc
