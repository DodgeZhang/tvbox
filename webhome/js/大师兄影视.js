// 本资源来源于互联网公开渠道，仅可用于个人学习爬虫技术。
// 严禁将其用于任何商业用途，下载后请于 24 小时内删除，搜索结果均来自源站，本人不承担任何责任。

import {Crypto, _} from 'assets://js/lib/cat.js';
let host = 'https://www.dsxys.me';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36';

// 分类筛选器：home(filter=true) 时返回给壳，category 的 extend 会收到用户选择。
const FILTER_OPTIONS = [
    {
        key: 'sort',
        name: '排序',
        value: [
            { n: '时间', v: 'time' },
            { n: '人气', v: 'hits' },
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
            { n: '奇幻', v: '奇幻' },
            { n: '冒险', v: '冒险' },
            { n: '灾难', v: '灾难' },
            { n: '恐怖', v: '恐怖' },
            { n: '惊悚', v: '惊悚' },
            { n: '剧情', v: '剧情' },
            { n: '战争', v: '战争' },
            { n: '歌舞', v: '歌舞' },
            { n: '经典', v: '经典' },
            { n: '悬疑', v: '悬疑' },
            { n: '动画', v: '动画' },
            { n: '同性', v: '同性' },
            { n: '网络电影', v: '网络电影' },
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
            { n: '日本', v: '日本' },
            { n: '韩国', v: '韩国' },
            { n: '欧美', v: '欧美' },
            { n: '英国', v: '英国' },
            { n: '泰国', v: '泰国' },
            { n: '其它', v: '其它' },
        ],
    },
    {
        key: 'lang',
        name: '语言',
        value: [
            { n: '全部', v: '' },
            { n: '国语', v: '国语' },
            { n: '英语', v: '英语' },
            { n: '粤语', v: '粤语' },
            { n: '韩语', v: '韩语' },
            { n: '日语', v: '日语' },
            { n: '法语', v: '法语' },
            { n: '德语', v: '德语' },
            { n: '泰语', v: '泰语' },
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

// 站点分类映射：壳展示的分类名 → 站点 URL 中的 type_id
const CATEGORIES = [
    { type_id: '1', type_name: '电影' },
    { type_id: '2', type_name: '剧集' },
    { type_id: '3', type_name: '综艺' },
    { type_id: '4', type_name: '动漫' },
];

async function init(cfg) {
    if (typeof cfg.ext === 'string' && cfg.ext.startsWith('http')) {
        host = cfg.ext.trim().replace(/\/$/, '');
    }
}

async function home(filter) {
    const classes = _.map(CATEGORIES, (c) => ({
        type_id: c.type_id,
        type_name: c.type_name,
    }));
    // 首页推荐：抓取首页各板块卡片
    const videos = await fetchHomeVod();
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
            filters[typeId] = FILTER_OPTIONS;
        }
    }
    return filters;
}

async function homeVod() {
    const videos = await fetchHomeVod();
    return JSON.stringify({ list: videos });
}

// 抓取首页视频卡片
async function fetchHomeVod() {
    try {
        const resp = await req(`${host}/`, { headers: getHeaders() });
        const html = resp.content;
        return parseVodCards(html);
    } catch (e) {
        return [];
    }
}

// 解析首页/分类页的视频卡片
function parseVodCards(html) {
    const videos = [];
    // 匹配 module-poster-item 卡片：<a href="/dsx/ID.html" title="名称" class="module-poster-item ...">
    const cardRegex = /<a[^>]*href="\/dsx\/(\d+)\.html"[^>]*title="([^"]*)"[^>]*class="module-poster-item[^"]*"[^>]*>[\s\S]*?<div[^>]*class="module-item-note"[^>]*>([^<]*)<\/div>[\s\S]*?<img[^>]*data-original="([^"]*)"[^>]*>/g;
    let match;
    while ((match = cardRegex.exec(html)) !== null) {
        videos.push({
            vod_id: match[1],
            vod_name: match[2],
            vod_pic: fixUrl(match[4]),
            vod_remarks: match[3].trim(),
        });
    }
    return videos;
}

// 分类列表：URL 格式 /k/{type_id}-{area}-{sort}-{class}-{lang}-{letter}------{page}---{year}.html
async function category(tid, pg, filter, extend) {
    extend = extend && typeof extend === 'object' ? extend : {};
    const page = parseInt(pg) || 1;
    const area = extend.area || '';
    const sort = extend.sort || '';
    const cls = extend.class || '';
    const lang = extend.lang || '';
    const year = extend.year || '';
    const letter = '';

    // 构建 URL：12 个字段用 '-' 分隔，page 在第 9 位（索引 8）
    const parts = [tid, area, sort, cls, lang, letter, '', '', page, '', '', year];
    const url = `${host}/k/${parts.join('-')}.html`;

    try {
        const resp = await req(url, { headers: getHeaders() });
        const html = resp.content;
        const list = parseVodCards(html);

        // 判断是否有下一页：查找分页链接中是否包含 page+1
        const hasNext = html.includes(`-${page + 1}---.html`) || html.includes('下一页');
        const pageCount = list.length > 0 ? (hasNext ? page + 1 : page) : page;

        return JSON.stringify({
            list: list,
            pagecount: pageCount,
            page: page,
            limit: list.length,
            total: list.length > 0 ? 999999 : page * 30,
        });
    } catch (e) {
        return JSON.stringify({ list: [], pagecount: 1, page: page, limit: 0, total: 0 });
    }
}

