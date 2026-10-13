// 本资源来源于互联网公开渠道，仅可用于个人学习爬虫技术。
// 严禁将其用于任何商业用途，下载后请于 24 小时内删除，搜索结果均来自源站，本人不承担任何责任。
import {
    Crypto as e,
    _ as t
} from "assets://js/lib/cat.js";
let a, o, r, n, s, i, d, c, l, p, u, f = `${o}_3qys_B7k7Dt56Rn`;
const _ = "function" == typeof js2Proxy && "function" == typeof desX && "function" != typeof getProxy,
    v = {
        "User-Agent": "okhttp/4.12.0"
    },
    y = {
        "电影": {
            class: ["动作", "喜剧", "爱情", "科幻", "恐怖", "悬疑", "犯罪", "战争", "动画", "冒险", "历史", "灾难", "纪录", "剧情"],
            area: ["大陆", "香港", "台湾", "美国", "日本", "韩国", "泰国", "印度", "英国", "法国", "德国", "加拿大", "西班牙", "意大利", "澳大利亚"],
            year: k(2016, ["2015-2011", "2010-2000", "90年代", "80年代", "更早"])
        },
        "剧集": {
            class: ["爱情", "古装", "武侠", "历史", "家庭", "喜剧", "悬疑", "犯罪", "战争", "奇幻", "科幻", "恐怖"],
            area: ["大陆", "香港", "台湾", "美国", "日本", "韩国", "泰国", "英国"],
            year: k(2021, ["2020-2016", "2015-2011", "2010-2000", "更早"])
        },
        "综艺": {
            class: ["真人秀", "音乐", "脱口秀", "歌舞", "爱情"],
            area: ["大陆", "香港", "台湾", "美国", "日本", "韩国"],
            year: k(2011, ["更早"])
        },
        "动漫": {
            class: ["冒险", "奇幻", "科幻", "武侠", "悬疑"],
            area: ["大陆", "日本", "欧美"],
            year: k(2011, ["更早"])
        }
    };
