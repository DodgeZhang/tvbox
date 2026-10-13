import { load } from 'assets://js/lib/cat.js';
import 'assets://js/lib/crypto-js.js';

var BILI_COOKIE = '';
var BILI_GUEST_COOKIE = '';  // 自动获取的访客 Cookie
var extConfig = {};

const PLACEHOLDER = 'https://i0.hdslb.com/bfs/static/jinkela/video/asserts/nocover.png';
const DEFAULT_TYPE = '音乐#新闻#白噪音#沙雕动漫#虾仁#短剧#电影#歌曲#演唱会#鬼畜#搞笑#脑洞乌托邦#相声#小品#戏曲#音乐#MV#舞曲#舞蹈#纪录片#健身#帕梅拉#武术#太极拳#广场舞#体育#球星#世界杯#UP主#小姐姐#女优#美食#食谱#荒野求生#旅游#风景#游戏#解说#演讲#考公考试#平面设计#软件教学';     // 分类兜底

function decodeHtml(str) {
    if (!str) return '';
    return str.replace(/&quot;/g, '"')
              .replace(/&amp;/g, '&')
              .replace(/&lt;/g, '<')
              .replace(/&gt;/g, '>')
              .replace(/&#39;/g, "'")
              .replace(/&nbsp;/g, ' ');
}

function fmtDuration(str) {
    if (!str) return '';
    let parts = str.split(':').map(Number);
    let minutes = 0;
    if (parts.length === 3) {
        minutes = parts[0] * 60 + parts[1] + Math.round(parts[2] / 60);
    } else if (parts.length === 2) {
        minutes = parts[0] + Math.round(parts[1] / 60);
    }
    return minutes > 0 ? minutes + '分钟' : '';
}

function formatCount(num) {
    if (!num && num !== 0) return '';
    let n = Number(num);
    if (n >= 10000) {
        let w = n / 10000;
        return (w % 1 === 0 ? w.toFixed(0) : w.toFixed(1)) + '万';
    }
    return n.toString();
}

const mixinKeyEncTab = [
  46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5,
  49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55,
  40, 61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62,
  11, 36, 20, 34, 44, 52
];

let wbiKeyCache = { key: '', hour: -1 };

function getMixinKey(orig) {
  let temp = '';
  for (let i = 0; i < mixinKeyEncTab.length; i++) {
    if (mixinKeyEncTab[i] < orig.length) temp += orig[mixinKeyEncTab[i]];
  }
  return temp.slice(0, 32);
}

async function updateWbiKey() {
  const now = new Date();
  const hour = now.getHours();
  if (wbiKeyCache.key && wbiKeyCache.hour === hour) return;

  // 用当前有效的 Cookie 请求 wbi 密钥
  const ck = BILI_COOKIE || BILI_GUEST_COOKIE || 'buvid3=84B0395D-C9F2-C490-E92E-A09AB48FE26E71636infoc';
  try {
    const resp = await req('https://api.bilibili.com/x/web-interface/nav', {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.bilibili.com',
        'Origin': 'https://www.bilibili.com',
        'Cookie': ck
      }
    });
    const data = JSON.parse(resp.content);
    const imgUrl = data.data.wbi_img.img_url;
    const subUrl = data.data.wbi_img.sub_url;
    const imgKey = imgUrl.split('/').pop().split('.')[0];
    const subKey = subUrl.split('/').pop().split('.')[0];
    wbiKeyCache.key = getMixinKey(imgKey + subKey);
    wbiKeyCache.hour = hour;
  } catch (e) {
    wbiKeyCache.key = '';  
  }
}

function encWbi(params, key) {
  if (!key) return '';
  const sortedKeys = Object.keys(params).sort();
  const query = sortedKeys.map(k => {
    const v = params[k];
    return encodeURIComponent(k) + '=' + encodeURIComponent(v).replace(/[!'()*]/g, '');
  }).join('&');
  const w_rid = CryptoJS.MD5(query + key).toString();
  return query + '&w_rid=' + w_rid;
}

async function fetchGuestCookie() {
  try {
    const resp = await req('https://space.bilibili.com/2/video', {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      },
      timeout: 8000
    });
    if (resp && resp.headers) {
      let cookies = resp.headers['set-cookie'] || [];
      if (typeof cookies === 'string') cookies = [cookies];
      const parts = cookies.map(c => c.split(';')[0].trim()).filter(c => c);
      if (parts.length > 0) BILI_GUEST_COOKIE = parts.join('; ');
    }
  } catch (e) {
  }
}

function getHeaders(useCookie) {
    let ck = BILI_COOKIE || BILI_GUEST_COOKIE || 'buvid3=84B0395D-C9F2-C490-E92E-A09AB48FE26E71636infoc';
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
        'Referer': 'https://www.bilibili.com',
        'Origin': 'https://www.bilibili.com',
        'Cookie': useCookie ? ck : 'buvid3=84B0395D-C9F2-C490-E92E-A09AB48FE26E71636infoc'
    };
}

