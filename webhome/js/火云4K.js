// 本资源来源于互联网公开渠道，仅可用于个人学习爬虫技术。
// 严禁将其用于任何商业用途，下载后请于 24 小时内删除，搜索结果均来自源站，本人不承担任何责任。

import {Crypto, _} from 'assets://js/lib/cat.js';
let host = 'https://bubutv.top';
let device_id = '';
const pkg = 'com.sunshine.tv';
const ver = '4';
const device_id_cache_key = 'com.sunshine.tv_3qys_B7k7Dt56Rn';

// 分类筛选器：home(filter=true) 时返回给壳，category 的 extend 会收到用户选择。
const FILTER_OPTIONS = [
    {
        key: 'sort',
        name: '排序',
        value: [
            { n: '最热', v: 'hits' },
            { n: '最新', v: 'addtime' },
            { n: '评分', v: 'score' },
        ],
    },
    {
        key: 'class',
        name: '类型',
        value: [
            { n: '全部', v: '' },
            { n: '动作', v: '动作' },
            { n: '喜剧', v: '喜剧' },
            { n: '爱情', v: '爱情' },
            { n: '科幻', v: '科幻' },
            { n: '悬疑', v: '悬疑' },
            { n: '恐怖', v: '恐怖' },
            { n: '犯罪', v: '犯罪' },
            { n: '战争', v: '战争' },
            { n: '动画', v: '动画' },
            { n: '剧情', v: '剧情' },
            { n: '纪录', v: '纪录' },
        ],
    },
    {
        key: 'area',
        name: '地区',
        value: [
            { n: '全部', v: '' },
            { n: '大陆', v: '大陆' },
            { n: '香港', v: '香港' },
            { n: '台湾', v: '台湾' },
            { n: '美国', v: '美国' },
            { n: '韩国', v: '韩国' },
            { n: '日本', v: '日本' },
            { n: '泰国', v: '泰国' },
            { n: '英国', v: '英国' },
            { n: '法国', v: '法国' },
            { n: '印度', v: '印度' },
            { n: '其它', v: '其它' },
        ],
    },
    {
        key: 'year',
        name: '年份',
        value: [
            { n: '全部', v: '' },
            { n: '2026', v: '2026' },
            { n: '2025', v: '2025' },
            { n: '2024', v: '2024' },
            { n: '2023', v: '2023' },
            { n: '2022', v: '2022' },
            { n: '2021', v: '2021' },
            { n: '2020', v: '2020' },
            { n: '2019', v: '2019' },
            { n: '2018', v: '2018' },
            { n: '更早', v: '更早' },
        ],
    },
];

async function init(cfg) {
    const ext = cfg.ext;
    if (typeof cfg.ext === 'string' && cfg.ext.startsWith('http')) {
        host = cfg.ext.trim().replace(/\/$/, '');
    }
}

async function home(filter) {
    const hd = await getHeaders();
    const resp = await req(`${host}/api.php/app/index/home`, { headers: hd });
    const json = JSON.parse(resp.content);
    const classes = _.map(json.data.categories, (i) => ({
        'type_id': i.type_name,
        'type_name': i.type_name
    }));
    const videos = [];
    for (const cat of json.data.categories) {
        videos.push(...arr2vods(cat.videos));
    }
    const result = { class: classes, list: videos };
    if (filter) {
        result.filters = buildFilters(classes);
    }
    return JSON.stringify(result);
}

function buildFilters(classes) {
    const filters = {};
    for (const item of classes || []) {
        const typeId = item && item.type_id ? item.type_id.toString().trim() : '';
        if (typeId) {
            // 每个分类共用一套筛选项；壳会按当前分类读取对应筛选器。
            filters[typeId] = FILTER_OPTIONS;
        }
    }
    return filters;
}

async function homeVod() {
    return JSON.stringify({ list: [] });
}

async function category(tid, pg, filter, extend) {
    const hd = await getHeaders();
    extend = extend && typeof extend === 'object' ? extend : {};
    const params = {
        type_name: tid,
        page: pg,
        sort: extend.sort || 'hits',
    };
    // 将壳传回来的筛选条件透传给接口；空值代表“全部”，不拼到请求里。
    for (const key of ['class', 'area', 'year', 'lang', 'letter']) {
        if (extend[key] !== undefined && extend[key] !== null && extend[key] !== '') {
            params[key] = extend[key];
        }
    }
    const query = _.map(Object.keys(params), (key) => `${encodeURIComponent(key)}=${encodeURIComponent(params[key])}`).join('&');
    const url = `${host}/api.php/app/filter/vod?${query}`;
    const resp = await req(url, { headers: hd });
    const json = JSON.parse(resp.content);
    const data = json.data || [];
    const list = Array.isArray(data) ? data : (data.list || data.data || []);
    const page = parseInt(pg);
    const limit = parseInt(json.limit || data.limit || 24);
    // 该接口实际有后续页，但返回的 pageCount 固定为 1，会导致壳认为没有下一页。
    // 只要当前页有数据，就把 pagecount 设置为下一页，滑到底时壳才会继续请求。
    const pageCount = list.length > 0 ? page + 1 : page;
    return JSON.stringify({
        list: arr2vods(list),
        pagecount: pageCount,
        page: page,
        limit: limit,
        total: list.length > 0 ? 999999 : page * limit
    });
}

