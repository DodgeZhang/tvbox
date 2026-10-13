//本资源来源于互联网公开渠道，仅可用于个人学习爬虫技术。
//严禁将其用于任何商业用途，下载后请于 24 小时内删除，搜索结果均来自源站，本人不承担任何责任。
import {
    load as t
} from "assets://js/lib/cat.js";
let e, a = "https://www.985djw.com",
    i = "",
    n = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "zh-CN,zh;q=0.9",
        "cache-control": "no-cache",
        pragma: "no-cache",
        priority: "u=0, i",
        "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "upgrade-insecure-requests": "1"
    };
async function r(t) {
    "function" == typeof js2Proxy && "function" == typeof desX && "function" != typeof getProxy && (e = !0);
    let n = t.ext;
    if ("object" == typeof n && null !== n) {
        let t = n.host || "";
        t && t.startsWith("http") && (a = t), n.picProxy && n.picProxy.startsWith("http") && (i = n.picProxy)
    } else "string" == typeof n && n.startsWith("http") && (a = n);
    a.endsWith("/") && (a = a.slice(0, -1))
}
async function s(i) {
    let n = [],
        r = {},
        s = await u(a + "/"),
        o = t(s);
    if (o(".stui-header__menu ul li a").each((t, e) => {
            let a = o(e).attr("href"),
                i = o(e).text().trim();
            if (a && "/" !== a && -1 === a.indexOf(".html")) {
                let t = a.match(/\/nl\/([^\/]+)\//);
                t && n.push({
                    type_id: t[1],
                    type_name: i
                })
            }
        }), e && n.unshift({
            type_id: "home",
            type_name: "首页"
        }), n.length > 0) {
        let i = e && n.length > 1 ? n[1].type_id : n[0].type_id,
            s = await u(a + "/nl/" + i + "/", a + "/"),
            o = t(s),
            l = {
                "类型": "class",
                "地区": "area",
                "年份": "year",
                "语言": "lang",
                "排序": "by"
            },
            c = {
                class: 3,
                area: 1,
                year: 11,
                lang: 4,
                by: 2
            },
            p = [];
        o(".stui-screen__list").each((t, e) => {
            let a = o(e).find("li:first-child span.text-muted").text().replace("按", "").trim(),
                i = l[a];
            if (i) {
                let t = [],
                    n = "";
                o(e).find("a").each((e, a) => {
                    let r = o(a).text().trim(),
                        s = (o(a).attr("href") || "").split("-")[c[i]] || "";
                    "" === r && "" === s || ("全部" === r && (n = s), t.push({
                        n: r,
                        v: s
                    }))
                }), t.length > 1 && p.push({
                    key: i,
                    name: a,
                    init: n,
                    value: t
                })
            }
        });
        for (let t = 0; t < n.length; t++) "home" !== n[t].type_id && (r[n[t].type_id] = p)
    }
    return JSON.stringify({
        class: n,
        filters: r
    })
}
async function o() {
    return await l("home", 1, null, {})
}
async function l(e, i, n, r) {
    let s = i || 1;
    if ("home" === e) {
        let e = await u(a + "/"),
            i = h(t(e));
        return JSON.stringify({
            page: 1,
            pagecount: 1,
            list: i
        })
    }
    let o = r || {},
        l = o.area || "",
        c = o.by || "",
        p = o.class || "",
        d = o.lang || "",
        m = o.letter || "",
        f = o.year || "",
        _ = a + `/vodshow/${e}-${l}-${c}-${p}-${d}-${m}---${s}---${f}/`,
        y = await u(_, a + "/nl/" + e + "/"),
        g = t(y),
        v = h(g),
        x = s,
        w = g(".stui-page .num").text();
    return w && w.includes("/") && (x = parseInt(w.split("/")[1])), JSON.stringify({
        page: parseInt(s),
        pagecount: parseInt(x),
        list: v
    })
}
async function c(e, i, n) {
    let r = n || 1,
        s = "";
    s = "1" === String(r) ? a + "/vodsearch/-------------/?wd=" + encodeURIComponent(e) + "&submit=" : a + `/vodsearch/${encodeURIComponent(e)}----------${r}---/`;
    let o = await u(s, a + "/"),
        l = t(o),
        c = h(l),
        p = r,
        d = l(".stui-page .num").text();
    return d && d.includes("/") && (p = parseInt(d.split("/")[1])), JSON.stringify({
        page: parseInt(r),
        pagecount: parseInt(p),
        list: c
    })
}
async function p(e) {
    let i = e.startsWith("http") ? e : a + e,
        n = await u(i, a + "/"),
        r = t(n),
        s = {
            vod_id: e,
            vod_name: r("h1.title a").text().trim(),
            vod_pic: m(r(".stui-content__thumb img").attr("data-original")),
            type_name: "",
            vod_year: "",
            vod_area: "",
            vod_remarks: "",
            vod_actor: "",
            vod_director: "",
            vod_content: r(".stui-content__desc").text().trim(),
            vod_play_from: "",
            vod_play_url: ""
        };
    r(".stui-content__detail p.data").each((t, e) => {
        let a = r(e).text();
        a.includes("类型：") && (s.type_name = r(e).find("a").text().trim()), a.includes("地区：") && (s.vod_area = r(e).find("a").text().trim()), a.includes("年份：") && (s.vod_year = r(e).find("a").text().trim()), a.includes("主演：") && (s.vod_actor = a.replace("主演：", "").trim()), a.includes("导演：") && (s.vod_director = a.replace("导演：", "").trim())
    });
    let o = [];
    return r(".stui-pannel").each((t, e) => {
        r(e).find(".stui-pannel__head h3.title").text().includes("手机在线播放器") && (s.vod_play_from = "碎光在线", r(e).find("ul.stui-content__playlist li a").each((t, e) => {
            let a = r(e).attr("href"),
                i = r(e).text().trim();
            a && o.push(i + "$" + a)
        }))
    }), s.vod_play_url = o.join("#"), JSON.stringify({
        list: [s]
    })
}
async function d(t, e, i) {
    let r = e.startsWith("http") ? e : a + e,
        s = "",
        o = (await u(r, a + "/")).match(/player_aaaa\s*=\s*(\{[\s\S]*?\})/);
    if (o) try {
        s = JSON.parse(o[1]).url || ""
    } catch (t) {
        console.error("解析 player_aaaa 核心数组失败: " + t.message)
    }
    return JSON.stringify({
        parse: 0,
        url: s,
        header: {
            "User-Agent": n["User-Agent"]
        }
    })
}
async function u(t, e) {
    let a = Object.assign({}, n);
    return e ? (a.referer = e, a["sec-fetch-site"] = "same-origin") : a["sec-fetch-site"] = "none", (await req(t, {
        headers: a
    })).content
}

function h(t) {
    let e = [];
    return t(".stui-vodlist__item").each((a, i) => {
        let n = t(i).find("a.stui-vodlist__thumb"),
            r = n.attr("href");
        r && e.push({
            vod_id: r,
            vod_name: n.attr("title") || "",
            vod_pic: m(n.attr("data-original")),
            vod_remarks: n.find(".pic-text").text().trim() || ""
        })
    }), e
}

function m(t) {
    return t ? (t.startsWith("//") ? t = "http:" + t : t.startsWith("/") && (t = a + t), i ? i + t : t) : ""
}
export function __jsEvalReturn() {
    return {
        init: r,
        home: s,
        homeVod: o,
        category: l,
        search: c,
        detail: p,
        play: d
    }
}