function searchHeaders() {
    let ck = BILI_COOKIE || BILI_GUEST_COOKIE || 'buvid3=84B0395D-C9F2-C490-E92E-A09AB48FE26E71636infoc';
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36',
        'Referer': 'https://www.bilibili.com',
        'Origin': 'https://www.bilibili.com',
        'Cookie': ck
    };
}

async function init(config) {
    let cfg = typeof config === 'string' ? JSON.parse(config) : (config || {});
    extConfig = cfg;
    let cookieSource = cfg.cookie || '';    // 这里填cookie或外链URL
    if (cookieSource) {
        if (cookieSource.startsWith('http://') || cookieSource.startsWith('https://')) {
            try {
                let resp = await req(cookieSource, { headers: { 'User-Agent': 'Mozilla/5.0' }, timeout: 8000 });
                if (resp && resp.content) BILI_COOKIE = resp.content.trim();
            } catch (e) {}
        } else {
            BILI_COOKIE = cookieSource;
        }
    }
    
    if (!BILI_COOKIE) {
        await fetchGuestCookie();
    }
    
    await updateWbiKey();
    return '{}';
}

async function home(filter) {
    let typeStr = extConfig.type || '';     // 这里填分类URL
    for (let retry = 0; retry < 2; retry++) {
        if (typeStr.startsWith('http')) {
            try {
                let resp = await req(typeStr, { headers: { 'User-Agent': 'Mozilla/5.0' }, timeout: 8000 });
                if (resp && resp.content) {
                    let data = JSON.parse(resp.content);
                    if (data && data.class) return JSON.stringify(data);
                }
            } catch (e) {
                if (retry === 1) print('网络分类加载失败，使用内置分类');
                else await new Promise(resolve => setTimeout(resolve, 1000));
            }
        } else break;
    }
    let names = (typeStr.indexOf('#') > -1 ? typeStr : DEFAULT_TYPE).split('#').filter(n => n.trim());
    let classes = names.map(n => ({ type_id: n, type_name: n }));

    let filters = {};
    names.forEach(n => {
        filters[n] = [
            {
                key: 'order',
                name: '排序',
                value: [
                    { n: '综合排序', v: 'totalrank' },
                    { n: '最多点击', v: 'click' },
                    { n: '最新发布', v: 'pubdate' },
                    { n: '最多弹幕', v: 'dm' },
                    { n: '最多收藏', v: 'stow' }
                ]
            },
            {
                key: 'duration',
                name: '时长',
                value: [
                    { n: '全部时长', v: '0' },
                    { n: '60分钟以上', v: '4' },
                    { n: '30~60分钟', v: '3' },
                    { n: '10~30分钟', v: '2' },
                    { n: '10分钟以下', v: '1' }
                ]
            }
        ];
    });

    return JSON.stringify({ class: classes, filters: filters });
}

async function homeVod() { return JSON.stringify({ list: [] }); }

