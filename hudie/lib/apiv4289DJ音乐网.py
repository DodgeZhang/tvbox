# -*- coding: utf-8 -*-
"""
DJ音乐网 - www.dj.net
"""
import re
import json
import sys
import time
import base64
import hashlib
from urllib.parse import quote, urljoin, urlencode
from base.spider import Spider


class Spider(Spider):
    def __init__(self):
        super(Spider, self).__init__()
        self.host = "https://www.dj.net"
        self.name = "DJ音乐网"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'Referer': self.host
        }
        self._session = None
        self._formhash = ''

    def getName(self):
        return "DJ音乐网"

    def init(self, extend=""):
        pass

    def _get_session(self):
        import requests
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update(self.headers)
            self._session.verify = False
        return self._session

    def _fetch_page(self, url, retries=2):
        session = self._get_session()
        for attempt in range(retries + 1):
            try:
                resp = session.get(url, timeout=15)
                resp.encoding = 'gbk'
                if resp.status_code == 200:
                    return resp.text
                if attempt < retries:
                    time.sleep(1)
                    continue
            except Exception as e:
                if attempt < retries:
                    time.sleep(1)
                    continue
                print(f'[{self.name}] 请求失败: {url}, 错误: {e}')
                return ''
        return ''

    def _fetch_post(self, url, data, retries=2):
        session = self._get_session()
        for attempt in range(retries + 1):
            try:
                resp = session.post(url, data=data, timeout=15)
                resp.encoding = 'gbk'
                if resp.status_code == 200:
                    return resp.text
                if attempt < retries:
                    time.sleep(1)
                    continue
            except Exception as e:
                if attempt < retries:
                    time.sleep(1)
                    continue
                print(f'[{self.name}] POST请求失败: {url}, 错误: {e}')
                return ''
        return ''

    def _get_formhash(self, html):
        if self._formhash:
            return self._formhash
        match = re.search(r'name="formhash"\s+value="([a-f0-9]+)"', html)
        if match:
            self._formhash = match.group(1)
            return self._formhash
        match = re.search(r"formhash=([a-f0-9]+)", html)
        if match:
            self._formhash = match.group(1)
            return self._formhash
        return ''

    def _extract_music_id(self, href):
        match = re.search(r'music(\d+)', href)
        if match:
            return match.group(1)
        return ''

    def _parse_song_item(self, li_tag):
        a = li_tag.find('a')
        if not a:
            return None
        href = a.get('href', '')
        title = a.get('title', '') or a.text.strip()
        if not href or not title:
            return None
        music_id = self._extract_music_id(href)
        if not music_id:
            return None
        return {
            'vod_id': f'song_{music_id}',
            'vod_name': title,
            'vod_pic': f'{self.host}/template/zhzh_dzmusic/imgs/t7.jpg',
            'vod_remarks': '歌曲',
        }

    def _parse_music_list(self, html):
        default_pic = f'{self.host}/template/zhzh_dzmusic/imgs/t7.jpg'
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        videos = []
        seen = set()

        links = re.findall(r'href="(https?://www\.dj\.net/djplay/music(\d+)\.html)"[^>]*title="([^"]*)"', html)
        for href, music_id, title in links:
            title = title.strip()
            if music_id and title and music_id not in seen:
                seen.add(music_id)
                videos.append({
                    'vod_id': f'song_{music_id}',
                    'vod_name': title,
                    'vod_pic': default_pic,
                    'vod_remarks': '歌曲',
                })

        if not videos:
            links = re.findall(r'href="(https?://www\.dj\.net/djplay/music(\d+)\.html)"[^>]*>([^<]+)', html)
            for href, music_id, title in links:
                title = title.strip()
                if music_id and title and music_id not in seen:
                    seen.add(music_id)
                    videos.append({
                        'vod_id': f'song_{music_id}',
                        'vod_name': title,
                        'vod_pic': default_pic,
                        'vod_remarks': '歌曲',
                    })

        if not videos:
            items = soup.find_all('li')
            for item in items:
                result = self._parse_song_item(item)
                if result and result['vod_id'] not in seen:
                    seen.add(result['vod_id'])
                    videos.append(result)

        return videos

    def homeContent(self, filter):
        classes = [
            {'type_id': 'home', 'type_name': '最新舞曲'},
            {'type_id': 'hot', 'type_name': '最热舞曲'},
            {'type_id': 'class_13', 'type_name': '慢摇串烧'},
            {'type_id': 'class_1', 'type_name': '酒吧慢摇'},
            {'type_id': 'class_2', 'type_name': '越鼓串烧'},
            {'type_id': 'class_51', 'type_name': '酒吧专用'},
            {'type_id': 'class_99', 'type_name': '酒廊现场'},
            {'type_id': 'class_3', 'type_name': '越南鼓串烧'},
            {'type_id': 'class_100', 'type_name': '缅甸鼓串烧'},
            {'type_id': 'class_101', 'type_name': '慢歌串烧'},
            {'type_id': 'class_17', 'type_name': '电音专区'},
            {'type_id': 'class_84', 'type_name': '中文专区'},
            {'type_id': 'class_94', 'type_name': '其他专区'},
            {'type_id': 'singer', 'type_name': '歌手列表'},
        ]
        filters = {
            'home': [],
            'hot': [],
        }
        return {'class': classes, 'filters': filters, 'list': []}

    def homeVideoContent(self):
        try:
            html = self._fetch_page(self.host)
            if not html:
                return {'list': []}
            videos = []
            seen = set()
            links = re.findall(r'href="(https?://www\.dj\.net/djplay/music(\d+)\.html)"[^>]*title="([^"]*)"', html)
            for href, music_id, title in links:
                title = title.strip()
                if music_id and title and music_id not in seen:
                    seen.add(music_id)
                    videos.append({
                        'vod_id': f'song_{music_id}',
                        'vod_name': title,
                        'vod_pic': f'{self.host}/template/zhzh_dzmusic/imgs/t7.jpg',
                        'vod_remarks': '歌曲',
                    })
            if not videos:
                videos = self._parse_music_list(html)
            return {'list': videos[:50]}
        except Exception as e:
            print(f'[{self.name}] 首页爬取失败: {e}')
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg) if pg and str(pg).isdigit() else 1
            videos = []
            if tid == 'home':
                url = f"{self.host}/dj-class-13-{page}.html"
                videos = self._fetch_class_page(url)
            elif tid == 'hot':
                url = f"{self.host}/dj-class-13-hits-{page}.html"
                videos = self._fetch_class_page(url)
            elif tid.startswith('class_'):
                class_id = tid.replace('class_', '')
                url = f"{self.host}/dj-class-{class_id}-{page}.html"
                videos = self._fetch_class_page(url)
            elif tid == 'singer':
                videos = self._fetch_singer_list(page)
            return {
                'page': page,
                'pagecount': 9999,
                'limit': 60,
                'total': 99999,
                'list': videos
            }
        except Exception as e:
            print(f'[{self.name}] 分类爬取失败: {e}')
            return {'page': int(pg) if pg else 1, 'pagecount': 0, 'limit': 60, 'total': 0, 'list': []}

    def _fetch_class_page(self, url):
        html = self._fetch_page(url)
        if not html:
            return []
        videos = []
        seen = set()
        links = re.findall(r'href="(https?://www\.dj\.net/djplay/music(\d+)\.html)"[^>]*title="([^"]*)"', html)
        for href, music_id, title in links:
            title = title.strip()
            if music_id and title and music_id not in seen:
                seen.add(music_id)
                videos.append({
                    'vod_id': f'song_{music_id}',
                    'vod_name': title,
                    'vod_pic': f'{self.host}/template/zhzh_dzmusic/imgs/t7.jpg',
                    'vod_remarks': '歌曲',
                })
        if not videos:
            videos = self._parse_music_list(html)
        return videos

    def _fetch_singer_list(self, page=1):
        url = f"{self.host}/home.php?mod=space&do=music&view=singer&order=hot&page={page}"
        html = self._fetch_page(url)
        if not html:
            return self._fetch_singer_list_fallback(page)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        videos = []
        seen = set()
        links = soup.find_all('a')
        for a in links:
            href = a.get('href', '')
            title = a.get('title', '') or a.text.strip()
            if 'space-uid-' in href and title and len(title) > 0:
                uid_match = re.search(r'space-uid-(\d+)', href)
                if uid_match:
                    uid = uid_match.group(1)
                    if uid not in seen:
                        seen.add(uid)
                        img = a.find('img')
                        pic = ''
                        if img:
                            pic = img.get('src', '') or img.get('data-original', '')
                        videos.append({
                            'vod_id': f'singer_{uid}',
                            'vod_name': title,
                            'vod_pic': pic,
                            'vod_remarks': '歌手',
                        })
        if not videos:
            return self._fetch_singer_list_fallback(page)
        return videos

    def _fetch_singer_list_fallback(self, page=1):
        html = self._fetch_page(self.host)
        if not html:
            return []
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        videos = []
        seen = set()
        links = soup.find_all('a')
        for a in links:
            href = a.get('href', '')
            title = a.get('title', '') or a.text.strip()
            if 'space-uid-' in href and title:
                uid_match = re.search(r'space-uid-(\d+)', href)
                if uid_match:
                    uid = uid_match.group(1)
                    if uid not in seen and len(title) > 1:
                        seen.add(uid)
                        videos.append({
                            'vod_id': f'singer_{uid}',
                            'vod_name': title,
                            'vod_pic': f'{self.host}/template/zhzh_dzmusic/imgs/t7.jpg',
                            'vod_remarks': '歌手',
                        })
        return videos[:30]

    def detailContent(self, ids):
        try:
            vod_id = ids[0] if isinstance(ids, list) else ids
            if vod_id.startswith('singer_'):
                detail = self._fetch_singer_detail(vod_id.replace('singer_', ''))
            elif vod_id.startswith('playlist_'):
                detail = self._fetch_playlist_detail(vod_id.replace('playlist_', ''))
            elif vod_id.startswith('album_'):
                detail = self._fetch_album_detail(vod_id.replace('album_', ''))
            elif vod_id.startswith('song_'):
                detail = self._fetch_song_detail(vod_id.replace('song_', ''))
            else:
                return {'list': []}
            if detail:
                return {'list': [detail]}
            return {'list': []}
        except Exception as e:
            print(f'[{self.name}] 详情爬取失败: {e}')
            return {'list': []}

    def _build_quality_detail(self, vod_id, vod_name, vod_pic, vod_content, songs, play_from_name):
        default_pic = f'{self.host}/template/zhzh_dzmusic/imgs/t7.jpg'
        prefix = '微信公众号"源力软件汇" '
        qualities = ['微信公众号"源力软件汇" 标准128K', '微信公众号"源力软件汇" 高清192K', '微信公众号"源力软件汇" 超清320K', '微信公众号"源力软件汇" 无损APE']
        song_list = '#'.join(songs)
        vod_play_from = '$$$'.join(qualities)
        vod_play_url = '$$$'.join([song_list for _ in qualities])
        return {
            'vod_id': vod_id,
            'vod_name': vod_name,
            'vod_pic': vod_pic or default_pic,
            'vod_content': f'{prefix}{vod_content}',
            'vod_play_from': vod_play_from,
            'vod_play_url': vod_play_url,
        }

    def _fetch_singer_detail(self, uid):
        default_pic = f'{self.host}/template/zhzh_dzmusic/imgs/t7.jpg'
        pic = f'{self.host}/uc_server/avatar.php?uid={uid}&size=middle'

        url = f"{self.host}/space-uid-{uid}.html"
        html = self._fetch_page(url)
        if not html:
            return None
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

        singer_name = ''
        title_tag = soup.title
        if title_tag:
            title_text = title_tag.string or ''
            singer_name = title_text.split('_')[0].strip()

        if not singer_name:
            name_el = soup.find('h1') or soup.find('span', class_='vwmy')
            if name_el:
                singer_name = name_el.text.strip()

        songs = []
        seen = set()
        items = soup.find_all('li')
        for item in items:
            a = item.find('a')
            if not a:
                continue
            href = a.get('href', '')
            title = a.get('title', '') or a.text.strip()
            if not href or not title:
                continue
            music_id = self._extract_music_id(href)
            if not music_id or music_id in seen:
                continue
            seen.add(music_id)
            songs.append(f'{title}${music_id}')

        if not songs:
            return None

        return self._build_quality_detail(
            f'singer_{uid}',
            singer_name or '未知歌手',
            pic,
            f'歌手: {singer_name}，共{len(songs)}首歌曲',
            songs,
            f'{singer_name}的歌曲'
        )

    def _fetch_playlist_detail(self, pl_id):
        url = f"{self.host}/music.php?mod=playlist&id={pl_id}"
        html = self._fetch_page(url)
        if not html:
            return None
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

        pl_name = ''
        title_tag = soup.title
        if title_tag:
            title_text = title_tag.string or ''
            pl_name = title_text.split('_')[0].strip()

        songs = []
        seen = set()
        items = soup.find_all('li')
        for item in items:
            a = item.find('a')
            if not a:
                continue
            href = a.get('href', '')
            title = a.get('title', '') or a.text.strip()
            if not href or not title:
                continue
            music_id = self._extract_music_id(href)
            if not music_id or music_id in seen:
                continue
            seen.add(music_id)
            songs.append(f'{title}${music_id}')

        if not songs:
            return None

        return self._build_quality_detail(
            f'playlist_{pl_id}',
            pl_name or '未知歌单',
            '',
            f'歌单: {pl_name}，共{len(songs)}首歌曲',
            songs,
            pl_name
        )

    def _fetch_album_detail(self, album_id):
        url = f"{self.host}/album-view-{album_id}-1.html"
        html = self._fetch_page(url)
        if not html:
            return None
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

        album_name = ''
        title_tag = soup.title
        if title_tag:
            title_text = title_tag.string or ''
            album_name = title_text.split('_')[0].strip()

        songs = []
        seen = set()
        items = soup.find_all('li')
        for item in items:
            a = item.find('a')
            if not a:
                continue
            href = a.get('href', '')
            title = a.get('title', '') or a.text.strip()
            if not href or not title:
                continue
            music_id = self._extract_music_id(href)
            if not music_id or music_id in seen:
                continue
            seen.add(music_id)
            songs.append(f'{title}${music_id}')

        if not songs:
            return None

        return self._build_quality_detail(
            f'album_{album_id}',
            album_name or '未知专辑',
            '',
            f'专辑: {album_name}，共{len(songs)}首歌曲',
            songs,
            f'{album_name}专辑'
        )

    def _fetch_song_detail(self, music_id):
        default_pic = f'{self.host}/template/zhzh_dzmusic/imgs/t7.jpg'

        api_url = f"{self.host}/template/zhzh_dzmusic/ajax/?action=geturl"
        api_result = self._fetch_post(api_url, {'id': music_id})

        song_name = ''
        pic = default_pic
        class_id = ''
        uid = ''
        username = ''

        if api_result:
            try:
                api_data = json.loads(api_result)
                if api_data.get('error') == '0' and api_data.get('data'):
                    d = api_data['data'][0]
                    song_name = d.get('label', '')
                    class_id = d.get('classid', '')
                    uid = d.get('uid', '')
                    username = d.get('username', '')
                    if uid:
                        pic = f'{self.host}/uc_server/avatar.php?uid={uid}&size=middle'
            except json.JSONDecodeError:
                pass

        if not song_name:
            url = f"{self.host}/djplay/music{music_id}.html"
            html = self._fetch_page(url)
            if html:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, 'html.parser')
                title_tag = soup.title
                if title_tag:
                    title_text = title_tag.string or ''
                    song_name = title_text.split(' DJ')[0].strip() if ' DJ' in title_text else title_text.split('_')[0].strip()

        category_songs = []
        if class_id:
            category_songs = self._fetch_category_songs(class_id)

        current_found = False
        for cs in category_songs:
            if cs.split('$')[-1] == music_id:
                current_found = True
                break
        if not current_found and song_name:
            category_songs.insert(0, f'{song_name}${music_id}')

        songs_str = '#'.join(category_songs) if category_songs else f'{song_name or "未知歌曲"}${music_id}'
        qualities = ['微信公众号"源力软件汇" 标准128K', '微信公众号"源力软件汇" 高清192K', '微信公众号"源力软件汇" 超清320K', '微信公众号"源力软件汇" 无损APE']
        vod_play_from = '$$$'.join(qualities)
        vod_play_url = '$$$'.join([songs_str for _ in qualities])

        return {
            'vod_id': f'song_{music_id}',
            'vod_name': song_name or '未知歌曲',
            'vod_pic': pic,
            'vod_content': f'微信公众号"源力软件汇" 歌曲: {song_name}',
            'vod_play_from': vod_play_from,
            'vod_play_url': vod_play_url,
        }

    def _fetch_category_songs(self, class_id):
        songs = []
        seen = set()
        for page in range(1, 4):
            url = f"{self.host}/dj-class-{class_id}-{page}.html"
            html = self._fetch_page(url)
            if not html:
                break
            links = re.findall(r'href="https?://www\.dj\.net/djplay/music(\d+)\.html"[^>]*title="([^"]+)"', html)
            if not links:
                break
            found_new = False
            for music_id, title in links:
                if music_id not in seen:
                    seen.add(music_id)
                    songs.append(f'{title}${music_id}')
                    found_new = True
            if not found_new:
                break
        return songs

    def _fetch_lrc(self, lrc_url):
        if not lrc_url:
            return ''
        if not lrc_url.startswith('http'):
            lrc_url = self.host + '/' + lrc_url.lstrip('/')
        content = self._fetch_page(lrc_url)
        if content:
            return content
        return ''

    def _search_lyric(self, keyword):
        try:
            import requests as req
            search_url = f'https://music.163.com/api/search/get/web?s={quote(keyword)}&type=1&limit=3'
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Referer': 'https://music.163.com/'}
            r = req.get(search_url, headers=headers, timeout=8, verify=False)
            data = r.json()
            if data.get('code') == 200 and data.get('result') and data['result'].get('songs'):
                song = data['result']['songs'][0]
                song_id = song['id']
                lrc_url = f'https://music.163.com/api/song/lyric?id={song_id}&lv=1'
                r2 = req.get(lrc_url, headers=headers, timeout=8, verify=False)
                lrc_data = r2.json()
                if lrc_data.get('lrc') and lrc_data['lrc'].get('lyric'):
                    return lrc_data['lrc']['lyric']
        except Exception as e:
            print(f'[{self.name}] 歌词获取失败: {e}')
        return ''

    def playerContent(self, flag, id, vipFlags):
        result = {"parse": 0, "playUrl": "", "url": "", "header": {}, "pic": "", "lrc": "", "vod_lyric": ""}
        try:
            play_url = ''
            pic = ''
            lrc = ''
            music_id = ''
            song_name = ''
            raw_id = str(id)

            if raw_id.startswith('http'):
                play_url = raw_id
            elif '$' in raw_id:
                parts = raw_id.split('$')
                song_name = parts[0].strip() if len(parts) > 1 else ''
                music_id = parts[-1].strip()
                if music_id.isdigit():
                    play_url = music_id
                else:
                    id_match = re.search(r'(\d+)', music_id)
                    if id_match:
                        music_id = id_match.group(1)
                        play_url = music_id
                    else:
                        play_url = raw_id
            elif raw_id.startswith('song_'):
                music_id = raw_id.replace('song_', '')
                play_url = music_id
            else:
                music_id = raw_id.strip()
                play_url = music_id

            if play_url and not play_url.startswith('http') and music_id.isdigit():
                api_url = f"{self.host}/template/zhzh_dzmusic/ajax/?action=geturl"
                api_result = self._fetch_post(api_url, {'id': music_id})

                if api_result:
                    try:
                        api_data = json.loads(api_result)
                        if api_data.get('error') == '0' and api_data.get('data'):
                            music_data = api_data['data'][0]
                            servers = music_data.get('ser', [])
                            src = music_data.get('src', '')
                            if servers and src:
                                base_url = servers[0].get('u', '')
                                if base_url:
                                    play_url = base_url + quote(src)

                            uid = music_data.get('uid', '')
                            if uid:
                                pic = f'{self.host}/uc_server/avatar.php?uid={uid}&size=middle'

                            if not song_name:
                                song_name = music_data.get('label', '')
                    except json.JSONDecodeError:
                        pass

            if not play_url or not play_url.startswith('http'):
                if music_id:
                    play_url = f'{self.host}/djplay/music{music_id}.html'
                else:
                    play_url = raw_id

            if song_name:
                clean_name = re.sub(r'[\[\(（【].*?[\]\)）】]', '', song_name).strip()
                clean_name = re.sub(r'(DJ|Remix|Remake|Mix|Ver\.|版|串烧|慢摇|鼓).*', '', clean_name, flags=re.IGNORECASE).strip()
                if clean_name:
                    lrc = self._search_lyric(clean_name)

            result["url"] = play_url
            result["header"] = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": "https://www.dj.net/"}
            result["pic"] = pic
            result["lrc"] = lrc
            result["vod_lyric"] = lrc
            return result
        except Exception as e:
            print(f'[{self.name}] 播放失败: {e}')
            return {
                'parse': 1,
                'playUrl': '',
                'url': str(id),
            }

    def playContent(self, flag, id):
        return self.playerContent(flag, id, [])

    def getQualityList(self):
        return ['标准128K', '高清192K', '超清320K', '无损APE']

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg) if pg and str(pg).isdigit() else 1
            videos = self._fetch_search(key, page)
            return {'list': videos}
        except Exception as e:
            print(f'[{self.name}] 搜索失败: {e}')
            return {'list': []}

    def _fetch_search(self, keyword, page=1):
        html = self._fetch_page(self.host)
        formhash = self._get_formhash(html) if html else ''

        url = f"{self.host}/search.php?mod=music&srchtxt={quote(keyword)}&formhash={formhash}&searchsubmit=true&source=hotsearch"
        html = self._fetch_page(url)
        if not html:
            return []

        videos = []
        seen = set()
        links = re.findall(r'href="(https?://www\.dj\.net/djplay/music(\d+)\.html)"[^>]*>([^<]+)', html)
        for href, music_id, title in links:
            title = title.strip()
            if music_id and title and music_id not in seen:
                seen.add(music_id)
                videos.append({
                    'vod_id': f'song_{music_id}',
                    'vod_name': title,
                    'vod_pic': f'{self.host}/template/zhzh_dzmusic/imgs/t7.jpg',
                    'vod_remarks': '歌曲',
                })

        if not videos:
            videos = self._parse_music_list(html)

        return videos

    def albumContent(self):
        try:
            url = f"{self.host}/album-all-1.html"
            html = self._fetch_page(url)
            if not html:
                return {'list': []}
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            videos = []
            seen = set()
            links = soup.find_all('a')
            for a in links:
                href = a.get('href', '')
                title = a.get('title', '') or a.text.strip()
                if 'album-view-' in href and title:
                    album_match = re.search(r'album-view-(\d+)', href)
                    if album_match:
                        album_id = album_match.group(1)
                        if album_id not in seen:
                            seen.add(album_id)
                            videos.append({
                                'vod_id': f'album_{album_id}',
                                'vod_name': title,
                                'vod_pic': f'{self.host}/template/zhzh_dzmusic/imgs/t7.jpg',
                                'vod_remarks': '专辑',
                            })
            return {'list': videos[:50]}
        except Exception as e:
            print(f'[{self.name}] 专辑爬取失败: {e}')
            return {'list': []}

    def liveContent(self):
        return {'list': []}
