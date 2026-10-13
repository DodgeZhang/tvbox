/*
@header({
  searchable: 1,
  filterable: 1,
  quickSearch: 0,
  title: 'SaoHuo',
  lang: 'cat'
})
*/

import { load } from 'assets://js/lib/cat.js';

let host = 'https://shdy2.com';
let cookie = '';

const headers = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 9; ALN-AL00 Build/PQ3B.190801.05281406; wv) AppleWebKit/537.36',
    'accept-language': 'zh-CN,zh;q=0.9'
};

async function request(url, options = {}) {
    try {
        let hdrs = { ...headers, ...options.headers };
        if (cookie) hdrs['Cookie'] = cookie;
        let res = await req(url, { headers: hdrs, ...options });
        let setCookie = res.headers && res.headers['set-cookie'];
        if (setCookie) cookie = Array.isArray(setCookie) ? setCookie.join('; ') : setCookie;
        return res.content || '';
    } catch (e) {
        console.log('[请求失败] ' + url + ' - ' + e.message);
        return '';
    }
}

async function init(ext) {
    if (typeof ext === 'string' && ext.trim().length > 0) host = ext.trim();
    console.log('[当前域名] ' + host);
    await request(host);
}

function home() {
    const classes = [
        { type_id: '1', type_name: '电影' },
        { type_id: '2', type_name: '电视剧' },
        { type_id: '4', type_name: '动漫' }
    ];
    const filters = {
        "1": [{ "key": "cateId", "name": "类型", "value": [
            { "n": "全部", "v": "1" }, { "n": "喜剧", "v": "6" }, { "n": "爱情", "v": "7" },
            { "n": "恐怖", "v": "8" }, { "n": "动作", "v": "9" }, { "n": "科幻", "v": "10" },
            { "n": "战争", "v": "11" }, { "n": "犯罪", "v": "12" }, { "n": "动画", "v": "13" },
            { "n": "奇幻", "v": "14" }, { "n": "剧情", "v": "15" }, { "n": "冒险", "v": "16" },
            { "n": "悬疑", "v": "17" }, { "n": "惊悚", "v": "18" }, { "n": "其他", "v": "20" }
        ]}],
        "2": [{ "key": "cateId", "name": "类型", "value": [
            { "n": "全部", "v": "2" }, { "n": "国产剧", "v": "20" }, { "n": "TVB", "v": "21" },
            { "n": "韩剧", "v": "22" }, { "n": "美剧", "v": "23" }, { "n": "日剧", "v": "24" },
            { "n": "英剧", "v": "25" }, { "n": "台剧", "v": "26" }, { "n": "其他", "v": "27" }
        ]}],
        "4": [{ "key": "cateId", "name": "类型", "value": [
            { "n": "全部", "v": "4" }, { "n": "搞笑", "v": "38" }, { "n": "恋爱", "v": "39" },
            { "n": "热血", "v": "40" }, { "n": "格斗", "v": "41" }, { "n": "美少女", "v": "42" },
            { "n": "魔法", "v": "43" }, { "n": "机战", "v": "44" }, { "n": "校园", "v": "45" },
            { "n": "亲子", "v": "46" }, { "n": "童话", "v": "47" }, { "n": "冒险", "v": "48" },
            { "n": "真人", "v": "49" }, { "n": "LOLI", "v": "50" }, { "n": "其他", "v": "51" }
        ]}]
    };
    return JSON.stringify({ class: classes, filters: filters });
}

async function homeVod() {
    if (!host || typeof host !== 'string') { host = 'https://shdy2.com'; await init(); }
    let html = await request(host);
    if (!html) return JSON.stringify({ list: [] });
    const $ = load(html);
    let list = [];
    $('.v_list li, .module-item, .myui-vodlist__box, .stui-vodlist__box, li.vodlist_box').each((i, el) => {
        if (i >= 6) return false;
        let a = $(el).find('a').first();
        let href = a.attr('href') || '';
        let title = a.attr('title') || '';
        let pic = a.find('img').attr('data-original') || a.find('img').attr('src') || '';
        let remarks = $(el).find('.v_note, .continu, .pic-text, .pic-tag, .module-item-note').first().text().trim();
        if (title && href) {
            list.push({
                vod_id: href.startsWith('http') ? href : (host + href),
                vod_name: title,
                vod_pic: pic.startsWith('http') ? pic : (host + pic),
                vod_remarks: remarks
            });
        }
    });
    return JSON.stringify({ list });
}