async function search(wd, quick, pg=1) {
    const hd = await getHeaders();
    const url = `${host}/api.php/app/search/index?wd=${encodeURIComponent(wd)}&page=${pg}&limit=15`;
    const resp = await req(url, { headers: hd });
    const json = JSON.parse(resp.content);
    return JSON.stringify({
        list: arr2vods(json.data),
        pagecount: json.pageCount,
        page: parseInt(pg)
    });
}

async function detail(id) {
    const hd = await getHeaders();
    const resp = await req(`${host}/api.php/app/vod/get_detail?vod_id=${id}`, { headers: hd });
    const json = JSON.parse(resp.content);
    const data = json.data[0];
    const vodplayer = json.vodplayer;
    const shows = [];
    const play_urls = [];
    const raw_shows = data.vod_play_from.split('$$$');
    const raw_urls_list = data.vod_play_url.split('$$$');
    for (let i = 0; i < raw_shows.length; i++) {
        const show_code = raw_shows[i];
        const urls_str = raw_urls_list[i];
        let need_parse = 0;
        let is_show = 0;
        let name = show_code;
        const player_info = _.find(vodplayer, (p) => p.from === show_code);
        if (player_info) {
            is_show = 1;
            need_parse = player_info.decode_status;
            if (show_code.toLowerCase() !== player_info.show.toLowerCase()) {
                name = `${player_info.show} (${show_code})`;
            }
        }
        if (is_show === 1) {
            const urls = [];
            for (const url_item of urls_str.split('#')) {
                if (url_item.includes('$')) {
                    const [episode, url] = url_item.split('$');
                    urls.push(`${episode}$${show_code}@${need_parse}@${url}`);
                }
            }
            if (urls.length > 0) {
                play_urls.push(urls.join('#'));
                shows.push(name);
            }
        }
    }
    const video = {
        'vod_id': data.vod_id.toString(),
        'vod_name': data.vod_name,
        'vod_pic': data.vod_pic,
        'vod_remarks': data.vod_remarks,
        'vod_year': data.vod_year,
        'vod_area': data.vod_area,
        'vod_actor': data.vod_actor,
        'vod_director': data.vod_director,
        'vod_content': data.vod_content,
        'vod_play_from': shows.join('$$$'),
        'vod_play_url': play_urls.join('$$$'),
        'type_name': data.vod_class
    };
    return JSON.stringify({ list: [video] });
}

async function play(flag, vid, flags) {
    const parts = vid.split('@');
    const play_from = parts[0];
    const need_parse = parts[1];
    const raw_url = parts[2];
    let url = '';
    let jx = 0;
    if (need_parse === '1') {
        try {
            const hd = await getHeaders();
            const apiUrl = `${host}/api.php/app/decode/url/?url=${encodeURIComponent(raw_url)}&vodFrom=${play_from}`;
            const resp = await req(apiUrl, { headers: hd, timeout: 30000 });
            const json = JSON.parse(resp.content);
            if (json.data && json.data.startsWith('http')) {
                url = json.data;
            }
        } catch (e) {
            console.error('Play decode error:', e);
        }
    }
    if (!url) {
        url = raw_url;
        if (/(www\.iqiyi|v\.qq|v\.youku|www\.mgtv|www\.bilibili)\.com/.test(raw_url)) {
            jx = 1;
        }
    }
    return JSON.stringify({ jx: jx, parse: 0, url: url, header: {'User-Agent': 'com.sunshine.tv/1.2.0 (Linux;Android 15) AndroidXMedia3/1.4.1'}});
}

async function getHeaders() {
    const timestamp = Math.floor(Date.now() / 1000).toString();
    const nonce = randomStr(3, '0123456789');
    if (!device_id) {
        device_id = await local.get('cache', device_id_cache_key);
        if (!device_id || device_id.length !== 16) {
            device_id = randomStr(16);
            await local.set('cache', device_id_cache_key, device_id);
        }
    }
    const sign_str = `finger=SF-C3B2B41F6EFFFF9869176CF68F6790E8F07506FC88632C94B4F5F0430D5498CA&id=${pkg}&nonce=${nonce}&sk=SK-thanks&time=${timestamp}&v=${ver}`;
    const sign = sha256(sign_str);
    return {
        'User-Agent': 'okhttp/4.12.0',
        'Accept': 'application/json',
        'x-aid': pkg,
        'x-ave': ver,
        'x-time': timestamp,
        'x-nonc': nonce,
        'x-sign': sign,
        'x-device-id': device_id,
        'x-device-brand': 'vivo',
        'x-device-model': 'V2309A',
        'x-update-id': '0245861b-2ebf-5524-389d-f983830651ec'
    };
}

function arr2vods(arr) {
    return _.map(arr, (i) => {
        let type_name = i.type_name || '';
        if (i.vod_class) {
            type_name = type_name + (type_name ? ',' : '') + i.vod_class;
        }
        return {
            'vod_id': i.vod_id.toString(),
            'vod_name': i.vod_name,
            'vod_pic': i.vod_pic,
            'vod_remarks': i.vod_remarks,
            'type_name': type_name,
            'vod_year': i.vod_year
        };
    });
}

function randomStr(len, chars = '0123456789abcdef') {
    let str = '';
    for (let i = 0; i < len; i++) {
        str += chars[_.random(0, chars.length - 1)];
    }
    return str;
}

function sha256(text) {
    return Crypto.SHA256(text).toString().toUpperCase();
}

export function __jsEvalReturn() {
    return {
        init: init,
        home: home,
        homeVod: homeVod,
        category: category,
        search: search,
        detail: detail,
        play: play
    };
}
