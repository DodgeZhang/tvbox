import cheerio from 'assets://js/lib/cheerio.min.js';

const appConfig = {
    siteName: "狐狸君影视",
    siteUrl: "https://www.foxjun.com"
}
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";
const Headers = {
    "User-Agent": UA,
    "Referer": appConfig.siteUrl + "/",
}

async function init(ext) {
    console.log("初始化爬虫:", appConfig.siteName);
}

function getYearFilter() {
    let years = [{ "n": "全部", "v": "" }];
    const currentYear = new Date().getFullYear().toString();
    for (let y = currentYear; y >= currentYear - 22; y--) {
        years.push({ "n": String(y), "v": String(y) });
    }
    return { "key": "year", "name": "年份", "value": years };
}

function getLetterFilter() {
    return {
        "key": "letter", "name": "字母", "value": [
            { "n": "全部", "v": "" },
            { "n": "A", "v": "A" }, { "n": "B", "v": "B" }, { "n": "C", "v": "C" }, { "n": "D", "v": "D" },
            { "n": "E", "v": "E" }, { "n": "F", "v": "F" }, { "n": "G", "v": "G" }, { "n": "H", "v": "H" },
            { "n": "I", "v": "I" }, { "n": "J", "v": "J" }, { "n": "K", "v": "K" }, { "n": "L", "v": "L" },
            { "n": "M", "v": "M" }, { "n": "N", "v": "N" }, { "n": "O", "v": "O" }, { "n": "P", "v": "P" },
            { "n": "Q", "v": "Q" }, { "n": "R", "v": "R" }, { "n": "S", "v": "S" }, { "n": "T", "v": "T" },
            { "n": "U", "v": "U" }, { "n": "V", "v": "V" }, { "n": "W", "v": "W" }, { "n": "X", "v": "X" },
            { "n": "Y", "v": "Y" }, { "n": "Z", "v": "Z" }, { "n": "0-9", "v": "0-9" }
        ]
    }
}

function getOrderFilter() {
    return {
        "key": "orderBy", "name": "排序", "value": [
            { "n": "时间", "v": "time" },
            { "n": "人气", "v": "hits" },
            { "n": "评分", "v": "score" }
        ]
    }
}

const CommonFilters = [
    getYearFilter(),
    getLetterFilter(),
    getOrderFilter()
];

