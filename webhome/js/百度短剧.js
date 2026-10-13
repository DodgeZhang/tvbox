/*
@header({
  searchable: 1,
  filterable: 0,
  quickSearch: 1,
  title: '百度短剧',
  lang: 'cat'
})
*/
import { Crypto as CryptoJS } from 'assets://js/lib/cat.js';

let siteName = '百度短剧', siteKey = '', siteType = 0;

let UA = "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36";
let clarity_order = { '蓝光': 1, '超清': 2, '标清': 3 };

let rule = {
    host: 'https://mbd.baidu.com',
    detailHost: 'https://sv.baidu.com',
    listUrl: '/feedapi/v1/videoserver/playlets/list?service=bdbox',
    searchUrl: '/feedapi/v1/videoserver/playlets/search?service=bdbox',
    detailUrl: '/haokan/ui-video/playlet/rec/detail?log=vhk&tn=1020970b&ctn=1008350n&blur=1',
    playUrl: '/appui/api?cmd=video/relate&log=vhk&tn=1020970b&ctn=1008350n&blur=1',
};

const headers = {
    'User-Agent': UA,
    'Content-Type': 'application/x-www-form-urlencoded',
    'Accept': 'application/json'
};

function init(cfg) {
    siteName = cfg.skey?.split('_')[1] || cfg.skey || '百度短剧';
    siteKey = cfg.skey;
    siteType = cfg.stype;
}

function safeJSONParse(str, defaultValue = {}) {
    if (!str || typeof str === 'object') return str || defaultValue;
    try {
        return JSON.parse(str);
    } catch {
        return defaultValue;
    }
}

async function request(url, options = {}) {
    const reqHeaders = { ...headers, ...options.headers };
    let postType = reqHeaders['Content-Type']?.includes('json') ? 'json' :
        reqHeaders['Content-Type']?.includes('form') ? 'form' : '';

    try {
        const response = await req(url, {
            method: options.method || 'GET',
            headers: reqHeaders,
            data: options.data,
            postType: postType,
            timeout: options.timeout || 15000
        });
        const content = response?.content || response?.data || response;
        return typeof content === 'object' ? content : safeJSONParse(content);
    } catch {
        return null;
    }
}

function home(filter) {
    let he = ["全部", "新剧", "限时免费", "精选", "独播"];
    let ticailist = [
        "神医", "连续剧", "都市", "现代言情", "异能", "逆袭", "甜宠", "总裁", "萌宝", "战神", "宫斗宅斗", "神豪",
        "虐恋", "闪婚", "玄幻", "穿越重生", "年代", "家庭伦理", "古代言情", "武侠武打", "赘婿", "单元剧", "青春校园",
        "历史架空", "王妃", "鉴宝", "科幻", "军旅战争", "种田"
    ];

    let classes = he.map(name => ({ type_id: name, type_name: name }));
    classes = classes.concat(ticailist.map(name => ({
        type_id: name === "全部" ? "全部题材" : name,
        type_name: name
    })));
    return JSON.stringify({ class: classes, filters: {} });
}

async function homeVod() {
    const categoryResult = await category('新剧', 1, {}, {});
    const list = safeJSONParse(categoryResult).list || [];
    return JSON.stringify({ list: list.slice(0, 12) });
}