// 搜索：URL 格式 /s/{keyword}----------{page}---.html
async function search(wd, quick, pg = 1) {
    const page = parseInt(pg) || 1;
    const keyword = encodeURIComponent(wd);
    // 搜索 URL 有 13 个 '-' 分隔的字段，page 在第 11 位
    const url = `${host}/s/${keyword}----------${page}---.html`;

    try {
        const resp = await req(url, { headers: getHeaders() });
        const html = resp.content;
        const list = parseSearchCards(html);

        // 判断是否有下一页
        const hasNext = html.includes(`----------${page + 1}---.html`) || html.includes('下一页');
        const pageCount = list.length > 0 ? (hasNext ? page + 1 : page) : page;

        return JSON.stringify({
            list: list,
            pagecount: pageCount,
            page: page,
        });
    } catch (e) {
        return JSON.stringify({ list: [], pagecount: 1, page: page });
    }
}

// 解析搜索页视频卡片
function parseSearchCards(html) {
    const videos = [];
    // 搜索页卡片结构：<a href="/dsx/ID.html" class="module-card-item-poster"> ... <div class="module-item-note">备注</div> ... <img data-original="图片" alt="名称"> ...
    // 注意：<strong> 标题在卡片外部兄弟元素中，不在 <a> 标签内
    const cardRegex = /<a[^>]*href="\/dsx\/(\d+)\.html"[^>]*class="module-card-item-poster"[^>]*>[\s\S]*?<div[^>]*class="module-item-note"[^>]*>([^<]*)<\/div>[\s\S]*?<img[^>]*data-original="([^"]*)"[^>]*alt="([^"]*)"[^>]*>/g;
    let match;
    while ((match = cardRegex.exec(html)) !== null) {
        videos.push({
            vod_id: match[1],
            vod_name: match[4],
            vod_pic: fixUrl(match[3]),
            vod_remarks: match[2].trim(),
        });
    }
    // 备用正则：alt 在 data-original 之前的情况
    if (videos.length === 0) {
        const altRegex = /<a[^>]*href="\/dsx\/(\d+)\.html"[^>]*class="module-card-item-poster"[\s\S]*?alt="([^"]*)"[\s\S]*?data-original="([^"]*)"[\s\S]*?module-item-note[^>]*>([^<]*)</g;
        while ((match = altRegex.exec(html)) !== null) {
            videos.push({
                vod_id: match[1],
                vod_name: match[2],
                vod_pic: fixUrl(match[3]),
                vod_remarks: match[4].trim(),
            });
        }
    }
    return videos;
}

// 详情页：/dsx/{vod_id}.html
async function detail(id) {
    try {
        const resp = await req(`${host}/dsx/${id}.html`, { headers: getHeaders() });
        const html = resp.content;

        // 提取标题
        const nameMatch = html.match(/<h1[^>]*>([^<]*)<\/h1>/);
        const vod_name = nameMatch ? nameMatch[1].trim() : '';

        // 提取封面图
        const picMatch = html.match(/module-info-poster[\s\S]*?data-original="([^"]*)"/);
        const vod_pic = picMatch ? fixUrl(picMatch[1]) : '';

        // 提取简介
        const contentMatch = html.match(/module-info-introduction-content[\s\S]*?<p>([^<]*)<\/p>/);
        const vod_content = contentMatch ? contentMatch[1].trim() : '';

        // 提取分类标签
        const tagMatches = html.matchAll(/module-info-tag-link[\s\S]*?>([^<]+)</g);
        const tags = [];
        for (const m of tagMatches) {
            tags.push(m[1].trim());
        }
        const vod_year = tags[0] || '';
        const vod_area = tags[1] || '';
        const vod_class = tags.slice(2).join(',');

        // 提取信息项（导演、主演、语言、上映、备注等）
        const vod_director = extractInfoItem(html, '导演') || '';
        const vod_actor = extractInfoItem(html, '主演') || '';
        const vod_remarks = extractInfoItem(html, '备注') || extractInfoItem(html, '集数') || '';

        // 提取播放源和选集
        const { play_from, play_url } = extractPlayList(html, id);

        const video = {
            vod_id: id.toString(),
            vod_name: vod_name,
            vod_pic: vod_pic,
            vod_remarks: vod_remarks,
            vod_year: vod_year,
            vod_area: vod_area,
            vod_actor: vod_actor,
            vod_director: vod_director,
            vod_content: vod_content,
            vod_play_from: play_from,
            vod_play_url: play_url,
            type_name: vod_class,
        };
        return JSON.stringify({ list: [video] });
    } catch (e) {
        return JSON.stringify({ list: [] });
    }
}