const myFilters = {
    "dianying": [
        {
            "key": "class", "name": "剧情", "value": [
                { "n": "全部", "v": "" },
                { "n": "喜剧", "v": "喜剧" },
                { "n": "爱情", "v": "爱情" },
                { "n": "恐怖", "v": "恐怖" },
                { "n": "动作", "v": "动作" },
                { "n": "科幻", "v": "科幻" },
                { "n": "剧情", "v": "剧情" },
                { "n": "战争", "v": "战争" },
                { "n": "犯罪", "v": "犯罪" },
                { "n": "动画", "v": "动画" },
                { "n": "奇幻", "v": "奇幻" },
                { "n": "武侠", "v": "武侠" },
                { "n": "冒险", "v": "冒险" },
                { "n": "悬疑", "v": "悬疑" },
                { "n": "惊悚", "v": "惊悚" },
                { "n": "经典", "v": "经典" },
                { "n": "青春", "v": "青春" },
                { "n": "文艺", "v": "文艺" },
                { "n": "古装", "v": "古装" },
                { "n": "历史", "v": "历史" },
                { "n": "运动", "v": "运动" },
                { "n": "儿童", "v": "儿童" },
                { "n": "纪录片", "v": "纪录片" }
            ]
        },
        ...CommonFilters
    ],
    "donghua": [
        {
            "key": "class", "name": "剧情", "value": [
                { "n": "全部", "v": "" },
                { "n": "情感", "v": "情感" },
                { "n": "科幻", "v": "科幻" },
                { "n": "热血", "v": "热血" },
                { "n": "推理", "v": "推理" },
                { "n": "搞笑", "v": "搞笑" },
                { "n": "冒险", "v": "冒险" },
                { "n": "校园", "v": "校园" },
                { "n": "动作", "v": "动作" },
                { "n": "机战", "v": "机战" },
                { "n": "运动", "v": "运动" },
                { "n": "战争", "v": "战争" },
                { "n": "少年", "v": "少年" },
                { "n": "少女", "v": "少女" },
                { "n": "社会", "v": "社会" },
                { "n": "原创", "v": "原创" },
                { "n": "亲子", "v": "亲子" },
                { "n": "益智", "v": "益智" },
                { "n": "励志", "v": "励志" }
            ]
        },
        ...CommonFilters
    ],
    "meiouju": [
        {
            "key": "class", "name": "剧情", "value": [
                { "n": "全部", "v": "" },
                { "n": "剧情", "v": "剧情" },
                { "n": "喜剧", "v": "喜剧" },
                { "n": "动作", "v": "动作" },
                { "n": "科幻", "v": "科幻" },
                { "n": "悬疑", "v": "悬疑" },
                { "n": "惊悚", "v": "惊悚" },
                { "n": "恐怖", "v": "恐怖" },
                { "n": "犯罪", "v": "犯罪" },
                { "n": "战争", "v": "战争" },
                { "n": "爱情", "v": "爱情" },
                { "n": "奇幻", "v": "奇幻" },
                { "n": "冒险", "v": "冒险" },
                { "n": "历史", "v": "历史" }
            ]
        },
        ...CommonFilters
    ],
    "guochanju": [
        {
            "key": "class", "name": "剧情", "value": [
                { "n": "全部", "v": "" },
                { "n": "古装", "v": "古装" },
                { "n": "战争", "v": "战争" },
                { "n": "青春偶像", "v": "青春偶像" },
                { "n": "喜剧", "v": "喜剧" },
                { "n": "家庭", "v": "家庭" },
                { "n": "犯罪", "v": "犯罪" },
                { "n": "动作", "v": "动作" },
                { "n": "奇幻", "v": "奇幻" },
                { "n": "剧情", "v": "剧情" },
                { "n": "历史", "v": "历史" },
                { "n": "经典", "v": "经典" },
                { "n": "乡村", "v": "乡村" },
                { "n": "情景", "v": "情景" },
                { "n": "商战", "v": "商战" },
                { "n": "网剧", "v": "网剧" }
            ]
        },
        ...CommonFilters
    ],
    "rihanju": [
        {
            "key": "class", "name": "剧情", "value": [
                { "n": "全部", "v": "" },
                { "n": "剧情", "v": "剧情" },
                { "n": "喜剧", "v": "喜剧" },
                { "n": "爱情", "v": "爱情" },
                { "n": "悬疑", "v": "悬疑" },
                { "n": "惊悚", "v": "惊悚" },
                { "n": "恐怖", "v": "恐怖" },
                { "n": "犯罪", "v": "犯罪" },
                { "n": "动作", "v": "动作" },
                { "n": "科幻", "v": "科幻" },
                { "n": "奇幻", "v": "奇幻" },
                { "n": "历史", "v": "历史" },
                { "n": "战争", "v": "战争" },
                { "n": "家庭", "v": "家庭" }
            ]
        },
        ...CommonFilters
    ]
};

async function home(filter) {
    return JSON.stringify({
        class: [
            { type_id: "dianying", type_name: "电影" },
            { type_id: "donghua", type_name: "动画" },
            { type_id: "meiouju", type_name: "美欧剧" },
            { type_id: "guochanju", type_name: "国产剧" },
            { type_id: "rihanju", type_name: "日韩剧" }
        ],
        filters: myFilters
    });
}

async function category(tid, pg, filter, extend) {
    pg = pg || 1;
    let url = "";
    
    // 狐狸君分页格式: /channel/xxx.html?page=2
    if (pg === 1) {
        url = `${appConfig.siteUrl}/channel/${tid}.html`;
    } else {
        url = `${appConfig.siteUrl}/channel/${tid}.html?page=${pg}`;
    }

    try {
        const html = (await req(url, { headers: Headers })).content;
        const $ = cheerio.load(html);
        let list = [];

        // 列表结构: .article-list > .article-item > .media > .media-left > a
        $(".article-item").each(function (index, el) {
            const linkEl = $(el).find(".media-left a").first();
            let vod_id = linkEl.attr("href") || '';
            let vod_name = linkEl.find(".embed-responsive span").attr("title") || '';
            if (!vod_name) {
                vod_name = linkEl.attr("title") || '';
            }
            vod_name = vod_name.trim();
            
            let vod_pic = linkEl.find("img").attr("src") || '';
            if (!vod_pic) {
                vod_pic = linkEl.find("img").attr("data-src") || '';
            }
            
            // 提取备注信息（年份+清晰度）
            let vod_remarks = "";
            const yearMatch = vod_name.match(/(\d{4})/);
            if (yearMatch) {
                vod_remarks = yearMatch[1];
            }
            const qualityMatch = vod_name.match(/(1080p|4K|720p|HD|BD|HD中字|中英双字|国语中字|国粤双语|国英双语)/i);
            if (qualityMatch) {
                vod_remarks = vod_remarks + (vod_remarks ? ' ' : '') + qualityMatch[1];
            }

            if (vod_id && vod_name) {
                list.push({
                    vod_id,
                    vod_name,
                    vod_pic,
                    vod_remarks
                });
            }
        });

        let pagecount = 1;
        // 从分页ul中提取最大页码
        const lastPageLink = $("ul.pagination li a[href*='page=']").last().attr("href");
        if (lastPageLink) {
            const pageMatch = lastPageLink.match(/page=(\d+)/);
            if (pageMatch) {
                pagecount = parseInt(pageMatch[1]);
            }
        } else {
            // 尝试从所有分页链接找最大页码
            let maxPage = 1;
            $("ul.pagination li a[href*='page=']").each((i, el) => {
                const href = $(el).attr("href") || '';
                const match = href.match(/page=(\d+)/);
                if (match) {
                    const p = parseInt(match[1]);
                    if (p > maxPage) maxPage = p;
                }
            });
            if (maxPage > 1) pagecount = maxPage;
        }

        return JSON.stringify({
            list,
            pagecount
        });
    } catch (e) {
        console.error("分类列表获取失败:", e.message);
        return JSON.stringify({ list: [], pagecount: 0 });
    }
}