async function category(tid, pg, filterParams, extendParams) {
    if (typeof tid === 'string' && tid.endsWith('_clicklink')) tid = tid.split('_')[0];
    let page = parseInt(pg) || 1;
    let sel = {};
    if (filterParams) Object.assign(sel, filterParams);
    if (extendParams) Object.assign(sel, extendParams);
    let order = sel.order || 'totalrank';
    let duration = sel.duration || '0';
    let keyword = tid;
    if (sel.tid) keyword += ' ' + sel.tid;

    await updateWbiKey();
    const params = {
        search_type: 'video',
        keyword: keyword,
        order: order,
        duration: duration,
        page: page
    };
    const query = encWbi(params, wbiKeyCache.key);
    const url = 'https://api.bilibili.com/x/web-interface/wbi/search/type?' + query;

    for (let retry = 0; retry < 3; retry++) {
        try {
            let resp = await req(url, { headers: searchHeaders(), timeout: 8000 });
            if (!resp || !resp.content) continue;
            let data = JSON.parse(resp.content);
            let items = (data.data && data.data.result) || [];
            let list = items.map(v => {
                let img = v.pic || '';
                if (img.startsWith('//')) img = 'https:' + img;
                if (!img) img = PLACEHOLDER;
                let durationStr = fmtDuration(v.duration);
                let playStr = formatCount(v.play);
                let danmuStr = formatCount(v.danmaku);
                let remarkParts = [];
                if (durationStr) remarkParts.push(durationStr);
                if (playStr) remarkParts.push(playStr + '播放');
                if (danmuStr) remarkParts.push(danmuStr + '弹幕');
                return {
                    vod_id: v.bvid + '@' + v.aid,
                    vod_name: decodeHtml(v.title.replace(/<[^>]*>/g, '')),
                    vod_pic: img,
                    vod_remarks: remarkParts.join(' | ')
                };
            });
            let hasMore = list.length >= 20;
            if (!list.length) list.push({ vod_id: '0', vod_name: '无结果', vod_pic: PLACEHOLDER });
            return JSON.stringify({ list, page, pagecount: hasMore ? page + 1 : page, limit: 20, total: list.length });
        } catch (e) {
            if (retry === 2) {
                return JSON.stringify({ list: [{ vod_id: '0', vod_name: '请求失败', vod_pic: PLACEHOLDER }], page: 1, pagecount: 1 });
            }
            await new Promise(resolve => setTimeout(resolve, 1500));
        }
    }
}

async function detail(ids) {
    let idStr = Array.isArray(ids) ? ids[0] : ids;
    if (!idStr || idStr.indexOf('@') === -1) return JSON.stringify({ list: [] });
    let parts = idStr.split('@'), aid = parts[1];
    try {
        let viewUrl = 'https://api.bilibili.com/x/web-interface/view?aid=' + aid;
        let resp = await req(viewUrl, { headers: getHeaders(true) });
        let info = JSON.parse(resp.content).data;
        if (!info) return JSON.stringify({ list: [] });

        let title = decodeHtml((info.title || '').replace(/<[^>]*>/g, ''));
        let pic = info.pic || PLACEHOLDER;
        if (pic.startsWith('//')) pic = 'https:' + pic;
        let desc = info.desc || '';
        let duration = info.duration || 0;
        let owner = info.owner || {};
        let stat = info.stat || {};
        let tname = info.tname || '';
        let pubdate = info.pubdate || 0;
        let upName = owner.name || '未知';

        let follower = '';
        try {
            let statUrl = 'https://api.bilibili.com/x/relation/stat?vmid=' + owner.mid;
            let statResp = await req(statUrl, { headers: getHeaders(false) });
            let statData = JSON.parse(statResp.content).data;
            if (statData && statData.follower > 0) {
                follower = formatCount(statData.follower);
            }
        } catch (e) {}

        let director = '🆙 ' + '[a=cr:' + JSON.stringify({id: upName + '_clicklink', name: upName}) + '/]' + upName + '[/a]';
        if (follower) director += '　👥 ' + follower;

        let actor = '▶' + (stat.view || 0) + ' 💬' + (stat.danmaku || 0) + ' 👍' + (stat.like || 0) + ' 💰' + (stat.coin || 0) + ' ⭐' + (stat.favorite || 0);  
        let year = pubdate ? new Date(pubdate * 1000).getFullYear().toString() : '';

        let pages = info.pages || [];
        let bilibiliPlayUrls = pages.map(p => {
            let epTitle = (p.part || 'P' + p.page).replaceAll('#', '﹟').replaceAll('$', '﹩');
            return epTitle + '$' + aid + '+' + p.cid;
        });

        let relatedPlayUrls = [];
        try {
            let relatedUrl = 'https://api.bilibili.com/x/web-interface/archive/related?aid=' + aid;
            let relResp = await req(relatedUrl, { headers: getHeaders(true) });
            let relData = JSON.parse(relResp.content).data;
            if (relData && Array.isArray(relData)) {
                relData.forEach(rd => {
                    let cid = rd.cid;
                    let rdTitle = decodeHtml((rd.title || '').replaceAll('#', '﹟').replaceAll('$', '﹩'));
                    let aaid = rd.aid;
                    relatedPlayUrls.push(rdTitle + '$' + aaid + '+' + cid);
                });
            }
        } catch (e) {}

        let playFrom = 'B站';
        let playUrl = bilibiliPlayUrls.join('#');
        if (relatedPlayUrls.length > 0) {
            playFrom += '$$$相关推荐';
            playUrl += '$$$' + relatedPlayUrls.join('#');
        }

        return JSON.stringify({
            list: [{
                vod_id: idStr,
                vod_name: title,
                vod_pic: pic,
                vod_remarks: Math.floor(duration / 60) + '分钟',
                vod_content: desc,
                vod_play_from: playFrom,
                vod_play_url: playUrl,
                vod_director: director,
                vod_actor: actor,
                type_name: tname,
                vod_year: year
            }]
        });
    } catch (e) {
        return JSON.stringify({ list: [] });
    }
}

