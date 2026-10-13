/*
@header({
  searchable: 1,
  filterable: 1,
  quickSearch: 1,
  title: '布谷音乐[音]',
  author: 'cupid',
  lang: 'cat'
})
*/

const API_SEARCH = 'http://buguyy.top/api/search';
const API_URL = 'http://buguyy.top/api/geturl';
const API_HOTLIST = 'http://buguyy.top/api/hotlist';
const API_NEWLIST = 'http://buguyy.top/api/newlist';
const API_RANDOM = 'http://buguyy.top/api/random';
const PIC = 'https://copyright.bdstatic.com/vcg/creative/fcbafd433c4960b5039ef96217838ecf.jpg@h_1280';
const headers = {
  'User-Agent': 'Mozilla/5.0',
  'Referer': 'https://buguyy.top/'
};
const DEFAULT_SEARCH_KEYWORD = '周杰伦';

const CLASSES = [
  { type_id: 'random', type_name: '精选歌曲' },
  { type_id: 'hot', type_name: '热门歌曲' },
  { type_id: 'new', type_name: '最新歌曲' },
  { type_id: 'search', type_name: '歌手筛选' }
];

const SEARCH_FILTERS = [{
  key: 'keyword',
  name: '关键词',
  value: ['周杰伦','陈奕迅','林俊杰','邓紫棋','薛之谦','张学友','刘德华','王菲','孙燕姿','李荣浩','毛不易','张杰','许嵩','汪苏泷','周深','五月天','Beyond','蔡依林','梁静茹','张惠妹','周华健','任贤齐','赵雷','朴树','华晨宇','杨宗纬','张碧晨','王力宏','陶喆','伍佰','许巍'].map(x => ({ n: x, v: x }))
}];