// 从 HTML 中提取信息项内容（如导演、主演等）
function extractInfoItem(html, title) {
    const regex = new RegExp(`${title}[：:]?<\\/span>[\\s\\S]*?<div[^>]*class="module-info-item-content"[^>]*>([\\s\\S]*?)<\\/div>`);
    const match = html.match(regex);
    if (match) {
        // 去掉 HTML 标签，保留文本
        return match[1].replace(/<[^>]+>/g, '').replace(/\/\s*$/, '').trim();
    }
    return '';
}

// 提取播放列表：多个播放源 + 每个源的选集
function extractPlayList(html, vodId) {
    const playFromList = [];
    const playUrlList = [];

    // 提取播放源标签名：<div class="module-tab-item ..." data-dropdown-value="大陆0线">
    const tabRegex = /<div[^>]*class="module-tab-item[^"]*"[^>]*data-dropdown-value="([^"]*)"[^>]*>/g;
    const tabNames = [];
    let tabMatch;
    while ((tabMatch = tabRegex.exec(html)) !== null) {
        tabNames.push(tabMatch[1]);
    }

    // 提取所有播放列表内容块：<div class="module-play-list-content ...">...</div>
    const listRegex = /<div[^>]*class="module-play-list-content[^"]*"[^>]*>([\s\S]*?)<\/div>\s*<\/div>/g;
    const lists = [];
    let listMatch;
    while ((listMatch = listRegex.exec(html)) !== null) {
        lists.push(listMatch[1]);
    }

    // 为每个播放源提取选集
    for (let i = 0; i < tabNames.length; i++) {
        const tabName = tabNames[i];
        const listHtml = lists[i] || '';
        const episodes = [];

        // 匹配选集链接：<a class="module-play-list-link" href="/video/ID-P-E.html"><span>名称</span></a>
        const epRegex = /<a[^>]*class="module-play-list-link"[^>]*href="\/video\/(\d+)-(\d+)-(\d+)\.html"[^>]*>[\s\S]*?<span>([^<]*)<\/span>/g;
        let epMatch;
        while ((epMatch = epRegex.exec(listHtml)) !== null) {
            const epName = epMatch[4].trim();
            const epUrl = `${epMatch[1]}-${epMatch[2]}-${epMatch[3]}`;
            episodes.push(`${epName}$${epUrl}`);
        }

        if (episodes.length > 0) {
            playFromList.push(tabName);
            playUrlList.push(episodes.join('#'));
        }
    }

    return {
        play_from: playFromList.join('$$$'),
        play_url: playUrlList.join('$$$'),
    };
}

// 播放页：/video/{vod_id}-{player}-{episode}.html
// 页面包含 player_aaaa 对象，其中有直链 m3u8 URL
async function play(flag, vid, flags) {
    try {
        const url = `${host}/video/${vid}.html`;
        const resp = await req(url, { headers: getHeaders() });
        const html = resp.content;

        // 从 HTML 中提取 player_aaaa 对象
        // player_aaaa 包含嵌套的 vod_data 对象，使用花括号配平算法提取完整 JSON
        const playerData = extractPlayerAaaa(html);
        if (playerData) {
            const playUrl = playerData.url || '';
            const encrypt = playerData.encrypt || 0;

            // encrypt=0 表示直链，可以直接播放
            if (playUrl && playUrl.startsWith('http')) {
                return JSON.stringify({
                    jx: 0,
                    parse: 0,
                    url: playUrl,
                    header: { 'User-Agent': UA },
                });
            }
        }
    } catch (e) {
        // 解析失败，返回空
    }
    return JSON.stringify({ jx: 0, parse: 0, url: '', header: { 'User-Agent': UA } });
}

// 从 HTML 中提取 player_aaaa 对象（支持嵌套花括号）
function extractPlayerAaaa(html) {
    const marker = 'player_aaaa';
    const startIdx = html.indexOf(marker);
    if (startIdx < 0) return null;

    // 找到 = 后的第一个 {
    let idx = startIdx + marker.length;
    while (idx < html.length && html[idx] !== '{') idx++;
    if (idx >= html.length) return null;

    // 花括号配平：从第一个 { 开始计数，遇到 { 加 1，遇到 } 减 1
    let depth = 0;
    let endIdx = -1;
    for (let i = idx; i < html.length; i++) {
        if (html[i] === '{') depth++;
        else if (html[i] === '}') {
            depth--;
            if (depth === 0) { endIdx = i; break; }
        }
    }
    if (endIdx < 0) return null;

    const jsonStr = html.substring(idx, endIdx + 1);
    try {
        return JSON.parse(jsonStr);
    } catch (e) {
        return null;
    }
}

// 工具函数：修复图片 URL（补全 host 前缀）
function fixUrl(url) {
    if (!url) return '';
    if (url.startsWith('http')) return url;
    if (url.startsWith('//')) return 'https:' + url;
    if (url.startsWith('/')) return host + url;
    return url;
}

// 工具函数：获取请求头
function getHeaders() {
    return {
        'User-Agent': UA,
        'Referer': host + '/',
    };
}

export function __jsEvalReturn() {
    return {
        init: init,
        home: home,
        homeVod: homeVod,
        category: category,
        search: search,
        detail: detail,
        play: play,
    };
}