async function category(tid, pg, filter, extend) {
    if (!host || typeof host !== 'string') { host = 'https://shdy2.com'; await init(); }
    let page = parseInt(pg) || 1;
    let cateId = (extend && extend.cateId) || tid;
    let url = host + '/list/' + cateId;
    if (page > 1) url += '-' + page;
    url += '.html';
    console.log('[category] ' + url);
    let html = await request(url);
    if (!html) return JSON.stringify({ list: [], page, pagecount: 1 });

    const $ = load(html);
    let list = [];
    $('.v_list li, .module-item, .myui-vodlist__box, .stui-vodlist__box, li.vodlist_box').each((i, el) => {
        let a = $(el).find('a').first();
        let href = a.attr('href') || '';
        let title = a.attr('title') || '';
        let pic = a.find('img').attr('data-original') || a.find('img').attr('src') || '';
        let remarks = $(el).find('.v_note, .continu, .pic-text, .pic-tag, .module-item-note').first().text().trim();
        if (title && href) {
            list.push({
                vod_id: href.startsWith('http') ? href : (host + href),
                vod_name: title,
                vod_pic: pic.startsWith('http') ? pic : (host + pic),
                vod_remarks: remarks
            });
        }
    });

    let pagecount = page;
    let pageLinks = $('.page a, .pagination a, #page a, .pages a');
    if (pageLinks.length > 0) {
        let maxPage = 0;
        pageLinks.each((i, el) => {
            let m = ($(el).attr('href') || '').match(/[-_](\d+)\.html/);
            if (m && m[1]) {
                let p = parseInt(m[1]);
                if (p > maxPage) maxPage = p;
            }
        });
        if (maxPage > 0) pagecount = maxPage;
    } else if (list.length >= 10) {
        pagecount = page + 1;
    }

    return JSON.stringify({ list, page, pagecount, limit: list.length, total: pagecount * list.length });
}

