import { load } from 'assets://js/lib/cat.js';

var BILI_COOKIE = '';
var isLogin = false;
var isVip = false;

function getHeaders(needCookie) {
    var cookie = BILI_COOKIE || 'buvid3=84B0395D-C9F2-C490-E92E-A09AB48FE26E71636infoc';
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0',
        'Referer': 'https://www.bilibili.com',
        'Cookie': needCookie ? cookie.replace(/,/g, '%2C') : 'buvid3=84B0395D-C9F2-C490-E92E-A09AB48FE26E71636infoc'
    };
}

var FIXED_FILTERS = [
    { name: '排序', key: 'order', value: [
        { v: '0', n: '更新时间' }, { v: '1', n: '弹幕数量' }, { v: '2', n: '播放数量' },
        { v: '3', n: '追看人数' }, { v: '4', n: '最高评分' }, { v: '5', n: '开播时间' }, { v: '6', n: '上映时间' }
    ]},
    { name: '付费', key: 'season_status', value: [
        { v: '-1', n: '全部' }, { v: '1', n: '免费' }, { v: '2%2C6', n: '付费' }, { v: '4%2C6', n: '大会员' }
    ]}
];
var ALL_FILTERS = {};
['1','3','4','2','7','5'].forEach(function(t) { ALL_FILTERS[t] = FIXED_FILTERS; });

async function init(config) {
    var json = {};
    try { json = JSON.parse(config); } catch (e) {}
       
    var cookieSource = json.cookie || '';    // 这里填cookie或外链URL
    if (cookieSource) {
        if (cookieSource.startsWith('http://') || cookieSource.startsWith('https://')) {
            try {
                var resp = await req(cookieSource, { headers: { 'User-Agent': 'Mozilla/5.0' }, timeout: 8000 });
                if (resp && resp.content) {
                    BILI_COOKIE = resp.content.trim();
                }
            } catch (e) { BILI_COOKIE = ''; }
        } else {
            BILI_COOKIE = cookieSource;
        }
    }

    try {
        var navResp = await req('https://api.bilibili.com/x/web-interface/nav', { headers: getHeaders(true) });
        var navData = JSON.parse(navResp.content);
        if (navData.data) {
            isLogin = navData.data.isLogin || false;
            isVip = navData.data.vipStatus === 1;
        }
    } catch (e) {}
    return '{}';
}

async function home(filter) {
    var classes = [
        { type_id: '1', type_name: '番剧' }, 
        { type_id: '4', type_name: '国创' },
        { type_id: '2', type_name: '电影' },
        { type_id: '5', type_name: '电视剧' },
        { type_id: '3', type_name: '纪录' },       
        { type_id: '7', type_name: '综艺' }
    ];
    return JSON.stringify({ class: classes, filters: ALL_FILTERS });
}

async function homeVod() { return JSON.stringify({ list: [] }); }

async function category(tid, pg, filterParams, extendParams) {
    var page = parseInt(pg) || 1;
    var typeId = tid;
    var params = { order: '0', season_status: '-1', style_id: -1, sort: -1, area: -1 };
    var sel = {};
    if (typeof filterParams === 'object') Object.assign(sel, filterParams);
    if (typeof extendParams === 'object') Object.assign(sel, extendParams);
    if (sel.order) params.order = sel.order;
    if (sel.season_status) params.season_status = sel.season_status;
    var query = 'order=' + params.order + '&season_status=' + params.season_status +
        '&style_id=' + params.style_id + '&sort=' + params.sort + '&area=' + params.area +
        '&pagesize=20&type=1&season_type=' + typeId + '&page=' + page;
    var url = 'https://api.bilibili.com/pgc/season/index/result?' + query;
    var resp = await req(url, { headers: getHeaders(false) });
    if (!resp || !resp.content) return JSON.stringify({ list: [] });
    var data = JSON.parse(resp.content);
    var list = [];
    var seasons = (data.data && data.data.list) ? data.data.list : [];
    seasons.forEach(function(item) {
        list.push({
            vod_id: item.season_id,
            vod_name: item.title.replace(/<[^>]*>/g, ''),
            vod_pic: item.cover,
            vod_remarks: item.index_show || ''
        });
    });
    var hasMore = data.data && data.data.has_next === 1;
    return JSON.stringify({ list: list, page: page, pagecount: hasMore ? page + 1 : page, limit: 20, total: hasMore ? (page+1)*20 : page*20 });
}