async function play(flag, id) {
    if (!id || id.indexOf('+') === -1) return JSON.stringify({ parse: 0, url: '' });
    let parts = id.split('+'), aid = parts[0], cid = parts[1];
    try {
        let dashUrl = 'https://api.bilibili.com/x/player/playurl?avid=' + aid + '&cid=' + cid + '&qn=127&fnval=4048&fourk=1';
        let resp = await req(dashUrl, { headers: getHeaders(true) });
        let data = JSON.parse(resp.content);
        if (!data.data || !data.data.dash) return JSON.stringify({ parse: 0, url: '' });
        
        let dash = data.data.dash;
        let videos = dash.video || [];
        let duration = dash.duration || 0;
        let minBuf = dash.min_buffer_time || 1.5;

        let rawAudios = dash.audio ? [...dash.audio] : [];
        if (dash.flac && dash.flac.audio) {
            if (Array.isArray(dash.flac.audio)) rawAudios.push(...dash.flac.audio);
            else rawAudios.push(dash.flac.audio);
        }
        if (dash.dolby && dash.dolby.audio) {
            if (Array.isArray(dash.dolby.audio)) rawAudios.push(...dash.dolby.audio);
            else rawAudios.push(dash.dolby.audio);
        }

        let audioList = [];
        let seenAudio = new Set();
           
        const audioPriority = { 30251: 1, 30250: 2, 30280: 3, 30232: 4, 30216: 5 };
        rawAudios.sort((a, b) => {
            let pA = audioPriority[a.id] || 99;
            let pB = audioPriority[b.id] || 99;
            return pA - pB;
        });
    
        for (let a of rawAudios) {
            if (a && a.id && !seenAudio.has(a.id)) {
                seenAudio.add(a.id);
                audioList.push(a);
            }
        }

        let formats = data.data.support_formats || [];
        if (formats.length === 0) {
            let aq = data.data.accept_quality || [];
            let ad = data.data.accept_description || [];
            formats = aq.map((q, i) => ({ quality: q, display_desc: ad[i] || q.toString() }));
        }
        let qnMap = {};
        formats.forEach(f => { qnMap[f.quality] = f.display_desc || f.new_description || f.quality.toString(); });

        let urlsArray = [];
        let seenStreams = new Set();
        
        videos.sort((a, b) => b.id - a.id);
        for (let v of videos) {
            let qn = v.id;
            
            let codecName = '';
            if (v.codecs) {
                if (v.codecs.includes('avc')) codecName = 'AVC';
                else if (v.codecs.includes('hev') || v.codecs.includes('hvc')) codecName = 'HEVC';
                else if (v.codecs.includes('av01')) codecName = 'AV1';
                else if (v.codecs.includes('dvh') || v.codecs.includes('dve')) codecName = '杜比';
            }
            
            let streamKey;
            if (qn <= 80) {
                streamKey = qn.toString();
                codecName = ''; 
            } else {
                streamKey = qn + '_' + codecName; 
            }
            
            if (!seenStreams.has(streamKey)) {
                seenStreams.add(streamKey);
                
                let baseName = qnMap[qn] || ('画质' + qn);
                if (qn === 126 || codecName === '杜比') {
                    baseName = '杜比视界';
                } else if (qn === 125) {
                    baseName = 'HDR真彩色(' + (codecName || 'HEVC') + ')';
                } else {
                    if (codecName) baseName += '(' + codecName + ')';
                }

                let mpd = buildMpd(v, audioList, duration, minBuf);
                let dataUri = 'data:application/dash+xml;base64,' + base64Encode(mpd);
                urlsArray.push({ name: baseName, url: dataUri, qn: qn, bw: v.bandwidth || 0 });
            }
        }

        if (urlsArray.length === 0) return JSON.stringify({ parse: 0, url: '' });

        urlsArray.sort((a, b) => {
            if (b.qn !== a.qn) return b.qn - a.qn;
            return b.bw - a.bw;
        });

        let arr = [];
        urlsArray.forEach(q => { 
            arr.push(q.name); 
            arr.push(q.url); 
        });

        return JSON.stringify({
            parse: 0, 
            jx: 0,
            url: arr,
            danmaku: 'https://api.bilibili.com/x/v1/dm/list.so?oid=' + cid,
            header: JSON.stringify(getHeaders(true))
        });
    } catch (e) { return JSON.stringify({ parse: 0, url: '' }); }
}