function text(v) { return String(v == null ? '' : v).trim(); }
function safeJson(v, def) { try { return JSON.parse(String(v || '')); } catch (e) { return def; } }
function cleanAbout(s) { return text(s).replace(/<br\s*\/?\s*>/gi, ' ').replace(/\[[^\]]+\]/g, '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim(); }
function enc(v) { return encodeURIComponent(String(v == null ? '' : v)); }
function dec(v) { try { return decodeURIComponent(String(v || '')); } catch (e) { return String(v || ''); } }

function parseBase64Json(v) {
  v = text(v);
  if (!v) return {};
  try {
    v = v.replace(/-/g, '+').replace(/_/g, '/');
    while (v.length % 4) v += '=';
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=';
    let str = '', i = 0;
    v = v.replace(/[^A-Za-z0-9+/=]/g, '');
    while (i < v.length) {
      const e1 = chars.indexOf(v.charAt(i++));
      const e2 = chars.indexOf(v.charAt(i++));
      const e3 = chars.indexOf(v.charAt(i++));
      const e4 = chars.indexOf(v.charAt(i++));
      const c1 = (e1 << 2) | (e2 >> 4);
      const c2 = ((e2 & 15) << 4) | (e3 >> 2);
      const c3 = ((e3 & 3) << 6) | e4;
      str += String.fromCharCode(c1);
      if (e3 !== 64) str += String.fromCharCode(c2);
      if (e4 !== 64) str += String.fromCharCode(c3);
    }
    return JSON.parse(decodeURIComponent(escape(str)));
  } catch (e) { return {}; }
}

function parseExtend(x) {
  if (!x) return {};
  if (typeof x === 'object') return x;
  x = text(x);
  const b = parseBase64Json(x);
  if (Object.keys(b).length) return b;
  const j = safeJson(x, null);
  if (j && typeof j === 'object') return j;
  const out = {};
  x.replace(/^\?/, '').split('&').forEach(seg => {
    const p = seg.split('=');
    if (p[0]) out[p[0]] = dec(p.slice(1).join('='));
  });
  return out;
}

async function reqText(url, opt) {
  opt = opt || {};
  const o = { headers: Object.assign({}, headers, opt.headers || {}), timeout: opt.timeout || 15000 };
  let r = '';
  if (typeof Java !== 'undefined' && Java && Java.req) {
    r = await Java.req(url, o);
  } else if (typeof req !== 'undefined') {
    r = await req(url, o);
  } else if (typeof request !== 'undefined') {
    r = await request(url, o);
  }
  if (typeof r === 'string') return r;
  return String((r && (r.content || r.body || r.data)) || r || '');
}

async function requestJson(url) {
  const html = await reqText(url);
  const js = safeJson(html, null);
  return js && typeof js === 'object' ? js : {};
}

function safeJsonObj(v, def) {
  if (v && typeof v === 'object') return v;
  return safeJson(v, def || {});
}

function normalizeSong(song) {
  song = song || {};
  const id = text(song.id);
  const name = text(song.title || song.name || '未知歌曲');
  const pic = text(song.picurl || song.pic || '') || PIC;
  const singer = text(song.singer || song.artist || '');
  const about = cleanAbout(song.about || song.artist || '');
  return {
    vod_id: 'song@@' + enc(id) + '@@' + enc(name),
    vod_name: name,
    vod_pic: pic,
    vod_remarks: singer || (about ? about.slice(0, 24) : '布谷音乐')
  };
}

async function fetchList(url, limit) {
  const data = await requestJson(url);
  const raw = Array.isArray(data.data) ? data.data : (Array.isArray(data.list) ? data.list : (Array.isArray(data) ? data : []));
  return raw.slice(0, Math.max(1, Number(limit) || 20));
}

async function fetchSongs(keyword, limit) {
  keyword = text(keyword);
  if (!keyword) return [];
  const data = await requestJson(API_SEARCH + '?keyword=' + enc(keyword) + '&limit=' + (Number(limit) || 20));
  return Array.isArray(data.data) ? data.data : [];
}

async function fetchPlayUrl(id) {
  id = text(id);
  if (!id) return '';
  const data = await requestJson(API_URL + '?id=' + enc(id));
  return text(data.url || (data.data && data.data.url) || '');
}

function resolveKeyword(tid, extend) {
  extend = parseExtend(extend);
  return text(extend.keyword || extend.wd || extend.q || (tid === 'search' ? DEFAULT_SEARCH_KEYWORD : ''));
}

async function home(filter) {
  const list = (await fetchList(API_RANDOM, 20).catch(() => [])).map(normalizeSong);
  return JSON.stringify({ class: CLASSES, filters: { search: SEARCH_FILTERS }, list });
}

async function homeT4(reqObj) {
  return home(reqObj && reqObj.filter);
}

async function homeVod() {
  const list = (await fetchList(API_RANDOM, 20).catch(() => [])).map(normalizeSong);
  return JSON.stringify({ list });
}

async function category(tid, pg, filter, extend) {
  if (tid && typeof tid === 'object') {
    const reqObj = tid;
    return category(reqObj.tid || reqObj.t || reqObj.id || 'hot', reqObj.pg || reqObj.page || 1, reqObj.filter || false, reqObj.extend || reqObj.ext || reqObj.f || {});
  }
  pg = Number(pg) || 1;
  const limit = 20;
  let rows = [];
  if (tid === 'hot' || tid === 'new' || tid === 'random') {
    const url = tid === 'hot' ? API_HOTLIST : (tid === 'new' ? API_NEWLIST : API_RANDOM);
    rows = await fetchList(url, limit).catch(() => []);
  } else {
    rows = await fetchSongs(resolveKeyword(tid, extend) || DEFAULT_SEARCH_KEYWORD, limit).catch(() => []);
  }
  const list = rows.map(normalizeSong);
  return JSON.stringify({ code: 1, msg: '数据列表', page: pg, pagecount: 1, limit, total: list.length, list });
}

async function search(wd, quick, pg) {
  pg = Number(pg) || 1;
  const list = (await fetchSongs(wd, 20).catch(() => [])).map(normalizeSong);
  return JSON.stringify({ code: 1, msg: '数据列表', page: pg, pagecount: 1, limit: 20, total: list.length, list });
}

async function detail(ids) {
  if (ids && typeof ids === 'object' && !Array.isArray(ids)) ids = ids.ids || ids.id || ids.vod_id || '';
  const idStr = Array.isArray(ids) ? text(ids[0]) : text(ids);
  if (!idStr) return { list: [] };
  const parts = idStr.split('@@');
  const songId = dec(parts[1] || idStr);
  const songName = dec(parts[2] || '布谷音乐');
  const displayName = text(songName || ('歌曲-' + songId));
  return JSON.stringify({ code: 1, msg: '数据列表', list: [{
    vod_id: idStr,
    vod_name: displayName,
    vod_pic: '',
    vod_remarks: '布谷音乐',
    type_name: '音乐',
    vod_content: '布谷音乐',
    vod_play_from: '布谷音乐',
    vod_play_url: displayName + '$' + songId
  }] });
}

async function play(flag, id, flags) {
  if (flag && typeof flag === 'object') {
    const reqObj = flag;
    return play(reqObj.flag || '', reqObj.id || reqObj.play || reqObj.url || '', reqObj.flags || []);
  }
  id = text(id);
  let playUrl = /^https?:\/\//i.test(id) ? id : await fetchPlayUrl(id).catch(() => '');
  return JSON.stringify({ parse: 0, jx: 0, playUrl: '', url: playUrl, header: headers, msg: playUrl ? '' : '播放地址解析失败' });
}

async function homeContent(filter) { return safeJsonObj(await home(filter), { class: [], filters: {}, list: [] }); }
async function homeVideoContent() { return safeJsonObj(await homeVod(), { list: [] }); }
async function categoryContent(tid, pg, filter, extend) { return safeJsonObj(await category(tid, pg, filter, extend || {}), { list: [] }); }
async function detailContent(ids) { return safeJsonObj(await detail(ids), { list: [] }); }
async function searchContent(wd, quick, pg) { return safeJsonObj(await search(wd, quick, pg || 1), { list: [] }); }
async function playerContent(flag, id, flags) { return safeJsonObj(await play(flag, id, flags), { parse: 1, url: id }); }

export function __jsEvalReturn() {
  return {
    init: function () {},
    home,
    homeVod,
    category,
    detail,
    search,
    play,
    homeContent,
    homeVideoContent,
    categoryContent,
    detailContent,
    searchContent,
    playerContent
  };
}