async function detail(ids) {
    var seasonId = Array.isArray(ids) ? ids[0] : ids;
    if (!seasonId) return JSON.stringify({ list: [] });
    var detailUrl = 'https://api.bilibili.com/pgc/view/web/season?season_id=' + seasonId;
    var resp = await req(detailUrl, { headers: getHeaders(true) });
    if (!resp || !resp.content) return JSON.stringify({ list: [] });
    var data = JSON.parse(resp.content);
    var season = data.result;
    if (!season) return JSON.stringify({ list: [] });

    // 基础信息
    var title = season.title || '未知剧名';
    var cover = season.cover || '';
    var desc = season.evaluate || '';
    var actors = season.actors || '';
    var episodes = season.episodes || [];
    var typeName = season.share_sub_title || ''; 
    var areas = (season.areas && season.areas[0]) ? season.areas[0].name : ''; 
    var pubDate = (season.publish && season.publish.pub_time) ? season.publish.pub_time.substring(0, 4) : ''; 
    var newEpDesc = (season.new_ep && season.new_ep.desc) ? season.new_ep.desc : ''; 
    var stat = season.stat || {};
    var danmakus = stat.danmakus || 0;
    var likes = stat.likes || 0;
    var coins = stat.coins || 0;
    var favorites = stat.favorites || 0;

    var scoreText = '';
    if (season.rating && season.rating.score) {
        scoreText = '评分: ' + season.rating.score + '　' + (season.subtitle || '');
    } else {
        scoreText = '暂无评分' + '　' + (season.subtitle || '');
    }

    function zh(num) {
        if (Number(num) > 1e8) return (num / 1e8).toFixed(2) + '亿';
        if (Number(num) > 1e4) return (num / 1e4).toFixed(2) + '万';
        return num.toString();
    }

    var statusText = '弹幕: ' + zh(danmakus) + '　点赞: ' + zh(likes) + '　投币: ' + zh(coins) + '　追番追剧: ' + zh(favorites);

    var playUrls = episodes.map(function(ep) {
        var part = (ep.share_copy || ep.title || '剧集').replace('#', '\uff03').replace('$', '\uff04');
        return part + '$' + ep.aid + '+' + ep.cid;
    }).join('#');

    return JSON.stringify({
        list: [{
            vod_id: seasonId,
            vod_name: title,
            vod_pic: cover,
            vod_remarks: episodes.length + '集 ' + (newEpDesc || ''),
            vod_content: desc,
            vod_actor: actors,
            vod_director: scoreText,
            vod_area: areas,
            type_name: typeName,
            vod_year: pubDate,
            vod_play_from: '哔哩影视',
            vod_play_url: playUrls
        }]
    });
}

async function search(keyword, quick, pg) {
    var page = pg || '1';
    var keywordEnc = encodeURIComponent(keyword);
    var ftUrl = 'https://api.bilibili.com/x/web-interface/search/type?search_type=media_ft&keyword=' + keywordEnc + '&page=' + page;
    var bangumiUrl = 'https://api.bilibili.com/x/web-interface/search/type?search_type=media_bangumi&keyword=' + keywordEnc + '&page=' + page;
    var results = [];
    try {
        var [ftResp, bangumiResp] = await Promise.all([
            req(ftUrl, { headers: getHeaders(false) }),
            req(bangumiUrl, { headers: getHeaders(false) })
        ]);
        [ftResp, bangumiResp].forEach(function(resp) {
            if (!resp || !resp.content) return;
            var data = JSON.parse(resp.content);
            var items = (data.data && data.data.result) ? data.data.result : [];
            items.forEach(function(item) {
                results.push({
                    vod_id: item.season_id,
                    vod_name: item.title.replace(/<[^>]*>/g, ''),
                    vod_pic: item.cover,
                    vod_remarks: item.index_show || ''
                });
            });
        });
    } catch (e) {}
    var seen = new Set();
    var finalList = [];
    results.forEach(function(item) { if (!seen.has(item.vod_id)) { seen.add(item.vod_id); finalList.push(item); } });
    return JSON.stringify({ list: finalList, page: parseInt(page), pagecount: 1, limit: finalList.length, total: finalList.length });
}