function buildMpd(video, audioList, duration, minBuf) {
    let mpd = '<?xml version="1.0" encoding="utf-8"?>\n';
    mpd += '<MPD xmlns="urn:mpeg:dash:schemas:mpd:2011" minBufferTime="PT' + minBuf + 'S" type="static" mediaPresentationDuration="PT' + duration + 'S" profiles="urn:mpeg:dash:profile:isoff-on-demand:2011">\n';
    mpd += '  <Period duration="PT' + duration + 'S">\n';
    mpd += '    <AdaptationSet contentType="video" mimeType="' + video.mime_type + '" segmentAlignment="true" startWithSAP="1">\n';
    mpd += '      <Representation id="' + video.id + '" bandwidth="' + video.bandwidth + '" codecs="' + video.codecs + '" width="' + video.width + '" height="' + video.height + '" frameRate="' + (video.frame_rate || video.frameRate || 25) + '" sar="' + (video.sar || '1:1') + '">\n';
    mpd += '        <BaseURL>' + (video.baseUrl || video.base_url).replace(/&/g, '&amp;') + '</BaseURL>\n';
    mpd += '        <SegmentBase indexRange="' + (video.segment_base ? video.segment_base.index_range : '0-0') + '">\n';
    mpd += '          <Initialization range="' + (video.segment_base ? video.segment_base.initialization : '0-0') + '"/>\n';
    mpd += '        </SegmentBase>\n';
    mpd += '      </Representation>\n';
    mpd += '    </AdaptationSet>\n';
    
    if (audioList && audioList.length > 0) {
        for (let audio of audioList) {
            let label = '';
            if (audio.id === 30251) label = '无损Hi-Res'; 
            else if (audio.id === 30250) label = '杜比全景声';
            else if (audio.id === 30280) label = '192k高音质';
            else if (audio.id === 30232) label = '132k标准';
            else if (audio.id === 30216) label = '64k流畅';
            else label = '音质_' + audio.id;

            mpd += '    <AdaptationSet contentType="audio" mimeType="' + audio.mime_type + '" segmentAlignment="true" startWithSAP="0" lang="' + label + '">\n';
            mpd += '      <Label>' + label + '</Label>\n';
            mpd += '      <Representation id="audio_' + audio.id + '" bandwidth="' + audio.bandwidth + '" codecs="' + audio.codecs + '">\n';
            mpd += '        <BaseURL>' + (audio.baseUrl || audio.base_url).replace(/&/g, '&amp;') + '</BaseURL>\n';
            mpd += '        <SegmentBase indexRange="' + (audio.segment_base ? audio.segment_base.index_range : '0-0') + '">\n';
            mpd += '          <Initialization range="' + (audio.segment_base ? audio.segment_base.initialization : '0-0') + '"/>\n';   
            mpd += '        </SegmentBase>\n';
            mpd += '      </Representation>\n';
            mpd += '    </AdaptationSet>\n';
        }
    }
    
    mpd += '  </Period>\n</MPD>';
    return mpd;
}

function base64Encode(str) {
    let bytes = [];
    for (let i = 0; i < str.length; i++) {
        let c = str.charCodeAt(i);
        if (c < 0x80) bytes.push(c);
        else if (c < 0x800) {
            bytes.push(0xc0 | (c >> 6), 0x80 | (c & 0x3f));
        } else if (c < 0x10000) {
            bytes.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
        } else {
            bytes.push(0xf0 | (c >> 18), 0x80 | ((c >> 12) & 0x3f), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
        }
    }
    let base64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
    let result = '';
    for (let i = 0; i < bytes.length; i += 3) {
        let b1 = bytes[i], b2 = bytes[i + 1] || 0, b3 = bytes[i + 2] || 0;
        result += base64.charAt(b1 >> 2);
        result += base64.charAt(((b1 & 0x3) << 4) | (b2 >> 4));
        result += (i + 1 < bytes.length) ? base64.charAt(((b2 & 0xf) << 2) | (b3 >> 6)) : '=';
        result += (i + 2 < bytes.length) ? base64.charAt(b3 & 0x3f) : '=';
    }
    return result;
}

async function search(keyword, quick, pg) { return category(keyword, pg || '1', {}, {}); }
async function searchContent(keyword, quick, page) { return search(keyword, quick, page); }

export function __jsEvalReturn() {
    return { init, home, homeVod, category, detail, play, search, searchContent };
}