async function detail(id) {
    if (!host || typeof host !== 'string') { host = 'https://shdy2.com'; await init(); }
    let url = id.startsWith('http') ? id : (host + id);
    let html = await request(url);
    if (!html) return JSON.stringify({ list: [] });
    const $ = load(html);

    let vod_name = $('h1.v_title, h1.title').first().text().trim().replace(/\s*-.*$/, '');
    let vod_pic = $('img.lazyload').first().attr('data-original') || $('img.lazyload').first().attr('src') || '';
    if (vod_pic && !vod_pic.startsWith('http')) vod_pic = host + vod_pic;
    let vod_remarks = $('.score, .text-red').text().trim();

    let type_name = '', vod_area = '', vod_year = '', vod_director = '', vod_actor = '';
    let infoStr = $('.v_info_box p').first().text().trim() || $('.myui-content__detail > p.data').first().text().trim();
    if (infoStr) {
        let segs = infoStr.split('/').map(s => s.trim());
        if (segs.length >= 3) {
            vod_area = segs[0];
            vod_year = segs[1];
            type_name = segs[2];
            for (let seg of segs.slice(3)) {
                if (seg.startsWith('导演:')) vod_director = seg.replace('导演:', '').trim();
                else if (seg.startsWith('主演:')) {
                    vod_actor = seg.replace('主演:', '').trim();
                    vod_actor = vod_actor.replace(/剧情介绍.*$/, '').trim();
                }
            }
        }
    }
    if (!type_name) type_name = $('.myui-content__detail > p.data:contains("分类：")').text().replace('分类：', '').trim();
    if (!vod_area) vod_area = $('.myui-content__detail > p.data:contains("地区：")').text().replace('地区：', '').trim();
    if (!vod_year) {
        let m = ($('.myui-content__detail > p.data:contains("年份：")').text() || '').match(/(\d{4})/);
        if (m) vod_year = m[1];
    }
    if (!vod_director) {
        let t = $('.myui-content__detail > p.data:contains("导演：")').text().replace('导演：', '').trim();
        if (t) vod_director = t;
    }
    if (!vod_actor) {
        let t = $('.myui-content__detail > p.data:contains("主演：")').text().replace('主演：', '').trim();
        if (t) {
            t = t.replace(/剧情介绍.*$/, '').trim();
            vod_actor = t;
        }
    }

    let vod_content = $('.intro, .des, p.p_txt').text().trim() || $('#info_more, .detail-content').text().trim();

    // 播放列表（强制正序）
    let sourceNames = [];
    let sourceUrls = [];
    const fromList = $('.play_from ul.from_list li');
    const linkBlocks = $('#play_link > li');
    if (fromList.length && linkBlocks.length && fromList.length === linkBlocks.length) {
        fromList.each((i, el) => {
            sourceNames.push($(el).text().trim());
            let episodes = [];
            linkBlocks.eq(i).find('a').each((j, a) => {
                let href = $(a).attr('href') || '';
                let text = $(a).text().trim();
                let num = parseInt(text.replace(/[^0-9]/g, ''));
                if (isNaN(num)) num = j + 1;
                episodes.push({ text, href, num });
            });
            episodes.sort((a, b) => a.num - b.num);
            sourceUrls.push(episodes.map(ep => ep.text + '$' + ep.href).join('#'));
        });
    } else if (linkBlocks.length) {
        linkBlocks.each((i, el) => {
            sourceNames.push('线路' + (i + 1));
            let episodes = [];
            $(el).find('a').each((j, a) => {
                let href = $(a).attr('href') || '';
                let text = $(a).text().trim();
                let num = parseInt(text.replace(/[^0-9]/g, ''));
                if (isNaN(num)) num = j + 1;
                episodes.push({ text, href, num });
            });
            episodes.sort((a, b) => a.num - b.num);
            sourceUrls.push(episodes.map(ep => ep.text + '$' + ep.href).join('#'));
        });
    } else {
        let panels = $('.myui-panel_bd .myui-content__list');
        let titles = $('.myui-panel__head a + h3.title');
        titles.each((i, el) => {
            sourceNames.push($(el).text().trim());
            let episodes = [];
            let panel = panels.eq(i);
            if (panel.length) {
                panel.find('a').each((j, a) => {
                    let href = $(a).attr('href') || '';
                    let text = $(a).text().trim();
                    let num = parseInt(text.replace(/[^0-9]/g, ''));
                    if (isNaN(num)) num = j + 1;
                    episodes.push({ text, href, num });
                });
                episodes.sort((a, b) => a.num - b.num);
                sourceUrls.push(episodes.map(ep => ep.text + '$' + ep.href).join('#'));
            }
        });
    }

    return JSON.stringify({
        list: [{
            vod_id: id,
            vod_name,
            vod_pic,
            vod_content,
            vod_play_from: sourceNames.join('$$$'),
            vod_play_url: sourceUrls.join('$$$'),
            vod_director,
            vod_actor,
            type_name,
            vod_area,
            vod_year,
            vod_remarks
        }]
    });
}

async function search(wd, quick, pg) {
    if (!host || typeof host !== 'string') { host = 'https://shdy2.com'; await init(); }
    let html = await request(host + '/s----------.html?wd=' + encodeURIComponent(wd));
    if (!html) return JSON.stringify({ list: [] });
    const $ = load(html);
    let list = [];
    $('.v_list li, .module-item, .myui-vodlist__box, .stui-vodlist__box, li.vodlist_box').each((i, el) => {
        let a = $(el).find('a').first();
        let href = a.attr('href') || '';
        let title = a.attr('title') || '';
        let pic = a.find('img').attr('data-original') || a.find('img').attr('src') || '';
        let remarks = $(el).find('.v_note, .continu, .pic-text').first().text().trim();
        if (title && href) {
            list.push({
                vod_id: href.startsWith('http') ? href : (host + href),
                vod_name: title,
                vod_pic: pic.startsWith('http') ? pic : (host + pic),
                vod_remarks: remarks
            });
        }
    });
    return JSON.stringify({ list });
}

async function play(flag, id, flags) {
    let finalUrl = id;
    if (!finalUrl.startsWith('http')) {
        if (!host) await init();
        finalUrl = host + finalUrl;
    }
    return JSON.stringify({ parse: 1, url: finalUrl, jx: 0 });
}

export function __jsEvalReturn() {
    return { init, home, homeVod, category, detail, play, search };
}