async function search(wd, quick, page) {
    if (page >= 2) {
        return JSON.stringify({ list: [], pagecount: 1 });
    }

    try {
        // 先获取首页提取searchtoken
        const homeHtml = (await req(appConfig.siteUrl, { headers: Headers })).content;
        const tokenMatch = homeHtml.match(/name="__searchtoken__" value="([^"]+)"/);
        const token = tokenMatch ? tokenMatch[1] : '';
        
        if (!token) {
            console.log("无法获取搜索token，搜索功能暂不可用");
            return JSON.stringify({ list: [], pagecount: 0 });
        }

        const searchUrl = `${appConfig.siteUrl}/s/`;
        const html = (await req(searchUrl, {
            method: 'POST',
            headers: {
                ...Headers,
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            data: `q=${encodeURIComponent(wd)}&__searchtoken__=${token}`
        })).content;
        
        const $ = cheerio.load(html);
        let list = [];

        // 搜索结果结构与分类页相同
        $(".article-item").each(function (index, el) {
            const linkEl = $(el).find(".media-left a").first();
            let vod_id = linkEl.attr("href") || '';
            let vod_name = linkEl.find(".embed-responsive span").attr("title") || '';
            if (!vod_name) {
                vod_name = linkEl.attr("title") || '';
            }
            vod_name = vod_name.trim();
            
            let vod_pic = linkEl.find("img").attr("src") || '';
            if (!vod_pic) {
                vod_pic = linkEl.find("img").attr("data-src") || '';
            }
            
            let vod_remarks = "";
            const yearMatch = vod_name.match(/(\d{4})/);
            if (yearMatch) vod_remarks = yearMatch[1];
            const qualityMatch = vod_name.match(/(1080p|4K|720p|HD|BD)/i);
            if (qualityMatch) {
                vod_remarks = vod_remarks + (vod_remarks ? ' ' : '') + qualityMatch[1];
            }

            if (vod_id && vod_name) {
                list.push({
                    vod_id,
                    vod_name,
                    vod_pic,
                    vod_remarks
                });
            }
        });

        return JSON.stringify({
            list: list,
            pagecount: 1
        });
    } catch (e) {
        console.error("搜索失败:", e.message);
        return JSON.stringify({ list: [], pagecount: 0 });
    }
}