async function category(tid, pg, filter, extend) {
    pg = pg <= 0 ? 1 : pg;
    let sub = ["新剧", "限时免费", "精选", "独播"].includes(tid) ? tid : "新剧";
    let tcsub = (tid === "全部" || tid === "全部题材") ? "" : tid;
    let t = Math.floor(Date.now() / 1000);
    let version = await md5(t + "v2");

    let postData = {
        'data': JSON.stringify({
            "data": {
                "extRequest": { "flow_tabid": "13" },
                "from": "feed",
                "page": "channel_video_landing",
                "pd": "feed",
                "refreshIndex": pg,
                "cursor": "",
                "theme": "",
                "timestamp": t,
                "version": version,
                "themes": [
                    { "kind": "综合", "names": [sub] },
                    { "kind": "题材", "names": [tcsub] }
                ]
            }
        })
    };

    const res = await request(`${rule.host}${rule.listUrl}`, { method: 'POST', data: postData });
    let videos = (res?.data?.items || []).map(it => ({
        vod_id: it.collId || '',
        vod_name: it.title || '未知标题',
        vod_pic: it.img || '',
        vod_remarks: it.updateStatus || '',
        vod_content: it.description || ''
    }));

    return JSON.stringify({
        page: pg,
        pagecount: pg + 1,
        limit: videos.length,
        total: videos.length * (pg + 1),
        list: videos
    });
}

async function detail(id) {
    const res = await request(`${rule.detailHost}${rule.detailUrl}`, {
        method: 'POST',
        data: { playlet_id: id, vid: "undefined" }
    });
    const dthtml = res?.data;
    const vids = dthtml?.vid_list || [];
    if (!vids.length) return JSON.stringify({ list: [] });

    const playArr = vids.map((vid, index) => `第${index + 1}集$${vid}`);
    const vod = {
        vod_id: id,
        vod_name: dthtml.playlet_title || '未知剧名',
        vod_pic: dthtml.playlet_poster || '',
        vod_content: dthtml.description || '',
        vod_remarks: `共${vids.length}集 热度值:${dthtml.hot_value || 0}`,
        vod_director: dthtml.tag_text || '',
        vod_year: dthtml.create_time || '',
        vod_play_from: "百度短剧",
        vod_play_url: playArr.join('#')
    };

    return JSON.stringify({ list: [vod] });
}

async function play(flag, id, flags) {
    let res = await request(`${rule.detailHost}${rule.playUrl}`, {
        method: 'POST',
        data: { method: "post", vid: id }
    });
    const video = res?.["video/relate"]?.data?.cur_video;
    if (!video?.clarityUrl) return JSON.stringify({ parse: 0, url: '', msg: '获取播放链接失败' });

    const urls = video.clarityUrl.filter(item => item?.url).map(item => ({
        title: item.title,
        url: item.url,
        order: clarity_order[item.title] || 999
    })).sort((a, b) => a.order - b.order);

    if (!urls.length) return JSON.stringify({ parse: 0, url: '', msg: '暂无可用播放地址' });

    const flat = urls.flatMap(item => [item.title, item.url]);
    return JSON.stringify({
        parse: 0,
        url: flat,
        header: { 'User-Agent': UA, 'Referer': rule.host }
    });
}

async function search(wd, quick, pg) {
    pg = pg <= 0 ? 1 : pg;
    let postData = {
        'data': JSON.stringify({
            "query": wd,
            "page": pg,
            "attribute": ["title"],
            "fe_page_type": "search",
            "extra": {
                "tab_id": "216",
                "flow_tabid": "13",
                "shortplay_source": "feed",
                "from": "feed",
                "tab_type": "搜索",
                "sub_template": "playlet_search_result"
            }
        })
    };

    const res = await request(`${rule.host}${rule.searchUrl}`, {
        method: 'POST',
        data: postData
    });
    let videos = (res?.data?.itemList || []).map(it => ({
        vod_id: it.nid?.split("_")[1] || '',
        vod_name: it.title || '未知标题',
        vod_pic: it.img || '',
        vod_remarks: (it.collNum || '0') + '集',
        vod_content: it.description || ''
    }));

    return JSON.stringify({
        page: pg,
        pagecount: pg + 1,
        limit: videos.length,
        total: videos.length * (pg + 1),
        list: videos
    });
}

async function md5(str) {
    return CryptoJS.MD5(str).toString(CryptoJS.enc.Hex).toLowerCase();
}

export function __jsEvalReturn() {
    return { init, home, homeVod, category, detail, play, search };
}