async function play(flag, id) {
    if (!id || id.indexOf('+') === -1) return JSON.stringify({ parse: 0, url: '' });
    var parts = id.split('+');
    var aid = parts[0], cid = parts[1];

    // ===== 优先 DASH =====
    try {
        var dashUrl = 'https://api.bilibili.com/x/player/playurl?avid=' + aid + '&cid=' + cid + '&qn=127&fnval=4048&fnver=0&fourk=1&platform=pc';
        var resp = await req(dashUrl, { headers: getHeaders(true), timeout: 10000 });
        var json = JSON.parse(resp.content);
        var result = json.result || json.data;
        if (result && result.dash) {
            var dash = result.dash;
            var videos = dash.video || [];
            var audios = dash.audio || [];
            var duration = dash.duration || 0;
            var minBuf = dash.min_buffer_time || 1.5;

            var formats = result.support_formats || [];
            if (formats.length === 0) {
                var aq = result.accept_quality || [];
                var ad = result.accept_description || [];
                formats = aq.map(function(q, i) { return { quality: q, display_desc: ad[i] || q.toString() }; });
            }
            var qnMap = {};
            formats.forEach(function(f) { qnMap[f.quality] = f.display_desc || f.new_description || f.quality.toString(); });

            var audio = null;
            for (var i = 0; i < audios.length; i++) {
                if (!audio || audios[i].id > audio.id) audio = audios[i];
            }

            var urlList = [];
            var seenQn = new Set();
            videos.sort(function(a, b) { return b.id - a.id; });
            for (var j = 0; j < videos.length; j++) {
                var v = videos[j];
                var qn = v.id;
                if (qnMap[qn] && !seenQn.has(qn)) {
                    seenQn.add(qn);
                    var mpd = buildMpd(v, audio, duration, minBuf);
                    var dataUri = 'data:application/dash+xml;base64,' + base64Encode(mpd);
                    urlList.push(qnMap[qn], dataUri);
                }
            }
            if (urlList.length > 0) {
                return JSON.stringify({
                    parse: 0, jx: 0,
                    url: urlList,
                    danmaku: 'https://api.bilibili.com/x/v1/dm/list.so?oid=' + cid,
                    header: JSON.stringify(getHeaders(true))
                });
            }
        }
    } catch (e) {}

    // ===== FLV 后备：利用真实 quality 去重 =====
    try {
        var infoUrl = 'https://api.bilibili.com/pgc/player/web/playurl?avid=' + aid + '&cid=' + cid + '&qn=0&fnval=1&fourk=1';
        var infoResp = await req(infoUrl, { headers: getHeaders(true), timeout: 5000 });
        var infoJson = JSON.parse(infoResp.content);
        var infoResult = infoJson.result || infoJson.data;
        var acceptQuality = (infoResult && infoResult.accept_quality) ? infoResult.accept_quality : [80, 64, 32, 16];
        var acceptDesc = (infoResult && infoResult.accept_description) ? infoResult.accept_description : [];

        var descMap = {};
        for (var i = 0; i < acceptQuality.length; i++) {
            descMap[acceptQuality[i]] = acceptDesc[i] || acceptQuality[i].toString();
        }

        var collected = {}; // key: 真实qn, value: {url, desc}
        // 从高到低遍历
        acceptQuality.sort(function(a,b){ return b - a; });
        for (var i = 0; i < acceptQuality.length; i++) {
            var qn = acceptQuality[i];
            try {
                var flvUrl = 'https://api.bilibili.com/pgc/player/web/playurl?avid=' + aid + '&cid=' + cid + '&qn=' + qn + '&fnval=1&fourk=1';
                var flvResp = await req(flvUrl, { headers: getHeaders(true), timeout: 5000 });
                var flvJson = JSON.parse(flvResp.content);
                var flvResult = flvJson.result || flvJson.data;
                if (flvResult && flvResult.durl && flvResult.durl.length > 0) {
                    // 以服务器返回的实际质量为准
                    var realQn = flvResult.quality !== undefined ? flvResult.quality : qn;
                    if (!collected[realQn]) {
                        var name = descMap[realQn] || flvResult.format || realQn.toString();
                        collected[realQn] = { url: flvResult.durl[0].url, desc: name };
                    }
                }
            } catch (e2) {}
        }

        var names = [], urls = [];
        // 按真实画质从高到低输出
        var keys = Object.keys(collected).sort(function(a,b){ return b - a; });
        for (var k = 0; k < keys.length; k++) {
            var item = collected[keys[k]];
            names.push(item.desc);
            urls.push(item.url);
        }

        if (urls.length > 0) {
            var urlList = [];
            for (var m = 0; m < names.length; m++) {
                urlList.push(names[m], urls[m]);
            }
            return JSON.stringify({
                parse: 0, jx: 0,
                url: urlList,
                danmaku: 'https://api.bilibili.com/x/v1/dm/list.so?oid=' + cid,
                header: JSON.stringify(getHeaders(true))
            });
        }
    } catch (e3) {}

    return JSON.stringify({ parse: 0, url: '' });
}