async function detail(id) {
    try {
        const url = appConfig.siteUrl + id;
        const response = await req(url, { headers: Headers });
        const html = response ? response.content : '';
        const $ = cheerio.load(html);

        // 获取标题 - h1.metas-title
        let vod_name = $('h1.metas-title').text().trim();
        if (!vod_name) {
            vod_name = $('h1').first().text().trim();
        }
        
        // 获取图片 - .movie-poster img
        const imgSrc = $('.movie-poster img').first().attr("src") || '';
        const vod_pic = imgSrc ? (imgSrc.startsWith('http') ? imgSrc : appConfig.siteUrl + imgSrc) : '';

        // 获取简介 - .content 区域
        let vod_content = '';
        const contentEl = $('.content');
        if (contentEl.length > 0) {
            // 获取纯文本，限制长度
            vod_content = contentEl.text().trim().replace(/\s+/g, ' ').substring(0, 500);
        }
        
        // 获取演员信息 - .movie-detail-box p
        let vod_actor = '';
        $('.movie-detail-box p').each((i, el) => {
            const text = $(el).text().trim();
            if (text.includes('主演') || text.includes('演员')) {
                vod_actor = text.replace(/主演[：:]/, '').trim();
            }
        });
        
        // 获取备注信息（从标题提取年份和清晰度）
        let vod_remarks = '';
        const yearMatch = vod_name.match(/(\d{4})/);
        if (yearMatch) vod_remarks = yearMatch[1];
        const qualityMatch = vod_name.match(/(1080p|4K|720p|HD|BD|HD中字|中英双字|国语中字|国粤双语|国英双语)/i);
        if (qualityMatch) {
            vod_remarks = vod_remarks + (vod_remarks ? ' ' : '') + qualityMatch[1];
        }

        // 收集所有下载链接作为"播放线路"
        // 狐狸君是下载站，没有在线播放，把下载链接包装成播放地址
        let playLines = [];
        let playUrls = [];
        
        // 磁力链接
        const magnetLinks = [];
        $('a[href^="magnet:"]').each((i, el) => {
            const href = $(el).attr('href');
            const text = $(el).text().trim() || `磁力链接${i+1}`;
            if (href) {
                magnetLinks.push(`${text}$${href}`);
            }
        });
        if (magnetLinks.length > 0) {
            playLines.push('磁力下载');
            // 正序排列（保持原始顺序）
            playUrls.push(magnetLinks.join('#'));
        }
        
        // 迅雷网盘
        const xunleiLinks = [];
        $('a[href*="pan.xunlei.com"]').each((i, el) => {
            const href = $(el).attr('href');
            const text = $(el).text().trim() || `迅雷网盘${i+1}`;
            if (href) {
                xunleiLinks.push(`${text}$${href}`);
            }
        });
        if (xunleiLinks.length > 0) {
            playLines.push('迅雷网盘');
            playUrls.push(xunleiLinks.join('#'));
        }
        
        // 百度网盘
        const baiduLinks = [];
        $('a[href*="pan.baidu.com"]').each((i, el) => {
            const href = $(el).attr('href');
            const text = $(el).text().trim() || `百度网盘${i+1}`;
            if (href) {
                baiduLinks.push(`${text}$${href}`);
            }
        });
        if (baiduLinks.length > 0) {
            playLines.push('百度网盘');
            playUrls.push(baiduLinks.join('#'));
        }
        
        // 夸克网盘
        const quarkLinks = [];
        $('a[href*="pan.quark.cn"]').each((i, el) => {
            const href = $(el).attr('href');
            const text = $(el).text().trim() || `夸克网盘${i+1}`;
            if (href) {
                quarkLinks.push(`${text}$${href}`);
            }
        });
        if (quarkLinks.length > 0) {
            playLines.push('夸克网盘');
            playUrls.push(quarkLinks.join('#'));
        }

        // 如果没有找到任何链接，使用详情页URL作为fallback
        if (playLines.length === 0) {
            playLines.push('资源链接');
            playUrls.push(`${vod_name}$${url}`);
        }

        const vod_play_from = playLines.join('$$$');
        const vod_play_url = playUrls.join('$$$');

        const vod = {
            vod_id: id,
            vod_name,
            vod_pic,
            vod_actor,
            vod_remarks,
            vod_content,
            vod_play_from,
            vod_play_url
        };

        return JSON.stringify({ list: [vod] });
    } catch (error) {
        console.error(`解析详情页异常 [ID: ${id}]:`, error);
        return JSON.stringify({ list: [] });
    }
}

async function play(flag, id, flags) {
    try {
        // 磁力链接 - OK影视/TVBox 内置磁力引擎直接播放
        // parse: 1 表示需要播放器调用内置解析引擎处理磁力链接
        if (id.startsWith('magnet:')) {
            return JSON.stringify({
                parse: 1,
                url: id,
                header: Headers
            });
        }
        
        // 网盘链接直接返回
        if (id.startsWith('http')) {
            return JSON.stringify({
                parse: 0,
                url: id,
                header: Headers
            });
        }
        
        // 相对路径补全
        if (id.startsWith('/')) {
            return JSON.stringify({
                parse: 0,
                url: appConfig.siteUrl + id,
                header: Headers
            });
        }

        return JSON.stringify({
            parse: 0,
            url: id,
            header: Headers
        });
    } catch (e) {
        console.error("播放失败:", e);
        return JSON.stringify({ parse: 0, url: "" });
    }
}

export default {
    init,
    home,
    category,
    detail,
    search,
    play
};