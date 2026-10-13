/*
@header({
  searchable: 1,
  filterable: 0,
  quickSearch: 0,
  title: '⚽ 体育cat｜聚合',
  author: 'OpenClaw',
  lang: 'cat',
  style: { type: 'rect', ratio: 0.75 }
})
*/


const __sports_src_0 = (function () {


let host = 'https://www.88kanqiu.la';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36';
const headers = {
  'User-Agent': UA,
  'Referer': host + '/',
  'Accept': 'text/html,application/json,*/*'
};

const B64_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

function stripHtml(s) {
  return String(s || '')
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, ' ')
    .trim();
}

function absUrl(url) {
  url = String(url || '').trim();
  if (!url) return '';
  if (/^https?:\/\//i.test(url)) return url;
  if (url.indexOf('//') === 0) return 'https:' + url;
  if (url.charAt(0) === '/') return host + url;
  return host + '/' + url;
}

function safeJson(text, def) {
  try { return JSON.parse(text || '{}'); } catch (e) { return def || {}; }
}

// TV 端 JS 环境不一定有 atob/TextDecoder；这里按 PHP 源的 base64_decode 逻辑手写 UTF-8 解码。
function base64ToUtf8(str) {
  str = String(str || '').replace(/[^A-Za-z0-9+/=]/g, '');
  const bytes = [];
  for (let i = 0; i < str.length; i += 4) {
    const c1 = B64_CHARS.indexOf(str.charAt(i));
    const c2 = B64_CHARS.indexOf(str.charAt(i + 1));
    const c3 = B64_CHARS.indexOf(str.charAt(i + 2));
    const c4 = B64_CHARS.indexOf(str.charAt(i + 3));
    if (c1 < 0 || c2 < 0) continue;
    const n = (c1 << 18) | (c2 << 12) | ((c3 < 0 ? 0 : c3) << 6) | (c4 < 0 ? 0 : c4);
    bytes.push((n >> 16) & 255);
    if (str.charAt(i + 2) !== '=') bytes.push((n >> 8) & 255);
    if (str.charAt(i + 3) !== '=') bytes.push(n & 255);
  }

  let out = '';
  for (let i = 0; i < bytes.length;) {
    const b1 = bytes[i++];
    if (b1 < 0x80) {
      out += String.fromCharCode(b1);
    } else if (b1 >= 0xc0 && b1 < 0xe0) {
      const b2 = bytes[i++] || 0;
      out += String.fromCharCode(((b1 & 0x1f) << 6) | (b2 & 0x3f));
    } else if (b1 >= 0xe0 && b1 < 0xf0) {
      const b2 = bytes[i++] || 0;
      const b3 = bytes[i++] || 0;
      out += String.fromCharCode(((b1 & 0x0f) << 12) | ((b2 & 0x3f) << 6) | (b3 & 0x3f));
    } else {
      const b2 = bytes[i++] || 0;
      const b3 = bytes[i++] || 0;
      const b4 = bytes[i++] || 0;
      const cp = ((b1 & 0x07) << 18) | ((b2 & 0x3f) << 12) | ((b3 & 0x3f) << 6) | (b4 & 0x3f);
      const u = cp - 0x10000;
      out += String.fromCharCode(0xd800 + (u >> 10), 0xdc00 + (u & 0x3ff));
    }
  }
  return out;
}

function decodePlaySource(raw) {
  raw = String(raw || '').trim();
  if (!raw) return null;
  for (let prefix = 0; prefix <= 8; prefix++) {
    for (let suffix = 0; suffix <= 4; suffix++) {
      if (raw.length <= prefix + suffix) continue;
      const candidate = raw.slice(prefix, raw.length - suffix);
      try {
        const decoded = base64ToUtf8(candidate);
        const pos = decoded.indexOf('{');
        if (pos < 0) continue;
        const obj = JSON.parse(decoded.slice(pos));
        if (obj && typeof obj === 'object') return obj;
      } catch (e) {}
    }
  }
  return null;
}

function toDirectPlayUrl(url) {
  url = String(url || '').trim();
  if (!url) return '';
  const m = url.match(/[?&]url=([^&]+)/);
  if (m && m[1]) {
    try { return decodeURIComponent(m[1]); } catch (e) { return m[1]; }
  }
  return url;
}

async function fetchText(url, referer) {
  const hd = {
    'User-Agent': UA,
    'Referer': referer || host + '/',
    'Accept': 'text/html,application/json,*/*'
  };

  // 部分壳只有 Java.req，部分壳只有 req；两种都兼容。
  if (typeof Java !== 'undefined' && Java && Java.req) {
    const r = Java.req(url, { headers: hd });
    return String((r && (r.body || r.content)) || '');
  }
  const r2 = await req(url, { headers: hd });
  return String((r2 && (r2.content || r2.body)) || '');
}

function getClasses() {
  return [
    { type_id: 'live', type_name: '正在直播' },
    { type_id: '0', type_name: '全部直播' },
    { type_id: '1', type_name: '篮球直播' },
    { type_id: '8', type_name: '足球直播' },
    { type_id: '21', type_name: '其他直播' }
  ];
}

function parseList(html, onlyLiving) {
  const list = [];
  const reg = /<li[^>]*class=["'][^"']*list-group-item[^"']*["'][^>]*>[\s\S]*?<\/li>/gi;
  let m;
  while ((m = reg.exec(String(html || ''))) !== null) {
    const item = m[0];
    const hrefMatch = item.match(/<a[^>]+href=["']([^"']*\/live\/\d+\/play[^"']*)["'][^>]*>/i);
    if (!hrefMatch) continue;

    const time = stripHtml((item.match(/class=["'][^"']*category-game-time[^"']*["'][^>]*>([\s\S]*?)<\//i) || [])[1]);
    const gameType = stripHtml((item.match(/class=["'][^"']*game-type[^"']*["'][^>]*>([\s\S]*?)<\//i) || [])[1]);

    const teams = [];
    const teamReg = /class=["'][^"']*team-name[^"']*["'][^>]*>([\s\S]*?)<\//gi;
    let tm;
    while ((tm = teamReg.exec(item)) !== null) teams.push(stripHtml(tm[1]));

    let title = [time, gameType, teams.length >= 2 ? teams[0] + ' vs ' + teams[1] : teams.join(' vs ')].filter(Boolean).join(' ').trim();
    if (!title || title === 'vs') title = stripHtml(item).replace(/直播中|观看|高清|视频直播/g, '').trim();
    if (!title) continue;

    const btnTextMatch = item.match(/<a[^>]+href=["'][^"']*\/live\/\d+\/play[^"']*["'][^>]*>([\s\S]*?)<\/a>/i);
    const remark = stripHtml(btnTextMatch ? btnTextMatch[1] : '') || '直播中';
    if (onlyLiving && remark !== '直播中') continue;
    const picMatch = item.match(/<img[^>]+(?:data-src|src)=["']([^"']+)["']/i);

    list.push({
      vod_id: absUrl(hrefMatch[1]) + '###' + encodeURIComponent(title),
      vod_name: title,
      vod_pic: absUrl(picMatch ? picMatch[1] : '/static/img/default.png'),
      vod_remarks: remark
    });
  }
  return list;
}

async function fetchGroupList(group) {
  let paths = ['/'];
  if (group === 'basketball') {
    paths = ['/match/1/live', '/match/2/live', '/match/20/live', '/match/4/live'];
  } else if (group === 'football') {
    paths = ['/match/3/live', '/match/8/live', '/match/9/live', '/match/10/live', '/match/14/live', '/match/15/live', '/match/12/live', '/match/13/live', '/match/7/live', '/match/11/live', '/match/27/live', '/match/26/live', '/match/31/live', '/match/23/live'];
  } else if (group === 'other') {
    paths = ['/match/21/live', '/match/29/live', '/match/25/live', '/match/19/live', '/match/38/live'];
  }

  const all = [];
  const seen = {};
  for (let i = 0; i < paths.length; i++) {
    try {
      const html = await fetchText(host + paths[i], host + '/');
      const items = parseList(html);
      for (let j = 0; j < items.length; j++) {
        const key = items[j].vod_id;
        if (seen[key]) continue;
        seen[key] = true;
        all.push(items[j]);
      }
    } catch (e) {}
  }
  return all;
}

async function init(cfg) {
  if (cfg && cfg.ext && String(cfg.ext).indexOf('http') === 0) host = String(cfg.ext).trim().replace(/\/$/, '');
}

async function home(filter) {
  return JSON.stringify({ class: getClasses(), filters: {} });
}

async function homeVod() {
  return await category('0', 1, false, {});
}

async function category(tid, pg, filter, extend) {
  tid = String((extend && extend.cateId) || tid || '0');
  pg = parseInt(pg) || 1;
  let group = '';
  if (tid === '1' || tid === 'basketball') group = 'basketball';
  else if (tid === '8' || tid === 'football') group = 'football';
  else if (tid === '21' || tid === 'other') group = 'other';

  let list = [];
  try {
    const onlyLiving = tid === 'live';
    list = group ? await fetchGroupList(group) : parseList(await fetchText(host + '/', host + '/'), onlyLiving);
  } catch (e) {
    list = [];
  }
  return JSON.stringify({ code: 1, msg: '数据列表', page: pg, pagecount: 1, limit: 20, total: list.length, list });
}

async function detail(id) {
  id = Array.isArray(id) ? id[0] : id;
  let realId = String(id || '');
  let displayName = '赛事直播';
  if (realId.indexOf('###') >= 0) {
    const parts = realId.split('###');
    realId = parts[0];
    try { displayName = decodeURIComponent(parts[1] || '赛事直播'); } catch (e) { displayName = parts[1] || '赛事直播'; }
  }

  const match = realId.match(/\/live\/(\d+)\/play/);
  const gameId = match ? match[1] : '';
  if (!gameId) return JSON.stringify({ code: 1, page: 1, pagecount: 1, limit: 0, total: 0, list: [] });

  let playUrls = '';
  try {
    const content = await fetchText(host + '/live/' + gameId + '/source', realId);
    const json = safeJson(content, {});
    const data = decodePlaySource(json.data || '');
    const links = (data && data.links) || [];
    const arr = [];
    for (let i = 0; i < links.length; i++) {
      const u = toDirectPlayUrl(links[i].url || '');
      if (u) arr.push((links[i].name || ('线路' + (i + 1))) + '$' + u);
    }
    playUrls = arr.join('#');
  } catch (e) {
    playUrls = '';
  }

  return JSON.stringify({
    code: 1,
    msg: '数据列表',
    page: 1,
    pagecount: 1,
    limit: 1,
    total: 1,
    list: [{
      vod_id: realId,
      vod_name: displayName,
      vod_pic: host + '/static/img/default.png',
      vod_remarks: '直播中',
      vod_play_from: '88看球',
      vod_play_url: playUrls,
      vod_content: '实时体育直播'
    }]
  });
}

async function search(wd, quick, pg) {
  return JSON.stringify({ code: 1, msg: '数据列表', page: parseInt(pg) || 1, pagecount: 1, limit: 20, total: 0, list: [] });
}

async function play(flag, id, flags) {
  const isDirect = /\.(m3u8|mp4)(\?|$)/i.test(String(id || ''));
  return JSON.stringify({ parse: isDirect ? 0 : 1, url: id, header: headers });
}

// OK影视/部分 CAT 壳兼容入口。
async function homeContent(filter) { return safeJson(await home(filter), { class: [], filters: {} }); }
async function homeVideoContent() { return safeJson(await homeVod(), { list: [] }); }
async function categoryContent(tid, pg, filter, extend) { return safeJson(await category(tid, pg, filter, extend || {}), { list: [] }); }
async function detailContent(ids) { return safeJson(await detail(ids), { list: [] }); }
async function searchContent(wd, quick, pg) { return safeJson(await search(wd, quick, pg || 1), { list: [] }); }
async function playerContent(flag, id, flags) { return safeJson(await play(flag, id, flags), { parse: 1, url: id }); }
  return { init, home, homeVod, category, search, detail, play, homeContent, homeVideoContent, categoryContent, detailContent, searchContent, playerContent };
})();


const __sports_src_1 = (function () {


let host = 'https://kafeizhibo.cc';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36';
const headers = {
  'User-Agent': UA,
  'Referer': host + '/pc',
  'Accept': 'application/json, text/plain, */*'
};

function safeJson(text, def) {
  try { return JSON.parse(text || '{}'); } catch (e) { return def || {}; }
}

function absUrl(url) {
  url = String(url || '').trim();
  if (!url) return '';
  if (/^https?:\/\//i.test(url)) return url;
  if (url.indexOf('//') === 0) return 'https:' + url;
  if (url.charAt(0) === '/') return host + url;
  return host + '/' + url;
}

function clean(s) {
  return String(s || '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
}

async function fetchJson(url) {
  const r = await req(url, { headers });
  return safeJson((r && (r.content || r.body)) || '{}', {});
}

function getClasses() {
  return [
    { type_id: 'all', type_name: '全部直播' },
    { type_id: 'hot', type_name: '热门直播' },
    { type_id: 'nba', type_name: 'NBA' },
    { type_id: '1', type_name: '足球直播' },
    { type_id: '2', type_name: '篮球直播' },
    { type_id: '3', type_name: '网球直播' },
    { type_id: '19', type_name: '台球直播' },
    { type_id: 'schedule', type_name: '赛程列表' },
    { type_id: 'recordings', type_name: '录像' }
  ];
}

function titleOf(it) {
  const mi = it.match_info || {};
  const league = it.league_name || mi.league_name || it.league || '';
  const home = it.home_team || mi.home_team || (it.homeTeam && it.homeTeam.name) || '';
  const away = it.away_team || mi.away_team || (it.awayTeam && it.awayTeam.name) || '';
  const title = it.title || it.name || '';
  if (title && title !== it.name) return clean(title);
  if (league && home && away) return clean(league + ' ' + home + ' vs ' + away);
  return clean(title || it.name || ('直播间 ' + (it.room_id || it.id || '')));
}

function remarkOf(it) {
  const parts = [];
  const status = it.status || (it.match_info && it.match_info.status) || '';
  if (status === 'live' || it.is_live) parts.push('直播中');
  else if (status === 'online') parts.push('在线');
  else if (status === 'upcoming') parts.push('未开赛');
  else if (status) parts.push(status);
  const score = (it.home_score !== undefined && it.away_score !== undefined) ? (it.home_score + '-' + it.away_score) : '';
  if (score && score !== '0-0') parts.push(score);
  if (it.heat) parts.push('热度:' + it.heat);
  if (it.name && it.title && it.name !== it.title) parts.push(it.name);
  return clean(parts.join(' ')) || '直播';
}

function picOf(it) {
  return absUrl(it.screenshot || it.avatar || it.home_team_logo || it.away_team_logo || (it.homeTeam && it.homeTeam.logo) || (it.awayTeam && it.awayTeam.logo) || '/images/logo.png');
}

function itemToVod(it) {
  const roomId = it.room_id || (it.archor && it.archor.room_id) || (Array.isArray(it.archors) && it.archors[0] && it.archors[0].room_id) || '';
  if (!roomId) return null;
  return {
    vod_id: String(roomId) + '###' + encodeURIComponent(titleOf(it)),
    vod_name: titleOf(it),
    vod_pic: picOf(it),
    vod_remarks: remarkOf(it)
  };
}

function recordingToVod(it) {
  const matchId = it.match_id || it.id || '';
  if (!matchId) return null;
  const name = titleOf(it);
  return {
    vod_id: 'rec$' + String(matchId) + '###' + encodeURIComponent(name),
    vod_name: name,
    vod_pic: absUrl(it.cover_image || it.screenshot || it.home_team_logo || it.away_team_logo || '/images/logo.png'),
    vod_remarks: clean([it.start_time || '', it.recording_count ? ('录像:' + it.recording_count) : '录像'].filter(Boolean).join(' '))
  };
}

async function init(cfg) {
  if (cfg && cfg.ext && String(cfg.ext).indexOf('http') === 0) host = String(cfg.ext).trim().replace(/\/$/, '');
}

async function home(filter) {
  return JSON.stringify({ class: getClasses(), filters: {} });
}

async function homeVod() {
  return await category('all', 1, false, {});
}

async function category(tid, pg, filter, extend) {
  tid = String((extend && extend.cateId) || tid || 'all');
  pg = parseInt(pg) || 1;
  const size = 30;
  let apiUrl = '';

  if (tid === 'schedule') {
    apiUrl = host + '/api/v1/schedule?type=all&page=' + pg + '&size=' + size + '&_t=' + Date.now();
  } else if (tid === 'recordings') {
    apiUrl = host + '/api/v1/recordings?page=' + pg + '&size=' + size + '&_t=' + Date.now();
  } else if (tid === 'nba') {
    // 官网没有单独 nba 参数；用篮球赛程聚合后按 NBA 关键字过滤，有 NBA 时显示 NBA，无 NBA 时为空不混入其他篮球。
    apiUrl = host + '/api/v1/schedule?type=2&page=' + pg + '&size=100&_t=' + Date.now();
  } else {
    const type = tid === 'all' ? '' : tid;
    apiUrl = host + '/api/v1/archor?type=' + encodeURIComponent(type) + '&_t=' + Date.now();
  }

  let list = [];
  let total = 0;
  try {
    const json = await fetchJson(apiUrl);
    const data = Array.isArray(json.data) ? json.data : [];
    const seen = {};
    for (let i = 0; i < data.length; i++) {
      if (tid === 'recordings') {
        const vod = recordingToVod(data[i]);
        if (vod && !seen[vod.vod_id]) { seen[vod.vod_id] = true; list.push(vod); }
      } else if (tid === 'nba') {
        const title = titleOf(data[i]);
        if (!/NBA|美职篮|美国职业篮球/i.test(title)) continue;
        if (Array.isArray(data[i].archors) && data[i].archors.length) {
          for (let j = 0; j < data[i].archors.length; j++) {
            const merged = Object.assign({}, data[i], data[i].archors[j], {
              title,
              screenshot: data[i].screenshot || data[i].archors[j].screenshot
            });
            const vod = itemToVod(merged);
            if (vod && !seen[vod.vod_id]) { seen[vod.vod_id] = true; list.push(vod); }
          }
        } else {
          const vod = itemToVod(data[i]);
          if (vod && !seen[vod.vod_id]) { seen[vod.vod_id] = true; list.push(vod); }
        }
      } else if (tid === 'schedule' && Array.isArray(data[i].archors) && data[i].archors.length) {
        for (let j = 0; j < data[i].archors.length; j++) {
          const merged = Object.assign({}, data[i], data[i].archors[j], {
            title: titleOf(data[i]),
            screenshot: data[i].screenshot || data[i].archors[j].screenshot
          });
          const vod = itemToVod(merged);
          if (vod && !seen[vod.vod_id]) { seen[vod.vod_id] = true; list.push(vod); }
        }
      } else {
        const vod = itemToVod(data[i]);
        if (vod && !seen[vod.vod_id]) { seen[vod.vod_id] = true; list.push(vod); }
      }
    }
    total = tid === 'nba' ? list.length : (json.total || list.length);
  } catch (e) {
    list = [];
  }
  return JSON.stringify({ code: 1, msg: '数据列表', page: pg, pagecount: 1, limit: size, total, list });
}

async function detail(id) {
  id = Array.isArray(id) ? id[0] : id;
  let roomId = String(id || '');
  let displayName = '咖啡直播';
  if (roomId.indexOf('###') >= 0) {
    const parts = roomId.split('###');
    roomId = parts[0];
    try { displayName = decodeURIComponent(parts[1] || displayName); } catch (e) { displayName = parts[1] || displayName; }
  }
  if (roomId.indexOf('rec$') === 0) {
    const matchId = roomId.slice(4);
    let vod = {
      vod_id: roomId,
      vod_name: displayName,
      vod_pic: host + '/images/logo.png',
      vod_remarks: '录像',
      vod_play_from: '咖啡录像',
      vod_play_url: '',
      vod_content: '咖啡直播赛事录像'
    };
    try {
      const json = await fetchJson(host + '/api/v1/match/' + encodeURIComponent(matchId) + '/recordings?_t=' + Date.now());
      const data = json.data || {};
      const match = data.match || {};
      const urls = [];
      const replays = Array.isArray(data.replays) ? data.replays : [];
      const highlights = Array.isArray(data.highlights) ? data.highlights : [];
      for (let i = 0; i < replays.length; i++) {
        if (replays[i].video_url) urls.push(clean(replays[i].title || ('录像' + (i + 1))) + '$' + replays[i].video_url);
      }
      for (let i = 0; i < highlights.length; i++) {
        if (highlights[i].video_url) urls.push(clean(highlights[i].title || ('集锦' + (i + 1))) + '$' + highlights[i].video_url);
      }
      vod = {
        vod_id: roomId,
        vod_name: titleOf(match) || displayName,
        vod_pic: absUrl((replays[0] && replays[0].cover_image) || match.cover_image || match.home_team_logo || match.away_team_logo || '/images/logo.png'),
        vod_remarks: clean([match.start_time || '', match.home_score !== undefined ? (match.home_score + '-' + match.away_score) : ''].filter(Boolean).join(' ')) || '录像',
        vod_play_from: '咖啡录像',
        vod_play_url: urls.join('#'),
        vod_content: '咖啡直播赛事录像'
      };
    } catch (e) {}
    return JSON.stringify({ code: 1, msg: '数据列表', page: 1, pagecount: 1, limit: 1, total: 1, list: [vod] });
  }
  if (!roomId) return JSON.stringify({ code: 1, page: 1, pagecount: 1, limit: 0, total: 0, list: [] });

  let vod = {
    vod_id: roomId,
    vod_name: displayName,
    vod_pic: host + '/images/logo.png',
    vod_remarks: '直播',
    vod_play_from: '咖啡直播',
    vod_play_url: '',
    vod_content: '咖啡直播实时体育直播'
  };

  try {
    const json = await fetchJson(host + '/api/v1/room/' + encodeURIComponent(roomId) + '?_t=' + Date.now());
    const data = json.data || {};
    const room = data.room_info || {};
    const archor = data.archor || {};
    const signals = Array.isArray(data.signals) ? data.signals : [];
    const urls = [];
    const seen = {};

    function addLine(name, url) {
      url = String(url || '').trim();
      if (!url || seen[url]) return;
      seen[url] = true;
      urls.push(clean(name || ('线路' + (urls.length + 1))) + '$' + url);
    }

    for (let i = 0; i < signals.length; i++) addLine(signals[i].name, signals[i].stream_url);
    addLine(archor.name, archor.stream_url);

    const title = room.title || displayName;
    vod = {
      vod_id: roomId,
      vod_name: clean(title),
      vod_pic: absUrl(archor.screenshot || room.avatar || archor.avatar || '/images/logo.png'),
      vod_remarks: remarkOf(Object.assign({}, room, archor)),
      vod_play_from: '咖啡直播',
      vod_play_url: urls.join('#'),
      vod_content: clean(room.notice || room.notice_h5 || '咖啡直播实时体育直播')
    };
  } catch (e) {}

  return JSON.stringify({ code: 1, msg: '数据列表', page: 1, pagecount: 1, limit: 1, total: 1, list: [vod] });
}

async function search(wd, quick, pg) {
  return JSON.stringify({ code: 1, msg: '数据列表', page: parseInt(pg) || 1, pagecount: 1, limit: 20, total: 0, list: [] });
}

async function play(flag, id, flags) {
  return JSON.stringify({ parse: 0, url: id, header: headers });
}

async function homeContent(filter) { return safeJson(await home(filter), { class: [], filters: {} }); }
async function homeVideoContent() { return safeJson(await homeVod(), { list: [] }); }
async function categoryContent(tid, pg, filter, extend) { return safeJson(await category(tid, pg, filter, extend || {}), { list: [] }); }
async function detailContent(ids) { return safeJson(await detail(ids), { list: [] }); }
async function searchContent(wd, quick, pg) { return safeJson(await search(wd, quick, pg || 1), { list: [] }); }
async function playerContent(flag, id, flags) { return safeJson(await play(flag, id, flags), { parse: 0, url: id }); }
  return { init, home, homeVod, category, search, detail, play, homeContent, homeVideoContent, categoryContent, detailContent, searchContent, playerContent };
})();


const __sports_src_2 = (function () {


const API_BASE = 'https://01cs01.fusk39cd.com/api/web/live_lists';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';
const headers = {
  'User-Agent': UA,
  'Accept': 'application/json, text/plain, */*',
  'Referer': 'https://01cs01.fusk39cd.com/'
};
const PAGE_SIZE = 20;

function safeString(v) {
  if (v === null || v === undefined || v === 'null') return '';
  return String(v);
}

function safeJson(text, def) {
  if (text && typeof text === 'object') return text;
  try { return JSON.parse(text || '{}'); } catch (e) { return def || {}; }
}

async function fetchJson(url) {
  if (typeof Java !== 'undefined' && Java && Java.req) {
    const r = Java.req(url, { headers });
    return safeJson((r && (r.body || r.content)) || '{}', {});
  }
  const r2 = await req(url, { headers });
  return safeJson((r2 && (r2.content || r2.body)) || '{}', {});
}

function getClasses() {
  return [
    { type_id: '1', type_name: '全部' },
    { type_id: '2', type_name: '足球' },
    { type_id: '3', type_name: '篮球' }
  ];
}

async function init(cfg) {}

async function home(filter) {
  return JSON.stringify({ class: getClasses(), filters: {} });
}

async function homeVod() {
  return await category('1', 1, false, {});
}

async function category(tid, pg, filter, extend) {
  const page = Math.max(parseInt(pg || '1', 10) || 1, 1);
  const typeId = safeString(tid || '1') || '1';
  const list = [];

  try {
    const url = API_BASE + '/' + encodeURIComponent(typeId);
    const json = await fetchJson(url);
    const rows = json && json.code === 200 && json.data && Array.isArray(json.data.data) ? json.data.data : [];

    for (let i = 0; i < rows.length; i++) {
      const item = rows[i];
      if (!item.tournament_id) continue;
      const type = safeString(item.type || typeId);
      const tournamentId = safeString(item.tournament_id);
      const memberId = safeString(item.member_id);
      const homeTeam = safeString(item.home_team_zh);
      const awayTeam = safeString(item.away_team_zh);
      const name = [homeTeam, awayTeam].filter(Boolean).join(' VS ') || safeString(item.league_name_zh) || tournamentId;

      list.push({
        vod_id: type + '|' + tournamentId + '|' + memberId,
        vod_name: name,
        vod_pic: safeString(item.cover),
        vod_remarks: safeString(item.league_name_zh) || safeString(item.match_time) || safeString(item.status)
      });
    }
  } catch (e) {
    return JSON.stringify({ code: 1, page, pagecount: 1, limit: PAGE_SIZE, total: 0, list: [] });
  }

  return JSON.stringify({
    code: 1,
    msg: '数据列表',
    page,
    pagecount: list.length >= PAGE_SIZE ? page + 1 : page,
    limit: PAGE_SIZE,
    total: list.length,
    list
  });
}

async function detail(id) {
  const idList = Array.isArray(id) ? id : String(id || '').split(',').filter(Boolean);
  const list = [];

  for (let n = 0; n < idList.length; n++) {
    const vid = safeString(idList[n]).trim();
    const parts = vid.split('|');
    if (parts.length !== 3) continue;
    const type = parts[0];
    const tournamentId = parts[1];
    const memberId = parts[2];

    try {
      const url = API_BASE + '/' + encodeURIComponent(type) + '/detail/' + encodeURIComponent(tournamentId) + '?member_id=' + encodeURIComponent(memberId);
      const json = await fetchJson(url);
      if (!json || json.code !== 200) continue;

      const detailObj = json.data && json.data.detail ? json.data.detail : {};
      const moreArr = json.data && Array.isArray(json.data.more) ? json.data.more : [];
      const homeTeam = safeString(detailObj.home_team_zh);
      const awayTeam = safeString(detailObj.away_team_zh);
      const vodName = [homeTeam, awayTeam].filter(Boolean).join(' VS ') || safeString(detailObj.league_name_zh) || vid;

      const playFromList = [];
      const playUrlList = [];
      for (let i = 0; i < moreArr.length; i++) {
        const source = moreArr[i];
        const username = safeString(source.username) || ('线路' + (i + 1));
        const urls = [];
        const flv = safeString(source.screen_url);
        const m3u8 = safeString(source.screen_url_m3u8);
        if (flv) urls.push('线路一$' + flv);
        if (m3u8) urls.push('线路二$' + m3u8);
        if (!urls.length) continue;
        playFromList.push(username.replace(/\$|#/g, ''));
        playUrlList.push(urls.join('#'));
      }

      list.push({
        vod_id: vid,
        vod_name: vodName,
        vod_pic: safeString(detailObj.cover),
        type_name: safeString(detailObj.league_name_zh),
        vod_remarks: safeString(detailObj.match_time) || safeString(detailObj.status),
        vod_content: safeString(detailObj.room_notice) || '体育直播',
        vod_play_from: playFromList.join('$$$') || '919体育',
        vod_play_url: playUrlList.join('$$$') || ('暂无播放$' + vid)
      });
    } catch (e) {}
  }

  return JSON.stringify({ code: 1, msg: '数据列表', page: 1, pagecount: 1, limit: list.length, total: list.length, list });
}

async function search(wd, quick, pg) {
  return JSON.stringify({ code: 1, msg: '数据列表', page: parseInt(pg) || 1, pagecount: 1, limit: 20, total: 0, list: [] });
}

async function play(flag, id, flags) {
  const url = safeString(id).replace(/\*\*\*/g, '#');
  if (!/^https?:\/\//i.test(url)) return JSON.stringify({ parse: 0, jx: 0, url: '', msg: '暂无播放地址' });
  return JSON.stringify({ parse: 0, jx: 0, url, header: headers });
}

async function homeContent(filter) { return safeJson(await home(filter), { class: [], filters: {} }); }
async function homeVideoContent() { return safeJson(await homeVod(), { list: [] }); }
async function categoryContent(tid, pg, filter, extend) { return safeJson(await category(tid, pg, filter, extend || {}), { list: [] }); }
async function detailContent(ids) { return safeJson(await detail(ids), { list: [] }); }
async function searchContent(wd, quick, pg) { return safeJson(await search(wd, quick, pg || 1), { list: [] }); }
async function playerContent(flag, id, flags) { return safeJson(await play(flag, id, flags), { parse: 0, url: id }); }
  return { init, home, homeVod, category, search, detail, play, homeContent, homeVideoContent, categoryContent, detailContent, searchContent, playerContent };
})();


const __sports_src_3 = (function () {


let host = 'https://m.jrskk.com';
const hosts = ['https://m.jrskk.com', 'https://m.jrs21.com', 'https://www.jrs33.com', 'https://3.swjrzx.com'];
const UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1';
const defaultPic = 'https://im-imgs-bucket.oss-accelerate.aliyuncs.com/icon-192.png';
let cacheTime = 0;
let cacheHtml = '';

const B64_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

function stripHtml(s) {
  return String(s || '')
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, ' ')
    .trim();
}

function cleanText(s) { return String(s || '').replace(/\s+/g, ' ').trim(); }

function absUrl(url, base) {
  url = String(url || '').trim();
  base = base || host;
  if (!url) return '';
  if (/^https?:\/\//i.test(url)) return url;
  if (url.indexOf('//') === 0) return 'https:' + url;
  if (url.charAt(0) === '/') return base + url;
  return base + '/' + url;
}

function utf8ToBase64Url(str) {
  str = unescape(encodeURIComponent(String(str || '')));
  let out = '';
  for (let i = 0; i < str.length; i += 3) {
    const c1 = str.charCodeAt(i);
    const c2 = str.charCodeAt(i + 1);
    const c3 = str.charCodeAt(i + 2);
    out += B64_CHARS.charAt(c1 >> 2);
    out += B64_CHARS.charAt(((c1 & 3) << 4) | ((c2 || 0) >> 4));
    out += isNaN(c2) ? '=' : B64_CHARS.charAt(((c2 & 15) << 2) | ((c3 || 0) >> 6));
    out += isNaN(c3) ? '=' : B64_CHARS.charAt(c3 & 63);
  }
  return out.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function base64UrlToUtf8(str) {
  str = String(str || '').replace(/-/g, '+').replace(/_/g, '/');
  while (str.length % 4) str += '=';
  let bytes = [];
  for (let i = 0; i < str.length; i += 4) {
    const c1 = B64_CHARS.indexOf(str.charAt(i));
    const c2 = B64_CHARS.indexOf(str.charAt(i + 1));
    const c3 = B64_CHARS.indexOf(str.charAt(i + 2));
    const c4 = B64_CHARS.indexOf(str.charAt(i + 3));
    if (c1 < 0 || c2 < 0) continue;
    const n = (c1 << 18) | (c2 << 12) | ((c3 < 0 ? 0 : c3) << 6) | (c4 < 0 ? 0 : c4);
    bytes.push((n >> 16) & 255);
    if (str.charAt(i + 2) !== '=') bytes.push((n >> 8) & 255);
    if (str.charAt(i + 3) !== '=') bytes.push(n & 255);
  }
  let raw = '';
  for (let j = 0; j < bytes.length; j++) raw += String.fromCharCode(bytes[j]);
  try { return decodeURIComponent(escape(raw)); } catch (e) { return raw; }
}

function safeJson(text, def) { try { return JSON.parse(text || '{}'); } catch (e) { return def || {}; } }

function matchCategory(tid, league, name, stype, hot) {
  tid = String(tid || 'all');
  const text = league + ' ' + name;
  if (tid === 'all' || tid === 'live') return true;
  if (tid === 'hot') return !!hot || /(NBA|CBA|英超|西甲|意甲|德甲|法甲|欧冠|中超|世界杯|世俱杯|亚冠|热门)/i.test(text);
  if (tid === 'basketball') return stype === 'lq' || /(NBA|CBA|WNBA|NBL|篮球|篮)/i.test(text);
  if (tid === 'football') return stype === 'zq' || (/(足球|英超|西甲|意甲|德甲|法甲|欧冠|欧联|中超|亚冠|足协|世界杯|世俱|巴西甲|巴西乙|日职|韩K|联赛|杯)/i.test(text) && !/(NBA|CBA|WNBA|NBL|篮球|篮)/i.test(text));
  if (tid === 'other') return !matchCategory('basketball', league, name, stype, hot) && !matchCategory('football', league, name, stype, hot);
  return true;
}

async function fetchText(url, referer) {
  const hd = { 'User-Agent': UA, 'Referer': referer || host + '/', 'Accept': 'text/html,application/json,*/*', 'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8' };
  if (typeof Java !== 'undefined' && Java && Java.req) {
    const r = await Java.req(url, { headers: hd });
    if (typeof r === 'string') return r;
    return String((r && (r.body || r.content || r.data)) || '');
  }
  const r2 = await req(url, { headers: hd });
  return String((r2 && (r2.content || r2.body)) || '');
}

async function fetchHome(force) {
  if (!force && cacheHtml && Date.now() - cacheTime < 60000) return cacheHtml;
  for (let i = 0; i < hosts.length; i++) {
    try {
      const html = await fetchText(hosts[i] + '/', hosts[i] + '/');
      if (html && (/loc_match|lab_team|JRKAN|play\/steam/i).test(html)) {
        host = hosts[i]; cacheHtml = html; cacheTime = Date.now(); return html;
      }
    } catch (e) {}
  }
  return cacheHtml || '';
}

function firstMatch(text, reg) { const m = String(text || '').match(reg); return m ? m[1] : ''; }

function parseList(html, tid) {
  const list = [];
  const reg = /<ul\b[^>]*class=["'][^"']*item[^"']*["'][^>]*>[\s\S]*?<\/ul>/gi;
  let m;
  while ((m = reg.exec(String(html || ''))) !== null) {
    const item = m[0];
    if (!/class=["'][^"']*ok[^"']*me[^"']*["']/i.test(item)) continue;
    const links = [];
    const areg = /<a\b([^>]*class=["'][^"']*ok[^"']*me[^"']*["'][^>]*)>([\s\S]*?)<\/a>/gi;
    let am;
    while ((am = areg.exec(item)) !== null) {
      const attrs = am[1];
      const href = firstMatch(attrs, /href=["']([^"']+)["']/i) || firstMatch(attrs, /data-play=["']([^"']+)["']/i);
      if (!href || href === 'javascript:void(0)') continue;
      const name = stripHtml(am[2]) || ('线路' + (links.length + 1));
      links.push({ name, url: absUrl(href, host) });
    }
    if (!links.length) continue;
    const league = stripHtml(firstMatch(item, /class=["'][^"']*lab_events[^"']*["'][\s\S]*?<span[^>]*class=["']name["'][^>]*>([\s\S]*?)<\/span>/i));
    const time = stripHtml(firstMatch(item, /class=["'][^"']*lab_time[^"']*["'][^>]*>([\s\S]*?)<\/li>/i));
    const home = stripHtml(firstMatch(item, /class=["'][^"']*lab_team_home[^"']*["'][\s\S]*?<strong[^>]*class=["']name["'][^>]*>([\s\S]*?)<\/strong>/i));
    const away = stripHtml(firstMatch(item, /class=["'][^"']*lab_team_away[^"']*["'][\s\S]*?<strong[^>]*class=["']name["'][^>]*>([\s\S]*?)<\/strong>/i));
    const stype = firstMatch(item, /data-stype=["']([^"']+)["']/i);
    const hot = /class=["'][^"']*hot[^"']*["']/i.test(item);
    let name = [time, league, [home, away].filter(Boolean).join(' vs ')].filter(Boolean).join(' ');
    if (!name) name = stripHtml(item).slice(0, 80) || '赛事直播';
    if (!matchCategory(tid, league, name, stype, hot)) continue;
    const pic = absUrl(firstMatch(item, /<img[^>]+src=["']([^"']+)["']/i) || defaultPic, host);
    const payload = { name, pic, links };
    list.push({ vod_id: 'jrs$' + utf8ToBase64Url(JSON.stringify(payload)), vod_name: name, vod_pic: pic, vod_remarks: links.map(x => x.name).slice(0, 3).join('/') || '直播' });
  }
  return list;
}

function getClasses() {
  return [
    { type_id: 'live', type_name: '正在直播' },
    { type_id: 'all', type_name: '全部赛程' },
    { type_id: 'basketball', type_name: '篮球直播' },
    { type_id: 'football', type_name: '足球直播' },
    { type_id: 'hot', type_name: '热门赛事' },
    { type_id: 'other', type_name: '其他赛事' }
  ];
}

async function init(cfg) { if (cfg && cfg.ext && String(cfg.ext).indexOf('http') === 0) host = String(cfg.ext).replace(/\/$/, ''); }
async function home(filter) { return JSON.stringify({ class: getClasses(), filters: {} }); }
async function homeVod() { return await category('live', 1, false, {}); }
async function category(tid, pg, filter, extend) {
  const html = await fetchHome(false);
  const list = parseList(html, tid || 'all');
  return JSON.stringify({ code: 1, msg: '数据列表', page: parseInt(pg) || 1, pagecount: 1, limit: list.length, total: list.length, list });
}
async function detail(id) {
  id = Array.isArray(id) ? id[0] : id;
  let payload = null;
  id = String(id || '');
  if (id.indexOf('jrs$') === 0) payload = safeJson(base64UrlToUtf8(id.slice(4)), null);
  if (!payload && /^https?:\/\//i.test(id)) payload = { name: '赛事直播', pic: defaultPic, links: [{ name: '直播', url: id }] };
  if (!payload) return JSON.stringify({ code: 1, list: [], page: 1, pagecount: 1, total: 0 });
  const playUrl = (payload.links || []).map((x, i) => (x.name || ('线路' + (i + 1))) + '$' + x.url).join('#');
  return JSON.stringify({ code: 1, msg: '数据列表', page: 1, pagecount: 1, limit: 1, total: 1, list: [{ vod_id: id, vod_name: payload.name || '赛事直播', vod_pic: payload.pic || defaultPic, vod_remarks: '直播', vod_content: 'JRKAN 体育赛事直播。部分线路为网页播放器，播放器可嗅探播放。', vod_play_from: 'JRS直播', vod_play_url: playUrl }] });
}
async function search(wd, quick, pg) { return JSON.stringify({ code: 1, msg: '数据列表', page: parseInt(pg) || 1, pagecount: 1, limit: 20, total: 0, list: [] }); }
async function play(flag, id, flags) { return JSON.stringify({ parse: /\.(m3u8|mp4|flv)(\?|$)/i.test(String(id || '')) ? 0 : 1, url: id, header: { 'User-Agent': UA, 'Referer': host + '/' } }); }

async function homeContent(filter) { return safeJson(await home(filter), { class: [], filters: {} }); }
async function homeVideoContent() { return safeJson(await homeVod(), { list: [] }); }
async function categoryContent(tid, pg, filter, extend) { return safeJson(await category(tid, pg, filter, extend || {}), { list: [] }); }
async function detailContent(ids) { return safeJson(await detail(ids), { list: [] }); }
async function searchContent(wd, quick, pg) { return safeJson(await search(wd, quick, pg || 1), { list: [] }); }
async function playerContent(flag, id, flags) { return safeJson(await play(flag, id, flags), { parse: 1, url: id }); }
  return { init, home, homeVod, category, search, detail, play, homeContent, homeVideoContent, categoryContent, detailContent, searchContent, playerContent };
})();


const __sports_src_4 = (function () {


let host = 'https://www.iqzhibo.com';
const dbHost = 'https://www.doubaozhibo.com';
const dbScheduleApi = dbHost + '/api/v1/schedules/public/local';
const dbPlaybackApi = dbHost + '/api/v1/playbacks';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36';

function getHeaders(referer) {
  return {
    'User-Agent': UA,
    'Referer': referer || host + '/',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
  };
}

function getHeaderValue(headers, name) {
  if (!headers) return '';
  const lower = String(name || '').toLowerCase();
  for (const k in headers) {
    if (String(k).toLowerCase() === lower) {
      const v = headers[k];
      return Array.isArray(v) ? String(v[0] || '') : String(v || '');
    }
  }
  return '';
}

function stripHtml(s) {
  return String(s || '')
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, ' ')
    .trim();
}

function cleanText(s) {
  return stripHtml(s).replace(/\s+/g, ' ').trim();
}

function absUrl(url, base) {
  url = String(url || '').trim();
  base = base || host;
  if (!url) return '';
  if (/^https?:\/\//i.test(url)) return url;
  if (url.indexOf('//') === 0) return 'https:' + url;
  if (url.charAt(0) === '/') return base.replace(/\/$/, '') + url;
  return base.replace(/\/$/, '') + '/' + url;
}

function safeJson(text, def) {
  try { return JSON.parse(text || '{}'); } catch (e) { return def || {}; }
}

async function fetchText(url, referer) {
  const hd = getHeaders(referer || host + '/');
  if (typeof Java !== 'undefined' && Java && Java.req) {
    const r = await Java.req(url, { headers: hd });
    if (typeof r === 'string') return r;
    const code = Number((r && (r.statusCode || r.status || r.code)) || 0);
    const loc = getHeaderValue(r && r.headers, 'location');
    if (loc && code >= 300 && code < 400) return await fetchText(absUrl(loc, url.indexOf(dbHost) === 0 ? dbHost : host), url);
    return String((r && (r.body || r.content || r.data)) || '');
  }
  const r2 = await req(url, { headers: hd });
  if (typeof r2 === 'string') return r2;
  const code2 = Number((r2 && (r2.statusCode || r2.status || r2.code)) || 0);
  const loc2 = getHeaderValue(r2 && r2.headers, 'location');
  if (loc2 && code2 >= 300 && code2 < 400) return await fetchText(absUrl(loc2, url.indexOf(dbHost) === 0 ? dbHost : host), url);
  return String((r2 && (r2.content || r2.body || r2.data)) || '');
}

function getClasses() {
  return [
    { type_id: 'zuqiu', type_name: '足球直播' },
    { type_id: 'lanqiu', type_name: '篮球直播' },
    { type_id: 'sssc', type_name: '实时赛程' },
    { type_id: 'huifang', type_name: '赛事回放' },
    { type_id: 'fifa', type_name: '世界杯' },
    { type_id: 'zhongchao', type_name: '中超' },
    { type_id: 'yingchao', type_name: '英超' },
    { type_id: 'xijia', type_name: '西甲' },
    { type_id: 'dejia', type_name: '德甲' },
    { type_id: 'yijia', type_name: '意甲' },
    { type_id: 'fajia', type_name: '法甲' }
  ];
}

function parseIqList(html) {
  html = String(html || '');
  const list = [];
  const reg = /<li>\s*<div class=["']liveinfo["'][\s\S]*?<\/li>/gi;
  let m;
  while ((m = reg.exec(html)) !== null) {
    const item = m[0];
    const title = cleanText((item.match(/class=["']title["'][^>]*>([\s\S]*?)<\/div>/i) || [])[1]);
    const homeBlock = (item.match(/class=["']team-zhu["'][^>]*>([\s\S]*?)<\/div>/i) || [])[1] || '';
    const awayBlock = (item.match(/class=["']team-ke["'][^>]*>([\s\S]*?)<\/div>/i) || [])[1] || '';
    const home = cleanText(homeBlock.replace(/<img[\s\S]*$/i, ''));
    const away = cleanText(awayBlock.replace(/^[\s\S]*?<img[^>]*>/i, ''));
    const hrefMatch = item.match(/<div class=["']livesource["'][\s\S]*?<a[^>]+href=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/i);
    if (!hrefMatch) continue;
    const imgMatch = item.match(/<img[^>]+src=["']([^"']+)["']/i);
    const teams = [home, away].filter(Boolean).join(' vs ');
    const name = [title, teams].filter(Boolean).join(' ');
    list.push({
      vod_id: absUrl(hrefMatch[1], host),
      vod_name: name || teams || title || '赛事直播',
      vod_pic: absUrl(imgMatch ? imgMatch[1] : '/logo.png', host),
      vod_remarks: cleanText(hrefMatch[2]) || '高清'
    });
  }
  return list;
}

function matchCategory(tid, league, name, dataType) {
  tid = String(tid || '');
  league = cleanText(league);
  name = cleanText(name);
  dataType = String(dataType || '');
  const text = league + ' ' + name;
  if (!tid || tid === 'sssc' || tid === 'huifang') return true;
  if (tid === 'zuqiu') return dataType === 'football' || (/(足|超|甲|乙|冠|欧联|日职|韩K|世界杯|世俱|足球|杯)/i.test(text) && !/(篮|NBA|CBA|WNBA|NBL|篮球)/i.test(text));
  if (tid === 'lanqiu') return dataType === 'basketball' || /(篮|NBA|CBA|WNBA|NBL|篮球)/i.test(text);
  const rules = {
    fifa: /(世界杯|世俱杯|世预赛|国际足联|FIFA)/i,
    zhongchao: /(中超|足协杯|中国超级联赛)/i,
    yingchao: /(英超|英格兰超级联赛)/i,
    xijia: /(西甲|西班牙甲级联赛)/i,
    dejia: /(德甲|德国甲级联赛)/i,
    yijia: /(意甲|意大利甲级联赛)/i,
    fajia: /(法甲|法国甲级联赛)/i
  };
  return rules[tid] ? rules[tid].test(text) : true;
}

function formatTimeText(matchTime) {
  const d = new Date(matchTime);
  if (!matchTime || isNaN(d.getTime())) return '';
  const pad = function (n) { return String(n).padStart(2, '0'); };
  return pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}

async function fetchJson(url, referer) {
  const text = await fetchText(url, referer || dbHost + '/');
  try { return JSON.parse(text || '{}'); } catch (e) { return {}; }
}

function parseApiSchedule(json, tid) {
  const days = json && json.data && Array.isArray(json.data.days) ? json.data.days : [];
  const list = [];
  for (let i = 0; i < days.length; i++) {
    const rows = Array.isArray(days[i].live) ? days[i].live : [];
    for (let j = 0; j < rows.length; j++) {
      const item = rows[j];
      const signals = Array.isArray(item.signals) ? item.signals : [];
      if (!signals.length) continue;
      const name = [formatTimeText(item.matchTime), cleanText(item.league), cleanText(item.teamA) + ' vs ' + cleanText(item.teamB)].filter(Boolean).join(' ');
      if (!matchCategory(tid, item.league, name, item.dataType)) continue;
      const links = signals.map(function (s, idx) {
        return { name: cleanText(s.name || s.label) || ('信号' + (idx + 1)), url: dbHost + '/play/' + s.playId + '?device=pc_web' };
      });
      list.push({
        vod_id: 'db$' + encodeURIComponent(JSON.stringify({ name: name, links: links })),
        vod_name: name,
        vod_pic: item.teamAImage || item.teamBImage || host + '/logo.png',
        vod_remarks: links.map(function (x) { return x.name; }).join('/') || '直播'
      });
    }
  }
  return list;
}

function parsePlaybackList(json, tid) {
  const rows = json && json.data && Array.isArray(json.data.list) ? json.data.list : [];
  const list = [];
  for (let i = 0; i < rows.length; i++) {
    const s = rows[i].schedule || {};
    const p = rows[i].playback || {};
    const lines = Array.isArray(p.lines) ? p.lines : [];
    if (!lines.length) continue;
    const fullName = cleanText(p.title) || [formatTimeText(s.matchTime), cleanText(s.league), cleanText(s.teamA) + ' vs ' + cleanText(s.teamB), '回放'].filter(Boolean).join(' ');
    if (!matchCategory(tid, s.league, fullName, s.dataType)) continue;
    const shortName = (cleanText(s.teamA) + ' vs ' + cleanText(s.teamB)).replace(/^\s*vs\s*|\s*vs\s*$/g, '') || fullName.replace(/^\d{4}年\d{1,2}月\d{1,2}日\s*/, '').replace(/\s*赛事回放$/, '');
    const remarkPrefix = [formatTimeText(s.matchTime), cleanText(s.league)].filter(Boolean).join(' ');
    const links = lines.map(function (line, idx) {
      return { name: cleanText(line.title) || ('回放' + (idx + 1)), url: absUrl(line.proxyUrl, dbHost) };
    });
    list.push({
      vod_id: 'db$' + encodeURIComponent(JSON.stringify({ name: fullName, links: links })),
      vod_name: shortName,
      vod_pic: s.teamAImage || s.teamBImage || host + '/logo.png',
      vod_remarks: [remarkPrefix, links.map(function (x) { return x.name; }).join('/')].filter(Boolean).join(' · ') || '回放'
    });
  }
  return list;
}

function parseProxySchedule(html, tid) {
  html = String(html || '');
  const list = [];
  const reg = /<article[^>]*class=["'][^"']*px-3 py-3 sm:px-4[^"']*["'][^>]*>[\s\S]*?<\/article>/gi;
  let m;
  while ((m = reg.exec(html)) !== null) {
    const item = m[0];
    const ps = [];
    const pReg = /<p[^>]*>([\s\S]*?)<\/p>/gi;
    let pm;
    while ((pm = pReg.exec(item)) !== null) ps.push(cleanText(pm[1]));
    const time = ps[0] || '';
    const league = ps[1] || '';

    const teams = [];
    const spanReg = /<span[^>]*class=["'][^"']*truncate[^"']*["'][^>]*>([\s\S]*?)<\/span>/gi;
    let sm;
    while ((sm = spanReg.exec(item)) !== null) {
      const t = cleanText(sm[1]);
      if (t && !/^信号|高清|返回/.test(t) && teams.indexOf(t) < 0) teams.push(t);
    }
    if (teams.length < 2) continue;
    const name = [time, league, teams[0] + ' vs ' + teams[1]].filter(Boolean).join(' ');
    if (!matchCategory(tid, league, name)) continue;

    const links = [];
    const aReg = /<a[^>]+href=["']([^"']+)["'][^>]*class=["'][^"']*home-signal-link[^"']*["'][^>]*>([\s\S]*?)<\/a>/gi;
    let am;
    while ((am = aReg.exec(item)) !== null) {
      const title = (am[0].match(/title=["']([^"']+)["']/i) || [])[1] || cleanText(am[2]) || ('信号' + (links.length + 1));
      links.push({ name: title, url: absUrl(am[1], dbHost) });
    }
    if (!links.length) continue;
    const img = (item.match(/<img[^>]+src=["']([^"']+)["']/i) || [])[1] || '/logo.png';
    list.push({
      vod_id: 'db$' + encodeURIComponent(JSON.stringify({ name: name, links: links })),
      vod_name: name,
      vod_pic: absUrl(img, dbHost),
      vod_remarks: links.map(function (x) { return x.name; }).join('/') || '直播'
    });
  }
  return list;
}

async function init(cfg) {
  if (cfg && cfg.ext && String(cfg.ext).indexOf('http') === 0) host = String(cfg.ext).trim().replace(/\/$/, '');
}

async function home(filter) {
  return JSON.stringify({ class: getClasses(), filters: {} });
}

async function homeVod() {
  return await category('zuqiu', 1, false, {});
}

async function category(tid, pg, filter, extend) {
  tid = String((extend && extend.cateId) || tid || 'zuqiu');
  pg = parseInt(pg) || 1;
  let list = [];
  try {
    if (tid === 'huifang') {
      list = parsePlaybackList(await fetchJson(dbPlaybackApi + '?page=' + pg + '&pageSize=20&dataType=all', dbHost + '/'), tid);
    } else {
      list = parseApiSchedule(await fetchJson(dbScheduleApi, dbHost + '/'), tid);
      if (!list.length && tid !== 'lanqiu') {
        list = parseProxySchedule(await fetchText(host + '/proxy.php', host + '/sssc/'), tid);
      }
    }
  } catch (e) {
    list = [];
  }
  return JSON.stringify({ code: 1, msg: '数据列表', page: pg, pagecount: list.length >= 20 ? pg + 1 : 1, limit: 50, total: list.length, list: list });
}

function parseNuxtProxy(html) {
  html = String(html || '');
  const hls = html.match(/(?:\\u002F|\/)hls(?:\\u002F|\/)[A-Za-z0-9._-]+\.m3u8/i);
  if (hls) return absUrl(hls[0].replace(/\\u002F/g, '/'), dbHost);
  const m = html.match(/"proxyUrl"\s*:\s*"((?:\\.|[^"\\])*)"/);
  if (m) {
    try { return absUrl(JSON.parse('"' + m[1] + '"'), dbHost); } catch (e) { return absUrl(m[1].replace(/\\u002F/g, '/'), dbHost); }
  }
  const iframe = html.match(/https?:\/\/www\.kanqiuge\.com\/embed\/play\/[A-Za-z0-9._-]+/i);
  if (iframe) return iframe[0];
  return '';
}

async function resolvePlayUrl(playUrl) {
  playUrl = String(playUrl || '');
  if (/\.(m3u8|flv|mp4)(\?|$)/i.test(playUrl)) return playUrl;
  try {
    const html = await fetchText(playUrl, host + '/sssc/');
    return parseNuxtProxy(html) || playUrl;
  } catch (e) {
    return playUrl;
  }
}

async function detail(id) {
  id = Array.isArray(id) ? id[0] : id;
  id = String(id || '');
  if (id.indexOf('db$') === 0) {
    let data = { name: '实时赛程', links: [] };
    try { data = JSON.parse(decodeURIComponent(id.slice(3))); } catch (e) {}
    const playUrls = (data.links || []).map(function (x) { return (x.name || '线路') + '$' + x.url; }).join('#');
    return JSON.stringify({
      code: 1,
      msg: '数据列表',
      page: 1,
      pagecount: 1,
      limit: 1,
      total: 1,
      list: [{
        vod_id: id,
        vod_name: data.name || '实时赛程',
        vod_pic: host + '/logo.png',
        vod_remarks: '直播',
        vod_play_from: '爱球直播',
        vod_play_url: playUrls,
        vod_content: '爱球直播实时赛程，播放时解析豆包直播信号。'
      }]
    });
  }

  let name = '赛事直播';
  let time = '';
  let playUrls = '';
  try {
    const html = await fetchText(id, host + '/');
    name = cleanText((html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i) || [])[1]) || name;
    time = cleanText((html.match(/<div class=["']match-header["'][\s\S]*?<p[^>]*>([\s\S]*?)<\/p>/i) || [])[1]);
    const arr = [];
    const aReg = /<div class=["']gohome["'][\s\S]*?<\/div>/i;
    const block = (html.match(aReg) || [])[0] || '';
    const linkReg = /<a[^>]+href=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi;
    let lm;
    while ((lm = linkReg.exec(block)) !== null) {
      const text = cleanText(lm[2]) || ('信号' + (arr.length + 1));
      if (/赛程|返回|首页/.test(text)) continue;
      const href = lm[1];
      arr.push(text + '$' + (href === '/sssc/' || href.indexOf('/sssc/') >= 0 ? host + '/proxy.php' : absUrl(href, host)));
    }
    if (!arr.length) arr.push('赛程$' + host + '/proxy.php');
    playUrls = arr.join('#');
  } catch (e) {
    playUrls = '赛程$' + host + '/proxy.php';
  }

  return JSON.stringify({
    code: 1,
    msg: '数据列表',
    page: 1,
    pagecount: 1,
    limit: 1,
    total: 1,
    list: [{
      vod_id: id,
      vod_name: name,
      vod_pic: host + '/logo.png',
      vod_remarks: time,
      vod_play_from: '爱球直播',
      vod_play_url: playUrls,
      vod_content: time || '爱球直播赛事导航'
    }]
  });
}

async function search(wd, quick, pg) {
  pg = parseInt(pg) || 1;
  let list = [];
  try {
    const html = await fetchText(host + '/search.html?keywords=' + encodeURIComponent(wd || '') + '&method=1', host + '/');
    list = parseIqList(html);
  } catch (e) {
    list = [];
  }
  return JSON.stringify({ code: 1, msg: '数据列表', page: pg, pagecount: 1, limit: 20, total: list.length, list: list });
}

async function play(flag, id, flags) {
  const url = await resolvePlayUrl(id);
  const direct = /\.(m3u8|flv|mp4)(\?|$)/i.test(String(url || ''));
  return JSON.stringify({
    parse: direct ? 0 : 1,
    url: url,
    header: {
      'User-Agent': UA,
      'Referer': String(url || '').indexOf('doubaozhibo.com') >= 0 ? dbHost + '/' : host + '/'
    }
  });
}

async function homeContent(filter) { return safeJson(await home(filter), { class: [], filters: {} }); }
async function homeVideoContent() { return safeJson(await homeVod(), { list: [] }); }
async function categoryContent(tid, pg, filter, extend) { return safeJson(await category(tid, pg, filter, extend || {}), { list: [] }); }
async function detailContent(ids) { return safeJson(await detail(ids), { list: [] }); }
async function searchContent(wd, quick, pg) { return safeJson(await search(wd, quick, pg || 1), { list: [] }); }
async function playerContent(flag, id, flags) { return safeJson(await play(flag, id, flags), { parse: 1, url: id }); }
  return { init, home, homeVod, category, search, detail, play, homeContent, homeVideoContent, categoryContent, detailContent, searchContent, playerContent };
})();



const __sports_src_5 = (function () {


const API_BASE = 'https://aapi2.xbncs.com/api';
const HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
  'Accept': 'application/json, text/plain, */*',
  'Referer': 'https://aapi2.xbncs.com/'
};
const PAGE_SIZE = 30;

function safeString(v) { if (v === null || v === undefined || v === 'null') return ''; return String(v); }
function safeJson(text, def) { if (text && typeof text === 'object') return text; try { return JSON.parse(text || '{}'); } catch (e) { return def || {}; } }

async function requestJson(url) {
  if (typeof Java !== 'undefined' && Java && Java.req) {
    const r = await Java.req(url, { headers: HEADERS });
    if (typeof r === 'string') return safeJson(r, {});
    return safeJson((r && (r.body || r.content || r.data)) || '{}', {});
  }
  const r2 = await req(url, { headers: HEADERS });
  return safeJson((r2 && (r2.content || r2.body || r2.data)) || '{}', {});
}

function getClasses() { return [{ type_id: '-1', type_name: '全部' }, { type_id: '1', type_name: '足球' }, { type_id: '2', type_name: '篮球' }]; }
async function init(cfg) {}
async function home(filter) { return JSON.stringify({ class: getClasses(), filters: {} }); }
async function homeVod() { return await category('-1', 1, false, {}); }

async function category(tid, pg, filter, extend) {
  const page = Math.max(parseInt(pg || '1', 10) || 1, 1);
  const navId = tid === '-1' || tid === undefined || tid === null ? '' : String(tid);
  const url = API_BASE + '/room/page?roomType=&navId=' + encodeURIComponent(navId) + '&roomId=&word=&page=' + page + '&pageSize=' + PAGE_SIZE + '&channelId=3&platform=1';
  const list = [];
  try {
    const json = await requestJson(url);
    const rows = json && json.data && Array.isArray(json.data.list) ? json.data.list : [];
    for (let i = 0; i < rows.length; i++) {
      const item = rows[i];
      const roomId = safeString(item.roomId);
      if (!roomId) continue;
      list.push({
        vod_id: roomId,
        vod_name: safeString(item.title) || safeString(item.nickName) || ('房间 ' + roomId),
        vod_pic: safeString(item.cover),
        vod_remarks: safeString(item.navName) || safeString(item.statusName) || safeString(item.liveStatus) || '直播'
      });
    }
  } catch (e) {}
  return JSON.stringify({ code: 1, msg: '数据列表', page: page, pagecount: list.length >= PAGE_SIZE ? page + 1 : page, limit: PAGE_SIZE, total: list.length, list: list });
}

async function detail(id) {
  id = Array.isArray(id) ? id[0] : id;
  const roomId = safeString(id).trim();
  if (!roomId) return JSON.stringify({ code: 1, list: [], page: 1, pagecount: 1, total: 0 });
  const vod = { vod_id: roomId, vod_name: '房间 ' + roomId, vod_pic: '', vod_content: '体育直播', type_name: '', vod_play_from: '球通', vod_play_url: '' };
  try {
    const json = await requestJson(API_BASE + '/room/info?roomId=' + encodeURIComponent(roomId) + '&channelId=3&platform=1');
    const data = json && json.data ? json.data : null;
    if (data) {
      vod.vod_name = safeString(data.title) || vod.vod_name;
      vod.vod_pic = safeString(data.cover);
      vod.vod_content = safeString(data.description) || safeString(data.notice) || '体育直播';
      vod.type_name = safeString(data.nickName) || safeString(data.navName);
      const playUrls = [];
      const pushUrl = safeString(data.pushUrl);
      const pullUrl = safeString(data.pullUrl);
      if (pushUrl) playUrls.push('flv$' + pushUrl);
      if (pullUrl) playUrls.push('m3u8$' + pullUrl);
      vod.vod_play_url = playUrls.join('#');
    }
  } catch (e) {}
  if (!vod.vod_play_url) vod.vod_play_url = '暂无播放$' + roomId;
  return JSON.stringify({ code: 1, msg: '数据列表', page: 1, pagecount: 1, limit: 1, total: 1, list: [vod] });
}

async function search(wd, quick, pg) { return JSON.stringify({ code: 1, msg: '数据列表', page: parseInt(pg) || 1, pagecount: 1, limit: 0, total: 0, list: [] }); }
async function play(flag, id, flags) { id = safeString(id).replace(/\*\*\*/g, '#'); return JSON.stringify({ parse: /^https?:\/\//i.test(id) ? 0 : 1, jx: 0, url: /^https?:\/\//i.test(id) ? id : '', msg: /^https?:\/\//i.test(id) ? '' : '暂无播放地址', header: HEADERS }); }
async function homeContent(filter) { return safeJson(await home(filter), { class: [], filters: {} }); }
async function homeVideoContent() { return safeJson(await homeVod(), { list: [] }); }
async function categoryContent(tid, pg, filter, extend) { return safeJson(await category(tid, pg, filter, extend || {}), { list: [] }); }
async function detailContent(ids) { return safeJson(await detail(ids), { list: [] }); }
async function searchContent(wd, quick, pg) { return safeJson(await search(wd, quick, pg || 1), { list: [] }); }
async function playerContent(flag, id, flags) { return safeJson(await play(flag, id, flags), { parse: 1, url: id }); }
  return { init, home, homeVod, category, search, detail, play, homeContent, homeVideoContent, categoryContent, detailContent, searchContent, playerContent };
})();

const SOURCES = [
  { id: 's0', name: '88看球', api: __sports_src_0 },
  { id: 's1', name: '咖啡直播', api: __sports_src_1 },
  { id: 's2', name: '919体育', api: __sports_src_2 },
  { id: 's3', name: 'JRS直播', api: __sports_src_3 },
  { id: 's4', name: '爱球直播', api: __sports_src_4 },
  { id: 's5', name: '球通体育', api: __sports_src_5 }
];

const SOURCE_CATS = {
  s0: [
    { n: '正在直播', v: 'live' },
    { n: '全部直播', v: '0' },
    { n: '篮球直播', v: '1' },
    { n: '足球直播', v: '8' },
    { n: '其他直播', v: '21' }
  ],
  s1: [
    { n: '全部直播', v: 'all' },
    { n: '热门直播', v: 'hot' },
    { n: 'NBA', v: 'nba' },
    { n: '足球直播', v: '1' },
    { n: '篮球直播', v: '2' },
    { n: '网球直播', v: '3' },
    { n: '台球直播', v: '19' },
    { n: '赛程列表', v: 'schedule' },
    { n: '录像', v: 'recordings' }
  ],
  s2: [
    { n: '全部', v: '1' },
    { n: '足球', v: '2' },
    { n: '篮球', v: '3' }
  ],
  s3: [
    { n: '正在直播', v: 'live' },
    { n: '全部赛程', v: 'all' },
    { n: '篮球直播', v: 'basketball' },
    { n: '足球直播', v: 'football' },
    { n: '热门赛事', v: 'hot' },
    { n: '其他赛事', v: 'other' }
  ],
  s4: [
    { n: '足球直播', v: 'zuqiu' },
    { n: '篮球直播', v: 'lanqiu' },
    { n: '实时赛程', v: 'sssc' },
    { n: '赛事回放', v: 'huifang' },
    { n: '世界杯', v: 'fifa' },
    { n: '中超', v: 'zhongchao' },
    { n: '英超', v: 'yingchao' },
    { n: '西甲', v: 'xijia' },
    { n: '德甲', v: 'dejia' },
    { n: '意甲', v: 'yijia' },
    { n: '法甲', v: 'fajia' }
  ],
  s5: [
    { n: '全部', v: '-1' },
    { n: '足球', v: '1' },
    { n: '篮球', v: '2' }
  ]
};

function __safeJson(text, def) {
  if (text && typeof text === 'object') return text;
  try { return JSON.parse(text || '{}'); } catch (e) { return def || {}; }
}

function __packId(srcId, id) {
  return srcId + '@@@' + String(id || '');
}

function __splitId(id) {
  const s = String(Array.isArray(id) ? id[0] : (id || ''));
  const p = s.indexOf('@@@');
  if (p < 0) return { srcId: '', raw: s };
  return { srcId: s.slice(0, p), raw: s.slice(p + 3) };
}

function __srcById(srcId) {
  for (let i = 0; i < SOURCES.length; i++) if (SOURCES[i].id === srcId) return SOURCES[i];
  return null;
}

function __firstCat(srcId) {
  const arr = SOURCE_CATS[srcId] || [];
  return arr.length ? arr[0].v : 'home';
}

function __classes() {
  const arr = [];
  for (let i = 0; i < SOURCES.length; i++) {
    arr.push({ type_id: SOURCES[i].id, type_name: SOURCES[i].name });
  }
  return arr;
}

function __filters() {
  const filters = {};
  for (let i = 0; i < SOURCES.length; i++) {
    const src = SOURCES[i];
    const values = SOURCE_CATS[src.id] || [];
    filters[src.id] = [{ key: 'cat', name: '分类', value: values }];
  }
  return filters;
}

function __pickExtendCat(extend) {
  extend = extend || {};
  return String(extend.cat || extend.type || extend.class || extend.cate || '');
}

function __prefixList(list, src) {
  list = Array.isArray(list) ? list : [];
  const out = [];
  for (let i = 0; i < list.length; i++) {
    const it = list[i] || {};
    const id = String(it.vod_id || '');
    if (!id) continue;
    out.push(Object.assign({}, it, {
      vod_id: __packId(src.id, id),
      vod_name: String(it.vod_name || ''),
      vod_remarks: it.vod_remarks || src.name
    }));
  }
  return out;
}

async function __callList(src, subTid, pg, filter, extend) {
  try {
    subTid = subTid || __firstCat(src.id);
    const obj = __safeJson(await src.api.category(subTid, pg || 1, filter || false, extend || {}), {});
    return __prefixList(obj.list || [], src);
  } catch (e) {
    return [];
  }
}

async function init(cfg) {
  for (let i = 0; i < SOURCES.length; i++) {
    try { if (SOURCES[i].api.init) await SOURCES[i].api.init(cfg || {}); } catch (e) {}
  }
}

async function home(filter) {
  return JSON.stringify({ class: __classes(), filters: __filters() });
}

async function homeVod() {
  // 首页只加载第一个源的默认二级分类，避免一进源就把所有体育站数据全量请求一遍。
  const src = SOURCES[0];
  const list = await __callList(src, __firstCat(src.id), 1, false, {});
  return JSON.stringify({ code: 1, msg: '数据列表', page: 1, pagecount: 1, limit: list.length, total: list.length, list });
}

async function category(tid, pg, filter, extend) {
  tid = String(tid || SOURCES[0].id);
  extend = extend || {};
  const src = __srcById(tid) || SOURCES[0];
  const subTid = __pickExtendCat(extend) || __firstCat(src.id);
  const list = await __callList(src, subTid, pg || 1, filter, extend);
  return JSON.stringify({ code: 1, msg: '数据列表', page: parseInt(pg) || 1, pagecount: 1, limit: list.length, total: list.length, list });
}

async function detail(id) {
  const sp = __splitId(id);
  const src = __srcById(sp.srcId);
  if (!src) return JSON.stringify({ code: 1, list: [], page: 1, pagecount: 1, total: 0 });
  try {
    const obj = __safeJson(await src.api.detail(sp.raw), {});
    const list = Array.isArray(obj.list) ? obj.list : [];
    for (let i = 0; i < list.length; i++) {
      if (list[i]) list[i].vod_id = __packId(src.id, list[i].vod_id || sp.raw);
    }
    obj.list = list;
    return JSON.stringify(obj);
  } catch (e) {
    return JSON.stringify({ code: 1, list: [], page: 1, pagecount: 1, total: 0, msg: String(e && e.message || e) });
  }
}

async function search(wd, quick, pg) {
  const list = [];
  for (let i = 0; i < SOURCES.length; i++) {
    try {
      const obj = __safeJson(await SOURCES[i].api.search(wd, quick, pg || 1), {});
      const part = __prefixList(obj.list || [], SOURCES[i]);
      for (let j = 0; j < part.length; j++) list.push(part[j]);
    } catch (e) {}
  }
  return JSON.stringify({ code: 1, msg: '数据列表', page: parseInt(pg) || 1, pagecount: 1, limit: list.length, total: list.length, list });
}

async function play(flag, id, flags) {
  return JSON.stringify(await playerContent(flag, id, flags));
}

async function playerContent(flag, id, flags) {
  const sp = __splitId(id);
  const src = __srcById(sp.srcId);
  if (!src) return { parse: 1, url: sp.raw || id };
  try {
    if (src.api.playerContent) return await src.api.playerContent(flag, sp.raw, flags);
    return __safeJson(await src.api.play(flag, sp.raw, flags), { parse: 1, url: sp.raw });
  } catch (e) {
    return { parse: 1, url: sp.raw };
  }
}

async function homeContent(filter) { return __safeJson(await home(filter), { class: [], filters: {} }); }
async function homeVideoContent() { return __safeJson(await homeVod(), { list: [] }); }
async function categoryContent(tid, pg, filter, extend) { return __safeJson(await category(tid, pg, filter, extend || {}), { list: [] }); }
async function detailContent(ids) { return __safeJson(await detail(ids), { list: [] }); }
async function searchContent(wd, quick, pg) { return __safeJson(await search(wd, quick, pg || 1), { list: [] }); }

export function __jsEvalReturn() {
  return { init, home, homeVod, category, search, detail, play, homeContent, homeVideoContent, categoryContent, detailContent, searchContent, playerContent };
}
