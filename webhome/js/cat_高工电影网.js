/*
title: '高工电影网', author: 'kh', data: '2026-06-04'
*/
import {load} from 'assets://js/lib/cat.js';

var HOST;
const MOBILE_UA = 'Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.91 Mobile Safari/537.36';
const DefHeader = {'User-Agent': MOBILE_UA};
const KParams = {headers: {'User-Agent': MOBILE_UA}, timeout: 5000};

async function init(cfg) {
    try {
        let host = cfg.ext?.host?.trim() || 'http://www.0531cc.com';
        HOST = host.replace(/\/$/, '');
        KParams.headers['Referer'] = HOST;
        let t = parseInt(cfg.ext?.timeout);
        KParams.timeout = t > 0 ? t : 5000;
        KParams.resHtml = await request(HOST);
    } catch (e) {
        console.error('初始化失败：', e.message);
    }
}

async function home(filter) {
    try {
        let resHtml = KParams.resHtml;
        if (!resHtml) throw new Error('首页请求失败');
        let classes = [
            {type_id:"12",type_name:"国剧"},{type_id:"13",type_name:"港剧"},{type_id:"14",type_name:"日剧"},{type_id:"15",type_name:"韩剧"},{type_id:"16",type_name:"美剧"},
            {type_id:"5",type_name:"爱情电影"},{type_id:"6",type_name:"动作电影"},{type_id:"7",type_name:"科幻电影"},{type_id:"8",type_name:"剧情电影"},{type_id:"9",type_name:"恐怖电影"},{type_id:"10",type_name:"喜剧电影"},{type_id:"11",type_name:"其他电影"},
            {type_id:"4",type_name:"综艺"},{type_id:"17",type_name:"大陆动漫"},{type_id:"18",type_name:"次元动漫"}
        ];
        return JSON.stringify({class: classes, filters: {}});
    } catch (e) {
        console.error('获取分类失败：', e.message);
        return JSON.stringify({class:[],filters:{}});
    }
}

async function homeVod() {
    try {
        let VODS = getVodList(KParams.resHtml).slice(0,20);
        return JSON.stringify({list: VODS});
    } catch (e) {
        console.error('推荐页失败：', e.message);
        return JSON.stringify({list:[]});
    }
}

async function category(tid, pg, filter, extend) {
    try {
        pg = parseInt(pg) || 1;
        let url = `${HOST}/as/${tid}-${pg}.html`;
        let VODS = getVodList(await request(url));
        return JSON.stringify({list:VODS, page:pg, pagecount:999, limit:30, total:29970});
    } catch (e) {
        console.error('分类页失败：', e.message);
        return JSON.stringify({list:[],page:1,pagecount:0,limit:30,total:0});
    }
}

async function search(){return JSON.stringify({list:[],page:1,pagecount:0});}

function getVodList(khtml) {
    try {
        if (!khtml) return [];
        let $ = load(khtml), kvods = [];
        $('.ajdfnv-3').each((_,item)=>{
            let $item = $(item);
            let link = $item.find('.kkfmdqwasda');
            let href = link.attr('href');
            let title = $item.find('.title').text().trim();
            let pic = link.find('img').attr('data-original') || link.find('img').attr('src');
            let remarks = $item.find('.aecccdfg,.rating-badge').text().trim() || '更新';
            if (pic && pic.startsWith('data:')) pic = '';
            if (href) kvods.push({vod_id:href, vod_name:title, vod_pic:pic, vod_remarks:remarks});
        });
        return kvods;
    } catch (e) {
        console.error('列表失败：', e.message);
        return [];
    }
}

async function detail(ids) {
    try {
        let url = !/^http/.test(ids) ? HOST+ids : ids;
        let html = await request(url), $ = load(html);
        let vod_name = $('.dfdgdasdaa .title,h1').text().trim();
        let vod_pic = $('.picture img').attr('data-original') || '';
        let vod_remarks = $('.aecccdfg').first().text().trim() || '';
        let vod_content = cutStr(html,'剧情简介','</p>') || cutStr(html,'简介：','<a') || '';
        let vod_director = cutStr(html,'导演：','</p>') || '';
        let vod_actor = cutStr(html,'主演：','</p>') || '';
        let vod_year = cutStr(html,'年份：','</p>') || '';
        let vod_area = cutStr(html,'地区：','<span') || '';
        let vod_type = cutStr(html,'类型：','</p>') || '';

        let playfrom = [], playList = [];
        $('.playlist').each((_,p)=>{
            let from = $(p).find('h3').text().trim();
            let list = [];
            $(p).find('ul li a').each((_,a)=>{
                let n = $(a).text().trim(), l = $(a).attr('href');
                if (l) list.push(n+'$'+l);
            });
            if (from) playfrom.push(from);
            if (list.length) playList.push(list.join('#'));
        });

        return JSON.stringify({list:[{
            vod_id:url, vod_name:vod_name, vod_pic:vod_pic, vod_remarks:vod_remarks,
            vod_year:vod_year, vod_type:vod_type, vod_area:vod_area,
            vod_director:vod_director, vod_actor:vod_actor, vod_content:vod_content.trim(),
            vod_play_from:playfrom.join('$$$'), vod_play_url:playList.join('$$$')
        }]});
    } catch (e) {
        console.error('详情失败：', e.message);
        return JSON.stringify({list:[]});
    }
}

async function play(flag, ids) {
    try {
        let playUrl = !/^http/.test(ids) ? HOST+ids : ids;
        let html = await request(playUrl), kurl='', kp=0;
        let m = html.match(/var player_.*?=([^]*?)</);
        if (m) kurl = safeParseJSON(m[1])?.url || '';

        if (!kurl) {
            let ifr = html.match(/<iframe[^>]*src=["']([^"']+)["']/i);
            if (ifr) {
                let src = ifr[1];
                kurl = src.includes('url=') ? src.split('url=')[1].split('&')[0] : src;
            }
        }

        if (kurl) {
            kurl = decodeURIComponent(kurl);
            if (kurl.startsWith('//')) kurl = 'https:'+kurl;
            if (!/\.(mp4|m3u8|flv|ts)/i.test(kurl)) {
                let j = safeParseJSON(await request(`https://v.70066.cc/video/v/${kurl}`));
                kurl = j?.url || '';
            }
        } else kp=1;

        return JSON.stringify({jx:0, parse:kp, url:kurl, header:DefHeader});
    } catch (e) {
        console.error('播放失败：', e.message);
        return JSON.stringify({jx:0,parse:0,url:'',header:{}});
    }
}

function dealStr(str,d=''){if(!str)return d;return String(str).replace(/\s+/g,' ').trim()||d;}
function cutStr(str,p='',s='',d='',c=true){try{let a=new RegExp(RegExp(p)+'([\\s\\S]*?)'+RegExp(s),'i');let m=str.match(a);return m? (c?dealStr(m[1]):m[1]) : d;}catch(e){return d;}}
function safeParseJSON(s){try{return JSON.parse(s);}catch(e){return null;}}

async function request(u,opt={}){
    try{
        opt.method=(opt.method||'get').toLowerCase();
        if(['get','head'].includes(opt.method))delete opt.data;
        let o={headers:opt.headers||KParams.headers,timeout:parseInt(opt.timeout)||KParams.timeout,...opt};
        let r=await req(u,o);
        return opt.withHeaders?JSON.stringify({...r.headers,body:r?.content||''}):r?.content||'';
    }catch(e){console.error(u+'→失败');return opt.withHeaders?JSON.stringify({body:''}):'';}
}

export function __jsEvalReturn() {
    return {init,home,homeVod,category,search,detail,play,proxy:null};
}