function buildMpd(video, audio, duration, minBuf) {
    var mpd = '<?xml version="1.0" encoding="utf-8"?>\n';
    mpd += '<MPD xmlns="urn:mpeg:dash:schemas:mpd:2011" minBufferTime="PT' + minBuf + 'S" type="static" mediaPresentationDuration="PT' + duration + 'S" profiles="urn:mpeg:dash:profile:isoff-on-demand:2011">\n';
    mpd += '  <Period duration="PT' + duration + 'S">\n';
    mpd += '    <AdaptationSet contentType="video" mimeType="' + video.mime_type + '" segmentAlignment="true" startWithSAP="1">\n';
    mpd += '      <Representation id="' + video.id + '" bandwidth="' + video.bandwidth + '" codecs="' + video.codecs + '" width="' + video.width + '" height="' + video.height + '" frameRate="' + (video.frame_rate || video.frameRate || 25) + '" sar="' + (video.sar || '1:1') + '">\n';
    mpd += '        <BaseURL>' + (video.baseUrl || video.base_url || '').replace(/&/g, '&amp;') + '</BaseURL>\n';
    mpd += '        <SegmentBase indexRange="' + (video.segment_base ? video.segment_base.index_range : '0-0') + '">\n';
    mpd += '          <Initialization range="' + (video.segment_base ? video.segment_base.initialization : '0-0') + '"/>\n';
    mpd += '        </SegmentBase>\n';
    mpd += '      </Representation>\n';
    mpd += '    </AdaptationSet>\n';
    if (audio) {
        mpd += '    <AdaptationSet contentType="audio" mimeType="' + audio.mime_type + '" segmentAlignment="true" startWithSAP="0">\n';
        mpd += '      <Representation id="' + audio.id + '" bandwidth="' + audio.bandwidth + '" codecs="' + audio.codecs + '">\n';
        mpd += '        <BaseURL>' + (audio.baseUrl || audio.base_url || '').replace(/&/g, '&amp;') + '</BaseURL>\n';
        mpd += '        <SegmentBase indexRange="' + (audio.segment_base ? audio.segment_base.index_range : '0-0') + '">\n';
        mpd += '          <Initialization range="' + (audio.segment_base ? audio.segment_base.initialization : '0-0') + '"/>\n';
        mpd += '        </SegmentBase>\n';
        mpd += '      </Representation>\n';
        mpd += '    </AdaptationSet>\n';
    }
    mpd += '  </Period>\n</MPD>';
    return mpd;
}

function base64Encode(str) {
    var bytes = [];
    for (var i = 0; i < str.length; i++) {
        var c = str.charCodeAt(i);
        if (c < 0x80) bytes.push(c);
        else if (c < 0x800) bytes.push(0xc0 | (c >> 6), 0x80 | (c & 0x3f));
        else if (c < 0x10000) bytes.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
        else bytes.push(0xf0 | (c >> 18), 0x80 | ((c >> 12) & 0x3f), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
    }
    var base64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
    var result = '';
    for (var i = 0; i < bytes.length; i += 3) {
        var b1 = bytes[i], b2 = bytes[i + 1] || 0, b3 = bytes[i + 2] || 0;
        result += base64.charAt(b1 >> 2);
        result += base64.charAt(((b1 & 0x3) << 4) | (b2 >> 4));
        result += (i + 1 < bytes.length) ? base64.charAt(((b2 & 0xf) << 2) | (b3 >> 6)) : '=';
        result += (i + 2 < bytes.length) ? base64.charAt(b3 & 0x3f) : '=';
    }
    return result;
}

export function __jsEvalReturn() {
    return { init, home, homeVod, category, detail, search, play };
}