async function h(e) {
    try {
        const t = e.ext;
        if (a = t.host, o = t.pkg, s = t.sk, n = t.finger, r = String(t.ver), i = t.updateId, d = t.device_id, p = t.filterDef || null, !(a && o && r && i && n && s)) throw new Error("");
        c = t.deviceBrand || "vivo", l = t.deviceModel || "V2309A", p = t.filterDef || null
    } catch (e) {
        a = 0
    }
}
async function m(e) {
    if (!a) return;
    const o = await O();
    let r = t.map(o.data.categories, e => ({
        type_id: e.type_name,
        type_name: e.type_name
    }));
    const n = {};
    for (const e of o.data.categories) {
        let t = e.type_name,
            a = e.filter_options && Object.keys(e.filter_options).length > 0 ? e.filter_options : y[t] || null;
        if (a) {
            n[t] = [];
            for (let e in a) {
                let o = "class" === e ? "类型" : "area" === e ? "地区" : "year" === e ? "年份" : e,
                    r = a[e],
                    s = [{
                        n: "全部",
                        v: ""
                    }];
                r.forEach(e => {
                    s.push({
                        n: e,
                        v: e
                    })
                });
                let i = "";
                if (p && p[t] && p[t][o]) {
                    const e = p[t][o].split(",");
                    for (const t of e) {
                        const e = t.trim(),
                            a = s.find(t => t.n === e);
                        if (a) {
                            i = a.v;
                            break
                        }
                    }
                }
                n[t].push({
                    key: e,
                    name: o,
                    init: i,
                    value: s
                })
            }
        }
    }
    void 0 !== _ && _ && r.unshift({
        type_id: "首页",
        type_name: "首页"
    });
    const s = [];
    if (!_)
        for (const e of o.data.categories) s.push(...J(e.videos));
    return JSON.stringify({
        class: r,
        filters: n,
        list: s
    })
}
async function g() {
    if (!a) return JSON.stringify({
        list: []
    });
    const e = await O(),
        t = [];
    if (e.data) {
        let a = [];
        if (Array.isArray(e.data.appCarouselVideos) && a.push(...e.data.appCarouselVideos), Array.isArray(e.data.recommend) && a.push(...e.data.recommend), Array.isArray(e.data.webCarouselVideos) && a.push(...e.data.webCarouselVideos), a.length > 0) {
            let e = J(a),
                o = new Set;
            for (let a = 0; a < e.length; a++) {
                let r = e[a].vod_id;
                o.has(r) || (o.add(r), t.push(e[a]))
            }
        } else if (e.data.categories)
            for (const a of e.data.categories) t.push(...J(a.videos))
    }
    return JSON.stringify({
        list: t
    })
}
async function $(e, t, o, r) {
    if ("首页" === e) {
        const e = JSON.parse(await g());
        return JSON.stringify({
            list: e.list,
            page: 1
        })
    }
    const n = await C();
    let s = `${a}/api.php/app/filter/vod?type_name=${encodeURIComponent(e)}&page=${t}&sort=hits`;
    if (r)
        for (let e in r) r[e] && (s += `&${e}=${encodeURIComponent(r[e])}`);
    const i = await req(s, {
            headers: n
        }),
        d = JSON.parse(i.content);
    return JSON.stringify({
        list: J(d.data),
        page: parseInt(t)
    })
}
async function w(e, t, o = 1) {
    const r = await C(),
        n = `${a}/api.php/app/search/index?wd=${encodeURIComponent(e)}&page=${o}&limit=15`,
        s = await req(n, {
            headers: r
        }),
        i = JSON.parse(s.content);
    return JSON.stringify({
        list: J(i.data),
        page: parseInt(o)
    })
}
async function S(e) {
    const o = await C(),
        r = await req(`${a}/api.php/app/vod/get_detail?vod_id=${e}`, {
            headers: o
        }),
        n = JSON.parse(r.content),
        s = n.data[0],
        i = n.vodplayer || [],
        d = s.vod_play_from.split("$$$"),
        c = s.vod_play_url.split("$$$");
    let l = [];
    for (let e = 0; e < d.length; e++) {
        const a = d[e],
            o = c[e],
            r = t.find(i, e => e.from === a);
        r && l.push({
            show_code: a,
            urls_str: o,
            player_info: r,
            sort: void 0 !== r.sort && null !== r.sort ? parseFloat(r.sort) : 999
        })
    }
    l.sort((e, t) => e.sort - t.sort);
    const p = [],
        u = [];
    for (const e of l) {
        const t = e.show_code,
            a = e.player_info;
        let o = a.decode_status || 0,
            r = a.decode_mode || "server",
            n = a.parse_url || "",
            s = t;
        t.toLowerCase() !== a.show.toLowerCase() && (s = `${a.show} (${t})`);
        const i = [];
        for (const a of e.urls_str.split("#"))
            if (a.includes("$")) {
                const [e, s] = a.split("$");
                i.push(`${e}$${t}@@${o}@@${r}@@${encodeURIComponent(n)}@@${s}`)
            } i.length > 0 && (u.push(i.join("#")), p.push(s))
    }
    const f = {
        vod_id: s.vod_id.toString(),
        vod_name: s.vod_name,
        vod_pic: N(s.vod_pic),
        vod_remarks: s.vod_remarks,
        vod_year: s.vod_year,
        vod_area: s.vod_area,
        vod_actor: s.vod_actor,
        vod_director: s.vod_director,
        vod_content: s.vod_content,
        vod_play_from: p.join("$$$"),
        vod_play_url: u.join("$$$"),
        type_name: s.vod_class
    };
    return JSON.stringify({
        list: [f]
    })
}
async function x(e, t, o) {
    const r = t.split("@@");
    let n, s, i, d, c;
    if (r.length >= 5) n = r[0], s = r[1], i = r[2], d = decodeURIComponent(r[3]), c = r.slice(4).join("@@");
    else {
        const e = t.split("@");
        n = e[0], s = e[1], c = e.slice(2).join("@"), i = "server", d = ""
    }
    let l = "",
        p = 0;
    if ("1" === s)
        if ("client" === i && d && d.startsWith("http")) {
            let e = "";
            e = d.includes("{url}") ? d.replace("{url}", c) : d + c;
            try {
                const t = await req(e, {
                        headers: v,
                        timeout: 15e3
                    }),
                    a = JSON.parse(t.content);
                a.url ? l = a.url : a.data && a.data.url && (l = a.data.url)
            } catch (e) {}
        } else try {
            const e = await C(),
                t = `${a}/api.php/app/decode/url/?url=${encodeURIComponent(c)}&vodFrom=${n}`,
                o = await req(t, {
                    headers: e,
                    timeout: 3e4
                }),
                r = JSON.parse(o.content);
            r.data && r.data.startsWith("http") && (l = r.data)
        } catch (e) {}
    l || (l = c, /(www\.iqiyi|v\.qq|v\.youku|www\.mgtv|www\.bilibili)\.com/.test(c) && (p = 1));
    let u = {
        jx: p,
        parse: 0,
        url: l,
        header: {
            "User-Agent": "com.sunshine.tv/1.2.0 (Linux;Android 15) AndroidXMedia3/1.4.1"
        }
    };
    return JSON.stringify(u)
}
async function C() {
    const t = Math.floor(Date.now() / 1e3).toString(),
        a = A(3, "0123456789");
    d || (d = await local.get("cache", f), d && 16 === d.length || (d = A(16), await local.set("cache", f, d)));
    const p = `finger=${n}&id=${o}&nonce=${a}&sk=${s}&time=${t}&v=${r}`,
        u = e.SHA256(p).toString().toUpperCase();
    let y = {
        ...v,
        Accept: "application/json",
        "x-aid": o,
        "x-ave": r,
        "x-time": t,
        "x-nonc": a,
        "x-sign": u,
        "x-device-id": d,
        "x-device-brand": c,
        "x-device-model": l,
        "x-platform": "android",
        "x-update-id": i
    };
    return _ && (y["Accept-Encoding"] = "gzip"), y
}
async function O() {
    if (u) return u;
    const e = await C(),
        t = await req(`${a}/api.php/app/index/home`, {
            headers: e
        }),
        o = JSON.parse(t.content).data || {};
    return u = {
        data: {
            appCarouselVideos: o.appCarouselVideos || [],
            recommend: o.recommend || [],
            webCarouselVideos: o.webCarouselVideos || [],
            categories: o.categories || []
        }
    }, u
}

function J(e) {
    return t.map(e, e => {
        let t = e.type_name || "";
        return e.vod_class && (t = t + (t ? "," : "") + e.vod_class), {
            vod_id: e.vod_id.toString(),
            vod_name: e.vod_name,
            vod_pic: N(e.vod_pic || ""),
            vod_remarks: e.vod_remarks,
            type_name: t,
            vod_year: e.vod_year
        }
    })
}
const N = e => (e || "").replace("https://api.zxki.cn/api/imgfdl?url=", "");

function k(e, t) {
    let a = (new Date).getFullYear(),
        o = [];
    for (; a >= e;) o.push(String(a--));
    return [...o, ...t]
}

function A(e, a = "0123456789abcdef") {
    let o = "";
    for (let r = 0; r < e; r++) o += a[t.random(0, a.length - 1)];
    return o
}
export function __jsEvalReturn() {
    return {
        init: h,
        home: m,
        homeVod: g,
        category: $,
        search: w,
        detail: S,
        play: x
    }
}