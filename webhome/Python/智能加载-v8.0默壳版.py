# -*- coding: utf-8 -*-
# @tvbox-role manager
# @version v8.0
# @release-format plain-release-v1
# @dual-app-loader WebHTV,OK影视



import base64
import gzip
import concurrent.futures
import copy
import hashlib
import json
import os
import re
import shutil
import socket
import threading
import time
import urllib.parse
import urllib.error
import urllib.request
import zipfile

from base.spider import Spider as BaseSpider


def _detect_storage_root():
    candidates = []
    external = str(os.environ.get("EXTERNAL_STORAGE", "")).strip()
    if external:
        candidates.append(external)
    candidates.extend(("/sdcard", "/storage/emulated/0", os.path.expanduser("~/storage/shared")))
    seen = set()
    for candidate in candidates:
        path = os.path.abspath(os.path.expanduser(candidate))
        real = os.path.realpath(path)
        if real in seen:
            continue
        seen.add(real)
        if os.path.isdir(path):
            return real
    return os.path.abspath(external or "/sdcard")


def _detect_local_base(storage_root):
    candidates = []
    configured = str(os.environ.get("TVBOX_HOME", "")).strip()
    if configured:
        candidates.append(configured)
    candidates.extend(
        (
            os.path.join(storage_root, "tvbox"),
            os.path.join(storage_root, "TVBox"),
        )
    )
    for candidate in candidates:
        path = os.path.realpath(os.path.abspath(os.path.expanduser(candidate)))
        if os.path.isdir(path):
            return path
    return os.path.realpath(os.path.join(storage_root, "tvbox"))


def _detect_child_dir(base, *names):
    if os.path.isdir(base):
        try:
            entries = {
                name.lower(): name
                for name in os.listdir(base)
                if os.path.isdir(os.path.join(base, name))
            }
            for name in names:
                actual = entries.get(name.lower())
                if actual:
                    return os.path.join(base, actual)
        except Exception:
            pass
    return os.path.join(base, names[0])


DETECTED_STORAGE_ROOT = _detect_storage_root()
DETECTED_LOCAL_BASE = _detect_local_base(DETECTED_STORAGE_ROOT)

# 进程级自动补扫冷却，防止“补扫 -> 重载 -> 重建实例 -> 再补扫”循环。
_AUTO_SCAN_STATE = {"last": 0.0}
_MANUAL_SCAN_LOCK = threading.Lock()
_MANUAL_SCAN_STATE = {}


class RegistryChangedError(RuntimeError):
    pass


class SiteTestCancelled(RuntimeError):
    pass




class ReleaseAuthorizationError(RuntimeError):
    pass


class PackageServiceRequestError(ValueError):
    def __init__(self, message, status=0, code="", retry_after=0):
        super().__init__(message)
        self.status = int(status or 0)
        self.code = str(code or "").strip()
        self.retry_after = max(0, int(retry_after or 0))


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _StandaloneProgressHandle(object):
    """独立进度对话框句柄（横向进度条 + 消息文本）。

    供网络同步/测试连接等没有「确认-进度面板」的等待操作使用；所有控件
    操作都 post 到 UI 线程执行。owner 为空时是静默空句柄：无 Android
    环境（如纯 Python 测试）下 update/finish/dismiss 全部安全空转。
    """

    MIN_INTERVAL = 0.12

    def __init__(self, owner, dialog, bar, message_view, handler):
        self._owner = owner
        self._dialog = dialog
        self._bar = bar
        self._message = message_view
        self._handler = handler
        self._closed = False
        self._last_ts = 0.0

    @classmethod
    def null(cls):
        return cls(None, None, None, None, None)

    def _alive(self):
        return (
            self._owner is not None
            and not self._closed
            and not self._owner._destroyed
        )

    def _post(self, fn, allow_closed=False):
        owner = self._owner
        if owner is None or (self._closed and not allow_closed):
            return
        try:
            from java import dynamic_proxy, jclass

            runnable_class = jclass("java.lang.Runnable")
            with owner._ProxyCreationLock(owner):

                class ProgressRunnable(dynamic_proxy(runnable_class)):
                    def __init__(self_inner):
                        super(ProgressRunnable, self_inner).__init__()
                        self_inner._proxy_id = owner._retain_proxy(self_inner)

                    def run(self_inner):
                        try:
                            if (
                                not self._closed or allow_closed
                            ) and not owner._destroyed:
                                fn()
                        finally:
                            owner._release_proxy(self_inner._proxy_id)

                runner = ProgressRunnable()
            owner._dialog_refs.append(runner)
            self._handler.post(runner)
        except Exception:
            try:
                fn()
            except Exception:
                pass

    def update(
        self,
        message=None,
        done=None,
        total=None,
        indeterminate=None,
        force=False,
    ):
        if not self._alive():
            return
        now = time.monotonic()
        if not force and now - self._last_ts < self.MIN_INTERVAL:
            return
        self._last_ts = now

        def _render():
            try:
                if message is not None:
                    self._message.setText(str(message))
                if total is not None and int(total) > 0:
                    self._bar.setIndeterminate(False)
                    self._bar.setMax(int(total))
                    value = int(done or 0)
                    if value < 0:
                        value = 0
                    if value > int(total):
                        value = int(total)
                    self._bar.setProgress(value)
                elif indeterminate:
                    self._bar.setIndeterminate(True)
            except Exception:
                pass

        self._post(_render)

    def finish(self, message, ok=True):
        if not self._alive():
            return
        prefix = "✅ 完成：" if ok else "❌ 失败："
        self.update(
            prefix + str(message or ""),
            done=100 if ok else None,
            total=100 if ok else None,
            indeterminate=False if not ok else None,
            force=True,
        )
        self._post(self._show_close_button)

    def _show_close_button(self):
        owner = self._owner
        try:
            from java import dynamic_proxy, jclass

            click_listener = jclass(
                "android.content.DialogInterface$OnClickListener"
            )
            with owner._ProxyCreationLock(owner):

                class CloseListener(dynamic_proxy(click_listener)):
                    def onClick(self_inner, dialog, which):
                        self.dismiss()

                listener = CloseListener()
            owner._dialog_refs.append(listener)
            try:
                self._dialog.setButton(-1, "确定", listener)
            except Exception:
                # 按钮已在创建时存在，退化为仅改文案。
                self._dialog.getButton(-1).setText("确定")
        except Exception:
            pass

    def dismiss(self):
        if self._closed:
            return
        self._closed = True

        def _do_dismiss():
            try:
                self._dialog.dismiss()
            except Exception:
                pass

        self._post(_do_dismiss, allow_closed=True)


# === UI_ICONS BEGIN (auto-generated, do not edit by hand) ===
_UI_ICONS = {
    'classify': 'data:image/png;base64,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',
    'download': 'data:image/png;base64,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',
    'folder': 'data:image/png;base64,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',
    'reset': 'data:image/png;base64,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',
    'retest': 'data:image/png;base64,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',
    'scan': 'data:image/png;base64,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',
    'status': 'data:image/png;base64,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',
    'switches': 'data:image/png;base64,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',
    'test': 'data:image/png;base64,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',
    'toggle_off': 'data:image/png;base64,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',
    'toggle_on': 'data:image/png;base64,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',
    'trash': 'data:image/png;base64,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',
    'types': 'data:image/png;base64,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',
    'undo': 'data:image/png;base64,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',
}
# === UI_ICONS END ===


class Spider(BaseSpider):
    # ==========================================================================
    # 配置区
    # ==========================================================================
    SCAN_ROOTS = [
        {"path": _detect_child_dir(DETECTED_LOCAL_BASE, "py", "python"), "type": "PY", "extensions": [".py"]},
        {"path": _detect_child_dir(DETECTED_LOCAL_BASE, "js", "javascript"), "type": "JS", "extensions": [".js", ".json"]},
        {"path": _detect_child_dir(DETECTED_LOCAL_BASE, "csp"), "type": "CSP", "extensions": [".json"]},
        # 已按用户要求移除 XBPQ 扫描根，仅保留 csp 作为 JAR/CSP 站点源目录。
        {"path": _detect_child_dir(DETECTED_LOCAL_BASE, "html"), "type": "HTML", "extensions": [".html"]},
        # 独立本地直播目录（直播文件 / 直播 / lives / live），复用 CSP 类型以命中整包 JSON 解析。
        {"path": _detect_child_dir(DETECTED_LOCAL_BASE, "直播文件", "直播", "lives", "live"), "type": "CSP", "extensions": [".json"]},
    ]

    # WebHTV 原生站点注入注册表。
    REGISTRY_PATH = os.path.join(DETECTED_STORAGE_ROOT, "TV", "CustomCsp", "registry.json")
    OUTPUT_PATH = REGISTRY_PATH
    STORAGE_ROOT = DETECTED_STORAGE_ROOT
    LOCAL_BASE_DIR = DETECTED_LOCAL_BASE
    VERSION = "v8.0"
    # 发布时由 CF 后台注入；明文开发版本留空，不访问真实授权服务。
    AUTHORIZATION_URL = "https://jwf.gtu.qzz.io/jwf/api/authorize"
    AUTHORIZATION_KEY = "dMsRmno7UEqgd5SR6A-AmTZS5306VEmrpX4U-M41wfQ"
    AUTHORIZATION_BUILD_ID = "6c9828b6f309c72e13712fd615b372f4"
    AUTHORIZATION_TIMEOUT = 8

    APP_MODE_WEBHTV = "webhtv"
    APP_MODE_OKTV = "oktv"
    APP_MODE_UNKNOWN = "unknown"
    OK_CONFIG_A = os.path.join(DETECTED_STORAGE_ROOT, "TV", "CustomCsp", "智能点播.json")
    OK_CONFIG_B = OK_CONFIG_A  # 不使用OK影视，指向同一文件
    OK_BASE_CACHE = os.path.join(DETECTED_STORAGE_ROOT, "TV", "CustomCsp", "基础配置缓存.json")
    OK_CONFIG_MARKER = "localAutoLoader"
    OK_CONFIG_VERSION = 1
    WEBHTV_LIVE_CONFIG = os.path.join(
        DETECTED_STORAGE_ROOT, "TV", "CustomCsp", "智能直播.json"
    )

    PACKAGE_SERVICE_URL = ""
    PACKAGE_DOWNLOAD_URL = ""
    PACKAGE_DOWNLOAD_NAME = "潇洒"
    PACKAGE_DOWNLOAD_ENABLED = False
    PACKAGE_INSTALL_MARKER = ".dual-local-package"
    PACKAGE_DOWNLOAD_DIR = os.path.join(
        DETECTED_STORAGE_ROOT, "TV", "CustomCsp", "downloads"
    )
    ONLINE_REPOSITORY_STATE_DIR = os.path.join(
        DETECTED_STORAGE_ROOT, "TV", "CustomCsp", "online-repositories"
    )
    # v8.0：网络扫描根的本地镜像根目录（每个网络根一个 <id> 子目录）。
    NETWORK_ROOT_CACHE_DIR = os.path.join(
        DETECTED_STORAGE_ROOT, "TV", "CustomCsp", "network-cache"
    )
    ONLINE_REPOSITORY_MARKER = ".local-repository.json"
    ONLINE_REPOSITORY_STATE_FORMAT = "local-media-repository-state/v1"
    MAX_REPOSITORY_MANIFEST_SIZE = 2 * 1024 * 1024
    MAX_REPOSITORY_FILES = 3000
    MAX_REPOSITORY_FILE_SIZE = 16 * 1024 * 1024
    MAX_REPOSITORY_TOTAL_SIZE = 128 * 1024 * 1024
    MAX_PACKAGE_DOWNLOAD_SIZE = 128 * 1024 * 1024
    MAX_PACKAGE_EXTRACT_SIZE = 512 * 1024 * 1024
    MAX_PACKAGE_FILES = 10000
    MAX_PACKAGE_FILE_SIZE = 128 * 1024 * 1024
    MAX_PACKAGE_CONFIG_SIZE = 4 * 1024 * 1024
    MAX_PACKAGE_CONFIG_DEPENDENCIES = 2000
    PACKAGE_DEPENDENCY_EXTENSIONS = (
        ".jar", ".py", ".js", ".json", ".jsonc", ".html",
        ".txt", ".m3u", ".m3u8", ".wasm", ".so", ".dat",
    )
    PACKAGE_ROOT_CONTEXT_FIELDS = (
        "spider", "parses", "proxy", "flags", "rules", "ijk", "ads",
        "doh", "hosts", "headers", "parse", "wallpaper", "logo",
        "notice", "danmaku", "webHomeExtensions",
    )

    HTML_API = "csp_Builtin"

    PAGE_SIZE = 60
    BACKUP_BEFORE_WRITE = True
    ALLOW_EMPTY_WRITE = False
    DEFAULT_SEARCHABLE = 1
    DEFAULT_QUICK_SEARCH = 1
    STRICT_RECOGNITION = True
    CACHE_VERSION = 13
    AUTO_RELOAD_APP = True
    AUTO_SCAN_ON_EMPTY = True
    # 测活结束后是否把屏蔽站点从配置中移除。默认关闭：测活存在误判，
    # 移除虽可恢复但会让站点从列表消失，需用户主动开启。
    AUTO_PRUNE_BLOCKED = False
    AUTO_SCAN_COOLDOWN = 300.0
    MANUAL_SCAN_DEDUP_WINDOW = 4.0
    APP_PORT_START = 9978
    APP_PORT_END = 9998
    APP_REQUEST_TIMEOUT = 0.35
    APP_RELOAD_DELAY = 1.0
    APP_PAGE_REFRESH_DELAY = 0.65
    MAX_SCAN_FILES = 3000
    MAX_SCAN_DEPTH = 8
    MAX_SOURCE_SIZE = 5 * 1024 * 1024
    MAX_JAR_DEX_SCAN_SIZE = 64 * 1024 * 1024
    MAX_LOG_SIZE = 256 * 1024
    SITE_TEST_TIMEOUT = 3.0
    SITE_FUNCTION_TEST_TIMEOUT = 15.0
    SITE_TEST_CONCURRENCY = 10
    SITE_TEST_AVAILABLE_TTL = 24 * 60 * 60
    SITE_TEST_FAILURE_TTL = 10 * 60
    SITE_TEST_LIMITED_TTL = 30 * 60
    # 失效需连续确认的次数：首次失效只降级为受限并保留在列表中，
    # 避免网络抖动、上游限流或单次超时把可用站点直接从 App 移除。
    SITE_TEST_FAILURE_CONFIRM_COUNT = 2
    MAX_SITE_TESTS = 300
    SITE_TEST_CACHE_VERSION = 7
    SITE_TEST_HISTORY_LIMIT = 10
    MEDIA_PROBE_TIMEOUT = 4.0
    MEDIA_SAMPLE_BYTES = 256 * 1024
    MEDIA_PLAYLIST_BYTES = 128 * 1024
    GENERATED_KEY_PREFIX = "local_auto_"
    GENERATED_LIVE_PREFIX = "local_auto_live_"
    GENERATED_CONTEXT_PREFIX = "local_auto_context_"
    GENERATED_INSERT_INDEX = None  # None 表示追加；也可填写 0、1、2……

    JS_EXCLUDE = {
        "drpy2-fast.min.js",
        "drpy2.min.js",
        "drpy2-obj.min.js",
        "drpy2-template.js",
        "drpy2.js",
        "config.js",
    }
    JS_RUNTIME_NAMES = (
        "drpy2.min.js",
        "drpy2.js",
        "drpy2-fast.min.js",
        "drpy2-obj.min.js",
    )
    SKIP_DIRS = {
        "__pycache__",
        "node_modules",
        ".git",
        ".svn",
        "lib",
        "libs",
        "extension",
        "extensions",
        "webhomeextensions",
        # v8.0：网络目录镜像只允许由网络根 spec 扫描，避免本地根重复收录/错组。
        "network-cache",
    }
    PY_EXCLUDE_RELATIVE = {"base/spider.py"}
    JS_EXTENSION_SUFFIXES = (".ext.js", ".extension.js", ".user.js")
    ADULT_SYMBOLS = ("🔞", "🈲", "㊙")
    ADULT_KEYWORDS = (
        "18禁", "r18", "成人", "色情", "情色", "无码", "有码", "女优",
        "麻豆", "偷拍", "乱伦", "淫", "福利姬", "裸聊", "约炮", "里番",
        "少妇", "爱色", "好色", "色播", "色库", "色岛", "色站", "黄色仓库",
        "小黄书", "榨汁姐", "国产麻豆", "高端外泄", "自拍偷拍", "国产自拍",
    )
    ADULT_LATIN_PATTERN = re.compile(
        r"(?:rule34|porn|hentai|jable|javday|jav6k|javffm|javtsunami|xvideos|"
        r"xhamster|xnxx|missav|mrjav|netflav|pornlulu|pornhub|sexnguon|"
        r"onlyfans|redtube|youporn|spankbang|brazzers|hanime|91porn|"
        r"91md|avgle|kissav|pandaav|airav|kanav|nowav|soav|owoav|qinav)",
        re.IGNORECASE,
    )
    # ==========================================================================

    TYPE_ORDER = {"PY": 0, "JS": 1, "CSP": 2, "HTML": 3}
    TYPE_PREFIX = {
        "PY": "",
        "JS": "",
        "CSP": "",
        "HTML": "",
    }
    TYPE_LABEL = {
        "PY": "PY",
        "JS": "JS",
        "CSP": "JAR/CSP",
        "HTML": "HTML",
    }
    TYPE_GROUP = {
        "PY": "[py]",
        "JS": "[js]",
        "CSP": "[jar]",
        "HTML": "[html]",
    }
    TYPE_EXTENSIONS = {
        "PY": [".py"],
        "JS": [".js", ".json"],
        "CSP": [".json"],
        "HTML": [".html"],
    }
    REPOSITORY_TYPE_DIRS = {
        "py": "PY",
        "js": "JS",
        "csp": "CSP",
        "html": "HTML",
    }
    SCAN_SETTINGS_TID = "scan_settings"
    BACKUPS_TID = "scan_backups"
    FAVORITES_TID = "favorites"
    TAG_TID_PREFIX = "tag:"
    STATUS_ID = "__local_source_status__"
    RESCAN_ID = "__local_source_rescan__"
    # v7.0：扫描与加载分离，首页拆为两张独立卡片。
    SCAN_NOW_ID = "__local_source_scan_only__"
    LOAD_ALL_ID = "__local_source_load_all__"
    CLEAR_SITES_ID = "__local_source_clear_sites__"
    FULL_CLEAR_ID = "__local_source_full_clear__"
    BATCH_UNBLOCK_ID = "__local_source_batch_unblock__"
    UNBLOCK_ALL_ID = "__local_source_unblock_all__"
    DELETE_BACKUPS_ID = "__local_source_delete_backups__"
    TEST_SITES_ID = "__local_source_test_sites__"
    RETEST_SITES_ID = "__local_source_retest_sites__"
    AUTO_CLASSIFY_ID = "__local_source_auto_classify__"
    SCAN_BASE_PATH_ID = "__local_source_scan_base_path__"
    RESET_SCAN_BASE_ID = "__local_source_reset_scan_base__"
    ACTION_RESCAN = "local_source_rescan"
    # v7.0：仅扫描不写盘 / 加载全部扫描结果。
    ACTION_SCAN_ONLY = "local_source_scan_only"
    ACTION_LOAD_ALL = "local_source_load_all"
    ACTION_OPEN_SCAN_ONLY = "local_source_open_scan_only"
    ACTION_OPEN_LOAD_ALL = "local_source_open_load_all"
    # v7.0：文件浏览器（browser:<编码目录>）与文件三选一加载。
    BROWSER_TID_PREFIX = "browser:"
    BROWSER_ROOT_TID = "browser:"
    # v7.0：已永久加载站点列表分类。
    LOADED_TID = "loaded:"
    ACTION_LOAD_CHOICE_PREFIX = "local_source_load_choice:"
    ACTION_LOAD_PERM_PREFIX = "local_source_load_perm:"
    ACTION_LOAD_TEMP_PREFIX = "local_source_load_temp:"
    ACTION_UNLOAD_PREFIX = "local_source_unload:"
    ACTION_BLOCK_PREFIX = "local_source_block:"
    # v7.0：临时加载走 FloatSpider 方案——反射运行中 VodConfig 内存 addSite，
    # 不写任何配置文件，退出 App 后随进程消失。以下为跨壳类名候选。
    RUNTIME_VOD_CONFIG_SUFFIXES = (
        "api.config.VodConfig",   # 新版 FongMi 及主流分支
        "api.VodConfig",          # 旧版 FongMi（config 子包重构前）
        "config.VodConfig",
        "VodConfig",
    )
    RUNTIME_SITE_SUFFIXES = (
        "bean.Site",
        "bean.site.Site",
        "api.Site",
        "api.config.Site",
        "model.Site",
    )
    RUNTIME_URL_UTIL_SUFFIXES = ("utils.UrlUtil",)
    RUNTIME_REFRESH_EVENT_SUFFIXES = ("event.RefreshEvent",)
    RUNTIME_BASE_PACKAGES = ("com.fongmi.android.tv", "com.github.catvod")
    # ClassLoader 兜底用的锚点类：必须与壳代码在同一 dex / 类加载器。
    # 不能用 android.app.Application（由框架类加载器加载，找不到壳类）。
    RUNTIME_ANCHOR_CLASSES = ("com.github.catvod.Proxy",)
    ACTION_CLEAR_SITES = "local_source_clear_sites"
    ACTION_FULL_CLEAR = "local_source_full_clear"
    ACTION_UNLOAD_ALL_PERM = "local_source_unload_all_perm"
    ACTION_CONVERT_ALL_TO_TEMP = "local_source_convert_all_to_temp"
    ACTION_BATCH_UNBLOCK = "local_source_batch_unblock"
    ACTION_UNBLOCK_ALL = "local_source_unblock_all"
    ACTION_DELETE_BACKUPS = "local_source_delete_backups"
    ACTION_TEST_SITES = "local_source_test_sites"
    ACTION_RETEST_SITES = "local_source_retest_sites"
    ACTION_AUTO_CLASSIFY = "local_source_auto_classify"
    ACTION_OPEN_STATUS = "local_source_open_status"
    ACTION_OPEN_RESCAN = "local_source_open_rescan"
    ACTION_OPEN_TEST_SITES = "local_source_open_test_sites"
    ACTION_OPEN_RETEST_SITES = "local_source_open_retest_sites"
    ACTION_BROWSER_BATCH_SELECT = "local_source_browser_batch_select"
    ACTION_OPEN_AUTO_CLASSIFY = "local_source_open_auto_classify"
    ACTION_OPEN_CLEAR_SITES = "local_source_open_clear_sites"
    ACTION_OPEN_FULL_CLEAR = "local_source_open_full_clear"
    ACTION_EDIT_SCAN_BASE = "local_source_edit_scan_base"
    ACTION_RESET_SCAN_BASE = "local_source_reset_scan_base"
    ACTION_EDIT_SCAN_TYPES = "local_source_edit_scan_types"
    ACTION_EDIT_DOWNLOAD_URL = "local_source_edit_download_url"
    ACTION_TOGGLE_DOWNLOAD = "local_source_toggle_download"
    ACTION_DOWNLOAD_PACKAGE = "local_source_download_package"
    ACTION_DOWNLOAD_PACKAGE_PREFIX = "local_source_download_package:"
    ACTION_DELETE_DOWNLOAD_SITES = "local_source_delete_download_sites"
    ACTION_EDIT_REPOSITORY_URL = "local_source_edit_repository_url"
    ACTION_APPLY_SCAN_CONFIG = "local_source_apply_scan_config"
    ACTION_TOGGLE_TYPE_PREFIX = "local_source_toggle_type:"
    ACTION_TOGGLE_AUTO_SCAN = "local_source_toggle_auto_scan"
    ACTION_TOGGLE_AUTO_PRUNE = "local_source_toggle_auto_prune"
    ACTION_TOGGLE_IGNORE_PREFIX = "local_source_toggle_ignore:"
    ACTION_RESTORE_SNAPSHOT_PREFIX = "local_source_restore_snapshot:"
    ACTION_SOURCE_PREFIX = "local_source_info:"
    ACTION_EDIT_SOURCE_METADATA = "local_source_edit_metadata"
    ACTION_EXPORT_PROFILE = "local_source_export_profile"
    ACTION_IMPORT_PROFILE = "local_source_import_profile"
    ACTION_SYNC_REPOSITORIES = "local_source_sync_repositories"
    # ======================================================================
    # v8.0 网络扫描根（路线 B：远程目录镜像到本地缓存后走本地扫描链路）
    # ======================================================================
    NETWORK_ROOTS_TID = "network_roots"
    NETWORK_ADD_ID = "__local_source_network_add__"
    NETWORK_SYNC_ALL_ID = "__local_source_network_sync_all__"
    NETWORK_ROOT_CACHE_DIRNAME = "network-cache"
    # 标记文件不带 .json/.html 等扫描扩展名，避免被本地扫描当源文件误收。
    NETWORK_MANIFEST_NAME = ".netmanifest"
    NETWORK_MARKER_NAME = ".netroot"
    NETWORK_PROTOCOLS = ("auto", "http", "webdav", "github", "gitee")
    NETWORK_TIMEOUT = 12
    NETWORK_CONNECT_TIMEOUT = 8
    NETWORK_WORKERS = 4
    NETWORK_MAX_FILES = 2000
    NETWORK_MAX_DEPTH = 8
    NETWORK_MAX_FILE_SIZE = 5 * 1024 * 1024
    # 镜像只收录本地扫描链认识的源文件扩展名。
    NETWORK_EXTENSIONS = (".py", ".js", ".json", ".html")
    # GitHub 公益加速站（2026 仍存活）：直连失败时按序自动回退，拼接方式为
    # 「加速站 + 完整 GitHub URL」，同时支持 raw / codeload 归档 / 部分 API。
    # 仅用于无 Token 的公开仓库；私有库带凭据时强制直连，避免凭据泄漏给第三方。
    NETWORK_GITHUB_MIRRORS = (
        "https://gh-proxy.org/",
        "https://ghfast.top/",
        "https://ghproxy.net/",
        "https://github.moeyy.xyz/",
        "https://gh.llkk.cc/",
    )
    # API 不可达时改拉源码归档（tar.gz）列举目录树的体积上限。
    NETWORK_GITHUB_ARCHIVE_MAX_SIZE = 64 * 1024 * 1024
    ACTION_NET_ADD = "local_source_network_add"
    ACTION_NET_SYNC_ALL = "local_source_network_sync_all"
    # 分类页根卡：点击弹出操作菜单（同步/编辑/停用/删除）。
    ACTION_NET_ROOT_PREFIX = "local_source_network_root:"
    ACTION_NET_SYNC_PREFIX = "local_source_network_sync:"
    ACTION_NET_EDIT_PREFIX = "local_source_network_edit:"
    ACTION_NET_TOGGLE_PREFIX = "local_source_network_toggle:"
    ACTION_NET_DELETE_PREFIX = "local_source_network_delete:"
    # 引导前缀：在真实 action 前加此前缀，触发「确认执行」对话框。
    # 确认后由后台线程去掉前缀调用 action() 执行真实操作。
    ACTION_OPEN_PREFIX = "local_source_open:"

    def __init__(self):
        super().__init__()
        self.lock = threading.RLock()
        self.inited = False
        self.scan_roots = [dict(item) for item in self.SCAN_ROOTS]
        self.configured_scan_roots = [dict(item) for item in self.scan_roots]
        self.scan_base_path = ""
        self.registry_path = self.REGISTRY_PATH
        self.output_path = self.OUTPUT_PATH
        self.settings_path = os.path.join(os.path.dirname(self.REGISTRY_PATH), "配置文件.json")
        self.cache_path = os.path.join(os.path.dirname(self.REGISTRY_PATH), "扫描缓存.json")
        self.backup_dir = os.path.join(os.path.dirname(self.REGISTRY_PATH), "backups")
        self.roots_config_path = os.path.join(
            os.path.dirname(self.REGISTRY_PATH), "扫描目录.json"
        )
        self.log_path = os.path.join(
            os.path.dirname(self.REGISTRY_PATH), "运行日志.log"
        )
        self.html_api = self.HTML_API
        self.local_base_dir = self.LOCAL_BASE_DIR
        self.page_size = self.PAGE_SIZE
        self.max_scan_files = self.MAX_SCAN_FILES
        self.max_scan_depth = self.MAX_SCAN_DEPTH
        self.max_source_size = self.MAX_SOURCE_SIZE
        self.max_log_size = self.MAX_LOG_SIZE
        self.backup_before_write = self.BACKUP_BEFORE_WRITE
        self.allow_empty_write = self.ALLOW_EMPTY_WRITE
        self.generated_insert_index = self.GENERATED_INSERT_INDEX
        self.type_enabled = {source_type: True for source_type in self.TYPE_ORDER}
        self.pending_type_enabled = dict(self.type_enabled)
        # 「站点功能测活」弹窗中的文件夹开关：csp / html / js / py。
        # True=测活该类型文件夹内的文件，False=跳过。
        self._site_test_folder_switches = {
            source_type: True for source_type in self.TYPE_ORDER
        }
        self.block_adult_sites = False
        self.pending_block_adult_sites = False
        self.config_dirty = False
        self.manual_ignored_sources = set()
        self.auto_blocked_sources = set()
        self.adult_blocked_sources = set()
        self.adult_allowed_sources = set()
        self.ignored_sources = set()
        # 被「自动清理屏蔽站点」移出配置的 identity。不删除源文件，
        # 只在扫描阶段跳过；清除入口会一并清空，使其重新参与扫描。
        self.pruned_sources = set()
        self.site_test_results = {}
        self.site_test_history = {}
        self.source_metadata = {}
        self.incomplete_scan_roots = []
        self.incomplete_scan_types = set()
        self.strict_recognition = self.STRICT_RECOGNITION
        self.auto_reload_app = self.AUTO_RELOAD_APP
        self.auto_scan_on_empty = self.AUTO_SCAN_ON_EMPTY
        self.auto_prune_blocked = self.AUTO_PRUNE_BLOCKED
        self.auto_scan_suspended = False
        self.app_mode = self._detect_app_mode()
        self.ok_config_a = self.OK_CONFIG_A
        self.ok_config_b = self.OK_CONFIG_B
        self.ok_base_cache_path = self.OK_BASE_CACHE
        self.ok_base_config_url = ""
        self.ok_last_target = ""
        self.webhtv_live_config_path = self.WEBHTV_LIVE_CONFIG
        self.package_service_url = self.PACKAGE_SERVICE_URL
        self.package_download_url = self.PACKAGE_DOWNLOAD_URL
        self.package_download_enabled = self.PACKAGE_DOWNLOAD_ENABLED
        self.package_external_configured = False
        self.package_device_id = hashlib.sha256(os.urandom(32)).hexdigest()[:32]
        self.package_download_sites = []
        self.package_download_dir = self.PACKAGE_DOWNLOAD_DIR
        self._package_download_lock = threading.Lock()
        self._package_download_thread = None
        self._package_download_state = "idle"
        self._package_download_message = ""
        self._package_download_trace_id = ""
        self._package_authorization_ticket = ""
        self._authorization_last_error = ""
        self.online_repositories = []
        self.online_repository_state_dir = self.ONLINE_REPOSITORY_STATE_DIR
        self._repository_sync_lock = threading.Lock()
        self._repository_sync_thread = None
        self._repository_sync_state = "idle"
        self._repository_sync_message = ""
        self._repository_sync_trace_id = ""
        # ===== v8.0 网络扫描根状态 =====
        # network_roots: [{id,name,url,protocol,username,password,token,
        #   enabled,last_sync,last_status,last_message,file_count,byte_count}]
        self.network_roots = []
        self.network_root_cache_dir = self.NETWORK_ROOT_CACHE_DIR
        self._network_sync_running = False
        self._network_sync_root_id = ""
        self._network_sync_message = ""
        self._network_sync_lock = threading.Lock()
        # GitHub 加速站会话级记忆：None=未探测，""/直连成功，"https://..."镜像成功。
        # 第一个文件/接口探测成功后整条同步链路粘住该线路，避免每个文件重试。
        self._github_fast_base = None
        self.app_server_ports = list(range(self.APP_PORT_START, self.APP_PORT_END + 1))
        self.last_app_port = 0
        self.cache = self._empty_cache()
        self.status = self._empty_status()
        # ===== v7.0 扫描/加载分离相关状态 =====
        # 永久选择集合（persist 到配置文件）。None 表示尚未从 v6 迁移，
        # 首次扫描后按 registry 是否已有自动站点决定初始化为全选/空选。
        self.selected_identities = None
        self.selection_initialized = False
        # 临时选择集合：仅进程内有效。临时站点通过反射注入运行中的
        # VodConfig（FloatSpider 方案），不落任何配置文件，退出 App 后
        # 随进程自动消失，无需启动清理。
        self.temp_identities = set()
        # 默壳版：永久注入选择集合。
        # 单文件永久加载不再写入配置文件，而是像临时加载一样直接注入
        # 运行态站点表，并将 identity 持久化到本集合；App 启动/重建后
        # 自动重新注入（不限 PID，永久站点应在每次启动都恢复）。
        self.perm_injected_identities = set()
        # 临时站点当前 home key（自己记录，不读 App 侧：重建回退首站会
        # 污染持久化 home，看门补注需要靠它恢复选中）。
        self._temp_home_key = ""
        # None=加载全部（兼容旧管线语义）；set(identity)=仅生成子集。
        self._load_filter = None
        # True=已执行过仅扫描，结果可浏览但尚未加载。
        self.scan_only_done = False
        self._dialog_refs = []
        self._notification_refs = []
        self._proxy_alive = set()  # 保持所有动态代理存活直到 run() 完成
        self._proxy_id_counter = 0
        self._proxy_id_lock = threading.Lock()
        # 复用确认框作为「进度详情面板」的共享状态：
        # _active_progress_panel 是在途进度面板的引用（仅持有轻量句柄），
        # panel 在确认后进入 running 模式，_update_progress_panel() 会把
        # 任务进度实时回填到该面板的 TextView，供界面显示进度与详情。
        self._active_progress_panel = None
        self._progress_panel_key = 0
        self._progress_panel_lock = threading.Lock()
        # Chaquopy 桥接层在多个线程同时创建/回调 DynamicProxy Runnable 时
        # 可能错误调用抽象的 _chaquopyGetDict。所有 UI 代理的创建和调用
        # 必须通过此锁串行化，避免竞争条件导致崩溃。
        self._ui_proxy_lock = threading.RLock()
        # 通知保留单独的 gate，确保同一时刻只有一个通知代理在途。
        self._notification_gate = threading.Lock()
        self._site_test_toast = None
        self._site_test_thread = None
        self._site_test_control_lock = threading.Lock()
        self._site_test_cancel = threading.Event()
        self._destroyed = False
        self._jar_inspection_cache = {}
        self._app_identity_cache = None
        self._package_filter_excluded = False
        self._retest_pending = []
        self._retest_auto_blocked = set()
        self._reload_generation = 0
        self._page_refresh_generation = 0
        self._author_scan_surprise_shown = False

    def _retain_proxy(self, proxy):
        """保持代理存活，防止GC导致崩溃"""
        with self._proxy_id_lock:
            self._proxy_id_counter += 1
            proxy_id = self._proxy_id_counter
        self._proxy_alive.add(proxy_id)
        return proxy_id

    def _release_proxy(self, proxy_id):
        """释放代理引用"""
        self._proxy_alive.discard(proxy_id)

    def _disable_gc_for_proxy(self):
        """创建动态代理前禁用GC，防止Chaquopy内部映射表被破坏"""
        try:
            import gc
            gc.disable()
            gc.collect()
        except Exception:
            pass

    def _re_enable_gc_after_proxy(self):
        """代理创建后重新启用GC"""
        try:
            import gc
            gc.enable()
        except Exception:
            pass

    class _ProxyCreationLock:
        """上下文管理器：在创建动态代理时禁用GC"""
        def __init__(self, owner):
            self._owner = owner
        def __enter__(self):
            self._owner._ui_proxy_lock.acquire()
            self._owner._disable_gc_for_proxy()
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            self._owner._re_enable_gc_after_proxy()
            self._owner._ui_proxy_lock.release()
            return False  # 不吞掉异常

    def getName(self):
        return "智能加载 {}".format(self.VERSION)

    def _authorize_release(self, action):
        action = str(action or "").strip()
        if action not in ("package_download", "site_health"):
            raise ReleaseAuthorizationError("授权动作无效")
        # 本地授权校验已移除：不再访问远程授权服务器，直接放行并返回本地票据。
        # 原远端 build_id 授权被作者关闭后，这里已删除对 jwf.gtu.qzz.io 的请求，
        # 测活 / 本地包下载 / 在线仓库等操作不再被“版本构建不存在或已被替换”拦截。
        ticket = (
            "local-{}".format(
                hashlib.sha256(
                    "{}+{}".format(self.package_device_id, action).encode("utf-8")
                ).hexdigest()[:24]
            )
        )
        self._authorization_last_error = ""
        return ticket

    def _detect_app_mode(self):
        """探测当前进程自己的本机端口，避免多 App 同开时误判。"""
        try:
            from java import jclass

            proxy_class = jclass("com.github.catvod.Proxy")
            port = int(proxy_class.getPort())
            if port > 0:
                try:
                    payload = self._request_json(
                        "http://127.0.0.1:{}/manage/configs".format(port), 0.8
                    )
                    if isinstance(payload.get("items"), list):
                        return self.APP_MODE_WEBHTV
                except Exception:
                    pass
            try:
                jclass("com.fongmi.android.tv.setting.CustomCspSetting")
                return self.APP_MODE_WEBHTV
            except Exception:
                pass
            try:
                jclass("com.fongmi.android.tv.bean.Config")
                return self.APP_MODE_OKTV
            except Exception:
                return self.APP_MODE_UNKNOWN
        except Exception:
            # 桌面验证环境没有 Chaquopy Java bridge，保留可测试状态。
            return self.APP_MODE_UNKNOWN

    def _app_mode_label(self):
        return {
            self.APP_MODE_WEBHTV: "WebHTV",
            self.APP_MODE_OKTV: "OK影视",
        }.get(self.app_mode, "未识别环境")

    def init(self, extend=""):
        with self.lock:
            if self.inited:
                return
            external_options = self._parse_extend(extend)
            self.package_external_configured = self._has_package_download_url(
                external_options
            )
            self._apply_extend(external_options)
            self._load_roots_config()
            self.configured_scan_roots = [dict(item) for item in self.scan_roots]
            self._load_settings()
            # 外部仓库参数在本地设置读取后再次合并，确保 location.json/ext
            # 可以新增或更新同备注仓库，同时保留用户另外添加的本地仓库。
            self._apply_online_repository_options(external_options, merge=True)
            external_service_url = self._package_service_url_option(
                external_options
            )
            if external_service_url:
                self.package_service_url = external_service_url
                for item in self.package_download_sites:
                    if str(item.get("source_type", "")).lower() == "builtin":
                        item["url"] = external_service_url
                self._sync_legacy_package_download_fields()
            external_scan_base = self._scan_base_path_option(external_options)
            if external_scan_base:
                self._apply_scan_base_path(external_scan_base)
            self._migrate_builtin_package_install_directory()
            try:
                self._normalize_backup_storage()
            except Exception as exc:
                self._warn("历史备份整理失败: {}".format(exc))
            startup_warnings = list(self.status["warnings"])
            self._set_manual_idle_status()
            try:
                restored = self._restore_scan_snapshot()
            except Exception as exc:
                restored = False
                # 记入 startup_warnings，避免被补扫的状态重置覆盖
                warning = "扫描快照恢复失败: {}".format(exc)
                startup_warnings.append(warning)
                self._log("WARN", warning)
            if not restored:
                try:
                    self._auto_scan_on_enter_locked()
                except Exception as exc:
                    self._warn("进入自动补扫失败: {}".format(exc))
            elif not self.selection_initialized:
                # v6 -> v7：快照可用而选择集未初始化，按 registry 现状迁移。
                try:
                    self._ensure_selection_initialized_locked()
                except Exception as exc:
                    self._warn("加载选择初始化失败: {}".format(exc))
            if startup_warnings:
                self.status["warnings"] = list(dict.fromkeys(
                    startup_warnings + self.status["warnings"]
                ))
            self.inited = True
        # 默壳版：init 完成后自动恢复永久注入站点到运行态站点表。
        # 永久注入站点不受 PID 限制，每次启动都应恢复。
        if self.perm_injected_identities:
            try:
                self._restore_perm_injected_sites()
            except Exception as exc:
                self._warn("永久注入站点恢复失败: {}".format(exc))

    def _empty_cache(self):
        return {
            "sources": [],
            "ignored": [],
            "lives": [],
            "contexts": [],
            "source_index": {},
            "type_counts": {},
            "ignored_counts": {},
        }

    def _empty_status(self):
        return {
            "scan_time": "-",
            "found": 0,
            "included": 0,
            "skipped": 0,
            "duplicates": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "ignored": 0,
            "adult_filtered": 0,
            "compatibility_blocked": 0,
            "stale_ignored_removed": 0,
            "limit_reached": False,
            "manual_sites": 0,
            "generated_sites": 0,
            "generated_lives": 0,
            "duplicate_lives": 0,
            "added_sites": 0,
            "updated_sites": 0,
            "removed_sites": 0,
            "unchanged_sites": 0,
            "registry_changed": False,
            "write_state": "尚未扫描",
            "written": False,
            "warnings": [],
            "error": "",
        }

    # --------------------------------------------------------------------------
    # 可选 extend 配置
    # --------------------------------------------------------------------------
    def _apply_extend(self, extend):
        data = self._parse_extend(extend)
        if not isinstance(data, dict):
            return

        roots = data.get("scan_roots", data.get("scanRoots"))
        if isinstance(roots, list):
            normalized = self._normalize_scan_roots(roots)
            if normalized:
                self.scan_roots = normalized

        self.registry_path = self._string_option(
            data, ("registry_path", "registryPath", "base_config_path", "baseConfigPath"), self.registry_path
        )
        self.output_path = self._string_option(
            data, ("output_path", "outputPath"), self.registry_path
        )
        self.settings_path = self._string_option(
            data,
            ("settings_path", "settingsPath"),
            os.path.join(os.path.dirname(self.output_path), "配置文件.json"),
        )
        self.cache_path = self._string_option(
            data,
            ("cache_path", "cachePath"),
            os.path.join(os.path.dirname(self.output_path), "扫描缓存.json"),
        )
        self.backup_dir = self._string_option(
            data,
            ("backup_dir", "backupDir"),
            os.path.join(os.path.dirname(self.output_path), "backups"),
        )
        self.roots_config_path = self._string_option(
            data,
            ("roots_config_path", "rootsConfigPath"),
            os.path.join(os.path.dirname(self.output_path), "扫描目录.json"),
        )
        self.log_path = self._string_option(
            data,
            ("log_path", "logPath"),
            os.path.join(os.path.dirname(self.output_path), "运行日志.log"),
        )
        self.html_api = self._string_option(data, ("html_api", "htmlApi"), self.html_api)
        self.ok_config_a = self._string_option(
            data, ("ok_config_a", "okConfigA"), self.ok_config_a
        )
        self.ok_config_b = self._string_option(
            data, ("ok_config_b", "okConfigB"), self.ok_config_b
        )
        self.ok_base_cache_path = self._string_option(
            data, ("ok_base_cache", "okBaseCache"), self.ok_base_cache_path
        )
        self.ok_base_config_url = self._string_option(
            data, ("ok_base_config", "okBaseConfig"), self.ok_base_config_url
        )
        self.webhtv_live_config_path = self._string_option(
            data,
            ("webhtv_live_config", "webhtvLiveConfig"),
            self.webhtv_live_config_path,
        )
        self._apply_package_download_options(data)
        self.package_download_dir = self._string_option(
            data,
            ("package_download_dir", "packageDownloadDir"),
            self.package_download_dir,
        )
        self.online_repository_state_dir = self._string_option(
            data,
            ("online_repository_state_dir", "onlineRepositoryStateDir"),
            self.online_repository_state_dir,
        )
        self._apply_online_repository_options(data, merge=True)
        self.page_size = self._int_option(data, ("page_size", "pageSize"), self.page_size, 1, 200)
        self.max_scan_files = self._int_option(
            data, ("max_scan_files", "maxScanFiles"), self.max_scan_files, 1, 20000
        )
        self.max_scan_depth = self._int_option(
            data, ("max_scan_depth", "maxScanDepth"), self.max_scan_depth, 0, 32
        )
        self.max_source_size = self._int_option(
            data,
            ("max_source_size", "maxSourceSize"),
            self.max_source_size,
            1024,
            100 * 1024 * 1024,
        )
        self.max_log_size = self._int_option(
            data,
            ("max_log_size", "maxLogSize"),
            self.max_log_size,
            16 * 1024,
            2 * 1024 * 1024,
        )
        self.backup_before_write = self._bool_option(
            data, ("backup_before_write", "backupBeforeWrite"), self.backup_before_write
        )
        self.allow_empty_write = self._bool_option(
            data, ("allow_empty_write", "allowEmptyWrite"), self.allow_empty_write
        )
        self.strict_recognition = self._bool_option(
            data, ("strict_recognition", "strictRecognition"), self.strict_recognition
        )
        self.auto_reload_app = self._bool_option(
            data, ("auto_reload_app", "autoReloadApp"), self.auto_reload_app
        )
        self.auto_scan_on_empty = self._bool_option(
            data, ("auto_scan_on_empty", "autoScanOnEmpty"), self.auto_scan_on_empty
        )
        self.auto_prune_blocked = self._bool_option(
            data, ("auto_prune_blocked", "autoPruneBlocked"), self.auto_prune_blocked
        )
        if "generated_insert_index" in data or "generatedInsertIndex" in data:
            value = data.get("generated_insert_index", data.get("generatedInsertIndex"))
            try:
                self.generated_insert_index = max(0, int(value))
            except Exception:
                self.generated_insert_index = None

    def _parse_extend(self, extend):
        if isinstance(extend, dict):
            return extend
        if not isinstance(extend, str) or not extend.strip():
            return {}
        text = extend.strip()
        try:
            return json.loads(text)
        except Exception:
            pass
        path = text.replace("file://", "")
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fp:
                    return json.load(fp)
            except Exception:
                return {}
        return {}

    def _package_service_url_option(self, data):
        if not isinstance(data, dict):
            return ""
        service = data.get(
            "package_service_url", data.get("packageServiceUrl", "")
        )
        values = data.get(
            "package_download_sites", data.get("packageDownloadSites")
        )
        if isinstance(values, dict):
            values = [values]
        if not service and isinstance(values, list):
            for item in values:
                if not isinstance(item, dict):
                    continue
                if (
                    str(item.get("source_type", item.get("sourceType", ""))).lower()
                    in ("builtin", "default")
                    or str(item.get("id", "")).strip() in ("cf-service", "xiaosa")
                ):
                    service = item.get("url", item.get("downloadUrl", ""))
                    break
        if not service and not values:
            service = data.get(
                "package_download_url", data.get("packageDownloadUrl", "")
            )
        try:
            return self._normalize_package_download_url(service)
        except Exception:
            return ""

    def _has_package_download_url(self, data):
        if not isinstance(data, dict):
            return False
        explicit = data.get(
            "package_service_url", data.get("packageServiceUrl", "")
        )
        try:
            if self._normalize_package_download_url(explicit):
                return True
        except Exception:
            pass
        values = data.get(
            "package_download_sites", data.get("packageDownloadSites")
        )
        if isinstance(values, dict):
            values = [values]
        if not isinstance(values, list):
            return False
        return any(
            isinstance(item, dict)
            and (
                str(
                    item.get("source_type", item.get("sourceType", ""))
                ).strip().lower() in ("builtin", "default")
                or str(item.get("id", "")).strip() in ("cf-service", "xiaosa")
            )
            and bool(
                self._package_service_url_option(
                    {"package_download_sites": [item]}
                )
            )
            for item in values
        )

    def _scan_base_path_option(self, data):
        if not isinstance(data, dict):
            return ""
        value = data.get("scan_base_path", data.get("scanBasePath", ""))
        if not isinstance(value, str) or not value.strip():
            return ""
        return self._normalize_scan_base_path(value)

    def _load_roots_config(self):
        path = os.path.abspath(os.path.expanduser(self.roots_config_path))
        if not os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            if isinstance(data, list):
                roots = data
                limits = {}
            elif isinstance(data, dict):
                roots = data.get("roots", data.get("scan_roots", []))
                limits = data.get("limits", {})
            else:
                raise ValueError("顶层必须是数组或 JSON 对象")
            normalized = self._normalize_scan_roots(roots) if isinstance(roots, list) else []
            if normalized:
                self.scan_roots = normalized
            runtime = dict(data) if isinstance(data, dict) else {}
            if isinstance(runtime.get("runtime"), dict):
                runtime.update(runtime["runtime"])
            self.ok_config_a = self._string_option(
                runtime, ("ok_config_a", "okConfigA"), self.ok_config_a
            )
            self.ok_config_b = self._string_option(
                runtime, ("ok_config_b", "okConfigB"), self.ok_config_b
            )
            self.ok_base_cache_path = self._string_option(
                runtime,
                ("ok_base_cache", "okBaseCache"),
                self.ok_base_cache_path,
            )
            self.ok_base_config_url = self._string_option(
                runtime,
                ("ok_base_config", "okBaseConfig"),
                self.ok_base_config_url,
            )
            self._apply_package_download_options(runtime)
            self.package_download_dir = self._string_option(
                runtime,
                ("package_download_dir", "packageDownloadDir"),
                self.package_download_dir,
            )
            self.log_path = self._string_option(
                runtime, ("log_path", "logPath"), self.log_path
            )
            if isinstance(limits, dict):
                self.max_scan_files = self._int_option(
                    limits,
                    ("max_files", "maxFiles"),
                    self.max_scan_files,
                    1,
                    20000,
                )
                self.max_scan_depth = self._int_option(
                    limits,
                    ("max_depth", "maxDepth"),
                    self.max_scan_depth,
                    0,
                    32,
                )
                self.max_source_size = self._int_option(
                    limits,
                    ("max_file_size", "maxFileSize"),
                    self.max_source_size,
                    1024,
                    100 * 1024 * 1024,
                )
                self.max_log_size = self._int_option(
                    limits,
                    ("max_log_size", "maxLogSize"),
                    self.max_log_size,
                    16 * 1024,
                    2 * 1024 * 1024,
                )
        except Exception as exc:
            self._warn("扫描目录配置读取失败，将使用自动探测目录: {}".format(exc))

    def _normalize_scan_roots(self, roots):
        result = []
        seen = set()
        for item in roots:
            if isinstance(item, str):
                path = item
                source_type = os.path.basename(path).upper()
                if source_type == "HTML":
                    pass
                elif source_type == "CSP":
                    pass
                elif source_type not in ("PY", "JS"):
                    continue
                extensions = self.TYPE_EXTENSIONS[source_type]
            elif isinstance(item, dict):
                path = str(item.get("path", "")).strip()
                source_type = str(item.get("type", "")).strip().upper()
                if source_type not in self.TYPE_ORDER:
                    continue
                extensions = item.get("extensions", self.TYPE_EXTENSIONS[source_type])
            else:
                continue
            if not path:
                continue
            if not isinstance(extensions, (list, tuple)):
                extensions = [extensions]
            extensions = [self._normalize_extension(ext) for ext in extensions]
            extensions = [ext for ext in extensions if ext]
            if not extensions:
                extensions = list(self.TYPE_EXTENSIONS[source_type])
            identity = (os.path.abspath(os.path.expanduser(path)), source_type)
            if identity in seen:
                continue
            seen.add(identity)
            result.append({"path": path, "type": source_type, "extensions": extensions})
        return result

    def _string_option(self, data, keys, fallback):
        for key in keys:
            if key in data and str(data.get(key, "")).strip():
                return str(data[key]).strip()
        return fallback

    def _int_option(self, data, keys, fallback, minimum, maximum):
        for key in keys:
            if key not in data:
                continue
            try:
                return max(minimum, min(maximum, int(data[key])))
            except Exception:
                return fallback
        return fallback

    def _bool_option(self, data, keys, fallback):
        for key in keys:
            if key not in data:
                continue
            value = data[key]
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            return str(value).strip().lower() in ("1", "true", "yes", "on")
        return fallback

    def _normalize_repository_name(self, value):
        name = re.sub(r"[\x00-\x1f]+", " ", str(value or "")).strip()
        name = re.sub(r"\s+", " ", name)
        if not name:
            raise ValueError("备注名不能为空")
        if name in (".", "..") or re.search(r"[\\/:*?\"<>|]", name):
            raise ValueError("备注名不能包含 \\ / : * ? \" < > | 等文件夹非法字符")
        if len(name) > 40:
            raise ValueError("备注名不能超过 40 个字符")
        return name

    def _normalize_repository_url(self, value):
        url = str(value or "").strip().strip('"').strip("'")
        if not url:
            raise ValueError("仓库地址不能为空")
        if len(url) > 2048:
            raise ValueError("仓库地址过长")
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
            raise ValueError("仓库地址必须是 http 或 https URL")
        host = (parsed.hostname or "").lower()
        parts = [urllib.parse.unquote(item) for item in parsed.path.split("/") if item]
        if host in ("github.com", "www.github.com") and len(parts) >= 2:
            owner, repository = parts[0], parts[1]
            if repository.lower().endswith(".git"):
                repository = repository[:-4]
            ref = "HEAD"
            relative = []
            if len(parts) >= 4 and parts[2].lower() in ("blob", "tree"):
                ref = parts[3]
                relative = parts[4:]
                if parts[2].lower() == "blob" and relative:
                    pass
                elif not relative or not relative[-1].lower().endswith(".json"):
                    relative.append("repository.json")
            else:
                relative = ["repository.json"]
            path = "/".join(
                urllib.parse.quote(item, safe="-._~")
                for item in (owner, repository, ref) + tuple(relative)
            )
            return "https://raw.githubusercontent.com/{}".format(path)
        path = parsed.path
        if path.endswith("/"):
            path += "repository.json"
        return urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, path, parsed.query, "")
        )

    def _repository_id(self, name):
        return hashlib.sha256(
            self._normalize_repository_name(name).casefold().encode("utf-8")
        ).hexdigest()[:16]

    def _normalize_online_repositories(self, values):
        if isinstance(values, dict):
            values = [values]
        if not isinstance(values, list):
            return []
        result = []
        seen_names = set()
        seen_urls = set()
        for raw in values[:50]:
            if not isinstance(raw, dict):
                continue
            try:
                name = self._normalize_repository_name(
                    raw.get("name", raw.get("remark", raw.get("label", "")))
                )
                url = self._normalize_repository_url(
                    raw.get("url", raw.get("repositoryUrl", ""))
                )
            except Exception:
                continue
            name_key = name.casefold()
            url_key = url.casefold()
            if name_key in seen_names or url_key in seen_urls:
                continue
            seen_names.add(name_key)
            seen_urls.add(url_key)
            try:
                file_count = max(
                    0,
                    int(raw.get("file_count", raw.get("fileCount", 0)) or 0),
                )
            except Exception:
                file_count = 0
            item = {
                "id": self._repository_id(name),
                "name": name,
                "url": url,
                "enabled": self._as_bool(raw.get("enabled", True), True),
                "version": str(raw.get("version", "") or "").strip()[:80],
                "manifest_digest": str(
                    raw.get("manifest_digest", raw.get("manifestDigest", "")) or ""
                ).strip().lower(),
                "file_count": file_count,
                "last_sync": str(
                    raw.get("last_sync", raw.get("lastSync", "")) or ""
                ).strip()[:32],
                "last_status": str(
                    raw.get("last_status", raw.get("lastStatus", "")) or ""
                ).strip()[:24],
                "last_message": str(
                    raw.get("last_message", raw.get("lastMessage", "")) or ""
                ).strip()[:240],
            }
            result.append(item)
        return result

    def _apply_online_repository_options(self, data, merge=False):
        if not isinstance(data, dict):
            return
        key = (
            "online_repositories"
            if "online_repositories" in data
            else "onlineRepositories"
            if "onlineRepositories" in data
            else ""
        )
        if key:
            raw_values = data.get(key)
        else:
            single_url = data.get(
                "online_repository_url", data.get("onlineRepositoryUrl", "")
            )
            if not str(single_url or "").strip():
                return
            raw_values = [
                {
                    "name": data.get(
                        "online_repository_name",
                        data.get("onlineRepositoryName", "在线仓库"),
                    ),
                    "url": single_url,
                    "enabled": data.get(
                        "online_repository_enabled",
                        data.get("onlineRepositoryEnabled", True),
                    ),
                }
            ]
        normalized = self._normalize_online_repositories(raw_values)
        if not merge:
            self.online_repositories = normalized
            return
        existing = {
            str(item.get("name", "")).casefold(): item
            for item in self.online_repositories
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        }
        for external in normalized:
            name_key = external["name"].casefold()
            current = existing.get(name_key)
            if current is None:
                self.online_repositories.append(external)
                existing[name_key] = external
                continue
            current["url"] = external["url"]
            current["enabled"] = bool(external.get("enabled", True))
            current["id"] = external["id"]


    def _online_repositories_summary(self):
        if not self.online_repositories:
            return "未配置在线仓库"
        enabled = sum(
            1
            for item in self.online_repositories
            if self._as_bool(item.get("enabled", True), True)
        )
        return "共 {} 个，已启用 {} 个：{}".format(
            len(self.online_repositories),
            enabled,
            "、".join(
                "{}({})".format(
                    item.get("name", "未命名"),
                    "开" if self._as_bool(item.get("enabled", True), True) else "关",
                )
                for item in self.online_repositories
            ),
        )

    def _package_download_site_id(self, name, url):
        payload = "{}\0{}".format(str(name or ""), str(url or ""))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _package_download_site_enabled(self, item):
        fallback = self._as_bool(item.get("enabled", True), True)
        return self._as_bool(
            item.get("site_enabled", item.get("siteEnabled", fallback)),
            fallback,
        )

    def _package_download_live_enabled(self, item):
        fallback = self._as_bool(item.get("enabled", True), True)
        return self._as_bool(
            item.get("live_enabled", item.get("liveEnabled", fallback)),
            fallback,
        )

    def _package_download_health_enabled(self, item):
        return self._as_bool(
            item.get("health_enabled", item.get("healthEnabled", True)),
            True,
        )

    def _package_download_site_active(self, item):
        return bool(
            self._package_download_site_enabled(item)
            or self._package_download_live_enabled(item)
        )

    def _normalize_package_download_name(self, value):
        name = re.sub(r"[\x00-\x1f]+", " ", str(value or "")).strip()
        name = re.sub(r"\s+", " ", name)
        if not name:
            raise ValueError("备注名不能为空")
        if name in (".", "..") or re.search(r"[\\/:*?\"<>|]", name):
            raise ValueError("备注名不能包含 \\ / : * ? \" < > | 等文件夹非法字符")
        if len(name) > 40:
            raise ValueError("备注名不能超过 40 个字符")
        return name

    def _default_package_download_site(self, enabled=None):
        service_url = self.package_service_url or self.PACKAGE_SERVICE_URL
        if not service_url:
            return None
        initial = bool(
            self.PACKAGE_DOWNLOAD_ENABLED if enabled is None else enabled
        )
        return {
            "id": "cf-service",
            "name": self.PACKAGE_DOWNLOAD_NAME,
            "url": service_url,
            "enabled": initial,
            "site_enabled": initial,
            "live_enabled": initial,
            "health_enabled": True,
            "source_type": "builtin",
            "site_count": 0,
            "dependency_count": 0,
            "live_count": 0,
        }

    def _migrate_package_download_name(self, value, fallback="本地包"):
        raw = str(value or fallback)
        try:
            return self._normalize_package_download_name(raw)
        except Exception:
            migrated = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", raw)
            migrated = re.sub(r"\s+", " ", migrated).strip(" ._")
            return self._normalize_package_download_name(
                (migrated or fallback)[:40]
            )

    def _normalize_package_download_sites(self, values, default_if_empty=True):
        normalized = []
        seen_names = set()
        seen_urls = set()
        if isinstance(values, dict):
            values = [values]
        if isinstance(values, list):
            for raw in values[:50]:
                if not isinstance(raw, dict):
                    continue
                try:
                    url = self._normalize_package_download_url(
                        raw.get("url", raw.get("downloadUrl", ""))
                    )
                    name = self._migrate_package_download_name(
                        raw.get("name", raw.get("remark", raw.get("label", ""))),
                        fallback=self._package_name_from_url(url),
                    )
                except Exception:
                    continue
                site_id = re.sub(
                    r"[^A-Za-z0-9_-]+", "", str(raw.get("id", "")).strip()
                )[:40]
                if not site_id:
                    site_id = self._package_download_site_id(name, url)
                raw_source_type = str(
                    raw.get("source_type", raw.get("sourceType", ""))
                ).strip().lower()
                if raw_source_type in ("builtin", "default"):
                    source_type = "builtin"
                elif raw_source_type in ("config", "json", "tvbox"):
                    source_type = "config"
                elif (
                    site_id in ("cf-service", "xiaosa")
                    or name in (self.PACKAGE_DOWNLOAD_NAME, "CF本地包")
                ) and self.package_service_url and (
                    self._package_download_url_identity(url)
                    == self._package_download_url_identity(self.package_service_url)
                ):
                    # 兼容旧 v4：CF 服务曾被保存成普通 ZIP 下载站点。
                    source_type = "builtin"
                else:
                    source_type = "zip"
                if source_type == "builtin":
                    name = self.PACKAGE_DOWNLOAD_NAME
                name_key = name.casefold()
                url_key = self._package_download_url_identity(url)
                if name_key in seen_names or url_key in seen_urls:
                    continue
                try:
                    site_count = max(
                        0, int(raw.get("site_count", raw.get("siteCount", 0)) or 0)
                    )
                except Exception:
                    site_count = 0
                try:
                    dependency_count = max(
                        0,
                        int(
                            raw.get(
                                "dependency_count",
                                raw.get("dependencyCount", 0),
                            )
                            or 0
                        ),
                    )
                except Exception:
                    dependency_count = 0
                try:
                    live_count = max(
                        0, int(raw.get("live_count", raw.get("liveCount", 0)) or 0)
                    )
                except Exception:
                    live_count = 0
                legacy_enabled = self._as_bool(raw.get("enabled", True), True)
                site_enabled = self._as_bool(
                    raw.get(
                        "site_enabled",
                        raw.get("siteEnabled", legacy_enabled),
                    ),
                    legacy_enabled,
                )
                live_enabled = self._as_bool(
                    raw.get(
                        "live_enabled",
                        raw.get("liveEnabled", legacy_enabled),
                    ),
                    legacy_enabled,
                )
                health_enabled = self._as_bool(
                    raw.get(
                        "health_enabled",
                        raw.get("healthEnabled", True),
                    ),
                    True,
                )
                normalized.append(
                    {
                        "id": site_id,
                        "name": name,
                        "url": url,
                        "enabled": bool(site_enabled or live_enabled),
                        "site_enabled": bool(site_enabled),
                        "live_enabled": bool(live_enabled),
                        "health_enabled": bool(health_enabled),
                        "source_type": source_type,
                        "site_count": site_count,
                        "dependency_count": dependency_count,
                        "live_count": live_count,
                    }
                )
                seen_names.add(name_key)
                seen_urls.add(url_key)
        if not normalized and default_if_empty:
            default_site = self._default_package_download_site()
            normalized = [default_site] if default_site else []
        return normalized

    def _sync_legacy_package_download_fields(self):
        sites = self.package_download_sites
        if not isinstance(sites, list):
            sites = []
        self.package_download_sites = sites
        if not sites:
            self.package_download_url = self.package_service_url
            self.package_download_enabled = False
            return
        primary = next(
            (
                item
                for item in sites
                if str(item.get("source_type", "")).lower() == "builtin"
            ),
            sites[0],
        )
        self.package_download_url = self.package_service_url or str(
            primary.get("url", self.PACKAGE_DOWNLOAD_URL)
        )
        self.package_download_enabled = self._package_download_site_active(primary)

    def _apply_package_download_options(self, data):
        if not isinstance(data, dict):
            return
        raw_sites = data.get(
            "package_download_sites", data.get("packageDownloadSites")
        )
        service_value = self._package_service_url_option(data)
        if service_value:
            self.package_service_url = service_value
        if isinstance(raw_sites, (list, dict)):
            normalized = self._normalize_package_download_sites(
                raw_sites, default_if_empty=False
            )
            if normalized or isinstance(raw_sites, list):
                self.package_download_sites = normalized
                self._sync_legacy_package_download_fields()
                return
        has_url = "package_download_url" in data or "packageDownloadUrl" in data
        has_enabled = (
            "package_download_enabled" in data
            or "packageDownloadEnabled" in data
        )
        if not (has_url or has_enabled):
            return
        url = self._string_option(
            data,
            ("package_download_url", "packageDownloadUrl"),
            self.package_download_url,
        )
        enabled = self._bool_option(
            data,
            ("package_download_enabled", "packageDownloadEnabled"),
            self.package_download_enabled,
        )
        try:
            url = self._normalize_package_download_url(url)
        except Exception:
            return
        self.package_download_sites = [
            {
                "id": "xiaosa"
                if url == self.PACKAGE_DOWNLOAD_URL
                else self._package_download_site_id("自定义", url),
                "name": self.PACKAGE_DOWNLOAD_NAME
                if url == self.PACKAGE_DOWNLOAD_URL
                else "自定义",
                "url": url,
                "enabled": bool(enabled),
                "site_enabled": bool(enabled),
                "live_enabled": bool(enabled),
                "health_enabled": True,
                "source_type": (
                    "builtin"
                    if self.package_service_url
                    and self._package_download_url_identity(url)
                    == self._package_download_url_identity(self.package_service_url)
                    else "zip"
                ),
                "site_count": 0,
                "dependency_count": 0,
                "live_count": 0,
            }
        ]
        self._sync_legacy_package_download_fields()

    def _load_settings(self):
        path = os.path.abspath(os.path.expanduser(self.settings_path))
        if not os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            if not isinstance(data, dict):
                return
            type_enabled = data.get("type_enabled", data.get("typeEnabled", {}))
            if isinstance(type_enabled, dict):
                for source_type in self.TYPE_ORDER:
                    if source_type in type_enabled:
                        self.type_enabled[source_type] = self._as_bool(
                            type_enabled[source_type], True
                        )
            pending = data.get("pending_type_enabled", data.get("pendingTypeEnabled", {}))
            self.pending_type_enabled = dict(self.type_enabled)
            if isinstance(pending, dict):
                for source_type in self.TYPE_ORDER:
                    if source_type in pending:
                        self.pending_type_enabled[source_type] = self._as_bool(
                            pending[source_type], self.type_enabled[source_type]
                        )
            self.block_adult_sites = self._as_bool(
                data.get("block_adult_sites", data.get("blockAdultSites", False)),
                False,
            )
            self.pending_block_adult_sites = self._as_bool(
                data.get(
                    "pending_block_adult_sites",
                    data.get("pendingBlockAdultSites", self.block_adult_sites),
                ),
                self.block_adult_sites,
            )
            self.config_dirty = any(
                self.pending_type_enabled[source_type] != self.type_enabled[source_type]
                for source_type in self.TYPE_ORDER
            ) or self.pending_block_adult_sites != self.block_adult_sites
            # 「站点功能测活」/「全部重新检测」开关记忆恢复（跨会话）。
            folder_switches = data.get(
                "site_test_folder_switches",
                data.get("siteTestFolderSwitches", {}),
            )
            if isinstance(folder_switches, dict):
                for source_type in self.TYPE_ORDER:
                    if source_type in folder_switches:
                        self._site_test_folder_switches[source_type] = self._as_bool(
                            folder_switches[source_type], True
                        )
            scan_base = data.get("scan_base_path", data.get("scanBasePath", ""))
            if str(scan_base or "").strip():
                self._apply_scan_base_path(str(scan_base))
            # v8.0：恢复网络扫描根配置。
            net_roots = data.get("network_roots", data.get("networkRoots"))
            if isinstance(net_roots, list):
                try:
                    self.network_roots = self._normalize_network_roots(net_roots)
                except Exception as exc:
                    self._warn("网络目录配置恢复失败: {}".format(exc))
            test_results = data.get("site_test_results", data.get("siteTestResults", {}))
            if isinstance(test_results, dict):
                self.site_test_results = {
                    str(identity): result
                    for identity, result in test_results.items()
                    if str(identity).strip() and isinstance(result, dict)
                }
            test_history = data.get(
                "site_test_history", data.get("siteTestHistory", {})
            )
            if isinstance(test_history, dict):
                self.site_test_history = {
                    str(identity): [
                        dict(item)
                        for item in values[-self.SITE_TEST_HISTORY_LIMIT :]
                        if isinstance(item, dict)
                    ]
                    for identity, values in test_history.items()
                    if str(identity).strip() and isinstance(values, list)
                }
            self.source_metadata = self._normalize_source_metadata(
                data.get("source_metadata", data.get("sourceMetadata", {}))
            )
            self._retest_pending = list(dict.fromkeys(
                str(identity).strip()
                for identity in data.get(
                    "retest_pending", data.get("retestPending", [])
                )
                if str(identity).strip()
            )) if isinstance(
                data.get("retest_pending", data.get("retestPending", [])), list
            ) else []
            self._retest_auto_blocked = self._identity_set(
                data.get(
                    "retest_auto_blocked", data.get("retestAutoBlocked", [])
                )
            )
            manual_ignored = data.get(
                "manual_ignored_sources", data.get("manualIgnoredSources")
            )
            auto_blocked = data.get(
                "auto_blocked_sources", data.get("autoBlockedSources")
            )
            self.adult_blocked_sources = self._identity_set(
                data.get("adult_blocked_sources", data.get("adultBlockedSources", []))
            )
            self.adult_allowed_sources = self._identity_set(
                data.get("adult_allowed_sources", data.get("adultAllowedSources", []))
            )
            if isinstance(manual_ignored, list) or isinstance(auto_blocked, list):
                self.manual_ignored_sources = self._identity_set(manual_ignored)
                self.auto_blocked_sources = self._identity_set(auto_blocked)
            else:
                legacy_ignored = self._identity_set(
                    data.get("ignored_sources", data.get("ignoredSources", []))
                )
                # 旧版本没有记录忽略来源，无法可靠区分手动选择和测活屏蔽。
                # 按手动忽略迁移，避免升级后擅自恢复用户明确隐藏的站点。
                self.manual_ignored_sources = legacy_ignored
                self.auto_blocked_sources = set()
            # 受限站点同样保留在自动屏蔽中：屏蔽只能由用户手工恢复，或由
            # 任意一次测活判定为 available 解除，重启不是解除的理由。
            # v6 旧测活曾把单章节媒体失败提升成整站失效。该类结果只有
            # 在已经取得列表和播放候选后才会写入 failure_kind=playback，
            # 升级时可安全恢复站点，并保留播放抽样信息供界面查看。
            for identity in list(self.auto_blocked_sources):
                result = self.site_test_results.get(identity, {})
                if str(result.get("failure_kind", "")) != "playback":
                    continue
                self.auto_blocked_sources.discard(identity)
                result["state"] = "available"
                result["confirmed"] = False
                result["failure_count"] = 0
                result.pop("failure_kind", None)
                detail = str(result.get("detail", "") or "")
                result["detail"] = detail.split("；已确认失效", 1)[0][
                    :240
                ]
            self._sync_ignored_sources()
            self.strict_recognition = self._as_bool(
                data.get("strict_recognition", data.get("strictRecognition", self.strict_recognition)),
                self.strict_recognition,
            )
            self.auto_scan_on_empty = self._as_bool(
                data.get("auto_scan_on_empty", data.get("autoScanOnEmpty", self.auto_scan_on_empty)),
                self.auto_scan_on_empty,
            )
            self.auto_prune_blocked = self._as_bool(
                data.get(
                    "auto_prune_blocked",
                    data.get("autoPruneBlocked", self.auto_prune_blocked),
                ),
                self.auto_prune_blocked,
            )
            self.pruned_sources = self._identity_set(
                data.get("pruned_sources", data.get("prunedSources", []))
            )
            # v7.0：永久加载选择集合。键不存在时保持 None，待首次扫描迁移。
            selected_sources = data.get(
                "selected_sources", data.get("selectedSources")
            )
            if isinstance(selected_sources, list):
                self.selected_identities = self._identity_set(selected_sources)
                self.selection_initialized = self._as_bool(
                    data.get(
                        "selection_initialized",
                        data.get("selectionInitialized", True),
                    ),
                    True,
                )
            # v7.0：临时加载状态跨 spider 实例恢复（App 重建会销毁并
            # 重建实例，临时状态不能只存内存）。仅限同一 App 进程：
            # 进程重启后临时站已随运行态消失，不得复活。
            try:
                temp_owner_pid = int(
                    data.get("temp_owner_pid", data.get("tempOwnerPid", 0)) or 0
                )
            except Exception:
                temp_owner_pid = 0
            current_pid = self._app_process_id()
            if temp_owner_pid and current_pid and temp_owner_pid != current_pid:
                self.temp_identities = set()
                self._temp_home_key = ""
            else:
                self.temp_identities = self._identity_set(
                    data.get("temp_sources", data.get("tempSources", []))
                )
                self._temp_home_key = str(
                    data.get("temp_home_key", data.get("tempHomeKey", "")) or ""
                ).strip()
            # 默壳版：永久注入集合恢复。不受 PID 限制——永久注入站点
            # 在每次 App 启动后都应自动恢复到运行态站点表。
            self.perm_injected_identities = self._identity_set(
                data.get("perm_injected_sources", data.get("permInjectedSources", []))
            )
            self.auto_scan_suspended = self._as_bool(
                data.get("auto_scan_suspended", data.get("autoScanSuspended", False)),
                False,
            )
            self._author_scan_surprise_shown = self._as_bool(
                data.get(
                    "author_scan_surprise_shown",
                    data.get("authorScanSurpriseShown", False),
                ),
                False,
            )
            saved_base_url = str(
                data.get("ok_base_config_url", data.get("okBaseConfigUrl", ""))
                or ""
            ).strip()
            if saved_base_url and not self.ok_base_config_url:
                self.ok_base_config_url = saved_base_url
            self.ok_last_target = str(
                data.get("ok_last_target", data.get("okLastTarget", "")) or ""
            ).strip()
            self._apply_package_download_options(data)
            self._apply_online_repository_options(data, merge=False)
            saved_device_id = str(
                data.get("package_device_id", data.get("packageDeviceId", "")) or ""
            ).strip()
            if re.fullmatch(r"[A-Za-z0-9._:-]{16,128}", saved_device_id):
                self.package_device_id = saved_device_id
            try:
                port = int(data.get("last_app_port", data.get("lastAppPort", 0)) or 0)
                self.last_app_port = port if self.APP_PORT_START <= port <= 65535 else 0
            except Exception:
                self.last_app_port = 0
        except Exception as exc:
            self._warn("扫描设置读取失败，将使用默认配置: {}".format(exc))

    def _identity_set(self, values):
        if not isinstance(values, (list, tuple, set)):
            return set()
        return {
            str(item).strip() for item in values if str(item).strip()
        }

    def _normalize_source_tags(self, values):
        if isinstance(values, str):
            values = re.split(r"[,，;；\n]+", values)
        if not isinstance(values, (list, tuple, set)):
            return []
        result = []
        seen = set()
        for value in values:
            tag = re.sub(r"\s+", " ", str(value or "")).strip()[:24]
            key = tag.casefold()
            if not tag or key in seen:
                continue
            seen.add(key)
            result.append(tag)
            if len(result) >= 8:
                break
        return result

    def _normalize_source_metadata(self, values):
        if not isinstance(values, dict):
            return {}
        result = {}
        for identity, raw in list(values.items())[:3000]:
            clean_identity = str(identity or "").strip()
            if not clean_identity or not isinstance(raw, dict):
                continue
            favorite = self._as_bool(raw.get("favorite", False), False)
            tags = self._normalize_source_tags(raw.get("tags", []))
            if favorite or tags:
                result[clean_identity] = {
                    "favorite": favorite,
                    "tags": tags,
                }
        return result

    def _source_metadata_for(self, source_or_identity):
        identity = (
            str(source_or_identity.get("identity", "")).strip()
            if isinstance(source_or_identity, dict)
            else str(source_or_identity or "").strip()
        )
        value = self.source_metadata.get(identity, {})
        return value if isinstance(value, dict) else {}

    def _set_source_metadata(self, identity, favorite=False, tags=None):
        identity = str(identity or "").strip()
        if not identity:
            raise ValueError("站点稳定标识为空")
        clean = {
            "favorite": bool(favorite),
            "tags": self._normalize_source_tags(tags or []),
        }
        if clean["favorite"] or clean["tags"]:
            self.source_metadata[identity] = clean
        else:
            self.source_metadata.pop(identity, None)
        self._save_settings()
        return clean

    def _management_profile_path(self):
        return os.path.join(
            os.path.dirname(os.path.abspath(os.path.expanduser(self.settings_path))),
            "local-media-profile.json",
        )

    def _management_profile_data(self):
        return {
            "format": "local-media-profile/v1",
            "exportedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
            "scan_base_path": self.scan_base_path,
            "type_enabled": {
                source_type: bool(self.type_enabled.get(source_type, True))
                for source_type in self.TYPE_ORDER
            },
            "block_adult_sites": bool(self.block_adult_sites),
            "manual_ignored_sources": sorted(self.manual_ignored_sources),
            "adult_allowed_sources": sorted(self.adult_allowed_sources),
            "source_metadata": self._normalize_source_metadata(
                self.source_metadata
            ),
            "package_download_states": [
                {
                    "id": str(item.get("id", "")),
                    "name": str(item.get("name", "")),
                    "site_enabled": self._package_download_site_enabled(item),
                    "live_enabled": self._package_download_live_enabled(item),
                    "health_enabled": self._package_download_health_enabled(item),
                }
                for item in self.package_download_sites
                if str(item.get("id", "")).strip()
            ],
            "online_repositories": [
                {
                    "name": str(item.get("name", "")),
                    "url": str(item.get("url", "")),
                    "enabled": self._as_bool(item.get("enabled", True), True),
                }
                for item in self.online_repositories
            ],
        }

    def _export_management_profile(self, path=None):
        target = os.path.abspath(
            os.path.expanduser(path or self._management_profile_path())
        )
        self._atomic_write_plain_json(target, self._management_profile_data())
        return target

    def _import_management_profile(self, path=None):
        source = os.path.abspath(
            os.path.expanduser(path or self._management_profile_path())
        )
        with open(source, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        if not isinstance(data, dict) or data.get("format") != "local-media-profile/v1":
            raise ValueError("管理配置格式不受支持")
        type_enabled = data.get("type_enabled", {})
        if not isinstance(type_enabled, dict):
            raise ValueError("类型开关格式错误")
        manual_ignored = data.get("manual_ignored_sources", [])
        adult_allowed = data.get("adult_allowed_sources", [])
        metadata = data.get("source_metadata", {})
        states = data.get("package_download_states", [])
        repositories = data.get("online_repositories")
        if not isinstance(manual_ignored, list):
            raise ValueError("手工屏蔽列表格式错误")
        if not isinstance(adult_allowed, list):
            raise ValueError("18+ 放行列表格式错误")
        if not isinstance(metadata, dict):
            raise ValueError("收藏与标签格式错误")
        if states is not None and not isinstance(states, list):
            raise ValueError("接口开关格式错误")
        if repositories is not None and not isinstance(repositories, list):
            raise ValueError("在线仓库格式错误")
        next_types = dict(self.type_enabled)
        for source_type in self.TYPE_ORDER:
            if source_type in type_enabled:
                next_types[source_type] = self._as_bool(
                    type_enabled[source_type], next_types[source_type]
                )
        next_metadata = self._normalize_source_metadata(metadata)
        state_map = {
            str(item.get("id", "")).strip(): item
            for item in states or []
            if isinstance(item, dict) and str(item.get("id", "")).strip()
        }
        next_sites = copy.deepcopy(self.package_download_sites)
        for item in next_sites:
            state = state_map.get(str(item.get("id", "")).strip())
            if state is None:
                continue
            item["site_enabled"] = self._as_bool(
                state.get("site_enabled", item.get("site_enabled", True)),
                True,
            )
            item["live_enabled"] = self._as_bool(
                state.get("live_enabled", item.get("live_enabled", True)),
                True,
            )
            item["health_enabled"] = self._as_bool(
                state.get("health_enabled", item.get("health_enabled", True)),
                True,
            )
            item["enabled"] = bool(
                item["site_enabled"] or item["live_enabled"]
            )
        next_repositories = (
            copy.deepcopy(self.online_repositories)
            if repositories is None
            else self._normalize_online_repositories(repositories)
        )
        backup = os.path.join(
            os.path.dirname(os.path.abspath(os.path.expanduser(self.settings_path))),
            "导入前备份.json",
        )
        settings_path = os.path.abspath(os.path.expanduser(self.settings_path))
        if os.path.isfile(settings_path):
            with open(settings_path, "r", encoding="utf-8") as fp:
                current = json.load(fp)
            self._atomic_write_plain_json(backup, current)
        previous = {
            "type_enabled": dict(self.type_enabled),
            "pending_type_enabled": dict(self.pending_type_enabled),
            "block_adult_sites": self.block_adult_sites,
            "pending_block_adult_sites": self.pending_block_adult_sites,
            "config_dirty": self.config_dirty,
            "manual_ignored_sources": set(self.manual_ignored_sources),
            "adult_allowed_sources": set(self.adult_allowed_sources),
            "source_metadata": copy.deepcopy(self.source_metadata),
            "package_download_sites": copy.deepcopy(self.package_download_sites),
            "online_repositories": copy.deepcopy(self.online_repositories),
            "scan_base_path": self.scan_base_path,
        }
        try:
            self.type_enabled = next_types
            self.pending_type_enabled = dict(next_types)
            self.block_adult_sites = self._as_bool(
                data.get("block_adult_sites", self.block_adult_sites),
                self.block_adult_sites,
            )
            self.pending_block_adult_sites = self.block_adult_sites
            self.config_dirty = False
            self.manual_ignored_sources = self._identity_set(manual_ignored)
            self.adult_allowed_sources = self._identity_set(adult_allowed)
            self.source_metadata = next_metadata
            self.package_download_sites = next_sites
            self.online_repositories = next_repositories
            self._apply_scan_base_path(
                str(data.get("scan_base_path", "") or "").strip()
            )
            self._sync_ignored_sources()
            self._save_settings()
        except Exception:
            self.type_enabled = previous["type_enabled"]
            self.pending_type_enabled = previous["pending_type_enabled"]
            self.block_adult_sites = previous["block_adult_sites"]
            self.pending_block_adult_sites = previous["pending_block_adult_sites"]
            self.config_dirty = previous["config_dirty"]
            self.manual_ignored_sources = previous["manual_ignored_sources"]
            self.adult_allowed_sources = previous["adult_allowed_sources"]
            self.source_metadata = previous["source_metadata"]
            self.package_download_sites = previous["package_download_sites"]
            self.online_repositories = previous["online_repositories"]
            self._apply_scan_base_path(previous["scan_base_path"])
            self._sync_ignored_sources()
            raise
        return source, backup if os.path.isfile(backup) else ""

    def _sync_ignored_sources(self):
        self.ignored_sources = set(self.manual_ignored_sources)
        self.ignored_sources.update(self.auto_blocked_sources)
        if not self.block_adult_sites:
            self.ignored_sources.update(self.adult_blocked_sources)

    def _prune_blocked_sources_locked(self):
        """把测活屏蔽的站点移出配置，返回本次新增移除的数量。

        只处理 auto_blocked_sources：手工屏蔽属于用户的明确决策，被自动
        逻辑接管后用户将无法区分「我屏蔽的」和「系统清理的」。

        不删除任何源文件。整包类型多个站点共用同一个 api.json，删文件会
        因一个站点失效而波及整包；且用户目录里有手工放置的 PY/JS。移除
        仅作用于扫描阶段，清除入口可让其重新参与扫描。
        """
        if not self.auto_prune_blocked:
            return 0
        candidates = {
            identity
            for identity in self.auto_blocked_sources
            if identity and identity not in self.pruned_sources
        }
        if not candidates:
            return 0

        names = []
        for identity in candidates:
            source = next(
                (
                    item
                    for item in self.cache.get("ignored", [])
                    if item.get("identity") == identity
                ),
                None,
            )
            names.append(str((source or {}).get("name", "") or identity)[:60])

        self.pruned_sources.update(candidates)
        self.auto_blocked_sources.difference_update(candidates)
        self._sync_ignored_sources()
        self._log(
            "INFO",
            "自动清理屏蔽站点 {} 个（仅移出配置，源文件保留）: {}".format(
                len(candidates), "、".join(sorted(names)[:8])
            ),
        )
        return len(candidates)

    def _as_bool(self, value, fallback=False):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if value is None:
            return fallback
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    def _save_settings(self):
        path = os.path.abspath(os.path.expanduser(self.settings_path))
        self._sync_legacy_package_download_fields()
        data = {
            "type_enabled": {
                source_type: bool(self.type_enabled.get(source_type, True))
                for source_type in self.TYPE_ORDER
            },
            "pending_type_enabled": {
                source_type: bool(
                    self.pending_type_enabled.get(
                        source_type, self.type_enabled.get(source_type, True)
                    )
                )
                for source_type in self.TYPE_ORDER
            },
            "block_adult_sites": bool(self.block_adult_sites),
            "pending_block_adult_sites": bool(
                self.pending_block_adult_sites
            ),
            "strict_recognition": bool(self.strict_recognition),
            "auto_scan_on_empty": bool(self.auto_scan_on_empty),
            "auto_prune_blocked": bool(self.auto_prune_blocked),
            "pruned_sources": sorted(self.pruned_sources),
            "selected_sources": (
                sorted(self.selected_identities)
                if self.selected_identities is not None
                else []
            ),
            # 临时加载状态跨 spider 实例恢复：App 重建站点表会销毁并
            # 重建实例，仅存内存会丢失。按进程 PID 归属，进程重启后
            # 临时站本已随运行态消失，不得从配置复活。
            "temp_sources": sorted(self.temp_identities),
            "temp_home_key": str(self._temp_home_key or ""),
            "temp_owner_pid": int(self._app_process_id()),
            "perm_injected_sources": sorted(self.perm_injected_identities),
            "selection_initialized": bool(self.selection_initialized),
            "auto_scan_suspended": bool(self.auto_scan_suspended),
            "scan_base_path": self.scan_base_path,
            "ignored_sources": sorted(self.ignored_sources),
            "manual_ignored_sources": sorted(self.manual_ignored_sources),
            "auto_blocked_sources": sorted(self.auto_blocked_sources),
            "adult_blocked_sources": sorted(self.adult_blocked_sources),
            "adult_allowed_sources": sorted(self.adult_allowed_sources),
            "site_test_results": self.site_test_results,
            "site_test_history": self.site_test_history,
            "source_metadata": self.source_metadata,
            "retest_pending": list(self._retest_pending),
            "retest_auto_blocked": sorted(self._retest_auto_blocked),
            "last_app_port": int(self.last_app_port or 0),
            "ok_base_config_url": self.ok_base_config_url,
            "ok_last_target": self.ok_last_target,
            "package_download_sites": [
                {
                    "id": str(item.get("id", "")),
                    "name": str(item.get("name", "")),
                    "url": str(item.get("url", "")),
                    "enabled": self._package_download_site_active(item),
                    "site_enabled": self._package_download_site_enabled(item),
                    "live_enabled": self._package_download_live_enabled(item),
                    "health_enabled": self._package_download_health_enabled(item),
                    "source_type": str(item.get("source_type", "zip")),
                    "site_count": max(0, int(item.get("site_count", 0) or 0)),
                    "dependency_count": max(
                        0, int(item.get("dependency_count", 0) or 0)
                    ),
                    "live_count": max(0, int(item.get("live_count", 0) or 0)),
                }
                for item in self.package_download_sites
            ],
            "package_service_url": self.package_service_url,
            "package_download_url": self.package_download_url,
            "package_download_enabled": bool(self.package_download_enabled),
            "online_repositories": [
                {
                    "id": str(item.get("id", "")),
                    "name": str(item.get("name", "")),
                    "url": str(item.get("url", "")),
                    "enabled": self._as_bool(item.get("enabled", True), True),
                    "version": str(item.get("version", "")),
                    "manifest_digest": str(item.get("manifest_digest", "")),
                    "file_count": max(0, int(item.get("file_count", 0) or 0)),
                    "last_sync": str(item.get("last_sync", "")),
                    "last_status": str(item.get("last_status", "")),
                    "last_message": str(item.get("last_message", ""))[:240],
                }
                for item in self.online_repositories
            ],
            "package_device_id": self.package_device_id,
            "author_scan_surprise_shown": bool(
                self._author_scan_surprise_shown
            ),
            "site_test_folder_switches": {
                source_type: bool(
                    self._site_test_folder_switches.get(source_type, True)
                )
                for source_type in self.TYPE_ORDER
            },
            # v8.0：网络扫描根（含凭据，仅落在本机配置文件中）。
            "network_roots": [
                {
                    "id": str(item.get("id", "")),
                    "name": str(item.get("name", "")),
                    "url": str(item.get("url", "")),
                    "protocol": str(item.get("protocol", "auto")),
                    "username": str(item.get("username", "")),
                    "password": str(item.get("password", "")),
                    "token": str(item.get("token", "")),
                    "enabled": self._as_bool(item.get("enabled", True), True),
                    "last_sync": str(item.get("last_sync", "")),
                    "last_status": str(item.get("last_status", "")),
                    "last_message": str(item.get("last_message", ""))[:240],
                    "file_count": max(0, int(item.get("file_count", 0) or 0)),
                    "byte_count": max(0, int(item.get("byte_count", 0) or 0)),
                }
                for item in self.network_roots
            ],
        }
        self._atomic_write_plain_json(path, data)

    def _normalize_scan_base_path(self, value):
        path = str(value or "").strip().strip('"').strip("'")
        if path.lower().startswith("file://"):
            path = path[7:]
        if not path:
            return ""
        path = os.path.expanduser(path)
        if not os.path.isabs(path):
            path = os.path.join(self.STORAGE_ROOT, path.lstrip("/"))
        return os.path.realpath(os.path.abspath(path))

    # ======================================================================
    # v8.0 网络扫描根 —— 配置与本地展开
    # 路线 B：网络根只负责把远程目录镜像到本地缓存目录，之后所有扫描/识别/
    # 注入/浏览逻辑看到的都是普通本地文件，现有链路零改动。
    # ======================================================================
    def _normalize_network_roots(self, values):
        """归一化网络根配置；非法 URL/缺 id 的条目直接丢弃。"""
        if not isinstance(values, list):
            return []
        normalized = []
        seen_ids = set()
        for raw in values:
            if not isinstance(raw, dict):
                continue
            url = self._network_normalize_url(raw.get("url", ""))
            root_id = str(raw.get("id", "")).strip()
            if not root_id:
                root_id = self._network_root_id(url)
            if not url or root_id in seen_ids:
                continue
            seen_ids.add(root_id)
            protocol = str(raw.get("protocol", "auto") or "auto").strip().lower()
            if protocol not in self.NETWORK_PROTOCOLS:
                protocol = "auto"
            name = str(raw.get("name", "")).strip()
            if not name:
                name = self._network_default_name(url, protocol)
            normalized.append(
                {
                    "id": root_id,
                    "name": name[:40],
                    "url": url,
                    "protocol": protocol,
                    "username": str(raw.get("username", "") or "").strip()[:128],
                    "password": str(raw.get("password", "") or "")[:256],
                    "token": str(raw.get("token", "") or "")[:256],
                    "enabled": self._as_bool(raw.get("enabled", True), True),
                    "last_sync": str(raw.get("last_sync", "") or ""),
                    "last_status": str(raw.get("last_status", "") or "")[:32],
                    "last_message": str(raw.get("last_message", "") or "")[:240],
                    "file_count": max(0, int(raw.get("file_count", 0) or 0)),
                    "byte_count": max(0, int(raw.get("byte_count", 0) or 0)),
                }
            )
        return normalized

    @staticmethod
    def _network_normalize_url(value):
        url = str(value or "").strip().strip('"').strip("'")
        if not url:
            return ""
        if "://" not in url:
            url = "http://" + url
        try:
            parsed = urllib.parse.urlsplit(url)
        except Exception:
            return ""
        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https") or not parsed.netloc:
            return ""
        return url

    def _network_root_id(self, url):
        return "net_" + self._digest(str(url or ""), 16)

    def _network_default_name(self, url, protocol):
        try:
            parsed = urllib.parse.urlsplit(url)
            parts = [seg for seg in parsed.path.split("/") if seg]
            base = urllib.parse.unquote(parts[-1] if parts else parsed.netloc)
            return "{}（{}）".format(base[:24], protocol)
        except Exception:
            return "网络目录（{}）".format(protocol)

    def _network_root_by_id(self, root_id):
        root_id = str(root_id or "")
        for item in self.network_roots:
            if item.get("id") == root_id:
                return item
        return None

    def _network_root_cache_dir(self, root):
        root_id = str((root or {}).get("id", "") or "")
        if not root_id:
            root_id = self._network_root_id((root or {}).get("url", ""))
        return os.path.join(
            os.path.abspath(os.path.expanduser(self.network_root_cache_dir)),
            root_id,
        )

    def _network_root_specs(self):
        """把已镜像到本地的网络根展开成普通扫描 spec。

        未同步过（缓存目录不存在）的根不产出 spec；协议适配与下载只在
        显式「扫描 / 立即同步」时发生，进入页面等自动扫描不会发网络请求。
        """
        specs = []
        for root in self.network_roots:
            if not root.get("enabled", True):
                continue
            cache_dir = self._network_root_cache_dir(root)
            if not os.path.isdir(cache_dir):
                continue
            try:
                derived = self._scan_roots_for_base(cache_dir)
            except Exception as exc:
                self._warn("网络目录展开失败: {} ({})".format(root.get("name"), exc))
                continue
            for spec in derived:
                spec = dict(spec)
                spec["network"] = True
                spec["network_root_id"] = root.get("id", "")
                specs.append(spec)
        return specs

    def _effective_scan_roots(self):
        """本地扫描根 + 网络根镜像目录，顺序固定本地优先。"""
        return list(self.scan_roots) + self._network_root_specs()

    def _network_root_display_map(self):
        """浏览器根真实路径 -> 显示名（网络根加 🌐 前缀便于辨认）。"""
        mapping = {}
        for root in self.network_roots:
            if not root.get("enabled", True):
                continue
            cache_dir = self._network_root_cache_dir(root)
            if not os.path.isdir(cache_dir):
                continue
            try:
                for spec in self._scan_roots_for_base(cache_dir):
                    real_path = os.path.realpath(
                        os.path.abspath(os.path.expanduser(str(spec.get("path", ""))))
                    )
                    mapping[os.path.normcase(real_path)] = "🌐 {}".format(
                        root.get("name", "网络目录")
                    )
            except Exception:
                continue
        return mapping

    # ------------------------------------------------------------------
    # HTTP 基础层
    # ------------------------------------------------------------------
    @staticmethod
    def _network_quote_url(url):
        """对 URL 的 path 做百分号编码（中文路径），保留已编码字符与查询串。"""
        try:
            parsed = urllib.parse.urlsplit(url)
            quoted_path = urllib.parse.quote(
                urllib.parse.unquote(parsed.path),
                safe="/%:@!$&'()*+,;=-._~",
            )
            return urllib.parse.urlunsplit(
                (
                    parsed.scheme,
                    parsed.netloc,
                    quoted_path,
                    parsed.query,
                    parsed.fragment,
                )
            )
        except Exception:
            return url

    @staticmethod
    def _network_decode_body(body, content_type="", prefer="utf-8"):
        encodings = []
        ct = str(content_type or "").lower()
        match = re.search(r"charset=([a-zA-Z0-9_\-]+)", ct)
        if match:
            encodings.append(match.group(1))
        encodings.extend([prefer, "utf-8", "gb18030", "latin-1"])
        for encoding in encodings:
            try:
                return body.decode(encoding)
            except Exception:
                continue
        return body.decode("utf-8", errors="replace")

    def _network_auth(self, root):
        return {
            "username": str(root.get("username", "") or ""),
            "password": str(root.get("password", "") or "")
            or str(root.get("token", "") or ""),
            "token": str(root.get("token", "") or ""),
        }

    def _network_http_request(
        self,
        url,
        method="GET",
        headers=None,
        data=None,
        auth=None,
        timeout=None,
        digest_retry=True,
    ):
        """统一 HTTP 调用。返回 (status, headers(dict), body(bytes), final_url)。

        - 默认禁代理（局域网分享常见，系统代理会拦截 192.168.* 请求）。
        - 带凭据时先主动发 Basic；401 后再用 Digest opener 重试一次。
        """
        auth = auth or {}
        timeout = max(2.0, float(timeout or self.NETWORK_TIMEOUT))
        request_headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android) LocalMediaHub/8",
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
        if headers:
            request_headers.update({str(k): str(v) for k, v in headers.items()})
        username = str(auth.get("username", "") or "")
        password = str(auth.get("password", "") or "")
        token = str(auth.get("token", "") or "")
        if token and "Authorization" not in request_headers:
            request_headers["Authorization"] = "Bearer {}".format(token)
        if username and "Authorization" not in request_headers:
            request_headers["Authorization"] = "Basic " + base64.b64encode(
                "{}:{}".format(username, password).encode("utf-8")
            ).decode("ascii")
        quoted = self._network_quote_url(url)
        request = urllib.request.Request(
            quoted,
            data=data,
            headers=request_headers,
            method=str(method or "GET").upper(),
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=timeout) as response:
                status = int(getattr(response, "status", response.getcode()) or 0)
                body = response.read()
                final_url = str(response.geturl() or quoted)
                headers_out = {
                    str(k).lower(): str(v)
                    for k, v in (response.headers.items() if response.headers else [])
                }
                return status, headers_out, body, final_url
        except urllib.error.HTTPError as exc:
            if (
                digest_retry
                and int(exc.code or 0) == 401
                and username
            ):
                return self._network_http_digest(
                    quoted,
                    method,
                    dict(request_headers),
                    data,
                    username,
                    password,
                    timeout,
                )
            raise ValueError("HTTP {}".format(exc.code))
        except urllib.error.URLError as exc:
            raise ValueError("网络请求失败: {}".format(exc.reason))
        except socket.timeout:
            raise ValueError("请求超时")
        except TimeoutError:
            raise ValueError("请求超时")

    def _network_http_digest(
        self, url, method, headers, data, username, password, timeout
    ):
        # 401 后用标准库 Digest/Basic password manager 再试一次。
        headers = {
            k: v for k, v in (headers or {}).items() if k != "Authorization"
        }
        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        try:
            parsed = urllib.parse.urlsplit(url)
            top = "{}://{}".format(parsed.scheme, parsed.netloc)
        except Exception:
            top = url
        password_mgr.add_password(None, top, username, password)
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPBasicAuthHandler(password_mgr),
            urllib.request.HTTPDigestAuthHandler(password_mgr),
        )
        request = urllib.request.Request(
            url, data=data, headers=headers, method=str(method or "GET").upper()
        )
        try:
            with opener.open(request, timeout=timeout) as response:
                status = int(getattr(response, "status", response.getcode()) or 0)
                body = response.read()
                final_url = str(response.geturl() or url)
                headers_out = {
                    str(k).lower(): str(v)
                    for k, v in (response.headers.items() if response.headers else [])
                }
                return status, headers_out, body, final_url
        except urllib.error.HTTPError as exc:
            raise ValueError("认证失败 HTTP {}".format(exc.code))
        except urllib.error.URLError as exc:
            raise ValueError("认证请求失败: {}".format(exc.reason))
        except (socket.timeout, TimeoutError):
            raise ValueError("请求超时")

    # ------------------------------------------------------------------
    # 协议识别
    # ------------------------------------------------------------------
    def _network_git_host(self, url):
        """github/gitee 返回 (api_base, raw_template, token_query, label)。"""
        host = str(urllib.parse.urlsplit(url).netloc or "").lower()
        if host == "github.com" or host.endswith(".github.com"):
            return (
                "https://api.github.com",
                "https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}",
                False,
                "github",
            )
        if host == "gitee.com" or host.endswith(".gitee.com"):
            return (
                "https://gitee.com/api/v5",
                "https://gitee.com/{owner}/{repo}/raw/{branch}/{path}",
                True,
                "gitee",
            )
        return None

    # ------------------------------------------------------------------
    # GitHub 加速站回退（直连 -> 公益镜像依次尝试，成功线路会话内粘滞）
    # ------------------------------------------------------------------
    def _network_github_ordered_bases(self, url):
        """返回 [(base, final_url)]；base 为 "" 表示直连。"""
        bases = [""] + [str(item).rstrip("/") for item in self.NETWORK_GITHUB_MIRRORS]
        sticky = self._github_fast_base
        if sticky is not None and sticky in bases:
            bases = [sticky] + [item for item in bases if item != sticky]
        return [
            (base, url if not base else "{}/{}".format(base, url))
            for base in bases
        ]

    def _network_github_fast_request(
        self, url, root, headers=None, method="GET", data=None
    ):
        """GitHub 专用 GET：直连失败自动换加速站。

        - 公开库：直连 → 各加速站依次尝试，首个成功线路记为粘滞线路；
        - 配置了 Token（私有库）：只走直连，绝不把凭据/私有 URL 交给第三方代理；
        - 404/401/400 属于资源或权限问题，换站无意义，直接返回。
        """
        auth = self._network_auth(root)
        token = str(auth.get("token", "") or auth.get("password", "") or "")
        request_headers = {str(k): str(v) for k, v in (headers or {}).items()}
        if token:
            request_headers.setdefault("Authorization", "Bearer {}".format(token))
            candidates = [("", url)]
        else:
            candidates = self._network_github_ordered_bases(url)
        last_error = None
        for base, final_url in candidates:
            try:
                status, resp_headers, body, final = self._network_http_request(
                    final_url,
                    method=method,
                    headers=request_headers,
                    data=data,
                    auth=None,
                )
                self._github_fast_base = base
                return status, resp_headers, body, final
            except Exception as exc:
                # 底层 HTTP 层对非 2xx 统一抛 ValueError("HTTP 状态码")。
                code_match = re.match(r"^HTTP\s+(\d{3})$", str(exc).strip())
                code = int(code_match.group(1)) if code_match else 0
                if code in (400, 401, 404):
                    # 资源不存在/凭据无效：换加速站也是同样结果，直接终止。
                    raise
                # 网络失败 / 超时 / 403 限流 / 429 / 5xx / 202：换下一候选线路。
                last_error = exc
                if self._github_fast_base == base:
                    self._github_fast_base = None
                continue
        raise last_error or ValueError("GitHub 直连与加速站均不可用")

    def _network_resolve_protocol(self, root):
        """返回实际协议名；显式指定优先，auto 先认 Git 站点再探 WebDAV。"""
        url = str(root.get("url", "") or "")
        configured = str(root.get("protocol", "auto") or "auto").strip().lower()
        if configured in ("github", "gitee"):
            if not self._network_git_host(url):
                raise ValueError("地址不是 {} 仓库链接".format(
                    "GitHub" if configured == "github" else "Gitee"
                ))
            return configured
        if configured in ("http", "webdav"):
            return configured
        if self._network_git_host(url):
            return self._network_git_host(url)[3]
        # WebDAV 探测：Depth:0 PROPFIND，207 即视为 WebDAV。
        auth = self._network_auth(root)
        body = (
            b'<?xml version="1.0" encoding="utf-8"?>'
            b'<D:propfind xmlns:D="DAV:"><D:allprop/></D:propfind>'
        )
        try:
            status, _headers, _text, _final = self._network_http_request(
                self._network_collection_url(url),
                method="PROPFIND",
                headers={"Depth": "0", "Content-Type": "application/xml; charset=utf-8"},
                data=body,
                auth=auth,
                timeout=self.NETWORK_CONNECT_TIMEOUT,
            )
            if status == 207:
                return "webdav"
        except Exception:
            pass
        return "http"

    @staticmethod
    def _network_collection_url(url):
        """目录集合 URL 约定以 / 结尾。"""
        parsed = urllib.parse.urlsplit(url)
        path = parsed.path or "/"
        if not path.endswith("/"):
            path = path + "/"
        return urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, path, parsed.query, "")
        )

    # ------------------------------------------------------------------
    # 协议适配：列目录树
    # entry 统一结构：{rel, url, size, mtime, etag, is_dir}
    # ------------------------------------------------------------------
    def _network_safe_rel(self, rel):
        """远程相对路径转本地安全相对路径（POSIX 风格）；不安全返回 None。"""
        rel = str(rel or "").replace("\\", "/").strip()
        rel = urllib.parse.unquote(rel)
        if not rel or rel.startswith("/") or ":" in rel:
            return None
        parts = []
        for part in rel.split("/"):
            part = part.strip()
            if not part or part in (".", ".."):
                if part == "..":
                    return None
                continue
            if part in (os.sep, "/") or part.startswith("."):
                # 隐藏文件（含本镜像自己的标记文件）不参与镜像。
                return None
            parts.append(part)
        return "/".join(parts) if parts else None

    def _network_list_tree(self, root, protocol):
        if protocol in ("github", "gitee"):
            return self._network_list_git(root, protocol)
        if protocol == "webdav":
            return self._network_list_webdav(root)
        return self._network_list_http(root)

    def _network_list_http(self, root):
        """HTTP 静态目录索引（nginx/apache/python http.server/IIS autoindex）。"""
        from html.parser import HTMLParser

        auth = self._network_auth(root)

        class AnchorCollector(HTMLParser):
            def __init__(self):
                super().__init__()
                self.links = []
                self.base = ""
                self._in_a = False
                self._href = None
                self._text = []

            def handle_starttag(self, tag, attrs):
                tag = tag.lower()
                if tag == "base":
                    self.base = str(dict(attrs).get("href", "") or "")
                elif tag == "a":
                    href = dict(attrs).get("href")
                    if href is not None:
                        self._in_a = True
                        self._href = str(href)
                        self._text = []

            def handle_data(self, data):
                if self._in_a:
                    self._text.append(data)

            def handle_endtag(self, tag):
                if tag.lower() == "a" and self._in_a:
                    self.links.append((self._href, "".join(self._text).strip()))
                    self._in_a = False

        root_url = self._network_collection_url(root["url"])
        root_parsed = urllib.parse.urlsplit(root_url)
        root_host = root_parsed.netloc.lower()
        root_path = urllib.parse.unquote(root_parsed.path)
        entries = []
        visited = set()
        queue = [root_url]
        seen_rels = set()
        max_dirs = 3000
        while queue:
            if len(visited) >= max_dirs:
                raise ValueError("远程目录层级过多（>{}），已中止".format(max_dirs))
            index_url = queue.pop(0)
            if index_url in visited:
                continue
            visited.add(index_url)
            status, headers, body, _final = self._network_http_request(
                index_url, auth=auth
            )
            if status != 200:
                raise ValueError("目录列表请求失败 HTTP {}：{}".format(status, index_url))
            html = self._network_decode_body(
                body, headers.get("content-type", "")
            )
            collector = AnchorCollector()
            collector.feed(html)
            base_url = (
                urllib.parse.urljoin(index_url, collector.base)
                if collector.base
                else index_url
            )
            for href, text in collector.links:
                lower_href = str(href or "").lower().strip()
                if not lower_href or lower_href.startswith(
                    ("#", "javascript:", "mailto:", "tel:", "data:")
                ):
                    continue
                abs_url = urllib.parse.urljoin(base_url, href)
                abs_url = urllib.parse.urldefrag(abs_url)[0]
                try:
                    parsed = urllib.parse.urlsplit(abs_url)
                except Exception:
                    continue
                if parsed.scheme.lower() not in ("http", "https"):
                    continue
                if parsed.netloc.lower() != root_host:
                    continue
                decoded_path = urllib.parse.unquote(parsed.path)
                if decoded_path == root_path and parsed.query:
                    # 排序/翻页链接（?C=N;O=D）等。
                    continue
                is_dir = (
                    decoded_path.endswith("/")
                    or str(href).rstrip().endswith("/")
                    or str(text).rstrip().endswith("/")
                )
                if is_dir:
                    if not (decoded_path.rstrip("/") + "/").startswith(root_path):
                        continue
                    child_url = self._network_collection_url(
                        urllib.parse.urlunsplit(
                            (parsed.scheme, parsed.netloc, parsed.path, "", "")
                        )
                    )
                    if child_url == index_url or child_url in visited:
                        continue
                    rel = self._network_safe_rel(
                        urllib.parse.unquote(
                            child_url[
                                len(
                                    urllib.parse.urlunsplit(
                                        (
                                            root_parsed.scheme,
                                            root_parsed.netloc,
                                            root_parsed.path,
                                            "",
                                            "",
                                        )
                                    )
                                ) :
                            ]
                        )
                    )
                    if rel and rel.count("/") + 1 < self.NETWORK_MAX_DEPTH:
                        queue.append(child_url)
                    continue
                if not decoded_path.startswith(root_path):
                    continue
                raw_rel = urllib.parse.unquote(decoded_path[len(root_path):])
                rel = self._network_safe_rel(raw_rel)
                if not rel or rel in seen_rels:
                    continue
                if rel.count("/") + 1 > self.NETWORK_MAX_DEPTH:
                    continue
                seen_rels.add(rel)
                entries.append(
                    {
                        "rel": rel,
                        "url": urllib.parse.urlunsplit(
                            (
                                parsed.scheme,
                                parsed.netloc,
                                parsed.path,
                                parsed.query,
                                "",
                            )
                        ),
                        "size": 0,
                        "mtime": "",
                        "etag": "",
                        "is_dir": False,
                    }
                )
        return entries

    @staticmethod
    def _webdav_localname(tag):
        return str(tag or "").split("}", 1)[-1].lower()

    def _network_list_webdav(self, root):
        auth = self._network_auth(root)
        root_url = self._network_collection_url(root["url"])
        root_parsed = urllib.parse.urlsplit(root_url)
        root_path = urllib.parse.unquote(root_parsed.path)
        body = (
            b'<?xml version="1.0" encoding="utf-8"?>'
            b'<D:propfind xmlns:D="DAV:"><D:allprop/></D:propfind>'
        )

        def propfind(url, depth):
            status, headers, data, _final = self._network_http_request(
                url,
                method="PROPFIND",
                headers={
                    "Depth": str(depth),
                    "Content-Type": "application/xml; charset=utf-8",
                },
                data=body,
                auth=auth,
            )
            if status != 207:
                raise ValueError("WebDAV PROPFIND 失败 HTTP {}".format(status))
            return data

        def parse_multistatus(data, request_url):
            import xml.etree.ElementTree as ET

            rows = []
            try:
                xml_root = ET.fromstring(data)
            except Exception as exc:
                raise ValueError("WebDAV 响应解析失败: {}".format(exc))
            for node in xml_root.iter():
                if self._webdav_localname(node.tag) != "response":
                    continue
                href = ""
                size = 0
                modified = ""
                etag = ""
                is_dir = False
                has_status_ok = True
                for child in node.iter():
                    name = self._webdav_localname(child.tag)
                    text = (child.text or "").strip() if child.text else ""
                    if name == "href" and text and not href:
                        href = text
                    elif name == "getcontentlength" and text:
                        try:
                            size = int(text)
                        except Exception:
                            size = 0
                    elif name == "getlastmodified" and text:
                        modified = text
                    elif name == "getetag" and text:
                        etag = text
                    elif name == "collection":
                        is_dir = True
                    elif name == "status" and text:
                        has_status_ok = "200" in text or "207" in text
                if not href or not has_status_ok:
                    continue
                abs_url = urllib.parse.urljoin(request_url, href)
                parsed = urllib.parse.urlsplit(abs_url)
                decoded_path = urllib.parse.unquote(parsed.path)
                if not decoded_path.endswith("/") and is_dir:
                    abs_url = self._network_collection_url(abs_url)
                    parsed = urllib.parse.urlsplit(abs_url)
                    decoded_path = urllib.parse.unquote(parsed.path)
                rows.append(
                    {
                        "url": urllib.parse.urlunsplit(
                            (
                                parsed.scheme,
                                parsed.netloc,
                                parsed.path,
                                parsed.query,
                                "",
                            )
                        ),
                        "path": decoded_path,
                        "size": size,
                        "mtime": modified,
                        "etag": etag,
                        "is_dir": is_dir,
                    }
                )
            return rows

        entries = []
        seen_rels = set()

        def absorb(rows, include_self_dirs):
            for row in rows:
                path = row["path"]
                if not (path.rstrip("/") + "/").startswith(root_path):
                    continue
                if path.rstrip("/") + "/" == root_path:
                    continue
                raw_rel = path[len(root_path):]
                rel = self._network_safe_rel(raw_rel)
                if not rel or rel in seen_rels:
                    continue
                depth = rel.count("/") + 1
                if row["is_dir"]:
                    if depth < self.NETWORK_MAX_DEPTH and include_self_dirs:
                        seen_rels.add(rel)
                    continue
                if depth > self.NETWORK_MAX_DEPTH:
                    continue
                seen_rels.add(rel)
                entries.append(
                    {
                        "rel": rel,
                        "url": row["url"],
                        "size": row["size"],
                        "mtime": row["mtime"],
                        "etag": row["etag"],
                        "is_dir": False,
                    }
                )

        # 先尝试 Depth: infinity（一次取整棵树）。
        infinite_ok = False
        try:
            rows = parse_multistatus(propfind(root_url, "infinity"), root_url)
            if len(rows) > 1:
                absorb(rows, True)
                infinite_ok = True
        except Exception:
            infinite_ok = False
        if not infinite_ok:
            # 兼容不允许 infinity 的服务器（部分 IIS/群晖）：逐层 Depth:1。
            queue = [root_url]
            visited = set()
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                rows = parse_multistatus(propfind(current, "1"), current)
                child_dirs = []
                for row in rows:
                    path = row["path"]
                    if not (path.rstrip("/") + "/").startswith(root_path):
                        continue
                    if path.rstrip("/") + "/" == current.rstrip("/") + "/":
                        continue
                    if row["is_dir"]:
                        rel = self._network_safe_rel(path[len(root_path):])
                        if (
                            rel
                            and rel.count("/") + 1 < self.NETWORK_MAX_DEPTH
                            and row["url"] not in visited
                        ):
                            child_dirs.append(row["url"])
                absorb(rows, False)
                queue.extend(child_dirs)
        return entries

    def _network_parse_git_url(self, url):
        parsed = urllib.parse.urlsplit(url)
        host_config = self._network_git_host(url)
        if not host_config:
            raise ValueError("不是 GitHub/Gitee 仓库链接")
        raw_parts = [urllib.parse.unquote(seg) for seg in parsed.path.split("/") if seg]
        if len(raw_parts) < 2:
            raise ValueError("仓库链接需包含 用户名/仓库名")
        owner = raw_parts[0]
        repo = raw_parts[1]
        if repo.endswith(".git"):
            repo = repo[:-4]
        branch = ""
        prefix = ""
        if len(raw_parts) >= 4 and raw_parts[2] in ("tree", "blob"):
            branch = raw_parts[3]
            prefix = "/".join(raw_parts[4:])
            if raw_parts[2] == "blob":
                # .../blob/branch/dir 不规范，但兼容处理。
                pass
        return owner, repo, branch, prefix.strip("/"), host_config

    def _network_git_get_json(self, api_url, root, token_query=False):
        auth = self._network_auth(root)
        url = api_url
        headers = {"Accept": "application/vnd.github+json"}
        token = auth["token"] or auth["password"]
        host_info = self._network_git_host(root.get("url", ""))
        is_github = bool(host_info and host_info[3] == "github")
        if is_github:
            # GitHub：加速回退由 _network_github_fast_request 统一处理，
            # Token（如有）也在其中以直连方式附加，不经过第三方代理。
            status, _h, body, _final = self._network_github_fast_request(
                url, root, headers=headers
            )
        else:
            if token_query and token:
                separator = "&" if "?" in url else "?"
                url = "{}{}access_token={}".format(
                    url, separator, urllib.parse.quote(token, safe="")
                )
            elif token:
                headers["Authorization"] = "Bearer {}".format(token)
            status, _h, body, _final = self._network_http_request(
                url, headers=headers, auth=None
            )
        if status == 403:
            raise ValueError(
                "仓库 API 拒绝访问（HTTP 403）：可能是私有库未填 Token，或触发了限流"
            )
        if status == 404:
            raise ValueError("仓库或分支不存在（HTTP 404），请检查链接与 Token")
        if status != 200:
            raise ValueError("仓库 API 请求失败 HTTP {}".format(status))
        try:
            return json.loads(body.decode("utf-8"))
        except Exception as exc:
            raise ValueError("仓库 API 返回解析失败: {}".format(exc))

    def _network_list_git(self, root, protocol):
        owner, repo, branch, prefix, host_config = self._network_parse_git_url(
            root["url"]
        )
        api_base, raw_template, token_query, _label = host_config
        data = None
        if protocol == "github":
            # api.github.com 在部分网络下被限流/阻断：API 失败时自动改拉
            # codeload 源码归档（同样支持加速站前缀）来列举目录树。
            # 404 属于仓库/分支真实不存在，不回退。
            try:
                if not branch:
                    info = self._network_git_get_json(
                        "{}/repos/{}/{}".format(api_base, owner, repo),
                        root,
                        token_query,
                    )
                    branch = str(info.get("default_branch", "master") or "master")
                tree_url = "{}/repos/{}/{}/git/trees/{}?recursive=1".format(
                    api_base, owner, repo, urllib.parse.quote(branch, safe="/")
                )
                data = self._network_git_get_json(tree_url, root, token_query)
            except Exception as api_exc:
                if "404" in str(api_exc):
                    raise
                self._warn(
                    "GitHub API 不可达（{}），改用源码归档加速列举".format(api_exc)
                )
                return self._network_github_tree_from_tarball(
                    root, owner, repo, branch, prefix
                )
        else:
            if not branch:
                info = self._network_git_get_json(
                    "{}/repos/{}/{}".format(api_base, owner, repo), root, token_query
                )
                branch = str(info.get("default_branch", "master") or "master")
            tree_url = "{}/repos/{}/{}/git/trees/{}?recursive=1".format(
                api_base, owner, repo, urllib.parse.quote(branch, safe="/")
            )
            data = self._network_git_get_json(tree_url, root, token_query)
        tree = data.get("tree", []) if isinstance(data, dict) else []
        if not isinstance(tree, list):
            raise ValueError("仓库目录树返回格式无效")
        if data.get("truncated"):
            self._warn("GitHub/Gitee 仓库目录树被服务端截断，文件可能不全")
        entries = []
        prefix_norm = prefix.strip("/")
        for item in tree:
            if not isinstance(item, dict) or item.get("type") != "blob":
                continue
            full_path = str(item.get("path", "") or "")
            if prefix_norm:
                prefix_with_slash = prefix_norm + "/"
                if full_path != prefix_norm and not full_path.startswith(prefix_with_slash):
                    continue
                rel_raw = full_path[len(prefix_norm):].lstrip("/")
            else:
                rel_raw = full_path
            rel = self._network_safe_rel(rel_raw)
            if not rel:
                continue
            if rel.count("/") + 1 > self.NETWORK_MAX_DEPTH:
                continue
            quoted_segments = "/".join(
                urllib.parse.quote(seg, safe="")
                for seg in [branch] + full_path.split("/")
            )
            # 用明确的主机前缀拼，避免模板字段理解偏差。
            if protocol == "gitee":
                raw_url = "https://gitee.com/{}/{}/raw/{}".format(
                    owner, repo, quoted_segments
                )
                auth = self._network_auth(root)
                token = auth["token"] or auth["password"]
                if token:
                    raw_url += "?access_token={}".format(
                        urllib.parse.quote(token, safe="")
                    )
            else:
                raw_url = "https://raw.githubusercontent.com/{}/{}/{}".format(
                    owner, repo, quoted_segments
                )
            try:
                size = int(item.get("size", 0) or 0)
            except Exception:
                size = 0
            entries.append(
                {
                    "rel": rel,
                    "url": raw_url,
                    "size": size,
                    "mtime": "",
                    "etag": str(item.get("sha", "") or ""),
                    "is_dir": False,
                }
            )
        return entries

    def _network_github_tree_from_tarball(self, root, owner, repo, branch, prefix):
        """API 不可用时的兜底：拉 codeload 源码归档解析目录树。

        归档 URL 同样适用「加速站 + 完整 URL」拼接；公开库走加速回退，
        私有库（带 Token）只直连。返回结构与 _network_list_git 一致。
        """
        import gzip
        import io
        import tarfile

        branches = [branch] if branch else ["main", "master"]
        prefix_norm = str(prefix or "").strip("/")
        last_error = None
        for candidate_branch in branches:
            archive_url = (
                "https://codeload.github.com/{}/{}/tar.gz/refs/heads/{}".format(
                    urllib.parse.quote(owner, safe=""),
                    urllib.parse.quote(repo, safe=""),
                    urllib.parse.quote(candidate_branch, safe=""),
                )
            )
            try:
                status, _h, body, _final = self._network_github_fast_request(
                    archive_url, root
                )
                if status != 200:
                    raise ValueError("HTTP {}".format(status))
                if not body:
                    raise ValueError("源码归档内容为空")
                if len(body) > self.NETWORK_GITHUB_ARCHIVE_MAX_SIZE:
                    raise ValueError("源码归档超过 {}MB 上限".format(
                        self.NETWORK_GITHUB_ARCHIVE_MAX_SIZE // (1024 * 1024)
                    ))
                entries = []
                with gzip.GzipFile(fileobj=io.BytesIO(body)) as gz:
                    with tarfile.open(fileobj=gz, mode="r|") as tf:
                        for member in tf:
                            if not member.isfile():
                                continue
                            parts = str(member.name or "").split("/", 1)
                            if len(parts) < 2:
                                continue
                            full_path = parts[1]
                            if prefix_norm:
                                prefix_with_slash = prefix_norm + "/"
                                if full_path != prefix_norm and not full_path.startswith(
                                    prefix_with_slash
                                ):
                                    continue
                                rel_raw = full_path[len(prefix_norm):].lstrip("/")
                            else:
                                rel_raw = full_path
                            rel = self._network_safe_rel(rel_raw)
                            if not rel:
                                continue
                            if rel.count("/") + 1 > self.NETWORK_MAX_DEPTH:
                                continue
                            quoted_segments = "/".join(
                                urllib.parse.quote(seg, safe="")
                                for seg in [candidate_branch] + full_path.split("/")
                            )
                            raw_url = (
                                "https://raw.githubusercontent.com/{}/{}/{}".format(
                                    owner, repo, quoted_segments
                                )
                            )
                            entries.append(
                                {
                                    "rel": rel,
                                    "url": raw_url,
                                    "size": int(getattr(member, "size", 0) or 0),
                                    "mtime": "",
                                    "etag": "",
                                    "is_dir": False,
                                }
                            )
                self._warn(
                    "GitHub 已通过源码归档列举 {} 个文件（分支 {}），增量按文件大小判断".format(
                        len(entries), candidate_branch
                    )
                )
                return entries
            except Exception as exc:
                last_error = exc
                continue
        raise ValueError(
            "GitHub API 与源码归档均列举失败：{}".format(last_error)
        )

    # ------------------------------------------------------------------
    # 镜像同步引擎
    # ------------------------------------------------------------------
    def _network_manifest_path(self, cache_dir):
        return os.path.join(cache_dir, self.NETWORK_MANIFEST_NAME)

    def _network_marker_path(self, cache_dir):
        return os.path.join(cache_dir, self.NETWORK_MARKER_NAME)

    def _network_load_manifest(self, cache_dir):
        path = self._network_manifest_path(cache_dir)
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            if isinstance(data, dict) and isinstance(data.get("files"), dict):
                return data
        except Exception:
            pass
        return {"files": {}}

    def _network_file_target(self, cache_dir, rel):
        safe_rel = self._network_safe_rel(rel)
        if not safe_rel:
            return None
        target = os.path.normpath(os.path.join(cache_dir, *safe_rel.split("/")))
        if not target.startswith(os.path.normpath(cache_dir) + os.sep):
            return None
        return target

    def _network_head_metadata(self, root, entry):
        """HTTP 源：HEAD 取 ETag / Last-Modified / Content-Length 做增量。"""
        try:
            status, headers, _body, _final = self._network_http_request(
                entry["url"],
                method="HEAD",
                auth=self._network_auth(root),
            )
        except Exception:
            return None
        if status != 200:
            return None
        meta = {}
        etag = str(headers.get("etag", "") or "").strip()
        modified = str(headers.get("last-modified", "") or "").strip()
        length = str(headers.get("content-length", "") or "").strip()
        if etag:
            meta["etag"] = etag
        if modified:
            meta["mtime"] = modified
        if length.isdigit():
            meta["size"] = int(length)
        return meta or None

    def _network_download_one(self, root, entry, target):
        headers = {}
        response_headers = {}
        host_info = self._network_git_host(root.get("url", ""))
        if host_info and host_info[3] == "github":
            # GitHub raw：公开库直连失败自动换加速站（Token 私有库强制直连，
            # Bearer 由 fast_request 附加），成功线路在本次同步内粘滞。
            status, response_headers, body, _final = self._network_github_fast_request(
                entry["url"], root
            )
        elif host_info and host_info[3] == "gitee":
            # Gitee token 已放在 query。
            status, response_headers, body, _final = self._network_http_request(
                entry["url"], headers=headers, auth=None
            )
        else:
            status, response_headers, body, _final = self._network_http_request(
                entry["url"], headers=headers, auth=self._network_auth(root)
            )
        if status != 200:
            raise ValueError("HTTP {}".format(status))
        if not body:
            raise ValueError("文件内容为空")
        parent = os.path.dirname(target)
        if not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        tmp_path = target + ".tmp.{}-{}".format(os.getpid(), threading.get_ident())
        try:
            with open(tmp_path, "wb") as fp:
                fp.write(body)
            os.replace(tmp_path, target)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
        extra_meta = {}
        etag = str(response_headers.get("etag", "") or "").strip()
        modified = str(response_headers.get("last-modified", "") or "").strip()
        length = str(response_headers.get("content-length", "") or "").strip()
        if etag:
            extra_meta["etag"] = etag
        if modified:
            extra_meta["mtime"] = modified
        if length.isdigit():
            extra_meta["size"] = int(length)
        return len(body), extra_meta

    def _network_entry_changed(self, entry, old_meta):
        if not isinstance(old_meta, dict):
            return True
        if entry.get("etag"):
            return str(old_meta.get("etag", "")) != str(entry["etag"])
        new_size = int(entry.get("size", 0) or 0)
        old_size = int(old_meta.get("size", -1) or -1)
        if new_size and old_size is not None:
            return new_size != old_size
        if entry.get("mtime") and entry["mtime"] != old_meta.get("mtime", ""):
            return True
        return True

    def _sync_network_root_locked(self, root, progress=None):
        """同步单个网络根到本地缓存目录。返回统计 dict。"""
        url = str(root.get("url", "") or "")
        if not self._network_normalize_url(url):
            raise ValueError("网络地址无效")
        root["url"] = self._network_normalize_url(url)
        protocol = self._network_resolve_protocol(root)
        root["protocol"] = protocol
        cache_dir = self._network_root_cache_dir(root)

        def report(message, done=None, total=None, indeterminate=None):
            self._network_sync_message = str(message)
            if progress:
                try:
                    progress(
                        str(message),
                        done=done,
                        total=total,
                        indeterminate=indeterminate,
                    )
                except TypeError:
                    # 兼容只接受单参数的旧式回调（如测试桩）。
                    try:
                        progress(str(message))
                    except Exception:
                        pass
                except Exception:
                    pass

        report(
            "正在获取 {} 目录列表…".format(protocol.upper()),
            indeterminate=True,
        )
        entries = self._network_list_tree(root, protocol)
        candidates = []
        skipped_large = 0
        for entry in entries:
            rel = entry.get("rel", "")
            extension = os.path.splitext(rel.lower())[1]
            if extension not in self.NETWORK_EXTENSIONS:
                continue
            size = int(entry.get("size", 0) or 0)
            if size > self.NETWORK_MAX_FILE_SIZE:
                skipped_large += 1
                continue
            candidates.append(entry)
            if len(candidates) >= self.NETWORK_MAX_FILES:
                break
        if not candidates:
            raise ValueError(
                "远程目录中没有发现 .py/.js/.json/.html 源文件，请确认地址指向源文件目录"
            )
        # 确认远程有效后才创建本地镜像目录，避免失败残留空目录被当成扫描根。
        os.makedirs(cache_dir, exist_ok=True)

        old_manifest = self._network_load_manifest(cache_dir)
        old_files = old_manifest.get("files", {})
        # HTTP 静态目录索引页通常不带文件大小/摘要；先并发 HEAD 取回
        # ETag/Last-Modified/Content-Length，让增量跳过真正生效。
        if protocol == "http" and candidates:
            head_workers = max(1, min(self.NETWORK_WORKERS * 2, len(candidates)))
            head_total = len(candidates)
            head_done = 0
            report(
                "正在检查文件更新（0/{}）…".format(head_total),
                done=0,
                total=head_total,
            )
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=head_workers
            ) as executor:
                head_futures = {
                    executor.submit(self._network_head_metadata, root, entry): entry
                    for entry in candidates
                }
                for future in concurrent.futures.as_completed(head_futures):
                    entry = head_futures[future]
                    try:
                        head_meta = future.result()
                    except Exception:
                        head_meta = None
                    if head_meta:
                        entry.update(head_meta)
                    head_done += 1
                    if head_done % 10 == 0 or head_done == head_total:
                        report(
                            "正在检查文件更新（{}/{}）…".format(
                                head_done, head_total
                            ),
                            done=head_done,
                            total=head_total,
                        )
        download_list = []
        new_meta = {}
        for entry in candidates:
            rel = entry["rel"]
            meta = {
                "size": int(entry.get("size", 0) or 0),
                "mtime": str(entry.get("mtime", "") or ""),
                "etag": str(entry.get("etag", "") or ""),
                "url": entry["url"],
            }
            new_meta[rel] = meta
            if self._network_entry_changed(entry, old_files.get(rel)):
                download_list.append(entry)

        total = len(download_list)
        downloaded_bytes = 0
        done = 0
        failures = []
        failed_rels = set()

        def work(entry):
            target = self._network_file_target(cache_dir, entry["rel"])
            if not target:
                raise ValueError("不安全的文件路径: {}".format(entry["rel"]))
            written, extra_meta = self._network_download_one(root, entry, target)
            return entry["rel"], written, extra_meta

        if download_list:
            max_workers = max(1, min(self.NETWORK_WORKERS, total))
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers
            ) as executor:
                future_map = {
                    executor.submit(work, entry): entry for entry in download_list
                }
                for future in concurrent.futures.as_completed(future_map):
                    entry = future_map[future]
                    try:
                        rel, written, extra_meta = future.result()
                        downloaded_bytes += int(written or 0)
                        if extra_meta:
                            new_meta.setdefault(rel, {}).update(extra_meta)
                    except Exception as exc:
                        failed_rels.add(entry["rel"])
                        if len(failures) < 20:
                            failures.append(
                                "{}: {}".format(entry["rel"], exc)
                            )
                    done += 1
                    # 沿用旧版「首批 + 每 10 个 + 末批」节奏，避免逐文件
                    # 刷日志/刷 UI；进度数值照常驱动百分比。
                    if done == 1 or done % 10 == 0 or done == total:
                        report(
                            "正在下载 {}/{}：{}".format(
                                done, total, entry["rel"]
                            ),
                            done=done,
                            total=total,
                        )
        else:
            # 无需下载时也要把确定进度条补满，避免空条/除零。
            report("远程文件均为最新，无需下载", done=1, total=1)
        # 下载失败的文件不写入新清单，并保留旧镜像（如有），下次同步自动重试。
        for rel in failed_rels:
            new_meta.pop(rel, None)

        # 清理远程已删除的旧镜像文件与空目录。
        report("正在清理失效镜像文件…", indeterminate=True)
        removed = 0
        for rel in list(old_files.keys()):
            if rel in new_meta or rel in failed_rels:
                continue
            target = self._network_file_target(cache_dir, rel)
            if target and os.path.isfile(target):
                try:
                    os.remove(target)
                    removed += 1
                except Exception:
                    pass
        for current, dirs, files in os.walk(cache_dir, topdown=False):
            if current == cache_dir:
                continue
            try:
                if not os.listdir(current):
                    os.rmdir(current)
            except Exception:
                pass

        manifest = {
            "format": "local-network-root-cache/v1",
            "url": root["url"],
            "protocol": protocol,
            "synced_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "files": new_meta,
        }
        report("正在写入镜像清单…", indeterminate=True)
        with open(self._network_manifest_path(cache_dir), "w", encoding="utf-8") as fp:
            json.dump(manifest, fp, ensure_ascii=False, indent=0)
        with open(self._network_marker_path(cache_dir), "w", encoding="utf-8") as fp:
            json.dump(
                {
                    "id": root["id"],
                    "name": root.get("name", ""),
                    "url": root["url"],
                    "protocol": protocol,
                },
                fp,
                ensure_ascii=False,
            )
        total_bytes = sum(int(item.get("size", 0) or 0) for item in candidates)
        if failures and len(failures) == total:
            status = "fail"
        elif failures:
            status = "warn"
        else:
            status = "ok"
        return {
            "protocol": protocol,
            "total": len(candidates),
            "downloaded": total - len(failures),
            "failed": len(failures),
            "failures": failures,
            "removed": removed,
            "skipped_large": skipped_large,
            "bytes": total_bytes,
            "status": status,
        }

    def _sync_network_roots_locked(self, only_root_id=None, progress=None):
        """扫描/手动同步入口。返回 (success_count, detail_lines)。

        单个根失败不影响其它根，也不中断本地扫描。
        progress(message, done=None, total=None, indeterminate=None) 可选，
        用于把每个根的同步进度回传到进度对话框/面板。
        """
        targets = []
        for root in self.network_roots:
            if not root.get("enabled", True):
                continue
            if only_root_id and root.get("id") != only_root_id:
                continue
            targets.append(root)
        if not targets:
            return 0, []
        details = []
        success = 0
        self._network_sync_running = True
        if progress:
            try:
                progress(
                    "准备同步 {} 个网络目录…".format(len(targets)),
                    indeterminate=True,
                )
            except Exception:
                pass
        try:
            for root in targets:
                name = str(root.get("name", "网络目录"))
                self._network_sync_root_id = str(root.get("id", ""))
                self._network_sync_message = "准备同步「{}」".format(name)
                self._log("INFO", "网络目录开始同步: {} ({})".format(name, root.get("url")))

                def _root_progress(message, _name=name, **kwargs):
                    # 原有行为：每个阶段消息都写日志；同时转发给上层 UI。
                    self._log("INFO", str(message))
                    if progress:
                        try:
                            progress(
                                "「{}」{}".format(_name, message),
                                **kwargs
                            )
                        except TypeError:
                            try:
                                progress(
                                    "「{}」{}".format(_name, message)
                                )
                            except Exception:
                                pass
                        except Exception:
                            pass

                try:
                    stats = self._sync_network_root_locked(
                        root,
                        progress=_root_progress,
                    )
                    root["last_sync"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    root["last_status"] = stats["status"]
                    root["file_count"] = stats["total"]
                    root["byte_count"] = stats["bytes"]
                    if stats["status"] == "ok":
                        message = "同步完成：{} 个源文件".format(stats["total"])
                    else:
                        message = "同步完成：{}/{} 成功，{} 个失败".format(
                            stats["downloaded"],
                            stats["total"],
                            stats["failed"],
                        )
                    root["last_message"] = message
                    details.append("「{}」{}".format(name, message))
                    self._log(
                        "INFO" if stats["status"] != "fail" else "WARN",
                        "网络目录同步{}: {} -> {}".format(
                            stats["status"], name, message
                        ),
                    )
                    if stats["status"] != "fail":
                        success += 1
                except Exception as exc:
                    root["last_sync"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    root["last_status"] = "fail"
                    root["last_message"] = str(exc)[:240]
                    details.append("「{}」同步失败：{}".format(name, exc))
                    self._warn("网络目录同步失败: {} ({})".format(name, exc))
            try:
                self._save_settings()
            except Exception as exc:
                self._warn("网络目录同步状态保存失败: {}".format(exc))
        finally:
            self._network_sync_running = False
            self._network_sync_root_id = ""
            self._network_sync_message = ""
        return success, details

    def _network_remove_root(self, root_id, remove_cache=True):
        root = self._network_root_by_id(root_id)
        if not root:
            return False
        self.network_roots = [
            item for item in self.network_roots if item.get("id") != root_id
        ]
        if remove_cache:
            cache_dir = self._network_root_cache_dir(root)
            try:
                if os.path.isdir(cache_dir):
                    shutil.rmtree(cache_dir, ignore_errors=True)
            except Exception as exc:
                self._warn("网络目录缓存删除失败: {}".format(exc))
        self._save_settings()
        return True

    def _network_probe_locked(self, url, username, password, protocol="auto"):
        """添加/编辑对话框的「测试连接」：识别协议并数出顶层条目。"""
        normalized = self._network_normalize_url(url)
        if not normalized:
            raise ValueError("地址必须是 http:// 或 https:// 链接")
        if protocol not in self.NETWORK_PROTOCOLS:
            protocol = "auto"
        probe_root = {
            "id": self._network_root_id(normalized),
            "url": normalized,
            "protocol": protocol,
            "username": str(username or ""),
            "password": str(password or ""),
            "token": str(password or ""),
            "enabled": True,
        }
        protocol = self._network_resolve_protocol(probe_root)
        if protocol in ("github", "gitee"):
            entries = self._network_list_git(probe_root, protocol)
        elif protocol == "webdav":
            entries = self._network_list_webdav(probe_root)
        else:
            entries = self._network_list_http(probe_root)
        source_files = [
            item
            for item in entries
            if os.path.splitext(str(item.get("rel", "")).lower())[1]
            in self.NETWORK_EXTENSIONS
        ]
        sample = []
        for item in source_files[:5]:
            sample.append(item["rel"])
        return protocol, len(source_files), sample

    @staticmethod
    def _dir_contains_any_file(path):
        """目录树下是否存在任意普通文件（忽略隐藏目录）。

        用于区分“真实分类目录”与旧版本自动创建的空分类文件夹；
        遇到第一个文件即返回，不做全量遍历。
        """
        try:
            for current, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                if files:
                    return True
        except Exception:
            return False
        return False

    def _scan_roots_for_base(self, base_path):
        # 扫描根语义：优先使用根下“确实含有文件”的类型子目录
        # （py/python、js、csp、html，标准分类布局）；子目录不存在、
        # 或只是空目录（常见于旧版本设置路径时自动创建的空分类文件夹）
        # 时，回退为直接递归扫描根目录本身。这样无论扫描根设成 webhome
        # 容器、Python 目录，还是 TVBoxOSC 这类任意目录，里面任意层级
        # 的源文件都能被扫到；标准布局行为不变。
        def type_root(*names):
            detected = _detect_child_dir(base_path, *names)
            if os.path.isdir(detected) and self._dir_contains_any_file(detected):
                return detected
            return base_path

        roots = [
            {
                "path": type_root("py", "python"),
                "type": "PY",
                "extensions": [".py"],
            },
            {
                "path": type_root("js", "javascript"),
                "type": "JS",
                "extensions": [".js", ".json"],
            },
            {
                "path": type_root("csp"),
                "type": "CSP",
                "extensions": [".json"],
            },
            # 已按用户要求移除 XBPQ 扫描根，仅保留 csp 作为 JAR/CSP 站点源目录。
            {
                "path": type_root("html"),
                "type": "HTML",
                "extensions": [".html"],
            },
        ]
        # 独立本地直播目录：直播文件 / 直播 / lives / live 等目录（只放 TVBox 直播配置）。
        # 复用 CSP 类型根以便命中共用的整包 JSON 解析分支，由 _has_raw_lives 识别出
        # 非空 lives 数组后照常收录为本地直播。仅当目录真实存在时才加入，避免对不存在
        # 的路径触发“目录不存在”告警并把扫描标记为不完整。
        live_dir = _detect_child_dir(base_path, "直播文件", "直播", "lives", "live")
        if live_dir and os.path.isdir(live_dir):
            roots.append(
                {
                    "path": live_dir,
                    "type": "CSP",
                    "extensions": [".json"],
                }
            )
        return roots

    def _auto_classify_extension_map(self):
        """根据当前扫描根构建 扩展名 -> 目标子目录 的映射。
        只有映射到唯一类型的扩展名才可安全归类；.json 同时属于 JS/CSP，视为歧义不移动。"""
        ext_to_dirs = {}
        for root in self.scan_roots:
            directory = root.get("path")
            if not directory:
                continue
            for ext in root.get("extensions", []):
                ext_to_dirs.setdefault(ext.lower(), []).append(directory)
        unique = {}
        ambiguous = set()
        for ext, dirs in ext_to_dirs.items():
            distinct = list(dict.fromkeys(dirs))
            if len(distinct) == 1:
                unique[ext] = distinct[0]
            else:
                ambiguous.add(ext)
        return unique, ambiguous

    def _auto_classify_files(self):
        """把扫描根目录顶层散落的源文件移动到对应类型子目录。
        - 仅处理根目录顶层的普通文件，不递归、不动子目录内已归类文件。
        - 跳过符号链接、隐藏文件、管理脚本自身。
        - 目标已存在同名文件时跳过，绝不覆盖。
        - .json 等歧义扩展名不移动，计入“需手动归类”。
        返回 (moved, skipped_conflict, skipped_ambiguous, skipped_other, created_dirs, errors, detail_lines)。
        """
        base = self.local_base_dir
        if not base or not os.path.isdir(base):
            raise ValueError("扫描根目录不存在: {}".format(base or "(未设置)"))

        unique_map, ambiguous_exts = self._auto_classify_extension_map()

        moved = 0
        skipped_conflict = 0
        skipped_ambiguous = 0
        skipped_other = 0
        created_dirs = []
        errors = []
        detail = []

        try:
            entries = sorted(os.listdir(base), key=lambda v: v.lower())
        except Exception as exc:
            raise ValueError("读取扫描根目录失败: {} ({})".format(base, exc))

        self_real = None
        try:
            self_real = os.path.realpath(__file__)
        except Exception:
            self_real = None

        for name in entries:
            if name.startswith("."):
                continue
            src = os.path.join(base, name)
            try:
                if os.path.islink(src) or not os.path.isfile(src):
                    continue
            except Exception:
                continue
            src_real = os.path.realpath(src)
            if self_real and src_real == self_real:
                continue
            lower_name = name.lower()
            matched_exts = [
                ext
                for ext in set(unique_map) | ambiguous_exts
                if lower_name.endswith(ext)
            ]
            if not matched_exts:
                skipped_other += 1
                continue
            # 先匹配 .csp.json 这类多后缀，避免被末尾 .json
            # 误判为歧义文件。
            ext = max(matched_exts, key=len)
            if ext in ambiguous_exts:
                skipped_ambiguous += 1
                detail.append("歧义跳过 {}（{} 可属多个类型，请手动归类）".format(name, ext))
                continue
            target_dir = unique_map.get(ext)
            if not target_dir:
                skipped_other += 1
                continue
            destination = os.path.join(target_dir, name)
            if os.path.exists(destination):
                skipped_conflict += 1
                detail.append("冲突跳过 {}（目标已存在同名文件）".format(name))
                continue
            try:
                if not os.path.isdir(target_dir):
                    os.makedirs(target_dir, exist_ok=True)
                    created_dirs.append(target_dir)
                shutil.move(src, destination)
                moved += 1
                detail.append("已归类 {} -> {}/".format(name, os.path.basename(target_dir)))
            except Exception as exc:
                errors.append("{}: {}".format(name, exc))
                self._log("ERROR", "自动分类移动失败 {} -> {}: {}".format(src, destination, exc))

        return (
            moved,
            skipped_conflict,
            skipped_ambiguous,
            skipped_other,
            created_dirs,
            errors,
            detail,
        )

    def _run_auto_classify(self):
        """执行自动分类并生成用户可见的摘要与详情文本。调用方需持有 self.lock。
        仅移动文件，不触发扫描或重载；完成后提示用户点击“一键扫描并加载”。"""
        try:
            (
                moved,
                skipped_conflict,
                skipped_ambiguous,
                skipped_other,
                created_dirs,
                errors,
                detail,
            ) = self._auto_classify_files()
        except Exception as exc:
            self._log("ERROR", "自动分类失败: {}".format(exc))
            message = "自动分类失败：{}".format(exc)
            return message, message

        parts = ["已归类 {} 个".format(moved)]
        if skipped_conflict:
            parts.append("同名冲突跳过 {}".format(skipped_conflict))
        if skipped_ambiguous:
            parts.append("歧义(.json 等)跳过 {}".format(skipped_ambiguous))
        if skipped_other:
            parts.append("其它跳过 {}".format(skipped_other))
        if errors:
            parts.append("失败 {}".format(len(errors)))
        summary = "；".join(parts)
        if moved:
            summary += "；请点击「扫描」后重新「加载」生效"

        content_lines = [
            "扫描根目录：{}".format(self.local_base_dir),
            "本次归类：{} 个文件".format(moved),
            "同名冲突跳过：{}".format(skipped_conflict),
            "歧义扩展名跳过：{}（.json 同属 JS/CSP，需手动放入对应子目录）".format(
                skipped_ambiguous
            ),
            "其它跳过：{}（无扩展名或未配置类型）".format(skipped_other),
        ]
        if created_dirs:
            content_lines.append(
                "新建子目录：{}".format(
                    ", ".join(os.path.basename(d) for d in created_dirs)
                )
            )
        if detail:
            content_lines.append("")
            content_lines.append("明细:")
            content_lines.extend("- " + line for line in detail[:100])
            if len(detail) > 100:
                content_lines.append("- ...（其余 {} 条省略）".format(len(detail) - 100))
        if errors:
            content_lines.append("")
            content_lines.append("失败明细:")
            content_lines.extend("- " + line for line in errors[:50])
        content_lines.append("")
        content_lines.append(
            "仅移动文件，未触发扫描；确认无误后请「扫描」并重新「加载」。"
        )
        self._log(
            "INFO",
            "自动分类完成: 移动 {}, 冲突 {}, 歧义 {}, 其它 {}, 失败 {}".format(
                moved, skipped_conflict, skipped_ambiguous, skipped_other, len(errors)
            ),
        )
        return summary, "\n".join(content_lines)

    def _apply_scan_base_path(self, value):
        path = self._normalize_scan_base_path(value)
        if path:
            self.scan_base_path = path
            self.local_base_dir = path
            self.scan_roots = self._scan_roots_for_base(path)
        else:
            self.scan_base_path = ""
            self.local_base_dir = self.LOCAL_BASE_DIR
            self.scan_roots = [dict(item) for item in self.configured_scan_roots]

    def _create_scan_base_tree(self, path):
        created = []
        try:
            if os.path.exists(path) and not os.path.isdir(path):
                raise ValueError("输入路径不是目录: {}".format(path))
            if not os.path.isdir(path):
                missing = []
                current = path
                while current and not os.path.exists(current):
                    missing.append(current)
                    parent = os.path.dirname(current)
                    if parent == current:
                        break
                    current = parent
                for directory in reversed(missing):
                    if os.path.isdir(directory):
                        continue
                    try:
                        os.mkdir(directory)
                    except FileExistsError:
                        if not os.path.isdir(directory):
                            raise
                    else:
                        created.append(directory)
            for root in self._scan_roots_for_base(path):
                directory = root["path"]
                if os.path.isdir(directory):
                    continue
                try:
                    os.mkdir(directory)
                except FileExistsError:
                    if not os.path.isdir(directory):
                        raise
                else:
                    created.append(directory)
            return created
        except Exception:
            self._remove_created_scan_dirs(created)
            raise

    def _remove_created_scan_dirs(self, directories):
        for directory in reversed(directories):
            try:
                os.rmdir(directory)
            except Exception:
                pass

    def _set_scan_base_path(self, value):
        path = self._normalize_scan_base_path(value)
        previous_path = self.scan_base_path
        previous_base = self.local_base_dir
        previous_roots = [dict(item) for item in self.scan_roots]
        created_dirs = []
        try:
            if path:
                created_dirs = self._create_scan_base_tree(path)
                if not os.access(path, os.R_OK):
                    raise ValueError("目录不可读: {}".format(path))
            self._apply_scan_base_path(path)
            self._save_settings()
            self._set_manual_idle_status(
                "扫描目录已更新，请点击「扫描」"
            )
            self._clear_scan_cache_file()
            if created_dirs:
                self._log(
                    "INFO",
                    "扫描分类目录已自动创建: {}".format(
                        ", ".join(created_dirs)
                    ),
                )
        except Exception:
            self.scan_base_path = previous_path
            self.local_base_dir = previous_base
            self.scan_roots = previous_roots
            self._remove_created_scan_dirs(created_dirs)
            raise
        return self.scan_base_path

    def _set_pending_type_settings(self, values, block_adult_sites=None):
        previous = dict(self.pending_type_enabled)
        previous_block_adult = self.pending_block_adult_sites
        previous_dirty = self.config_dirty
        for source_type in self.TYPE_ORDER:
            if source_type in values:
                self.pending_type_enabled[source_type] = bool(values[source_type])
        if block_adult_sites is not None:
            self.pending_block_adult_sites = bool(block_adult_sites)
        self.config_dirty = any(
            self.pending_type_enabled[item] != self.type_enabled[item]
            for item in self.TYPE_ORDER
        ) or self.pending_block_adult_sites != self.block_adult_sites
        try:
            self._save_settings()
        except Exception:
            self.pending_type_enabled = previous
            self.pending_block_adult_sites = previous_block_adult
            self.config_dirty = previous_dirty
            raise
        return self.config_dirty

    def _current_android_activity(self, jclass):
        app_class = jclass("com.fongmi.android.tv.App")
        activity_class = jclass("android.app.Activity")
        modifier_class = jclass("java.lang.reflect.Modifier")
        app_info = app_class.getClass()
        activity_info = activity_class.getClass()

        for method in app_info.getDeclaredMethods():
            try:
                if not modifier_class.isStatic(method.getModifiers()):
                    continue
                if len(method.getParameterTypes()) != 0:
                    continue
                if not activity_info.isAssignableFrom(method.getReturnType()):
                    continue
                method.setAccessible(True)
                try:
                    activity = method.invoke(None, [])
                except Exception:
                    activity = method.invoke(None)
                if activity is not None:
                    return activity
            except Exception:
                continue

        app = None
        for field in app_info.getDeclaredFields():
            try:
                if not modifier_class.isStatic(field.getModifiers()):
                    continue
                if not app_info.isAssignableFrom(field.getType()):
                    continue
                field.setAccessible(True)
                app = field.get(None)
                if app is not None:
                    break
            except Exception:
                continue
        if app is not None:
            for field in app.getClass().getDeclaredFields():
                try:
                    if modifier_class.isStatic(field.getModifiers()):
                        continue
                    if not activity_info.isAssignableFrom(field.getType()):
                        continue
                    field.setAccessible(True)
                    activity = field.get(app)
                    if activity is not None:
                        return activity
                except Exception:
                    continue
        raise ValueError("未找到当前 Android 页面")

    def _android_ui_context(self, jclass):
        try:
            activity = self._current_android_activity(jclass)
            if activity is not None:
                return activity, activity
        except Exception:
            pass

        context_candidates = []
        try:
            app_class = jclass("com.fongmi.android.tv.App")
            for method_name in ("get", "getInstance", "instance"):
                try:
                    method = getattr(app_class, method_name)
                    context = method() if callable(method) else method
                    if context is not None:
                        context_candidates.append(context)
                except Exception:
                    continue
        except Exception:
            pass
        try:
            activity_thread = jclass("android.app.ActivityThread")
            context = activity_thread.currentApplication()
            if context is not None:
                context_candidates.append(context)
        except Exception:
            pass
        try:
            platform = jclass("com.chaquo.python.Python").getPlatform()
            for method_name in (
                "getApplication", "getApplicationContext", "getContext",
            ):
                try:
                    method = getattr(platform, method_name)
                    context = method() if callable(method) else method
                    if context is not None:
                        context_candidates.append(context)
                except Exception:
                    continue
        except Exception:
            pass
        return None, next(
            (context for context in context_candidates if context is not None),
            None,
        )

    def _open_scan_base_dialog(self):
        try:
            from java import dynamic_proxy, jclass

            toast_class = jclass("android.widget.Toast")
            edit_text_class = jclass("android.widget.EditText")
            input_type = jclass("android.text.InputType")
            click_listener = jclass(
                "android.content.DialogInterface$OnClickListener"
            )
            runnable_class = jclass("java.lang.Runnable")
            try:
                builder_class = jclass(
                    "com.google.android.material.dialog.MaterialAlertDialogBuilder"
                )
            except Exception:
                builder_class = jclass("android.app.AlertDialog$Builder")
            activity = self._current_android_activity(jclass)
            owner = self

            with self._ProxyCreationLock(self):

                class SaveListener(dynamic_proxy(click_listener)):
                    def __init__(self, edit):
                        super().__init__()
                        self.edit = edit

                    def onClick(self, dialog, which):
                        try:
                            value = str(self.edit.getText().toString())
                            with owner.lock:
                                saved = owner._set_scan_base_path(value)
                            message = (
                                "扫描根目录已恢复自动探测"
                                if not saved
                                else "扫描根目录已保存: {}".format(saved)
                            )
                            toast_class.makeText(
                                activity, message, toast_class.LENGTH_LONG
                            ).show()
                        except Exception as exc:
                            toast_class.makeText(
                                activity,
                                "扫描根目录保存失败: {}".format(exc),
                                toast_class.LENGTH_LONG,
                            ).show()

                class CancelListener(dynamic_proxy(click_listener)):
                    def onClick(self, dialog, which):
                        return None

                class ShowDialog(dynamic_proxy(runnable_class)):
                    def __init__(self):
                        super().__init__()
                        self._proxy_id = owner._retain_proxy(self)

                    def run(self):
                        try:
                            self._run_dialog()
                        except Exception as exc:
                            message = "根目录输入框打开失败: {}".format(exc)
                            owner._log("ERROR", message)
                            try:
                                toast_class.makeText(
                                    activity, message, toast_class.LENGTH_LONG
                                ).show()
                            except Exception:
                                owner._notify_app(message)
                        finally:
                            owner._release_proxy(self._proxy_id)

                    def _run_dialog(self):
                        edit = edit_text_class(activity)
                        current = owner.scan_base_path or owner.local_base_dir
                        edit.setSingleLine(True)
                        edit.setInputType(
                            input_type.TYPE_CLASS_TEXT
                            | input_type.TYPE_TEXT_VARIATION_URI
                        )
                        edit.setHint("/storage/emulated/0/xxxx/xxx")
                        edit.setText(current)
                        edit.setSelection(len(current))
                        save_listener = SaveListener(edit)
                        cancel_listener = CancelListener()
                        builder = builder_class(activity)
                        builder.setTitle("设置扫描目录")
                        builder.setView(edit)
                        builder.setPositiveButton("保存", save_listener)
                        builder.setNegativeButton("取消", cancel_listener)
                        dialog = builder.show()
                        edit.requestFocus()
                        owner._dialog_refs.extend(
                            [edit, save_listener, cancel_listener, dialog]
                        )

                runner = ShowDialog()
                self._dialog_refs.append(runner)
                activity.runOnUiThread(runner)
            return True, ""
        except Exception as exc:
            return False, "根目录输入框打开失败: {}".format(exc)

    def _run_load_choice_action(self, action_string):
        """后台线程执行单文件加载/移出，避免对话框回调线程阻塞。"""

        def _worker():
            try:
                result = self.action(action_string)
                message = ""
                if isinstance(result, dict):
                    message = str(result.get("msg", "") or "")
                if message:
                    self._notify_app(message)
                self._schedule_manager_page_refresh()
            except Exception as exc:
                self._log("ERROR", "文件加载操作失败: {}".format(exc))
                self._notify_app("文件加载操作失败: {}".format(exc))

        worker_thread = threading.Thread(
            target=_worker, name="local-source-load-file"
        )
        worker_thread.daemon = True
        worker_thread.start()

    # ==================================================================
    # v8.0 网络目录：后台任务 / 对话框（添加、编辑、菜单、确认、测试连接）
    # ==================================================================
    def _run_network_action(self, action_string):
        """后台线程执行网络目录动作（删除等），避免对话框回调线程阻塞。"""

        def _worker():
            try:
                result = self.action(action_string)
                message = ""
                if isinstance(result, dict):
                    message = str(result.get("msg", "") or "")
                if message:
                    self._notify_app(message)
                self._schedule_manager_page_refresh()
            except Exception as exc:
                self._log("ERROR", "网络目录操作失败: {}".format(exc))
                self._notify_app("网络目录操作失败: {}".format(exc))

        worker_thread = threading.Thread(
            target=_worker, name="local-network-action"
        )
        worker_thread.daemon = True
        worker_thread.start()

    def _network_start_sync_worker(self, only_root_id=""):
        """启动后台同步线程；进行中拒绝重复触发。"""
        if self._network_sync_running:
            self._notify_app("已有网络目录同步任务在进行，请稍候")
            return
        target_id = str(only_root_id or "")
        if target_id and not self._network_root_by_id(target_id):
            self._notify_app("网络目录不存在，可能已被删除")
            return

        def _worker():
            progress_ui = self._create_standalone_progress(
                "正在同步网络目录",
                "准备同步…",
                indeterminate=True,
            )
            try:
                def _forward(
                    message,
                    done=None,
                    total=None,
                    indeterminate=None,
                ):
                    progress_ui.update(
                        message,
                        done=done,
                        total=total,
                        indeterminate=indeterminate,
                    )

                with self.lock:
                    _count, details = self._sync_network_roots_locked(
                        only_root_id=target_id or None,
                        progress=_forward,
                    )
                message = "；".join(details) if details else "没有需要同步的已启用网络目录"
                progress_ui.finish(message, ok=True)
                self._schedule_manager_page_refresh()
            except Exception as exc:
                self._log("ERROR", "网络目录后台同步失败: {}".format(exc))
                progress_ui.finish("网络目录同步失败: {}".format(exc), ok=False)

        worker_thread = threading.Thread(
            target=_worker, name="local-network-sync"
        )
        worker_thread.daemon = True
        worker_thread.start()

    def _network_start_probe_worker(self, url, username, secret, protocol="auto"):
        """后台测试连接（列目录在 HTTP 场景下可能有多层请求，避免卡 UI）。"""

        def _worker():
            progress_ui = self._create_standalone_progress(
                "正在测试连接",
                "正在与网络目录建立连接，请稍候…",
                indeterminate=True,
            )
            try:
                with self.lock:
                    protocol_name, count, sample = self._network_probe_locked(
                        url, username, secret, protocol
                    )
                label = self._network_protocol_label(protocol_name)
                if count:
                    preview = "、".join(sample[:3])
                    message = "连接成功：{}，发现 {} 个源文件（如 {}）".format(
                        label, count, preview
                    )
                else:
                    message = "连接成功：{}，但该目录下未发现 .py/.js/.json/.html 源文件".format(
                        label
                    )
                progress_ui.finish(message, ok=True)
            except Exception as exc:
                self._log("WARN", "网络目录连接测试失败: {}".format(exc))
                progress_ui.finish("连接失败: {}".format(exc), ok=False)

        worker_thread = threading.Thread(
            target=_worker, name="local-network-probe"
        )
        worker_thread.daemon = True
        worker_thread.start()

    def _open_network_confirm_dialog(self, title, message, on_confirm):
        """通用二次确认框；on_confirm 是无参 Python 可调用对象。"""
        try:
            from java import dynamic_proxy, jclass

            click_listener = jclass(
                "android.content.DialogInterface$OnClickListener"
            )
            runnable_class = jclass("java.lang.Runnable")
            try:
                builder_class = jclass(
                    "com.google.android.material.dialog.MaterialAlertDialogBuilder"
                )
            except Exception:
                builder_class = jclass("android.app.AlertDialog$Builder")
            activity = self._current_android_activity(jclass)
            owner = self

            with self._ProxyCreationLock(self):

                class ConfirmListener(dynamic_proxy(click_listener)):
                    def onClick(self, dialog, which):
                        try:
                            on_confirm()
                        except Exception as exc:
                            owner._log("ERROR", "确认操作执行失败: {}".format(exc))
                            owner._notify_app("操作失败: {}".format(exc))

                class CancelListener(dynamic_proxy(click_listener)):
                    def onClick(self, dialog, which):
                        return None

                class ShowDialog(dynamic_proxy(runnable_class)):
                    def __init__(self):
                        super().__init__()
                        self._proxy_id = owner._retain_proxy(self)

                    def run(self):
                        try:
                            builder = builder_class(activity)
                            builder.setTitle(title)
                            builder.setMessage(message)
                            confirm_listener = ConfirmListener()
                            cancel_listener = CancelListener()
                            builder.setPositiveButton("确认", confirm_listener)
                            builder.setNegativeButton("取消", cancel_listener)
                            dialog = builder.show()
                            owner._dialog_refs.extend(
                                [confirm_listener, cancel_listener, dialog]
                            )
                        finally:
                            owner._release_proxy(self._proxy_id)

                runner = ShowDialog()
                self._dialog_refs.append(runner)
                activity.runOnUiThread(runner)
            return True, ""
        except Exception as exc:
            return False, "确认框打开失败: {}".format(exc)

    def _open_network_root_menu_dialog(self, root_id):
        """单个网络根的操作菜单。"""
        try:
            from java import dynamic_proxy, jclass

            toast_class = jclass("android.widget.Toast")
            click_listener = jclass(
                "android.content.DialogInterface$OnClickListener"
            )
            runnable_class = jclass("java.lang.Runnable")
            try:
                builder_class = jclass(
                    "com.google.android.material.dialog.MaterialAlertDialogBuilder"
                )
            except Exception:
                builder_class = jclass("android.app.AlertDialog$Builder")
            activity = self._current_android_activity(jclass)
            owner = self
            with self.lock:
                root = self._network_root_by_id(root_id)
                if not root:
                    return False, "网络目录不存在，请刷新页面"
                snapshot = {
                    "id": str(root.get("id", "")),
                    "name": str(root.get("name", "网络目录")),
                    "url": str(root.get("url", "")),
                    "username": str(root.get("username", "") or ""),
                    "secret": str(root.get("password", "") or root.get("token", "")),
                    "enabled": bool(root.get("enabled", True)),
                    "protocol": str(root.get("protocol", "auto") or "auto"),
                }
            labels = [
                "🔄 立即同步（后台增量下载）",
                "✏️ 编辑",
                "⏸ 停用" if snapshot["enabled"] else "▶️ 启用",
                "🔌 测试连接",
                "🗑 删除（同时删除本地镜像，不可恢复）",
            ]

            with self._ProxyCreationLock(self):

                class MenuListener(dynamic_proxy(click_listener)):
                    def onClick(self, dialog, which):
                        try:
                            if which == 0:
                                # v8.0：同步进度由独立进度对话框展示，不再弹 toast。
                                owner._network_start_sync_worker(snapshot["id"])
                            elif which == 1:
                                owner._open_network_edit_dialog(snapshot["id"])
                            elif which == 2:
                                with owner.lock:
                                    target = owner._network_root_by_id(snapshot["id"])
                                    if target:
                                        target["enabled"] = not target.get(
                                            "enabled", True
                                        )
                                        owner._save_settings()
                                owner._schedule_manager_page_refresh()
                            elif which == 3:
                                # v8.0：测试进度由独立进度对话框展示，不再弹 toast。
                                owner._network_start_probe_worker(
                                    snapshot["url"],
                                    snapshot["username"],
                                    snapshot["secret"],
                                    snapshot["protocol"],
                                )
                            elif which == 4:
                                opened, message = owner._open_network_confirm_dialog(
                                    "删除网络目录",
                                    "将删除「{}」的配置和全部本地镜像文件，且不可恢复。确认删除？".format(
                                        snapshot["name"]
                                    ),
                                    lambda: owner._run_network_action(
                                        owner.ACTION_NET_DELETE_PREFIX
                                        + snapshot["id"]
                                    ),
                                )
                                if not opened:
                                    owner._notify_app(message)
                        except Exception as exc:
                            try:
                                toast_class.makeText(
                                    activity,
                                    "操作失败: {}".format(exc),
                                    toast_class.LENGTH_LONG,
                                ).show()
                            except Exception:
                                owner._notify_app("操作失败: {}".format(exc))

                class ShowDialog(dynamic_proxy(runnable_class)):
                    def __init__(self):
                        super().__init__()
                        self._proxy_id = owner._retain_proxy(self)

                    def run(self):
                        try:
                            builder = builder_class(activity)
                            builder.setTitle("🌐 {}".format(snapshot["name"]))
                            menu_listener = MenuListener()
                            builder.setItems(labels, menu_listener)
                            dialog = builder.show()
                            owner._dialog_refs.extend([menu_listener, dialog])
                        finally:
                            owner._release_proxy(self._proxy_id)

                runner = ShowDialog()
                self._dialog_refs.append(runner)
                activity.runOnUiThread(runner)
            return True, ""
        except Exception as exc:
            return False, "网络目录菜单打开失败: {}".format(exc)

    def _open_network_edit_dialog(self, root_id=""):
        """添加 / 编辑网络根：名称、地址、协议、用户名、密码/Token。"""
        try:
            from java import dynamic_proxy, jclass

            toast_class = jclass("android.widget.Toast")
            edit_text_class = jclass("android.widget.EditText")
            linear_layout_class = jclass("android.widget.LinearLayout")
            scroll_view_class = jclass("android.widget.ScrollView")
            text_view_class = jclass("android.widget.TextView")
            input_type = jclass("android.text.InputType")
            click_listener = jclass(
                "android.content.DialogInterface$OnClickListener"
            )
            view_click_listener = jclass("android.view.View$OnClickListener")
            runnable_class = jclass("java.lang.Runnable")
            try:
                builder_class = jclass(
                    "com.google.android.material.dialog.MaterialAlertDialogBuilder"
                )
            except Exception:
                builder_class = jclass("android.app.AlertDialog$Builder")
            activity = self._current_android_activity(jclass)
            owner = self
            with self.lock:
                existing = self._network_root_by_id(root_id) if root_id else None
                initial = (
                    {
                        "name": str(existing.get("name", "")),
                        "url": str(existing.get("url", "")),
                        "protocol": str(existing.get("protocol", "auto")),
                        "username": str(existing.get("username", "")),
                        "secret": str(
                            existing.get("password", "")
                            or existing.get("token", "")
                        ),
                    }
                    if existing
                    else {
                        "name": "",
                        "url": "",
                        "protocol": "auto",
                        "username": "",
                        "secret": "",
                    }
                )
            dialog_title = "编辑网络目录" if existing else "添加网络目录"
            protocol_values = ["auto", "http", "webdav", "github", "gitee"]
            protocol_labels = [
                "自动识别（推荐）",
                "HTTP 静态目录",
                "WebDAV",
                "GitHub 仓库",
                "Gitee 仓库",
            ]
            holder = {"protocol": initial["protocol"]}

            with self._ProxyCreationLock(self):

                class SaveListener(dynamic_proxy(view_click_listener)):
                    def __init__(self, edits, protocol_view, dialog):
                        super().__init__()
                        self.edits = edits
                        self.protocol_view = protocol_view
                        self.dialog = dialog

                    def onClick(self, view):
                        name = str(self.edits["name"].getText().toString()).strip()
                        url = str(self.edits["url"].getText().toString()).strip()
                        username = str(
                            self.edits["username"].getText().toString()
                        ).strip()
                        secret = str(
                            self.edits["secret"].getText().toString()
                        ).strip()
                        try:
                            with owner.lock:
                                message = owner._save_network_root_form_locked(
                                    root_id,
                                    name,
                                    url,
                                    holder["protocol"],
                                    username,
                                    secret,
                                )
                            toast_class.makeText(
                                activity, message, toast_class.LENGTH_LONG
                            ).show()
                            try:
                                self.dialog.dismiss()
                            except Exception:
                                pass
                            owner._schedule_manager_page_refresh()
                        except Exception as exc:
                            toast_class.makeText(
                                activity,
                                "保存失败: {}".format(exc),
                                toast_class.LENGTH_LONG,
                            ).show()

                class TestListener(dynamic_proxy(view_click_listener)):
                    def __init__(self, edits):
                        super().__init__()
                        self.edits = edits

                    def onClick(self, view):
                        url = str(self.edits["url"].getText().toString()).strip()
                        username = str(
                            self.edits["username"].getText().toString()
                        ).strip()
                        secret = str(
                            self.edits["secret"].getText().toString()
                        ).strip()
                        if not owner._network_normalize_url(url):
                            toast_class.makeText(
                                activity,
                                "请先填写有效的 http(s) 地址",
                                toast_class.LENGTH_LONG,
                            ).show()
                            return
                        owner._network_start_probe_worker(
                            url, username, secret, holder["protocol"]
                        )
                        # v8.0：测试进度由独立进度对话框展示，不再弹 toast。

                class ProtocolRowListener(dynamic_proxy(view_click_listener)):
                    def __init__(self, label_view, edits):
                        super().__init__()
                        self.label_view = label_view
                        self.edits = edits

                    def onClick(self, view):
                        label_view_ref = self.label_view

                        class ItemListener(dynamic_proxy(click_listener)):
                            def onClick(self, inner_dialog, inner_which):
                                try:
                                    holder["protocol"] = protocol_values[inner_which]
                                    self_label = "协议：{} ▾".format(
                                        protocol_labels[inner_which]
                                    )
                                    label_view_ref.setText(self_label)
                                except Exception as exc:
                                    toast_class.makeText(
                                        activity,
                                        "协议选择失败: {}".format(exc),
                                        toast_class.LENGTH_LONG,
                                    ).show()

                        item_listener = ItemListener()
                        builder = builder_class(activity)
                        builder.setTitle("选择协议")
                        builder.setItems(protocol_labels, item_listener)
                        inner_dialog = builder.show()
                        owner._dialog_refs.extend([item_listener, inner_dialog])

                class CancelListener(dynamic_proxy(click_listener)):
                    def onClick(self, dialog, which):
                        return None

                class ShowDialog(dynamic_proxy(runnable_class)):
                    def __init__(self):
                        super().__init__()
                        self._proxy_id = owner._retain_proxy(self)

                    def run(self):
                        try:
                            density = float(
                                activity.getResources().getDisplayMetrics().density
                            )
                            padding = int(16 * density + 0.5)
                            row_gap = int(6 * density + 0.5)
                            container = linear_layout_class(activity)
                            container.setOrientation(linear_layout_class.VERTICAL)
                            container.setPadding(padding, row_gap, padding, row_gap)

                            def add_label(text):
                                label = text_view_class(activity)
                                label.setText(text)
                                label.setTextSize(13.0)
                                label.setPadding(0, row_gap, 0, 0)
                                container.addView(label)
                                return label

                            def add_input(hint, value, uri=False, secret_field=False):
                                edit = edit_text_class(activity)
                                edit.setSingleLine(True)
                                if uri:
                                    edit.setInputType(
                                        input_type.TYPE_CLASS_TEXT
                                        | input_type.TYPE_TEXT_VARIATION_URI
                                    )
                                elif secret_field:
                                    edit.setInputType(
                                        input_type.TYPE_CLASS_TEXT
                                        | input_type.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD
                                    )
                                else:
                                    edit.setInputType(input_type.TYPE_CLASS_TEXT)
                                edit.setHint(hint)
                                edit.setText(value)
                                edit.setSelection(len(value))
                                container.addView(edit)
                                return edit

                            warning = text_view_class(activity)
                            warning.setText(
                                "注意：镜像到本地的 py/js/html 源文件会在本机执行，仅添加你信任的地址。"
                            )
                            warning.setTextSize(12.0)
                            warning.setPadding(0, 0, 0, row_gap)
                            container.addView(warning)
                            add_label("名称（可空，自动取地址末段）")
                            name_edit = add_input("例如：客厅电视分享包", initial["name"])
                            add_label("目录地址 *")
                            url_edit = add_input(
                                "http://192.168.1.2:8181/本地包/py",
                                initial["url"],
                                uri=True,
                            )
                            add_label("协议（点击切换）")
                            protocol_view = text_view_class(activity)
                            current_index = (
                                protocol_values.index(holder["protocol"])
                                if holder["protocol"] in protocol_values
                                else 0
                            )
                            protocol_view.setText(
                                "协议：{} ▾".format(protocol_labels[current_index])
                            )
                            protocol_view.setTextSize(15.0)
                            protocol_view.setPadding(
                                0, row_gap, 0, row_gap
                            )
                            container.addView(protocol_view)
                            add_label("用户名（WebDAV 鉴权用，可空）")
                            username_edit = add_input(
                                "用户名", initial["username"]
                            )
                            add_label("密码 / Token（可空；GitHub/Gitee 私有库填 Token）")
                            secret_edit = add_input(
                                "密码或访问令牌",
                                initial["secret"],
                                secret_field=True,
                            )
                            edits = {
                                "name": name_edit,
                                "url": url_edit,
                                "username": username_edit,
                                "secret": secret_edit,
                            }
                            scroll = scroll_view_class(activity)
                            scroll.addView(container)
                            builder = builder_class(activity)
                            builder.setTitle(dialog_title)
                            builder.setView(scroll)
                            noop_cancel = CancelListener()
                            builder.setPositiveButton("保存", noop_cancel)
                            builder.setNeutralButton("测试连接", noop_cancel)
                            builder.setNegativeButton("取消", noop_cancel)
                            dialog = builder.show()
                            save_listener = SaveListener(
                                edits, protocol_view, dialog
                            )
                            test_listener = TestListener(edits)
                            protocol_listener = ProtocolRowListener(
                                protocol_view, edits
                            )
                            protocol_view.setOnClickListener(protocol_listener)
                            dialog.getButton(-1).setOnClickListener(save_listener)
                            dialog.getButton(-3).setOnClickListener(test_listener)
                            owner._dialog_refs.append(
                                [
                                    scroll,
                                    container,
                                    warning,
                                    name_edit,
                                    url_edit,
                                    protocol_view,
                                    username_edit,
                                    secret_edit,
                                    noop_cancel,
                                    save_listener,
                                    test_listener,
                                    protocol_listener,
                                    dialog,
                                ]
                            )
                        finally:
                            owner._release_proxy(self._proxy_id)

                runner = ShowDialog()
                self._dialog_refs.append(runner)
                activity.runOnUiThread(runner)
            return True, ""
        except Exception as exc:
            return False, "网络目录编辑窗口打开失败: {}".format(exc)

    def _save_network_root_form_locked(
        self, root_id, name, url, protocol, username, secret
    ):
        """表单保存逻辑（调用方持锁）。返回提示文案，失败抛异常。"""
        normalized_url = self._network_normalize_url(url)
        if not normalized_url:
            raise ValueError("地址必须是有效的 http(s) 链接")
        if protocol not in self.NETWORK_PROTOCOLS:
            protocol = "auto"
        if protocol in ("github", "gitee") and not self._network_git_host(
            normalized_url
        ):
            raise ValueError(
                "当前协议要求 {} 仓库链接，请改选自动识别或 HTTP/WebDAV".format(
                    "GitHub" if protocol == "github" else "Gitee"
                )
            )
        new_id = root_id or self._network_root_id(normalized_url)
        existing = self._network_root_by_id(new_id) if root_id else None
        if existing is None:
            for item in self.network_roots:
                if item.get("url") == normalized_url:
                    raise ValueError("该地址已存在：{}".format(item.get("name")))
            existing = {
                "id": new_id,
                "name": "",
                "url": normalized_url,
                "protocol": protocol,
                "username": "",
                "password": "",
                "token": "",
                "enabled": True,
                "last_sync": "",
                "last_status": "never",
                "last_message": "",
                "file_count": 0,
                "byte_count": 0,
            }
            self.network_roots.append(existing)
        existing["url"] = normalized_url
        existing["protocol"] = protocol
        existing["username"] = username[:128]
        existing["password"] = secret[:256]
        existing["token"] = secret[:256]
        if name:
            existing["name"] = name[:40]
        elif not existing.get("name"):
            existing["name"] = self._network_default_name(
                normalized_url, protocol
            )
        self.network_roots = self._normalize_network_roots(self.network_roots)
        self._save_settings()
        return "已保存「{}」，可点立即同步或直接点扫描".format(existing["name"])

    def _open_load_choice_dialog(self, source_id):
        """文件卡三选一窗口：永久加载 / 临时加载 / 取消（已加载时可移出）。"""
        try:
            from java import dynamic_proxy, jclass

            toast_class = jclass("android.widget.Toast")
            click_listener = jclass(
                "android.content.DialogInterface$OnClickListener"
            )
            runnable_class = jclass("java.lang.Runnable")
            try:
                builder_class = jclass(
                    "com.google.android.material.dialog.MaterialAlertDialogBuilder"
                )
            except Exception:
                builder_class = jclass("android.app.AlertDialog$Builder")
            activity = self._current_android_activity(jclass)
            owner = self

            with self.lock:
                source = self.cache.get("source_index", {}).get(source_id)
                if not source:
                    return False, "文件不在扫描结果中，请重新扫描"
                state = self._source_load_state(source)
                file_name = str(
                    source.get("name") or source.get("base_name") or source_id
                )
                relative = str(source.get("relative_in_root", ""))
                source_type = str(source.get("type", "")).upper()
                temp_supported = source_type == "PY"
                type_label = self.TYPE_LABEL.get(source_type, source_type or "未知")
                perm_action = self.ACTION_LOAD_PERM_PREFIX + source_id
                temp_action = self.ACTION_LOAD_TEMP_PREFIX + source_id
                unload_action = self.ACTION_UNLOAD_PREFIX + source_id

            with self._ProxyCreationLock(self):

                class ChoiceListener(dynamic_proxy(click_listener)):
                    """exec_action 为空表示仅提示，不执行加载。"""

                    def __init__(self, exec_action, toast_message):
                        super().__init__()
                        self.exec_action = exec_action
                        self.toast_message = toast_message

                    def onClick(self, dialog, which):
                        try:
                            if self.exec_action:
                                owner._run_load_choice_action(self.exec_action)
                            elif self.toast_message:
                                toast_class.makeText(
                                    activity,
                                    self.toast_message,
                                    toast_class.LENGTH_LONG,
                                ).show()
                        except Exception as exc:
                            try:
                                toast_class.makeText(
                                    activity,
                                    "操作失败: {}".format(exc),
                                    toast_class.LENGTH_LONG,
                                ).show()
                            except Exception:
                                owner._notify_app("操作失败: {}".format(exc))

                class ShowDialog(dynamic_proxy(runnable_class)):
                    def __init__(self):
                        super().__init__()
                        self._proxy_id = owner._retain_proxy(self)

                    def run(self):
                        try:
                            self._run_dialog()
                        except Exception as exc:
                            message = "加载选择窗口打开失败: {}".format(exc)
                            owner._log("ERROR", message)
                            try:
                                toast_class.makeText(
                                    activity, message, toast_class.LENGTH_LONG
                                ).show()
                            except Exception:
                                owner._notify_app(message)
                        finally:
                            owner._release_proxy(self._proxy_id)

                    def _run_dialog(self):
                        # 布局约定（Material/AlertDialog）：Neutral 单独居左，
                        # Negative+Positive 并列居右。
                        # 已加载：Neutral=移出加载、Negative=转为临时、Positive=保持
                        # 未加载：Neutral=屏蔽、Negative=临时加载、Positive=永久加载
                        block_action = owner.ACTION_BLOCK_PREFIX + source_id
                        if state == "perm":
                            if temp_supported:
                                message = (
                                    "文件：{}\n目录：{}\n类型：{}\n\n当前：永久加载\n"
                                    "退出 App 后仍然保留。"
                                ).format(file_name, relative, type_label)
                                positive = ChoiceListener("", "该文件已是永久加载")
                                positive_text = "仍为永久"
                                negative = ChoiceListener(temp_action, "")
                                negative_text = "转为临时加载"
                            else:
                                message = (
                                    "文件：{}\n目录：{}\n类型：{}\n\n当前：已加载\n"
                                    "退出 App 后仍然保留。"
                                ).format(file_name, relative, type_label)
                                positive = ChoiceListener("", "该文件已加载")
                                positive_text = "保持加载"
                                negative = None
                                negative_text = ""
                            neutral = ChoiceListener(unload_action, "")
                            neutral_text = "移出加载"
                        elif state == "temp":
                            message = (
                                "文件：{}\n目录：{}\n类型：{}\n\n当前：临时加载\n"
                                "退出 App 后将自动消失。"
                            ).format(file_name, relative, type_label)
                            positive = ChoiceListener(perm_action, "")
                            negative = None
                            neutral = ChoiceListener(unload_action, "")
                            positive_text = "转为永久加载"
                            negative_text = ""
                            neutral_text = "移出加载"
                        else:
                            if temp_supported:
                                message = (
                                    "文件：{}\n目录：{}\n类型：{}\n\n请选择加载方式：\n"
                                    "· 临时加载：直接注入当前 App（不写配置），"
                                    "退出 App 后自动消失\n"
                                    "· 永久加载：写入配置，重启后仍然保留"
                                ).format(file_name, relative, type_label)
                                negative = ChoiceListener(temp_action, "")
                                negative_text = "临时加载"
                                positive_text = "永久加载"
                            else:
                                message = (
                                    "文件：{}\n目录：{}\n类型：{}\n\n"
                                    "该类型仅支持加载：\n"
                                    "· 加载：写入配置，重启后仍然保留"
                                ).format(file_name, relative, type_label)
                                negative = None
                                negative_text = ""
                                positive_text = "加载"
                            positive = ChoiceListener(perm_action, "")
                            neutral = ChoiceListener(block_action, "")
                            neutral_text = "屏蔽"
                        builder = builder_class(activity)
                        builder.setTitle("加载站点文件")
                        builder.setMessage(message)
                        builder.setPositiveButton(positive_text, positive)
                        builder.setNeutralButton(neutral_text, neutral)
                        if negative is not None:
                            builder.setNegativeButton(negative_text, negative)
                        dialog = builder.show()
                        owner._dialog_refs.extend(
                            [
                                ref
                                for ref in (positive, neutral, negative, dialog)
                                if ref is not None
                            ]
                        )

                runner = ShowDialog()
                self._dialog_refs.append(runner)
                activity.runOnUiThread(runner)
            return True, ""
        except Exception as exc:
            return False, "加载选择窗口打开失败: {}".format(exc)

    def _normalize_package_download_url(self, value):
        url = str(value or "").strip().strip('"').strip("'")
        if not url:
            raise ValueError("下载地址不能为空")
        if len(url) > 2048:
            raise ValueError("下载地址过长")
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
            raise ValueError("下载地址必须是 http 或 https URL")
        return url

    def _package_download_url_identity(self, value):
        return self._encoded_download_url(value).casefold()

    def _package_request_headers(self, accept="*/*"):
        headers = {
            "User-Agent": "okhttp/4.12.0",
            "Accept": accept,
            "X-Device-ID": self.package_device_id,
            "X-Client-Version": self.VERSION,
            "Connection": "close",
        }
        if self._package_authorization_ticket:
            headers["X-Release-Ticket"] = self._package_authorization_ticket
        return headers

    def _package_service_error(self, error):
        status = int(getattr(error, "code", 0) or 0)
        headers = getattr(error, "headers", None)
        retry_after = str(headers.get("Retry-After", "") if headers else "").strip()
        code = str(headers.get("X-Package-Code", "") if headers else "").strip()
        message = ""
        try:
            payload = error.read(8192)
            data = json.loads(payload.decode("utf-8-sig"))
            if isinstance(data, dict):
                code = str(data.get("code", code) or code).strip()
                message = str(data.get("message", data.get("error", "")) or "").strip()
                retry_after = str(data.get("retryAfter", retry_after) or retry_after).strip()
        except Exception:
            pass
        try:
            retry_seconds = max(0, int(float(retry_after)))
        except Exception:
            retry_seconds = 0
        if code == "SERVICE_DISABLED":
            text = "接口已关闭：{}".format(message or "服务维护中，请稍后再试")
            return PackageServiceRequestError(text, status, code, retry_seconds)
        if code == "RATE_LIMITED":
            seconds = max(1, retry_seconds)
            wait = "{} 秒".format(seconds) if seconds < 60 else "{} 分钟".format((seconds + 59) // 60)
            text = "请求次数已达上限：{}（{}后重试）".format(message or "访问过于频繁", wait)
            return PackageServiceRequestError(text, status, code, seconds)
        if code == "CLIENT_UPGRADE_REQUIRED":
            text = message or "接口要求使用智能加载 v4.0 或更高版本"
            return PackageServiceRequestError(text, status, code, retry_seconds)
        text = message or "CF 接口返回 HTTP {}".format(status)
        return PackageServiceRequestError(text, status, code, retry_seconds)

    def _package_open_url(self, value, timeout=15, accept="*/*", method="GET"):
        url = self._normalize_package_download_url(value)
        request = urllib.request.Request(
            self._encoded_download_url(url),
            headers=self._package_request_headers(accept),
            method=str(method or "GET").upper(),
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            return opener.open(request, timeout=max(2, int(timeout)))
        except urllib.error.HTTPError as exc:
            raise self._package_service_error(exc)


    def _package_read_limited(self, response, limit, initial=b""):
        payload = bytearray(initial or b"")
        while True:
            chunk = response.read(min(128 * 1024, int(limit) + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > int(limit):
                raise ValueError("下载内容超过大小上限")
        return bytes(payload)

    def _package_parse_json_text(self, text):
        value = str(text or "").lstrip("\ufeff")
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            cleaned = self._strip_json_trailing_commas(
                self._strip_json_comments(value)
            )
            return json.loads(cleaned)


    def _package_download_site_type_label(self, item):
        sites = max(0, int(item.get("site_count", 0) or 0))
        dependencies = max(0, int(item.get("dependency_count", 0) or 0))
        lives = max(0, int(item.get("live_count", 0) or 0))
        source_type = str(item.get("source_type", "config")).lower()
        prefix = (
            "内置"
            if source_type == "builtin"
            else "ZIP"
            if source_type == "zip"
            else "接口"
        )
        return "{}{}/{}·直播{}".format(prefix, sites, dependencies, lives)

    def _package_download_sites_summary(self):
        return ", ".join(
            "{}[{}]:站{}·播{}·测{}".format(
                item.get("name", "未命名"),
                self._package_download_site_type_label(item),
                "开" if self._package_download_site_enabled(item) else "关",
                "开" if self._package_download_live_enabled(item) else "关",
                "开" if self._package_download_health_enabled(item) else "关",
            )
            for item in self.package_download_sites
        ) or "无"

    def _open_blocked_sources_dialog(self):
        try:
            from java import dynamic_proxy, jclass

            toast_class = jclass("android.widget.Toast")
            linear_layout_class = jclass("android.widget.LinearLayout")
            scroll_view_class = jclass("android.widget.ScrollView")
            text_view_class = jclass("android.widget.TextView")
            switch_class = jclass("android.widget.Switch")
            click_listener = jclass(
                "android.content.DialogInterface$OnClickListener"
            )
            view_click_listener = jclass("android.view.View$OnClickListener")
            runnable_class = jclass("java.lang.Runnable")
            try:
                builder_class = jclass(
                    "com.google.android.material.dialog.MaterialAlertDialogBuilder"
                )
            except Exception:
                builder_class = jclass("android.app.AlertDialog$Builder")
            activity = self._current_android_activity(jclass)
            owner = self
            blocked = sorted(
                self.cache.get("ignored", []),
                key=lambda item: (
                    str(item.get("name", "")).casefold(),
                    str(item.get("identity", "")),
                ),
            )
            if not blocked:
                return False, "当前没有屏蔽站点"

            with self._ProxyCreationLock(self):

                class NoopListener(dynamic_proxy(click_listener)):
                    def onClick(self, dialog, which):
                        return None

                class SelectAllListener(dynamic_proxy(view_click_listener)):
                    def __init__(self, switches):
                        super().__init__()
                        self.switches = switches

                    def onClick(self, view):
                        for control in self.switches.values():
                            control.setChecked(True)

                class RestoreListener(dynamic_proxy(view_click_listener)):
                    def __init__(self, switches, dialog):
                        super().__init__()
                        self.switches = switches
                        self.dialog = dialog

                    def onClick(self, view):
                        selected = [
                            source_id
                            for source_id, control in self.switches.items()
                            if bool(control.isChecked())
                        ]
                        if not selected:
                            toast_class.makeText(
                                activity, "请先选择站点", toast_class.LENGTH_SHORT
                            ).show()
                            return
                        try:
                            with owner.lock:
                                restored, reload_detail = owner._restore_blocked_sources(
                                    selected
                                )
                            toast_class.makeText(
                                activity,
                                "已解除 {} 个站点；{}".format(
                                    len(restored), reload_detail
                                ),
                                toast_class.LENGTH_LONG,
                            ).show()
                            self.dialog.dismiss()
                        except Exception as exc:
                            toast_class.makeText(
                                activity,
                                "批量解除屏蔽失败: {}".format(exc),
                                toast_class.LENGTH_LONG,
                            ).show()

                class ShowDialog(dynamic_proxy(runnable_class)):
                    def __init__(self):
                        super().__init__()
                        self._proxy_id = owner._retain_proxy(self)

                    def run(self):
                        try:
                            density = float(
                                activity.getResources().getDisplayMetrics().density
                            )
                            padding = int(16 * density + 0.5)
                            row_padding = int(8 * density + 0.5)
                            container = linear_layout_class(activity)
                            container.setOrientation(linear_layout_class.VERTICAL)
                            container.setPadding(padding, row_padding, padding, row_padding)
                            description = text_view_class(activity)
                            description.setText("选择多个站点后一次解除、一次加载")
                            description.setTextSize(13.0)
                            description.setPadding(0, 0, 0, row_padding)
                            container.addView(description)
                            switches = {}
                            for source in blocked:
                                control = switch_class(activity)
                                control.setText(
                                    "{} · {} · {}".format(
                                        source.get("name", "未命名"),
                                        source.get("type", ""),
                                        source.get("relative_in_root", ""),
                                    )
                                )
                                control.setTextSize(15.0)
                                control.setChecked(False)
                                control.setPadding(0, row_padding, 0, row_padding)
                                control.setFocusable(True)
                                container.addView(control)
                                switches[str(source.get("id", ""))] = control
                            scroll = scroll_view_class(activity)
                            scroll.addView(container)
                            noop_listener = NoopListener()
                            builder = builder_class(activity)
                            builder.setTitle("批量解除屏蔽")
                            builder.setView(scroll)
                            builder.setPositiveButton("解除选中", noop_listener)
                            builder.setNeutralButton("全选", noop_listener)
                            builder.setNegativeButton("取消", noop_listener)
                            dialog = builder.show()
                            restore_listener = RestoreListener(switches, dialog)
                            select_all_listener = SelectAllListener(switches)
                            dialog.getButton(-1).setOnClickListener(restore_listener)
                            dialog.getButton(-3).setOnClickListener(select_all_listener)
                            owner._dialog_refs.append(
                                [
                                    scroll,
                                    container,
                                    description,
                                    switches,
                                    noop_listener,
                                    restore_listener,
                                    select_all_listener,
                                    dialog,
                                ]
                            )
                        finally:
                            owner._release_proxy(self._proxy_id)

                runner = ShowDialog()
                self._dialog_refs.append(runner)
                activity.runOnUiThread(runner)
            return True, ""
        except Exception as exc:
            return False, "批量解除屏蔽界面打开失败: {}".format(exc)

    def _open_browser_batch_select_dialog(self, dir_path=""):
        """文件浏览批量选择对话框：列出指定目录下的站点，支持多选后批量操作。"""
        try:
            from java import dynamic_proxy, jclass

            builder_class = jclass("android.app.AlertDialog$Builder")
            linear_layout_class = jclass("android.widget.LinearLayout")
            switch_class = jclass("android.widget.Switch")
            scroll_view_class = jclass("android.widget.ScrollView")
            text_view_class = jclass("android.widget.TextView")
            toast_class = jclass("android.widget.Toast")
            activity = self._current_android_activity(jclass)
            if activity is None:
                return False, "当前没有可用 Activity"
            click_listener = jclass("android.content.DialogInterface$OnClickListener")
            view_click_listener = jclass("android.view.View$OnClickListener")
            runnable_class = jclass("java.lang.Runnable")

            all_sources = self.cache.get("sources", [])
            if not all_sources:
                return False, "没有可操作的站点"
            # 按目录过滤
            if dir_path:
                real_dir = os.path.realpath(os.path.abspath(os.path.expanduser(dir_path)))
                groups = self._browser_root_groups()
                matched_root = None
                best_len = -1
                for root_path, _root_types, _display_name in groups:
                    if not self._safe_path_within(real_dir, root_path):
                        continue
                    root_len = len(os.path.normcase(root_path))
                    if root_len > best_len:
                        best_len = root_len
                        matched_root = root_path
                if matched_root:
                    rel_dir = os.path.relpath(real_dir, matched_root)
                    prefix = "" if rel_dir == "." else rel_dir.replace(os.sep, "/").strip("/") + "/"
                    matched_norm = os.path.normcase(matched_root)
                    filtered = []
                    for source in all_sources:
                        scan_root = str(source.get("scan_root", "")).strip()
                        if not scan_root:
                            continue
                        if os.path.normcase(os.path.realpath(os.path.abspath(scan_root))) != matched_norm:
                            continue
                        rel = str(source.get("relative_in_root", "")).replace("\\", "/")
                        if not rel.startswith(prefix):
                            continue
                        tail = rel[len(prefix):]
                        if not tail or "/" in tail:
                            continue
                        filtered.append(source)
                    all_sources = filtered
            if not all_sources:
                return False, "当前目录没有可操作的站点"
            all_sources = sorted(
                all_sources,
                key=lambda item: (
                    str(item.get("type", "")).casefold(),
                    str(item.get("name", "")).casefold(),
                ),
            )
            owner = self

            with self._ProxyCreationLock(self):

                class NoopListener(dynamic_proxy(click_listener)):
                    def onClick(self, dialog, which):
                        return None

                class SelectAllListener(dynamic_proxy(view_click_listener)):
                    def __init__(self, switches):
                        super().__init__()
                        self.switches = switches

                    def onClick(self, view):
                        for control in self.switches.values():
                            control.setChecked(True)

                class DismissListener(dynamic_proxy(view_click_listener)):
                    """仅关闭对话框的按钮监听器（View$OnClickListener）。"""

                    def __init__(self, dialog):
                        super().__init__()
                        self.dialog = dialog

                    def onClick(self, view):
                        self.dialog.dismiss()

                class BatchActionListener(dynamic_proxy(view_click_listener)):
                    """批量操作监听器：action_type = block/temp/perm/unload"""

                    def __init__(self, switches, dialog, action_type):
                        super().__init__()
                        self.switches = switches
                        self.dialog = dialog
                        self.action_type = action_type

                    def onClick(self, view):
                        selected = [
                            source_id
                            for source_id, control in self.switches.items()
                            if bool(control.isChecked())
                        ]
                        if not selected:
                            toast_class.makeText(
                                activity, "请先选择站点", toast_class.LENGTH_SHORT
                            ).show()
                            return
                        try:
                            success, failed = 0, 0
                            for source_id in selected:
                                try:
                                    ok = self._do_action(source_id)
                                    if ok:
                                        success += 1
                                    else:
                                        failed += 1
                                except Exception:
                                    failed += 1
                            action_label = {
                                "block": "屏蔽",
                                "temp": "临时加载",
                                "perm": "永久加载",
                                "unload": "移出加载",
                            }.get(self.action_type, "操作")
                            toast_class.makeText(
                                activity,
                                "已{} {} 个{}".format(
                                    action_label,
                                    success,
                                    "，失败 {} 个".format(failed) if failed else "",
                                ),
                                toast_class.LENGTH_LONG,
                            ).show()
                            self.dialog.dismiss()
                            # 批量操作完成后刷新列表，让屏蔽/加载/移出生效
                            owner._schedule_manager_page_refresh()
                        except Exception as exc:
                            toast_class.makeText(
                                activity,
                                "批量操作失败: {}".format(exc),
                                toast_class.LENGTH_LONG,
                            ).show()

                    def _do_action(self, source_id):
                        """根据 action_type 执行对应操作，返回是否成功"""
                        if self.action_type == "block":
                            # 屏蔽：先移出加载，再持久化到 manual_ignored_sources，
                            # 并从 sources 中移除；只写 manual 集合同步 ignored_sources，
                            # 否则刷新/重启后快照恢复会丢失屏蔽状态。
                            with owner.lock:
                                ok, _ = owner._unload_file_locked(source_id)
                            source = owner.cache.get("source_index", {}).get(source_id)
                            if source:
                                identity = str(source.get("identity", ""))
                                if identity:
                                    with owner.lock:
                                        owner.manual_ignored_sources.add(identity)
                                        owner._sync_ignored_sources()
                                        ignored = owner.cache.get("ignored", [])
                                        if not isinstance(ignored, list):
                                            ignored = []
                                            owner.cache["ignored"] = ignored
                                        already = any(
                                            str(item.get("identity", "")) == identity
                                            for item in ignored
                                        )
                                        if not already:
                                            source["ignored"] = True
                                            ignored.append(source)
                                        # 从 sources 列表中移除被屏蔽的站点
                                        owner.cache["sources"] = [
                                            item
                                            for item in owner.cache.get("sources", [])
                                            if str(item.get("id", "")) != source_id
                                        ]
                                        # 更新类型计数
                                        source_type = str(source.get("type", "")).upper()
                                        if source_type in owner.cache.get("type_counts", {}):
                                            owner.cache["type_counts"][source_type] = max(
                                                0,
                                                owner.cache["type_counts"].get(source_type, 0)
                                                - 1,
                                            )
                                        owner._save_settings()
                                        try:
                                            owner._save_scan_snapshot()
                                        except Exception:
                                            pass
                            return True
                        elif self.action_type == "temp":
                            # 临时加载：先移出（如果已加载），再临时加载
                            with owner.lock:
                                owner._unload_file_locked(source_id)
                                ok, _ = owner._load_single_file_locked(source_id, True)
                            return ok
                        elif self.action_type == "perm":
                            # 永久加载：先移出（如果已加载），再永久加载
                            with owner.lock:
                                owner._unload_file_locked(source_id)
                                ok, _ = owner._load_single_file_locked(source_id, False)
                            return ok
                        elif self.action_type == "unload":
                            # 移出加载
                            with owner.lock:
                                ok, _ = owner._unload_file_locked(source_id)
                            return ok
                        return False

                class ShowDialog(dynamic_proxy(runnable_class)):
                    def __init__(self):
                        super().__init__()
                        self._proxy_id = owner._retain_proxy(self)

                    def run(self):
                        try:
                            density = float(
                                activity.getResources().getDisplayMetrics().density
                            )
                            padding = int(16 * density + 0.5)
                            row_padding = int(8 * density + 0.5)
                            container = linear_layout_class(activity)
                            container.setOrientation(linear_layout_class.VERTICAL)
                            container.setPadding(padding, row_padding, padding, row_padding)
                            description = text_view_class(activity)
                            description.setText("选择站点后批量操作：屏蔽/临时加载/永久加载/移出加载")
                            description.setTextSize(13.0)
                            description.setPadding(0, 0, 0, row_padding)
                            container.addView(description)
                            switches = {}
                            for source in all_sources:
                                control = switch_class(activity)
                                state = owner._source_load_state(source)
                                state_label = {
                                    "perm": "🟢永久",
                                    "temp": "🟡临时",
                                    "none": "⚪未加载",
                                }.get(state, "⚪未加载")
                                control.setText(
                                    "{} {} · {} · {}".format(
                                        state_label,
                                        source.get("name", "未命名"),
                                        source.get("type", ""),
                                        source.get("relative_in_root", ""),
                                    )
                                )
                                control.setTextSize(15.0)
                                control.setChecked(False)
                                control.setPadding(0, row_padding, 0, row_padding)
                                control.setFocusable(True)
                                container.addView(control)
                                switches[str(source.get("id", ""))] = control
                            scroll = scroll_view_class(activity)
                            scroll.addView(container)
                            noop_listener = NoopListener()
                            builder = builder_class(activity)
                            builder.setTitle("批量选择 ({} 个站点)".format(len(all_sources)))
                            builder.setView(scroll)
                            # 检查目录中是否全是 PY 类型，决定按钮布局
                            all_py = all(
                                str(source.get("type", "")).upper() == "PY"
                                for source in all_sources
                            )
                            if all_py:
                                # 全是 PY：Neutral=屏蔽、Negative=临时加载、Positive=永久加载
                                builder.setPositiveButton("永久加载", noop_listener)
                                builder.setNeutralButton("屏蔽", noop_listener)
                                builder.setNegativeButton("临时加载", noop_listener)
                            else:
                                # 含非 PY：Neutral=屏蔽、Negative=加载（永久）、Positive=取消
                                builder.setPositiveButton("取消", noop_listener)
                                builder.setNeutralButton("屏蔽", noop_listener)
                                builder.setNegativeButton("加载", noop_listener)
                            dialog = builder.show()
                            block_listener = BatchActionListener(switches, dialog, "block")
                            if all_py:
                                temp_listener = BatchActionListener(switches, dialog, "temp")
                                perm_listener = BatchActionListener(switches, dialog, "perm")
                                unload_listener = None
                                dismiss_listener = None
                            else:
                                temp_listener = None
                                perm_listener = BatchActionListener(switches, dialog, "perm")
                                unload_listener = BatchActionListener(switches, dialog, "unload")
                                dismiss_listener = DismissListener(dialog)
                            select_all_listener = SelectAllListener(switches)
                            owner._dialog_refs.extend(
                                [
                                    block_listener,
                                    temp_listener,
                                    perm_listener,
                                    unload_listener,
                                    dismiss_listener,
                                    select_all_listener,
                                    noop_listener,
                                    dialog,
                                ]
                            )
                            if all_py:
                                dialog.getButton(dialog.BUTTON_POSITIVE).setOnClickListener(
                                    perm_listener
                                )
                                dialog.getButton(dialog.BUTTON_NEUTRAL).setOnClickListener(
                                    block_listener
                                )
                                dialog.getButton(dialog.BUTTON_NEGATIVE).setOnClickListener(
                                    temp_listener
                                )
                            else:
                                dialog.getButton(dialog.BUTTON_POSITIVE).setOnClickListener(
                                    dismiss_listener
                                )
                                dialog.getButton(dialog.BUTTON_NEUTRAL).setOnClickListener(
                                    block_listener
                                )
                                dialog.getButton(dialog.BUTTON_NEGATIVE).setOnClickListener(
                                    perm_listener
                                )
                        except Exception as exc:
                            toast_class.makeText(
                                activity,
                                "批量选择界面异常: {}".format(exc),
                                toast_class.LENGTH_LONG,
                            ).show()

                runner = ShowDialog()
                owner._dialog_refs.append(runner)
                activity.runOnUiThread(runner)
            return True, ""
        except Exception as exc:
            return False, "批量选择界面打开失败: {}".format(exc)

    def _open_source_metadata_dialog(self):
        try:
            from java import dynamic_proxy, jclass

            toast_class = jclass("android.widget.Toast")
            linear_layout_class = jclass("android.widget.LinearLayout")
            edit_text_class = jclass("android.widget.EditText")
            switch_class = jclass("android.widget.Switch")
            input_type = jclass("android.text.InputType")
            click_listener = jclass(
                "android.content.DialogInterface$OnClickListener"
            )
            runnable_class = jclass("java.lang.Runnable")
            try:
                builder_class = jclass(
                    "com.google.android.material.dialog.MaterialAlertDialogBuilder"
                )
            except Exception:
                builder_class = jclass("android.app.AlertDialog$Builder")
            activity = self._current_android_activity(jclass)
            owner = self
            sources = sorted(
                self.cache.get("sources", []) + self.cache.get("ignored", []),
                key=lambda item: (
                    str(item.get("name", "")).casefold(),
                    str(item.get("identity", "")),
                ),
            )
            if not sources:
                return False, "暂无站点，请先扫描"

            with self._ProxyCreationLock(self):

                class CancelListener(dynamic_proxy(click_listener)):
                    def onClick(self, dialog, which):
                        return None

                class SaveListener(dynamic_proxy(click_listener)):
                    def __init__(self, source, favorite_control, tags_edit):
                        super().__init__()
                        self.source = source
                        self.favorite_control = favorite_control
                        self.tags_edit = tags_edit

                    def onClick(self, dialog, which):
                        try:
                            with owner.lock:
                                saved = owner._set_source_metadata(
                                    self.source.get("identity", ""),
                                    favorite=bool(self.favorite_control.isChecked()),
                                    tags=str(self.tags_edit.getText().toString()),
                                )
                            toast_class.makeText(
                                activity,
                                "已保存：{} · 收藏{} · 标签 {}".format(
                                    self.source.get("name", "站点"),
                                    "开" if saved["favorite"] else "关",
                                    "、".join(saved["tags"]) or "无",
                                ),
                                toast_class.LENGTH_LONG,
                            ).show()
                            owner._schedule_manager_page_refresh()
                        except Exception as exc:
                            toast_class.makeText(
                                activity,
                                "收藏与标签保存失败: {}".format(exc),
                                toast_class.LENGTH_LONG,
                            ).show()

                def show_editor(source):
                    density = float(activity.getResources().getDisplayMetrics().density)
                    padding = int(16 * density + 0.5)
                    row_padding = int(8 * density + 0.5)
                    metadata = owner._source_metadata_for(source)
                    container = linear_layout_class(activity)
                    container.setOrientation(linear_layout_class.VERTICAL)
                    container.setPadding(padding, row_padding, padding, 0)
                    favorite_control = switch_class(activity)
                    favorite_control.setText("收藏")
                    favorite_control.setChecked(bool(metadata.get("favorite", False)))
                    favorite_control.setPadding(0, row_padding, 0, row_padding)
                    container.addView(favorite_control)
                    tags_edit = edit_text_class(activity)
                    tags_edit.setSingleLine(False)
                    tags_edit.setInputType(input_type.TYPE_CLASS_TEXT)
                    tags_edit.setHint("标签用逗号分隔，最多 8 个")
                    tags_edit.setText("，".join(owner._normalize_source_tags(metadata.get("tags", []))))
                    container.addView(tags_edit)
                    save_listener = SaveListener(source, favorite_control, tags_edit)
                    cancel_listener = CancelListener()
                    builder = builder_class(activity)
                    builder.setTitle(str(source.get("name", "收藏与标签")))
                    builder.setView(container)
                    builder.setPositiveButton("保存", save_listener)
                    builder.setNegativeButton("取消", cancel_listener)
                    dialog = builder.show()
                    owner._dialog_refs.append(
                        [container, favorite_control, tags_edit, save_listener, cancel_listener, dialog]
                    )

                class SelectListener(dynamic_proxy(click_listener)):
                    def onClick(self, dialog, which):
                        index = int(which)
                        if 0 <= index < len(sources):
                            show_editor(sources[index])

                class ShowDialog(dynamic_proxy(runnable_class)):
                    def __init__(self):
                        super().__init__()
                        self._proxy_id = owner._retain_proxy(self)

                    def run(self):
                        try:
                            labels = []
                            for source in sources:
                                metadata = owner._source_metadata_for(source)
                                labels.append(
                                    "{}{} · {}{}".format(
                                        "★ " if metadata.get("favorite") else "",
                                        source.get("name", "未命名"),
                                        source.get("type", ""),
                                        " · " + "、".join(metadata.get("tags", []))
                                        if metadata.get("tags") else "",
                                    )
                                )
                            select_listener = SelectListener()
                            cancel_listener = CancelListener()
                            builder = builder_class(activity)
                            builder.setTitle("选择站点")
                            builder.setItems(labels, select_listener)
                            builder.setNegativeButton("取消", cancel_listener)
                            dialog = builder.show()
                            owner._dialog_refs.append(
                                [labels, select_listener, cancel_listener, dialog]
                            )
                        finally:
                            owner._release_proxy(self._proxy_id)

                runner = ShowDialog()
                self._dialog_refs.append(runner)
                activity.runOnUiThread(runner)
            return True, ""
        except Exception as exc:
            return False, "收藏与标签界面打开失败: {}".format(exc)

    def _open_scan_types_dialog(self):
        try:
            from java import dynamic_proxy, jclass

            toast_class = jclass("android.widget.Toast")
            linear_layout_class = jclass("android.widget.LinearLayout")
            text_view_class = jclass("android.widget.TextView")
            switch_class = jclass("android.widget.Switch")
            click_listener = jclass(
                "android.content.DialogInterface$OnClickListener"
            )
            view_click_listener = jclass("android.view.View$OnClickListener")
            runnable_class = jclass("java.lang.Runnable")
            try:
                builder_class = jclass(
                    "com.google.android.material.dialog.MaterialAlertDialogBuilder"
                )
            except Exception:
                builder_class = jclass("android.app.AlertDialog$Builder")
            activity = self._current_android_activity(jclass)
            owner = self

            with self._ProxyCreationLock(self):

                class NoopListener(dynamic_proxy(click_listener)):
                    def onClick(self, dialog, which):
                        return None

                class SaveButtonListener(dynamic_proxy(view_click_listener)):
                    def __init__(self, switches, adult_switch, dialog):
                        super().__init__()
                        self.switches = switches
                        self.adult_switch = adult_switch
                        self.dialog = dialog

                    def onClick(self, view):
                        values = {
                            source_type: bool(control.isChecked())
                            for source_type, control in self.switches.items()
                        }
                        try:
                            with owner.lock:
                                dirty = owner._set_pending_type_settings(
                                    values,
                                    block_adult_sites=bool(
                                        self.adult_switch.isChecked()
                                    ),
                                )
                            message = (
                                "扫描类型已保存，请点击应用并加载"
                                if dirty
                                else "扫描类型设置未变更"
                            )
                            toast_class.makeText(
                                activity, message, toast_class.LENGTH_LONG
                            ).show()
                            self.dialog.dismiss()
                        except Exception as exc:
                            toast_class.makeText(
                                activity,
                                "扫描类型保存失败: {}".format(exc),
                                toast_class.LENGTH_LONG,
                            ).show()

                class ShowDialog(dynamic_proxy(runnable_class)):
                    def __init__(self):
                        super().__init__()
                        self._proxy_id = owner._retain_proxy(self)

                    def run(self):
                        try:
                            try:
                                self._run_dialog()
                            except Exception as exc:
                                message = "扫描类型开关打开失败: {}".format(exc)
                                owner._log("ERROR", message)
                                try:
                                    toast_class.makeText(
                                        activity, message, toast_class.LENGTH_LONG
                                    ).show()
                                except Exception:
                                    owner._notify_app(message)
                        finally:
                            owner._release_proxy(self._proxy_id)

                    def _run_dialog(self):
                        density = float(
                            activity.getResources().getDisplayMetrics().density
                        )
                        padding = int(16 * density + 0.5)
                        row_padding = int(8 * density + 0.5)
                        container = linear_layout_class(activity)
                        container.setOrientation(linear_layout_class.VERTICAL)
                        container.setPadding(padding, row_padding, padding, 0)
                        description = text_view_class(activity)
                        description.setText(
                            "选择扫描时读取的站点类型"
                        )
                        description.setTextSize(13.0)
                        description.setPadding(0, 0, 0, row_padding)
                        container.addView(description)
                        switches = {}
                        for source_type in owner.TYPE_ORDER:
                            control = switch_class(activity)
                            control.setText(
                                "{} 扫描".format(
                                    owner.TYPE_LABEL.get(source_type, source_type)
                                )
                            )
                            control.setTextSize(16.0)
                            control.setChecked(
                                bool(
                                    owner.pending_type_enabled.get(
                                        source_type,
                                        owner.type_enabled.get(source_type, True),
                                    )
                                )
                            )
                            control.setPadding(0, row_padding, 0, row_padding)
                            control.setFocusable(True)
                            container.addView(control)
                            switches[source_type] = control
                        adult_switch = switch_class(activity)
                        adult_switch.setText("🔞站点 扫描")
                        adult_switch.setTextSize(16.0)
                        adult_switch.setChecked(
                            bool(owner.pending_block_adult_sites)
                        )
                        adult_switch.setPadding(0, row_padding, 0, row_padding)
                        adult_switch.setFocusable(True)
                        container.addView(adult_switch)
                        noop_listener = NoopListener()
                        builder = builder_class(activity)
                        builder.setTitle("扫描类型开关")
                        builder.setView(container)
                        builder.setPositiveButton("保存", noop_listener)
                        builder.setNegativeButton("取消", noop_listener)
                        dialog = builder.show()
                        save_listener = SaveButtonListener(
                            switches, adult_switch, dialog
                        )
                        dialog.getButton(-1).setOnClickListener(save_listener)
                        owner._dialog_refs.append(
                            [
                                container,
                                description,
                                switches,
                                adult_switch,
                                noop_listener,
                                save_listener,
                                dialog,
                            ]
                        )

                runner = ShowDialog()
                self._dialog_refs.append(runner)
                activity.runOnUiThread(runner)
            return True, ""
        except Exception as exc:
            return False, "扫描类型开关打开失败: {}".format(exc)

    def _open_status_dialog(self):
        try:
            from java import dynamic_proxy, jclass

            text_view_class = jclass("android.widget.TextView")
            scroll_view_class = jclass("android.widget.ScrollView")
            click_listener = jclass(
                "android.content.DialogInterface$OnClickListener"
            )
            runnable_class = jclass("java.lang.Runnable")
            try:
                builder_class = jclass(
                    "com.google.android.material.dialog.MaterialAlertDialogBuilder"
                )
            except Exception:
                builder_class = jclass("android.app.AlertDialog$Builder")
            activity = self._current_android_activity(jclass)
            owner = self

            def _status_content():
                test_counts = {
                    "available": 0,
                    "unavailable": 0,
                    "limited": 0,
                }
                playback_counts = {}
                for result in list(owner.site_test_results.values()):
                    state = (
                        str(result.get("state", ""))
                        if isinstance(result, dict)
                        else ""
                    )
                    if state in test_counts:
                        test_counts[state] += 1
                    if isinstance(result, dict):
                        playback = str(
                            result.get("playback_state", "") or ""
                        ).strip()
                        if playback:
                            playback_counts[playback] = (
                                playback_counts.get(playback, 0) + 1
                            )
                playback_text = " · ".join(
                    "{} {}".format(name, count)
                    for name, count in sorted(playback_counts.items())
                ) or "无"
                types_text = " ".join(
                    "{}:{}{}".format(
                        owner.TYPE_LABEL.get(t, t),
                        "开" if owner.type_enabled.get(t, True) else "关",
                        "->{}".format(
                            "开"
                            if owner.pending_type_enabled.get(
                                t, owner.type_enabled.get(t, True)
                            )
                            else "关"
                        )
                        if owner.pending_type_enabled.get(
                            t, owner.type_enabled.get(t, True)
                        )
                        != owner.type_enabled.get(t, True)
                        else "",
                    )
                    for t in owner.TYPE_ORDER
                )
                source_type_counts = {}
                for _source in owner.cache["sources"]:
                    _src_type = str(
                        _source.get("type", "") if isinstance(_source, dict) else ""
                    ).upper()
                    source_type_counts[_src_type] = (
                        source_type_counts.get(_src_type, 0) + 1
                    )
                source_type_text = " · ".join(
                    "{} {}".format(
                        owner.TYPE_LABEL.get(t, t), source_type_counts.get(t, 0)
                    )
                    for t in owner.TYPE_ORDER
                    if source_type_counts.get(t, 0)
                ) or "-"
                _name_holder = {}
                for _src in list(owner.cache.get("sources", [])) + list(
                    owner.cache.get("ignored", [])
                ):
                    if isinstance(_src, dict) and _src.get("identity"):
                        _name_holder[_src["identity"]] = str(
                            _src.get("name", "未命名站点")
                        )
                limited_lines = []
                for _identity, _result in list(owner.site_test_results.items()):
                    if not isinstance(_result, dict):
                        continue
                    if str(_result.get("state", "")) != "limited":
                        continue
                    _lname = _name_holder.get(_identity, _identity)
                    _ldetail = str(_result.get("detail", "") or "未说明原因")
                    _ldetail = " ".join(_ldetail.split())[:80]
                    limited_lines.append("  · {}：{}".format(_lname, _ldetail))
                limited_section = (
                    ["受限明细："] + limited_lines
                    if limited_lines
                    else []
                )
                # 计算无效站点明细
                skipped_count = owner.status.get("skipped", 0)
                duplicates_count = owner.status.get("duplicates", 0)
                adult_filtered = owner.status.get("adult_filtered", 0)
                compatibility_blocked = owner.status.get("compatibility_blocked", 0)
                ignored_count = len(owner.cache.get("ignored", []))
                stale_removed = owner.status.get("stale_ignored_removed", 0)

                # 文件去向明细 - 始终显示所有字段
                file_breakdown = []
                file_breakdown.append(
                    "有效站点：{} 个".format(len(owner.cache["sources"]))
                )
                file_breakdown.append(
                    "跳过文件：{} 个".format(skipped_count)
                )
                file_breakdown.append(
                    "重复文件：{} 个".format(duplicates_count)
                )
                if adult_filtered:
                    file_breakdown.append(
                        "成人过滤：{} 个".format(adult_filtered)
                    )
                if compatibility_blocked:
                    file_breakdown.append(
                        "兼容拦截：{} 个".format(compatibility_blocked)
                    )
                file_breakdown.append(
                    "已屏蔽站点：{} 个".format(ignored_count)
                )
                if stale_removed:
                    file_breakdown.append(
                        "过期屏蔽清除：{} 个".format(stale_removed)
                    )

                return "\n".join(
                    [
                        "版本：{}".format(owner.VERSION),
                        "运行环境：{}".format(owner._app_mode_label()),
                        "",
                        "扫描时间：{}".format(owner.status["scan_time"]),
                        "发现文件：{}".format(owner.status["found"]),
                        "待应用配置：{}".format(
                            "未应用" if owner.config_dirty else "已应用"
                        ),
                        "写入状态：{}".format(owner.status["write_state"]),
                        "类型开关：{}".format(types_text or "-"),
                        "",
                    ]
                    + file_breakdown
                    + [
                        "源分类：{}".format(source_type_text),
                        "集成直播：{} 个".format(
                            len(owner.cache.get("lives", []))
                        ),
                        "",
                        "功能测活：可用 {0} · 失效 {1} · 受限 {2}".format(
                            test_counts["available"],
                            test_counts["unavailable"],
                            test_counts["limited"],
                        ),
                    ]
                    + limited_section
                    + [
                        "播放验证：{}".format(playback_text),
                        "",
                        "最近错误：{}".format(
                            owner.status["error"] or "无"
                        ),
                    ]
                )

            with self._ProxyCreationLock(self):

                class DismissListener(dynamic_proxy(click_listener)):
                    def onClick(self, dialog, which):
                        return None

                class ShowDialog(dynamic_proxy(runnable_class)):
                    def __init__(self):
                        super().__init__()
                        self._proxy_id = owner._retain_proxy(self)

                    def run(self):
                        try:
                            try:
                                self._run_dialog()
                            except Exception as exc:
                                message = "运行状态对话框打开失败: {}".format(exc)
                                owner._log("ERROR", message)
                                owner._notify_app(message)
                        finally:
                            owner._release_proxy(self._proxy_id)

                    def _run_dialog(self):
                        density = float(
                            activity.getResources().getDisplayMetrics().density
                        )
                        padding = int(16 * density + 0.5)
                        text = text_view_class(activity)
                        text.setText(_status_content())
                        text.setTextSize(14.0)
                        text.setLineSpacing(0.0, 1.25)
                        text.setPadding(padding, padding, padding, padding)
                        text.setTextIsSelectable(True)
                        scroll = scroll_view_class(activity)
                        scroll.addView(text)
                        dismiss_listener = DismissListener()
                        builder = builder_class(activity)
                        builder.setTitle("运行状态与诊断")
                        builder.setView(scroll)
                        builder.setPositiveButton("确定", dismiss_listener)
                        dialog = builder.show()
                        owner._dialog_refs.extend(
                            [text, scroll, dismiss_listener, dialog]
                        )

                runner = ShowDialog()
                self._dialog_refs.append(runner)
                activity.runOnUiThread(runner)
            return True, ""
        except Exception as exc:
            return False, "运行状态对话框打开失败: {}".format(exc)

    def _open_action_dialog(self, kind, extra_desc=""):
        """为首页管理卡片 / 设置页执行项弹出「确认执行」原生对话框，确认后复用为「进度详情面板」。
        - 确认前：展示确认框（标题 + 说明 + 确认/取消）。
        - 确认后：复用同一对话框切换为「运行中」模式，实时显示任务进度与详情，
          可取消当前进度（站点测活/重新检测），或显示完成/失败汇总。
        - extra_desc：可选，额外追加在描述末尾的说明（如「恢复至...」展示备份名称）。
        """
        try:
            from java import dynamic_proxy, jclass

            ACTIONS = {
                "scan_only": {
                    "title": "扫描",
                    "desc": (
                        "只扫描设定好的目录，结果在「文件浏览」分类中展示，\n"
                        "可像文件管理器一样进入文件夹挑选文件。\n\n"
                        "扫描不会改写站点配置，也不会重载 App。"
                    ),
                    "running_title": "正在扫描…",
                    "destructive": False,
                    "cancellable": False,
                    "exec_action": self.ACTION_SCAN_ONLY,
                    "confirm_text": "开始扫描",
                },
                "load_all": {
                    "title": "加载全部",
                    "desc": (
                        "把当前扫描到的全部站点文件加载到 App。\n\n"
                        "按永久加载处理，重启 App 后仍然保留；\n"
                        "若只想临时加载个别文件，请到「文件浏览」中点选。"
                    ),
                    "running_title": "正在加载…",
                    "destructive": False,
                    "cancellable": False,
                    "exec_action": self.ACTION_LOAD_ALL,
                    "confirm_text": "永久加载全部",
                },
                "rescan": {
                    "title": "扫描并加载",
                    "desc": (
                        "将重新扫描本地目录，识别站点 / 直播文件并重载配置。\n\n"
                        "扫描期间请勿退出，完成后自动更新 App 站点列表。"
                    ),
                    "running_title": "正在扫描…",
                    "destructive": False,
                    "cancellable": False,
                    "exec_action": self.ACTION_RESCAN,
                    "confirm_text": "开始扫描",
                },
                "test_sites": {
                    "title": "站点功能测活",
                    "desc": (
                        "并发检测各站点的首页 / 分类 / 搜索 功能可用性。\n\n"
                        "后台逐站检测；确认后本框将实时显示每站进度与详情，\n"
                        "可随时取消当前进度。"
                    ),
                    "running_title": "正在测活…",
                    "destructive": False,
                    "cancellable": True,
                    "exec_action": self.ACTION_TEST_SITES,
                    "confirm_text": "开始检测",
                },
                "retest_sites": {
                    "title": "全部重新检测",
                    "desc": (
                        "清除缓存的测活结果，并重新并发检测全部站点的\n"
                        "首页 / 分类 / 搜索功能。\n\n"
                        "后台逐站检测；确认后本框将实时显示每站进度与详情，\n"
                        "可随时取消当前进度。"
                    ),
                    "running_title": "正在重新检测…",
                    "destructive": False,
                    "cancellable": True,
                    "exec_action": self.ACTION_RETEST_SITES,
                    "confirm_text": "重新检测",
                },
                "auto_classify": {
                    "title": "自动分类",
                    "desc": (
                        "将顶层源文件自动归入对应的类型子目录\n"
                        "（py / js / csp / html）。\n\n"
                        "便于后续扫描与管理，扫描类型需保持打开。"
                    ),
                    "running_title": "正在分类…",
                    "destructive": False,
                    "cancellable": False,
                    "exec_action": self.ACTION_AUTO_CLASSIFY,
                    "confirm_text": "执行分类",
                },
                "clear_sites": {
                    "title": "清除自动站点",
                    "desc": (
                        "清除全部自动生成的站点配置，\n"
                        "但保留手工注入的站点。\n\n"
                        "⚠ 被清除的自动站点将不再出现在 App 列表中；\n"
                        "若需恢复，请重新执行扫描后再加载。"
                    ),
                    "running_title": "正在清除…",
                    "destructive": True,
                    "cancellable": False,
                    "exec_action": self.ACTION_CLEAR_SITES,
                    "confirm_text": "确认清除",
                },
                "full_clear": {
                    "title": "一键清除",
                    "desc": (
                        "清除已加载站点、下载目录、缓存、\n"
                        "历史备份与收藏记录。\n\n"
                        "⚠ 该操作为不可撤销操作，执行后将恢复到初始状态。\n"
                        "用户原始文件及接口设置会被保留。"
                    ),
                    "running_title": "正在一键清除…",
                    "destructive": True,
                    "cancellable": False,
                    "exec_action": self.ACTION_FULL_CLEAR,
                    "confirm_text": "确认清除",
                },
                # ---- 设置页执行类项（统一确认框）----
                "reset_scan_base": {
                    "title": "恢复默认目录",
                    "desc": (
                        "将扫描目录恢复为默认本地目录。\n\n"
                        "该操作仅重置扫描根目录，不会删除已扫描的站点。"
                    ),
                    "running_title": "正在恢复默认目录…",
                    "destructive": False,
                    "cancellable": False,
                    "exec_action": self.ACTION_RESET_SCAN_BASE,
                    "confirm_text": "恢复默认",
                },
                "apply_scan": {
                    "title": "应用并扫描",
                    "desc": (
                        "应用当前扫描配置，并重新扫描本地目录。\n\n"
                        "v8.0：仅更新文件浏览结果，不写配置、不重载；\n"
                        "确认无误后请点击首页「加载全部」或进文件浏览点选。"
                    ),
                    "running_title": "正在应用并扫描…",
                    "destructive": False,
                    "cancellable": False,
                    "exec_action": self.ACTION_APPLY_SCAN_CONFIG,
                    "confirm_text": "开始扫描",
                },
                "export_profile": {
                    "title": "导出管理配置",
                    "desc": (
                        "将当前管理配置（目录、类型、过滤、收藏等）\n"
                        "导出为一个 JSON 配置文件。\n\n"
                        "导出文件位于备份目录，可用于日后导入恢复。"
                    ),
                    "running_title": "正在导出…",
                    "destructive": False,
                    "cancellable": False,
                    "exec_action": self.ACTION_EXPORT_PROFILE,
                    "confirm_text": "导出",
                },
                "import_profile": {
                    "title": "导入管理配置",
                    "desc": (
                        "从备份目录导入管理配置文件，覆盖当前配置。\n\n"
                        "⚠ 当前配置将被导入内容覆盖（导入前自动备份）。"
                    ),
                    "running_title": "正在导入…",
                    "destructive": True,
                    "cancellable": False,
                    "exec_action": self.ACTION_IMPORT_PROFILE,
                    "confirm_text": "导入并覆盖",
                },
                "restore_backup": {
                    "title": "恢复历史备份",
                    "desc": (
                        "将选定的历史备份快照恢复到当前配置。\n\n"
                        "⚠ 当前配置将被该备份覆盖，恢复后请「扫描」并「加载」应用。"
                    ),
                    "running_title": "正在恢复备份…",
                    "destructive": True,
                    "cancellable": False,
                    "exec_action": None,  # 动态填充，见下方
                    "confirm_text": "恢复",
                },
                "delete_backups": {
                    "title": "删除历史备份",
                    "desc": (
                        "删除全部历史备份文件。\n\n"
                        "⚠ 该操作不可撤销，删除后将无法恢复已备份的配置快照。"
                    ),
                    "running_title": "正在删除…",
                    "destructive": True,
                    "cancellable": False,
                    "exec_action": self.ACTION_DELETE_BACKUPS,
                    "confirm_text": "确认删除",
                },
                # ---- 设置页开关类项（也统一改为确认框）----
                "toggle_auto_scan": {
                    "title": "自动补扫",
                    "desc": (
                        "切换「扫描结果为空时自动补扫」开关。\n\n"
                        "确认后按当前开关状态取反：开启则空目录自动重扫，"
                        "关闭则仅执行手动扫描。"
                    ),
                    "running_title": "正在切换自动补扫…",
                    "destructive": False,
                    "cancellable": False,
                    "exec_action": self.ACTION_TOGGLE_AUTO_SCAN,
                    "confirm_text": "切换开关",
                },
                "toggle_auto_prune": {
                    "title": "自动清理屏蔽站点",
                    "desc": (
                        "切换「自动清理屏蔽站点」开关。\n\n"
                        "确认后按当前开关状态取反：开启则在测活后自动清理"
                        "被屏蔽的站点，关闭则保留。"
                    ),
                    "running_title": "正在切换自动清理…",
                    "destructive": False,
                    "cancellable": False,
                    "exec_action": self.ACTION_TOGGLE_AUTO_PRUNE,
                    "confirm_text": "切换开关",
                },
            }
            cfg = ACTIONS.get(kind)
            if cfg is None:
                return False, "未知对话框类型: {}".format(kind)
            # 「恢复至...」带动态备份名：由调用方通过 extra_desc 传入，这里据此补全 exec_action。
            if kind == "restore_backup" and extra_desc:
                cfg = dict(cfg)
                cfg["exec_action"] = self.ACTION_RESTORE_SNAPSHOT_PREFIX + extra_desc
                cfg["desc"] = cfg["desc"] + "\n\n备份文件：{}".format(extra_desc)

            text_view_class = jclass("android.widget.TextView")
            scroll_view_class = jclass("android.widget.ScrollView")
            click_listener = jclass(
                "android.content.DialogInterface$OnClickListener"
            )
            runnable_class = jclass("java.lang.Runnable")
            try:
                builder_class = jclass(
                    "com.google.android.material.dialog.MaterialAlertDialogBuilder"
                )
            except Exception:
                builder_class = jclass("android.app.AlertDialog$Builder")
            activity = self._current_android_activity(jclass)
            owner = self
            exec_action = cfg["exec_action"]
            destructive = cfg["destructive"]
            confirm_text = cfg["confirm_text"]
            cancellable = cfg.get("cancellable", False)

            # 预分配一个面板 key，避免关闭后旧面板误改写新面板。
            with self._progress_panel_lock:
                self._progress_panel_key += 1
                panel_key = self._progress_panel_key

            with self._ProxyCreationLock(self):

                class DismissListener(dynamic_proxy(click_listener)):
                    def onClick(self, dialog, which):
                        # 「取消」点击后对话框自动关闭；同步释放在途面板，
                        # 避免残留引用吞掉之后的进度更新。
                        owner._release_progress_panel(panel_key)

                class CancelProgressListener(dynamic_proxy(click_listener)):
                    """运行中点击「取消当前进度」：触发任务取消并收尾。"""

                    def onClick(self, dialog, which):
                        owner._cancel_progress_panel(panel_key)

                class ExecListener(dynamic_proxy(click_listener)):
                    """确认后：切换到运行模式，复用本框显示进度，启动后台任务。"""

                    def onClick(self, dialog, which):
                        # 确认前读取文件夹开关状态（仅测活类对话框存在）。
                        sw = getattr(owner, "_dialog_switches_ref", None)
                        if sw is not None:
                            for stype, control in sw.items():
                                try:
                                    owner._site_test_folder_switches[stype] = bool(
                                        control.isChecked()
                                    )
                                except Exception:
                                    pass
                        owner._start_panel_action(
                            panel_key, cfg, exec_action, cancellable
                        )

                class ShowDialog(dynamic_proxy(runnable_class)):
                    def __init__(self):
                        super().__init__()
                        self._proxy_id = owner._retain_proxy(self)

                    def run(self):
                        try:
                            try:
                                self._run_dialog()
                            except Exception as exc:
                                message = "{} 对话框打开失败: {}".format(
                                    cfg["title"], exc
                                )
                                owner._log("ERROR", message)
                                owner._notify_app(message)
                        finally:
                            owner._release_proxy(self._proxy_id)

                    def _run_dialog(self):
                        density = float(
                            activity.getResources().getDisplayMetrics().density
                        )
                        padding = int(16 * density + 0.5)
                        # 「站点功能测活」/「全部重新检测」文件夹开关所需的控件。
                        # 仅这两种测活类对话框显示开关，其他弹窗不显示。
                        linear_cls = jclass("android.widget.LinearLayout")
                        switch_cls = jclass("android.widget.Switch")
                        checked_listener = jclass(
                            "android.widget.CompoundButton$OnCheckedChangeListener"
                        )
                        is_site_test = kind in ("test_sites", "retest_sites")
                        container = linear_cls(activity)
                        container.setOrientation(
                            linear_cls.VERTICAL
                        )
                        container.setPadding(padding, padding, padding, 0)
                        text = text_view_class(activity)
                        text.setText(cfg["desc"])
                        text.setTextSize(15.0 if not destructive else 14.0)
                        text.setLineSpacing(0.0, 1.3)
                        text.setPadding(0, 0, 0, int(8 * density + 0.5))
                        text.setTextIsSelectable(True)
                        container.addView(text)
                        # v8.0：进度面板内嵌横向进度条，扫描/同步/测活等等待
                        # 操作可直观看到进度走到哪里；确认前隐藏，点确认后显示。
                        progress_bar_cls = jclass("android.widget.ProgressBar")
                        bar_attr = jclass("android.R$attr")
                        progress_bar = progress_bar_cls(
                            activity,
                            None,
                            bar_attr.progressBarStyleHorizontal,
                        )
                        bar_params = linear_cls.LayoutParams(
                            linear_cls.LayoutParams.MATCH_PARENT,
                            linear_cls.LayoutParams.WRAP_CONTENT,
                        )
                        bar_params.setMargins(
                            0, 0, 0, int(8 * density + 0.5)
                        )
                        progress_bar.setLayoutParams(bar_params)
                        progress_bar.setMax(100)
                        progress_bar.setProgress(0)
                        progress_bar.setIndeterminate(False)
                        progress_bar.setVisibility(8)  # View.GONE
                        container.addView(progress_bar)
                        # 保存当前对话框的文件夹开关容器供确认时核对（冗余但稳妥）。
                        switches = {}
                        if is_site_test:
                            owner._dialog_switches_ref = switches
                        if is_site_test:
                            for s_type in owner.TYPE_ORDER:
                                control = switch_cls(activity)
                                control.setText(
                                    "{} 文件夹".format(
                                        owner.TYPE_LABEL.get(s_type, s_type)
                                    )
                                )
                                control.setTextSize(15.0)
                                # 先按持久状态设定初始勾选，再注册监听，
                                # 避免 setChecked 触发 onCheckedChanged 误写旧值。
                                control.setChecked(
                                    bool(
                                        owner._site_test_folder_switches.get(
                                            s_type, True
                                        )
                                    )
                                )

                                class FolderSwitchChange(dynamic_proxy(checked_listener)):
                                    def onCheckedChanged(
                                        self, buttonView, isChecked, _folder_type=s_type
                                    ):
                                        # 拨动开关即实时记忆，下次打开对话框仍保持。
                                        # 用默认参数 _folder_type 绑定当前迭代类型，
                                        # 避免闭包共享循环变量 s_type 导致全部写入最后一类(HTML)。
                                        owner._site_test_folder_switches[_folder_type] = bool(
                                            isChecked
                                        )

                                control.setOnCheckedChangeListener(
                                    FolderSwitchChange()
                                )
                                control.setPadding(
                                    0, int(4 * density + 0.5), 0, int(4 * density + 0.5)
                                )
                                switches[s_type] = control
                                container.addView(control)
                        scroll = scroll_view_class(activity)
                        scroll.addView(container)
                        confirm_listener = ExecListener()
                        dismiss = DismissListener()
                        builder = builder_class(activity)
                        builder.setTitle(cfg["title"])
                        builder.setView(scroll)
                        builder.setPositiveButton(confirm_text, confirm_listener)
                        builder.setNegativeButton("取消", dismiss)
                        dialog = builder.show()
                        # v8.0 修复：AlertDialog 的按钮点击后默认会自动 dismiss，
                        # 进度面板（含进度条）会在点「开始」的瞬间被关闭、
                        # 后续进度更新全部写到不可见对话框上。这里覆盖确认按钮
                        # 为 View 级监听（不触发自动关闭），与批量选择等对话框一致。
                        view_click_listener = jclass(
                            "android.view.View$OnClickListener"
                        )

                        class ConfirmNoDismiss(
                            dynamic_proxy(view_click_listener)
                        ):
                            def onClick(self, view):
                                confirm_listener.onClick(dialog, -1)

                        confirm_no_dismiss = ConfirmNoDismiss()
                        dialog.getButton(-1).setOnClickListener(
                            confirm_no_dismiss
                        )
                        # 登记为在途进度面板（确认前仅保存句柄，确认后才对外可见）。
                        with owner._progress_panel_lock:
                            owner._active_progress_panel = {
                                "key": panel_key,
                                "dialog": dialog,
                                "text": text,
                                "bar": progress_bar,
                                "running": False,
                                "cancel_requested": False,
                            }
                        owner._dialog_refs.extend(
                            [
                                text,
                                progress_bar,
                                container,
                                scroll,
                                confirm_listener,
                                confirm_no_dismiss,
                                dismiss,
                                dialog,
                            ]
                        )

                runner = ShowDialog()
                self._dialog_refs.append(runner)
                activity.runOnUiThread(runner)
            return True, ""
        except Exception as exc:
            return False, "对话框打开失败: {}".format(exc)

    def _open_settings_action_dialog(self, real_action):
        """根据设置页的真实 action 解析 kind，弹出「确认执行」对话框。
        返回 (opened, message)；opened=False 时 message 为错误描述。
        """
        kind = None
        extra_desc = ""
        if real_action == self.ACTION_RESET_SCAN_BASE:
            kind = "reset_scan_base"
        elif real_action == self.ACTION_APPLY_SCAN_CONFIG:
            kind = "apply_scan"
        elif real_action == self.ACTION_EXPORT_PROFILE:
            kind = "export_profile"
        elif real_action == self.ACTION_IMPORT_PROFILE:
            kind = "import_profile"
        elif real_action == self.ACTION_DELETE_BACKUPS:
            kind = "delete_backups"
        elif real_action == self.ACTION_TOGGLE_AUTO_SCAN:
            kind = "toggle_auto_scan"
        elif real_action == self.ACTION_TOGGLE_AUTO_PRUNE:
            kind = "toggle_auto_prune"
        elif real_action.startswith(self.ACTION_RESTORE_SNAPSHOT_PREFIX):
            # 「恢复至...」动态参数：解析备份文件名并展示。
            name = os.path.basename(
                real_action[len(self.ACTION_RESTORE_SNAPSHOT_PREFIX):]
            )
            kind = "restore_backup"
            extra_desc = name
        if kind is None:
            return False, "未知的设置操作: {}".format(real_action)
        return self._open_action_dialog(kind, extra_desc=extra_desc)

    def _start_panel_action(self, panel_key, cfg, exec_action, cancellable):
        """确认动作：把确认框复用为「进度详情面板」并启动后台任务线程。"""

        def _worker():
            try:
                result = self.action(exec_action)
                msg = ""
                if isinstance(result, dict):
                    msg = str(result.get("msg", ""))
                elif result:
                    msg = str(result)
                if msg:
                    self._finish_progress_panel(panel_key, msg, ok=True)
            except Exception as exc:
                message = "执行失败: {}".format(exc)
                self._log("ERROR", message)
                self._finish_progress_panel(panel_key, message, ok=False)

        # 先把面板切换到运行模式（标题 + 复位按钮 + 初始提示）。
        try:
            from java import dynamic_proxy, jclass

            click_listener = jclass(
                "android.content.DialogInterface$OnClickListener"
            )
        except Exception:
            click_listener = None

        def _switch_to_running():
            with self._progress_panel_lock:
                panel = self._active_progress_panel
                if (
                    not panel
                    or panel.get("key") != panel_key
                    or panel.get("dialog") is None
                ):
                    # 面板已关闭/失效，仍照常执行后台任务。
                    self._launch_panel_worker(panel_key, _worker)
                    return
            panel["running"] = True
            panel["text"].setText("已启动：{}…".format(cfg["running_title"]))
            # 运行模式先展示不确定进度条，任务回传具体数值后切换为确定百分比。
            bar = panel.get("bar")
            if bar is not None:
                try:
                    bar.setVisibility(0)  # View.VISIBLE
                    bar.setMax(100)
                    bar.setProgress(0)
                    bar.setIndeterminate(True)
                except Exception:
                    pass
            try:
                panel["dialog"].setTitle(cfg["running_title"])
                activity = panel["dialog"].getContext()
            except Exception:
                activity = None
            # 更新按钮：确认按钮已点击（触发本回调），仅保留底部操作按钮。
            self._reserve_panel_cancel_button(
                panel, panel_key, cancellable, click_listener
            )
            # 运行中把「取消」按钮改为空操作并禁止空白/返回关闭：
            # 否则任务中途面板被 dismiss 后，进度条与结果都不可见。
            try:
                view_click_listener = jclass(
                    "android.view.View$OnClickListener"
                )

                class NoopViewClick(dynamic_proxy(view_click_listener)):
                    def onClick(self, view):
                        return None

                noop_view_click = NoopViewClick()
                self._dialog_refs.append(noop_view_click)
                negative = panel["dialog"].getButton(-2)
                if negative is not None:
                    negative.setOnClickListener(noop_view_click)
                panel["dialog"].setCancelable(False)
            except Exception:
                pass
            self._launch_panel_worker(panel_key, _worker)

        runnable_class = None
        if click_listener is not None:
            try:
                runnable_class = jclass("java.lang.Runnable")
            except Exception:
                runnable_class = None
        if runnable_class is not None:
            try:
                from java import dynamic_proxy

                activity = None
                try:
                    activity = self._current_android_activity(jclass)
                except Exception:
                    activity = None
                owner = self

                with self._ProxyCreationLock(self):

                    class SwitchToRunning(dynamic_proxy(runnable_class)):
                        def __init__(self):
                            super().__init__()
                            self._proxy_id = owner._retain_proxy(self)

                        def run(self):
                            try:
                                _switch_to_running()
                            finally:
                                owner._release_proxy(self._proxy_id)
                    runner = SwitchToRunning()
                    self._dialog_refs.append(runner)
                    # 不再截断，保持所有代理引用防止GC导致崩溃
                    if activity is not None:
                        activity.runOnUiThread(runner)
                        return
            except Exception:
                pass
        _switch_to_running()

    def _reserve_panel_cancel_button(
        self, panel, panel_key, cancellable, click_listener
    ):
        """运行模式下，把底部操作按钮调整为「取消当前进度」或「完成」。
        - 可取消任务（测活/重检测）：显示「取消当前进度」，点击触发 cancel。
        - 不可取消任务（扫描/清除/分类）：运行中显示「取消」，完成变「确定」。
        尽力而为：若当前构造环境拿不到按钮视图则跳过，不影响核心功能。
        """
        try:
            dialog = panel.get("dialog")
            if dialog is None:
                return
            if click_listener is None:
                return
            try:
                from java import dynamic_proxy, jclass
            except Exception:
                return
            owner = self
            with self._ProxyCreationLock(self):
                if cancellable:
                    class CancelListener(dynamic_proxy(click_listener)):
                        def onClick(self, d, which):
                            owner._cancel_progress_panel(panel_key)

                    listener = CancelListener()
                    self._dialog_refs.append(listener)
                    dialog.setButton(
                        -1,  # BUTTON_POSITIVE
                        "取消当前进度",
                        listener,
                    )
                else:
                    class CloseListener(dynamic_proxy(click_listener)):
                        def onClick(self, d, which):
                            owner._release_progress_panel(panel_key)

                    listener = CloseListener()
                    self._dialog_refs.append(listener)
                    try:
                        dialog.setButton(-1, "取消", listener)
                    except Exception:
                        pass
        except Exception as exc:
            self._log("WARN", "进度面板按钮调整失败: {}".format(exc))

    def _launch_panel_worker(self, panel_key, worker_fn):
        worker = threading.Thread(
            target=worker_fn,
            name="local-source-panel-action",
            daemon=True,
        )
        worker.start()

    def _update_progress_panel(
        self,
        message,
        panel_key=None,
        done=None,
        total=None,
        indeterminate=None,
    ):
        """线程安全地把任务进度/详情回填到在途进度面板。
        若干净地没有可用的进度面板，则退化为 _notify_app toast。

        - total>0：进度条切换为确定模式，按 done/total 显示百分比；
        - indeterminate=True：切换为不确定模式（往返动画）；
        - 两者均为 None：仅刷新文字，进度条形态保持不变。
        """
        text = " ".join(str(message or "").split()).strip()
        if not text or self._destroyed:
            return False
        with self._progress_panel_lock:
            panel = self._active_progress_panel
            if (
                not panel
                or panel.get("text") is None
                or panel.get("running") is False
            ):
                panel = None
            elif (
                panel_key is not None
                and panel.get("key") != panel_key
            ):
                panel = None
        if panel is None:
            return self._notify_app(text)
        text_view = panel.get("text")
        bar_view = panel.get("bar")

        try:
            from java import dynamic_proxy, jclass

            runnable_class = jclass("java.lang.Runnable")
            handler_class = jclass("android.os.Handler")
            looper_class = jclass("android.os.Looper")
        except Exception:
            runnable_class = None
        if runnable_class is None:
            try:
                text_view.setText(text)
            except Exception:
                pass
            return True

        owner = self

        with self._ProxyCreationLock(self):

            class SetText(dynamic_proxy(runnable_class)):
                def __init__(self):
                    super().__init__()
                    self._proxy_id = owner._retain_proxy(self)

                def run(self):
                    try:
                        # 更新时再次校验面板仍在途，避免写穿旧面板。
                        with owner._progress_panel_lock:
                            current = owner._active_progress_panel
                            if (
                                not current
                                or current.get("key") != panel.get("key")
                                or current.get("text") is not text_view
                            ):
                                return
                        if owner._destroyed:
                            return
                        text_view.setText(text)
                        if bar_view is not None:
                            try:
                                if total is not None and int(total) > 0:
                                    bar_view.setIndeterminate(False)
                                    bar_view.setMax(int(total))
                                    value = int(done or 0)
                                    if value < 0:
                                        value = 0
                                    if value > int(total):
                                        value = int(total)
                                    bar_view.setProgress(value)
                                elif indeterminate:
                                    bar_view.setIndeterminate(True)
                            except Exception:
                                pass
                    finally:
                        owner._release_proxy(self._proxy_id)
            runner = SetText()
            self._dialog_refs.append(runner)
            # 不再截断，保持所有代理引用
            try:
                handler_class(looper_class.getMainLooper()).post(runner)
            except Exception:
                try:
                    text_view.setText(text)
                except Exception:
                    pass
        return True

    def _finish_progress_panel(self, panel_key, message, ok=True):
        """任务结束：把汇总结果回填到面板，并把底部按钮切换为「确定」关闭。"""
        text = " ".join(str(message or "").split()).strip() or (
            "完成" if ok else "任务中断"
        )
        if ok:
            body = "✅ 完成\n\n{}".format(text)
        else:
            body = "❌ 未完成\n\n{}".format(text)
        # 成功把进度条补满；失败则停止不确定动画，保留当前进度位置。
        self._update_progress_panel(
            body,
            panel_key=panel_key,
            done=100 if ok else None,
            total=100 if ok else None,
            indeterminate=False if not ok else None,
        )
        with self._progress_panel_lock:
            panel = self._active_progress_panel
            if (
                not panel
                or panel.get("key") != panel_key
                or panel.get("dialog") is None
            ):
                return
        dialog = panel.get("dialog")
        owner = self

        with self._ProxyCreationLock(self):
            try:
                from java import dynamic_proxy, jclass

                click_listener = jclass(
                    "android.content.DialogInterface$OnClickListener"
                )

                class CloseListener(dynamic_proxy(click_listener)):
                    def onClick(self, d, which):
                        owner._release_progress_panel(panel_key)

                def _finalize():
                    try:
                        listener = CloseListener()
                        self._dialog_refs.append(listener)
                        dialog.setButton(-1, "确定", listener)
                    except Exception:
                        pass

                runnable_class = jclass("java.lang.Runnable")
                handler_class = jclass("android.os.Handler")
                looper_class = jclass("android.os.Looper")

                class FinalizeDialog(dynamic_proxy(runnable_class)):
                    def __init__(self):
                        super().__init__()
                        self._proxy_id = owner._retain_proxy(self)

                    def run(self):
                        try:
                            _finalize()
                        finally:
                            owner._release_proxy(self._proxy_id)

                runner = FinalizeDialog()
                self._dialog_refs.append(runner)
                handler_class(looper_class.getMainLooper()).post(runner)
            except Exception:
                try:
                    dialog.setButton(-1, "确定", None)
                except Exception:
                    pass

    def _cancel_progress_panel(self, panel_key):
        """用户点击「取消当前进度」：请求取消当前任务并收起进度面板。"""
        # 触发实际任务取消（站点测活/重检测通过 _site_test_cancel 中断）。
        cancelled = False
        try:
            if self._site_test_cancel is not None:
                self._site_test_cancel.set()
                cancelled = True
        except Exception:
            pass
        self._update_progress_panel(
            "正在取消当前进度…", panel_key=panel_key
        )
        if cancelled:
            self._log("INFO", "用户请求取消当前站点测活进度")
        self._close_progress_panel_after(panel_key)

    def _release_progress_panel(self, panel_key):
        """释放并关闭在途进度面板（清除活跃引用，避免 GC 复活）。"""
        with self._progress_panel_lock:
            panel = self._active_progress_panel
            if (
                panel
                and panel.get("key") == panel_key
            ):
                dialog = panel.get("dialog")
                try:
                    if dialog is not None:
                        dialog.dismiss()
                except Exception:
                    pass
                self._active_progress_panel = None

    def _close_progress_panel_after(self, panel_key, delay=0.4):
        """延迟关闭进度面板，让取消提示可见后再收起。"""

        def _do_close():
            time.sleep(delay)
            self._release_progress_panel(panel_key)

        worker = threading.Thread(
            target=_do_close,
            name="local-source-panel-close",
            daemon=True,
        )
        worker.start()

    def _create_standalone_progress(self, title, message="", indeterminate=True):
        """在 UI 线程同步创建独立进度对话框（横向进度条 + 消息文本）。

        网络同步/测试连接等没有「确认-进度面板」的等待操作使用本方法。
        可在任意线程调用：内部切到 UI 线程创建并等待句柄；拿不到
        Activity 或创建超时（2 秒）时返回静默空句柄，后台任务不受影响。
        """
        try:
            from java import dynamic_proxy, jclass

            activity = self._current_android_activity(jclass)
        except Exception:
            activity = None
        if activity is None:
            return _StandaloneProgressHandle.null()

        box = {}
        created = threading.Event()
        owner = self
        initial_message = str(message or "")
        initial_indeterminate = bool(indeterminate)

        with self._ProxyCreationLock(self):
            runnable_class = jclass("java.lang.Runnable")

            class BuildRunnable(dynamic_proxy(runnable_class)):
                def __init__(self):
                    super().__init__()
                    self._proxy_id = owner._retain_proxy(self)

                def run(self):
                    try:
                        try:
                            density = float(
                                activity.getResources().getDisplayMetrics().density
                            )
                            padding = int(16 * density + 0.5)
                            try:
                                builder_class = jclass(
                                    "com.google.android.material.dialog.MaterialAlertDialogBuilder"
                                )
                            except Exception:
                                builder_class = jclass(
                                    "android.app.AlertDialog$Builder"
                                )
                            linear_cls = jclass("android.widget.LinearLayout")
                            text_cls = jclass("android.widget.TextView")
                            bar_cls = jclass("android.widget.ProgressBar")
                            bar_attr = jclass("android.R$attr")
                            container = linear_cls(activity)
                            container.setOrientation(linear_cls.VERTICAL)
                            container.setPadding(padding, padding, padding, 0)
                            bar = bar_cls(
                                activity,
                                None,
                                bar_attr.progressBarStyleHorizontal,
                            )
                            bar_params = linear_cls.LayoutParams(
                                linear_cls.LayoutParams.MATCH_PARENT,
                                linear_cls.LayoutParams.WRAP_CONTENT,
                            )
                            bar_params.setMargins(
                                0, 0, 0, int(10 * density + 0.5)
                            )
                            bar.setLayoutParams(bar_params)
                            bar.setMax(100)
                            bar.setProgress(0)
                            bar.setIndeterminate(initial_indeterminate)
                            container.addView(bar)
                            text_view = text_cls(activity)
                            text_view.setTextSize(14.0)
                            text_view.setLineSpacing(0.0, 1.3)
                            text_view.setTextIsSelectable(True)
                            text_view.setText(initial_message)
                            container.addView(text_view)
                            builder = builder_class(activity)
                            builder.setTitle(title)
                            builder.setView(container)
                            # v8.0：创建时即带「关闭」按钮并允许点空白/返回键
                            # 关闭；关闭只是收起进度显示，后台任务继续执行。
                            click_listener = jclass(
                                "android.content.DialogInterface$OnClickListener"
                            )

                            class CloseNowListener(
                                dynamic_proxy(click_listener)
                            ):
                                def onClick(self, dialog_, which):
                                    handle = box.get("handle")
                                    if handle is not None:
                                        handle.dismiss()

                            close_now = CloseNowListener()
                            builder.setPositiveButton("关闭", close_now)
                            builder.setCancelable(True)
                            dialog = builder.show()
                            handler_class = jclass("android.os.Handler")
                            looper_class = jclass("android.os.Looper")
                            handler = handler_class(
                                looper_class.getMainLooper()
                            )
                            box["handle"] = _StandaloneProgressHandle(
                                owner, dialog, bar, text_view, handler
                            )
                            owner._dialog_refs.extend(
                                [bar, text_view, container, close_now, dialog]
                            )
                        except Exception as exc:
                            owner._log(
                                "ERROR",
                                "独立进度对话框创建失败: {}".format(exc),
                            )
                    finally:
                        created.set()
                        owner._release_proxy(self._proxy_id)

            runner = BuildRunnable()
        self._dialog_refs.append(runner)
        activity.runOnUiThread(runner)
        created.wait(2.0)
        return box.get("handle") or _StandaloneProgressHandle.null()

    def _apply_pending_type_settings(self):
        previous_types = dict(self.type_enabled)
        previous_pending = dict(self.pending_type_enabled)
        previous_block_adult = self.block_adult_sites
        previous_pending_block_adult = self.pending_block_adult_sites
        previous_dirty = self.config_dirty
        try:
            self.type_enabled = {
                source_type: bool(
                    self.pending_type_enabled.get(
                        source_type, self.type_enabled.get(source_type, True)
                    )
                )
                for source_type in self.TYPE_ORDER
            }
            self.pending_type_enabled = dict(self.type_enabled)
            self.block_adult_sites = bool(self.pending_block_adult_sites)
            self.pending_block_adult_sites = self.block_adult_sites
            self.config_dirty = False
            self._sync_ignored_sources()
            self._save_settings()
        except Exception:
            self.type_enabled = previous_types
            self.pending_type_enabled = previous_pending
            self.block_adult_sites = previous_block_adult
            self.pending_block_adult_sites = previous_pending_block_adult
            self.config_dirty = previous_dirty
            self._sync_ignored_sources()
            raise

    def _load_scan_cache_payload(self, warn=True):
        path = os.path.abspath(os.path.expanduser(self.cache_path))
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            if (
                not isinstance(data, dict)
                or data.get("version") != self.CACHE_VERSION
                or str(data.get("app_mode", "")) != self.app_mode
            ):
                return {}
            return data
        except Exception as exc:
            if warn:
                self._warn(
                    "增量扫描缓存读取失败，将全量扫描: {}".format(
                        exc
                    )
                )
            return {}

    def _load_scan_cache(self):
        try:
            data = self._load_scan_cache_payload()
            files = data.get("files", {}) if isinstance(data, dict) else {}
            return files if isinstance(files, dict) else {}
        except Exception:
            return {}

    def _save_scan_cache(self, files):
        path = os.path.abspath(os.path.expanduser(self.cache_path))
        previous = self._load_scan_cache_payload(warn=False)
        data = {
            "version": self.CACHE_VERSION,
            "app_mode": self.app_mode,
            "files": files,
        }
        if isinstance(previous.get("snapshot"), dict):
            data["snapshot"] = previous["snapshot"]
        self._atomic_write_plain_json(path, data)

    def _scan_snapshot_sources(self):
        fields = (
            "id",
            "identity",
            "key",
            "type",
            "path",
            "scan_root",
            "root_order",
            "relative_in_root",
            "base_name",
            "package_label",
            "package_id",
            "name",
            "validation",
            "ignored",
            "size",
            "mtime_ns",
            "csp_site",
            "dependencies",
            "test_result",
            "site",
        )
        result = []
        for source in self.cache["sources"] + self.cache["ignored"]:
            result.append(
                {
                    field: copy.deepcopy(source[field])
                    for field in fields
                    if field in source
                }
            )
        return result

    def _scan_location_signature(self):
        payload = {
            "scan_base_path": self.scan_base_path,
            "local_base_dir": self.local_base_dir,
            "roots": [
                {
                    "path": os.path.realpath(
                        os.path.abspath(os.path.expanduser(str(item.get("path", ""))))
                    ),
                    "type": str(item.get("type", "")).upper(),
                    "extensions": sorted(
                        str(value).lower()
                        for value in item.get("extensions", [])
                        if str(value).strip()
                    ),
                }
                for item in self.scan_roots
                if isinstance(item, dict)
            ],
        }
        return self._digest(
            json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
            24,
        )

    def _save_scan_snapshot(self):
        path = os.path.abspath(os.path.expanduser(self.cache_path))
        data = self._load_scan_cache_payload(warn=False)
        files = data.get("files", {}) if isinstance(data, dict) else {}
        if not isinstance(files, dict):
            files = {}
        status_fields = (
            "scan_time",
            "found",
            "included",
            "skipped",
            "duplicates",
            "cache_hits",
            "cache_misses",
            "ignored",
            "adult_filtered",
            "compatibility_blocked",
            "stale_ignored_removed",
            "manual_sites",
            "generated_sites",
            "generated_lives",
            "duplicate_lives",
            "added_sites",
            "updated_sites",
            "removed_sites",
            "unchanged_sites",
        )
        data = {
            "version": self.CACHE_VERSION,
            "app_mode": self.app_mode,
            "files": files,
            "snapshot": {
                "registry_token": self._registry_token(self.output_path),
                "package_state": self._package_download_state_signature(),
                "scan_state": self._scan_location_signature(),
                "sources": self._scan_snapshot_sources(),
                "lives": copy.deepcopy(self.cache.get("lives", [])),
                "contexts": copy.deepcopy(self.cache.get("contexts", [])),
                "status": {
                    field: copy.deepcopy(self.status.get(field))
                    for field in status_fields
                },
            },
        }
        self._atomic_write_plain_json(path, data)

    def _set_cached_source_ignored(self, source, ignored):
        source_id = str(source.get("id", "")).strip()
        current = self.cache.get("source_index", {}).get(source_id)
        if current is None:
            raise ValueError("站点不存在，请重新扫描")
        self.cache["sources"] = [
            item for item in self.cache.get("sources", [])
            if str(item.get("id", "")) != source_id
        ]
        self.cache["ignored"] = [
            item for item in self.cache.get("ignored", [])
            if str(item.get("id", "")) != source_id
        ]
        current["ignored"] = bool(ignored)
        target = "ignored" if ignored else "sources"
        self.cache[target].append(current)
        type_counts = {}
        ignored_counts = {}
        for item in self.cache["sources"]:
            source_type = str(item.get("type", "")).upper()
            type_counts[source_type] = type_counts.get(source_type, 0) + 1
        for item in self.cache["ignored"]:
            source_type = str(item.get("type", "")).upper()
            ignored_counts[source_type] = ignored_counts.get(source_type, 0) + 1
        self.cache["type_counts"] = type_counts
        self.cache["ignored_counts"] = ignored_counts
        self.status["included"] = len(self.cache["sources"])
        self.status["ignored"] = len(self.cache["ignored"])
        self.status["registry_changed"] = True
        self.status["write_state"] = "屏蔽设置待「加载」后生效"

    def _restore_blocked_sources(self, source_ids):
        """批量恢复屏蔽站点。

        恢复只是把站点从 ignored 挪回 sources（未加载状态），不写注册表、
        不触发配置生成——否则 _load_filter=None 的"全部加载"语义会把所有
        扫描到的站点重新注入注册表，导致恢复的站点被立刻加载。
        """
        ordered_ids = list(dict.fromkeys(
            str(value or "").strip() for value in source_ids
            if str(value or "").strip()
        ))
        sources = []
        for source_id in ordered_ids:
            source = self.cache.get("source_index", {}).get(source_id)
            if source and source.get("ignored"):
                sources.append(source)
        if not sources:
            raise ValueError("没有可解除屏蔽的站点")

        previous = {
            "ignored_sources": set(self.ignored_sources),
            "manual_ignored_sources": set(self.manual_ignored_sources),
            "auto_blocked_sources": set(self.auto_blocked_sources),
            "adult_blocked_sources": set(self.adult_blocked_sources),
            "adult_allowed_sources": set(self.adult_allowed_sources),
            "pruned_sources": set(self.pruned_sources),
            "site_test_results": dict(self.site_test_results),
            "retest_pending": list(self._retest_pending),
            "retest_auto_blocked": set(self._retest_auto_blocked),
            "cache": copy.deepcopy(self.cache),
            "status": copy.deepcopy(self.status),
        }
        identities = {source["identity"] for source in sources}
        for source in sources:
            identity = source["identity"]
            self.manual_ignored_sources.discard(identity)
            self.auto_blocked_sources.discard(identity)
            if source.get("adult_blocked") or (
                (not self.block_adult_sites) and self._is_adult_source(source)
            ):
                self.adult_allowed_sources.add(identity)
            self.adult_blocked_sources.discard(identity)
            self.pruned_sources.discard(identity)
            self._retest_auto_blocked.discard(identity)
            self.site_test_results.pop(identity, None)
        self._retest_pending = [
            value for value in self._retest_pending if value not in identities
        ]
        self._sync_ignored_sources()

        try:
            self._save_settings()
            for source in sources:
                self._set_cached_source_ignored(source, False)
            try:
                self._save_scan_snapshot()
            except Exception as exc:
                self._warn("批量解除后扫描列表快照保存失败: {}".format(exc))
        except Exception as exc:
            self.ignored_sources = previous["ignored_sources"]
            self.manual_ignored_sources = previous["manual_ignored_sources"]
            self.auto_blocked_sources = previous["auto_blocked_sources"]
            self.adult_blocked_sources = previous["adult_blocked_sources"]
            self.adult_allowed_sources = previous["adult_allowed_sources"]
            self.pruned_sources = previous["pruned_sources"]
            self.site_test_results = previous["site_test_results"]
            self._retest_pending = previous["retest_pending"]
            self._retest_auto_blocked = previous["retest_auto_blocked"]
            self.cache = previous["cache"]
            self.status = previous["status"]
            try:
                self._save_settings()
            except Exception:
                pass
            raise ValueError("解除屏蔽保存失败：{}".format(exc))

        # 恢复屏蔽只影响扫描缓存（站点并未注入注册表），用轻量页面刷新即可，
        # 避免全量 VodConfig 重载导致 App 重建站点表并跳到"智能点播"接口。
        self._schedule_manager_page_refresh()
        return sources, "已安排轻量刷新"

    def _restore_scan_snapshot(self, force=False):
        data = self._load_scan_cache_payload(warn=False)
        snapshot = data.get("snapshot", {}) if isinstance(data, dict) else {}
        if not isinstance(snapshot, dict):
            return False
        expected_token = str(snapshot.get("registry_token", ""))
        if not force and (
            not expected_token
            or expected_token != self._registry_token(self.output_path)
        ):
            return False
        if not force and str(
            snapshot.get("package_state", "")
        ) != self._package_download_state_signature():
            return False
        if not force and str(
            snapshot.get("scan_state", "")
        ) != self._scan_location_signature():
            return False
        raw_sources = snapshot.get("sources", [])
        if not isinstance(raw_sources, list):
            return False
        raw_lives = snapshot.get("lives", [])
        if not isinstance(raw_lives, list):
            raw_lives = []
        raw_contexts = snapshot.get("contexts", [])
        if not isinstance(raw_contexts, list):
            raw_contexts = []

        restored = self._empty_cache()
        seen_ids = set()
        for raw in raw_sources:
            if not isinstance(raw, dict):
                continue
            source = copy.deepcopy(raw)
            source_id = str(source.get("id", "")).strip()
            identity = str(source.get("identity", "")).strip()
            source_type = str(source.get("type", "")).upper()
            if (
                not source_id
                or source_id in seen_ids
                or not identity
                or source_type not in self.TYPE_ORDER
                or not isinstance(source.get("site"), dict)
            ):
                continue
            source["type"] = source_type
            source["ignored"] = identity in self.ignored_sources
            source["adult_blocked"] = (
                (not self.block_adult_sites)
                and identity in self.adult_blocked_sources
            )
            test_result = self.site_test_results.get(identity, {})
            if not isinstance(test_result, dict) or test_result.get(
                "source_signature"
            ) != self._source_signature(source):
                test_result = {}
            source["test_result"] = test_result
            seen_ids.add(source_id)
            restored["source_index"][source_id] = source
            if source["ignored"]:
                restored["ignored"].append(source)
                counts = restored["ignored_counts"]
            else:
                restored["sources"].append(source)
                counts = restored["type_counts"]
            counts[source_type] = counts.get(source_type, 0) + 1
        restored["lives"] = [
            copy.deepcopy(item)
            for item in raw_lives
            if isinstance(item, dict) and isinstance(item.get("live"), dict)
        ]
        restored["contexts"] = [
            copy.deepcopy(item)
            for item in raw_contexts
            if isinstance(item, dict)
            and isinstance(item.get("context"), dict)
            and bool(item.get("context"))
        ]
        if (
            not restored["sources"]
            and not restored["ignored"]
            and not restored["lives"]
            and not restored["contexts"]
        ):
            return False

        current_manual = self.status["manual_sites"]
        current_generated = self.status["generated_sites"]
        saved_status = snapshot.get("status", {})
        self.cache = restored
        if isinstance(saved_status, dict):
            for field in self._empty_status():
                if field in saved_status:
                    self.status[field] = copy.deepcopy(saved_status[field])
        self.status["included"] = len(restored["sources"])
        self.status["ignored"] = len(restored["ignored"])
        self.status["manual_sites"] = current_manual
        self.status["generated_sites"] = current_generated
        self.status["written"] = True
        self.status["registry_changed"] = False
        self.status["write_state"] = "已恢复上次成功扫描结果"
        self.status["error"] = ""
        return True

    def _atomic_write_plain_json(self, path, data):
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        temp_path = path + ".tmp"
        content = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        try:
            with open(temp_path, "w", encoding="utf-8") as fp:
                fp.write(content)
                fp.flush()
                os.fsync(fp.fileno())
            os.replace(temp_path, path)
        except Exception:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
            raise

    # --------------------------------------------------------------------------
    # OK影视兼容：标准配置合并与 A/B 热重载
    # --------------------------------------------------------------------------
    def _ok_config_paths(self):
        return (
            os.path.realpath(os.path.abspath(os.path.expanduser(self.ok_config_a))),
            os.path.realpath(os.path.abspath(os.path.expanduser(self.ok_config_b))),
        )

    def _is_ok_generated_config_url(self, value):
        url = str(value or "").strip()
        if not url:
            return False
        path = self._reference_path(url)
        if path:
            return path in set(self._ok_config_paths())
        clean = url.split("?", 1)[0].rstrip("/")
        return any(clean.endswith("/" + os.path.basename(path)) for path in self._ok_config_paths())

    def _current_vod_config_url(self):
        """读取当前活动点播接口，两端通用。

        OK影视经 Java Config 读取；WebHTV 走本机管理接口的 type=0 活动项。
        """
        if self.app_mode == self.APP_MODE_OKTV:
            return self._ok_current_config_url()
        last_error = "未发现 WebHTV 本机服务"
        for port in self._app_port_candidates():
            try:
                payload = self._request_json(
                    "http://127.0.0.1:{}/manage/configs".format(port),
                    self.APP_REQUEST_TIMEOUT,
                )
                items = payload.get("items", []) if isinstance(payload, dict) else []
                current = next(
                    (
                        item
                        for item in items
                        if isinstance(item, dict)
                        and int(item.get("type", -1)) == 0
                        and bool(item.get("active", False))
                        and str(item.get("url", "")).strip()
                    ),
                    None,
                )
                if current:
                    return str(current["url"]).strip()
                last_error = "WebHTV 未返回当前点播接口"
            except Exception as exc:
                last_error = str(exc)
        raise ValueError("读取 WebHTV 当前点播接口失败: {}".format(last_error))

    def _ok_current_config_url(self):
        try:
            from java import jclass

            return str(
                jclass("com.fongmi.android.tv.bean.Config").vod().getUrl() or ""
            ).strip()
        except Exception as exc:
            raise ValueError("读取 OK影视当前点播接口失败: {}".format(exc))

    def _ok_fetch_config_text(self, value):
        path = self._reference_path(value)
        if path and os.path.isfile(path):
            with open(path, "r", encoding="utf-8-sig") as fp:
                return fp.read()
        lower = value.lower()
        if lower.startswith("assets://"):
            try:
                from java import jclass

                port = int(jclass("com.github.catvod.Proxy").getPort())
                value = "http://127.0.0.1:{}/{}".format(
                    port, value[9:].lstrip("/")
                )
            except Exception as exc:
                raise ValueError("无法读取 assets 配置: {}".format(exc))
        if not value.lower().startswith(("http://", "https://")):
            raise ValueError("不支持的基础配置地址: {}".format(value))
        request = urllib.request.Request(
            value,
            headers={"User-Agent": "okhttp/4.12.0", "Accept": "application/json"},
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=10) as response:
            return response.read().decode("utf-8-sig")

    def _ok_decoder_base64(self, text):
        match = re.search(r"[A-Za-z0-9]{8}\*\*", text)
        if not match:
            return text
        payload = text[match.end() :]
        return base64.b64decode(payload).decode("utf-8")

    def _ok_decoder_cbc(self, text):
        try:
            decoded = bytes.fromhex(text).decode("utf-8", errors="replace").lower()
            key_start = decoded.index("$#") + 2
            key_end = decoded.index("#$", key_start)
            key = (decoded[key_start:key_end] + "0" * 16)[:16].encode("utf-8")
            iv = (decoded[-13:] + "0" * 16)[:16].encode("utf-8")
            start = text.index("2324") + 4
            encrypted = bytes.fromhex(text[start:-26])
            from Crypto.Cipher import AES

            plain = AES.new(key, AES.MODE_CBC, iv).decrypt(encrypted)
            padding = plain[-1]
            if padding < 1 or padding > 16 or plain[-padding:] != bytes([padding]) * padding:
                raise ValueError("AES 填充无效")
            return plain[:-padding].decode("utf-8")
        except Exception as exc:
            raise ValueError("2423 配置解密失败: {}".format(exc))

    def _ok_fix_relative_urls(self, base_url, text):
        protected = {}

        def protect(match):
            token = "__LOCAL_AUTO_JS_{}__".format(len(protected))
            protected[token] = urllib.parse.urljoin(base_url, match.group(1))
            return '"{}"'.format(token)

        pattern = re.compile(r'"((?:\.\.?/)[^"?]+\.js\?[^" ]*)"')
        value = pattern.sub(protect, text)
        parent = urllib.parse.urljoin(base_url, "../")
        current = urllib.parse.urljoin(base_url, "./")
        value = value.replace("../", parent).replace("./", current)
        for token, resolved in protected.items():
            value = value.replace(token, resolved)
        return value

    def _ok_decode_config(self, url, depth=0):
        value = str(url or "").strip()
        if not value:
            raise ValueError("基础配置地址为空")
        if depth > 3:
            raise ValueError("多仓配置嵌套过深")
        text = self._ok_fetch_config_text(value).strip()
        if "**" in text:
            text = self._ok_decoder_base64(text)
        if text.startswith("2423"):
            text = self._ok_decoder_cbc(re.sub(r"\s+", "", text))
        text = self._ok_fix_relative_urls(value, text)
        try:
            data = json.loads(text.lstrip("\ufeff"))
        except Exception as exc:
            raise ValueError("基础配置不是有效 JSON: {}".format(exc))
        if not isinstance(data, dict):
            raise ValueError("基础配置顶层必须是 JSON 对象")
        urls = data.get("urls")
        if isinstance(urls, list) and urls:
            first = urls[0]
            child_url = first.get("url", "") if isinstance(first, dict) else first
            return self._ok_decode_config(child_url, depth + 1)
        return data

    def _ok_clean_base_config(self, config):
        data = copy.deepcopy(config) if isinstance(config, dict) else {}
        data.pop(self.OK_CONFIG_MARKER, None)
        sites = data.get("sites", [])
        if isinstance(sites, dict):
            sites = [sites]
        elif not isinstance(sites, list):
            sites = [sites] if isinstance(sites, str) and sites.strip() else []
        clean_sites = []
        for site in sites:
            if isinstance(site, dict):
                key = str(site.get("key", "")).strip()
                if key.startswith(self.GENERATED_KEY_PREFIX) or site.get(
                    self.OK_CONFIG_MARKER
                ):
                    continue
            clean_sites.append(site)
        data["sites"] = clean_sites
        lives = data.get("lives", [])
        if isinstance(lives, dict):
            lives = [lives]
        elif not isinstance(lives, list):
            lives = []
        data["lives"] = [
            live
            for live in lives
            if not isinstance(live, dict) or not live.get(self.OK_CONFIG_MARKER)
        ]
        return data

    def _ok_read_base_cache(self):
        path = os.path.abspath(os.path.expanduser(self.ok_base_cache_path))
        if not os.path.isfile(path):
            return {}
        try:
            cached = self._read_config_file(path, "OK影视基础配置缓存")
            config = cached.get("config", cached)
            return self._ok_clean_base_config(config)
        except Exception as exc:
            self._warn("OK影视基础配置缓存读取失败: {}".format(exc))
            return {}

    def _ok_save_base_cache(self, config):
        payload = {
            "baseUrl": self.ok_base_config_url,
            "savedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
            "config": self._ok_clean_base_config(config),
        }
        self._atomic_write_plain_json(self.ok_base_cache_path, payload)

    def _ok_base_config(self):
        current_url = self._current_vod_config_url()
        current_generated = self._is_ok_generated_config_url(current_url)

        if current_url and not current_generated:
            config = self._ok_clean_base_config(self._ok_decode_config(current_url))
            self.ok_base_config_url = current_url
            self._ok_save_base_cache(config)
            self._save_settings()
            return config

        if self.ok_base_config_url and not self._is_ok_generated_config_url(
            self.ok_base_config_url
        ):
            try:
                config = self._ok_clean_base_config(
                    self._ok_decode_config(self.ok_base_config_url)
                )
                self._ok_save_base_cache(config)
                return config
            except Exception as exc:
                self._warn(
                    "{} 基础配置刷新失败，使用本地缓存: {}".format(
                        self._app_mode_label(), exc
                    )
                )

        cached = self._ok_read_base_cache()
        if cached:
            return cached
        if current_url:
            return self._ok_clean_base_config(self._ok_decode_config(current_url))
        raise ValueError(
            "未找到 {} 当前配置或基础配置缓存".format(self._app_mode_label())
        )

    def _ok_registry_sites(self, registry):
        sites = []
        used_keys = set()
        skipped_html = 0
        for item in registry.get("items", []):
            if not isinstance(item, dict) or not bool(item.get("enabled", True)):
                continue
            site = self._registry_item_site(item)
            if not isinstance(site, dict):
                continue
            kind = str(item.get("kind", "")).strip().lower()
            if kind == "live":
                continue
            source_type = self._generated_item_type(item)
            if source_type == "HTML" or kind == "webhome" or site.get("homePage"):
                skipped_html += 1
                continue
            if not str(site.get("key", "")).strip():
                continue
            site = copy.deepcopy(site)
            base_key = str(site.get("key", "")).strip()
            unique_key = base_key
            index = 2
            while unique_key in used_keys:
                unique_key = "{}_{}".format(base_key, index)
                index += 1
            used_keys.add(unique_key)
            site["key"] = unique_key
            if self._is_generated_registry_item(item):
                site[self.OK_CONFIG_MARKER] = {
                    "version": self.OK_CONFIG_VERSION,
                    "sourceId": str(item.get("id", "")),
                    "originalKey": base_key,
                }
            sites.append(site)
        if skipped_html:
            if self.app_mode == self.APP_MODE_WEBHTV:
                # WebHTV 的 WebHome 由站点注入通道加载，不进标准配置。
                self._log(
                    "INFO",
                    "已跳过 {} 个 HTML 站点，改由 WebHome 注入加载".format(
                        skipped_html
                    ),
                )
            else:
                self._warn(
                    "{} 不支持 WebHome，已跳过 {} 个 HTML 站点".format(
                        self._app_mode_label(), skipped_html
                    )
                )
        return sites

    def _ok_registry_lives(self, registry):
        lives = []
        seen = set()
        for item in registry.get("items", []):
            if (
                not isinstance(item, dict)
                or not bool(item.get("enabled", True))
                or str(item.get("kind", "")).strip().lower() != "live"
            ):
                continue
            live = copy.deepcopy(self._registry_item_live(item))
            fingerprint = self._live_fingerprint(live)
            if not fingerprint or fingerprint in seen:
                continue
            seen.add(fingerprint)
            live.setdefault(
                self.OK_CONFIG_MARKER,
                {
                    "version": self.OK_CONFIG_VERSION,
                    "sourceId": str(item.get("id", "")),
                },
            )
            lives.append(live)
        return lives

    def _registry_root_contexts(self, registry):
        contexts = []
        for item in registry.get("items", []):
            if (
                not isinstance(item, dict)
                or not bool(item.get("enabled", True))
                or str(item.get("kind", "")).strip().lower() != "other"
            ):
                continue
            other = item.get("other", {})
            if isinstance(other, dict) and other:
                contexts.append(copy.deepcopy(other))
        return contexts

    def _merge_root_context(self, target, source):
        if not isinstance(target, dict) or not isinstance(source, dict):
            return target
        for key, value in source.items():
            if key in ("sites", "lives") or value is None:
                continue
            current = target.get(key)
            if isinstance(value, list):
                if not value:
                    continue
                merged = copy.deepcopy(current) if isinstance(current, list) else []
                fingerprints = {
                    json.dumps(
                        item,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    for item in merged
                }
                for item in value:
                    fingerprint = json.dumps(
                        item,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    if fingerprint not in fingerprints:
                        fingerprints.add(fingerprint)
                        merged.append(copy.deepcopy(item))
                target[key] = merged
            elif isinstance(value, dict):
                if not value:
                    continue
                if not isinstance(current, dict):
                    target[key] = copy.deepcopy(value)
                    continue
                for child, child_value in value.items():
                    if child not in current or current.get(child) in (None, ""):
                        current[child] = copy.deepcopy(child_value)
            elif key not in target or current in (None, ""):
                target[key] = copy.deepcopy(value)
        return target

    def _ok_build_config(self, registry):
        config = self._ok_base_config()
        local_sites = self._ok_registry_sites(registry)
        local_lives = self._ok_registry_lives(registry)
        root_contexts = self._registry_root_contexts(registry)
        for context in root_contexts:
            self._merge_root_context(config, context)
        local_keys = {
            str(site.get("key", "")).strip()
            for site in local_sites
            if isinstance(site, dict)
        }
        base_sites = config.get("sites", [])
        if isinstance(base_sites, dict):
            base_sites = [base_sites]
        elif not isinstance(base_sites, list):
            base_sites = [base_sites] if isinstance(base_sites, str) and base_sites.strip() else []
        base_sites = [
            site
            for site in base_sites
            if not isinstance(site, dict)
            or str(site.get("key", "")).strip() not in local_keys
        ]
        config["sites"] = local_sites + base_sites
        base_lives = config.get("lives", [])
        if isinstance(base_lives, dict):
            base_lives = [base_lives]
        elif not isinstance(base_lives, list):
            base_lives = []
        base_lives = [
            live
            for live in base_lives
            if not isinstance(live, dict) or not live.get(self.OK_CONFIG_MARKER)
        ]
        base_live_fingerprints = {
            self._live_fingerprint(live)
            for live in base_lives
            if isinstance(live, dict)
        }
        local_lives = [
            live
            for live in local_lives
            if self._live_fingerprint(live) not in base_live_fingerprints
        ]
        merged_lives = local_lives + base_lives
        # 空占位会在 App 解析时被移除，同时确保关闭最后一个集成源后清空旧直播。
        config["lives"] = merged_lives or [{}]
        home_key = str(registry.get("homeKey", "")).strip()
        if home_key and home_key in local_keys:
            config["home"] = home_key
        config[self.OK_CONFIG_MARKER] = {
            "version": self.OK_CONFIG_VERSION,
            "loader": self.VERSION,
            "baseUrl": self.ok_base_config_url,
            "generatedSites": len(local_sites),
            "generatedLives": len(local_lives),
            "generatedContexts": len(root_contexts),
        }
        return config

    def _is_webhome_registry_item(self, item):
        """判断注册表项是否属于 WebHome（HTML）能力。

        v6.0 统一加载模型下，WebHome 是唯一仍走站点注入的类型，
        其余站点一律通过标准 TVBox 点播配置加载。
        """
        if not isinstance(item, dict):
            return False
        kind = str(item.get("kind", "")).strip().lower()
        if kind == "live" or kind == "other":
            return False
        if kind == "webhome":
            return True
        if self._generated_item_type(item) == "HTML":
            return True
        site = self._registry_item_site(item)
        return bool(
            isinstance(site, dict) and str(site.get("homePage", "")).strip()
        )

    def _standard_config_paths(self):
        return self._ok_config_paths()

    def _standard_config_reference(self):
        """已生成的标准点播配置引用；尚未生成时返回空串。

        WebHTV 用它把点播接口切到本脚本生成的配置；OK影视沿用自己的
        A/B 切换逻辑，不经过这里。
        """
        for path in self._standard_config_paths():
            if os.path.isfile(path):
                return self._file_url(path)
        return ""

    def _write_standard_configs(self, registry):
        """写入标准 TVBox 点播配置。

        v6.0 起 WebHTV 与 OK影视共用这一份配置，是两端的主加载链路。
        OK影视没有其它加载途径，基础配置读取失败必须向上暴露；WebHTV 仍有
        WebHome 注入通道且注册表已经落盘，此时只记录警告，不让一次本机服务
        不可达把整轮扫描判定为失败。
        """
        try:
            config = self._ok_build_config(registry)
        except Exception as exc:
            if self.app_mode == self.APP_MODE_OKTV:
                raise
            self._warn("标准点播配置生成失败，本轮跳过: {}".format(exc))
            return None
        for path in self._standard_config_paths():
            self._atomic_write_plain_json(path, config)
        self.status["write_state"] = "已生成 {} 本地配置".format(
            self._app_mode_label()
        )
        self.status["written"] = True
        return config

    def _ok_write_generated_configs(self, registry):
        return self._write_standard_configs(registry)

    def _ok_next_config_target(self):
        current_url = self._ok_current_config_url()
        path_a, path_b = self._ok_config_paths()
        current_path = self._reference_path(current_url)
        target_path = path_b if current_path == path_a else path_a
        return self._file_url(target_path)

    def _perform_ok_vod_reload(self):
        try:
            from java import jclass

            port = int(jclass("com.github.catvod.Proxy").getPort())
            if port < 1:
                raise ValueError("OK影视本机服务尚未启动")
            target = self._ok_next_config_target()
            config = json.dumps(
                {"type": 0, "url": target, "name": "智能点播"},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            body = urllib.parse.urlencode(
                {"config": config, "targets": "[]", "force": "false"}
            ).encode("utf-8")
            request = urllib.request.Request(
                "http://127.0.0.1:{}/action?do=sync&mode=1&type=history".format(port),
                data=body,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
                    "Connection": "close",
                },
            )
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=2.5) as response:
                if int(getattr(response, "status", response.getcode())) != 200:
                    raise ValueError("HTTP {}".format(response.getcode()))
            self.ok_last_target = target
            self._save_settings()
            return True, "OK影视本地站点已主动重载"
        except Exception as exc:
            self._warn("OK影视主动重载失败: {}".format(exc))
            return False, "OK影视配置已生成；主动重载失败，重启 App 后生效"

    def _reload_app_vod_config(self, expected_keys=None):
        if not self.auto_reload_app:
            return False, "配置已写入；App 自动重载已关闭"
        expected = set(expected_keys) if expected_keys is not None else None
        with self.lock:
            try:
                registry_snapshot = copy.deepcopy(self._load_registry())
            except Exception as exc:
                self._warn("App 主动重载快照创建失败: {}".format(exc))
                return False, "配置已写入；主动重载快照创建失败"
            reload_state = {
                "last_app_port": int(self.last_app_port or 0),
                "generated_live_count": len(self.cache.get("lives", [])),
                "registry": registry_snapshot,
            }
            self._reload_generation += 1
            generation = self._reload_generation
            worker = threading.Thread(
                target=self._delayed_app_vod_reload,
                args=(generation, expected, reload_state),
                name="local-source-reload",
            )
            worker.daemon = True
            worker.start()
        self._log(
            "INFO",
            "已安排 App 主动重载: delay={}s items={}".format(
                self.APP_RELOAD_DELAY,
                len(expected) if expected is not None else "-",
            ),
        )
        return True, "已安排主动重载 {} 站点列表".format(self._app_mode_label())

    def _local_server_port(self):
        """返回 App 本机服务端口；探测不到时返回 0。

        与 _app_port_candidates 不同，这里只取真正确认可用的端口，不做
        全端口段枚举——测活要的是"当前进程的服务地址"，枚举出来的端口
        可能属于另一个同时运行的 App。
        """
        port = self._current_proxy_port()
        if port:
            return port
        with self.lock:
            return int(self.last_app_port or 0)

    def _runtime_site_reference(self, reference):
        """把 file:// 引用改写成 App 本机 HTTP 地址。

        宿主的 Site.objectFrom 会对 api/ext/homePage 调 UrlUtil.convert，
        把 file:// 换成 http://127.0.0.1:<port>/file/。QuickJS 的
        Module.fetch 只认 http/assets/lib 前缀，拿到原始 file:// 会返回
        null，随后 createObj 对 null 取内容抛异常，站点被误判为失效。
        测活直接调 BaseLoader.getSpider，绕过了那次转换，所以必须在这里
        补上，否则本地 JS 站点永远初始化失败。
        """
        value = str(reference or "").strip()
        if not value.lower().startswith("file://"):
            return value
        port = self._local_server_port()
        if not port:
            return value
        relative = value[7:].lstrip("/")
        return "http://127.0.0.1:{}/file/{}".format(
            port, urllib.parse.quote(relative, safe="/%:@&=+$,~")
        )

    def _current_proxy_port(self):
        try:
            from java import jclass

            port = int(jclass("com.github.catvod.Proxy").getPort())
            return port if port > 0 else 0
        except Exception:
            return 0

    def _app_port_candidates(self):
        ports = []
        current_port = self._current_proxy_port()
        if current_port:
            ports.append(current_port)
        if self.last_app_port and self.last_app_port not in ports:
            ports.append(self.last_app_port)
        ports.extend(port for port in self.app_server_ports if port not in ports)
        return ports

    def _schedule_manager_page_refresh(self, delay=0.2):
        with self.lock:
            self._page_refresh_generation += 1
            generation = self._page_refresh_generation
        worker = threading.Thread(
            target=self._delayed_manager_page_refresh,
            args=(generation, max(0.05, float(delay))),
            name="local-source-page-refresh",
        )
        worker.daemon = True
        worker.start()
        return True, "已安排首页和分类页轻量刷新"

    def _delayed_manager_page_refresh(self, generation, delay):
        time.sleep(delay)
        try:
            with self.lock:
                if generation != self._page_refresh_generation:
                    return
            ok, detail = self._perform_manager_page_refresh()
            self._log("INFO" if ok else "WARN", detail)
            # 轻量刷新是后台维护动作，不弹 Toast 打扰用户；失败时也不弹，
            # 失败原因已写日志，且下次操作会再次触发刷新。
        except Exception as exc:
            detail = "页面轻量刷新失败: {}".format(exc)
            self._log("ERROR", detail)
            self._notify_app(detail)

    def _perform_manager_page_refresh(self, refresh_types=None):
        refresh_types = tuple(refresh_types or ("home", "category"))
        labels = {"home": "首页", "category": "分类页"}
        last_error = "未发现当前 App 本机服务"
        for port in self._app_port_candidates():
            base = "http://127.0.0.1:{}".format(port)
            try:
                for refresh_type in refresh_types:
                    query = urllib.parse.urlencode(
                        {"do": "refresh", "type": refresh_type}
                    )
                    self._request_status(
                        base + "/action?" + query,
                        max(1.2, self.APP_REQUEST_TIMEOUT * 3),
                    )
                    time.sleep(0.08)
                self._remember_app_port(port)
                page_names = "和".join(
                    labels.get(item, item) for item in refresh_types
                )
                return True, "{}已轻量刷新".format(page_names or "页面")
            except Exception as exc:
                last_error = str(exc)
        return False, "页面轻量刷新失败: {}".format(last_error)

    def _delayed_app_vod_reload(self, generation, expected_keys, reload_state):
        time.sleep(max(0.1, float(self.APP_RELOAD_DELAY)))
        try:
            with self.lock:
                if generation != self._reload_generation:
                    return
            # 网络请求必须在锁外执行，避免 Android UI 线程保存设置时等待。
            ok, detail = self._perform_app_vod_reload(expected_keys, reload_state)
            if ok and self.app_mode == self.APP_MODE_WEBHTV:
                time.sleep(max(0.2, float(self.APP_PAGE_REFRESH_DELAY)))
                # 主动补刷两个页面，避免 App 内部 VodConfig.load 只更新运行态、
                # 当前首页仍保留旧列表，必须再手动扫描才显示新站点。
                page_ok, page_detail = self._perform_manager_page_refresh(
                    refresh_types=("home", "category")
                )
                detail = "{}；{}".format(detail, page_detail)
                if not page_ok:
                    self._warn(
                        "站点已重载，{}；可手动刷新页面".format(page_detail)
                    )
            # 兜底补注临时站点：重载（无论成败）及上面的页面/直播刷新都会
            # 触发 App 重建运行态站点表，且 App 侧重建可能晚于本线程校验
            # 结束，单次补注仍可能被二次冲掉；看门逐轮补注并延迟复查。
            self._watch_reinject_temp_sites(generation)
            self._log("INFO" if ok else "WARN", detail)
            self._notify_app(detail)
        except Exception as exc:
            detail = "App 主动重载失败: {}".format(exc)
            self._log("ERROR", detail)
            self._notify_app(detail)

    def _perform_app_vod_reload(self, expected_keys=None, reload_state=None):
        trace_id = self._active_operation_trace_id()
        if self.app_mode == self.APP_MODE_OKTV:
            self._trace_log(
                trace_id,
                "app_reload",
                "oktv.begin",
                expected_site_count=(
                    len(expected_keys) if expected_keys is not None else None
                ),
            )
            ok, detail = self._perform_ok_vod_reload()
            self._trace_log(
                trace_id,
                "app_reload",
                "oktv.complete",
                level="INFO" if ok else "WARN",
                ok=bool(ok),
                detail=detail,
            )
            return ok, detail
        last_error = "未发现 WebHTV 本机服务"
        state = reload_state if isinstance(reload_state, dict) else {}
        ports = []
        if "last_app_port" in state:
            last_app_port = int(state.get("last_app_port") or 0)
        else:
            with self.lock:
                last_app_port = int(self.last_app_port or 0)
        if last_app_port:
            ports.append(last_app_port)
        ports.extend(port for port in self.app_server_ports if port not in ports)
        self._trace_log(
            trace_id,
            "app_reload",
            "webhtv.begin",
            ports=ports,
            expected_site_count=(
                len(expected_keys) if expected_keys is not None else None
            ),
            generated_config=self._safe_log_url(
                self._standard_config_reference()
            ),
        )
        for port in ports:
            base = "http://127.0.0.1:{}".format(port)
            port_started = time.monotonic()
            self._trace_log(
                trace_id,
                "app_reload",
                "port.begin",
                port=port,
            )
            try:
                payload = self._request_json(
                    base + "/manage/configs", self.APP_REQUEST_TIMEOUT
                )
                items = payload.get("items", []) if isinstance(payload, dict) else []
                current = next(
                    (
                        item
                        for item in items
                        if isinstance(item, dict)
                        and int(item.get("type", -1)) == 0
                        and bool(item.get("active", False))
                    ),
                    None,
                )
                if not current or not str(current.get("url", "")).strip():
                    last_error = "WebHTV 未返回当前点播接口"
                    self._trace_log(
                        trace_id,
                        "app_reload",
                        "port.rejected",
                        level="WARN",
                        port=port,
                        config_count=len(items),
                        reason=last_error,
                    )
                    continue
                # v6.0：普通站点改由标准点播配置承载，因此这里切换到本脚本
                # 生成的配置文件；未能生成时退回重载原接口，保证 WebHome
                # 注入仍能刷新。
                target_url = str(current["url"]).strip()
                generated_target = self._standard_config_reference()
                self._trace_log(
                    trace_id,
                    "app_reload",
                    "config.detected",
                    port=port,
                    config_count=len(items),
                    current_url=self._safe_log_url(target_url),
                    generated_url=self._safe_log_url(generated_target),
                )
                if generated_target:
                    generated_registered = any(
                        isinstance(item, dict)
                        and int(item.get("type", -1)) == 0
                        and self._live_config_reference_matches(
                            item.get("url", ""), generated_target
                        )
                        for item in items
                    )
                    if not generated_registered:
                        self._trace_log(
                            trace_id,
                            "app_reload",
                            "config.register.begin",
                            port=port,
                            target_url=self._safe_log_url(generated_target),
                        )
                        register_query = urllib.parse.urlencode(
                            {
                                "type": 0,
                                "url": generated_target,
                                "name": "智能点播",
                            }
                        )
                        self._request_json(
                            base + "/manage/configs?" + register_query,
                            max(1.5, self.APP_REQUEST_TIMEOUT * 4),
                        )
                        self._trace_log(
                            trace_id,
                            "app_reload",
                            "config.register.complete",
                            port=port,
                        )
                    target_url = generated_target
                # 只重载当前点播配置，不再向 /manage/csp 回写
                # registry。/manage/csp 会用 Java 格式重写同一文件，
                # 使扫描快照 token 变化，新 Spider 会误判为无快照并
                # 再次自动补扫，形成“重载 -> 补扫 -> 重载”循环。
                query = urllib.parse.urlencode(
                    {"type": 0, "url": target_url}
                )
                self._trace_log(
                    trace_id,
                    "app_reload",
                    "config.use.begin",
                    port=port,
                    target_url=self._safe_log_url(target_url),
                )
                self._request_json(
                    base + "/manage/config/use?" + query,
                    max(1.5, self.APP_REQUEST_TIMEOUT * 4),
                )
                self._trace_log(
                    trace_id,
                    "app_reload",
                    "config.use.complete",
                    port=port,
                )
                runtime_ok, runtime_detail = self._verify_webhtv_site_keys(
                    base, expected_keys
                )
                self._trace_log(
                    trace_id,
                    "app_reload",
                    "runtime.verify.complete",
                    level="INFO" if runtime_ok else "WARN",
                    port=port,
                    ok=bool(runtime_ok),
                    detail=runtime_detail,
                )
                if not runtime_ok:
                    last_error = runtime_detail
                    # 已成功读取配置并完成切换，当前端口就是 WebHTV 管理端口。
                    # 继续枚举只会让连接拒绝覆盖真正的运行态错误。
                    self._remember_app_port(port)
                    self._trace_log(
                        trace_id,
                        "app_reload",
                        "webhtv.failed",
                        level="WARN",
                        attempted_ports=[port],
                        error=last_error,
                    )
                    return False, "App 主动重载失败：{}；重启 App 后生效".format(
                        last_error
                    )
                try:
                    refreshed = self._request_json(
                        base + "/manage/configs",
                        max(1.2, self.APP_REQUEST_TIMEOUT * 3),
                    )
                    refreshed_items = (
                        refreshed.get("items", [])
                        if isinstance(refreshed, dict)
                        else []
                    )
                    if isinstance(refreshed_items, list):
                        items = refreshed_items
                except Exception:
                    pass
                live_ok, live_detail = self._reload_webhtv_live_config(
                    base, items, state
                )
                if not live_ok:
                    self._warn(live_detail)
                self._remember_app_port(port)
                self._trace_log(
                    trace_id,
                    "app_reload",
                    "port.success",
                    port=port,
                    live_ok=bool(live_ok),
                    live_detail=live_detail,
                    elapsed_ms=int((time.monotonic() - port_started) * 1000),
                )
                return True, "WebHTV 站点列表已主动重载，已触发页面刷新；{}".format(
                    live_detail
                )
            except Exception as exc:
                last_error = str(exc)
                self._trace_log(
                    trace_id,
                    "app_reload",
                    "port.failed",
                    level="WARN",
                    port=port,
                    elapsed_ms=int((time.monotonic() - port_started) * 1000),
                    error=str(exc),
                )
        if last_error:
            self._warn("WebHTV 本机管理接口未确认: {}".format(last_error))
        self._trace_log(
            trace_id,
            "app_reload",
            "webhtv.failed",
            level="WARN",
            attempted_ports=ports,
            error=last_error,
        )
        return False, "App 主动重载失败：{}；配置已写入，重启 App 后生效".format(
            last_error
        )

    def _verify_webhtv_site_keys(self, base, expected_keys):
        trace_id = self._active_operation_trace_id()
        if expected_keys is None:
            time.sleep(0.25)
            self._trace_log(
                trace_id,
                "app_reload",
                "runtime.verify.skipped",
                reason="expected keys not provided",
            )
            return True, "未要求校验运行态站点"
        expected = {
            str(key).strip() for key in expected_keys if str(key).strip()
        }
        self._trace_log(
            trace_id,
            "app_reload",
            "runtime.verify.begin",
            base=self._safe_log_url(base),
            expected_count=len(expected),
        )
        deadline = time.time() + max(5.0, self.APP_REQUEST_TIMEOUT * 12)
        last_error = "WebHTV 运行态站点尚未刷新"
        attempts = 0
        actual_count = 0
        missing_count = len(expected)
        stale_count = 0
        missing = set(expected)
        stale_generated = set()
        while time.time() < deadline:
            attempts += 1
            try:
                payload = self._request_json(
                    base + "/manage/proxy/suggest/sites",
                    max(0.6, self.APP_REQUEST_TIMEOUT * 2),
                )
                raw_sites = (
                    payload.get("sites", [])
                    if isinstance(payload, dict)
                    else []
                )
                actual = {
                    str(item.get("key", "")).strip()
                    for item in raw_sites
                    if isinstance(item, dict)
                    and str(item.get("key", "")).strip()
                }
                missing = expected - actual
                stale_generated = {
                    key
                    for key in actual
                    if key.startswith(self.GENERATED_KEY_PREFIX)
                    and key not in expected
                }
                actual_count = len(actual)
                missing_count = len(missing)
                stale_count = len(stale_generated)
                if not missing and not stale_generated:
                    self._trace_log(
                        trace_id,
                        "app_reload",
                        "runtime.verify.matched",
                        attempts=attempts,
                        expected_count=len(expected),
                        actual_count=actual_count,
                    )
                    return True, "WebHTV 运行态站点已核对"
                details = []
                if missing:
                    details.append(
                        "缺少 {} 个生成站点".format(len(missing))
                    )
                if stale_generated:
                    details.append(
                        "残留 {} 个旧生成站点".format(
                            len(stale_generated)
                        )
                    )
                last_error = "WebHTV 运行态{}".format("、".join(details))
            except Exception as exc:
                last_error = "WebHTV 运行态回读失败: {}".format(exc)
            time.sleep(0.15)
        self._trace_log(
            trace_id,
            "app_reload",
            "runtime.verify.failed",
            level="WARN",
            attempts=attempts,
            expected_count=len(expected),
            actual_count=actual_count,
            missing_count=missing_count,
            stale_generated_count=stale_count,
            missing_keys=sorted(missing)[:12],
            stale_generated_keys=sorted(stale_generated)[:12],
            error=last_error,
        )
        return False, last_error

    def _live_config_reference_matches(self, left, right):
        left_value = str(left or "").strip()
        right_value = str(right or "").strip()
        if not left_value or not right_value:
            return False
        left_path = self._reference_path(left_value)
        right_path = self._reference_path(right_value)
        if left_path and right_path:
            return left_path == right_path
        return left_value.rstrip("/") == right_value.rstrip("/")

    def _live_config_lives(self, reference, name="原直播"):
        value = str(reference or "").strip()
        if not value:
            return []
        path = self._reference_path(value)
        try:
            if path:
                if not os.path.isfile(path):
                    raise ValueError("本地直播配置不存在: {}".format(path))
                try:
                    data = self._load_json_compatible(path)
                except Exception:
                    return [{"name": str(name or "原直播"), "type": 0, "url": value}]
            else:
                with self._package_open_url(
                    value, timeout=8, accept="application/json,text/plain,*/*"
                ) as response:
                    payload = self._package_read_limited(
                        response, self.MAX_PACKAGE_CONFIG_SIZE
                    )
                try:
                    data = self._package_parse_json_text(
                        payload.decode("utf-8-sig")
                    )
                except Exception:
                    return [{"name": str(name or "原直播"), "type": 0, "url": value}]
        except Exception as exc:
            raise ValueError("原活动直播配置读取失败: {}".format(exc))
        if not isinstance(data, dict):
            raise ValueError("原活动直播配置格式无效")
        lives = data.get("lives", [])
        if isinstance(lives, dict):
            lives = [lives]
        if not isinstance(lives, list):
            raise ValueError("原活动直播配置的 lives 格式无效")
        return [copy.deepcopy(item) for item in lives if isinstance(item, dict)]

    def _existing_webhtv_base_lives(self):
        path = os.path.abspath(os.path.expanduser(self.webhtv_live_config_path))
        if not os.path.isfile(path):
            return []
        try:
            data = self._load_json_compatible(path)
        except Exception as exc:
            self._warn("旧本地直播聚合配置读取失败: {}".format(exc))
            return []
        marker = data.get(self.OK_CONFIG_MARKER, {}) if isinstance(data, dict) else {}
        base_fingerprints = {
            str(item).strip()
            for item in marker.get("baseLiveFingerprints", [])
            if str(item).strip()
        } if isinstance(marker, dict) else set()
        lives = data.get("lives", []) if isinstance(data, dict) else []
        if isinstance(lives, dict):
            lives = [lives]
        return [
            copy.deepcopy(item)
            for item in lives
            if isinstance(item, dict)
            and self._live_fingerprint(item) in base_fingerprints
        ]

    def _write_webhtv_live_config(
        self, base_lives=None, registry=None, generated_live_count=None
    ):
        lives = []
        seen = set()
        for live in base_lives if isinstance(base_lives, list) else []:
            if not isinstance(live, dict):
                continue
            item = copy.deepcopy(live)
            fingerprint = self._live_fingerprint(item)
            if not fingerprint or fingerprint in seen:
                continue
            seen.add(fingerprint)
            lives.append(item)
        base_fingerprints = set(seen)
        if not isinstance(registry, dict):
            try:
                registry = self._load_registry()
            except Exception:
                registry = {"items": []}
        for item in registry.get("items", []):
            if (
                not isinstance(item, dict)
                or not bool(item.get("enabled", True))
                or str(item.get("kind", "")).strip().lower() != "live"
            ):
                continue
            live = copy.deepcopy(self._registry_item_live(item))
            fingerprint = self._live_fingerprint(live)
            if not fingerprint or fingerprint in seen:
                continue
            seen.add(fingerprint)
            lives.append(live)
        # [live-auto] 第三来源：从本次扫描的实时去重直播缓存 self.cache["lives"] 取数，
        # 使 智能直播.json 也能像 智能点播.json 一样随每次扫描自动更新，
        # 不再依赖磁盘 registry 的 kind=live 项或手动维护的 base lives。
        # 元素结构 {"live": <裸live dict>, "id": GEN_LIVE_xxx, ...}，经 _registry_item_live 取 live 字段，
        # 再走 _live_fingerprint 统一去重（与 base_lives / registry 共享 seen 集合，避免重复）。
        for item in self.cache.get("lives", []):
            if not isinstance(item, dict):
                continue
            live = copy.deepcopy(self._registry_item_live(item))
            fingerprint = self._live_fingerprint(live)
            if not fingerprint or fingerprint in seen:
                continue
            seen.add(fingerprint)
            lives.append(live)
        payload = {
            self.OK_CONFIG_MARKER: {
                "version": self.OK_CONFIG_VERSION,
                "loader": self.VERSION,
                "generatedLives": (
                    len(self.cache.get("lives", []))
                    if generated_live_count is None
                    else max(0, int(generated_live_count))
                ),
                "baseLives": len(base_fingerprints),
                "baseLiveFingerprints": sorted(base_fingerprints),
            },
            "lives": lives or [{}],
        }
        self._atomic_write_plain_json(self.webhtv_live_config_path, payload)
        return self._file_url(self.webhtv_live_config_path), len(lives)

    def _reload_webhtv_live_config(self, base, config_items, reload_state=None):
        # 已禁用智能直播.json生成，直接返回成功
        return True, "智能直播配置已禁用"

    def _remember_app_port(self, port):
        with self.lock:
            if self.last_app_port == int(port):
                return
            self.last_app_port = int(port)
            try:
                self._save_settings()
            except Exception as exc:
                self._warn("App 端口缓存保存失败: {}".format(exc))

    def _generated_registry_keys(self, registry=None):
        """本轮应出现在 App 运行态的自动生成站点 key。

        v6.0 统一加载模型下，普通站点走标准点播配置、WebHome 走注入通道，
        两者都应能被 App 回读到，因此以扫描缓存的未屏蔽站点为准；注入表
        只是其中 WebHome 部分的落盘形式，不再是完整集合。
        OK影视不加载 WebHome，回读集合里也不能包含它，否则会把正常重载
        判定为“缺少生成站点”。
        """
        skip_webhome = self.app_mode != self.APP_MODE_WEBHTV
        keys = set()
        for source in self.cache.get("sources", []):
            site = source.get("site") or {}
            if not isinstance(site, dict):
                site = {}
            if skip_webhome and (
                str(source.get("type", "")).upper() == "HTML"
                or str(site.get("homePage", "")).strip()
            ):
                continue
            # 整包的 source.key 是本地管理标识，运行时保留原始 site.key。
            runtime_key = str(site.get("key", "")).strip() or str(
                source.get("key", "")
            ).strip()
            if runtime_key:
                keys.add(runtime_key)
        if keys:
            return keys
        registry = registry if isinstance(registry, dict) else self._load_registry()
        for item in registry.get("items", []):
            if (
                not isinstance(item, dict)
                or not self._is_generated_registry_item(item)
                or item.get("enabled", True) is False
            ):
                continue
            site = self._registry_item_site(item)
            if not isinstance(site, dict):
                continue
            if skip_webhome and self._is_webhome_registry_item(item):
                continue
            runtime_key = str(site.get("key", "")).strip()
            if runtime_key:
                keys.add(runtime_key)
        return keys

    def _request_json(self, url, timeout):
        headers = {"Accept": "application/json", "Connection": "close"}
        request = urllib.request.Request(
            url,
            headers=headers,
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=max(1.0, float(timeout or 3.0))) as response:
                status = getattr(response, "status", response.getcode())
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise ValueError("HTTP {}".format(exc.code))
        except urllib.error.URLError as exc:
            raise ValueError("网络请求失败: {}".format(exc.reason))
        except socket.timeout:
            raise ValueError("请求超时")
        except TimeoutError:
            raise ValueError("请求超时")
        except Exception as exc:
            raise ValueError("请求异常: {}".format(exc))
        if int(status) < 200 or int(status) >= 300:
            raise ValueError("HTTP {}".format(status))
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ValueError("JSON 解析失败: {}".format(exc))
        if not isinstance(data, dict):
            raise ValueError("WebHTV 本机接口返回格式无效")
        return data

    def _request_status(self, url, timeout):
        request = urllib.request.Request(
            url,
            headers={"Accept": "*/*", "Connection": "close"},
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=max(1.0, float(timeout or 3.0))) as response:
                status = int(getattr(response, "status", response.getcode()))
                response.read(1024)
        except urllib.error.HTTPError as exc:
            raise ValueError("HTTP {}".format(exc.code))
        except urllib.error.URLError as exc:
            raise ValueError("网络请求失败: {}".format(exc.reason))
        except socket.timeout:
            raise ValueError("请求超时")
        except TimeoutError:
            raise ValueError("请求超时")
        except Exception as exc:
            raise ValueError("请求异常: {}".format(exc))
        if status < 200 or status >= 300:
            raise ValueError("HTTP {}".format(status))
        return status

    def _notify_app(self, message, wait=False, replace=False):
        text = " ".join(str(message or "").split()).strip()
        if not text or self._destroyed:
            return False
        if not self._notification_gate.acquire(False):
            return False
        gate_handed_to_runner = False
        try:
            from java import dynamic_proxy, jclass

            toast_class = jclass("android.widget.Toast")
            runnable_class = jclass("java.lang.Runnable")
            handler_class = jclass("android.os.Handler")
            looper_class = jclass("android.os.Looper")
            activity, context = self._android_ui_context(jclass)
            if context is None:
                return False
            handler = handler_class(looper_class.getMainLooper())
            owner = self
            displayed = threading.Event()

            with self._ProxyCreationLock(self):

                # 复用 ShowNotification 类定义，避免频繁创建动态代理
                if not hasattr(owner, '_ShowNotificationClass'):
                    class ShowNotification(dynamic_proxy(runnable_class)):
                        def __init__(self):
                            super().__init__()
                            self._proxy_id = owner._retain_proxy(self)
                            self._toast = None
                            self._text = ""
                            self._replace = False
                            self._displayed = None
                            self._context = None
                            self._toast_class = None

                        def configure(self, text, replace, displayed, context, toast_class, toast):
                            self._text = text
                            self._replace = replace
                            self._displayed = displayed
                            self._context = context
                            self._toast_class = toast_class
                            self._toast = toast

                        def run(self):
                            try:
                                try:
                                    if self._toast is None:
                                        self._toast = self._toast_class.makeText(
                                            self._context,
                                            self._text[:120],
                                            self._toast_class.LENGTH_LONG,
                                        )
                                    else:
                                        self._toast.setText(self._text[:120])
                                    self._toast.show()
                                except Exception as exc:
                                    owner._log(
                                        "WARN", "站点通知显示失败: {}".format(exc)
                                    )
                            finally:
                                owner._release_proxy(self._proxy_id)
                                try:
                                    owner._notification_refs.remove(self)
                                except (ValueError, AttributeError):
                                    pass
                                if self._displayed:
                                    self._displayed.set()
                                try:
                                    owner._notification_gate.release()
                                except RuntimeError:
                                    pass

                    owner._ShowNotificationClass = ShowNotification

                # 创建实例并配置
                runner = owner._ShowNotificationClass()
                runner.configure(text, replace, displayed, context, toast_class, None if not replace else owner._site_test_toast)
                self._notification_refs.append(runner)
                try:
                    if activity is not None:
                        activity.runOnUiThread(runner)
                        queued = True
                    else:
                        queued = handler.post(runner)
                except Exception:
                    self._notification_refs.remove(runner)
                    raise
            # 部分 Chaquopy 版本会把 Java void/boolean 返回值映射为 None。
            # None 表示调用已发出；只有明确的 false 才视为入队失败。
            if queued is not None and not bool(queued):
                self._notification_refs.remove(runner)
                return False
            gate_handed_to_runner = True
            if wait and not displayed.wait(1.5):
                self._log("WARN", "站点通知等待 UI 显示超时: {}".format(text))
                return False
            return True
        except Exception as exc:
            try:
                self._log("WARN", "站点通知调度失败: {}".format(exc))
            except Exception:
                pass
            return False
        finally:
            if not gate_handed_to_runner:
                try:
                    self._notification_gate.release()
                except RuntimeError:
                    pass

    def _show_author_scan_surprise(self):
        if not self.cache["sources"]:
            return False
        first_scan = not self._author_scan_surprise_shown
        added_sites = max(0, int(self.status.get("added_sites", 0) or 0))
        if first_scan:
            message = "笔落惊风雨，霞飞映晚枫。已点亮 {} 个站点。".format(
                len(self.cache["sources"])
            )
        elif added_sites:
            message = "风过江面，晚枫又点亮 {} 个新站点。".format(
                added_sites
            )
        else:
            return False
        if not self._notify_app(message):
            return False
        if first_scan:
            self._author_scan_surprise_shown = True
            try:
                self._save_settings()
            except Exception as exc:
                self._warn("作者彩蛋状态保存失败: {}".format(exc))
        self._log(
            "INFO",
            "{}扫描彩蛋已显示: {}".format(
                "首次手动" if first_scan else "新增站点", message
            ),
        )
        return True

    def _test_sites_locked(self, force=False, source_identities=None):
        active_sources = list(self.cache["sources"])
        ignored_sources = list(self.cache["ignored"])
        targeted = source_identities is not None
        if targeted:
            selected = {
                str(identity).strip()
                for identity in source_identities
                if str(identity).strip()
            }
            active_sources = [
                source
                for source in active_sources
                if source.get("identity") in selected
            ]
            ignored_sources = [
                source
                for source in ignored_sources
                if source.get("identity") in selected
            ]
        # 「站点功能测活」弹窗文件夹开关过滤：开关关闭的类型，其文件跳过测活。
        _switches = self._site_test_folder_switches
        active_sources = [
            source
            for source in active_sources
            if _switches.get(str(source.get("type", "")).upper(), True)
        ]
        ignored_sources = [
            source
            for source in ignored_sources
            if _switches.get(str(source.get("type", "")).upper(), True)
        ]
        all_sources = ignored_sources + active_sources
        source_by_identity = {
            source["identity"]: source for source in all_sources
        }
        if not all_sources:
            return {
                "tested": 0,
                "cached": 0,
                "available": 0,
                "unavailable": 0,
                "limited": 0,
                "blocked": 0,
                "restored": 0,
                "remaining": 0,
                "retest": False,
            }
        previous_ignored = set(self.ignored_sources)
        previous_manual_ignored = set(self.manual_ignored_sources)
        previous_auto_blocked = set(self.auto_blocked_sources)
        previous_results = dict(self.site_test_results)
        previous_cache = copy.deepcopy(self.cache)
        previous_status = self.status
        previous_retest_pending = list(self._retest_pending)
        previous_retest_auto_blocked = set(self._retest_auto_blocked)
        retest = bool(self._retest_pending) and not targeted
        if targeted:
            pending_all = list(all_sources) if force else [
                source
                for source in active_sources
                if not self._has_fresh_test_result(source)
            ]
            pending_count = len(pending_all)
            pending = pending_all  # 取消测活上限：整批全测
            cached_count = max(0, len(all_sources) - pending_count)
        elif force and not retest:
            self._retest_pending = [
                source["identity"] for source in all_sources
            ]
            self._retest_auto_blocked = set(self.auto_blocked_sources)
            for source in all_sources:
                source["test_result"] = {}
            retest = True
        if targeted:
            pass
        elif retest:
            self._retest_pending = [
                identity
                for identity in self._retest_pending
                if identity in source_by_identity
            ]
            pending_identities = self._retest_pending  # 取消测活上限：整批全测
            pending = [
                source_by_identity[identity] for identity in pending_identities
            ]
            pending_count = len(self._retest_pending)
            cached_count = max(0, len(all_sources) - pending_count)
        else:
            pending_all = [
                source
                for source in active_sources
                if not self._has_fresh_test_result(source)
            ]
            pending = pending_all  # 取消测活上限：整批全测
            pending_count = len(pending_all)
            cached_count = len(active_sources) - len(pending_all)
        counts = {"available": 0, "unavailable": 0, "limited": 0}
        blocked = 0
        restored = 0
        total = len(pending)
        self._log(
            "INFO",
            "开始站点检测: 模式={} 待请求={} 缓存命中={} 总站点={}".format(
                "全部复检" if retest else "增量检测",
                total,
                cached_count,
                len(all_sources),
            ),
        )
        self._site_test_toast = None
        executor = None
        try:
            completed_count = 0

            def record_result(source, result):
                nonlocal blocked, restored, completed_count
                completed_count += 1
                result = self._finalize_test_result(source, result)
                result["source_signature"] = self._source_signature(source)
                state = result["state"]
                counts[state] += 1
                self.site_test_results[source["identity"]] = result
                self._append_site_test_history(source["identity"], result)
                source["test_result"] = result
                state_label = self._test_result_label(result)
                source_name = " ".join(
                    str(source.get("name", "未命名站点")).split()
                )[:60]
                self._log(
                    "INFO",
                    "站点检测 [{}/{}] {}: {} | {} | {}".format(
                        completed_count,
                        total,
                        source_name or "未命名站点",
                        state_label,
                        result.get("detail", ""),
                        source.get("path", source.get("identity", "")),
                    ),
                )
                notified = self._notify_app(
                    "[{}/{}] {}：{}".format(
                        completed_count,
                        total,
                        source_name or "未命名站点",
                        state_label,
                    ),
                    wait=True,
                    replace=False,
                )
                # 逐站进度同步到在途进度面板（若无面板则 _update_progress_panel 内部退化为 toast）
                self._update_progress_panel(
                    "[{}/{}] {}：{}".format(
                        completed_count,
                        total,
                        source_name or "未命名站点",
                        state_label,
                    )
                )
                if notified:
                    time.sleep(0.15)
                if (
                    (
                        state == "limited"
                        or (
                            state == "unavailable"
                            and bool(result.get("confirmed", False))
                        )
                    )
                    and source["identity"] not in self.auto_blocked_sources
                ):
                    # 受限与已确认失效都进屏蔽分类：首次失效已被降级为受限，
                    # 若受限不入屏蔽，这些站点将既不可见也无人处理。
                    was_ignored = source["identity"] in self.ignored_sources
                    self.auto_blocked_sources.add(source["identity"])
                    self._sync_ignored_sources()
                    if not was_ignored:
                        blocked += 1
                elif (
                    state == "available"
                    and source["identity"] in self.auto_blocked_sources
                ):
                    # 任意一次测活合格即解除自动屏蔽：否则普通测活测通的
                    # 站点会显示「可用」却仍留在屏蔽分类里。
                    self.auto_blocked_sources.discard(source["identity"])
                    self._sync_ignored_sources()
                    self._retest_auto_blocked.discard(source["identity"])
                    restored += 1

            workers = max(1, min(int(self.SITE_TEST_CONCURRENCY), total or 1, 16))
            executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=workers,
                thread_name_prefix="site-functional-test",
            )
            future_sources = {
                executor.submit(self._test_source_availability, source): source
                for source in pending
            }
            waiting = set(future_sources)
            deadline = time.monotonic() + max(
                self.SITE_FUNCTION_TEST_TIMEOUT,
                ((total + workers - 1) // workers)
                * self.SITE_FUNCTION_TEST_TIMEOUT,
            )
            while waiting and time.monotonic() < deadline:
                if self._site_test_cancel.is_set():
                    raise SiteTestCancelled("站点检测已取消")
                done, waiting = concurrent.futures.wait(
                    waiting,
                    timeout=min(0.5, max(0.0, deadline - time.monotonic())),
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                for future in done:
                    source = future_sources[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = self._test_result(
                            "limited",
                            "App 真实 Spider 检测异常: {}".format(exc),
                            time.strftime("%Y-%m-%d %H:%M:%S"),
                            test_stage="functional",
                        )
                    record_result(source, result)
            for future in waiting:
                future.cancel()
                record_result(
                    future_sources[future],
                    self._test_result(
                        "limited",
                        "App 真实 Spider 超过批次等待时间",
                        time.strftime("%Y-%m-%d %H:%M:%S"),
                        test_stage="functional",
                    ),
                )
            executor.shutdown(wait=False, cancel_futures=True)
            if targeted:
                remaining = max(0, pending_count - len(pending))
            elif retest:
                processed = {source["identity"] for source in pending}
                self._retest_pending = [
                    identity
                    for identity in self._retest_pending
                    if identity not in processed
                ]
                remaining = len(self._retest_pending)
                if not remaining:
                    self._retest_auto_blocked.clear()
            else:
                remaining = max(0, pending_count - len(pending))
            pruned = self._prune_blocked_sources_locked()
            self._save_settings()
            if blocked or restored or pruned:
                if not self._refresh_locked(allow_empty=True):
                    raise ValueError(self.status["error"] or self.status["write_state"])
            summary = {
                "tested": len(pending),
                "cached": cached_count,
                "available": counts["available"],
                "unavailable": counts["unavailable"],
                "limited": counts["limited"],
                "blocked": blocked,
                "restored": restored,
                "pruned": pruned,
                "remaining": remaining,
                "retest": bool(force or retest),
            }
            self._log(
                "INFO",
                "站点检测完成: 请求={tested} 可用={available} 功能或结构失效={unavailable} "
                "受限={limited} 新增失效屏蔽={blocked} 恢复={restored} 剩余={remaining}".format(
                    **summary
                ),
            )
            return summary
        except Exception as exc:
            if executor is not None:
                try:
                    executor.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass
            self._log(
                "INFO" if isinstance(exc, SiteTestCancelled) else "ERROR",
                "站点检测批次{}: {}".format(
                    "已取消" if isinstance(exc, SiteTestCancelled) else "失败",
                    exc,
                ),
            )
            self.ignored_sources = previous_ignored
            self.manual_ignored_sources = previous_manual_ignored
            self.auto_blocked_sources = previous_auto_blocked
            self.site_test_results = previous_results
            self.cache = previous_cache
            self.status = previous_status
            self._retest_pending = previous_retest_pending
            self._retest_auto_blocked = previous_retest_auto_blocked
            try:
                self._save_settings()
            except Exception:
                pass
            raise

    def _site_test_summary_text(self, summary):
        return (
            "站点检测完成：请求 {tested}，可用 {available}，"
            "功能或结构失效 {unavailable}，受限 {limited}，"
            "新增屏蔽 {blocked}，恢复 {restored}，剩余 {remaining}"
        ).format(**summary)

    def _execute_site_test(self, force=False, source_identities=None):
        """Shared completion path for manual and download-triggered health checks."""
        summary = self._test_sites_locked(
            force=force,
            source_identities=source_identities,
        )
        if summary["blocked"] or summary["restored"]:
            _, reload_detail = self._reload_app_vod_config(
                expected_keys=self._generated_registry_keys()
            )
        else:
            reload_detail = "屏蔽状态未变化，无需重载"
        self.inited = True
        summary_text = self._site_test_summary_text(summary)
        self._log("INFO", "{}；{}".format(summary_text, reload_detail))
        if not self._destroyed:
            self._notify_app(summary_text)
        return summary, summary_text

    def _run_site_test_worker(self, force):
        current = threading.current_thread()
        try:
            self._execute_site_test(force=force)
        except SiteTestCancelled:
            self._log("INFO", "站点检测后台任务已取消")
        except Exception as exc:
            message = "站点检测失败：{}".format(exc)
            self._log("ERROR", "站点检测后台任务失败: {}".format(exc))
            if not self._destroyed:
                self._notify_app(message)
        finally:
            with self._site_test_control_lock:
                if self._site_test_thread is current:
                    self._site_test_thread = None

    def _start_site_test_worker(self, force=False):
        # 启动线程时只持有 _site_test_control_lock，不阻塞其他操作
        with self._site_test_control_lock:
            worker = self._site_test_thread
            if worker is not None and worker.is_alive():
                return False
            worker = threading.Thread(
                target=self._run_site_test_worker,
                args=(bool(force),),
                name="webhtv-site-test",
            )
            worker.daemon = True
            self._destroyed = False
            self._site_test_cancel.clear()
            self._site_test_thread = worker
            worker.start()
            return True

    def _site_test_is_running(self):
        with self._site_test_control_lock:
            worker = self._site_test_thread
            return worker is not None and worker.is_alive()

    def _source_signature(self, source):
        size = source.get("size")
        modified_ns = source.get("mtime_ns")
        if size is None or modified_ns is None:
            try:
                stat = os.stat(source["path"])
                size = stat.st_size
                modified_ns = getattr(
                    stat, "st_mtime_ns", int(stat.st_mtime * 1000000000)
                )
            except Exception:
                return "missing"
        signature_data = {
            "version": self.SITE_TEST_CACHE_VERSION,
            "type": str(source.get("type", "")).upper(),
            "size": int(size),
            "mtime_ns": int(modified_ns),
        }
        if source.get("dependencies"):
            dependency_stats = []
            for path in source.get("dependencies", []):
                try:
                    stat = os.stat(path)
                    dependency_stats.append(
                        {
                            "path": self._file_url(path),
                            "size": int(stat.st_size),
                            "mtime_ns": int(
                                getattr(
                                    stat,
                                    "st_mtime_ns",
                                    int(stat.st_mtime * 1000000000),
                                )
                            ),
                        }
                    )
                except Exception:
                    dependency_stats.append(
                        {"path": self._file_url(path), "missing": True}
                    )
            signature_data["dependencies"] = dependency_stats
        proxy_values = {
            name: str(os.environ.get(name, ""))
            for name in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "NO_PROXY",
                "http_proxy",
                "https_proxy",
                "no_proxy",
            )
            if os.environ.get(name)
        }
        signature_data["proxy"] = self._digest(
            json.dumps(proxy_values, sort_keys=True, separators=(",", ":")), 16
        )
        raw = json.dumps(
            signature_data, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _has_fresh_test_result(self, source):
        result = self.site_test_results.get(source["identity"])
        if (
            not isinstance(result, dict)
            or result.get("state") not in ("available", "unavailable", "limited")
            or result.get("source_signature") != self._source_signature(source)
        ):
            return False
        try:
            checked_ts = float(result.get("checked_ts", 0) or 0)
        except Exception:
            checked_ts = 0
        if checked_ts <= 0:
            return False
        ttl = {
            "available": self.SITE_TEST_AVAILABLE_TTL,
            "unavailable": self.SITE_TEST_FAILURE_TTL,
            "limited": self.SITE_TEST_LIMITED_TTL,
        }[result["state"]]
        return time.time() - checked_ts < max(1, float(ttl))

    def _site_option_text(self, value):
        if value in (None, ""):
            return ""
        if isinstance(value, str):
            return value
        return json.dumps(
            value, ensure_ascii=False, separators=(",", ":")
        )

    def _spider_result_data(self, payload):
        if isinstance(payload, dict):
            data = payload
        else:
            text = str(payload or "").strip()
            if not text:
                return None
            data = json.loads(text)
        return data if isinstance(data, dict) else None

    def _spider_result_items(self, payload):
        data = self._spider_result_data(payload)
        if data is None:
            return None, []
        items = data.get("list", [])
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            items = []
        return data, [item for item in items if isinstance(item, dict)]

    def _spider_result_counts(self, payload):
        data, items = self._spider_result_items(payload)
        if data is None:
            return None
        types = data.get("class", [])
        if isinstance(types, dict):
            types = [types]
        return {
            "items": len(items),
            "item_values": items,
            "types": [
                item for item in types if isinstance(item, dict)
            ] if isinstance(types, list) else [],
            "message": str(data.get("msg", "") or "").strip(),
        }

    def _first_vod_candidate(self, items):
        for item in items or []:
            if not isinstance(item, dict):
                continue
            vod_id = item.get("vod_id", item.get("vodId", item.get("id", "")))
            vod_id = str(vod_id or "").strip()
            if not vod_id:
                continue
            return {
                "id": vod_id,
                "name": str(
                    item.get("vod_name", item.get("vodName", item.get("name", "")))
                    or ""
                ).strip()[:80],
            }
        return {}

    def _extract_play_candidate(self, payload):
        data, items = self._spider_result_items(payload)
        if data is None or not items:
            return {}
        for item in items:
            play_from = item.get("vod_play_from", item.get("vodPlayFrom", ""))
            play_url = item.get("vod_play_url", item.get("vodPlayUrl", ""))
            if isinstance(play_url, list):
                play_url = "$$$".join(str(value or "") for value in play_url)
            play_url = str(play_url or "").strip()
            if not play_url:
                continue
            flags = str(play_from or "").split("$$$")
            groups = play_url.split("$$$")
            for group_index, group in enumerate(groups):
                flag = flags[group_index].strip() if group_index < len(flags) else ""
                for raw_episode in str(group or "").split("#"):
                    raw_episode = raw_episode.strip()
                    if not raw_episode:
                        continue
                    if "$" in raw_episode:
                        name, episode_id = raw_episode.split("$", 1)
                    else:
                        name, episode_id = raw_episode, raw_episode
                    episode_id = str(episode_id or "").strip()
                    if not episode_id:
                        continue
                    return {
                        "flag": flag,
                        "id": episode_id,
                        "name": str(name or "").strip()[:80],
                    }
        return {}

    def _normalize_player_headers(self, value):
        if isinstance(value, str):
            text = value.strip()
            if text:
                try:
                    value = json.loads(text)
                except Exception:
                    value = {}
        if not isinstance(value, dict):
            return {}
        headers = {}
        for key, item in value.items():
            name = str(key or "").strip()
            content = str(item or "").strip()
            if (
                not name
                or not content
                or "\r" in name
                or "\n" in name
                or "\r" in content
                or "\n" in content
            ):
                continue
            headers[name[:120]] = content[:2000]
        return headers

    def _parse_player_payload(self, payload):
        data = self._spider_result_data(payload)
        if data is None:
            return {}
        url_value = data.get("url", "")
        if isinstance(url_value, list):
            url_value = next(
                (
                    item
                    for item in url_value
                    if isinstance(item, str) and item.strip()
                ),
                "",
            )
        url = str(url_value or "").strip()
        parse_value = data.get("parse", data.get("jx", 0))
        try:
            parse_mode = int(parse_value or 0)
        except Exception:
            parse_mode = 1 if self._as_bool(parse_value, False) else 0
        return {
            "url": url,
            "parse": parse_mode,
            "headers": self._normalize_player_headers(
                data.get("header", data.get("headers", {}))
            ),
            "message": str(data.get("msg", "") or "").strip()[:160],
        }

    def _remaining_probe_timeout(self, deadline):
        remaining = float(deadline) - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("媒体检查时间已用尽")
        return max(0.25, min(float(self.MEDIA_PROBE_TIMEOUT), remaining))

    def _open_media_sample(self, url, headers, deadline, limit=None):
        request_headers = self._normalize_player_headers(headers)
        request_headers.setdefault("User-Agent", "Mozilla/5.0 LocalMediaHub/5")
        request_headers.setdefault("Accept", "*/*")
        request_headers.setdefault("Accept-Encoding", "identity")
        request_headers["Range"] = "bytes=0-{}".format(
            max(0, int((limit or self.MEDIA_SAMPLE_BYTES)) - 1)
        )
        request = urllib.request.Request(url, headers=request_headers, method="GET")
        with urllib.request.urlopen(
            request, timeout=self._remaining_probe_timeout(deadline)
        ) as response:
            status = int(getattr(response, "status", response.getcode()))
            max_bytes = max(1, int(limit or self.MEDIA_SAMPLE_BYTES))
            body = response.read(max_bytes + 1)[:max_bytes]
            return {
                "status": status,
                "url": str(response.geturl() or url),
                "content_type": str(
                    response.headers.get("Content-Type", "") or ""
                ).split(";", 1)[0].strip().lower(),
                "content_length": str(
                    response.headers.get("Content-Length", "") or ""
                ).strip(),
                "content_range": str(
                    response.headers.get("Content-Range", "") or ""
                ).strip(),
                "body": body,
            }

    def _media_sample_format(self, body, content_type=""):
        data = bytes(body or b"")
        lower_type = str(content_type or "").lower()
        if data.lstrip().startswith(b"#EXTM3U"):
            return "hls"
        if len(data) >= 12 and data[4:8] == b"ftyp":
            return "mp4"
        if data.startswith(b"FLV"):
            return "flv"
        if data.startswith(b"OggS"):
            return "ogg"
        if data.startswith(b"fLaC"):
            return "flac"
        if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
            return "wav"
        if data.startswith(b"\x1aE\xdf\xa3"):
            return "matroska"
        if data.startswith(b"ID3") or (
            len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0
        ):
            return "audio"
        for offset in range(min(188, len(data))):
            if (
                len(data) > offset + 376
                and data[offset] == 0x47
                and data[offset + 188] == 0x47
                and data[offset + 376] == 0x47
            ):
                return "mpegts"
        if lower_type.startswith("video/"):
            return "video"
        if lower_type.startswith("audio/"):
            return "audio"
        return ""

    def _media_result(self, state, playback_state, detail, sample=None, fmt=""):
        sample = sample if isinstance(sample, dict) else {}
        final_url = str(sample.get("url", "") or "")
        parsed = urllib.parse.urlsplit(final_url)
        media = {
            "host": str(parsed.hostname or ""),
            "status": int(sample.get("status", 0) or 0),
            "content_type": str(sample.get("content_type", "") or ""),
            "sample_bytes": len(sample.get("body", b"") or b""),
            "format": fmt or "unknown",
        }
        length = str(sample.get("content_length", "") or "")
        if length.isdigit():
            media["content_length"] = int(length)
        return {
            "state": state,
            "playback_state": playback_state,
            "detail": str(detail or "")[:240],
            "media": media,
        }

    def _probe_hls_playlist(self, sample, headers, deadline, depth=0):
        body = bytes(sample.get("body", b"") or b"")
        try:
            text = body.decode("utf-8-sig", errors="replace")
        except Exception:
            text = ""
        if "#EXTM3U" not in text[:4096]:
            return self._media_result(
                "limited",
                "media_failed",
                "播放地址返回的 HLS 清单格式异常",
                sample,
                "hls",
            )
        candidates = []
        for line in text.splitlines():
            value = line.strip()
            if not value or value.startswith("#") or len(value) > 4096:
                continue
            candidate = urllib.parse.urljoin(str(sample.get("url", "")), value)
            parsed = urllib.parse.urlsplit(candidate)
            if parsed.scheme.lower() in ("http", "https") and parsed.netloc:
                candidates.append(candidate)
        if not candidates:
            return self._media_result(
                "limited",
                "media_failed",
                "HLS 清单未发现可抽样的变体或媒体分片",
                sample,
                "hls",
            )
        try:
            nested = self._open_media_sample(
                candidates[0], headers, deadline, self.MEDIA_PLAYLIST_BYTES
            )
        except urllib.error.HTTPError as exc:
            state = "limited" if int(exc.code) in (401, 403) else "unavailable"
            playback_state = "auth_required" if state == "limited" else "media_failed"
            return self._media_result(
                state,
                playback_state,
                "HLS 抽样请求返回 HTTP {}".format(exc.code),
                {"url": candidates[0], "status": int(exc.code)},
                "hls",
            )
        nested_body = bytes(nested.get("body", b"") or b"")
        if nested_body.lstrip().startswith(b"#EXTM3U") and depth < 2:
            return self._probe_hls_playlist(nested, headers, deadline, depth + 1)
        if not nested_body:
            return self._media_result(
                "unavailable",
                "media_failed",
                "HLS 媒体分片为空",
                nested,
                "hls",
            )
        return self._media_result(
            "available",
            "media_sample",
            "HLS 清单与首个媒体分片抽样通过",
            nested,
            "hls",
        )

    def _probe_media_url(self, url, headers=None, deadline=None):
        value = str(url or "").strip()
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
            return self._media_result(
                "limited",
                "native_parse",
                "播放结果需要 App 原生协议或解析器处理",
                {"url": value},
            )
        deadline = float(deadline or (time.monotonic() + self.MEDIA_PROBE_TIMEOUT * 3))
        try:
            sample = self._open_media_sample(value, headers or {}, deadline)
        except urllib.error.HTTPError as exc:
            code = int(exc.code)
            if code in (401, 403):
                return self._media_result(
                    "limited",
                    "auth_required",
                    "媒体地址需要登录或授权，HTTP {}".format(code),
                    {"url": value, "status": code},
                )
            return self._media_result(
                "unavailable",
                "media_failed",
                "媒体地址返回 HTTP {}".format(code),
                {"url": value, "status": code},
            )
        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            return self._media_result(
                "limited",
                "media_failed",
                "媒体抽样请求受限: {}".format(str(exc)[:120]),
                {"url": value},
            )
        except Exception as exc:
            return self._media_result(
                "limited",
                "media_failed",
                "媒体抽样检查异常: {}".format(str(exc)[:120]),
                {"url": value},
            )

        body = bytes(sample.get("body", b"") or b"")
        content_type = str(sample.get("content_type", "") or "").lower()
        lowered = body[:4096].lstrip().lower()
        if (
            "mpegurl" in content_type
            or parsed.path.lower().endswith(".m3u8")
            or body.lstrip().startswith(b"#EXTM3U")
        ):
            return self._probe_hls_playlist(sample, headers or {}, deadline)
        if (
            content_type in ("text/html", "application/xhtml+xml")
            or lowered.startswith(b"<!doctype html")
            or lowered.startswith(b"<html")
        ):
            return self._media_result(
                "limited",
                "auth_required",
                "播放地址返回网页内容，可能需要登录、Cookie 或 WebView",
                sample,
            )
        if not body:
            return self._media_result(
                "unavailable",
                "media_failed",
                "媒体地址抽样内容为空",
                sample,
            )
        fmt = self._media_sample_format(body, content_type)
        if fmt:
            return self._media_result(
                "available",
                "media_sample",
                "直链媒体样本通过，格式 {}".format(fmt),
                sample,
                fmt,
            )
        return self._media_result(
            "limited",
            "direct_url",
            "已解析直链并取得数据，媒体格式仍需 App 播放器确认",
            sample,
        )

    def _test_source_functionality(self, source, checked_at):
        started = time.monotonic()
        source_name = source.get("name", "")[:40]
        source_identity = source.get("identity", "")[:20]

        def complete(used, result):
            if isinstance(result, dict):
                elapsed = max(0, int((time.monotonic() - started) * 1000))
                result.setdefault("elapsed_ms", elapsed)
                self._log(
                    "DEBUG",
                    "站点 {} ({}) 测活完成 - 阶段: {}, 状态: {}, 耗时: {} ms, 详情: {}".format(
                        source_name,
                        source_identity,
                        result.get("test_stage", "-"),
                        result.get("state", "-"),
                        elapsed,
                        str(result.get("detail", ""))[:80],
                    ),
                )
            return used, result

        if source.get("type") == "HTML":
            probe_url = self._source_probe_url(source)
            if probe_url:
                self._log(
                    "DEBUG",
                    "站点 {} ({}) 开始 HTML 连通性检测 - URL: {}".format(
                        source_name, source_identity, probe_url[:80]
                    ),
                )
                state, detail = self._probe_site_url(probe_url)
                return complete(
                    True,
                    self._test_result(
                        state,
                        "HTML 站点连通性检测: {}".format(detail),
                        checked_at,
                        origin=self._url_origin(probe_url),
                        failure_kind="connectivity" if state != "available" else "",
                    ),
                )
            return False, None
        site = source.get("site", {})
        if not isinstance(site, dict):
            return complete(
                True,
                self._test_result(
                    "unavailable",
                    "生成站点配置缺失",
                    checked_at,
                    failure_kind="structural",
                ),
            )
        api = self._site_option_text(site.get("api", ""))
        if not api:
            return complete(
                True,
                self._test_result(
                    "unavailable",
                    "站点运行入口缺失",
                    checked_at,
                    failure_kind="structural",
                ),
            )
        # 取消测活：CSP 站点需调取 jar 才能驱动 Spider。功能测活需要加载并运行
        # jar 内的 Spider 代码，这里统一跳过，站点保留为可用而不被屏蔽。
        if str(source.get("type", "")).upper() == "CSP":
            jar_opt = self._site_option_text(site.get("jar", ""))
            if str(jar_opt).strip():
                return complete(
                    True,
                    self._test_result(
                        "available",
                        "CSP 站点需调取 jar，已跳过功能测活",
                        checked_at,
                        test_stage="functional",
                    ),
                )
        # 与宿主 Site.objectFrom 的 UrlUtil.convert 对齐：本机运行时只能
        # 通过 App 的 HTTP 服务读取 file:// 资源。
        runtime_api = self._runtime_site_reference(api)
        runtime_ext = self._runtime_site_reference(
            self._site_option_text(site.get("ext", ""))
        )
        if runtime_api.lower().startswith("file://"):
            # 端口没探到就不要硬跑：初始化必然失败，且失败原因与脚本无关。
            return complete(
                True,
                self._test_result(
                    "limited",
                    "未探测到 App 本机服务端口，无法加载本地脚本，已跳过功能测活",
                    checked_at,
                    test_stage="functional",
                ),
            )
        try:
            from java import jclass

            loader = jclass(
                "com.fongmi.android.tv.api.loader.BaseLoader"
            ).get()
        except Exception:
            # 兼容没有公开 BaseLoader 的旧宿主，由后续静态/连通性检查接管。
            return False, None
        try:
            spider = loader.getSpider(
                # 测活使用源 identity 派生的唯一 key，避免不同本地包
                # 恰好使用同一 TVBox site.key 时复用了第一个 Spider。
                "{}audit_{}".format(
                    self.GENERATED_KEY_PREFIX,
                    self._digest(
                        "{}|{}".format(
                            source.get("identity", ""),
                            self._source_signature(source),
                        ),
                        20,
                    ),
                ),
                runtime_api,
                runtime_ext,
                self._site_option_text(site.get("jar", "")),
            )
        except Exception as exc:
            return complete(
                True,
                self._static_entry_fallback(
                    source,
                    checked_at,
                    "App 真实 Spider 初始化异常: {}".format(str(exc)[:120]),
                ),
            )

        try:
            spider_class = str(spider.getClass().getName())
        except Exception:
            spider_class = ""
        if spider is None or spider_class.endswith("SpiderNull"):
            return complete(
                True,
                self._static_entry_fallback(
                    source, checked_at, "App 真实 Spider 初始化失败"
                ),
            )

        # [exit-guard] 测活退出防护：在真正执行站点 JAR 的 Spider 方法（
        # homeContent/categoryContent/searchContent/liveContent 等）之前，
        # 先对站点主脚本与本地依赖做“高危退出/杀进程”静态筛查。站点 JS 运行
        # 在宿主 QuickJS 引擎内，与脚本同进程，若其调用 System.exit /
        # Process.killProcess 等就会连带让整个 App 进程退出重启，脚本无法在
        # 进程级拦截（Android 已移除 SecurityManager）。唯一可靠的阻断手段是
        # 不让疑似危险代码运行：命中即跳过本次功能测活、清理已加载 Spider，
        # 并把站点归类为“受限”保留，避免触发退出。做到“测活期间不让站点拥有
        # 退出 App 的能力”。
        try:
            risk_matches = self._scan_site_exit_risk(source)
        except Exception as exc:
            risk_matches = ["筛查异常: {}".format(str(exc)[:80])]
        if risk_matches:
            try:
                remove = getattr(loader, "removeSpiders", None) or getattr(
                    loader, "removeSpider", None
                )
                if callable(remove):
                    try:
                        remove(key)
                    except TypeError:
                        remove()
            except Exception:
                pass
            self._warn(
                "站点 {} ({}) 测活执行前检出疑似退出风险代码，已跳过并清理 Spider: {}".format(
                    source_name, source_identity, "；".join(risk_matches)[:120]
                )
            )
            return complete(
                True,
                self._test_result(
                    "limited",
                    "检测到疑似退出风险代码，已跳过测活，避免 App 退出重启: {}".format(
                        "；".join(risk_matches)[:160]
                    ),
                    checked_at,
                    test_stage="functional",
                ),
            )

        valid_responses = 0
        list_items = 0
        errors = []
        categories = []
        candidate = {}
        candidate_stage = ""
        deadline = started + max(1.0, float(self.SITE_FUNCTION_TEST_TIMEOUT))

        # 检测是否为直播站点
        site_type = site.get("type", 0)
        is_live = int(site_type or 0) == 1 or "/live/" in api.lower()

        def inspect(label, callback):
            nonlocal valid_responses, categories, list_items
            try:
                if time.monotonic() >= deadline:
                    raise TimeoutError("检测时间已用尽")
                counts = self._spider_result_counts(callback())
                if counts is None:
                    errors.append("{}返回为空".format(label))
                    return 0, {}
                valid_responses += 1
                categories.extend(counts["types"])
                list_items += counts["items"]
                if counts["items"] > 0:
                    return counts["items"], self._first_vod_candidate(
                        counts.get("item_values", [])
                    )
                if counts["message"]:
                    errors.append("{}: {}".format(label, counts["message"][:80]))
                return 0, {}
            except Exception as exc:
                errors.append("{}: {}".format(label, str(exc)[:100]))
                return 0, {}

        # 直播站点测活
        if is_live:
            try:
                if time.monotonic() >= deadline:
                    raise TimeoutError("直播检测时间已用尽")
                live_payload = spider.liveContent("")
                live_data = self._spider_result_data(live_payload)
                if live_data is None:
                    return complete(
                        True,
                        self._test_result(
                            "unavailable",
                            "直播站点 liveContent 返回为空",
                            checked_at,
                            failure_kind="functional",
                            test_stage="live",
                        ),
                    )
                live_class = live_data.get("class", [])
                if isinstance(live_class, dict):
                    live_class = [live_class]
                if not isinstance(live_class, list) or not live_class:
                    return complete(
                        True,
                        self._test_result(
                            "unavailable",
                            "直播站点未返回频道分类",
                            checked_at,
                            failure_kind="functional",
                            test_stage="live",
                        ),
                    )
                live_list = live_data.get("list", [])
                if isinstance(live_list, dict):
                    live_list = [live_list]
                channel_count = len([item for item in live_list if isinstance(item, dict)])
                result = self._test_result(
                    "available",
                    "直播站点返回 {} 个分类、{} 个频道".format(
                        len(live_class), channel_count
                    ),
                    checked_at,
                    test_stage="live",
                )
                result["playback_state"] = "live_ok"
                return complete(True, result)
            except Exception as exc:
                return complete(
                    True,
                    self._test_result(
                        "unavailable",
                        "直播站点 liveContent 检测异常: {}".format(str(exc)[:120]),
                        checked_at,
                        failure_kind="functional",
                        test_stage="live",
                    ),
                )

        count, item = inspect("首页", lambda: spider.homeContent(True))
        if not count:
            count, item = inspect("首页推荐", spider.homeVideoContent)
        if item:
            candidate = item
            candidate_stage = "home"

        category_seen = set()
        for category in categories[:5] if not candidate else []:
            type_id = str(
                category.get("type_id", category.get("typeId", "")) or ""
            ).strip()
            if not type_id or type_id in category_seen:
                continue
            category_seen.add(type_id)
            try:
                java_ext = jclass("java.util.HashMap")()
            except Exception:
                java_ext = {}
            count, item = inspect(
                "分类 {}".format(type_id),
                lambda tid=type_id, ext=java_ext: spider.categoryContent(
                    tid, "1", True, ext
                ),
            )
            if item:
                candidate = item
                candidate_stage = "category"
                break

        searchable = self._as_bool(site.get("searchable", True), True)
        if searchable and not candidate:
            for search_term in ["爱", "人", "家"]:
                count, item = inspect(
                    "搜索 '{}'".format(search_term),
                    lambda term=search_term: spider.searchContent(term, False),
                )
                if item:
                    candidate = item
                    candidate_stage = "search"
                    break

        if candidate:
            try:
                ids = jclass("java.util.ArrayList")()
                ids.add(candidate["id"])
            except Exception:
                ids = [candidate["id"]]
            try:
                if time.monotonic() >= deadline:
                    raise TimeoutError("详情检测时间已用尽")
                detail_payload = spider.detailContent(ids)
                detail_data, detail_items = self._spider_result_items(detail_payload)
                if detail_data is None or not detail_items:
                    result = self._test_result(
                        "available",
                        "列表可用，但 App 真实 Spider 详情返回为空",
                        checked_at,
                        test_stage="detail",
                    )
                    result["playback_state"] = "list_only"
                    return complete(True, result)
                play = self._extract_play_candidate(detail_data)
                if not play:
                    result = self._test_result(
                        "available",
                        "列表与详情可用，但详情未提供可抽样的选集",
                        checked_at,
                        test_stage="detail",
                    )
                    result["playback_state"] = "detail_ok"
                    return complete(True, result)
            except Exception as exc:
                result = self._test_result(
                    "available",
                    "列表可用，详情检测受限: {}".format(str(exc)[:120]),
                    checked_at,
                    test_stage="detail",
                )
                result["playback_state"] = "list_only"
                return complete(True, result)

            try:
                try:
                    vip_flags = jclass("java.util.ArrayList")()
                except Exception:
                    vip_flags = []
                if time.monotonic() >= deadline:
                    raise TimeoutError("播放解析时间已用尽")
                player_payload = spider.playerContent(
                    play.get("flag", ""), play["id"], vip_flags
                )
                player = self._parse_player_payload(player_payload)
                if not player and urllib.parse.urlsplit(play["id"]).scheme.lower() in (
                    "http",
                    "https",
                ):
                    player = {"url": play["id"], "parse": 0, "headers": {}}
                if not player or not player.get("url"):
                    result = self._test_result(
                        "available",
                        "详情与选集可用，但 App 真实 Spider 播放解析返回为空",
                        checked_at,
                        test_stage="player",
                    )
                    result["playback_state"] = "detail_ok"
                    return complete(True, result)
                if int(player.get("parse", 0) or 0):
                    result = self._test_result(
                        "available",
                        "详情与选集可用，播放地址交由 App 原生解析器处理",
                        checked_at,
                        test_stage="player",
                    )
                    result["playback_state"] = "native_parse"
                    return complete(True, result)
            except Exception as exc:
                result = self._test_result(
                    "available",
                    "详情与选集可用，播放解析受限: {}".format(str(exc)[:120]),
                    checked_at,
                    test_stage="player",
                )
                result["playback_state"] = "detail_ok"
                return complete(True, result)

            probe = self._probe_media_url(
                player["url"], player.get("headers", {}), deadline=deadline
            )
            # 对照海阔视界 RuleVerifyActivity：站点是否失效由首页/搜索
            # 是否能返回规则数据决定。详情、选集或媒体抽样结果单独记在
            # playback_state/detail，不能因为单个章节、鉴权音频或临时
            # 媒体错误把整个 275 听书站点判为失效并从 App 列表删除。
            playback_state = probe.get("playback_state", "")
            probe_state = "available"
            result = self._test_result(
                probe_state,
                "{}抽样：{}".format(
                    {
                        "home": "首页",
                        "category": "分类",
                        "search": "搜索",
                    }.get(candidate_stage, "列表"),
                    probe["detail"],
                ),
                checked_at,
                failure_kind="",
                test_stage="media" if probe_state == "available" else "player",
            )
            result["playback_state"] = playback_state
            result["media"] = probe.get("media", {})
            return complete(True, result)

        if list_items:
            result = self._test_result(
                "available",
                "App 真实 Spider 返回 {} 条列表数据，但未找到可进入详情的 vod_id".format(
                    list_items
                ),
                checked_at,
                test_stage="functional",
            )
            result["playback_state"] = "list_only"
            return complete(True, result)

        if valid_responses:
            detail = "App 真实 Spider 首页、分类和搜索均未返回数据"
            if errors:
                detail += "；" + "；".join(errors[:2])
            return complete(
                True,
                self._test_result(
                    "unavailable",
                    detail,
                    checked_at,
                    failure_kind="functional",
                    test_stage="functional",
                ),
            )
        return complete(
            True,
            self._test_result(
                "limited",
                "App 真实 Spider 调用受限：{}".format(
                    "；".join(errors[:2]) or "没有有效响应"
                ),
                checked_at,
                test_stage="functional",
            ),
        )

    def _test_source_availability(self, source):
        checked_at = time.strftime("%Y-%m-%d %H:%M:%S")
        source_type = source["type"]
        path = source["path"]
        try:
            if not os.path.isfile(path) or not os.access(path, os.R_OK):
                return self._test_result(
                    "unavailable",
                    "源文件不存在或不可读",
                    checked_at,
                    failure_kind="structural",
                )
            package_detail = ""
            if source.get("csp_site"):
                if "#bundle-site-" in str(source.get("identity", "")):
                    missing = [
                        item
                        for item in source.get("dependencies", [])
                        if not os.path.isfile(item) or not os.access(item, os.R_OK)
                    ]
                    if missing:
                        return self._test_result(
                            "unavailable",
                            "整包站点本地依赖已缺失: {}".format(missing[0]),
                            checked_at,
                            failure_kind="structural",
                        )
                    package_detail = source.get("validation", "") or "整包站点依赖完整"
                else:
                    valid, detail = self._validate_source(source_type, path)
                    if not valid:
                        return self._test_result(
                            "unavailable",
                            detail,
                            checked_at,
                            failure_kind="structural",
                        )
                    package_detail = (
                        detail
                        or source.get("validation", "")
                        or "目录包结构有效"
                    )
            if source_type == "HTML":
                valid, detail = self._validate_source("HTML", path)
                if valid:
                    return self._test_result(
                        "available", "本地 WebHome 页面结构有效", checked_at
                    )
                return self._test_result(
                    "unavailable",
                    detail,
                    checked_at,
                    failure_kind="structural",
                )
            if source_type == "JS":
                text = self._read_text(
                    self._source_probe_path(source), 512 * 1024
                )
                if not self._has_direct_js_spider(text):
                    return self._test_result(
                        "unavailable",
                        "未发现可执行的 JS Spider 入口",
                        checked_at,
                        failure_kind="structural",
                    )
            if source_type == "PY":
                valid, detail = self._validate_source("PY", path)
                if not valid:
                    return self._test_result(
                        "unavailable",
                        detail,
                        checked_at,
                        failure_kind="structural",
                    )
            functional_supported, functional_result = (
                self._test_source_functionality(source, checked_at)
            )
            if functional_supported:
                return functional_result

            probe_url = self._source_probe_url(source)
            if not probe_url:
                probe_path = self._source_probe_path(source)
                probe_url = self._extract_probe_url(probe_path)
            if not probe_url:
                return self._test_result(
                    "limited",
                    "{}；未提取到可安全探测的主页地址".format(
                        package_detail
                    ).lstrip("；"),
                    checked_at,
                )
            origin = self._url_origin(probe_url)
            if not origin:
                return self._test_result("limited", "主页地址格式无法确认", checked_at)
            state, detail = self._probe_site_url(probe_url)
            if package_detail:
                detail = package_detail + "；" + detail
            return self._test_result(state, detail, checked_at, origin)
        except Exception as exc:
            return self._test_result(
                "limited", "检测过程受限: {}".format(exc), checked_at
            )

    def _source_probe_path(self, source):
        site = source.get("csp_site", {})
        if isinstance(site, dict):
            fields = ("homePage", "ext", "api") if "#bundle-site-" in str(
                source.get("identity", "")
            ) else (("api",) if source.get("type") == "JS" else ("ext",))
            for field in fields:
                reference = site.get(field, "")
                if isinstance(reference, str) and reference.strip():
                    path = self._site_reference_path(reference)
                    if path and os.path.isfile(path) and os.access(path, os.R_OK):
                        return path
        return source["path"]

    def _source_probe_url(self, source):
        site = source.get("csp_site", {})
        if not isinstance(site, dict):
            return ""
        for field in ("homePage", "ext", "api"):
            value = site.get(field, "")
            if not isinstance(value, str):
                continue
            parsed = urllib.parse.urlsplit(value.strip())
            if parsed.scheme.lower() in ("http", "https") and parsed.netloc:
                return value.strip()
        return ""

    # [exit-guard] 测活退出风险静态筛查
    # 站点 JS 运行在宿主 QuickJS 引擎内，与脚本同进程。若其调用以下任一
    # “进程退出 / 杀进程 / 强制终止”入口，会让整个 App 进程退出重启，脚本
    # 无法在进程级拦截。因此测活执行 Spider 方法前先对源码做静态筛查，
    # 命中即跳过真实执行，从根本上阻断站点“退出 App”的能力。
    EXIT_RISK_PATTERNS = [
        # Java / Python 显式退出
        (re.compile(r"\bSystem\s*\.\s*exit\s*\("), "System.exit"),
        (re.compile(r"\bRuntime\s*\.\s*getRuntime\s*\(\s*\)\s*\.\s*(?:exit|halt)\s*\("), "Runtime.exit/halt"),
        (re.compile(r"\b(?:exit|halt)\s*\(\s*-?[0-9]"), "exit/halt(数值)"),
        (re.compile(r"\bsys\s*\.\s*exit\s*\("), "sys.exit"),
        (re.compile(r"\bos\s*\.\s*_?exit\s*\("), "os._exit"),
        # Android 杀进程
        (re.compile(r"\bkillProcess\s*\("), "killProcess"),
        (re.compile(r"\bmyPid\s*\(\s*\)"), "Process.myPid"),
        (re.compile(r"\bkillBackgroundProcesses\s*\("), "killBackgroundProcesses"),
        (re.compile(r"android\s*\.\s*os\s*\.\s*Process"), "android.os.Process"),
        (re.compile(r"\bProcess\s*\.\s*kill\s*\("), "Process.kill"),
        (re.compile(r"\bexitProcess\s*\("), "exitProcess"),
    ]

    def _scan_site_exit_risk(self, source):
        """对站点主脚本及本地依赖做“退出/杀进程”静态筛查，返回命中特征列表。"""
        hit_signatures = []
        scanned_paths = []

        candidates = [self._source_probe_path(source)]
        dependencies = source.get("dependencies") or []
        if isinstance(dependencies, list):
            for dep in dependencies:
                try:
                    p = self._reference_path(str(dep))
                except Exception:
                    p = ""
                if p and os.path.isfile(p) and os.access(p, os.R_OK):
                    candidates.append(p)
        # 兜底：若主脚本与 source.path 不同，也补扫原始 source.path
        try:
            raw_path = os.path.realpath(os.path.abspath(str(source.get("path", ""))))
        except Exception:
            raw_path = ""
        if raw_path and raw_path not in candidates and os.path.isfile(raw_path):
            candidates.append(raw_path)

        seen = set()
        for path_item in candidates:
            if not path_item:
                continue
            try:
                path_item = os.path.realpath(os.path.abspath(str(path_item)))
            except Exception:
                continue
            if not os.path.isfile(path_item) or not os.access(path_item, os.R_OK):
                continue
            if path_item in seen:
                continue
            seen.add(path_item)
            scanned_paths.append(path_item)
            try:
                text = self._read_text(path_item, 4 * 1024 * 1024)
            except Exception:
                continue
            if not text:
                continue
            low = text
            for pattern, signature in self.EXIT_RISK_PATTERNS:
                try:
                    if pattern.search(low):
                        label = "{}@{}".format(signature, os.path.basename(path_item))
                        if label not in hit_signatures:
                            hit_signatures.append(label)
                except Exception:
                    continue
            # 命中后不必继续扫其余文件，尽早返回
            if hit_signatures:
                break
        return hit_signatures[:4]

    def _test_result(
        self, state, detail, checked_at, origin="", failure_kind="",
        test_stage="",
    ):
        result = {
            "state": state,
            "detail": str(detail or "")[:240],
            "checked_at": checked_at,
            "checked_ts": time.time(),
        }
        if origin:
            result["origin"] = origin
        if failure_kind:
            result["failure_kind"] = str(failure_kind)
        if test_stage:
            result["test_stage"] = str(test_stage)
        return result

    def _static_entry_fallback(self, source, checked_at, reason):
        """Spider 初始化失败时，用静态入口检查决定是失效还是受限。

        初始化失败的原因未必是脚本坏了：本机服务端口未就绪、QuickJS
        运行时异常、宿主正在重载配置都会导致同样的结果。若文件本身
        含合法入口（QuickJS/CommonJS 导出或 drpy 规则），判为受限并
        保留在列表中，避免把可用站点从 App 删掉。
        """
        source_type = str(source.get("type", "")).upper()
        detector = {
            "JS": lambda text: (
                self._has_direct_js_spider(text) or self._has_drpy_rule(text)
            ),
            "PY": lambda text: bool(
                re.search(r"^\s*class\s+Spider\b", text, flags=re.MULTILINE)
            ),
        }.get(source_type)

        if detector is not None:
            try:
                text = self._read_text(self._source_probe_path(source), 512 * 1024)
            except Exception:
                text = ""
            if text and detector(text):
                return self._test_result(
                    "limited",
                    "{}；文件含合法 {} 入口，按受限保留".format(reason, source_type),
                    checked_at,
                    test_stage="functional",
                )

        return self._test_result(
            "unavailable",
            reason,
            checked_at,
            failure_kind="functional",
            test_stage="functional",
        )

    def _append_site_test_history(self, identity, result):
        identity = str(identity or "").strip()
        if not identity or not isinstance(result, dict):
            return
        entry = {}
        for key in (
            "state",
            "checked_at",
            "checked_ts",
            "test_stage",
            "playback_state",
            "elapsed_ms",
            "detail",
            "failure_kind",
            "confirmed",
        ):
            value = result.get(key)
            if value not in (None, ""):
                entry[key] = value
        media = result.get("media")
        if isinstance(media, dict):
            entry["media"] = {
                key: media[key]
                for key in (
                    "host",
                    "status",
                    "content_type",
                    "sample_bytes",
                    "format",
                )
                if key in media
            }
        history = list(self.site_test_history.get(identity, []))
        history.append(entry)
        self.site_test_history[identity] = history[-self.SITE_TEST_HISTORY_LIMIT :]

    def _site_test_history_text(self, identity, limit=5):
        history = self.site_test_history.get(str(identity or "").strip(), [])
        if not isinstance(history, list) or not history:
            return "无"
        lines = []
        for item in history[-max(1, int(limit)) :]:
            if not isinstance(item, dict):
                continue
            elapsed = item.get("elapsed_ms")
            elapsed_text = "{} ms".format(elapsed) if elapsed not in (None, "") else "-"
            lines.append(
                "- {} · {} · {} · {} · {} · {}".format(
                    item.get("checked_at", "-"),
                    self._test_result_label(item),
                    item.get("test_stage", "-") or "-",
                    item.get("playback_state", "-") or "-",
                    elapsed_text,
                    str(item.get("detail", "") or "")[:120],
                )
            )
        return "\n".join(lines) or "无"

    def _finalize_test_result(self, source, result):
        state = str(result.get("state", ""))
        if state != "unavailable":
            result["failure_count"] = 0
            result["confirmed"] = False
            return result

        identity = source.get("identity", "")
        previous = self.site_test_results.get(identity, {})
        # 只按 failure_count 累计：任何一次非失效判定都会把它清零，
        # 因此首次失效被降级为 limited 后，计数仍然保留，下一次失效才确认。
        previous_count = int(previous.get("failure_count", 0) or 0)
        result["failure_count"] = previous_count + 1 if previous_count > 0 else 1

        if result["failure_count"] >= self.SITE_TEST_FAILURE_CONFIRM_COUNT:
            result["confirmed"] = True
            suffix = "已连续 {} 次失效，将从 App 站点列表移除".format(result["failure_count"])
        else:
            result["confirmed"] = False
            result["state"] = "limited"
            suffix = "首次检测失效，保留在列表中待下次验证"

        result["detail"] = "{}；{}".format(
            str(result.get("detail", ""))[:180], suffix
        )[:240]
        return result

    def _extract_probe_url(self, path):
        text = self._read_text(path, 512 * 1024)
        text = text.replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")
        matches = re.findall(r"https?://[^\s\"'<>\\]+", text, flags=re.IGNORECASE)
        scored = []
        for index, value in enumerate(matches):
            value = value.rstrip("),;]}，。")
            parsed = urllib.parse.urlsplit(value)
            if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
                continue
            host = (parsed.hostname or "").lower()
            if host in ("127.0.0.1", "localhost") or host.endswith(".local"):
                continue
            lower = value.lower()
            score = -index
            if parsed.path in ("", "/"):
                score += 20
            if re.search(r"\.(?:jpg|jpeg|png|gif|webp|svg|m3u8|mp4|css|woff2?)(?:\?|$)", lower):
                score -= 50
            if host in ("example.com", "www.example.com"):
                score -= 100
            scored.append((score, value))
        return max(scored, default=(0, ""), key=lambda item: item[0])[1]

    def _url_origin(self, url):
        try:
            parsed = urllib.parse.urlsplit(url)
            if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
                return ""
            return "{}://{}/".format(parsed.scheme.lower(), parsed.netloc)
        except Exception:
            return ""

    def _probe_site_url(self, url):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Android; TVBox Site Check)",
                "Accept": "text/html,application/json;q=0.9,*/*;q=0.5",
                "Range": "bytes=0-1023",
                "Connection": "close",
            },
        )
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler(), NoRedirectHandler()
        )
        try:
            with opener.open(request, timeout=self.SITE_TEST_TIMEOUT) as response:
                status = int(getattr(response, "status", response.getcode()))
                response.read(1024)
            if 200 <= status < 400:
                return "available", "站点地址可达 (HTTP {})".format(status)
            return "limited", "站点响应受限 (HTTP {})".format(status)
        except urllib.error.HTTPError as exc:
            if 300 <= int(exc.code) < 400:
                return "available", "站点地址可达并返回跳转 (HTTP {})".format(
                    exc.code
                )
            return "limited", "站点响应受限 (HTTP {})".format(exc.code)
        except urllib.error.URLError as exc:
            reason = exc.reason
            text = str(reason).lower()
            if isinstance(reason, socket.timeout) or "timed out" in text or "timeout" in text:
                return "limited", "主页连接超时"
            if isinstance(reason, (socket.gaierror, ConnectionRefusedError)) or any(
                marker in text
                for marker in (
                    "connection refused",
                    "name or service not known",
                    "nodename nor servname",
                    "no address associated",
                )
            ):
                return "limited", "站点网络不可达: {}".format(reason)
            return "limited", "站点连接受限: {}".format(reason)
        except (socket.timeout, TimeoutError):
            return "limited", "主页连接超时"
        except ConnectionRefusedError as exc:
            return "limited", "站点连接被拒绝: {}".format(exc)
        except Exception as exc:
            return "limited", "主页检测受限: {}".format(exc)

    def _test_result_label(self, result):
        if not isinstance(result, dict):
            return "未检测"
        return {
            "available": "可用",
            "unavailable": "失效",
            "limited": "受限",
        }.get(str(result.get("state", "")), "未检测")

    def _normalize_extension(self, value):
        value = str(value or "").strip().lower()
        if not value:
            return ""
        return value if value.startswith(".") else "." + value

    # --------------------------------------------------------------------------
    # 本地包下载与安全安装
    # --------------------------------------------------------------------------
    def _package_download_running(self):
        with self._package_download_lock:
            worker = self._package_download_thread
            return worker is not None and worker.is_alive()

    def _package_root(self):
        # 包安装/下载目标根：优先取 CSP 类型扫描根（csp 目录），回退到 csp 子目录。
        for item in self.scan_roots:
            if str(item.get("type", "")).upper() != "CSP":
                continue
            path = str(item.get("path", "")).strip()
            if path:
                return os.path.realpath(os.path.abspath(os.path.expanduser(path)))
        return os.path.realpath(
            os.path.abspath(_detect_child_dir(self.local_base_dir, "csp"))
        )

    def _encoded_download_url(self, value):
        url = self._normalize_package_download_url(value)
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname or ""
        try:
            encoded_host = (
                host if host.isascii() else host.encode("idna").decode("ascii")
            )
        except Exception as exc:
            raise ValueError("下载地址域名转换失败: {}".format(exc))
        if ":" in encoded_host and not encoded_host.startswith("["):
            encoded_host = "[{}]".format(encoded_host)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("下载地址端口无效: {}".format(exc))
        netloc = encoded_host + (":{}".format(port) if port is not None else "")
        if parsed.username is not None:
            user_info = urllib.parse.quote(parsed.username, safe="")
            if parsed.password is not None:
                user_info += ":" + urllib.parse.quote(parsed.password, safe="")
            netloc = user_info + "@" + netloc
        path = urllib.parse.quote(urllib.parse.unquote(parsed.path), safe="/%:@")
        # 保留 url=SOURCE_URL 的现有百分号编码，避免源接口自身的 & 被拆成 CF 参数。
        query = urllib.parse.quote(parsed.query, safe="=&%:@/?+")
        return urllib.parse.urlunsplit(
            (parsed.scheme, netloc, path, query, parsed.fragment)
        )

    def _package_name_from_url(self, value):
        parsed = urllib.parse.urlsplit(value)
        name = urllib.parse.unquote(os.path.basename(parsed.path)).strip()
        if name.lower().endswith(".zip"):
            name = name[:-4]
        name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", name)
        name = re.sub(r"\s+", " ", name).strip(" ._")
        return (name or "本地包")[:80]

    def _package_name_from_label(self, value):
        return self._normalize_package_download_name(value)

    def _package_download_directory(self):
        path = os.path.expanduser(str(self.package_download_dir or "").strip())
        if not os.path.isabs(path):
            path = os.path.join(self.STORAGE_ROOT, path.lstrip("/"))
        return os.path.realpath(os.path.abspath(path))

    def _package_install_target(self, url=None, site_name=None):
        if site_name is not None:
            return os.path.join(
                self._package_root(), self._package_name_from_label(site_name)
            )
        package_name = self._package_name_from_url(
            url if url is not None else self.package_download_url
        )
        return os.path.join(
            self._package_root(), "自动下载-{}".format(package_name)
        )

    def _package_install_marker(self, target):
        return os.path.join(target, self.PACKAGE_INSTALL_MARKER)

    def _read_package_install_marker(self, target):
        path = self._package_install_marker(target)
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write_package_install_marker(self, target, data):
        path = self._package_install_marker(target)
        temp_path = path + ".tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False, indent=2)
                fp.write("\n")
                fp.flush()
                os.fsync(fp.fileno())
            os.replace(temp_path, path)
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass

    def _rename_package_install_directory(self, site_id, old_name, new_name):
        old_target = self._package_install_target(site_name=old_name)
        new_target = self._package_install_target(site_name=new_name)
        if os.path.realpath(old_target) == os.path.realpath(new_target):
            return None
        if not os.path.isdir(old_target):
            return None
        marker = self._read_package_install_marker(old_target)
        if str(marker.get("id", "")).strip() != str(site_id or "").strip():
            return None
        if os.path.exists(new_target):
            raise ValueError(
                "新备注名“{}”对应文件夹已存在，请更换备注名".format(new_name)
            )
        os.replace(old_target, new_target)
        marker["name"] = new_name
        try:
            self._write_package_install_marker(new_target, marker)
        except Exception:
            os.replace(new_target, old_target)
            raise
        return {
            "old": old_target,
            "new": new_target,
            "marker": marker,
            "old_name": old_name,
        }

    def _migrate_builtin_package_install_directory(self):
        for item in self.package_download_sites:
            if str(item.get("source_type", "")).lower() != "builtin":
                continue
            try:
                old_target = self._package_install_target(site_name="CF本地包")
                new_target = self._package_install_target(
                    site_name=self.PACKAGE_DOWNLOAD_NAME
                )
                site_id = str(item.get("id", "cf-service")).strip()
                old_marker = self._read_package_install_marker(old_target)
                new_marker = self._read_package_install_marker(new_target)
                if (
                    os.path.isdir(old_target)
                    and os.path.isdir(new_target)
                    and str(old_marker.get("id", "")).strip() == site_id
                    and str(new_marker.get("id", "")).strip() == site_id
                ):
                    shutil.rmtree(old_target)
                    return
                self._rename_package_install_directory(
                    site_id,
                    "CF本地包",
                    self.PACKAGE_DOWNLOAD_NAME,
                )
            except Exception as exc:
                self._warn("默认包目录迁移失败: {}".format(exc))
            return


    def _is_package_download_action(self, action):
        value = str(action or "")
        return value == self.ACTION_DOWNLOAD_PACKAGE or value.startswith(
            self.ACTION_DOWNLOAD_PACKAGE_PREFIX
        )

    # --------------------------------------------------------------------------
    # 在线仓库
    # --------------------------------------------------------------------------
    def _repository_sync_running(self):
        with self._repository_sync_lock:
            worker = self._repository_sync_thread
            return worker is not None and worker.is_alive()

    def _is_repository_sync_action(self, action):
        return str(action or "") == self.ACTION_SYNC_REPOSITORIES

    def _repository_marker_path(self, target):
        return os.path.join(target, self.ONLINE_REPOSITORY_MARKER)

    def _read_repository_marker(self, target):
        path = self._repository_marker_path(target)
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as fp:
                value = json.load(fp)
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}





    # --------------------------------------------------------------------------
    # 扫描与配置生成
    # --------------------------------------------------------------------------
    def _ensure_initialized(self):
        if self.inited:
            return
        self.init("")

    def _manual_scan_state_key(self):
        return os.path.realpath(
            os.path.abspath(os.path.expanduser(self.output_path))
        )

    def _begin_manual_scan_request(self):
        key = self._manual_scan_state_key()
        now = time.monotonic()
        with _MANUAL_SCAN_LOCK:
            state = _MANUAL_SCAN_STATE.setdefault(
                key, {"running": False, "last": 0.0}
            )
            if state["running"]:
                return False, "扫描请求已合并：当前扫描正在进行"
            elapsed = now - float(state.get("last", 0.0) or 0.0)
            if elapsed < max(0.5, float(self.MANUAL_SCAN_DEDUP_WINDOW)):
                return False, "已忽略重复触发：本次扫描刚刚完成"
            state["running"] = True
            state["started"] = now
        return True, ""

    def _finish_manual_scan_request(self):
        key = self._manual_scan_state_key()
        with _MANUAL_SCAN_LOCK:
            state = _MANUAL_SCAN_STATE.setdefault(
                key, {"running": False, "last": 0.0}
            )
            state["running"] = False
            state["last"] = time.monotonic()

    def _refresh_locked(self, allow_empty=False, progress=None):
        self.status = self._empty_status()
        self.status["scan_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        enabled_roots = [
            "{}={}".format(item.get("type", "?"), item.get("path", ""))
            for item in self.scan_roots
            if self.type_enabled.get(str(item.get("type", "")).upper(), True)
        ]
        self._log(
            "INFO",
            "开始扫描: allow_empty={} roots={}".format(
                bool(self.allow_empty_write or allow_empty),
                "; ".join(enabled_roots) or "无已开启目录",
            ),
        )
        try:
            self._scan_all_roots(progress=progress)
            if self.status["limit_reached"]:
                self.status["write_state"] = "扫描达到保护上限，已保护旧注册表"
                self.status["error"] = "请缩小扫描目录或调整 max_files"
                self._log("WARN", self.status["error"])
                return False
            if (
                not self.cache["sources"]
                and not self.cache["ignored"]
                and not self.cache.get("lives")
                and not (self.allow_empty_write or allow_empty)
                and not self._package_filter_excluded
                and not self.status["compatibility_blocked"]
            ):
                self.status["write_state"] = "未找到有效源，已保护旧配置"
                self.status["error"] = "扫描结果为空，未改写站点注入注册表"
                self._log("WARN", self.status["error"])
                return False
            if (
                not self.cache["sources"]
                and not self.cache.get("lives")
                and self.status["compatibility_blocked"]
            ):
                self._warn(
                    "检测到会导致当前 App 退出或接口不兼容的 JAR，"
                    "已清除对应旧注入站点"
                )
            self._generate_config()
            completed = self.status["written"] or self.status["write_state"] == "配置内容未变化"
            if completed:
                try:
                    self._save_scan_snapshot()
                except Exception as exc:
                    self._warn("扫描列表快照保存失败: {}".format(exc))
                if self.auto_scan_suspended:
                    self.auto_scan_suspended = False
                    try:
                        self._save_settings()
                    except Exception as exc:
                        self._warn("自动补扫状态保存失败: {}".format(exc))
            self._log(
                "INFO",
                "扫描完成: 发现={} 有效={} 直播={} 播放上下文={} 忽略={} 跳过={} 重复={} 状态={}".format(
                    self.status["found"],
                    self.status["included"],
                    self.status["generated_lives"],
                    len(self.cache.get("contexts", [])),
                    self.status["ignored"],
                    self.status["skipped"],
                    self.status["duplicates"],
                    self.status["write_state"],
                ),
            )
            return completed
        except Exception as exc:
            self.status["error"] = str(exc)
            self.status["write_state"] = "合并失败"
            self._log("ERROR", "扫描合并失败: {}".format(exc))
            return False

    # ==================================================================
    # v7.0：扫描 / 加载分离、选择集与临时加载
    # ==================================================================
    def _effective_selected_identities(self):
        """当前实际生效的加载集合 = 永久选择 ∪ 临时选择。"""
        permanent = self.selected_identities
        if not isinstance(permanent, set):
            permanent = set()
        return set(permanent) | set(self.temp_identities)

    def _source_load_state(self, source):
        """返回单个扫描结果当前的加载状态：perm / temp / none。"""
        identity = str(source.get("identity", ""))
        # 默壳版：perm 状态 = 永久注入集合（单文件注入）∪ 配置选择集（全部加载）。
        permanent = self.selected_identities
        if isinstance(permanent, set) and identity in permanent:
            return "perm"
        if identity in self.perm_injected_identities:
            return "perm"
        if identity in self.temp_identities:
            return "temp"
        return "none"

    def _selected_source_paths(self, identities):
        """把 identity 集合映射为对应源文件绝对路径集合（供直播/上下文归属判断）。"""
        targets = {str(value) for value in (identities or set())}
        paths = set()
        for source in self.cache.get("sources", []):
            if str(source.get("identity", "")) not in targets:
                continue
            path = str(source.get("path", "")).strip()
            if path:
                paths.add(os.path.normcase(os.path.abspath(path)))
        return paths

    def _ensure_selection_initialized_locked(self):
        """v6 -> v7 选择集一次性迁移。

        首次扫描后执行：旧 registry 已存在自动站点则默认全选（保留 v6
        “扫描即全部加载”的结果），否则为空集（v7 新用户需显式加载）。
        """
        if self.selection_initialized:
            return
        try:
            registry = self._load_registry()
            items = registry.get("items", []) if isinstance(registry, dict) else []
            has_generated = any(
                isinstance(item, dict) and self._is_generated_registry_item(item)
                for item in items
            )
        except Exception:
            has_generated = False
        if has_generated:
            self.selected_identities = {
                str(source.get("identity", ""))
                for source in self.cache.get("sources", [])
                if source.get("identity")
            }
        else:
            self.selected_identities = set()
        self.selection_initialized = True
        try:
            self._save_settings()
        except Exception as exc:
            self._warn("加载选择初始化保存失败: {}".format(exc))

    def _scan_only_locked(self, sync_network=False, progress=None):
        """仅扫描设定目录并填充浏览缓存，不写任何配置、不触发重载。"""
        self.status = self._empty_status()
        self.status["scan_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        enabled_roots = [
            "{}={}".format(item.get("type", "?"), item.get("path", ""))
            for item in self.scan_roots
            if self.type_enabled.get(str(item.get("type", "")).upper(), True)
        ]
        self._log(
            "INFO",
            "开始仅扫描(不写盘): roots={}".format(
                "; ".join(enabled_roots) or "无已开启目录"
            ),
        )
        try:
            self._scan_all_roots(
                sync_network=sync_network, progress=progress
            )
            if self.status["limit_reached"]:
                self.status["write_state"] = "扫描达到保护上限，请缩小目录后重试"
                self.status["error"] = "请缩小扫描目录或调整 max_files"
                self._log("WARN", self.status["error"])
                return False
            self._ensure_selection_initialized_locked()
            self.scan_only_done = True
            found = len(self.cache["sources"])
            lives = len(self.cache.get("lives", []))
            if found or lives:
                state = "扫描完成：{} 个站点 / {} 个直播可加载（未改动站点配置）".format(
                    found, lives
                )
            elif self.cache["ignored"]:
                state = "扫描完成：站点全部处于屏蔽状态，可在屏蔽分类恢复"
            else:
                state = "扫描完成：未发现可加载站点（未改动站点配置）"
            self.status["write_state"] = state
            self.status["error"] = ""
            # 扫描结果落盘：否则仅存实例内存，退出 App 重进/刷新接口
            # （新 spider 实例）后扫描结果丢失，需要重新扫描。
            try:
                self._save_scan_snapshot()
            except Exception as exc:
                self._warn("扫描列表快照保存失败: {}".format(exc))
            self._log(
                "INFO",
                "仅扫描完成: 站点={} 直播={} 忽略={}".format(
                    found, lives, self.status["ignored"]
                ),
            )
            return True
        except Exception as exc:
            self.status["error"] = str(exc)
            self.status["write_state"] = "扫描失败"
            self._log("ERROR", "仅扫描失败: {}".format(exc))
            return False

    def _apply_selection_and_write_locked(self, subset, save_snapshot=True):
        """按选择集生成配置并热重载。subset=None 表示全部加载。"""
        if subset is None:
            self._load_filter = None
        else:
            self._load_filter = {str(value) for value in subset}
        reload_detail = ""
        try:
            self._generate_config()
            completed = (
                self.status["written"]
                or self.status["write_state"] == "配置内容未变化"
            )
            if completed:
                if save_snapshot:
                    try:
                        self._save_scan_snapshot()
                    except Exception as exc:
                        self._warn("扫描列表快照保存失败: {}".format(exc))
                _, reload_detail = self._reload_app_vod_config(
                    expected_keys=self._selected_registry_keys()
                )
            return completed, reload_detail
        finally:
            self._load_filter = None

    def _load_all_locked(self):
        if not self.cache.get("sources") and not self.cache.get("lives"):
            return False, "还没有扫描结果，请先点击「扫描」"
        self._ensure_selection_initialized_locked()
        self.selected_identities = {
            str(source.get("identity", ""))
            for source in self.cache.get("sources", [])
            if source.get("identity")
        }
        # 加载全部按永久处理（保持 v6 语义），临时项随之转正。
        self.temp_identities = set()
        self._temp_home_key = ""
        # 默壳版：全部加载时清空永久注入记录——所有站点都通过配置选择集
        # 加载到"智能点播"接口，不再需要单独的注入记录。
        self.perm_injected_identities = set()
        self.selection_initialized = True
        try:
            self._save_settings()
        except Exception as exc:
            self._warn("永久加载选择保存失败: {}".format(exc))
        completed, _detail = self._apply_selection_and_write_locked(None, True)
        if completed:
            self.scan_only_done = False
        return completed, _detail

    def _load_single_file_locked(self, source_id, temporary):
        source = self.cache.get("source_index", {}).get(source_id)
        if not source:
            return False, "文件不在扫描结果中，请重新扫描"
        identity = str(source.get("identity", ""))
        if not identity:
            return False, "文件标识缺失，请重新扫描"
        name = str(source.get("name") or source.get("base_name") or identity)
        if temporary:
            # v7.0：仅 PY 文件支持临时加载（FloatSpider 内存注入方案）。
            source_type = str(source.get("type", "")).upper()
            if source_type != "PY":
                return False, "「{}」是 {} 类型，仅支持永久加载".format(
                    name, self.TYPE_LABEL.get(source_type, source_type or "未知")
                )
            # 永久态有两种来源，转换时都必须清理：
            # · selected：全部加载/配置选择集（写标准点播配置）
            # · injected：单文件永久加载（写注册表 + perm_injected 记录）
            was_perm_selected = (
                isinstance(self.selected_identities, set)
                and identity in self.selected_identities
            )
            was_perm_injected = identity in self.perm_injected_identities
            if was_perm_injected:
                # 单文件永久加载（注册表来源）转为临时：与"已加载站点-
                # 全部改为临时"完全相同的路径——只改加载方式：删注册表
                # 永久项、内存覆盖注入（set_home=False），不重新生成配置、
                # 不触发 App 重载。重载会重建站点表并把首页切到聚合接口
                # "智能点播"（即用户看到的"自动切换接口"）。
                self.perm_injected_identities.discard(identity)
                self._remove_site_from_registry(source)
                if was_perm_selected:
                    self.selected_identities.discard(identity)
                self.temp_identities.add(identity)
                try:
                    self._save_settings()
                except Exception as exc:
                    self._warn("加载状态保存失败: {}".format(exc))
                try:
                    self._inject_site_into_app(source, set_home=False)
                except Exception:
                    pass
                self._schedule_manager_page_refresh(delay=0.2)
                return True, "「{}」已改为临时加载，退出 App 后自动消失".format(name)
            if was_perm_selected:
                # 配置选择集来源（"全部加载"的聚合"智能点播"接口）：
                # 单站无法从聚合接口剥离，只能重生成配置并重载。
                # 第一步（此处）：从配置选择集移除并写盘，触发 App 异步
                # 重建站点表。第二步（看门）：确认重建落地后执行与"文件
                # 浏览-临时加载"完全相同的纯内存注入。此处若同步注入，
                # 注入结果会被随后落地的重建冲掉（实测站点出现后又消失）。
                self.selected_identities.discard(identity)
                try:
                    self._save_settings()
                except Exception as exc:
                    self._warn("加载选择保存失败: {}".format(exc))
                subset = set(self.selected_identities)
                completed, _detail = self._apply_selection_and_write_locked(
                    subset, save_snapshot=True
                )
                if not completed:
                    self.selected_identities.add(identity)
                    try:
                        self._save_settings()
                    except Exception:
                        pass
                    return False, "「{}」转为临时失败：{}".format(
                        name,
                        self.status.get("error")
                        or self.status.get("write_state")
                        or "未知错误",
                    )
                self.temp_identities.add(identity)
                # 只改变加载方式，不抢占当前接口：不设置 _temp_home_key，
                # 看门补注时该站 set_home=False（与"已加载站点-全部改为
                # 临时"的行为保持一致）。
                # 临时状态落盘：App 重建会销毁本实例，新实例靠它恢复。
                try:
                    self._save_settings()
                except Exception as exc:
                    self._warn("临时加载状态保存失败: {}".format(exc))
                return True, "「{}」已改为临时加载，退出 App 后自动消失".format(name)
            # 文件浏览-临时加载：纯内存注入，不写配置、不触发重建。
            ok, detail = self._inject_site_into_app(source)
            if not ok:
                return False, "临时加载失败：{}".format(detail or "未知错误")
            self.temp_identities.add(identity)
            # 临时状态落盘：App 重建会销毁本实例，新实例靠它恢复。
            try:
                self._save_settings()
            except Exception as exc:
                self._warn("临时加载状态保存失败: {}".format(exc))
            return True, "「{}」已临时加载，退出 App 后自动消失".format(name)
        # ===== 默壳版：单文件永久加载改为写入注册表方式 =====
        # 参考 webhtv 站点注入：把站点写入 registry.json 的 items 中，
        # 触发 App 重载后站点会出现在站点列表弹窗中，与普通站点混排。
        # 不再生成"智能点播"接口，也不反射注入运行态。
        self._ensure_selection_initialized_locked()
        # 若该文件此前以临时方式注入运行态，先移除避免重复。
        site = source.get("site") if isinstance(source.get("site"), dict) else {}
        runtime_key = str(site.get("key", "")).strip() or str(
            source.get("key", "")
        ).strip()
        if runtime_key:
            if self._temp_home_key == runtime_key:
                self._temp_home_key = ""
            try:
                self._remove_site_from_app(runtime_key)
            except Exception:
                pass
        self.temp_identities.discard(identity)
        # 写入注册表（作为生成项，但不走全部加载的配置生成流程）
        ok, detail = self._inject_site_to_registry(source)
        if not ok:
            return False, "永久加载失败：{}".format(detail or "未知错误")
        # 持久化永久注入记录
        self.perm_injected_identities.add(identity)
        # 同时从配置选择集中移除（避免与全部加载的配置写入重复）
        if isinstance(self.selected_identities, set):
            self.selected_identities.discard(identity)
        try:
            self._save_settings()
        except Exception as exc:
            self._warn("永久加载状态保存失败: {}".format(exc))
        # 默壳版：不做全量重载（避免重建站点表导致 home 回退）。
        # 注册表已写入，站点会在用户切换站点时自动生效。
        self._schedule_manager_page_refresh(delay=0.2)
        return True, "「{}」已永久加载，切换站点后生效".format(name)

    def _inject_site_to_registry(self, source):
        """把单个站点写入注册表（webhtv 站点注入方式）。

        将站点配置追加到 registry.json 的 items 中，App 重载后自动合并
        到主站点列表。站点作为生成项写入，但不受全部加载的选择集控制。
        """
        try:
            registry, token = self._load_registry_snapshot()
            items = registry.get("items", [])
            if not isinstance(items, list):
                items = []
            # 检查是否已存在（按 key 去重）
            site_dict = self._build_site(source)
            site_key = str(site_dict.get("key", "")).strip()
            existing_idx = -1
            for i, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                item_site = item.get("site", {})
                if isinstance(item_site, dict) and str(item_site.get("key", "")) == site_key:
                    existing_idx = i
                    break
            # 构建注册表项（生成项格式）
            generated_item = {
                "id": source.get("key", ""),
                "enabled": True,
                "kind": self._registry_kind(source),
                "sourceType": source.get("type", ""),
                "packageId": str(source.get("package_id", "")),
                "site": site_dict,
                "temporary": False,  # 永久注入，不是临时项
            }
            if existing_idx >= 0:
                items[existing_idx] = generated_item
            else:
                items.append(generated_item)
            registry["items"] = items
            self._atomic_write_json(registry, expected_token=token)
            # 注册表已变更，更新快照 token 避免下次启动时快照校验失败
            try:
                self._save_scan_snapshot()
            except Exception as exc:
                self._warn("更新扫描快照失败: {}".format(exc))
            return True, ""
        except Exception as exc:
            self._log("ERROR", "写入注册表失败: {}".format(exc))
            return False, str(exc)

    def _remove_site_from_registry(self, source):
        """从注册表移除单个站点。"""
        try:
            registry, token = self._load_registry_snapshot()
            items = registry.get("items", [])
            if not isinstance(items, list):
                return False
            site_key = str(source.get("key", "")).strip()
            new_items = []
            removed = False
            for item in items:
                if not isinstance(item, dict):
                    new_items.append(item)
                    continue
                item_site = item.get("site", {})
                if isinstance(item_site, dict) and str(item_site.get("key", "")) == site_key:
                    removed = True
                    continue
                new_items.append(item)
            if removed:
                registry["items"] = new_items
                self._atomic_write_json(registry, expected_token=token)
                # 注册表已变更，更新快照 token
                try:
                    self._save_scan_snapshot()
                except Exception as exc:
                    self._warn("更新扫描快照失败: {}".format(exc))
            return removed
        except Exception as exc:
            self._log("ERROR", "从注册表移除站点失败: {}".format(exc))
            return False

    def _restore_perm_injected_sites(self):
        """App 启动时，确保永久注入站点已写入注册表。

        永久注入站点在加载时已写入注册表，App 启动时会自动从注册表
        合并到主站点列表。此方法只做兜底校验：若注册表中缺失则补写。
        """
        if not self.perm_injected_identities:
            return
        index = self.cache.get("source_index", {})
        need_reload = False
        for source in self.cache.get("sources", []):
            identity = str(source.get("identity", ""))
            if identity not in self.perm_injected_identities:
                continue
            if index and source.get("id") not in index:
                continue
            # 检查注册表中是否已有该站点
            site_key = str(source.get("key", "")).strip()
            if not site_key:
                continue
            try:
                registry, _ = self._load_registry_snapshot()
                items = registry.get("items", [])
                found = False
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item_site = item.get("site", {})
                    if isinstance(item_site, dict) and str(item_site.get("key", "")) == site_key:
                        found = True
                        break
                if not found:
                    self._inject_site_to_registry(source)
                    need_reload = True
            except Exception:
                pass
        if need_reload:
            self._schedule_manager_page_refresh(delay=0.2)

    def _reinject_temp_sites_locked(self, exclude=None, restore_home=False):
        """永久写入触发 App 重载后，把仍为临时状态的站点重新注入运行态。

        restore_home=True 时使用本进程记录的临时 home key 恢复选中。
        不能读 App 侧持久化 home：重建时 App 找不到临时站会把 home
        回退到首站并覆盖持久化值，读到的已是被污染的结果。
        """
        if not self.temp_identities:
            return
        preferred_key = ""
        if restore_home:
            preferred_key = str(getattr(self, "_temp_home_key", "") or "")
        index = self.cache.get("source_index", {})
        restored_home = False
        for source in self.cache.get("sources", []):
            identity = str(source.get("identity", ""))
            if identity == exclude or identity not in self.temp_identities:
                continue
            if index and source.get("id") not in index:
                continue
            set_home = False
            if restore_home and preferred_key and not restored_home:
                site = (
                    source.get("site")
                    if isinstance(source.get("site"), dict)
                    else {}
                )
                runtime_key = str(site.get("key", "")).strip() or str(
                    source.get("key", "")
                ).strip()
                set_home = runtime_key == preferred_key
            try:
                ok, _detail = self._inject_site_into_app(
                    source, set_home=set_home
                )
                if ok and set_home:
                    restored_home = True
            except Exception:
                pass

    def _watch_reinject_temp_sites(
        self, generation, wait_rounds=15, hold_needed=3, interval=0.6,
        max_rounds=12,
    ):
        """App 重载重建站点表后补注临时站点，并确认稳定留存。

        重载校验对“移除型”变更（永久转临时/移出/清除）可能提前通过：
        旧运行态本就包含期望键集，校验在 App 异步重建落地前就结束了。
        因此看门分两阶段：先等运行态站点表真的被重建（临时站被冲掉），
        再补注并连续复查，连续 hold_needed 次无缺失才判定稳定。
        “永久转临时”的首次注入也由本看门完成（转换路径只做配置移除，
        不同步注入，避免注入被随后落地的重建冲掉）。
        """
        try:
            # 阶段一：等待重建落地。超时也继续补注——探测失败与重建未发生
            # 无法区分，而补注本身幂等无害。
            wiped = False
            for _ in range(max(1, int(wait_rounds))):
                if self._watch_aborted(generation):
                    return
                if self._temp_runtime_missing_keys():
                    wiped = True
                    break
                time.sleep(max(0.2, float(interval)))
            if wiped:
                self._log(
                    "INFO", "看门：已观察到运行态站点表重建，开始补注临时站点"
                )
            # 阶段二：补注并连续复查，稳定留存后才结束。
            stable = 0
            restore_home = True
            for _ in range(max(int(hold_needed), int(max_rounds))):
                if self._watch_aborted(generation):
                    return
                with self.lock:
                    if generation != self._reload_generation:
                        return
                    self._reinject_temp_sites_locked(restore_home=restore_home)
                restore_home = False
                time.sleep(max(0.2, float(interval)))
                if self._temp_runtime_missing_keys():
                    stable = 0
                    # 再次被重建冲掉时首页也被回退污染，下轮补注一并恢复。
                    restore_home = True
                    self._log("WARN", "看门：补注后临时站点仍被冲掉，继续补注")
                    continue
                stable += 1
                if stable >= int(hold_needed):
                    self._log("INFO", "看门：临时站点已稳定留存")
                    return
            self._warn("看门：补注未能在限定轮次内稳定，临时站点可能消失")
        except Exception as exc:
            self._warn("临时站点补注失败: {}".format(exc))

    def _watch_aborted(self, generation):
        """看门中止条件：无临时站、或已有更新一轮重载接管。

        不检查 _destroyed：看门的补注工作恰发生在 App 重建期间，
        而重建会销毁本 spider 实例（destroy 被 App 调用），但看门
        线程仍持有实例引用，补注通过反射操作全局 VodConfig，与实例
        存活状态无关；进程真退出时守护线程随之结束。
        """
        if not self.temp_identities:
            return True
        with self.lock:
            return generation != self._reload_generation

    def _temp_runtime_missing_keys(self):
        """运行态站点表中缺失的临时站点 key 集合；无法探测时返回空集。"""
        with self.lock:
            if not self.temp_identities:
                return set()
            expected_keys = set()
            index = self.cache.get("source_index", {})
            for source in self.cache.get("sources", []):
                identity = str(source.get("identity", ""))
                if identity not in self.temp_identities:
                    continue
                if index and source.get("id") not in index:
                    continue
                site = (
                    source.get("site")
                    if isinstance(source.get("site"), dict)
                    else {}
                )
                key = str(site.get("key", "")).strip() or str(
                    source.get("key", "")
                ).strip()
                if key:
                    expected_keys.add(key)
        if not expected_keys:
            return set()
        try:
            vod_config = self._runtime_vod_config()
            if vod_config is None:
                return set()
            sites = vod_config.getSites()
            actual = set()
            for i in range(sites.size()):
                actual.add(str(sites.get(i).getKey()))
            return expected_keys - actual
        except Exception:
            return set()

    def _unload_file_locked(self, source_id):
        source = self.cache.get("source_index", {}).get(source_id)
        if not source:
            return False, "文件不在扫描结果中，请重新扫描"
        identity = str(source.get("identity", ""))
        name = str(source.get("name") or source.get("base_name") or identity)
        state = self._source_load_state(source)
        if state == "none":
            return True, "「{}」当前未加载".format(name)
        # 临时项只存在于运行态内存，直接从 VodConfig 移除即可，无需写盘。
        if state == "temp":
            self.temp_identities.discard(identity)
            site = source.get("site") if isinstance(source.get("site"), dict) else {}
            runtime_key = str(site.get("key", "")).strip() or str(
                source.get("key", "")
            ).strip()
            if runtime_key and self._temp_home_key == runtime_key:
                self._temp_home_key = ""
            # 临时状态落盘：App 重建会销毁本实例，新实例靠它恢复。
            try:
                self._save_settings()
            except Exception as exc:
                self._warn("临时加载状态保存失败: {}".format(exc))
            removed = self._remove_site_from_app(runtime_key) if runtime_key else False
            if removed:
                return True, "「{}」已移出加载列表".format(name)
            return True, "「{}」已移出加载列表（退出 App 后彻底消失）".format(name)
        # 默壳版：永久注入站点移出——从注册表移除 + 清除持久化记录，
        # 触发 App 重载后站点从站点列表消失。
        if identity in self.perm_injected_identities:
            self.perm_injected_identities.discard(identity)
            site = source.get("site") if isinstance(source.get("site"), dict) else {}
            runtime_key = str(site.get("key", "")).strip() or str(
                source.get("key", "")
            ).strip()
            if runtime_key and self._temp_home_key == runtime_key:
                self._temp_home_key = ""
            try:
                self._save_settings()
            except Exception as exc:
                self._warn("永久加载状态保存失败: {}".format(exc))
            self._remove_site_from_registry(source)
            self._schedule_manager_page_refresh(delay=0.2)
            return True, "「{}」已移出加载列表".format(name)
        # 配置加载的站点移出（全部加载写入的站点）。
        if isinstance(self.selected_identities, set):
            self.selected_identities.discard(identity)
        self.temp_identities.discard(identity)
        try:
            self._save_settings()
        except Exception as exc:
            self._warn("加载选择保存失败: {}".format(exc))
        # 配置只写永久选择集；临时站点仅存运行态内存，不落盘。
        subset = (
            set(self.selected_identities)
            if isinstance(self.selected_identities, set)
            else set()
        )
        completed, _detail = self._apply_selection_and_write_locked(subset, True)
        if not completed:
            return False, "{} 移出失败：{}".format(
                name, self.status.get("error") or self.status.get("write_state") or "未知错误"
            )
        # 配置重载会重建运行态站点表，重新注入其余临时站点避免被冲掉。
        self._reinject_temp_sites_locked()
        return True, "「{}」已移出加载列表".format(name)

    def _selected_registry_keys(self):
        """永久选择集对应的运行态站点 key（用于 App 重载回读校验）。

        临时站点不写入配置文件，不参与重载回读校验。
        """
        selected = (
            set(self.selected_identities)
            if isinstance(self.selected_identities, set)
            else set()
        )
        keys = set()
        skip_webhome = self.app_mode != self.APP_MODE_WEBHTV
        for source in self.cache.get("sources", []):
            if str(source.get("identity", "")) not in selected:
                continue
            site = source.get("site") or {}
            if not isinstance(site, dict):
                site = {}
            if skip_webhome and (
                str(source.get("type", "")).upper() == "HTML"
                or str(site.get("homePage", "")).strip()
            ):
                continue
            runtime_key = str(site.get("key", "")).strip() or str(
                source.get("key", "")
            ).strip()
            if runtime_key:
                keys.add(runtime_key)
        return keys

    # ---- FloatSpider 风格：运行时反射注入/移除临时站点 ----
    def _runtime_vod_config(self):
        """获取运行中的 VodConfig 实例。失败返回 None。"""
        for suffix in self.RUNTIME_VOD_CONFIG_SUFFIXES:
            cls = self._find_runtime_class((suffix,))
            if cls is None:
                continue
            try:
                return cls.get()
            except Exception:
                continue
        return None

    def _app_process_id(self):
        """当前 App 进程 PID，用于判定临时加载状态是否属于本进程会话。

        同一 App 进程内 spider 实例销毁/重建 PID 不变；App 重启后 PID
        变化。读取失败返回 0（此时不做 PID 校验，避免误清临时状态）。
        """
        try:
            from java import jclass
            return int(jclass("android.os.Process").myPid())
        except Exception:
            return 0

    def _runtime_site_cls(self):
        """获取 Site 类。支持跨壳探测。"""
        return self._find_runtime_class(self.RUNTIME_SITE_SUFFIXES)

    def _find_runtime_class(self, suffixes, bases=None):
        """在运行时通过 jclass 定位目标类。支持跨壳类名探测。

        个别机型（多 dex 分包 / 旧版运行时）jclass 找不到壳内类，
        再用壳类加载器做 Class.forName 兜底（见
        _find_runtime_class_via_loader）。
        """
        bases = bases or self.RUNTIME_BASE_PACKAGES
        from java import jclass
        for base in bases:
            for suffix in suffixes:
                full = "{}.{}".format(base, suffix)
                try:
                    return jclass(full)
                except Exception:
                    continue
        return self._find_runtime_class_via_loader(suffixes, bases, jclass)

    def _find_runtime_class_via_loader(self, suffixes, bases, jclass):
        """jclass 全部失败时的兜底：拿到壳类加载器后 Class.forName。

        优先用 Chaquopy 保存的 App 类加载器（本脚本正运行其中）；
        再退到锚点壳类自身的类加载器。两者都与壳代码在同一 dex，
        不受 JNI 默认类加载器差异影响。
        """
        loaders = []
        try:
            Python = jclass("com.chaquo.python.Python")
            loader = Python.getInstance().getClassLoader()
            if loader is not None:
                loaders.append(loader)
        except Exception:
            pass
        for anchor in self.RUNTIME_ANCHOR_CLASSES:
            try:
                anchor_cls = jclass(anchor)
                loader = anchor_cls.getClassLoader()
                if loader is not None and loader not in loaders:
                    loaders.append(loader)
            except Exception:
                continue
        try:
            context_loader = (
                jclass("java.lang.Thread").currentThread().getContextClassLoader()
            )
            if context_loader is not None and context_loader not in loaders:
                loaders.append(context_loader)
        except Exception:
            pass
        try:
            Class = jclass("java.lang.Class")
        except Exception:
            return None
        for loader in loaders:
            for base in bases:
                for suffix in suffixes:
                    full = "{}.{}".format(base, suffix)
                    try:
                        return Class.forName(full, True, loader)
                    except Exception:
                        continue
        return None

    def _runtime_file_url(self, file_url):
        """将 file:// 路径转换为 App 本地 Server 可访问的 URL。

        优先通过 UrlUtil.convert 反射转换；失败则手动拼接
        http://127.0.0.1:<port>/file/…，与 FloatSpider 一致。
        """
        file_url = str(file_url or "").strip()
        if not file_url.startswith("file://"):
            return file_url
        try:
            from java import jclass
            UrlUtil = self._find_runtime_class(self.RUNTIME_URL_UTIL_SUFFIXES)
            if UrlUtil is not None:
                return str(UrlUtil.convert(file_url))
        except Exception:
            pass
        try:
            from java import jclass
            port = int(jclass("com.github.catvod.Proxy").getPort())
        except Exception:
            port = 9978
        relative = file_url[7:]
        return "http://127.0.0.1:{}/file/{}".format(port, relative.lstrip("/"))

    def _inject_site_into_app(self, source, set_home=True):
        """通过 Java 反射将单个站点直接注入运行中的 VodConfig（FloatSpider 方案）。

        不写入任何配置文件；set_home=True 时注入成功后自动切换首页到该站。
        返回 (ok, message)。
        """
        try:
            from java import jclass

            site_dict = self._build_site(source)
            VodConfig = self._find_runtime_class(self.RUNTIME_VOD_CONFIG_SUFFIXES)
            if VodConfig is None:
                return False, "未找到 VodConfig 类"
            vod_config = VodConfig.get()
            sites = vod_config.getSites()

            existing_index = -1
            for i in range(sites.size()):
                if sites.get(i).getKey() == site_dict["key"]:
                    existing_index = i
                    break

            Site = self._find_runtime_class(self.RUNTIME_SITE_SUFFIXES)
            if Site is None:
                return False, "未找到 Site 类"
            new_site = Site()
            new_site.setKey(site_dict["key"])
            new_site.setName(site_dict["name"])
            try:
                new_site.setType(int(site_dict.get("type", 3)))
            except Exception:
                pass
            if "api" in site_dict:
                new_site.setApi(self._runtime_file_url(site_dict["api"]))
            if "jar" in site_dict:
                new_site.setJar(self._runtime_file_url(site_dict["jar"]))
            if "ext" in site_dict:
                new_site.setExt(str(site_dict["ext"]))
            for field in ("searchable", "quickSearch", "changeable"):
                if field in site_dict:
                    try:
                        setter = getattr(
                            new_site,
                            "set" + field[0].upper() + field[1:],
                        )
                        setter(int(site_dict[field]))
                    except Exception:
                        pass
            if existing_index >= 0:
                sites.set(existing_index, new_site)
            else:
                sites.add(new_site)
            # 临时加载成功后自动切换首页到该站源。
            # VodConfig.setHome 内部会置选中态并发出 RefreshEvent.home()。
            switched = False
            if set_home:
                try:
                    vod_config.setHome(new_site)
                    switched = True
                    # 记录当前临时 home，供重建后看门补注恢复选中。
                    self._temp_home_key = str(site_dict["key"])
                except Exception as exc:
                    self._warn("切换到新加载站点失败: {}".format(exc))
            if not switched:
                self._post_app_refresh()
            return True, ""
        except Exception as exc:
            self._log("ERROR", "内存注入站点失败: {}".format(exc))
            return False, str(exc)

    def _remove_site_from_app(self, source_key):
        """通过 Java 反射从 VodConfig 运行态移除单个站点。"""
        try:
            from java import jclass
            VodConfig = self._find_runtime_class(self.RUNTIME_VOD_CONFIG_SUFFIXES)
            if VodConfig is None:
                return False
            vod_config = VodConfig.get()
            sites = vod_config.getSites()
            removed = False
            for i in range(sites.size() - 1, -1, -1):
                if sites.get(i).getKey() == source_key:
                    sites.remove(i)
                    removed = True
                    break
            if removed:
                self._post_app_refresh()
            return removed
        except Exception as exc:
            self._log("ERROR", "内存移除站点失败: {}".format(exc))
            return False

    def _post_app_refresh(self):
        """触发 App 首页刷新，让用户立即看到注入/移除后的站点列表。"""
        try:
            from java import jclass
            RefreshEvent = self._find_runtime_class(
                self.RUNTIME_REFRESH_EVENT_SUFFIXES
            )
            if RefreshEvent is not None:
                RefreshEvent.home()
        except Exception as exc:
            self._warn("App 刷新事件触发失败: {}".format(exc))

    def _auto_scan_on_enter_locked(self):
        """无有效快照时进入管理页自动扫描一次（v7：仅扫描，不写盘、不重载）。

        仅扫描目录并填充文件浏览缓存；加载由用户显式点击「加载」完成。
        进程内冷却防止频繁补扫。
        """
        if not self.auto_scan_on_empty or self.auto_scan_suspended:
            return False
        if self.config_dirty or not any(self.type_enabled.values()):
            return False
        now = time.monotonic()
        if now - _AUTO_SCAN_STATE["last"] < self.AUTO_SCAN_COOLDOWN:
            return False
        _AUTO_SCAN_STATE["last"] = now
        ok = self._scan_only_locked()
        if (
            not ok
            and not self.cache["sources"]
            and not self.cache["ignored"]
            and not self.cache.get("lives")
        ):
            self._set_manual_idle_status("未发现本地站点，请点击「扫描」")
        return True

    def _suspend_auto_scan(self):
        if self.auto_scan_suspended:
            return
        self.auto_scan_suspended = True
        try:
            self._save_settings()
        except Exception as exc:
            self._warn("自动补扫暂停状态保存失败: {}".format(exc))

    def _snapshot_matches_registry(self):
        data = self._load_scan_cache_payload(warn=False)
        snapshot = data.get("snapshot", {}) if isinstance(data, dict) else {}
        if not isinstance(snapshot, dict):
            return False
        token = str(snapshot.get("registry_token", ""))
        return bool(token) and token == self._registry_token(self.output_path)

    def _set_manual_idle_status(self, state="请点击「扫描」"):
        self.cache = self._empty_cache()
        self.status = self._empty_status()
        self.status["write_state"] = state
        try:
            registry = self._load_registry()
            items = registry.get("items", [])
            if isinstance(items, list):
                self.status["generated_sites"] = sum(
                    1 for item in items if self._is_generated_registry_item(item)
                )
                self.status["manual_sites"] = len(items) - self.status["generated_sites"]
        except Exception as exc:
            self._warn("注册表状态读取失败: {}".format(exc))

    def _clear_scan_cache_file(self):
        removed = 0
        path = os.path.abspath(os.path.expanduser(self.cache_path))
        protected = {
            os.path.abspath(os.path.expanduser(item))
            for item in (
                self.registry_path,
                self.output_path,
                self.settings_path,
                self.roots_config_path,
            )
        }
        if path in protected:
            self._warn("扫描缓存路径与配置文件冲突，已跳过删除: {}".format(path))
            return 0
        for candidate in (path, path + ".tmp"):
            try:
                os.remove(candidate)
                removed += 1
            except FileNotFoundError:
                pass
            except Exception as exc:
                self._warn("扫描缓存删除失败: {} ({})".format(candidate, exc))
        return removed

    def _scan_all_roots(self, sync_network=False, progress=None):
        """逐根扫描本地目录。

        progress(message, done=None, total=None, indeterminate=None) 可选：
        手动扫描时把「正在同步网络目录 / 正在扫描第几个根」回传到进度面板；
        自动补扫/启动刷新不传，行为与旧版完全一致。
        """
        self.cache = self._empty_cache()
        self._package_filter_excluded = False
        self._jar_inspection_cache = {}
        self.incomplete_scan_roots = []
        self.incomplete_scan_types = set()
        # v8.0：手动扫描时先同步已启用的网络目录到本地镜像；
        # 自动补扫/启动刷新不发起网络请求，直接沿用上次镜像。
        if sync_network and any(
            item.get("enabled", True) for item in self.network_roots
        ):
            if progress:
                try:
                    progress("正在同步网络目录…", indeterminate=True)
                except Exception:
                    pass
            try:
                self._sync_network_roots_locked(progress=progress)
            except Exception as exc:
                self._warn("网络目录同步异常（继续扫描本地与已有镜像）: {}".format(exc))
        effective_roots = self._effective_scan_roots()
        sources = []
        ignored_sources = []
        live_sources = []
        root_contexts = []
        site_enabled_package_ids = (
            self._site_enabled_package_download_site_ids()
        )
        live_enabled_package_ids = (
            self._live_enabled_package_download_site_ids()
        )
        seen_paths = set()
        self_path = os.path.realpath(__file__)
        old_file_cache = self._load_scan_cache()
        new_file_cache = {}
        available_types = set()
        limit_reached = False

        # v8.0：文件总数需遍历后才知道，进度条按「扫描根 i/N」粗粒度推进，
        # 消息文本同时展示已发现文件数，兼顾直观与零额外磁盘开销。
        total_roots = sum(
            1
            for spec in effective_roots
            if str(spec.get("type", "")).upper() in self.TYPE_ORDER
            and self.type_enabled.get(
                str(spec.get("type", "")).upper(), True
            )
        )
        root_index = 0
        if progress and total_roots:
            try:
                progress(
                    "开始扫描 {} 个目录…".format(total_roots),
                    done=0,
                    total=total_roots,
                )
            except Exception:
                pass

        for root_order, spec in enumerate(effective_roots):
            if limit_reached:
                break
            source_type = str(spec.get("type", "")).upper()
            if source_type not in self.TYPE_ORDER:
                self._warn("忽略未知类型目录: {}".format(spec))
                continue
            if not self.type_enabled.get(source_type, True):
                continue
            root_index += 1
            if progress:
                try:
                    type_label = self.TYPE_LABEL.get(source_type, source_type)
                    root_path = str(spec.get("path", ""))
                    progress(
                        "正在扫描（{}/{}）{} 目录：{} · 已发现 {} 个文件".format(
                            root_index,
                            total_roots,
                            type_label,
                            root_path,
                            self.status["found"],
                        ),
                        done=root_index - 1,
                        total=total_roots,
                    )
                except Exception:
                    pass
            root = os.path.abspath(os.path.expanduser(str(spec.get("path", ""))))
            extensions = {
                self._normalize_extension(ext)
                for ext in spec.get("extensions", self.TYPE_EXTENSIONS[source_type])
            }
            extensions.discard("")
            if not os.path.isdir(root):
                self._warn("目录不存在: {}".format(root))
                self._mark_scan_incomplete(source_type, root)
                continue
            available_types.add(source_type)
            manifest_owned_paths = self._manifest_owned_source_paths(
                root, source_type
            )
            manifest_owned_paths.update(
                self._bundle_owned_source_paths(root, source_type)
            )
            js_runtime_paths = (
                self._js_runtime_dependency_paths(root)
                if source_type == "JS"
                else set()
            )
            if source_type in ("CSP",):
                local_jar_pairs, local_jar_ambiguous = self._discover_json_jar_pairs(
                    root, manifest_owned_paths
                )
            else:
                local_jar_pairs, local_jar_ambiguous = {}, set()

            def walk_error(exc, current_type=source_type, current_root=root):
                failed_path = getattr(exc, "filename", "") or current_root
                self._mark_scan_incomplete(current_type, failed_path)
                self._warn("扫描目录读取失败: {} ({})".format(failed_path, exc))

            for current, dirs, files in os.walk(
                root, topdown=True, onerror=walk_error, followlinks=False
            ):
                relative_dir = os.path.relpath(current, root)
                depth = 0 if relative_dir == "." else relative_dir.count(os.sep) + 1
                dirs[:] = sorted(
                    [
                        name
                        for name in dirs
                        if not name.startswith(".")
                        and name.lower() not in self.SKIP_DIRS
                        and not os.path.islink(os.path.join(current, name))
                    ],
                    key=lambda value: value.lower(),
                )
                if depth >= self.max_scan_depth:
                    dirs[:] = []
                for file_name in sorted(files, key=lambda value: value.lower()):
                    full_path = os.path.join(current, file_name)
                    lower_name = file_name.lower()
                    extension = os.path.splitext(lower_name)[1]
                    if extension not in extensions:
                        continue
                    is_manifest = self._is_site_manifest_name(lower_name)
                    if source_type == "JS" and extension == ".json" and not is_manifest:
                        continue
                    candidate_path = os.path.realpath(full_path)
                    if not is_manifest and candidate_path in manifest_owned_paths:
                        continue
                    if source_type == "JS" and candidate_path in js_runtime_paths:
                        continue
                    if self.status["found"] >= self.max_scan_files:
                        limit_reached = True
                        self.status["limit_reached"] = True
                        self._warn(
                            "已达扫描文件上限 {}，后续文件未扫描".format(
                                self.max_scan_files
                            )
                        )
                        break
                    self.status["found"] += 1
                    if os.path.islink(full_path) or not os.path.isfile(full_path):
                        self.status["skipped"] += 1
                        continue
                    real_path = os.path.realpath(full_path)
                    if real_path == self_path and not self._is_auto_loader_python(
                        source_type, lower_name
                    ):
                        continue
                    if real_path in seen_paths:
                        self.status["duplicates"] += 1
                        continue
                    try:
                        readable = os.access(real_path, os.R_OK)
                        stat = os.stat(real_path)
                        file_size = stat.st_size
                        modified_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1000000000))
                    except Exception as exc:
                        self.status["skipped"] += 1
                        self._mark_scan_incomplete(source_type, full_path)
                        self._warn("读取文件状态失败: {} ({})".format(real_path, exc))
                        continue
                    if not readable or file_size <= 0:
                        self.status["skipped"] += 1
                        self._warn("跳过不可读或空文件: {}".format(real_path))
                        continue
                    if file_size > self.max_source_size:
                        self.status["skipped"] += 1
                        self._warn(
                            "跳过超过大小上限的文件: {} ({} bytes)".format(
                                real_path, file_size
                            )
                        )
                        continue

                    relative_in_root = os.path.relpath(real_path, root).replace(os.sep, "/")
                    if self._is_excluded(source_type, lower_name, relative_in_root):
                        self.status["skipped"] += 1
                        continue
                    identity = self._source_identity(source_type, real_path)
                    if identity in self.pruned_sources:
                        # 已被「自动清理屏蔽站点」移出配置。源文件仍在磁盘上，
                        # 从清除入口复位后即可重新参与扫描。
                        self.status["skipped"] += 1
                        continue

                    bundle = None
                    marker = {}
                    package_id = ""
                    package_label = ""
                    package_sites_enabled = True
                    package_lives_enabled = False
                    standalone_live_file = False
                    if (
                        source_type in ("CSP",)
                        and extension == ".json"
                        and not is_manifest
                    ):
                        marker = self._installed_package_marker(root, real_path)
                        package_id = str(marker.get("id", "")).strip()
                        package_label = str(marker.get("name", "")).strip()
                        package_sites_enabled = (
                            not package_id
                            or package_id in site_enabled_package_ids
                        )
                        package_lives_enabled = bool(
                            package_id
                            and package_id in live_enabled_package_ids
                        )
                        if package_id and (
                            not package_sites_enabled
                            or not package_lives_enabled
                        ):
                            self._package_filter_excluded = True
                        # 独立本地直播识别：未归档为「下载站点整包」(.dual-local-package
                        # 标记缺失) 的 .json，只要其根对象含非空 lives 数组，就视为本地
                        # 直播集合文件，绕过整包的 live 开关限制照常收录直播。
                        standalone_live_file = False
                        if not package_id:
                            standalone_live_file = self._has_raw_lives(real_path)
                        bundle = self._parse_site_bundle(
                            real_path,
                            include_sites=package_sites_enabled,
                            include_lives=package_lives_enabled or standalone_live_file,
                            include_context=bool(
                                package_id
                                and package_id in site_enabled_package_ids
                            ),
                        )
                    if bundle is not None:
                        role = self._detect_file_role(source_type, lower_name, real_path)
                        if role not in ("source", "forced_source"):
                            self.status["skipped"] += 1
                            self._warn("已按 {} 标识排除: {}".format(role, real_path))
                            continue
                        self.status["cache_misses"] += 1
                        seen_paths.add(real_path)
                        new_file_cache[identity] = {
                            "size": file_size,
                            "mtime_ns": modified_ns,
                            "strict": bool(self.strict_recognition),
                            "role": "bundle",
                            "valid": bool(bundle["sites"]),
                            "validation": "TVBox 整包配置",
                        }
                        root_context = bundle.get("root_context", {})
                        if (
                            isinstance(root_context, dict)
                            and root_context
                            and package_id in site_enabled_package_ids
                        ):
                            root_contexts.append(
                                {
                                    "id": self.GENERATED_CONTEXT_PREFIX
                                    + self._digest(
                                        "{}|{}".format(
                                            package_id, self._file_url(real_path)
                                        ),
                                        16,
                                    ),
                                    "package_id": package_id,
                                    "package_name": package_label,
                                    "path": real_path,
                                    "context": copy.deepcopy(root_context),
                                    "dependencies": copy.deepcopy(
                                        bundle.get(
                                            "root_context_dependencies", []
                                        )
                                    ),
                                }
                            )
                            self._log(
                                "INFO",
                                "整包播放上下文待集成: {} 字段={} 下载站点={}".format(
                                    real_path,
                                    ",".join(root_context.keys()),
                                    package_label or package_id,
                                ),
                            )
                        elif (
                            isinstance(root_context, dict)
                            and root_context
                            and package_id
                        ):
                            self._log(
                                "INFO",
                                "整包播放上下文未集成: {} 字段={} 原因=下载站点已关闭或删除".format(
                                    real_path, ",".join(root_context.keys())
                                ),
                            )
                        if package_id in site_enabled_package_ids:
                            for item in bundle.get("root_context_rejected", []):
                                self._log(
                                    "WARN",
                                    "整包播放上下文已跳过: {}.{} ({})".format(
                                        os.path.basename(real_path),
                                        item.get("field", "未知字段"),
                                        item.get("reason", "无法识别"),
                                    ),
                                )
                        if (
                            bundle.get("lives")
                            and (package_id in live_enabled_package_ids or standalone_live_file)
                        ):
                            for entry in bundle["lives"]:
                                live = copy.deepcopy(entry["live"])
                                live_name = str(live.get("name", "直播源")).strip()
                                if package_label and not live_name.startswith(
                                    "【{}】".format(package_label)
                                ):
                                    live["name"] = "【{}】{}".format(
                                        package_label, live_name
                                    )
                                elif standalone_live_file and not live_name.startswith(
                                    "【{}】".format(package_label or "")
                                ):
                                    # 独立本地直播：用「来源目录名」作标签，便于与整包直播区分。
                                    standalone_label = self._standalone_live_label(root, real_path)
                                    if standalone_label and not live_name.startswith(
                                        "【{}】".format(standalone_label)
                                    ):
                                        live["name"] = "【{}】{}".format(
                                            standalone_label, live_name
                                        )
                                identity_live = self._bundle_live_identity(
                                    real_path, live
                                )
                                live_sources.append(
                                    {
                                        "id": self.GENERATED_LIVE_PREFIX
                                        + self._digest(identity_live, 16),
                                        "identity": identity_live,
                                        "package_id": package_id,
                                        "package_name": package_label
                                        or self._standalone_live_label(root, real_path),
                                        "path": real_path,
                                        "live": live,
                                        "dependencies": entry["dependencies"],
                                    }
                                )
                            self._log(
                                "INFO",
                                "整包直播待集成: {} 直播={} 下载站点={} 独立直播文件={}".format(
                                    real_path,
                                    len(bundle["lives"]),
                                    package_label or package_id or "(本地)",
                                    "是" if standalone_live_file else "否",
                                ),
                            )
                        elif bundle.get("lives") and (package_id or standalone_live_file):
                            self._log(
                                "INFO",
                                "整包直播未集成: {} 直播={} 原因={}".format(
                                    real_path,
                                    len(bundle["lives"]),
                                    "下载站点已关闭或删除" if package_id else "未识别为有效直播集合",
                                ),
                            )
                        for entry in bundle["sites"]:
                            site = entry["site"]
                            site_identity = self._bundle_source_identity(
                                source_type, real_path, site
                            )
                            if site_identity in self.pruned_sources:
                                # 整包内的单个站点被清理：跳过该站点，
                                # 同包其它站点不受影响，api.json 不动。
                                self.status["skipped"] += 1
                                continue
                            if site_identity in seen_paths:
                                self.status["duplicates"] += 1
                                continue
                            seen_paths.add(site_identity)
                            new_file_cache[site_identity] = {
                                "size": file_size,
                                "mtime_ns": modified_ns,
                                "strict": bool(self.strict_recognition),
                                "role": "bundle_site",
                                "valid": True,
                                "validation": entry["validation"],
                            }
                            source_id = "src_" + self._digest(site_identity, 20)
                            key = (
                                self.GENERATED_KEY_PREFIX
                                + source_type.lower()
                                + "_"
                                + self._digest(site_identity, 14)
                            )
                            source = {
                                "id": source_id,
                                "identity": site_identity,
                                "key": key,
                                "type": source_type,
                                "path": real_path,
                                "scan_root": root,
                                "root_order": root_order,
                                "relative_in_root": "{}::site:{:04d}".format(
                                    relative_in_root, entry["index"]
                                ),
                                "base_name": str(site.get("name", "")).strip(),
                                "package_label": self._bundle_package_label(
                                    root, real_path
                                ),
                                "package_id": package_id,
                                "validation": entry["validation"],
                                "ignored": site_identity in self.ignored_sources,
                                "size": file_size,
                                "mtime_ns": modified_ns,
                                "csp_site": site,
                                "dependencies": entry["dependencies"],
                            }
                            test_result = self.site_test_results.get(site_identity, {})
                            if not isinstance(test_result, dict) or test_result.get(
                                "source_signature"
                            ) != self._source_signature(source):
                                test_result = {}
                            source["test_result"] = test_result
                            if source["ignored"]:
                                ignored_sources.append(source)
                            else:
                                sources.append(source)
                        rejected = bundle["rejected"]
                        self.status["skipped"] += len(rejected)
                        self._log(
                            "INFO",
                            "整包配置识别: {} 总站点={} 集成={} 跳过={} 站点开关={}".format(
                                real_path,
                                bundle["total"],
                                len(bundle["sites"]),
                                len(rejected),
                                "开" if package_sites_enabled else "关",
                            ),
                        )
                        if rejected:
                            self._warn(
                                "整包配置已跳过 {} 个依赖不完整或不兼容站点: {}".format(
                                    len(rejected), os.path.basename(real_path)
                                )
                            )
                            for item in rejected:
                                self._log(
                                    "WARN",
                                    "整包站点已跳过: {} ({})".format(
                                        item["name"], item["reason"]
                                    ),
                                )
                        if package_id in live_enabled_package_ids:
                            for item in bundle.get("live_rejected", []):
                                self._log(
                                    "WARN",
                                    "整包直播已跳过: {} ({})".format(
                                        item["name"], item["reason"]
                                    ),
                                )
                        continue

                    # CSP 整包（例如 type: 4 CMS 采集站）已在上方优先解析，
                    # 不需要本地 JAR。只有未识别为整包的普通 CSP JSON 才要求配对 JAR。
                    if (
                        source_type == "CSP"
                        and not is_manifest
                        and real_path not in local_jar_pairs
                        and real_path not in local_jar_ambiguous
                    ):
                        self.status["skipped"] += 1
                        continue

                    if package_id and not package_sites_enabled:
                        self._log(
                            "INFO",
                            "本地包站点文件未集成: {} 原因=站点开关已关闭".format(
                                real_path
                            ),
                        )
                        continue

                    cached = old_file_cache.get(identity)
                    cache_hit = (
                        isinstance(cached, dict)
                        and cached.get("size") == file_size
                        and cached.get("mtime_ns") == modified_ns
                        and cached.get("strict") == bool(self.strict_recognition)
                        and not is_manifest
                    )
                    if cache_hit:
                        role = str(cached.get("role", "source"))
                        valid = bool(cached.get("valid", True))
                        validation = str(cached.get("validation", ""))
                        self.status["cache_hits"] += 1
                    else:
                        role = self._detect_file_role(source_type, lower_name, real_path)
                        forced = role == "forced_source"
                        valid, validation = (
                            (True, "已通过 @tvbox-source 强制收录")
                            if forced
                            else self._validate_source(source_type, real_path)
                        )
                        self.status["cache_misses"] += 1
                    new_file_cache[identity] = {
                        "size": file_size,
                        "mtime_ns": modified_ns,
                        "strict": bool(self.strict_recognition),
                        "role": role,
                        "valid": bool(valid),
                        "validation": validation,
                    }
                    if role not in ("source", "forced_source"):
                        self.status["skipped"] += 1
                        self._warn("已按 {} 标识排除: {}".format(role, real_path))
                        continue
                    if not valid and self.strict_recognition:
                        self.status["skipped"] += 1
                        self._warn(validation)
                        continue
                    if validation and not valid:
                        self._warn(validation)
                    csp_site = None
                    dependencies = []
                    if source_type == "JS" and not is_manifest:
                        try:
                            js_text = self._read_text(real_path, 512 * 1024)
                            if (
                                self._has_drpy_rule(js_text)
                                and not self._has_direct_js_spider(js_text)
                            ):
                                runtime_path = self._find_js_runtime(
                                    real_path, root
                                )
                                if not runtime_path:
                                    self.status["skipped"] += 1
                                    self._warn(
                                        "DRPY 规则缺少 drpy2 运行时，已跳过: {}".format(
                                            real_path
                                        )
                                    )
                                    continue
                                csp_site = {
                                    "name": self._drpy_rule_title(js_text)
                                    or os.path.splitext(file_name)[0],
                                    "api": self._file_url(runtime_path),
                                    "ext": self._file_url(real_path),
                                    "type": 3,
                                    "searchable": self.DEFAULT_SEARCHABLE,
                                    "quickSearch": self.DEFAULT_QUICK_SEARCH,
                                }
                                dependencies = [runtime_path]
                                validation = "DRPY 规则；运行时 {}".format(
                                    os.path.basename(runtime_path)
                                )
                        except Exception as exc:
                            self.status["skipped"] += 1
                            self._warn(
                                "DRPY 规则配对失败: {} ({})".format(
                                    real_path, exc
                                )
                            )
                            continue
                    if source_type in ("CSP",) and not is_manifest:
                        if real_path in local_jar_ambiguous:
                            self.status["skipped"] += 1
                            self._warn(
                                "{} JAR 绑定不明确，已跳过: {}".format(
                                    source_type, real_path
                                )
                            )
                            continue
                        paired_jar = local_jar_pairs.get(real_path)
                        if paired_jar:
                            try:
                                csp_site, dependencies, validation = (
                                    self._auto_csp_site(real_path, paired_jar)
                                )
                            except Exception as exc:
                                self.status["skipped"] += 1
                                self._warn(
                                    "{} 自动配对失败: {} ({})".format(
                                        source_type, real_path, exc
                                    )
                                )
                                continue
                    if is_manifest and source_type in ("JS", "CSP"):
                        try:
                            csp_site, dependencies, validation = (
                                self._parse_site_manifest(real_path, source_type)
                            )
                        except Exception as exc:
                            self.status["skipped"] += 1
                            self._warn(
                                "站点清单解析失败: {} ({})".format(
                                    real_path, exc
                                )
                            )
                            continue

                    seen_paths.add(real_path)
                    if csp_site is not None:
                        base_name = str(csp_site.get("name", "")).strip()
                    else:
                        base_name = file_name[: -len(extension)] if extension else file_name
                    source_id = "src_" + self._digest(identity, 20)
                    key = self.GENERATED_KEY_PREFIX + source_type.lower() + "_" + self._digest(
                        identity, 14
                    )
                    source = {
                        "id": source_id,
                        "identity": identity,
                        "key": key,
                        "type": source_type,
                        "path": real_path,
                        "scan_root": root,
                        "root_order": root_order,
                        "relative_in_root": relative_in_root,
                        "base_name": base_name,
                        "validation": validation,
                        "ignored": identity in self.ignored_sources,
                        "size": file_size,
                        "mtime_ns": modified_ns,
                    }
                    package_label = self._installed_package_label(root, real_path)
                    if package_label:
                        source["package_label"] = package_label
                    if csp_site is not None:
                        source["csp_site"] = csp_site
                        source["dependencies"] = dependencies
                    test_result = self.site_test_results.get(identity, {})
                    if not isinstance(test_result, dict) or test_result.get(
                        "source_signature"
                    ) != self._source_signature(source):
                        test_result = {}
                    source["test_result"] = test_result
                    if source["ignored"]:
                        ignored_sources.append(source)
                    else:
                        sources.append(source)
                if limit_reached:
                    break
            if progress:
                try:
                    progress(
                        "已完成（{}/{}）个目录 · 累计发现 {} 个文件，正在整理结果…".format(
                            root_index,
                            total_roots,
                            self.status["found"],
                        ),
                        done=root_index,
                        total=total_roots,
                    )
                except Exception:
                    pass

        all_sources = sources + ignored_sources
        if not self.block_adult_sites:
            previous_adult_blocked = set(self.adult_blocked_sources)
            previous_adult_allowed = set(self.adult_allowed_sources)
            for source in all_sources:
                identity = source["identity"]
                is_adult = self._is_adult_source(source)
                if is_adult and identity not in self.adult_allowed_sources:
                    self.adult_blocked_sources.add(identity)
                    source["adult_blocked"] = True
                    source["ignored"] = True
                    self.status["adult_filtered"] += 1
                    self._log(
                        "INFO",
                        "18+站点已加入屏蔽列表: {} ({})".format(
                            source.get("base_name", "未命名站点"),
                            source.get("relative_in_root", source.get("path", "")),
                        ),
                    )
                else:
                    self.adult_blocked_sources.discard(identity)
                    source["adult_blocked"] = False
                    source["ignored"] = identity in (
                        self.manual_ignored_sources | self.auto_blocked_sources
                    )
                    if not is_adult:
                        self.adult_allowed_sources.discard(identity)
            self._sync_ignored_sources()
            if self.status["adult_filtered"]:
                self._log(
                    "INFO",
                    "18+站点屏蔽完成: {} 个，可在屏蔽分类中手动恢复".format(
                        self.status["adult_filtered"]
                    ),
                )
            if (
                previous_adult_blocked != self.adult_blocked_sources
                or previous_adult_allowed != self.adult_allowed_sources
            ):
                try:
                    self._save_settings()
                except Exception as exc:
                    self._warn("18+站点屏蔽状态保存失败: {}".format(exc))
        else:
            for source in all_sources:
                source["adult_blocked"] = False
                source["ignored"] = source["identity"] in (
                    self.manual_ignored_sources | self.auto_blocked_sources
                )
        self._apply_display_names(all_sources)
        all_sources.sort(
            key=lambda item: (
                item["root_order"],
                self.TYPE_ORDER[item["type"]],
                item["relative_in_root"].lower(),
            )
        )

        deduplicated_sources = []
        active_fingerprints = set()
        for source in all_sources:
            source["site"] = self._build_site(source)
            fingerprint = self._site_fingerprint(source["site"])
            if (
                not source["ignored"]
                and fingerprint
                and fingerprint in active_fingerprints
            ):
                self.status["duplicates"] += 1
                self._log(
                    "INFO",
                    "语义重复站点已去重: {} ({})".format(
                        source["base_name"], source["relative_in_root"]
                    ),
                )
                continue
            if not source["ignored"] and fingerprint:
                active_fingerprints.add(fingerprint)
            deduplicated_sources.append(source)

        all_sources = deduplicated_sources
        for source in all_sources:
            self.cache["source_index"][source["id"]] = source
            source_type = source["type"]
            counts_key = "ignored_counts" if source["ignored"] else "type_counts"
            counts = self.cache[counts_key]
            counts[source_type] = counts.get(source_type, 0) + 1

        self.cache["sources"] = [item for item in all_sources if not item["ignored"]]
        self.cache["ignored"] = [item for item in all_sources if item["ignored"]]
        deduplicated_lives = []
        seen_live_fingerprints = set()
        for item in live_sources:
            fingerprint = self._live_fingerprint(item.get("live", {}))
            if not fingerprint or fingerprint in seen_live_fingerprints:
                self.status["duplicate_lives"] += 1
                self._log(
                    "INFO",
                    "语义重复直播已去重: {}".format(
                        item.get("live", {}).get("name", "未命名直播")
                    ),
                )
                continue
            seen_live_fingerprints.add(fingerprint)
            deduplicated_lives.append(item)
        self.cache["lives"] = deduplicated_lives
        self.cache["contexts"] = root_contexts
        self.status["generated_lives"] = len(deduplicated_lives)
        self.status["included"] = len(self.cache["sources"])
        self.status["ignored"] = len(self.cache["ignored"])
        persisted_identities = (
            self.ignored_sources
            | self.adult_blocked_sources
            | self.adult_allowed_sources
        )
        stale_ignored = {
            identity
            for identity in persisted_identities
            if not limit_reached
            and identity.split("|", 1)[0] in available_types
            and not self._scan_failure_covers_identity(identity)
            and identity not in new_file_cache
        }
        if stale_ignored:
            self.manual_ignored_sources.difference_update(stale_ignored)
            self.auto_blocked_sources.difference_update(stale_ignored)
            self.adult_blocked_sources.difference_update(stale_ignored)
            self.adult_allowed_sources.difference_update(stale_ignored)
            self._sync_ignored_sources()
            self.status["stale_ignored_removed"] = len(stale_ignored)
        stale_test_results = {
            identity
            for identity in self.site_test_results
            if not limit_reached
            and identity.split("|", 1)[0] in available_types
            and not self._scan_failure_covers_identity(identity)
            and identity not in new_file_cache
        }
        for identity in stale_test_results:
            self.site_test_results.pop(identity, None)
        if stale_ignored or stale_test_results:
            try:
                self._save_settings()
            except Exception as exc:
                self._warn("过期扫描状态清理保存失败: {}".format(exc))
        for identity, cached in old_file_cache.items():
            if identity not in new_file_cache and self._scan_failure_covers_identity(identity):
                new_file_cache[identity] = cached
        try:
            self._save_scan_cache(new_file_cache)
        except Exception as exc:
            self._warn("增量扫描缓存保存失败: {}".format(exc))

    def _mark_scan_incomplete(self, source_type, path):
        source_type = str(source_type or "").upper()
        normalized = os.path.realpath(os.path.abspath(os.path.expanduser(str(path))))
        marker = (source_type, normalized)
        if marker not in self.incomplete_scan_roots:
            self.incomplete_scan_roots.append(marker)

    def _reference_path(self, reference):
        value = str(reference or "").strip()
        if not value.lower().startswith("file://"):
            return ""
        path = value[7:]
        if not os.path.isabs(path):
            path = os.path.join(self.STORAGE_ROOT, path)
        return os.path.realpath(os.path.abspath(os.path.expanduser(path)))

    def _identity_source_path(self, identity):
        parts = str(identity or "").split("|", 1)
        reference = parts[1].split("#bundle-site-", 1)[0] if len(parts) == 2 else ""
        return self._reference_path(reference) if reference else ""

    def _path_is_within(self, path, parent):
        if not path or not parent:
            return False
        try:
            return os.path.commonpath((path, parent)) == parent
        except Exception:
            return False

    def _scan_failure_covers_identity(self, identity):
        source_type = str(identity or "").split("|", 1)[0].upper()
        if source_type in self.incomplete_scan_types:
            return True
        path = self._identity_source_path(identity)
        return any(
            item_type == source_type and self._path_is_within(path, failed_path)
            for item_type, failed_path in self.incomplete_scan_roots
        )

    def _source_identity(self, source_type, path):
        return source_type + "|" + self._file_url(path)

    def _bundle_source_identity(self, source_type, bundle_path, site):
        identity = {
            "key": str(site.get("key", "")),
            "name": str(site.get("name", "")),
            "api": site.get("api", ""),
            "ext": site.get("ext", ""),
            "jar": site.get("jar", ""),
            "homePage": site.get("homePage", site.get("home_page", "")),
        }
        raw = json.dumps(
            identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return "{}|{}#bundle-site-{}".format(
            source_type,
            self._file_url(bundle_path),
            self._digest(raw, 20),
        )

    def _live_fingerprint(self, live):
        """生成直播去重指纹。

        除识别完全相同的 url / api 外，还要能识别「同一站点源」因同时打包了
        本地版(index.json)与远程镜像版(origin.json)而重复收录的直播：
        同一直播源会出现 jar/url 分别为 file:// 本地前缀与 https:// 远程前缀
        的两条记录，二者 url 不同但指向同一逻辑直播文件。为避免这类重复，
        指纹统一按【宿主站名 + 逻辑直播名 + url/api 的 basename】归一化，
        使本地打包版与远程镜像版判定为同一个逻辑直播源（保留先出现的）。
        """
        if not isinstance(live, dict):
            return ""

        name = str(live.get("name", "")).strip()
        host_match = re.match(r"^【([^】]*)】", name)
        # 宿主站名：用于区分不同站点源的同类直播，避免跨站同名被误合并。
        host = (host_match.group(1).strip() if host_match else "_").casefold() or "_"
        logic_name = (
            re.sub(r"^【[^】]*】\s*", "", name).strip() or name
        ).casefold()

        def _basename(value):
            value = str(value or "").strip()
            try:
                path = urllib.parse.urlsplit(value).path
            except Exception:
                path = ""
            if not value or path in ("", "/"):
                return ""
            return path.rstrip("/").split("/")[-1]

        url = str(live.get("url", "")).strip()
        api = str(live.get("api", "")).strip()
        if url or api:
            url_base = _basename(url).casefold()
            jar_base = _basename(live.get("jar", "")).casefold()
            if api:
                # api 型直播（如 type=3 咖啡体育）：宿主+逻辑名+api 即可唯一，
                # jar 用 basename 归一，避免本地/远程 jar 前缀差异导致重复。
                key = (host, logic_name, api.casefold(), jar_base)
            else:
                # url 型直播：宿主+逻辑名+url basename 归一，
                # file://…/iptv.m3u 与 https://…/iptv.m3u 视为同一逻辑直播源。
                key = (host, logic_name, url_base)
            return "live_normalized|" + json.dumps(
                key, ensure_ascii=False
            )

        # 无 url / api，仅按 groups 判重，同时保留宿主与逻辑名防止跨站误并。
        data = {
            "host": host,
            "name": logic_name,
            "groups": live.get("groups", []),
        }
        return "live_groups|" + json.dumps(
            data, ensure_ascii=False, sort_keys=True
        )

    def _bundle_live_identity(self, bundle_path, live):
        return "LIVE|{}#bundle-live-{}".format(
            self._file_url(bundle_path),
            self._digest(self._live_fingerprint(live), 20),
        )

    def _bundle_package_label(self, scan_root, bundle_path):
        installed_label = self._installed_package_label(scan_root, bundle_path)
        if installed_label:
            return installed_label
        root = os.path.realpath(os.path.abspath(os.path.expanduser(str(scan_root))))
        path = os.path.realpath(os.path.abspath(os.path.expanduser(str(bundle_path))))
        try:
            relative = os.path.relpath(path, root)
        except Exception:
            relative = os.path.basename(path)
        parts = [part for part in relative.split(os.sep) if part not in ("", ".", "..")]
        if len(parts) > 1:
            label = parts[0]
        else:
            root_name = os.path.basename(root.rstrip(os.sep))
            generic_roots = {
                "csp", "js", "javascript", "py", "python", "html",
            }
            label = (
                os.path.splitext(os.path.basename(path))[0]
                if root_name.lower() in generic_roots
                else root_name
            )
        label = re.sub(r"[\r\n\t【】]+", " ", str(label)).strip()
        return label[:32] or os.path.splitext(os.path.basename(path))[0][:32] or "本地包"

    def _has_raw_lives(self, path):
        """判断一个 JSON 文件的根对象是否含非空 lives 集合。

        用于「独立本地直播」识别：未归档为下载站点整包的 .json，
        只要根字典的 lives 是一个非空 list/dict，就视为本地直播集合文件。
        """
        try:
            data = self._load_json_compatible(path)
        except Exception:
            return False
        if not isinstance(data, dict):
            return False
        raw_lives = data.get("lives")
        return isinstance(raw_lives, (list, dict)) and bool(raw_lives)

    def _standalone_live_label(self, scan_root, source_path):
        """为独立本地直播文件生成来源标签。

        返回一个可读短标签（优先取 JSON 所在目录名，其次取文件名主体），
        用于给独立直播名加「【标签】直播名」前缀，便于与整包直播区分，
        也作为 live_sources 中 package_name 字段的回退值。
        """
        root = os.path.realpath(os.path.abspath(os.path.expanduser(str(scan_root))))
        path = os.path.realpath(os.path.abspath(os.path.expanduser(str(source_path))))
        try:
            relative = os.path.relpath(path, root)
        except Exception:
            relative = os.path.basename(path)
        parts = [part for part in relative.split(os.sep) if part not in ("", ".", "..")]
        name = os.path.splitext(os.path.basename(path))[0]
        if len(parts) >= 2:
            label = parts[-2]
        else:
            label = name
        label = re.sub(r"[\r\n\t【】]+", " ", str(label)).strip()
        return label[:32] or name[:32] or "本地直播"

    def _installed_package_marker(self, scan_root, source_path):
        root = os.path.realpath(os.path.abspath(os.path.expanduser(str(scan_root))))
        path = os.path.realpath(os.path.abspath(os.path.expanduser(str(source_path))))
        try:
            relative = os.path.relpath(path, root)
        except Exception:
            return {}
        parts = [part for part in relative.split(os.sep) if part not in ("", ".", "..")]
        if len(parts) < 2:
            return {}
        package_root = os.path.join(root, parts[0])
        marker = self._read_package_install_marker(package_root)
        return marker if isinstance(marker, dict) else {}

    def _installed_package_label(self, scan_root, source_path):
        marker = self._installed_package_marker(scan_root, source_path)
        label = str(marker.get("name", "")).strip()
        if not label:
            return ""
        label = re.sub(r"[\r\n\t【】]+", " ", label).strip()
        return label[:32]

    def _site_enabled_package_download_site_ids(self):
        return {
            str(item.get("id", "")).strip()
            for item in self.package_download_sites
            if self._package_download_site_enabled(item)
            and str(item.get("id", "")).strip()
        }

    def _live_enabled_package_download_site_ids(self):
        return {
            str(item.get("id", "")).strip()
            for item in self.package_download_sites
            if self._package_download_live_enabled(item)
            and str(item.get("id", "")).strip()
        }

    def _package_download_state_signature(self):
        values = sorted(
            "{}:s{}:l{}".format(
                str(item.get("id", "")).strip(),
                "1" if self._package_download_site_enabled(item) else "0",
                "1" if self._package_download_live_enabled(item) else "0",
            )
            for item in self.package_download_sites
            if str(item.get("id", "")).strip()
        )
        return self._digest("\n".join(values), 24)

    def _strip_json_comments(self, text):
        result = []
        index = 0
        in_string = False
        escaped = False
        length = len(text)
        while index < length:
            char = text[index]
            if in_string:
                result.append(char)
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                index += 1
                continue
            if char == '"':
                in_string = True
                result.append(char)
                index += 1
                continue
            if char == "/" and index + 1 < length:
                marker = text[index + 1]
                if marker == "/":
                    index += 2
                    while index < length and text[index] not in "\r\n":
                        index += 1
                    continue
                if marker == "*":
                    index += 2
                    while index + 1 < length and text[index : index + 2] != "*/":
                        if text[index] in "\r\n":
                            result.append(text[index])
                        index += 1
                    index = min(length, index + 2)
                    continue
            result.append(char)
            index += 1
        return "".join(result)

    def _strip_json_trailing_commas(self, text):
        result = []
        index = 0
        in_string = False
        escaped = False
        length = len(text)
        while index < length:
            char = text[index]
            if in_string:
                result.append(char)
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                index += 1
                continue
            if char == '"':
                in_string = True
                result.append(char)
                index += 1
                continue
            if char == ",":
                lookahead = index + 1
                while lookahead < length and text[lookahead].isspace():
                    lookahead += 1
                if lookahead < length and text[lookahead] in "}]":
                    index += 1
                    continue
            result.append(char)
            index += 1
        return "".join(result)

    def _load_json_compatible(self, path):
        try:
            with open(path, "r", encoding="utf-8-sig") as fp:
                text = fp.read()
        except Exception as exc:
            raise ValueError("读取文件失败: {} ({})".format(path, exc))
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            try:
                cleaned = self._strip_json_trailing_commas(
                    self._strip_json_comments(text)
                )
                return json.loads(cleaned)
            except Exception as exc:
                raise ValueError("JSON 解析失败: {} ({})".format(path, exc))

    def _local_file_looks_json(self, path):
        try:
            with open(path, "rb") as fp:
                prefix = fp.read(4096)
            text = prefix.decode("utf-8-sig", errors="replace").lstrip()
            return text.startswith(("{", "["))
        except Exception:
            return False

    def _parse_site_bundle(
        self, path, include_sites=True, include_lives=True,
        include_context=True,
    ):
        try:
            data = self._load_json_compatible(path)
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        raw_sites = data.get("sites", [])
        if isinstance(raw_sites, dict):
            raw_sites = [raw_sites]
        if not isinstance(raw_sites, list):
            raw_sites = []
        raw_lives_value = data.get("lives", [])
        if not raw_sites and (
            "lives" not in data
            or not isinstance(raw_lives_value, (list, dict))
        ):
            return None
        data["sites"] = raw_sites

        default_jar = data.get("spider", "")
        accepted = []
        rejected = []
        for index, raw_site in enumerate(
            data["sites"] if include_sites else []
        ):
            raw_name = "站点 #{}".format(index + 1)
            if isinstance(raw_site, dict):
                raw_name = str(
                    raw_site.get("name")
                    or raw_site.get("key")
                    or raw_name
                ).strip()
            try:
                site, dependencies, validation = self._normalize_bundle_site(
                    path, raw_site, default_jar, index
                )
                accepted.append(
                    {
                        "index": index,
                        "site": site,
                        "dependencies": dependencies,
                        "validation": validation,
                    }
                )
            except Exception as exc:
                rejected.append({"index": index, "name": raw_name, "reason": str(exc)})
        accepted_lives = []
        rejected_lives = []
        raw_lives = data.get("lives", [])
        if isinstance(raw_lives, dict):
            raw_lives = [raw_lives]
        if not isinstance(raw_lives, list):
            raw_lives = []
        raw_lives = [
            item for item in raw_lives if not isinstance(item, dict) or bool(item)
        ]
        for index, raw_live in enumerate(raw_lives if include_lives else []):
            raw_name = "直播 #{}".format(index + 1)
            if isinstance(raw_live, dict):
                raw_name = str(raw_live.get("name") or raw_name).strip()
            try:
                live, dependencies = self._normalize_bundle_live(
                    path, raw_live, default_jar, index
                )
                accepted_lives.append(
                    {
                        "index": index,
                        "live": live,
                        "dependencies": dependencies,
                    }
                )
            except Exception as exc:
                rejected_lives.append(
                    {"index": index, "name": raw_name, "reason": str(exc)}
                )
        root_context = {}
        root_context_dependencies = []
        rejected_context = []
        for field in self.PACKAGE_ROOT_CONTEXT_FIELDS:
            if not include_context:
                break
            if field not in data:
                continue
            value = data.get(field)
            if value in (None, "", [], {}):
                continue
            dependencies = []
            try:
                normalized = self._normalize_bundle_nested_refs(
                    path, copy.deepcopy(value), field, dependencies
                )
                root_context[field] = normalized
                root_context_dependencies.extend(dependencies)
            except Exception as exc:
                rejected_context.append(
                    {"field": field, "reason": str(exc)}
                )
        return {
            "total": len(data["sites"]),
            "sites": accepted,
            "rejected": rejected,
            "live_total": len(raw_lives),
            "lives": accepted_lives,
            "live_rejected": rejected_lives,
            "root_context": root_context,
            "root_context_dependencies": list(
                dict.fromkeys(root_context_dependencies)
            ),
            "root_context_rejected": rejected_context,
        }

    def _normalize_bundle_live(self, bundle_path, raw_live, default_jar, index):
        if not isinstance(raw_live, dict):
            raise ValueError("直播配置必须是 JSON 对象")
        live = copy.deepcopy(raw_live)
        name = str(live.get("name", "")).strip()
        if not name:
            raise ValueError("直播配置缺少 name")
        live["name"] = name
        dependencies = []

        for field in ("url", "api", "ext", "logo", "epg"):
            value = live.get(field, "")
            if not isinstance(value, str) or not value.strip():
                continue
            reference = self._resolve_bundle_reference(
                bundle_path, value, field
            )
            path = self._require_local_dependency(reference, field)
            if path:
                if field == "api" and path.lower().endswith((".py", ".js")):
                    source_type = "PY" if path.lower().endswith(".py") else "JS"
                    valid, detail = self._validate_source(source_type, path)
                    if not valid:
                        raise ValueError(detail)
                if (
                    field == "ext"
                    and path.lower().endswith((".json", ".jsonc"))
                    and self._local_file_looks_json(path)
                ):
                    self._load_json_compatible(path)
                dependencies.append(path)
            live[field] = reference

        jar_value = live.get("jar", "") or default_jar
        if jar_value:
            if not isinstance(jar_value, str):
                raise ValueError("直播 jar 必须是路径或 URL")
            jar_reference = self._resolve_bundle_reference(
                bundle_path, jar_value, "jar", with_md5=True
            )
            jar_path = self._require_local_dependency(
                jar_reference, "直播 jar", with_md5=True
            )
            if jar_path:
                actual_md5 = self._inspect_local_jar(jar_path)["md5"]
                jar_reference = (
                    jar_reference.split(";md5;", 1)[0].strip()
                    + ";md5;"
                    + actual_md5
                )
                dependencies.append(jar_path)
            live["jar"] = jar_reference

        has_groups = isinstance(live.get("groups"), list) and bool(
            live.get("groups")
        )
        if not str(live.get("url", "")).strip() and not str(
            live.get("api", "")
        ).strip() and not has_groups:
            raise ValueError("直播配置缺少 url、api 或 groups")
        return live, list(dict.fromkeys(dependencies))

    def _looks_like_bundle_local_reference(self, bundle_path, value, field):
        source = str(value or "").strip().split(";md5;", 1)[0].strip()
        if not source or source.startswith(("{", "[")):
            return False
        field_key = str(field or "").strip().lower()
        local_reference_fields = {
            "api", "ext", "jar", "homepage", "home_page", "filters", "filter",
            "class", "classes", "type", "config", "configs", "file", "path",
            "script", "source", "url", "logo", "epg",
        }
        if field == "api" and source.startswith("csp_"):
            return False
        scheme = urllib.parse.urlsplit(source).scheme.lower()
        if scheme in ("http", "https", "assets", "proxy"):
            return False
        if scheme in ("file", "clan"):
            return True
        if scheme:
            return False
        if source.startswith(("./", "../")):
            return True
        if os.path.isabs(source):
            storage_root = os.path.realpath(os.path.abspath(self.STORAGE_ROOT))
            real_source = os.path.realpath(os.path.abspath(source))
            local_prefixes = ("/storage/", "/sdcard/", "/data/")
            if (
                os.path.exists(source)
                or real_source == storage_root
                or real_source.startswith(storage_root + os.sep)
                or source.startswith(local_prefixes)
            ):
                return True
        sibling = os.path.join(os.path.dirname(bundle_path), source)
        if os.path.exists(sibling):
            return True
        extension = os.path.splitext(source.lower())[1]
        local_extensions = {
            ".json", ".jsonc", ".jar", ".py", ".js", ".html", ".htm",
            ".txt", ".m3u", ".m3u8",
        }
        if field == "jar":
            return True
        return extension in local_extensions and field_key in local_reference_fields

    def _resolve_bundle_reference(self, bundle_path, value, field, with_md5=False):
        source = str(value or "").strip()
        suffix = ""
        if with_md5 and ";md5;" in source:
            source, digest = source.split(";md5;", 1)
            source = source.strip()
            suffix = ";md5;" + digest.strip().lower()
        parsed = urllib.parse.urlsplit(source)
        if parsed.scheme.lower() == "clan" and parsed.hostname in (
            "localhost", "127.0.0.1"
        ):
            local_path = os.path.join(self.STORAGE_ROOT, parsed.path.lstrip("/"))
            return self._file_url(local_path) + suffix
        if not self._looks_like_bundle_local_reference(
            bundle_path, source, field
        ):
            return source + suffix
        return self._resolve_site_reference(
            bundle_path, source + suffix, with_md5=with_md5
        )

    def _require_local_dependency(self, reference, label, with_md5=False):
        path = self._site_reference_path(reference, with_md5=with_md5)
        if not path:
            return ""
        if not os.path.isfile(path) or not os.access(path, os.R_OK):
            raise ValueError("{} 不存在或不可读: {}".format(label, reference))
        if os.path.getsize(path) <= 0:
            raise ValueError("{} 是空文件: {}".format(label, reference))
        return path

    def _normalize_bundle_nested_refs(
        self, bundle_path, value, field, dependencies
    ):
        if isinstance(value, dict):
            return {
                key: self._normalize_bundle_nested_refs(
                    bundle_path, item, str(key), dependencies
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                self._normalize_bundle_nested_refs(
                    bundle_path, item, field, dependencies
                )
                for item in value
            ]
        if not isinstance(value, str) or not self._looks_like_bundle_local_reference(
            bundle_path, value, field
        ):
            return value
        with_md5 = field in ("jar", "spider")
        reference = self._resolve_bundle_reference(
            bundle_path, value, field, with_md5=with_md5
        )
        path = self._require_local_dependency(
            reference, field or "嵌套依赖", with_md5=with_md5
        )
        if path:
            if (
                path.lower().endswith((".json", ".jsonc"))
                and self._local_file_looks_json(path)
            ):
                self._load_json_compatible(path)
            dependencies.append(path)
        return reference

    def _normalize_bundle_site(self, bundle_path, raw_site, default_jar, index):
        if not isinstance(raw_site, dict):
            raise ValueError("站点必须是 JSON 对象")
        site = copy.deepcopy(raw_site)
        raw_home_page = site.get("homePage", site.get("home_page", ""))
        is_webhome = isinstance(raw_home_page, str) and bool(raw_home_page.strip())
        api = self._runtime_reference(self.html_api) if is_webhome else str(
            site.get("api", "")
        ).strip()
        if not api:
            raise ValueError("缺少 api")

        dependencies = []
        validation = []
        api_is_local = self._looks_like_bundle_local_reference(
            bundle_path, api, "api"
        )
        if api_is_local:
            api = self._resolve_bundle_reference(bundle_path, api, "api")
            api_path = self._require_local_dependency(api, "api")
            lower_api = api_path.lower()
            if lower_api.endswith(".py"):
                valid, detail = self._validate_source("PY", api_path)
            elif lower_api.endswith(".js"):
                valid, detail = self._validate_source("JS", api_path)
            else:
                valid, detail = True, ""
            if not valid:
                raise ValueError(detail)
            dependencies.append(api_path)
            if detail:
                validation.append(detail)
            site["api"] = api
        else:
            scheme = urllib.parse.urlsplit(api).scheme.lower()
            if not api.startswith("csp_") and scheme not in (
                "http", "https", "assets", "proxy"
            ):
                raise ValueError("api 类型无法确认: {}".format(api))
            site["api"] = api

        home_page = raw_home_page
        if isinstance(home_page, str) and home_page.strip():
            resolved_home = self._resolve_bundle_reference(
                bundle_path, home_page, "homePage"
            )
            home_path = self._require_local_dependency(resolved_home, "homePage")
            if home_path:
                dependencies.append(home_path)
            site["homePage"] = resolved_home
            site["api"] = api
            site.pop("home_page", None)
        elif home_page not in (None, ""):
            raise ValueError("homePage 必须是路径或 URL")

        ext = "" if is_webhome else site.get("ext", "")
        if isinstance(ext, str) and ext.strip():
            resolved_ext = self._resolve_bundle_reference(bundle_path, ext, "ext")
            ext_path = self._require_local_dependency(resolved_ext, "ext")
            if ext_path:
                if (
                    ext_path.lower().endswith((".json", ".jsonc"))
                    and self._local_file_looks_json(ext_path)
                ):
                    self._load_json_compatible(ext_path)
                dependencies.append(ext_path)
            site["ext"] = resolved_ext
        elif isinstance(ext, (dict, list)):
            site["ext"] = self._normalize_bundle_nested_refs(
                bundle_path, ext, "ext", dependencies
            )
        elif ext not in (None, "") and not isinstance(ext, (dict, list)):
            raise ValueError("ext 必须是路径、URL 或 JSON 对象")

        if is_webhome:
            site.pop("ext", None)
        jar_value = "" if is_webhome else site.get("jar", "")
        if (
            not is_webhome
            and not str(jar_value or "").strip()
            and api.startswith("csp_")
        ):
            jar_value = default_jar
        if jar_value:
            if not isinstance(jar_value, str):
                raise ValueError("jar 必须是路径或 URL")
            resolved_jar = self._resolve_bundle_reference(
                bundle_path, jar_value, "jar", with_md5=True
            )
            jar_detail = self._validate_site_jar(resolved_jar, api)
            jar_path = self._require_local_dependency(
                resolved_jar, "jar", with_md5=True
            )
            if jar_path:
                actual_md5 = self._inspect_local_jar(jar_path)["md5"]
                resolved_jar = (
                    resolved_jar.split(";md5;", 1)[0].strip()
                    + ";md5;"
                    + actual_md5
                )
                dependencies.append(jar_path)
            site["jar"] = resolved_jar
            if jar_detail:
                validation.append(jar_detail)
        elif api.startswith("csp_") and not str(site.get("homePage", "")).strip():
            raise ValueError("{} 缺少可验证的 jar".format(api))
        else:
            site.pop("jar", None)

        name = str(site.get("name") or site.get("key") or api).strip()
        if not name:
            name = "站点 #{}".format(index + 1)
        site["name"] = name
        site["type"] = int(site.get("type", 3))
        site.setdefault("searchable", 0 if is_webhome else self.DEFAULT_SEARCHABLE)
        site.setdefault("quickSearch", 0 if is_webhome else self.DEFAULT_QUICK_SEARCH)
        dependencies = list(dict.fromkeys(dependencies))
        return site, dependencies, "；".join(validation) or "整包站点本地依赖完整"

    def _manifest_owned_source_paths(self, root, source_type):
        source_type = str(source_type or "").upper()
        if source_type not in ("JS", "CSP") or not os.path.isdir(root):
            return set()
        fields = ("api", "ext") if source_type == "JS" else ("ext",)
        result = set()
        try:
            for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
                relative_dir = os.path.relpath(current, root)
                depth = 0 if relative_dir == "." else relative_dir.count(os.sep) + 1
                dirs[:] = [
                    name
                    for name in dirs
                    if not name.startswith(".")
                    and name.lower() not in self.SKIP_DIRS
                    and not os.path.islink(os.path.join(current, name))
                ]
                if depth >= self.max_scan_depth:
                    dirs[:] = []
                for name in files:
                    if not self._is_site_manifest_name(name):
                        continue
                    path = os.path.join(current, name)
                    if os.path.islink(path) or not os.path.isfile(path):
                        continue
                    try:
                        data = self._load_json_compatible(path)
                        if isinstance(data, dict) and isinstance(data.get("site"), dict) and not data.get("api"):
                            data = data["site"]
                        if not isinstance(data, dict):
                            continue
                        for field in fields:
                            reference = data.get(field, "")
                            if not isinstance(reference, str) or not reference.strip():
                                continue
                            resolved = self._resolve_site_reference(path, reference)
                            dependency = self._site_reference_path(resolved)
                            if dependency:
                                result.add(dependency)
                    except Exception:
                        continue
        except Exception:
            return result
        return result

    def _bundle_owned_source_paths(self, root, source_type):
        source_type = str(source_type or "").upper()
        if source_type not in ("CSP",) or not os.path.isdir(root):
            return set()
        result = set()

        def collect(bundle_path, value, field=""):
            if isinstance(value, dict):
                for key, item in value.items():
                    collect(bundle_path, item, str(key))
            elif isinstance(value, list):
                for item in value:
                    collect(bundle_path, item, field)
            elif isinstance(value, str) and self._looks_like_bundle_local_reference(
                bundle_path, value, field
            ):
                reference = self._resolve_bundle_reference(
                    bundle_path, value, field, with_md5=field == "jar"
                )
                dependency = self._site_reference_path(
                    reference, with_md5=field == "jar"
                )
                if dependency:
                    result.add(dependency)

        try:
            for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
                relative_dir = os.path.relpath(current, root)
                depth = 0 if relative_dir == "." else relative_dir.count(os.sep) + 1
                dirs[:] = [
                    name
                    for name in dirs
                    if not name.startswith(".")
                    and name.lower() not in self.SKIP_DIRS
                    and not os.path.islink(os.path.join(current, name))
                ]
                if depth >= self.max_scan_depth:
                    dirs[:] = []
                for name in files:
                    if not name.lower().endswith((".json", ".jsonc")):
                        continue
                    path = os.path.join(current, name)
                    if os.path.islink(path) or not os.path.isfile(path):
                        continue
                    try:
                        if os.path.getsize(path) > self.max_source_size:
                            continue
                        data = self._load_json_compatible(path)
                        if not isinstance(data, dict) or not isinstance(
                            data.get("sites"), list
                        ):
                            continue
                        collect(path, data.get("spider", ""), "jar")
                        collect(path, data["sites"])
                        collect(path, data.get("lives", []))
                        for field in self.PACKAGE_ROOT_CONTEXT_FIELDS:
                            if field in data:
                                collect(path, data[field], field)
                    except Exception:
                        continue
        except Exception:
            return result
        return result

    def _discover_json_jar_pairs(self, root, manifest_owned_paths):
        pairs = {}
        ambiguous = set()
        owned = set(manifest_owned_paths or ())
        try:
            for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
                relative_dir = os.path.relpath(current, root)
                depth = 0 if relative_dir == "." else relative_dir.count(os.sep) + 1
                dirs[:] = [
                    name
                    for name in dirs
                    if not name.startswith(".")
                    and name.lower() not in self.SKIP_DIRS
                    and not os.path.islink(os.path.join(current, name))
                ]
                if depth >= self.max_scan_depth:
                    dirs[:] = []
                jars = []
                rules = []
                for name in files:
                    path = os.path.join(current, name)
                    if os.path.islink(path) or not os.path.isfile(path):
                        continue
                    lower_name = name.lower()
                    real_path = os.path.realpath(path)
                    if lower_name.endswith(".jar"):
                        jars.append(real_path)
                    elif (
                        lower_name.endswith(".json")
                        and not self._is_site_manifest_name(lower_name)
                        and real_path not in owned
                    ):
                        rules.append(real_path)
                if not jars or not rules:
                    continue
                if len(jars) == 1:
                    for rule in rules:
                        pairs[rule] = jars[0]
                    continue
                jars_by_stem = {}
                for jar in jars:
                    stem = os.path.splitext(os.path.basename(jar))[0].lower()
                    jars_by_stem.setdefault(stem, []).append(jar)
                for rule in rules:
                    stem = os.path.splitext(os.path.basename(rule))[0].lower()
                    matches = jars_by_stem.get(stem, [])
                    if len(matches) == 1:
                        pairs[rule] = matches[0]
                    else:
                        ambiguous.add(rule)
        except Exception as exc:
            self._warn("JSON/JAR 配对扫描失败: {} ({})".format(root, exc))
        return pairs, ambiguous

    def _is_site_manifest_name(self, lower_name):
        value = str(lower_name or "").lower()
        return value == "site.json" or value.endswith(".site.json")

    def _adult_text_matches(self, value):
        text = str(value or "")
        lower = text.casefold()
        if any(symbol in text for symbol in self.ADULT_SYMBOLS):
            return True
        if any(keyword.casefold() in lower for keyword in self.ADULT_KEYWORDS):
            return True
        if self.ADULT_LATIN_PATTERN.search(text):
            return True
        if re.search(r"(?:^|[^0-9a-z])(?:adult|nsfw|xxx)(?:$|[^0-9a-z])", lower):
            return True
        if re.search(r"(?:^|[^0-9a-z])18(?:\+|xxx|av|j|禁)(?:$|[^0-9a-z])", lower):
            return True
        if re.search(r"(?:^|[^0-9a-z])av(?:$|[^0-9a-z])", lower):
            return True
        for token in re.findall(r"[a-z0-9]+", lower):
            if token.startswith("jav") and not token.startswith(
                ("java", "javascript")
            ):
                return True
        return False

    def _adult_content_matches(self, value):
        text = str(value or "")
        lower = text.casefold()
        if any(symbol in text for symbol in self.ADULT_SYMBOLS):
            return True
        strong_latin = bool(self.ADULT_LATIN_PATTERN.search(text))
        if re.search(r"(?:^|[^0-9a-z])18(?:\+|xxx|av|j|禁)(?:$|[^0-9a-z])", lower):
            return True
        keyword_hits = {
            keyword.casefold()
            for keyword in self.ADULT_KEYWORDS
            if keyword.casefold() in lower
        }
        weak_latin = bool(
            re.search(
                r"(?:^|[^0-9a-z])(?:adult|nsfw|xxx|av)(?:$|[^0-9a-z])",
                lower,
            )
        )
        return strong_latin or len(keyword_hits) + int(weak_latin) >= 2

    def _is_adult_source(self, source):
        site = source.get("csp_site", {})
        if isinstance(site, dict):
            for key in ("adult", "isAdult", "is_adult", "nsfw", "restricted18"):
                if key in site:
                    return self._as_bool(site.get(key), False)
            site_text = json.dumps(
                site, ensure_ascii=False, sort_keys=True, default=str
            )
            if self._adult_text_matches(site_text):
                return True

        values = [
            source.get("base_name", ""),
            os.path.basename(str(source.get("path", ""))),
        ]
        if not source.get("csp_site"):
            values.append(source.get("relative_in_root", ""))
        if any(self._adult_text_matches(value) for value in values):
            return True

        paths = list(source.get("dependencies", []))
        if not source.get("csp_site"):
            paths.append(source.get("path", ""))
        seen = set()
        for path in paths:
            real_path = os.path.realpath(str(path or ""))
            if not real_path or real_path in seen or not os.path.isfile(real_path):
                continue
            seen.add(real_path)
            if not real_path.lower().endswith(
                (".json", ".jsonc", ".py", ".js", ".html", ".htm", ".txt")
            ):
                continue
            try:
                text = self._read_text(real_path, 256 * 1024)
            except Exception:
                continue
            if "@tvbox-safe" in text.casefold():
                continue
            if "@tvbox-adult" in text.casefold() or self._adult_content_matches(text):
                return True
        return False

    def _is_excluded(self, source_type, lower_name, relative_in_root):
        relative_lower = relative_in_root.lower()
        if lower_name.startswith("."):
            return True
        if (
            source_type == "JS"
            and lower_name.endswith(".json")
            and not self._is_site_manifest_name(lower_name)
        ):
            return True
        if source_type == "JS" and lower_name in self.JS_EXCLUDE:
            return True
        if source_type == "PY":
            if lower_name == "__init__.py":
                return True
            if relative_lower in self.PY_EXCLUDE_RELATIVE:
                return True
        return False

    def _is_auto_loader_python(self, source_type, lower_name):
        return (
            source_type == "PY"
            and str(lower_name or "").startswith("自动加载")
            and str(lower_name or "").endswith(".py")
        )

    def _detect_file_role(self, source_type, lower_name, path):
        try:
            text = self._read_text(path, 64 * 1024)
        except Exception:
            text = ""
        lower_text = text.lower()

        if self._is_auto_loader_python(source_type, lower_name):
            return "source"
        if "@tvbox-ignore" in lower_text:
            return "ignore"
        role_match = re.search(r"@tvbox-role\s*(?:[:=]\s*)?([a-z_-]+)", lower_text)
        if role_match:
            role = role_match.group(1)
            if role in ("manager", "extension", "library", "ignore"):
                return role
            if role == "source":
                return "forced_source"
        if "@tvbox-source" in lower_text:
            return "forced_source"

        if source_type == "JS":
            if lower_name.endswith(self.JS_EXTENSION_SUFFIXES):
                return "extension"
            extension_signatures = (
                "window.fm",
                "fm.vodinline",
                "window.fongmibridge",
                "webhomeextensions",
                "gm_addstyle",
                "document-start",
                "fmsdk",
                "@match",
            )
            looks_like_extension = any(signature in lower_text for signature in extension_signatures)
            looks_like_rule = self._has_direct_js_spider(text)
            if looks_like_extension and not looks_like_rule:
                return "extension"
        return "source"

    def _resolve_site_reference(self, manifest_path, reference, with_md5=False):
        value = str(reference or "").strip()
        if not value:
            return ""
        suffix = ""
        source = value
        if with_md5 and ";md5;" in value:
            source, digest = value.split(";md5;", 1)
            source = source.strip()
            suffix = ";md5;" + digest.strip().lower()
        lower = source.lower()
        if lower.startswith(("http://", "https://", "assets://")):
            return source + suffix
        if lower.startswith("file://"):
            file_value = source[7:]
            if file_value.startswith(("./", "../")):
                path = os.path.join(os.path.dirname(manifest_path), file_value)
                return self._file_url(path) + suffix
            return source + suffix
        if os.path.isabs(source):
            return self._file_url(source) + suffix
        path = os.path.join(os.path.dirname(manifest_path), source)
        return self._file_url(path) + suffix

    def _site_reference_path(self, reference, with_md5=False):
        value = str(reference or "").strip()
        if with_md5:
            value = value.split(";md5;", 1)[0].strip()
        return self._reference_path(value)

    def _file_md5(self, path):
        digest = hashlib.md5()
        with open(path, "rb") as fp:
            while True:
                chunk = fp.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _dex_u32(self, data, offset):
        if offset < 0 or offset + 4 > len(data):
            raise ValueError("DEX 索引越界")
        return int.from_bytes(data[offset : offset + 4], "little")

    def _dex_uleb128(self, data, offset):
        value = 0
        for shift in range(0, 35, 7):
            if offset >= len(data):
                raise ValueError("DEX ULEB128 越界")
            byte = data[offset]
            offset += 1
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return value, offset
        raise ValueError("DEX ULEB128 格式无效")

    def _dex_defined_spider_classes(self, data):
        if len(data) < 0x70 or not data.startswith(b"dex\n"):
            raise ValueError("DEX 文件头无效")
        if self._dex_u32(data, 0x28) != 0x12345678:
            raise ValueError("DEX 字节序不受支持")
        string_ids_size = self._dex_u32(data, 0x38)
        string_ids_off = self._dex_u32(data, 0x3C)
        type_ids_size = self._dex_u32(data, 0x40)
        type_ids_off = self._dex_u32(data, 0x44)
        class_defs_size = self._dex_u32(data, 0x60)
        class_defs_off = self._dex_u32(data, 0x64)
        if string_ids_off + string_ids_size * 4 > len(data):
            raise ValueError("DEX string_ids 越界")
        if type_ids_off + type_ids_size * 4 > len(data):
            raise ValueError("DEX type_ids 越界")
        if class_defs_off + class_defs_size * 32 > len(data):
            raise ValueError("DEX class_defs 越界")

        result = set()
        prefix = b"Lcom/github/catvod/spider/"
        for index in range(class_defs_size):
            class_idx = self._dex_u32(data, class_defs_off + index * 32)
            if class_idx >= type_ids_size:
                raise ValueError("DEX class_idx 越界")
            descriptor_idx = self._dex_u32(
                data, type_ids_off + class_idx * 4
            )
            if descriptor_idx >= string_ids_size:
                raise ValueError("DEX descriptor_idx 越界")
            string_offset = self._dex_u32(
                data, string_ids_off + descriptor_idx * 4
            )
            _, value_offset = self._dex_uleb128(data, string_offset)
            end = data.find(b"\0", value_offset)
            if end < 0:
                raise ValueError("DEX 类描述符未终止")
            descriptor = data[value_offset:end]
            if descriptor.startswith(prefix) and descriptor.endswith(b";"):
                class_name = descriptor[len(prefix) : -1].decode(
                    "utf-8", errors="ignore"
                )
                if not class_name:
                    continue
                result.add(class_name.replace("/", "."))
        return result

    def _current_app_identity(self):
        if isinstance(self._app_identity_cache, tuple):
            return self._app_identity_cache
        package_name = ""
        app_label = ""
        try:
            from java import jclass

            context = None
            try:
                context = jclass(
                    "android.app.ActivityThread"
                ).currentApplication()
            except Exception:
                pass
            if context is None:
                try:
                    app_class = jclass("com.fongmi.android.tv.App")
                    for method_name in ("get", "getInstance", "instance"):
                        try:
                            method = getattr(app_class, method_name)
                            context = method() if callable(method) else method
                            if context is not None:
                                break
                        except Exception:
                            continue
                except Exception:
                    pass
            if context is not None:
                package_name = str(context.getPackageName()).strip()
                manager = context.getPackageManager()
                info = manager.getApplicationInfo(package_name, 0)
                app_label = str(manager.getApplicationLabel(info)).strip()
        except Exception:
            pass
        self._app_identity_cache = (package_name, app_label)
        return self._app_identity_cache

    def _decrypt_jar_guard_text(self, encoded, key_text):
        encrypted = base64.b64decode(encoded, validate=True)
        key = str(key_text).encode("utf-8")
        if len(key) not in (16, 24, 32) or not encrypted or len(encrypted) % 16:
            raise ValueError("AES 参数无效")
        try:
            from Crypto.Cipher import AES

            plain = AES.new(key, AES.MODE_CBC, key[:16]).decrypt(encrypted)
        except ImportError:
            from cryptography.hazmat.primitives.ciphers import (
                Cipher,
                algorithms,
                modes,
            )

            decryptor = Cipher(
                algorithms.AES(key), modes.CBC(key[:16])
            ).decryptor()
            plain = decryptor.update(encrypted) + decryptor.finalize()
        padding = plain[-1]
        if (
            padding < 1
            or padding > 16
            or plain[-padding:] != bytes([padding]) * padding
        ):
            raise ValueError("AES 填充无效")
        return plain[:-padding].decode("utf-8")

    def _inspect_dex_runtime_guard(self, dex_blobs):
        data = b"".join(dex_blobs)
        requires_spider_api = (
            b"Lcom/github/catvod/crawler/SpiderApi;" in data
            and b"initApi" in data
        )
        guard_markers = (
            b"getApplicationLabel" in data
            and b"getPackageName" in data
            and b"killProcess" in data
        )
        if not guard_markers:
            return {
                "forced_exit": False,
                "packages": set(),
                "labels": set(),
                "requires_spider_api": requires_spider_api,
            }

        decrypted = []
        key_text = "1234123412341234"
        if key_text.encode("ascii") in data:
            candidates = set(
                re.findall(rb"[A-Za-z0-9+/=]{32,4096}", data)
            )
            for candidate in candidates:
                if len(candidate) % 4:
                    continue
                try:
                    text = self._decrypt_jar_guard_text(candidate, key_text)
                    if text and all(
                        char in "\r\n\t" or ord(char) >= 32 for char in text
                    ):
                        decrypted.append(text)
                except Exception:
                    continue

        packages = set()
        labels = set()
        for text in decrypted:
            values = {
                item.strip()
                for item in text.split(",")
                if item.strip()
            }
            if len(values) < 2:
                continue
            if any("." in item and not any(ch.isspace() for ch in item) for item in values):
                packages.update(values)
            elif any(
                marker in values
                for marker in ("OK影视", "OK影视Pro", "TVBox", "影视仓")
            ):
                labels.update(values)
        exit_message = "⚠️加载失败，软件即将退出。"
        return {
            "forced_exit": exit_message in decrypted,
            "packages": packages,
            "labels": labels,
            "requires_spider_api": requires_spider_api,
        }

    def _jar_runtime_compatibility(self, inspection, api=""):
        guard = inspection.get("runtime_guard", {})
        if not isinstance(guard, dict):
            return True, ""
        if guard.get("forced_exit"):
            package_name, app_label = self._current_app_identity()
            packages = set(guard.get("packages", set()))
            labels = set(guard.get("labels", set()))
            if (
                package_name
                and app_label
                and package_name in packages
                and labels
                and app_label not in labels
            ):
                self.status["compatibility_blocked"] += 1
                return False, (
                    "JAR 内置应用名称校验不接受“{}”，运行后会主动结束 {}，"
                    "已阻止加载"
                ).format(app_label, self._app_mode_label())
        return True, ""

    def _inspect_local_jar(self, path):
        real_path = os.path.realpath(os.path.abspath(path))
        stat = os.stat(real_path)
        cache_key = (
            real_path,
            int(stat.st_size),
            int(
                getattr(
                    stat,
                    "st_mtime_ns",
                    int(stat.st_mtime * 1000000000),
                )
            ),
        )
        cached = self._jar_inspection_cache.get(cache_key)
        if isinstance(cached, dict):
            return cached
        if not zipfile.is_zipfile(real_path):
            raise ValueError("JAR 不是有效 ZIP: {}".format(real_path))
        with zipfile.ZipFile(real_path, "r") as archive:
            dex_entries = sorted(
                name
                for name in archive.namelist()
                if re.fullmatch(r"classes(?:[2-9][0-9]*)?\.dex", name)
            )
            if "classes.dex" not in dex_entries:
                raise ValueError("JAR 缺少 classes.dex: {}".format(real_path))
            remaining = self.MAX_JAR_DEX_SCAN_SIZE
            class_names = set()
            direct_classes = set()
            class_scan_complete = True
            dex_blobs = []
            for entry in dex_entries:
                info = archive.getinfo(entry)
                if remaining <= 0:
                    class_scan_complete = False
                    break
                read_limit = min(int(info.file_size), remaining)
                with archive.open(entry, "r") as dex_stream:
                    dex_data = dex_stream.read(read_limit + 1)
                if not dex_data.startswith(b"dex\n"):
                    raise ValueError(
                        "JAR 的 {} 格式无效: {}".format(entry, real_path)
                    )
                scanned = dex_data[:read_limit]
                remaining -= len(scanned)
                entry_complete = (
                    int(info.file_size) <= read_limit
                    and len(dex_data) <= read_limit
                )
                if not entry_complete:
                    class_scan_complete = False
                    continue
                dex_blobs.append(scanned)
                for class_name in self._dex_defined_spider_classes(scanned):
                    class_names.add(class_name)
                    if "." not in class_name and "$" not in class_name:
                        direct_classes.add(class_name)
        result = {
            "md5": self._file_md5(real_path),
            "classes": class_names,
            "direct_classes": direct_classes,
            "dex_entries": dex_entries,
            "class_scan_complete": class_scan_complete,
            "runtime_guard": self._inspect_dex_runtime_guard(dex_blobs),
        }
        self._jar_inspection_cache[cache_key] = result
        return result

    def _validate_site_jar(self, jar_reference, api=""):
        source, separator, expected_md5 = str(jar_reference).partition(";md5;")
        source = source.strip()
        expected_md5 = expected_md5.strip().lower() if separator else ""
        if expected_md5 and not re.fullmatch(r"[0-9a-f]{32}", expected_md5):
            raise ValueError("JAR md5 格式无效")
        lower = source.lower()
        if lower.startswith(("http://", "https://", "assets://")):
            return "远程或内置 JAR，等待 App 运行时确认"
        path = self._site_reference_path(source)
        if not path or not os.path.isfile(path) or not os.access(path, os.R_OK):
            raise ValueError("JAR 不存在或不可读: {}".format(source))
        inspection = self._inspect_local_jar(path)
        md5_detail = ""
        if expected_md5 and inspection["md5"] != expected_md5:
            md5_detail = "本地 JAR 声明 md5 不一致，已改用实际 md5"
        compatible, compatibility_detail = self._jar_runtime_compatibility(
            inspection, api
        )
        if not compatible:
            raise ValueError(compatibility_detail)
        class_name = api[len("csp_") :] if api.startswith("csp_") else ""
        confirmed = bool(class_name) and class_name in inspection["classes"]
        if confirmed:
            return "已确认 JAR 类 com.github.catvod.spider.{}{}{}".format(
                class_name,
                "；" + md5_detail if md5_detail else "",
                "；" + compatibility_detail if compatibility_detail else "",
            )
        if not class_name:
            return "JAR 结构有效{}".format(
                "；" + md5_detail if md5_detail else ""
            )
        if inspection["class_scan_complete"]:
            raise ValueError(
                "JAR 未包含类 com.github.catvod.spider.{}: {}".format(
                    class_name, path
                )
            )
        return "JAR 结构有效，类名未静态确认，等待 App 运行时验证{}".format(
            "；" + md5_detail if md5_detail else ""
        )

    def _auto_csp_site(self, config_path, jar_path):
        config = self._load_json_compatible(config_path)
        if not isinstance(config, dict) or not config:
            raise ValueError("CSP 配置必须是非空 JSON 对象")

        config_stem = os.path.splitext(os.path.basename(config_path))[0]
        inspection = self._inspect_local_jar(jar_path)
        matching_classes = sorted(
            class_name
            for class_name in inspection["direct_classes"]
            if class_name.casefold() == config_stem.casefold()
        )
        if len(matching_classes) != 1:
            if not matching_classes:
                reason = "JAR 中未找到与 {} 匹配的顶层类".format(
                    config_stem
                )
            else:
                reason = "JAR 中匹配到多个顶层类: {}".format(
                    ", ".join(matching_classes)
                )
            raise ValueError(reason + "，请使用 site.json 显式配置 api")

        class_name = matching_classes[0]
        api = "csp_" + class_name
        jar_reference = (
            self._file_url(jar_path) + ";md5;" + inspection["md5"]
        )
        folder_name = os.path.basename(os.path.dirname(config_path)).strip()
        if not folder_name or folder_name.casefold() == "csp":
            folder_name = config_stem
        site = {
            "name": folder_name,
            "type": 3,
            "api": api,
            "ext": self._file_url(config_path),
            "jar": jar_reference,
            "searchable": self.DEFAULT_SEARCHABLE,
            "quickSearch": self.DEFAULT_QUICK_SEARCH,
        }
        if config.get("filters"):
            site["filterable"] = 1
        detail = "已根据 JSON 文件名确认 JAR 类 com.github.catvod.spider.{}".format(
            class_name
        )
        return site, [jar_path], detail

    def _parse_site_manifest(self, path, source_type):
        data = self._load_json_compatible(path)
        if not isinstance(data, dict):
            raise ValueError("站点清单顶层必须是 JSON 对象")
        if isinstance(data.get("site"), dict) and not data.get("api"):
            data = data["site"]
        site = copy.deepcopy(data)
        source_type = str(source_type or "").upper()
        api = str(site.get("api", "")).strip()
        dependencies = []
        validation_details = []
        if source_type == "JS":
            if not api:
                raise ValueError("JS 清单缺少 api")
            api_reference = self._resolve_site_reference(path, api)
            if ".js" not in api_reference.lower():
                raise ValueError("JS 清单 api 必须指向 .js 文件或URL")
            api_path = self._site_reference_path(api_reference)
            if api_path:
                if not os.path.isfile(api_path) or not os.access(api_path, os.R_OK):
                    raise ValueError("JS api 不存在或不可读: {}".format(api_reference))
                valid, detail = self._validate_source("JS", api_path)
                if not valid:
                    raise ValueError(detail)
                dependencies.append(api_path)
            site["api"] = api_reference
            validation_details.append("JS 清单有效")
        else:
            if not re.fullmatch(r"csp_[A-Za-z_$][A-Za-z0-9_.$]*", api):
                raise ValueError("{} api 必须是 csp_ 开头的有效类名".format(source_type))
            site["api"] = api
        jar_value = str(site.get("jar", "")).strip()
        if source_type in ("CSP",) and not jar_value:
            raise ValueError("{} 清单缺少 jar".format(source_type))
        if jar_value:
            jar_reference = self._resolve_site_reference(
                path, jar_value, with_md5=True
            )
            jar_detail = self._validate_site_jar(jar_reference, api)
            jar_path = self._site_reference_path(jar_reference, with_md5=True)
            if jar_path:
                actual_md5 = self._inspect_local_jar(jar_path)["md5"]
                jar_reference = (
                    jar_reference.split(";md5;", 1)[0].strip()
                    + ";md5;"
                    + actual_md5
                )
                dependencies.append(jar_path)
            site["jar"] = jar_reference
            validation_details.append(jar_detail)
        else:
            site.pop("jar", None)
        ext = site.get("ext", "")
        if isinstance(ext, str) and ext.strip():
            ext_reference = self._resolve_site_reference(path, ext)
            ext_path = self._site_reference_path(ext_reference)
            if ext_path:
                if not os.path.isfile(ext_path) or not os.access(ext_path, os.R_OK):
                    raise ValueError("{} ext 不存在或不可读: {}".format(source_type, ext_reference))
                if os.path.getsize(ext_path) <= 0:
                    raise ValueError("{} ext 是空文件: {}".format(source_type, ext_path))
                if ext_path.lower().endswith(".json"):
                    self._load_json_compatible(ext_path)
                dependencies.append(ext_path)
            site["ext"] = ext_reference
        elif ext not in (None, "") and not isinstance(ext, (dict, list)):
            raise ValueError("{} ext 必须是路径、URL或JSON对象".format(source_type))
        site["type"] = 3
        site.setdefault("searchable", self.DEFAULT_SEARCHABLE)
        site.setdefault("quickSearch", self.DEFAULT_QUICK_SEARCH)
        name = str(site.get("name", "")).strip()
        if not name:
            stem = os.path.basename(path)
            if stem.lower() == "site.json":
                stem = os.path.basename(os.path.dirname(path))
            elif stem.lower().endswith(".site.json"):
                stem = stem[: -len(".site.json")]
            fallback = api[len("csp_") :] if api.startswith("csp_") else "JS站点"
            site["name"] = stem or fallback
        return (
            site,
            list(dict.fromkeys(dependencies)),
            "；".join(item for item in validation_details if item),
        )

    def _validate_source(self, source_type, path):
        try:
            lower_name = os.path.basename(path).lower()
            if (
                source_type in ("JS", "CSP")
                and self._is_site_manifest_name(lower_name)
            ):
                _, _, detail = self._parse_site_manifest(path, source_type)
                return True, detail
            elif source_type == "PY":
                text = self._read_text(path, 256 * 1024)
                if not re.search(r"\bclass\s+Spider\s*(?:\(|:)", text):
                    return False, "PY 文件未发现 Spider 类，已按依赖库跳过: {}".format(path)
            elif source_type == "JS":
                text = self._read_text(path, 256 * 1024)
                if not (
                    self._has_direct_js_spider(text)
                    or self._has_drpy_rule(text)
                ):
                    return False, "JS 文件未发现可执行 Spider 入口，已按依赖库或数据文件跳过: {}".format(path)
            elif source_type == "HTML":
                text = self._read_text(path, 128 * 1024).lower()
                if not any(tag in text for tag in ("<!doctype html", "<html", "<body")):
                    return False, "HTML 文件未发现页面结构: {}".format(path)
        except Exception as exc:
            return False, "{} 文件检查失败: {} ({})".format(source_type, path, exc)
        return True, ""

    def _has_quickjs_export(self, text):
        return bool(
            re.search(
                r"\bexport\s+(?:default|(?:async\s+)?function|class|const|let|var|\{)",
                str(text or ""),
            )
            or "__jsEvalReturn" in str(text or "")
            or "__JS_SPIDER__" in str(text or "")
        )

    def _decoded_js_payload(self, text):
        value = str(text or "").lstrip("\ufeff").strip()
        compact = re.sub(r"\s+", "", value)
        if (
            len(compact) < 32
            or len(compact) % 4
            or not re.fullmatch(r"[A-Za-z0-9+/=]+", compact)
        ):
            return value, False
        try:
            raw = base64.b64decode(compact, validate=True)
        except Exception:
            return value, False
        decoded = b""
        try:
            decoded = gzip.decompress(raw)
        except Exception:
            try:
                decoded = raw
            except Exception:
                decoded = b""
        if not decoded:
            return value, False
        candidate = decoded.decode("utf-8", errors="ignore").strip()
        printable = sum(
            1 for char in candidate if char.isprintable() or char in "\r\n\t"
        )
        if candidate and printable >= int(len(candidate) * 0.85):
            return candidate, True
        return value, False

    def _js_entrypoint_count(self, text):
        value = str(text or "")
        names = (
            "init",
            "home",
            "homeVod",
            "homeContent",
            "homeVideoContent",
            "category",
            "categoryContent",
            "detail",
            "detailContent",
            "play",
            "playerContent",
            "search",
            "searchContent",
            "proxy",
            "proxy_rule",
        )
        return sum(
            bool(
                re.search(
                    r"\b(?:async\s+)?function\s+{}\s*\(".format(
                        re.escape(name)
                    ),
                    value,
                )
                or re.search(
                    r"\b(?:const|let|var)\s+{}\s*=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)".format(
                        re.escape(name)
                    ),
                    value,
                )
            )
            for name in names
        )

    def _has_commonjs_spider(self, text):
        value = str(text or "")
        if not re.search(r"\bmodule\.exports\s*=\s*\{", value):
            return False
        return sum(
            bool(re.search(r"\b{}\b".format(name), value))
            for name in ("home", "category", "detail", "play", "search")
        ) >= 4

    def _has_direct_js_spider(self, text):
        value, decoded = self._decoded_js_payload(text)
        if self._has_quickjs_export(value) or self._has_commonjs_spider(value):
            return True
        # WvSpider/server.js 规则会直接暴露固定入口，不带 ES module 导出。
        # 依赖库即使含有 home/play 等普通单词，也不会同时声明这些入口。
        if self._js_entrypoint_count(value) >= 4:
            return True
        return False

    def _js_rule_text(self, text):
        value, _ = self._decoded_js_payload(text)
        if self._has_plain_drpy_rule(value):
            return value
        return value

    def _has_plain_drpy_rule(self, text):
        value = str(text or "")
        if not re.search(
            r"\b(?:var|let|const)\s+rule\s*=\s*\{",
            value,
        ):
            return False
        signatures = (
            "title:",
            "host:",
            "url:",
            "searchUrl:",
            "一级:",
            "二级:",
            "推荐:",
            "搜索:",
            "lazy:",
        )
        return sum(signature in value for signature in signatures) >= 2

    def _has_drpy_rule(self, text):
        value = self._js_rule_text(text)
        if self._has_plain_drpy_rule(value):
            return True
        # drpy2.getOriginalJs 原生支持 gzip/base64/AES/RSA 等无明文头规则。
        # 只在内容是较长的纯 Base64 载荷且解码后不是其他 Spider 时配对运行时。
        compact = re.sub(r"\s+", "", str(text or "").strip())
        return bool(
            len(compact) >= 256
            and len(compact) % 4 == 0
            and re.fullmatch(r"[A-Za-z0-9+/=]+", compact)
            and not self._has_direct_js_spider(text)
        )

    def _drpy_rule_title(self, text):
        value = self._js_rule_text(text)
        match = re.search(
            r"(?:^|[,\n\r{])\s*title\s*:\s*(['\"])(.*?)\1",
            value,
            re.DOTALL,
        )
        if not match:
            return ""
        return re.sub(r"\s+", " ", match.group(2)).strip()[:80]

    def _js_import_references(self, text):
        references = []
        for match in re.finditer(
            r"\bimport\s+(?:[^;\n]*?\s+from\s*)?(['\"])([^'\"]+)\1",
            str(text or ""),
        ):
            reference = match.group(2).strip()
            if reference.startswith(("./", "../")):
                references.append(reference.split("?", 1)[0])
        return references

    def _resolve_js_import_path(self, owner_path, reference):
        candidate = os.path.realpath(
            os.path.join(os.path.dirname(owner_path), reference)
        )
        choices = [candidate]
        if not os.path.splitext(candidate)[1]:
            choices.extend((candidate + ".js", os.path.join(candidate, "index.js")))
        return next((path for path in choices if os.path.isfile(path)), "")

    def _js_runtime_dependency_paths(self, root):
        root_real = os.path.realpath(os.path.abspath(root))
        runtimes = []
        for current, dirs, files in os.walk(root_real, topdown=True):
            dirs[:] = [
                name
                for name in dirs
                if not name.startswith(".") and name.lower() not in self.SKIP_DIRS
            ]
            by_lower = {name.lower(): name for name in files}
            for runtime_name in self.JS_RUNTIME_NAMES:
                actual = by_lower.get(runtime_name)
                if actual:
                    runtimes.append(os.path.realpath(os.path.join(current, actual)))
        result = set(runtimes)
        pending = list(runtimes)
        while pending:
            owner = pending.pop()
            try:
                text = self._read_text(owner, self.max_source_size)
            except Exception:
                continue
            for reference in self._js_import_references(text):
                dependency = self._resolve_js_import_path(owner, reference)
                if (
                    dependency
                    and self._path_is_within(dependency, root_real)
                    and dependency not in result
                ):
                    result.add(dependency)
                    pending.append(dependency)
        return result

    def _find_js_runtime(self, rule_path, root):
        root_real = os.path.realpath(os.path.abspath(root))
        current = os.path.realpath(os.path.dirname(rule_path))
        while self._path_is_within(current, root_real):
            try:
                by_lower = {
                    name.lower(): name
                    for name in os.listdir(current)
                    if os.path.isfile(os.path.join(current, name))
                }
            except Exception:
                by_lower = {}
            for runtime_name in self.JS_RUNTIME_NAMES:
                actual = by_lower.get(runtime_name)
                if actual:
                    return os.path.realpath(os.path.join(current, actual))
            if current == root_real:
                break
            parent = os.path.realpath(os.path.dirname(current))
            if parent == current:
                break
            current = parent
        return ""

    def _read_text(self, path, limit):
        with open(path, "rb") as fp:
            data = fp.read(limit)
        return data.decode("utf-8", errors="ignore")

    def _source_parent_suffix(self, source):
        path = os.path.realpath(
            os.path.abspath(os.path.expanduser(str(source.get("path", ""))))
        )
        parent = os.path.basename(os.path.dirname(path)).strip()
        if not parent:
            source_type = str(source.get("type", "")).upper()
            parent = self.TYPE_LABEL.get(source_type, source_type or "本地")
        parent = re.sub(r"[\r\n\t\[\]【】|]+", " ", parent)
        parent = re.sub(r"\s+", " ", parent).strip(" ._")
        return (parent or "本地")[:32]

    def _apply_display_names(self, sources):
        counts = {}
        folder_counts = {}
        for source in sources:
            identity = (source["type"], source["base_name"].lower())
            counts[identity] = counts.get(identity, 0) + 1
            folder = os.path.dirname(source["relative_in_root"]).replace(
                os.sep, "/"
            )
            folder_identity = identity + (folder.lower(),)
            folder_counts[folder_identity] = (
                folder_counts.get(folder_identity, 0) + 1
            )

        for source in sources:
            source_type = source["type"]
            base_name = source["base_name"]
            package_label = str(source.get("package_label", "")).strip()
            identity = (source_type, base_name.lower())
            duplicate_suffix = ""
            if counts.get(identity, 0) > 1:
                folder = os.path.dirname(source["relative_in_root"]).replace(os.sep, "/")
                folder_identity = identity + (folder.lower(),)
                if folder_counts.get(folder_identity, 0) > 1:
                    original_key = str(
                        source.get("csp_site", {}).get("key", "")
                        if isinstance(source.get("csp_site"), dict)
                        else ""
                    ).strip()
                    if "#bundle-site-" in source["identity"] and original_key:
                        disambiguator = original_key
                    else:
                        relative_name = os.path.basename(source["relative_in_root"])
                        disambiguator = os.path.splitext(relative_name)[0]
                else:
                    disambiguator = folder or os.path.basename(
                        source["scan_root"]
                    )
                duplicate_suffix = " · " + disambiguator
            parent_suffix = self._source_parent_suffix(source)
            package_prefix = (
                "【{}】".format(package_label)
                if package_label
                and package_label.casefold() != parent_suffix.casefold()
                else ""
            )
            source["name"] = (
                self.TYPE_PREFIX[source_type]
                + package_prefix
                + base_name
                + duplicate_suffix
                + "|[{}]".format(parent_suffix)
            )

    def _build_site(self, source):
        source_type = source["type"]
        file_ref = self._file_url(source["path"])
        site = {
            "key": source["key"],
            "name": source["name"],
            "type": 3,
            "searchable": self.DEFAULT_SEARCHABLE,
            "quickSearch": self.DEFAULT_QUICK_SEARCH,
        }
        if source.get("csp_site"):
            manifest_site = copy.deepcopy(source.get("csp_site", {}))
            if not isinstance(manifest_site, dict):
                manifest_site = {}
            original_key = str(manifest_site.get("key", "")).strip()
            site.update(manifest_site)
            # 整包 QuickJS/CSP 可能用配置 key 作为规则缓存或运行参数。
            # 注册表 item.id 已提供独立管理标识，无需改写运行 key。
            site["key"] = original_key or source["key"]
            site["name"] = source["name"]
            try:
                site["type"] = int(manifest_site.get("type", 3))
            except Exception:
                site["type"] = 3
            site.setdefault("searchable", self.DEFAULT_SEARCHABLE)
            site.setdefault("quickSearch", self.DEFAULT_QUICK_SEARCH)
        elif source_type == "PY":
            site.update({"api": file_ref})
        elif source_type == "JS":
            site.update(
                {
                    "api": file_ref,
                    "ext": "",
                }
            )
        elif source_type == "HTML":
            site.update(
                {
                    "api": self._runtime_reference(self.html_api),
                    "homePage": file_ref,
                }
            )
        return site

    def _file_url(self, path):
        absolute = os.path.realpath(os.path.abspath(os.path.expanduser(str(path))))
        storage_root = os.path.realpath(os.path.abspath(self.STORAGE_ROOT))
        try:
            relative = os.path.relpath(absolute, storage_root).replace(os.sep, "/")
        except Exception:
            relative = ""
        if relative and relative != ".." and not relative.startswith("../"):
            return "file://" + relative.lstrip("/")
        return "file://" + absolute

    def _runtime_reference(self, reference):
        value = str(reference or "").strip()
        if not value:
            return ""
        lower = value.lower()
        if lower.startswith(("http://", "https://", "file://", "assets://")):
            return value
        if value.startswith("csp_"):
            return value
        if os.path.isabs(value):
            return self._file_url(value)
        return self._file_url(os.path.join(self.local_base_dir, value.lstrip("./")))

    def _generate_config(self):
        base_duplicates = self.status["duplicates"]
        last_error = None
        for _ in range(3):
            registry, token = self._load_registry_snapshot()
            registry, manual_count, generated_count, duplicate_count, diff = self._merge_registry(
                registry
            )
            # v6.0：标准点播配置由完整合并结果生成（两端共用的主加载链路），
            # 写入注册表文件的只有 WebHome 注入视图。
            injection_registry, dropped = self._webhome_injection_registry(registry)
            try:
                self._atomic_write_json(injection_registry, expected_token=token)
                self.status["manual_sites"] = manual_count
                self.status["generated_sites"] = generated_count
                self.status["duplicates"] = base_duplicates + duplicate_count
                self.status["added_sites"] = diff["added"]
                self.status["updated_sites"] = diff["updated"]
                self.status["removed_sites"] = diff["removed"]
                self.status["unchanged_sites"] = diff["unchanged"]
                self._write_standard_configs(registry)
                if dropped:
                    self._log(
                        "INFO",
                        "{} 个自动项改由标准点播配置加载，未写入注入表".format(
                            dropped
                        ),
                    )
                return
            except RegistryChangedError as exc:
                last_error = exc
        raise RegistryChangedError(
            "注册表在扫描期间持续被修改，已停止写入: {}".format(last_error)
        )

    def _webhome_injection_registry(self, registry):
        """派生只含 WebHome 自动项的注入视图。

        v6.0 统一加载模型：普通站点、直播和播放上下文由标准点播配置承载，
        站点注入通道只保留 WebHTV 独有的 WebHome。手工项一律原样保留，
        OK影视不使用注入通道，因此自动项全部移除。
        """
        source = registry if isinstance(registry, dict) else {}
        items = source.get("items", [])
        if not isinstance(items, list):
            items = []
        kept = []
        dropped = 0
        for item in items:
            if not self._is_generated_registry_item(item):
                kept.append(item)
                continue
            if (
                self.app_mode == self.APP_MODE_WEBHTV
                and self._is_webhome_registry_item(item)
            ):
                kept.append(item)
                continue
            dropped += 1
        view = copy.deepcopy(source)
        view["items"] = copy.deepcopy(kept)
        kept_keys = {
            self._registry_item_key(item)
            for item in kept
            if isinstance(item, dict)
        }
        home_key = str(view.get("homeKey", "")).strip()
        if home_key.startswith(self.GENERATED_KEY_PREFIX) and home_key not in kept_keys:
            view["homeKey"] = ""
        return view, dropped

    def _merge_registry(self, registry):
        items = registry.get("items", [])
        if not isinstance(items, list):
            raise ValueError("站点注入注册表的 items 必须是数组")

        old_generated_items = [
            item for item in items if self._is_generated_registry_item(item)
        ]
        manual_items = []
        for item in items:
            if not isinstance(item, dict):
                manual_items.append(item)
                continue
            if self._is_generated_registry_item(item):
                continue
            manual_items.append(item)

        manual_fingerprints = {
            self._site_fingerprint(self._registry_item_site(item))
            for item in manual_items
            if isinstance(item, dict)
            and str(item.get("kind", "")).lower() != "live"
        }
        manual_live_fingerprints = {
            self._live_fingerprint(self._registry_item_live(item))
            for item in manual_items
            if isinstance(item, dict)
            and str(item.get("kind", "")).lower() == "live"
        }
        # v7.0：load_filter 为 None 时沿用“全部加载”；为集合时只生成
        # 选择集内的站点/直播/上下文（精确子集，旧自动项一律不保留）。
        load_filter = self._load_filter
        if load_filter is not None:
            load_filter = {str(value) for value in load_filter}
        temp_identities = set(self.temp_identities)
        temp_paths = self._selected_source_paths(temp_identities)
        selected_paths = (
            self._selected_source_paths(load_filter)
            if load_filter is not None
            else None
        )

        generated_items = []
        duplicate_count = 0
        for source in self.cache["sources"]:
            identity = str(source.get("identity", ""))
            if load_filter is not None and identity not in load_filter:
                continue
            site = source["site"]
            if self._site_fingerprint(site) in manual_fingerprints:
                duplicate_count += 1
                continue
            generated_item = {
                "id": source["key"],
                "enabled": True,
                "kind": self._registry_kind(source),
                "sourceType": source.get("type", ""),
                "packageId": str(source.get("package_id", "")),
                "site": site,
            }
            if identity in temp_identities:
                # 供冷启动清理识别：临时项退出 App 后必须被移除。
                generated_item["temporary"] = True
            generated_items.append(generated_item)
        for source in self.cache.get("lives", []):
            live_path = str(source.get("path", "")).strip()
            norm_path = (
                os.path.normcase(os.path.abspath(live_path)) if live_path else ""
            )
            # 在线包安装产生的直播由包开关独立管理，不受本地选择集约束。
            if (
                selected_paths is not None
                and not str(source.get("package_id", "")).strip()
                and norm_path not in selected_paths
            ):
                continue
            live = copy.deepcopy(source.get("live", {}))
            fingerprint = self._live_fingerprint(live)
            if fingerprint in manual_live_fingerprints:
                duplicate_count += 1
                continue
            live[self.OK_CONFIG_MARKER] = {
                "version": self.OK_CONFIG_VERSION,
                "sourceId": source.get("id", ""),
                "packageId": source.get("package_id", ""),
            }
            generated_item = {
                "id": source["id"],
                "enabled": True,
                "kind": "live",
                "packageId": source.get("package_id", ""),
                "sourcePath": self._file_url(source.get("path", "")),
                "live": live,
            }
            if norm_path and norm_path in temp_paths:
                generated_item["temporary"] = True
            generated_items.append(generated_item)
        for entry in self.cache.get("contexts", []):
            if not isinstance(entry, dict):
                continue
            context = entry.get("context", {})
            if not isinstance(context, dict):
                continue
            entry_path = str(entry.get("path", "")).strip()
            norm_entry = (
                os.path.normcase(os.path.abspath(entry_path))
                if entry_path
                else ""
            )
            # 在线包播放上下文由包开关独立管理，不受本地选择集约束。
            if (
                selected_paths is not None
                and not str(entry.get("package_id", "")).strip()
                and norm_entry not in selected_paths
            ):
                continue
            base_id = str(entry.get("id", "")).strip()
            for field in self.PACKAGE_ROOT_CONTEXT_FIELDS:
                if field not in context:
                    continue
                generated_item = {
                    "id": "{}{}_{}".format(
                        self.GENERATED_CONTEXT_PREFIX,
                        self._digest(base_id, 12),
                        self._digest(field, 6),
                    ),
                    "enabled": True,
                    "kind": "other",
                    "name": field,
                    "packageId": str(entry.get("package_id", "")),
                    "sourcePath": self._file_url(entry.get("path", "")),
                    "other": {field: copy.deepcopy(context[field])},
                }
                if norm_entry and norm_entry in temp_paths:
                    generated_item["temporary"] = True
                generated_items.append(generated_item)

        generated_identities = {
            self._registry_item_identity(item) for item in generated_items
        }
        ignored_generated_identities = {
            value
            for source in self.cache.get("ignored", [])
            for value in (
                str(source.get("id", "")).strip(),
                str(source.get("key", "")).strip(),
            )
            if value
        }
        ignored_site_fingerprints = {
            self._site_fingerprint(source.get("site", {}))
            for source in self.cache.get("ignored", [])
            if isinstance(source.get("site"), dict)
        }
        preserved_count = 0
        for item in old_generated_items:
            identity = self._registry_item_identity(item)
            # 临时项绝不跨生成保留，防止退出/重进后残留。
            if item.get("temporary"):
                continue
            if (
                identity in ignored_generated_identities
                or self._site_fingerprint(self._registry_item_site(item))
                in ignored_site_fingerprints
            ):
                # 屏蔽状态优先于“扫描根目录暂时不可用时保留旧注入项”，
                # 避免被屏蔽站点又回到 App 可选列表。
                continue
            # 子集加载精确收敛：未参与本轮生成的旧项一律移除。
            if load_filter is not None:
                continue
            if identity in generated_identities or not self._should_preserve_generated_item(item):
                continue
            generated_items.append(item)
            generated_identities.add(identity)
            preserved_count += 1
        if preserved_count:
            self._warn(
                "{} 个旧注入项因对应扫描目录暂时不可用而保留".format(
                    preserved_count
                )
            )

        if self.generated_insert_index is None:
            merged_items = manual_items + generated_items
        else:
            index = max(0, min(int(self.generated_insert_index), len(manual_items)))
            merged_items = manual_items[:index] + generated_items + manual_items[index:]

        registry["enabled"] = True
        registry.setdefault("insertIndex", 0)
        registry.setdefault("homeKey", "")
        registry["items"] = merged_items
        home_key = str(registry.get("homeKey", "")).strip()
        generated_site_keys = {
            self._registry_item_key(item)
            for item in generated_items
            if str(item.get("kind", "")).strip().lower()
            not in ("live", "other")
        }
        if (
            home_key.startswith(self.GENERATED_KEY_PREFIX)
            and home_key not in generated_site_keys
        ):
            registry["homeKey"] = ""
        old_map = {
            self._registry_item_identity(item): self._registry_content_fingerprint(item)
            for item in old_generated_items
        }
        new_map = {
            self._registry_item_identity(item): self._registry_content_fingerprint(item)
            for item in generated_items
        }
        shared = set(old_map) & set(new_map)
        diff = {
            "added": len(set(new_map) - set(old_map)),
            "removed": len(set(old_map) - set(new_map)),
            "updated": sum(1 for key in shared if old_map[key] != new_map[key]),
            "unchanged": sum(1 for key in shared if old_map[key] == new_map[key]),
        }
        return registry, len(manual_items), len(generated_items), duplicate_count, diff

    def _registry_kind(self, source):
        if source.get("type") == "HTML":
            return "webHome"
        site = source.get("site", {})
        if not isinstance(site, dict):
            return "csp"
        has_home = bool(str(site.get("homePage", "")).strip())
        return "webHome" if has_home else "csp"

    def _generated_item_type(self, item):
        source_type = str(item.get("sourceType", "")).strip().upper()
        if source_type in self.TYPE_ORDER:
            return source_type
        key = self._registry_item_key(item).lower()
        for source_type in self.TYPE_ORDER:
            if key.startswith(
                self.GENERATED_KEY_PREFIX.lower() + source_type.lower() + "_"
            ):
                return source_type
        return ""

    def _generated_item_reference(self, item, source_type):
        site = self._registry_item_site(item)
        if not isinstance(site, dict):
            return ""
        field = {
            "PY": "api",
            "JS": "api",
            "CSP": "jar",
            "HTML": "homePage",
        }.get(source_type, "")
        return str(site.get(field, "")).strip() if field else ""

    def _should_preserve_generated_item(self, item):
        item_id = str(item.get("id", "")).strip()
        if item_id.startswith(self.GENERATED_CONTEXT_PREFIX):
            package_id = str(item.get("packageId", "")).strip()
            if package_id not in self._site_enabled_package_download_site_ids():
                return False
            return False
        if item_id.startswith(self.GENERATED_LIVE_PREFIX):
            package_id = str(item.get("packageId", "")).strip()
            if package_id not in self._live_enabled_package_download_site_ids():
                return False
            return False
        source_type = self._generated_item_type(item)
        if not source_type:
            return False
        package_id = str(item.get("packageId", "")).strip()
        if (
            package_id
            and package_id not in self._site_enabled_package_download_site_ids()
        ):
            return False
        if source_type in self.incomplete_scan_types:
            return True
        failed_same_type = any(
            item_type == source_type
            for item_type, _ in self.incomplete_scan_roots
        )
        reference = self._generated_item_reference(item, source_type)
        if not reference:
            return failed_same_type
        reference_value = reference.split(";md5;", 1)[0].strip()
        if not self._reference_path(reference_value):
            # 远程 JAR/assets 等引用无法反推出所属清单目录。只要同类型
            # 存在失败根目录，就保守保留旧项，避免临时权限故障删站点。
            return failed_same_type
        return self._scan_failure_covers_identity(
            source_type + "|" + reference_value
        )

    def _load_registry(self):
        return self._load_registry_snapshot()[0]

    def _load_registry_snapshot(self):
        registry_path = os.path.abspath(os.path.expanduser(self.registry_path))
        output_path = os.path.abspath(os.path.expanduser(self.output_path))
        path = registry_path if os.path.isfile(registry_path) else output_path
        if os.path.isfile(path):
            try:
                with open(path, "rb") as fp:
                    raw = fp.read()
                registry = json.loads(raw.decode("utf-8"))
            except Exception as exc:
                raise ValueError("站点注入注册表无法读取，已停止写入: {} ({})".format(path, exc))
            if not isinstance(registry, dict):
                raise ValueError("站点注入注册表顶层必须是 JSON 对象: {}".format(path))
            if "items" not in registry:
                registry = self._legacy_registry(registry)
            token = (
                hashlib.sha256(raw).hexdigest()
                if os.path.abspath(path) == output_path
                else self._registry_token(output_path)
            )
            return registry, token
        return {
            "enabled": True,
            "insertIndex": 0,
            "homeKey": "",
            "items": [],
        }, "__missing__"

    def _registry_token(self, path=None):
        path = os.path.abspath(os.path.expanduser(path or self.output_path))
        if not os.path.isfile(path):
            return "__missing__"
        try:
            with open(path, "rb") as fp:
                return hashlib.sha256(fp.read()).hexdigest()
        except Exception:
            return "__error__"

    def _legacy_registry(self, data):
        items = []
        sites = data.get("sites", [])
        if isinstance(sites, list):
            for index, site in enumerate(sites):
                if not isinstance(site, dict):
                    continue
                key = str(site.get("key", "")).strip()
                items.append(
                    {
                        "id": key or "legacy_site_{}".format(index),
                        "enabled": True,
                        "kind": "webHome" if site.get("homePage") else "csp",
                        "site": site,
                    }
                )
        return {
            "enabled": bool(data.get("enabled", True)),
            "insertIndex": int(data.get("insertIndex", 0) or 0),
            "homeKey": str(data.get("homeKey", data.get("home", "")) or ""),
            "items": items,
        }

    def _registry_item_site(self, item):
        site = item.get("site")
        return site if isinstance(site, dict) else item

    def _registry_item_live(self, item):
        live = item.get("live")
        return live if isinstance(live, dict) else item

    def _registry_item_key(self, item):
        key = str(item.get("key", "")).strip()
        if key:
            return key
        site = item.get("site")
        site_key = str(site.get("key", "")).strip() if isinstance(site, dict) else ""
        return site_key or str(item.get("id", "")).strip()

    def _registry_item_identity(self, item):
        item_id = str(item.get("id", "")).strip()
        if self._is_generated_registry_item(item) and item_id:
            return item_id
        return self._registry_item_key(item)

    def _is_generated_registry_item(self, item):
        if not isinstance(item, dict):
            return False
        key = self._registry_item_key(item)
        item_id = str(item.get("id", "")).strip()
        return key.startswith(self.GENERATED_KEY_PREFIX) or item_id.startswith(
            self.GENERATED_KEY_PREFIX
        )

    def _clear_generated_registry(self):
        last_error = None
        for _ in range(3):
            registry, token = self._load_registry_snapshot()
            registry, removed = self._remove_generated_items(registry)
            try:
                self._atomic_write_json(registry, expected_token=token)
                self._write_standard_configs(registry)
                return removed
            except RegistryChangedError as exc:
                last_error = exc
        raise RegistryChangedError(
            "注册表在清除期间持续被修改: {}".format(last_error)
        )

    def _program_owned_download_directories(self):
        """Return immediate child directories installed and marked by this loader."""
        owned = {}

        def inspect_root(root):
            root = os.path.realpath(os.path.abspath(os.path.expanduser(root)))
            if not os.path.isdir(root) or os.path.islink(root):
                return
            with os.scandir(root) as entries:
                for entry in entries:
                    if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                        continue
                    target = os.path.realpath(entry.path)
                    if os.path.commonpath((target, root)) != root:
                        continue
                    package_marker = self._read_package_install_marker(target)
                    if str(package_marker.get("id", "")).strip():
                        owned[target] = "package"
                        continue
                    repository_marker = self._read_repository_marker(target)
                    if (
                        repository_marker.get("format")
                        == self.ONLINE_REPOSITORY_STATE_FORMAT
                        and str(repository_marker.get("id", "")).strip()
                    ):
                        owned[target] = "repository"

        seen_roots = set()
        candidates = [self._package_root()]
        candidates.extend(
            str(item.get("path", "")).strip()
            for item in self.scan_roots
            if str(item.get("path", "")).strip()
        )
        candidates.extend(
            str(item.get("path", "")).strip()
            for item in getattr(self, "configured_scan_roots", [])
            if str(item.get("path", "")).strip()
        )
        for root in candidates:
            if not root:
                continue
            root = os.path.realpath(os.path.abspath(os.path.expanduser(root)))
            if root in seen_roots:
                continue
            seen_roots.add(root)
            inspect_root(root)
        return [
            {"path": path, "kind": owned[path]}
            for path in sorted(owned)
        ]

    def _stage_program_download_deletions(self):
        token = self._digest(str(time.time_ns()), 12)
        transaction = []
        try:
            for item in self._program_owned_download_directories():
                source = item["path"]
                staged = source + ".local-media-clear-" + token
                if os.path.exists(staged):
                    raise ValueError("一键清除隔离目录已存在: {}".format(staged))
                os.replace(source, staged)
                transaction.append(
                    {
                        "kind": item["kind"],
                        "original": source,
                        "staged": staged,
                    }
                )
            return transaction
        except Exception:
            self._rollback_program_download_deletions(transaction)
            raise

    @staticmethod
    def _rollback_program_download_deletions(transaction):
        for item in reversed(transaction):
            original = str(item.get("original", "")).strip()
            staged = str(item.get("staged", "")).strip()
            if not staged or not os.path.exists(staged):
                continue
            if os.path.exists(original):
                raise ValueError("一键清除回滚目标已存在: {}".format(original))
            os.replace(staged, original)

    def _finalize_program_download_deletions(self, transaction):
        removed = {"package": 0, "repository": 0}
        warnings = []
        for item in transaction:
            staged = str(item.get("staged", "")).strip()
            if not staged or not os.path.exists(staged):
                continue
            try:
                if os.path.islink(staged) or not os.path.isdir(staged):
                    raise ValueError("隔离目标不是普通目录")
                shutil.rmtree(staged)
                kind = str(item.get("kind", ""))
                removed[kind] = removed.get(kind, 0) + 1
            except Exception as exc:
                warning = "已隔离但未能删除 {}: {}".format(staged, exc)
                warnings.append(warning)
        return removed, warnings

    def _clear_program_operation_artifacts(self):
        """Remove only temp/state files whose names or contents prove ownership."""
        removed = 0
        warnings = []

        def remove_path(path):
            nonlocal removed
            try:
                if os.path.islink(path):
                    raise ValueError("拒绝删除符号链接")
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                removed += 1
            except FileNotFoundError:
                pass
            except Exception as exc:
                warning = "程序临时内容清理失败 {}: {}".format(path, exc)
                warnings.append(warning)

        download_dir = self._package_download_directory()
        if os.path.isdir(download_dir) and not os.path.islink(download_dir):
            with os.scandir(download_dir) as entries:
                for entry in entries:
                    if re.fullmatch(
                        r"\.package-[0-9a-f]{16}\.zip\.part", entry.name
                    ):
                        remove_path(entry.path)

        package_root = self._package_root()
        if os.path.isdir(package_root) and not os.path.islink(package_root):
            with os.scandir(package_root) as entries:
                for entry in entries:
                    if re.fullmatch(
                        r"\.package-[0-9a-f]{12}\.(?:tmp|rollback)",
                        entry.name,
                    ):
                        remove_path(entry.path)

        state_dir = os.path.realpath(
            os.path.abspath(os.path.expanduser(self.online_repository_state_dir))
        )
        if os.path.isdir(state_dir) and not os.path.islink(state_dir):
            with os.scandir(state_dir) as entries:
                for entry in entries:
                    if re.fullmatch(r"\.(?:sync|delete)-[0-9a-f]+", entry.name):
                        remove_path(entry.path)
                        continue
                    if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                        continue
                    try:
                        with open(entry.path, "r", encoding="utf-8") as fp:
                            data = json.load(fp)
                    except Exception:
                        continue
                    if (
                        isinstance(data, dict)
                        and data.get("format")
                        == self.ONLINE_REPOSITORY_STATE_FORMAT
                    ):
                        remove_path(entry.path)
            try:
                os.rmdir(state_dir)
            except OSError:
                pass
        return removed, warnings

    def _reset_state_after_full_clear(self):
        # v7.1：加载选择集一并复位，否则重新扫描会按旧选择集显示/写回已清除站点。
        self.selected_identities = set()
        self.temp_identities = set()
        self._temp_home_key = ""
        self.perm_injected_identities = set()
        self.selection_initialized = True
        self.manual_ignored_sources.clear()
        self.auto_blocked_sources.clear()
        self.adult_blocked_sources.clear()
        self.adult_allowed_sources.clear()
        self.ignored_sources.clear()
        self.pruned_sources.clear()
        self.site_test_results.clear()
        self.site_test_history.clear()
        self.source_metadata.clear()
        self._retest_pending = []
        self._retest_auto_blocked.clear()
        self.auto_scan_suspended = True
        self._author_scan_surprise_shown = False
        for item in self.package_download_sites:
            item["site_count"] = 0
            item["dependency_count"] = 0
            item["live_count"] = 0
        for item in self.online_repositories:
            item["version"] = ""
            item["manifest_digest"] = ""
            item["file_count"] = 0
            item["last_sync"] = ""
            item["last_status"] = ""
            item["last_message"] = ""
        self._set_manual_idle_status("已一键清除，请重新下载或扫描")

    def _remove_generated_items(self, registry):
        items = registry.get("items", [])
        if not isinstance(items, list):
            raise ValueError("站点注入注册表的 items 必须是数组")
        generated_keys = {
            self._registry_item_key(item)
            for item in items
            if self._is_generated_registry_item(item)
        }
        kept = [item for item in items if not self._is_generated_registry_item(item)]
        removed = len(items) - len(kept)
        registry["items"] = kept
        if str(registry.get("homeKey", "")).strip() in generated_keys:
            registry["homeKey"] = ""
        return registry, removed

    def _restore_registry_file(self, backup_path):
        if not os.path.isfile(backup_path):
            raise ValueError("暂无可恢复的注册表备份")
        registry = self._validate_registry_backup(backup_path)
        current_path = os.path.abspath(os.path.expanduser(self.output_path))
        expected_token = self._registry_token(current_path)
        if os.path.isfile(current_path):
            self._create_registry_backup(current_path)
        self._atomic_write_json(
            registry,
            create_backup=False,
            expected_token=expected_token,
        )
        if self.app_mode == self.APP_MODE_OKTV:
            self._write_standard_configs(registry)
        return len(registry.get("items", []))

    def _create_registry_backup(self, source_path):
        os.makedirs(self.backup_dir, exist_ok=True)
        backup_path = self._latest_backup_path()
        temp_path = backup_path + ".tmp"
        try:
            shutil.copy2(source_path, temp_path)
            self._validate_registry_backup(temp_path)
            os.replace(temp_path, backup_path)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
        self._remove_legacy_backup_files(keep=backup_path)

    def _latest_backup_path(self):
        return os.path.join(
            os.path.abspath(os.path.expanduser(self.backup_dir)),
            "registry-latest.json",
        )

    def _backup_candidates(self):
        candidates = []
        backup_dir = os.path.abspath(os.path.expanduser(self.backup_dir))
        if os.path.isdir(backup_dir):
            candidates.extend(
                os.path.join(backup_dir, name)
                for name in os.listdir(backup_dir)
                if name.startswith("registry-")
                and name.endswith(".json")
                and os.path.isfile(os.path.join(backup_dir, name))
            )
        output_path = os.path.abspath(os.path.expanduser(self.output_path))
        for suffix in (".bak", ".before-restore.bak"):
            path = output_path + suffix
            if os.path.isfile(path):
                candidates.append(path)
        return candidates

    def _normalize_backup_storage(self):
        candidates = self._backup_candidates()
        if not candidates:
            return
        latest_path = self._latest_backup_path()
        valid_candidates = []
        for path in candidates:
            try:
                self._validate_registry_backup(path)
                valid_candidates.append(path)
            except Exception as exc:
                self._warn("忽略损坏的历史备份: {} ({})".format(path, exc))
        if not valid_candidates:
            return
        newest = max(
            valid_candidates,
            key=lambda path: (os.path.getmtime(path), os.path.basename(path)),
        )
        if os.path.abspath(newest) != os.path.abspath(latest_path):
            os.makedirs(os.path.dirname(latest_path), exist_ok=True)
            temp_path = latest_path + ".tmp"
            try:
                shutil.copy2(newest, temp_path)
                self._validate_registry_backup(temp_path)
                os.replace(temp_path, latest_path)
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
        self._remove_legacy_backup_files(keep=latest_path)

    def _validate_registry_backup(self, path):
        registry = self._read_config_file(path, "注册表备份")
        if "items" not in registry and isinstance(registry.get("sites"), list):
            registry = self._legacy_registry(registry)
        if not isinstance(registry.get("items"), list):
            raise ValueError("注册表备份的 items 必须是数组: {}".format(path))
        return registry

    def _remove_legacy_backup_files(self, keep=None):
        keep = os.path.abspath(keep) if keep else ""
        for path in self._backup_candidates():
            if os.path.abspath(path) == keep:
                continue
            try:
                os.remove(path)
            except Exception:
                pass

    def _delete_backup_files(self):
        removed = 0
        for path in self._backup_candidates():
            try:
                os.remove(path)
                removed += 1
            except FileNotFoundError:
                pass
        return removed

    def _list_backup_files(self):
        path = self._latest_backup_path()
        if not os.path.isfile(path):
            return []
        try:
            self._validate_registry_backup(path)
            return [path]
        except Exception:
            return []

    def _read_config_file(self, path, label):
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception as exc:
            raise ValueError("{}无法读取，已停止写入: {} ({})".format(label, path, exc))
        if not isinstance(data, dict):
            raise ValueError("{}顶层必须是 JSON 对象: {}".format(label, path))
        return data

    def _site_fingerprint(self, site):
        if not isinstance(site, dict):
            return ""
        data = {
            "type": site.get("type", 3),
            "api": site.get("api", ""),
            "ext": site.get("ext", ""),
            "jar": site.get("jar", ""),
            "homePage": site.get("homePage", site.get("home_page", "")),
        }
        return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def _registry_content_fingerprint(self, item):
        if not isinstance(item, dict):
            return ""
        return json.dumps(
            item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

    def _atomic_write_json(self, config, create_backup=True, expected_token=None):
        output_path = os.path.abspath(os.path.expanduser(self.output_path))
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.isdir(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        content = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
        if os.path.isfile(output_path):
            try:
                with open(output_path, "r", encoding="utf-8") as fp:
                    if fp.read() == content:
                        self.status["write_state"] = "配置内容未变化"
                        self.status["written"] = True
                        self.status["registry_changed"] = False
                        return
            except Exception:
                pass

        temp_path = output_path + ".tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as fp:
                fp.write(content)
                fp.flush()
                os.fsync(fp.fileno())
            with open(temp_path, "r", encoding="utf-8") as fp:
                check = json.load(fp)
            if not isinstance(check, dict) or not isinstance(check.get("items", []), list):
                raise ValueError("临时注册表校验失败")
            if expected_token is not None and self._registry_token(output_path) != expected_token:
                raise RegistryChangedError("注册表已被其他操作修改")
            if os.path.isfile(output_path) and self.backup_before_write and create_backup:
                self._create_registry_backup(output_path)
            os.replace(temp_path, output_path)
            self.status["write_state"] = "已写入 WebHTV 站点注入注册表"
            self.status["written"] = True
            self.status["registry_changed"] = True
        except Exception:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
            raise

    def _digest(self, value, length):
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]

    def _diagnostic_log_path(self):
        return os.path.abspath(os.path.expanduser(self.log_path))


    def _active_operation_trace_id(self):
        return (
            self._package_download_trace_id
            or self._repository_sync_trace_id
            or "-"
        )

    def _safe_log_url(self, value):
        text = str(value or "").strip()
        if not text:
            return ""
        try:
            parsed = urllib.parse.urlsplit(text)
            if parsed.scheme not in ("http", "https"):
                return text[:240]
            query_keys = sorted(
                {
                    key
                    for key, _item in urllib.parse.parse_qsl(
                        parsed.query, keep_blank_values=True
                    )
                    if key
                }
            )
            suffix = "?{}".format(",".join(query_keys)) if query_keys else ""
            return "{}://{}{}{}".format(
                parsed.scheme, parsed.netloc, parsed.path or "/", suffix
            )[:240]
        except Exception:
            return text.split("?", 1)[0][:240]

    def _trace_log(self, trace_id, component, event, level="INFO", **fields):
        sensitive_names = {
            "authorization_key",
            "release_ticket",
            "ticket",
            "token",
            "password",
            "secret",
        }

        def sanitize(name, value, depth=0):
            key = str(name or "field")[:48]
            if key.casefold() in sensitive_names:
                return "[redacted]"
            if depth >= 3:
                return str(value)[:320]
            if isinstance(value, str):
                text = value[:320]
                return (
                    self._safe_log_url(text)
                    if text.startswith(("http://", "https://"))
                    else text
                )
            if isinstance(value, (int, float, bool)) or value is None:
                return value
            if isinstance(value, (list, tuple, set)):
                return [
                    sanitize("item", item, depth + 1)
                    for item in list(value)[:30]
                ]
            if isinstance(value, dict):
                return {
                    str(item_key)[:48]: sanitize(
                        item_key, item_value, depth + 1
                    )
                    for item_key, item_value in list(value.items())[:30]
                }
            return str(value)[:320]

        safe = {
            str(name or "field")[:48]: sanitize(name, value)
            for name, value in fields.items()
        }
        payload = json.dumps(
            safe, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        self._log(
            level,
            "[trace={}] component={} event={} {}".format(
                str(trace_id or "-")[:32],
                str(component or "operation")[:32],
                str(event or "state")[:48],
                payload,
            ),
        )

    def _diagnostic_log_tail(self, line_limit=60, char_limit=12000):
        path = self._diagnostic_log_path()
        if not os.path.isfile(path):
            return ""
        try:
            read_limit = max(4096, min(int(self.max_log_size), 64 * 1024))
            size = os.path.getsize(path)
            with open(path, "rb") as fp:
                fp.seek(max(0, size - read_limit))
                payload = fp.read(read_limit)
            text = payload.decode("utf-8", errors="replace")
            if size > read_limit:
                text = text.split("\n", 1)[-1]
            lines = text.splitlines()[-max(1, int(line_limit)) :]
            return "\n".join(lines)[-max(1000, int(char_limit)) :]
        except Exception:
            return ""

    def _log(self, level, message):
        """写入单文件诊断日志，仅在当前操作触发时执行。"""
        text = " ".join(str(message or "").split()).strip()
        if not text:
            return
        try:
            path = self._diagnostic_log_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            limit = max(16 * 1024, int(self.max_log_size))
            line = "{} [{}] {}\n".format(
                time.strftime("%Y-%m-%d %H:%M:%S"),
                str(level or "INFO").upper()[:10],
                text[:4000],
            ).encode("utf-8", errors="replace")
            if len(line) > limit // 2:
                line = line[: limit // 2].decode("utf-8", errors="ignore").encode("utf-8")
                line = line.rstrip(b"\n") + b"\n"

            current_size = os.path.getsize(path) if os.path.isfile(path) else 0
            if current_size + len(line) > limit:
                header = b"... earlier log entries truncated ...\n"
                keep = max(0, limit - len(header) - len(line))
                tail = b""
                if keep and os.path.isfile(path):
                    with open(path, "rb") as fp:
                        fp.seek(max(0, current_size - keep))
                        tail = fp.read(keep)
                    newline = tail.find(b"\n")
                    if newline >= 0:
                        tail = tail[newline + 1 :]
                    else:
                        tail = b""
                temp_path = path + ".tmp"
                try:
                    with open(temp_path, "wb") as fp:
                        fp.write(header)
                        fp.write(tail)
                    os.replace(temp_path, path)
                finally:
                    try:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                    except Exception:
                        pass
            with open(path, "ab") as fp:
                fp.write(line)
        except Exception:
            # 诊断日志失败不应影响扫描和注册表写入。
            pass

    def _warn(self, text):
        if text and text not in self.status["warnings"]:
            self.status["warnings"].append(text)
            self._log("WARN", text)

    # --------------------------------------------------------------------------
    # TVBox 标准接口
    # --------------------------------------------------------------------------
    def homeContent(self, filter):
        self._ensure_initialized()
        # 推荐（首页 list）由 App 固定置顶为第一个标签，设置紧随其后固定为第二个标签。
        classes = [
            {
                "type_id": self.SCAN_SETTINGS_TID,
                "type_name": "设置" + (" *" if self.config_dirty else ""),
            },
            {
                "type_id": self.NETWORK_ROOTS_TID,
                "type_name": "🌐 网络目录 ({})".format(len(self.network_roots)),
            },
        ]
        if self.cache["sources"]:
            classes.append(
                {
                    "type_id": self.BROWSER_ROOT_TID,
                    "type_name": "文件浏览 ({})".format(len(self.cache["sources"])),
                    "type_flag": "1",
                }
            )
        perm_count = sum(
            1
            for source in self.cache["sources"]
            if self._source_load_state(source) == "perm"
        )
        if perm_count:
            classes.append(
                {
                    "type_id": self.LOADED_TID,
                    "type_name": "已加载站点 ({})".format(perm_count),
                }
            )
        favorite_count = sum(
            1
            for source in self.cache["sources"]
            if self._source_metadata_for(source).get("favorite")
        )
        if favorite_count:
            classes.append(
                {
                    "type_id": self.FAVORITES_TID,
                    "type_name": "收藏 ({})".format(favorite_count),
                }
            )
        tag_counts = {}
        for source in self.cache["sources"]:
            for tag in self._source_metadata_for(source).get("tags", []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        for tag in sorted(tag_counts, key=lambda value: value.casefold()):
            classes.append(
                {
                    "type_id": self.TAG_TID_PREFIX + urllib.parse.quote(tag, safe=""),
                    "type_name": "{} ({})".format(tag, tag_counts[tag]),
                }
            )
        ignored_count = len(self.cache.get("ignored", []))
        if ignored_count:
            classes.append(
                {
                    "type_id": "ignored",
                    "type_name": "已屏蔽 ({})".format(ignored_count),
                }
            )
        backup_count = len(self._list_backup_files())
        if backup_count:
            classes.append(
                {
                    "type_id": self.BACKUPS_TID,
                    "type_name": "历史备份 ({})".format(backup_count),
                }
            )
        return {"class": classes, "list": self._home_items()}

    def homeVideoContent(self):
        self._ensure_initialized()
        return {"list": self._home_items()}

    @staticmethod
    def _icon(key):
        return _UI_ICONS.get(key, "")

    def _home_items(self):
        scanned_count = len(self.cache["sources"])
        loaded_count = len(self._effective_selected_identities())
        temp_count = len(self.temp_identities)
        if self.status["written"] or loaded_count:
            status_name = "运行状态"
        elif scanned_count:
            status_name = "已扫描 · 待加载"
        else:
            status_name = "待扫描"
        status_remarks = "扫描 {} 个 · 已加载 {} 个".format(
            scanned_count, loaded_count
        )
        if temp_count:
            status_remarks += "（临时 {}）".format(temp_count)
        items = [
            {
                "vod_id": self.STATUS_ID,
                "vod_name": status_name,
                "vod_pic": self._icon("status"),
                "vod_remarks": status_remarks,
                "action": self.ACTION_OPEN_STATUS,
            },
        ]
        scan_remarks = (
            "重新扫描，{} 个文件可浏览".format(scanned_count)
            if scanned_count
            else "只扫描设定目录，不改动配置"
        )
        load_remarks = (
            "把 {} 个扫描结果全部永久加载".format(scanned_count)
            if scanned_count
            else "请先扫描"
        )
        items.extend(
            [
            {
                "vod_id": self.SCAN_NOW_ID,
                "vod_name": "扫描",
                "vod_pic": self._icon("scan"),
                "vod_remarks": scan_remarks,
                "action": self.ACTION_OPEN_SCAN_ONLY,
            },
            {
                "vod_id": self.LOAD_ALL_ID,
                "vod_name": "加载全部",
                "vod_pic": self._icon("download"),
                "vod_remarks": load_remarks,
                "action": self.ACTION_OPEN_LOAD_ALL,
            },
            {
                "vod_id": self.TEST_SITES_ID,
                "vod_name": "站点功能测活",
                "vod_pic": self._icon("test"),
                "vod_remarks": "并发检测首页 / 分类 / 搜索",
                "action": self.ACTION_OPEN_TEST_SITES,
            },
            {
                "vod_id": self.RETEST_SITES_ID,
                "vod_name": "全部重新检测",
                "vod_pic": self._icon("retest"),
                "vod_remarks": "清除缓存后重新检测",
                "action": self.ACTION_OPEN_RETEST_SITES,
            },
            {
                "vod_id": self.AUTO_CLASSIFY_ID,
                "vod_name": "自动分类",
                "vod_pic": self._icon("classify"),
                "vod_remarks": "顶层文件归入类型子目录",
                "action": self.ACTION_OPEN_AUTO_CLASSIFY,
            },
            {
                "vod_id": self.CLEAR_SITES_ID,
                "vod_name": "清除自动站点",
                "vod_pic": self._icon("trash"),
                "vod_remarks": "保留手工注入站点",
                "action": self.ACTION_OPEN_CLEAR_SITES,
            },
            {
                "vod_id": self.FULL_CLEAR_ID,
                "vod_name": "一键清除",
                "vod_pic": self._icon("reset"),
                "vod_remarks": "清除加载、下载、缓存和收藏；保留用户原始文件",
                "action": self.ACTION_OPEN_FULL_CLEAR,
            },
            ]
        )
        return items

    def categoryContent(self, tid, pg, filter, ext):
        self._ensure_initialized()
        page = self._page_number(pg)
        if tid == "all":
            items = list(self.cache["sources"])
        elif tid == self.FAVORITES_TID:
            items = [
                item for item in self.cache["sources"]
                if self._source_metadata_for(item).get("favorite")
            ]
        elif str(tid).startswith(self.TAG_TID_PREFIX):
            tag = urllib.parse.unquote(
                str(tid)[len(self.TAG_TID_PREFIX) :]
            ).casefold()
            items = [
                item for item in self.cache["sources"]
                if tag in {
                    str(value).casefold()
                    for value in self._source_metadata_for(item).get("tags", [])
                }
            ]
        elif str(tid).startswith("type:"):
            source_type = str(tid).split(":", 1)[1].upper()
            items = [item for item in self.cache["sources"] if item["type"] == source_type]
        elif tid == "ignored":
            # 已屏蔽分类：顶部提供"全部恢复"，点击卡片走恢复逻辑
            ignored_items = list(self.cache.get("ignored", []))
            items = []
            if ignored_items:
                items.append(
                    {
                        "loaded_action": True,
                        "action_id": "unblock_all",
                        "name": "全部恢复",
                        "remarks": "恢复全部 {} 个已屏蔽的站点".format(
                            len(ignored_items)
                        ),
                        "action": self.ACTION_UNBLOCK_ALL,
                    }
                )
            items.extend(ignored_items)
        elif str(tid) == self.BROWSER_ROOT_TID or str(tid).startswith(
            self.BROWSER_TID_PREFIX
        ):
            encoded = str(tid)[len(self.BROWSER_TID_PREFIX) :]
            dir_path = urllib.parse.unquote(encoded) if encoded else ""
            return self._paged_result(self._browser_items(dir_path), page)
        elif str(tid) == self.LOADED_TID:
            return self._paged_result(self._loaded_items(), page)
        elif tid == self.SCAN_SETTINGS_TID:
            return self._paged_result(self._scan_setting_items(), page)
        elif tid == self.NETWORK_ROOTS_TID:
            return self._paged_result(self._network_root_items(), page)
        elif tid == self.BACKUPS_TID:
            return self._paged_result(self._backup_items(), page)
        else:
            items = []
        return self._paged_result(items, page)

    def _network_protocol_label(self, protocol):
        return {
            "auto": "自动识别",
            "http": "HTTP目录",
            "webdav": "WebDAV",
            "github": "GitHub",
            "gitee": "Gitee",
        }.get(str(protocol or "auto"), "自动识别")

    def _network_status_label(self, root):
        status = str(root.get("last_status", "") or "")
        if self._network_sync_running and self._network_sync_root_id == root.get(
            "id"
        ):
            message = self._network_sync_message or "同步中"
            return "🔄 {}".format(message)
        return {
            "ok": "🟢 {}",
            "warn": "🟡 {}",
            "fail": "🔴 {}",
        }.get(status, "⚪ 未同步").format(root.get("last_message", "") or "")

    def _network_root_items(self):
        """网络目录管理页：添加入口 + 全部同步 + 每个根一张卡。"""
        items = [
            {
                "net_action": True,
                "action_id": self.NETWORK_ADD_ID,
                "name": "➕ 添加网络目录",
                "pic_key": "download",
                "remarks": "支持 HTTP 静态目录 / WebDAV / GitHub / Gitee",
                "action": self.ACTION_NET_ADD,
            }
        ]
        enabled_count = sum(
            1 for item in self.network_roots if item.get("enabled", True)
        )
        if enabled_count:
            sync_remarks = (
                "后台增量同步全部 {} 个已启用目录".format(enabled_count)
                if not self._network_sync_running
                else "正在同步：{}".format(self._network_sync_message or "…")
            )
            items.append(
                {
                    "net_action": True,
                    "action_id": self.NETWORK_SYNC_ALL_ID,
                    "name": "🔄 全部同步",
                    "pic_key": "retest",
                    "remarks": sync_remarks,
                    "action": self.ACTION_NET_SYNC_ALL,
                }
            )
        for root in self.network_roots:
            enabled = bool(root.get("enabled", True))
            remarks_parts = [
                self._network_protocol_label(root.get("protocol")),
                "已启用" if enabled else "已停用",
                "{} 个文件".format(int(root.get("file_count", 0) or 0)),
            ]
            if root.get("last_sync"):
                remarks_parts.append("上次同步 {}".format(root["last_sync"]))
            status_text = self._network_status_label(root)
            if status_text:
                remarks_parts.append(status_text)
            name = "🌐 {}".format(root.get("name", "网络目录"))
            if not enabled:
                name = "⏸ " + name
            items.append(
                {
                    "net_action": True,
                    "action_id": root.get("id", ""),
                    "name": name,
                    "pic_key": "folder",
                    "remarks": " · ".join(remarks_parts),
                    "action": self.ACTION_NET_ROOT_PREFIX + str(root.get("id", "")),
                }
            )
        return items

    def _browser_enabled_roots(self):
        """当前启用的扫描根（类型，绝对真实路径），顺序同 SCAN_ROOTS。

        v8.0：追加已启用网络根的本地镜像目录。
        """
        roots = []
        for spec in self._effective_scan_roots():
            root_type = str(spec.get("type", "")).upper()
            root_path = str(spec.get("path", "")).strip()
            if not root_path:
                continue
            if not self.type_enabled.get(root_type, True):
                continue
            roots.append(
                (
                    root_type,
                    os.path.realpath(
                        os.path.abspath(os.path.expanduser(root_path))
                    ),
                )
            )
        return roots

    @staticmethod
    def _safe_path_within(target, base):
        try:
            target_norm = os.path.normcase(
                os.path.realpath(os.path.abspath(target))
            )
            base_norm = os.path.normcase(os.path.realpath(os.path.abspath(base)))
            return target_norm == base_norm or os.path.commonpath(
                [target_norm, base_norm]
            ) == base_norm
        except Exception:
            return False

    def _root_folder_name(self, root_path, root_type):
        base_name = os.path.basename(os.path.normpath(root_path)) or root_path
        return "{}（{}）".format(
            base_name, self.TYPE_LABEL.get(root_type, root_type)
        )

    def _browser_root_groups(self):
        """去重后的浏览器根分组：[(真实路径, [类型...], 显示名), ...]。

        多个类型根指向同一物理目录时（扫描目录回退模式：该目录下没有
        非空的类型子目录，PY/JS/CSP/HTML 都回退到目录本身），合并为
        一张卡片，避免同一批文件在 4 个类型卡片里重复显示。单一根仍
        保留类型后缀（如 Python（PY））。
        """
        groups = []
        index_by_norm = {}
        for root_type, root_path in self._browser_enabled_roots():
            norm = os.path.normcase(root_path)
            if norm in index_by_norm:
                groups[index_by_norm[norm]][1].append(root_type)
            else:
                index_by_norm[norm] = len(groups)
                groups.append([root_path, [root_type]])
        result = []
        network_names = self._network_root_display_map()
        for root_path, root_types in groups:
            network_name = network_names.get(os.path.normcase(root_path))
            if network_name:
                display_name = network_name
            elif len(root_types) > 1:
                display_name = (
                    os.path.basename(os.path.normpath(root_path)) or root_path
                )
            else:
                display_name = self._root_folder_name(root_path, root_types[0])
            result.append((root_path, root_types, display_name))
        return result

    def _browser_items(self, dir_path):
        """文件浏览器：根页列扫描根，子页列下级文件夹与文件卡。"""
        sources = self.cache.get("sources", [])
        groups = self._browser_root_groups()
        if not dir_path:
            items = []
            for root_path, _root_types, display_name in groups:
                root_norm = os.path.normcase(root_path)
                root_sources = [
                    source
                    for source in sources
                    if os.path.normcase(
                        os.path.realpath(
                            os.path.abspath(str(source.get("scan_root", "")))
                        )
                    )
                    == root_norm
                ]
                if not root_sources:
                    continue
                items.append(
                    {
                        "browser_folder": True,
                        "browser_name": "📁 " + display_name,
                        "browser_dir": root_path,
                        "browser_remarks": "{} 项".format(len(root_sources)),
                    }
                )
            return items
        real_dir = os.path.realpath(os.path.abspath(os.path.expanduser(dir_path)))
        # 选“最深、最具体”的匹配根：回退模式下缺失类型目录会回退到父目录
        # （如 js 不存在时 JS 根=webhome，而 HTML 根=webhome/html），父根
        # 同样包含子目录，首个匹配会错误地把 html 文件归到父根导致空页。
        matched_root = None
        best_len = -1
        for root_path, _root_types, _display_name in groups:
            if not self._safe_path_within(real_dir, root_path):
                continue
            root_len = len(os.path.normcase(root_path))
            if root_len > best_len:
                best_len = root_len
                matched_root = root_path
        if not matched_root:
            return []
        rel_dir = os.path.relpath(real_dir, matched_root)
        prefix = "" if rel_dir == "." else rel_dir.replace(os.sep, "/").strip("/") + "/"
        subdirs = {}
        files = []
        matched_norm = os.path.normcase(matched_root)
        for source in sources:
            scan_root = str(source.get("scan_root", "")).strip()
            if not scan_root:
                continue
            scan_norm = os.path.normcase(
                os.path.realpath(os.path.abspath(scan_root))
            )
            if scan_norm != matched_norm:
                continue
            rel = str(source.get("relative_in_root", "")).replace("\\", "/")
            if not rel.startswith(prefix):
                continue
            tail = rel[len(prefix):]
            if not tail:
                continue
            if "/" in tail:
                sub_name = tail.split("/", 1)[0]
                subdirs[sub_name] = subdirs.get(sub_name, 0) + 1
            else:
                files.append(
                    {"browser_file": True, "source_id": source["id"]}
                )
        folders = []
        for name in sorted(subdirs.keys(), key=str.lower):
            child_dir = os.path.join(matched_root, prefix.rstrip("/"), name)
            folders.append(
                {
                    "browser_folder": True,
                    "browser_name": "📁 " + name,
                    "browser_dir": child_dir,
                    "browser_remarks": "{} 项".format(subdirs[name]),
                }
            )
        # 目录内有文件时，顶部加批量选择入口
        result_items = []
        if files:
            result_items.append(
                {
                    "browser_action": True,
                    "action_id": "batch_select",
                    "name": "批量选择",
                    "remarks": "选择当前目录站点批量加载/移出",
                    "action": self.ACTION_BROWSER_BATCH_SELECT + ":" + urllib.parse.quote(dir_path, safe=""),
                }
            )
        result_items.extend(folders)
        result_items.extend(files)
        return result_items

    def _loaded_items(self):
        """已永久加载站点列表：卡片与文件浏览一致，点击仍走三选一窗口。"""
        perm_sources = [
            source
            for source in self.cache.get("sources", [])
            if self._source_load_state(source) == "perm"
        ]
        if not perm_sources:
            return []
        items = [
            {
                "loaded_action": True,
                "action_id": "unload_all_perm",
                "name": "全部移出",
                "remarks": "移出全部 {} 个已永久加载的站点".format(len(perm_sources)),
                "action": self.ACTION_UNLOAD_ALL_PERM,
            },
            {
                "loaded_action": True,
                "action_id": "convert_all_temp",
                "name": "全部改为临时",
                "remarks": "把全部 {} 个永久站点改为临时加载".format(len(perm_sources)),
                "action": self.ACTION_CONVERT_ALL_TO_TEMP,
            },
        ]
        for source in perm_sources:
            items.append({"browser_file": True, "source_id": source["id"]})
        return items

    def _scan_setting_items(self):
        items = [
            {
                "id": self.SCAN_BASE_PATH_ID,
                "name": "扫描目录",
                "type": "PATH",
                "relative_in_root": self.scan_base_path
                or "自动探测：{}".format(self.local_base_dir),
                "settings": True,
                "scan_base_path": True,
            },
            {
                "id": self.RESET_SCAN_BASE_ID,
                "name": "恢复默认目录",
                "type": "RESET_PATH",
                "relative_in_root": self.LOCAL_BASE_DIR,
                "settings": True,
                "reset_scan_base": True,
            },
            {
                "id": "setting_scan_types",
                "name": "扫描类型",
                "type": "TYPES",
                "relative_in_root": "已启用：{}".format(
                    "、".join(
                        self.TYPE_LABEL.get(source_type, source_type)
                        for source_type in self.TYPE_ORDER
                        if self.pending_type_enabled.get(
                            source_type,
                            self.type_enabled.get(source_type, True),
                        )
                    )
                    or "无"
                ) + " · 18+：{}".format(
                    "扫描" if self.pending_block_adult_sites else "屏蔽"
                ),
                "settings": True,
                "scan_types": True,
            },
            {
                "id": "setting_apply",
                "name": "应用并扫描"
                if self.config_dirty
                else "扫描目录",
                "type": "APPLY",
                "relative_in_root": "应用待生效的类型变更并扫描"
                if self.config_dirty
                else "只扫描，不加载（结果见文件浏览）",
                "settings": True,
                "apply": True,
                "enabled": bool(self.config_dirty),
            },
            {
                "id": "setting_auto_scan",
                "name": "自动补扫",
                "type": "AUTO_SCAN",
                "relative_in_root": (
                    "已暂停，手动扫描一次后恢复"
                    if self.auto_scan_on_empty and self.auto_scan_suspended
                    else "无扫描快照时进入自动扫描一次"
                ),
                "settings": True,
                "auto_scan": True,
                "enabled": bool(self.auto_scan_on_empty),
            },
            {
                "id": "setting_auto_prune",
                "name": "自动清理屏蔽站点",
                "type": "AUTO_PRUNE",
                "relative_in_root": (
                    "测活结束后把屏蔽站点移出配置，源文件保留，已清理 {} 个".format(
                        len(self.pruned_sources)
                    )
                    if self.auto_prune_blocked
                    else "关闭：测活只屏蔽不移除"
                ),
                "settings": True,
                "auto_prune": True,
                "enabled": bool(self.auto_prune_blocked),
            },
            {
                "id": "setting_source_metadata",
                "name": "收藏与标签",
                "type": "SOURCE_METADATA",
                "relative_in_root": "已管理 {} 个站点".format(
                    len(self.source_metadata)
                ),
                "settings": True,
                "source_metadata": True,
            },
            {
                "id": "setting_export_profile",
                "name": "导出管理配置",
                "type": "EXPORT_PROFILE",
                "relative_in_root": self._management_profile_path(),
                "settings": True,
                "export_profile": True,
            },
            {
                "id": "setting_import_profile",
                "name": "导入管理配置",
                "type": "IMPORT_PROFILE",
                "relative_in_root": "从 local-media-profile.json 导入，导入前自动备份",
                "settings": True,
                "import_profile": True,
            },
        ]
        return items

    def _backup_items(self):
        items = []
        for path in self._list_backup_files():
            try:
                registry = self._validate_registry_backup(path)
                count = len(registry.get("items", []))
                modified = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(path))
                )
                items.append(
                    {
                        "id": "backup_" + self._digest(os.path.basename(path), 12),
                        "name": "恢复至 " + modified,
                        "type": "BACKUP",
                        "relative_in_root": "{} 个条目".format(count),
                        "backup": True,
                        "path": path,
                    }
                )
            except Exception as exc:
                self._warn("历史备份读取失败：{}（{}）".format(path, exc))
        if items:
            items.append(
                {
                    "id": self.DELETE_BACKUPS_ID,
                    "name": "删除历史备份",
                    "type": "DELETE_BACKUP",
                    "relative_in_root": "仅保留最近 1 份，点击删除",
                    "delete_backup": True,
                }
            )
        return items

    def detailContent(self, array):
        self._ensure_initialized()
        source_id = str(array[0]) if isinstance(array, (list, tuple)) and array else str(array or "")
        if source_id == self.STATUS_ID:
            return {"list": [self._status_detail()]}
        if source_id == self.AUTO_CLASSIFY_ID:
            # 详情页是 action() 之外的旁路入口，需自行复用同一套并发守卫，
            # 否则后台测活或下载进行中时会与其争用 cache 和目录。
            with self.lock:
                if self._site_test_is_running():
                    blocked = "后台检测进行中，请待本批完成后再执行"
                elif self._package_download_running():
                    blocked = "本地包下载安装中，请完成后再执行"
                elif self._repository_sync_running():
                    blocked = "在线仓库同步中，请完成后再执行"
                else:
                    blocked = ""
                if not blocked:
                    summary, content = self._run_auto_classify()
            if blocked:
                detail = self._status_detail()
                detail["vod_name"] = "自动分类"
                detail["vod_pic"] = self._icon("classify")
                detail["vod_remarks"] = blocked
                detail["vod_content"] = blocked + "\n\n" + detail.get("vod_content", "")
                return {"list": [detail]}
            detail = self._status_detail()
            detail["vod_name"] = "自动分类"
            detail["vod_pic"] = self._icon("classify")
            detail["vod_remarks"] = summary
            detail["vod_content"] = content + "\n\n" + detail.get("vod_content", "")
            return {"list": [detail]}
        if source_id in (self.SCAN_NOW_ID, self.LOAD_ALL_ID):
            # 正常路径由卡片 action 拦截；此处是部分壳“点击进详情”的兜底。
            result = self.action(
                self.ACTION_OPEN_SCAN_ONLY
                if source_id == self.SCAN_NOW_ID
                else self.ACTION_OPEN_LOAD_ALL
            )
            detail = self._status_detail()
            message = str(result.get("msg", "")) if isinstance(result, dict) else ""
            if message:
                detail["vod_remarks"] = message
            return {"list": [detail]}
        if source_id == self.RESCAN_ID:
            allowed, duplicate_message = self._begin_manual_scan_request()
            if not allowed:
                detail = self._status_detail()
                detail["vod_remarks"] = duplicate_message
                detail["vod_content"] = duplicate_message + "\n\n" + detail.get(
                    "vod_content", ""
                )
                return {"list": [detail]}
            try:
                with self.lock:
                    if self._site_test_is_running():
                        detail = self._status_detail()
                        detail["vod_remarks"] = "后台检测进行中"
                        detail["vod_content"] = (
                            "后台检测进行中，请待本批完成后再扫描。\n\n"
                            + detail.get("vod_content", "")
                        )
                        return {"list": [detail]}
                    if self._package_download_running():
                        detail = self._status_detail()
                        detail["vod_remarks"] = "本地包下载安装中"
                        detail["vod_content"] = (
                            "本地包下载安装中，请完成后再扫描。\n\n"
                            + detail.get("vod_content", "")
                        )
                        return {"list": [detail]}
                    if self._repository_sync_running():
                        detail = self._status_detail()
                        detail["vod_remarks"] = "在线仓库同步中"
                        detail["vod_content"] = (
                            "在线仓库同步中，请完成后再扫描。\n\n"
                            + detail.get("vod_content", "")
                        )
                        return {"list": [detail]}
                    if self._refresh_locked(
                        allow_empty=not any(self.type_enabled.values())
                    ):
                        self._show_author_scan_surprise()
                        self._reload_app_vod_config(
                            expected_keys=self._generated_registry_keys()
                        )
                    self.inited = True
                return {"list": [self._status_detail()]}
            finally:
                self._finish_manual_scan_request()

        source = self.cache["source_index"].get(source_id)
        if not source:
            return {"list": [{"vod_name": "站点不存在", "vod_content": "请重新扫描后再试。"}]}

        site_text = json.dumps(source["site"], ensure_ascii=False, indent=2)
        validation = source.get("validation") or "静态检查未发现明显问题"
        test_result = source.get("test_result", {})
        test_text = (
            "{} · {} · {} · {} · {} ms · {}".format(
                self._test_result_label(test_result),
                test_result.get("checked_at", "-"),
                test_result.get("test_stage", "-") or "-",
                test_result.get("playback_state", "-") or "-",
                test_result.get("elapsed_ms", "-"),
                test_result.get("detail", ""),
            )
            if isinstance(test_result, dict) and test_result
            else "未检测"
        )
        content = (
            "类型：{type}\n"
            "文件：{path}\n"
            "相对路径：{relative}\n"
            "稳定标识：{identity}\n"
            "检查：{validation}\n\n"
            "功能测活：{test_result}\n\n"
            "最近检测历史：\n{test_history}\n\n"
            "收藏：{favorite}\n"
            "标签：{tags}\n\n"
            "生成的站点配置：\n{site}\n\n"
            "运行环境：{app_mode}\n"
            "本地配置：{output}\n"
            "配置变更后 App 将自动重载站点列表。"
        ).format(
            type=self.TYPE_LABEL.get(source["type"], source["type"]),
            path=source["path"],
            relative=source["relative_in_root"],
            identity=source["identity"],
            validation=validation,
            test_result=test_text,
            test_history=self._site_test_history_text(source["identity"]),
            favorite="是" if self._source_metadata_for(source).get("favorite") else "否",
            tags="、".join(self._source_metadata_for(source).get("tags", [])) or "无",
            site=site_text,
            app_mode=self._app_mode_label(),
            output=(
                "{} / {}".format(self.ok_config_a, self.ok_config_b)
                if self.app_mode == self.APP_MODE_OKTV
                else self.output_path
            ),
        )
        return {
            "list": [
                {
                    "vod_id": source_id,
                    "vod_name": source["name"],
                    "vod_pic": "",
                    "vod_remarks": self.TYPE_LABEL.get(
                        source["type"], source["type"]
                    ),
                    "vod_content": content,
                }
            ]
        }

    def _status_detail(self):
        warning_text = "\n".join("- " + item for item in self.status["warnings"][:20]) or "无"
        error_text = self.status["error"] or "无"
        recent_log = self._diagnostic_log_tail() or "无"
        test_counts = {"available": 0, "unavailable": 0, "limited": 0}
        playback_counts = {}
        for result in list(self.site_test_results.values()):
            state = str(result.get("state", "")) if isinstance(result, dict) else ""
            if state in test_counts:
                test_counts[state] += 1
            if isinstance(result, dict):
                playback = str(result.get("playback_state", "") or "").strip()
                if playback:
                    playback_counts[playback] = playback_counts.get(playback, 0) + 1
        playback_text = " · ".join(
            "{} {}".format(name, count)
            for name, count in sorted(playback_counts.items())
        ) or "无"
        content = (
            "版本：{version}\n"
            "运行环境：{app_mode}\n"
            "扫描方式：手动 + 自动补扫（{auto_scan}）\n"
            "严格识别：{strict}\n"
            "待应用配置：{dirty}\n"
            "类型开关：{types}\n"
            "18+ 站点：{adult_mode}\n"
            "扫描时间：{scan_time}\n"
            "发现文件：{found}\n"
            "加载选择：永久 {loaded_perm} · 临时 {loaded_temp}\n"
            "有效站点：{included}\n"
            "集成直播：{generated_lives}\n"
            "直播去重：{duplicate_lives}\n"
            "播放上下文：{context_packages} 包 / {context_fields} 字段\n"
            "屏蔽站点：{ignored}\n"
            "清理过期屏蔽项：{stale_ignored}\n"
            "跳过文件：{skipped}\n"
            "自动屏蔽 18+ 站点：{adult_filtered}\n"
            "兼容性拦截：{compatibility_blocked}\n"
            "重复项：{duplicates}\n"
            "缓存命中 / 重检：{cache_hits}/{cache_misses}\n"
            "功能测活：可用 {test_available} · 失效 {test_unavailable} · 受限 {test_limited}\n"
            "播放验证：{playback_text}\n"
            "保留注入项：{manual}\n"
            "自动注入项：{generated}\n"
            "变更预览：+{added} ~{updated} -{removed} ={unchanged}\n"
            "写入状态：{state}\n"
            "错误：{error}\n\n"
            "警告：\n{warnings}\n\n"
            "本地配置输出：{output}\n\n"
            "扫描开关设置：{settings}\n\n"
            "扫描目录配置：{roots_config}\n"
            "诊断日志：{log_path}（上限 {max_log_kb} KB）\n"
            "扫描根目录：{scan_base}\n"
            "解析服务：{package_service}\n"
            "接口开关：{package_download}\n"
            "接口网址：\n{package_url}\n"
            "下载状态：{package_state}\n"
            "安装目录：{package_target}\n"
            "在线仓库：{repository_summary}\n"
            "仓库地址：\n{repository_urls}\n"
            "仓库同步：{repository_state}\n"
            "仓库安装规则：<类型目录>/<备注名>/<相对路径>\n"
            "扫描上限：文件 {max_files} · 深度 {max_depth} · 单文件 {max_size} 字节\n\n"
            "最近任务日志：\n{recent_log}\n\n"
            "v8.0：扫描与加载分离——「扫描」只更新文件浏览结果，不改动配置；\n"
            "点击「加载全部」或在文件浏览中选择文件后才写入并重载。\n"
            "原基础配置与手工注入项始终保留。\n\n"
            "----------------\n"
            "秋色正好，江 晚枫来过。"
        ).format(
            version=self.VERSION,
            app_mode=self._app_mode_label(),
            auto_scan="暂停"
            if self.auto_scan_on_empty and self.auto_scan_suspended
            else ("开" if self.auto_scan_on_empty else "关"),
            strict="开启" if self.strict_recognition else "关闭",
            dirty="是" if self.config_dirty else "否",
            types=" ".join(
                "{}:{}{}".format(
                    self.TYPE_LABEL.get(source_type, source_type),
                    "开" if self.type_enabled.get(source_type, True) else "关",
                    "->{}".format(
                        "开"
                        if self.pending_type_enabled.get(
                            source_type, self.type_enabled.get(source_type, True)
                        )
                        else "关"
                    )
                    if self.pending_type_enabled.get(
                        source_type, self.type_enabled.get(source_type, True)
                    )
                    != self.type_enabled.get(source_type, True)
                    else "",
                )
                for source_type in self.TYPE_ORDER
            ),
            adult_mode="{}{}".format(
                "扫描" if self.block_adult_sites else "屏蔽",
                " -> {}".format(
                    "扫描" if self.pending_block_adult_sites else "屏蔽"
                )
                if self.pending_block_adult_sites != self.block_adult_sites
                else "",
            ),
            scan_time=self.status["scan_time"],
            found=self.status["found"],
            loaded_perm=(
                len(self.selected_identities)
                if isinstance(self.selected_identities, set)
                else 0
            ),
            loaded_temp=len(self.temp_identities),
            included=self.status["included"],
            generated_lives=self.status["generated_lives"],
            duplicate_lives=self.status["duplicate_lives"],
            context_packages=len(self.cache.get("contexts", [])),
            context_fields=sum(
                len(item.get("context", {}))
                for item in self.cache.get("contexts", [])
                if isinstance(item, dict)
                and isinstance(item.get("context"), dict)
            ),
            ignored=self.status["ignored"],
            stale_ignored=self.status["stale_ignored_removed"],
            skipped=self.status["skipped"],
            adult_filtered=self.status["adult_filtered"],
            compatibility_blocked=self.status["compatibility_blocked"],
            duplicates=self.status["duplicates"],
            cache_hits=self.status["cache_hits"],
            cache_misses=self.status["cache_misses"],
            test_available=test_counts["available"],
            test_unavailable=test_counts["unavailable"],
            test_limited=test_counts["limited"],
            playback_text=playback_text,
            manual=self.status["manual_sites"],
            generated=self.status["generated_sites"],
            added=self.status["added_sites"],
            updated=self.status["updated_sites"],
            removed=self.status["removed_sites"],
            unchanged=self.status["unchanged_sites"],
            state=self.status["write_state"],
            error=error_text,
            warnings=warning_text,
            output=(
                "{} / {}".format(self.ok_config_a, self.ok_config_b)
                if self.app_mode == self.APP_MODE_OKTV
                else self.output_path
            ),
            settings=self.settings_path,
            roots_config=self.roots_config_path,
            log_path=self._diagnostic_log_path(),
            max_log_kb=max(1, int(self.max_log_size) // 1024),
            scan_base=self.scan_base_path or "自动探测 ({})".format(self.local_base_dir),
            package_service=self.package_service_url or "未配置",
            package_download=self._package_download_sites_summary(),
            package_url="\n".join(
                "- {} [{}]: {}".format(
                    item.get("name", "未命名"),
                    self._package_download_site_type_label(item),
                    item.get("url", ""),
                )
                for item in self.package_download_sites
            ) or "- 无",
            package_state="{}{}".format(
                self._package_download_state,
                " · " + self._package_download_message
                if self._package_download_message
                else "",
            ),
            package_target=os.path.join(self._package_root(), "<接口备注名>"),
            repository_summary=self._online_repositories_summary(),
            repository_urls="\n".join(
                "- {} [{}] {} 个文件: {}".format(
                    item.get("name", "未命名"),
                    "开" if self._as_bool(item.get("enabled", True), True) else "关",
                    int(item.get("file_count", 0) or 0),
                    item.get("url", ""),
                )
                for item in self.online_repositories
            ) or "- 无",
            repository_state="{}{}".format(
                self._repository_sync_state,
                " · " + self._repository_sync_message
                if self._repository_sync_message
                else "",
            ),
            recent_log=recent_log,
            max_files=self.max_scan_files,
            max_depth=self.max_scan_depth,
            max_size=self.max_source_size,
        )
        return {
            "vod_id": self.STATUS_ID,
            "vod_name": "运行状态与诊断",
            "vod_pic": self._icon("status"),
            "vod_remarks": self.status["write_state"],
            "vod_content": content,
        }

    def searchContent(self, key, quick, pg="1"):
        self._ensure_initialized()
        keyword = str(key or "").strip().lower()
        page = self._page_number(pg)
        if not keyword:
            items = []
        else:
            matched = [
                source
                for source in self.cache["sources"]
                if keyword in source["name"].lower()
                or keyword in source["relative_in_root"].lower()
                or keyword in source["type"].lower()
                or any(
                    keyword in str(tag).lower()
                    for tag in self._source_metadata_for(source).get("tags", [])
                )
            ]
            # v7.0：搜索结果同样以文件卡呈现，点击弹出加载三选一窗口。
            items = [
                {"browser_file": True, "source_id": source["id"]}
                for source in matched
            ]
        return self._paged_result(items, page)

    def _paged_result(self, items, page):
        total = len(items)
        page_size = max(1, int(self.page_size))
        page_count = max(1, (total + page_size - 1) // page_size)
        if page > page_count:
            page_items = []
        else:
            start = (page - 1) * page_size
            page_items = items[start : start + page_size]
        return {
            "page": page,
            "pagecount": page_count,
            "limit": page_size,
            "total": total,
            "list": [self._source_vod(item) for item in page_items],
        }

    def _source_state_icon(self, source):
        if source.get("adult_blocked"):
            return "🔞 "
        result = source.get("test_result", {})
        state = str(result.get("state", "")) if isinstance(result, dict) else ""
        if state == "unavailable":
            return "⛔ "
        if state == "limited":
            return "⚠ "
        return "🚫 " if source.get("ignored") else ""

    def _source_vod(self, source):
        if source.get("browser_folder"):
            # vod_tag=folder：壳以 vod_id 为 typeId 回调 categoryContent 进目录。
            return {
                "vod_id": self.BROWSER_TID_PREFIX
                + urllib.parse.quote(source["browser_dir"], safe=""),
                "vod_name": source["browser_name"],
                "vod_pic": self._icon("folder"),
                "vod_remarks": source["browser_remarks"],
                "vod_tag": "folder",
            }
        if source.get("browser_action"):
            return {
                "vod_id": source["action_id"],
                "vod_name": source["name"],
                "vod_pic": self._icon("switches"),
                "vod_remarks": source["remarks"],
                "action": source["action"],
            }
        if source.get("loaded_action"):
            return {
                "vod_id": source["action_id"],
                "vod_name": source["name"],
                "vod_pic": self._icon("trash"),
                "vod_remarks": source["remarks"],
                "action": source["action"],
            }
        if source.get("net_action"):
            return {
                "vod_id": source["action_id"],
                "vod_name": source["name"],
                "vod_pic": self._icon(source.get("pic_key", "folder")),
                "vod_remarks": source["remarks"],
                "action": source["action"],
            }
        if source.get("browser_file"):
            real = self.cache.get("source_index", {}).get(
                source["source_id"], {}
            )
            state = self._source_load_state(real)
            state_label = {
                "perm": "🟢 永久加载",
                "temp": "🟡 临时加载",
                "none": "⚪ 未加载",
            }.get(state, "⚪ 未加载")
            if state == "perm" and str(real.get("type", "")).upper() != "PY":
                # 非 PY 类型仅支持一种加载方式，统一显示“已加载”。
                state_label = "🟢 已加载"
            # 附加测活状态（如果有）
            test_label = ""
            identity = str(real.get("identity", ""))
            if identity:
                test_result = self.site_test_results.get(identity, {})
                if isinstance(test_result, dict) and test_result.get("state"):
                    test_state = str(test_result["state"])
                    test_label = " · 测活:{}".format(
                        self._test_result_label(test_result)
                    )
            return {
                "vod_id": str(real.get("id", source["source_id"])),
                "vod_name": str(
                    real.get("name")
                    or real.get("base_name")
                    or source["source_id"]
                ),
                "vod_pic": "",
                "vod_remarks": "{} · {}{}".format(
                    real.get("type", ""), state_label, test_label
                ),
                "action": self.ACTION_LOAD_CHOICE_PREFIX
                + str(real.get("id", "")),
            }
        if source.get("delete_backup"):
            return {
                "vod_id": source["id"],
                "vod_name": source["name"],
                "vod_pic": self._icon("trash"),
                "vod_remarks": source["relative_in_root"],
                "action": self.ACTION_OPEN_PREFIX + self.ACTION_DELETE_BACKUPS,
            }
        if source.get("backup"):
            return {
                "vod_id": source["id"],
                "vod_name": source["name"],
                "vod_pic": self._icon("undo"),
                "vod_remarks": source["relative_in_root"],
                "action": self.ACTION_OPEN_PREFIX + self.ACTION_RESTORE_SNAPSHOT_PREFIX
                + os.path.basename(source["path"]),
            }
        if source.get("settings"):
            if source.get("reset_scan_base"):
                return {
                    "vod_id": source["id"],
                    "vod_name": source["name"],
                    "vod_pic": self._icon("reset"),
                    "vod_remarks": source["relative_in_root"],
                    "action": self.ACTION_OPEN_PREFIX + self.ACTION_RESET_SCAN_BASE,
                }
            if source.get("scan_base_path"):
                return {
                    "vod_id": source["id"],
                    "vod_name": source["name"],
                    "vod_pic": self._icon("folder"),
                    "vod_remarks": source["relative_in_root"],
                    "action": self.ACTION_EDIT_SCAN_BASE,
                }
            if source.get("scan_types"):
                return {
                    "vod_id": source["id"],
                    "vod_name": source["name"],
                    "vod_pic": self._icon("types"),
                    "vod_remarks": source["relative_in_root"],
                    "action": self.ACTION_EDIT_SCAN_TYPES,
                }
            if source.get("apply"):
                return {
                    "vod_id": source["id"],
                    "vod_name": source["name"],
                    "vod_pic": self._icon("scan"),
                    "vod_remarks": source["relative_in_root"],
                    "action": self.ACTION_OPEN_PREFIX + self.ACTION_APPLY_SCAN_CONFIG,
                }
            if source.get("auto_scan"):
                enabled = bool(source.get("enabled"))
                return {
                    "vod_id": source["id"],
                    "vod_name": source["name"],
                    "vod_pic": self._icon("toggle_on" if enabled else "toggle_off"),
                    "vod_remarks": "{} · 点击切换 · {}".format(
                        "已启用" if enabled else "已停用",
                        source["relative_in_root"],
                    ),
                    "action": self.ACTION_OPEN_PREFIX + self.ACTION_TOGGLE_AUTO_SCAN,
                }
            if source.get("auto_prune"):
                enabled = bool(source.get("enabled"))
                return {
                    "vod_id": source["id"],
                    "vod_name": source["name"],
                    "vod_pic": self._icon("toggle_on" if enabled else "toggle_off"),
                    "vod_remarks": "{} · 点击切换 · {}".format(
                        "已启用" if enabled else "已停用",
                        source["relative_in_root"],
                    ),
                    "action": self.ACTION_OPEN_PREFIX + self.ACTION_TOGGLE_AUTO_PRUNE,
                }
            if source.get("source_metadata"):
                return {
                    "vod_id": source["id"],
                    "vod_name": source["name"],
                    "vod_pic": self._icon("classify"),
                    "vod_remarks": source["relative_in_root"],
                    "action": self.ACTION_EDIT_SOURCE_METADATA,
                }
            if source.get("export_profile"):
                return {
                    "vod_id": source["id"],
                    "vod_name": source["name"],
                    "vod_pic": self._icon("download"),
                    "vod_remarks": source["relative_in_root"],
                    "action": self.ACTION_OPEN_PREFIX + self.ACTION_EXPORT_PROFILE,
                }
            if source.get("import_profile"):
                return {
                    "vod_id": source["id"],
                    "vod_name": source["name"],
                    "vod_pic": self._icon("undo"),
                    "vod_remarks": source["relative_in_root"],
                    "action": self.ACTION_OPEN_PREFIX + self.ACTION_IMPORT_PROFILE,
                }
            enabled = bool(source.get("enabled"))
            return {
                "vod_id": source["id"],
                "vod_name": source["name"],
                "vod_pic": self._icon("toggle_on" if enabled else "toggle_off"),
                "vod_remarks": "{} · 点击切换".format(
                    "已启用" if enabled else "已停用"
                ),
                "action": self.ACTION_TOGGLE_TYPE_PREFIX + source["type"],
            }
        if source.get("adult_blocked"):
            state_label = "18+ 已屏蔽"
        elif source.get("ignored"):
            state_label = "已屏蔽"
        else:
            state_label = ""
        return {
            "vod_id": source["id"],
            "vod_name": "{}{}{}".format(
                self._source_state_icon(source),
                "★ " if self._source_metadata_for(source).get("favorite") else "",
                source["name"],
            ),
            "vod_pic": "",
            "vod_remarks": "{} · {}{}{}{}".format(
                source["type"],
                source["relative_in_root"],
                " · " + state_label if state_label else "",
                self._test_result_label(source.get("test_result")),
                " · " + "、".join(self._source_metadata_for(source).get("tags", []))
                if self._source_metadata_for(source).get("tags") else "",
            ),
            "action": self.ACTION_TOGGLE_IGNORE_PREFIX + source["id"],
        }

    def _page_number(self, value):
        try:
            return max(1, int(value))
        except Exception:
            return 1

    def action(self, action):
        action = str(action)
        self._log("INFO", "用户操作: {}".format(action))
        protected = (
            action not in (self.ACTION_TEST_SITES, self.ACTION_RETEST_SITES)
            and not action.startswith(self.ACTION_SOURCE_PREFIX)
            and action != self.ACTION_OPEN_STATUS  # 运行状态卡片不受测活阻塞
        )
        if protected:
            with self.lock:
                if self._site_test_is_running():
                    result = {
                        "code": 0,
                        "msg": "后台检测进行中，请待本批完成后再修改设置",
                    }
                elif (
                    self._package_download_running()
                    and not self._is_package_download_action(action)
                ):
                    result = {
                        "code": 0,
                        "msg": "本地包下载安装中，请完成后再修改配置",
                    }
                elif (
                    self._repository_sync_running()
                    and not self._is_repository_sync_action(action)
                ):
                    result = {
                        "code": 0,
                        "msg": "在线仓库同步中，请完成后再修改配置",
                    }
                elif action.startswith(self.ACTION_OPEN_PREFIX):
                    # 引导前缀拦截：设置页执行类项先弹「确认执行」框。
                    real_action = action[len(self.ACTION_OPEN_PREFIX):]
                    opened, message = self._open_settings_action_dialog(real_action)
                    if not opened:
                        self._log(
                            "WARN",
                            "设置操作确认框未打开 ({}): {}".format(
                                real_action, message
                            ),
                        )
                    result = {"code": 0, "msg": "" if opened else message}
                else:
                    result = self._action_impl(action)
        elif action.startswith(self.ACTION_OPEN_PREFIX):
            real_action = action[len(self.ACTION_OPEN_PREFIX):]
            opened, message = self._open_settings_action_dialog(real_action)
            if not opened:
                self._log(
                    "WARN",
                    "设置操作确认框未打开 ({}): {}".format(real_action, message),
                )
            result = {"code": 0, "msg": "" if opened else message}
        else:
            result = self._action_impl(action)
        return result

    def _action_impl(self, action):
        # ------------------------------------------------------------------
        # v8.0 网络扫描根动作
        # ------------------------------------------------------------------
        if action == self.ACTION_NET_ADD:
            opened, message = self._open_network_edit_dialog("")
            if not opened:
                self._log("WARN", "添加网络目录窗口未打开: {}".format(message))
            return {"code": 0, "msg": "" if opened else message}
        if action == self.ACTION_NET_SYNC_ALL:
            if self._network_sync_running:
                return {"code": 0, "msg": "网络目录同步中，请稍候"}
            enabled_count = sum(
                1 for item in self.network_roots if item.get("enabled", True)
            )
            if not enabled_count:
                return {"code": 0, "msg": "还没有启用的网络目录，请先添加"}
            opened, message = self._open_network_confirm_dialog(
                "全部同步网络目录",
                "将增量下载全部 {} 个已启用网络目录的最新文件到本机，期间可正常使用，确定开始？".format(
                    enabled_count
                ),
                lambda: self._network_start_sync_worker(""),
            )
            if not opened:
                self._log("WARN", "网络目录同步确认框未打开: {}".format(message))
            return {"code": 0, "msg": "" if opened else message}
        if action.startswith(self.ACTION_NET_ROOT_PREFIX):
            root_id = action[len(self.ACTION_NET_ROOT_PREFIX) :]
            opened, message = self._open_network_root_menu_dialog(root_id)
            if not opened:
                self._log("WARN", "网络目录菜单未打开: {}".format(message))
            return {"code": 0, "msg": "" if opened else message}
        if action.startswith(self.ACTION_NET_EDIT_PREFIX):
            root_id = action[len(self.ACTION_NET_EDIT_PREFIX) :]
            opened, message = self._open_network_edit_dialog(root_id)
            if not opened:
                self._log("WARN", "编辑网络目录窗口未打开: {}".format(message))
            return {"code": 0, "msg": "" if opened else message}
        if action.startswith(self.ACTION_NET_SYNC_PREFIX):
            root_id = action[len(self.ACTION_NET_SYNC_PREFIX) :]
            if self._network_sync_running:
                return {"code": 0, "msg": "网络目录同步中，请稍候"}
            self._network_start_sync_worker(root_id)
            # v8.0：进度由独立进度对话框展示，不额外弹 toast。
            return {"code": 0, "msg": ""}
        if action.startswith(self.ACTION_NET_TOGGLE_PREFIX):
            root_id = action[len(self.ACTION_NET_TOGGLE_PREFIX) :]
            with self.lock:
                target = self._network_root_by_id(root_id)
                if not target:
                    return {"code": 0, "msg": "网络目录不存在，请刷新页面"}
                target["enabled"] = not target.get("enabled", True)
                self._save_settings()
                enabled = target["enabled"]
            self._schedule_manager_page_refresh()
            return {
                "code": 0,
                "msg": "已{}「{}」".format(
                    "启用" if enabled else "停用", target.get("name", "网络目录")
                ),
            }
        if action.startswith(self.ACTION_NET_DELETE_PREFIX):
            root_id = action[len(self.ACTION_NET_DELETE_PREFIX) :]
            with self.lock:
                target = self._network_root_by_id(root_id)
                name = str((target or {}).get("name", "网络目录"))
                removed = self._network_remove_root(root_id, remove_cache=True)
            if not removed:
                return {"code": 0, "msg": "网络目录不存在，请刷新页面"}
            self._schedule_manager_page_refresh()
            return {"code": 0, "msg": "已删除「{}」及本地镜像".format(name)}
        if action == self.ACTION_OPEN_SCAN_ONLY:
            opened, message = self._open_action_dialog("scan_only")
            if not opened:
                self._log("WARN", "扫描确认框未打开: {}".format(message))
            return {"code": 0, "msg": "" if opened else message}
        if action == self.ACTION_OPEN_LOAD_ALL:
            opened, message = self._open_action_dialog("load_all")
            if not opened:
                self._log("WARN", "加载全部确认框未打开: {}".format(message))
            return {"code": 0, "msg": "" if opened else message}
        if action.startswith(self.ACTION_LOAD_CHOICE_PREFIX):
            source_id = action[len(self.ACTION_LOAD_CHOICE_PREFIX) :]
            opened, message = self._open_load_choice_dialog(source_id)
            if not opened:
                self._log("WARN", "加载选择窗口未打开: {}".format(message))
            return {"code": 0, "msg": "" if opened else message}
        if (
            action.startswith(self.ACTION_LOAD_PERM_PREFIX)
            or action.startswith(self.ACTION_LOAD_TEMP_PREFIX)
            or action.startswith(self.ACTION_UNLOAD_PREFIX)
        ):
            if action.startswith(self.ACTION_LOAD_PERM_PREFIX):
                load_kind, source_id = "perm", action[
                    len(self.ACTION_LOAD_PERM_PREFIX) :
                ]
            elif action.startswith(self.ACTION_LOAD_TEMP_PREFIX):
                load_kind, source_id = "temp", action[
                    len(self.ACTION_LOAD_TEMP_PREFIX) :
                ]
            else:
                load_kind, source_id = "unload", action[
                    len(self.ACTION_UNLOAD_PREFIX) :
                ]
            with self.lock:
                if self._site_test_is_running():
                    message = "后台检测进行中，请待本批完成后再加载"
                elif self._package_download_running():
                    message = "本地包下载安装中，请完成后再加载"
                elif self._repository_sync_running():
                    message = "在线仓库同步中，请完成后再加载"
                else:
                    message = ""
                if message:
                    return {"code": 0, "msg": message}
                if load_kind == "perm":
                    ok, message = self._load_single_file_locked(
                        source_id, False
                    )
                elif load_kind == "temp":
                    ok, message = self._load_single_file_locked(
                        source_id, True
                    )
                else:
                    ok, message = self._unload_file_locked(source_id)
                self.inited = True
                if ok:
                    self._schedule_manager_page_refresh()
                return {"code": 0, "msg": message}
        if action.startswith(self.ACTION_BLOCK_PREFIX):
            source_id = action[len(self.ACTION_BLOCK_PREFIX) :]
            with self.lock:
                source = self.cache.get("source_index", {}).get(source_id)
                if not source:
                    return {"code": 0, "msg": "文件不在扫描结果中"}
                identity = str(source.get("identity", ""))
                if not identity:
                    return {"code": 0, "msg": "无法获取站点身份标识"}
                # 先移出加载（如果有）
                self._unload_file_locked(source_id)
                # 持久化到 manual_ignored_sources，否则刷新/重启后屏蔽状态丢失
                self.manual_ignored_sources.add(identity)
                self._sync_ignored_sources()
                # 复用统一的缓存迁移逻辑：sources -> ignored，并重建计数
                self._set_cached_source_ignored(source, True)
                self._save_settings()
                try:
                    self._save_scan_snapshot()
                except Exception as exc:
                    self._warn("屏蔽后扫描列表快照保存失败: {}".format(exc))
                self._schedule_manager_page_refresh()
                return {"code": 0, "msg": "已屏蔽「{}」，可在屏蔽分类中解除".format(source.get("name", ""))}
        if action == self.ACTION_EDIT_SOURCE_METADATA:
            opened, message = self._open_source_metadata_dialog()
            if not opened:
                self._log("WARN", "收藏与标签界面未打开: {}".format(message))
            return {"code": 0, "msg": "" if opened else message}
        if action == self.ACTION_EXPORT_PROFILE:
            with self.lock:
                try:
                    path = self._export_management_profile()
                    self._schedule_manager_page_refresh()
                    return {"code": 0, "msg": "管理配置已导出：{}".format(path)}
                except Exception as exc:
                    self._log("ERROR", "管理配置导出失败: {}".format(exc))
                    return {"code": 0, "msg": "管理配置导出失败：{}".format(exc)}
        if action == self.ACTION_IMPORT_PROFILE:
            with self.lock:
                try:
                    path, backup = self._import_management_profile()
                    self._schedule_manager_page_refresh()
                    return {
                        "code": 0,
                        "msg": "管理配置已导入：{}{}；请「扫描」后重新「加载」".format(
                            path,
                            "；原设置备份：{}".format(backup) if backup else "",
                        ),
                    }
                except Exception as exc:
                    self._log("ERROR", "管理配置导入失败: {}".format(exc))
                    return {"code": 0, "msg": "管理配置导入失败：{}".format(exc)}
        if action == self.ACTION_EDIT_SCAN_BASE:
            opened, message = self._open_scan_base_dialog()
            if not opened:
                self._log("WARN", "扫描路径设置未打开: {}".format(message))
            return {
                "code": 0,
                "msg": "" if opened else message,
            }
        if action == self.ACTION_RESET_SCAN_BASE:
            with self.lock:
                try:
                    self._set_scan_base_path("")
                    self._schedule_manager_page_refresh()
                    return {
                        "code": 0,
                        "msg": "扫描目录已恢复为默认：{}".format(
                            self.local_base_dir
                        ),
                    }
                except Exception as exc:
                    self._log("ERROR", "扫描目录恢复失败: {}".format(exc))
                    return {
                        "code": 0,
                        "msg": "扫描目录恢复失败：{}".format(exc),
                    }
        if action == self.ACTION_EDIT_SCAN_TYPES:
            opened, message = self._open_scan_types_dialog()
            if not opened:
                self._log("WARN", "扫描类型设置未打开: {}".format(message))
            return {
                "code": 0,
                "msg": "" if opened else message,
            }
        if action == self.ACTION_OPEN_STATUS:
            opened, message = self._open_status_dialog()
            if not opened:
                self._log("WARN", "运行状态对话框未打开: {}".format(message))
            return {"code": 0, "msg": "" if opened else message}
        if action == self.ACTION_OPEN_RESCAN:
            opened, message = self._open_action_dialog("rescan")
            if not opened:
                self._log("WARN", "扫描对话框未打开: {}".format(message))
            return {"code": 0, "msg": "" if opened else message}
        if action == self.ACTION_OPEN_TEST_SITES:
            opened, message = self._open_action_dialog("test_sites")
            if not opened:
                self._log("WARN", "测活对话框未打开: {}".format(message))
            return {"code": 0, "msg": "" if opened else message}
        if action == self.ACTION_OPEN_RETEST_SITES:
            opened, message = self._open_action_dialog("retest_sites")
            if not opened:
                self._log("WARN", "重新检测对话框未打开: {}".format(message))
            return {"code": 0, "msg": "" if opened else message}
        if action == self.ACTION_OPEN_AUTO_CLASSIFY:
            opened, message = self._open_action_dialog("auto_classify")
            if not opened:
                self._log("WARN", "自动分类对话框未打开: {}".format(message))
            return {"code": 0, "msg": "" if opened else message}
        if action == self.ACTION_OPEN_CLEAR_SITES:
            opened, message = self._open_action_dialog("clear_sites")
            if not opened:
                self._log("WARN", "清除站点对话框未打开: {}".format(message))
            return {"code": 0, "msg": "" if opened else message}
        if action == self.ACTION_OPEN_FULL_CLEAR:
            opened, message = self._open_action_dialog("full_clear")
            if not opened:
                self._log("WARN", "一键清除对话框未打开: {}".format(message))
            return {"code": 0, "msg": "" if opened else message}
        if action == self.ACTION_BATCH_UNBLOCK:
            opened, message = self._open_blocked_sources_dialog()
            if not opened:
                self._log("WARN", "批量解除屏蔽界面未打开: {}".format(message))
            return {"code": 0, "msg": "" if opened else message}
        if action.startswith(self.ACTION_BROWSER_BATCH_SELECT):
            dir_path = ""
            if ":" in action[len(self.ACTION_BROWSER_BATCH_SELECT) :]:
                dir_path = urllib.parse.unquote(
                    action[len(self.ACTION_BROWSER_BATCH_SELECT) + 1 :]
                )
            opened, message = self._open_browser_batch_select_dialog(dir_path=dir_path)
            if not opened:
                self._log("WARN", "批量选择界面未打开: {}".format(message))
            return {"code": 0, "msg": "" if opened else message}
        if action == self.ACTION_UNBLOCK_ALL:
            with self.lock:
                source_ids = [
                    source.get("id", "")
                    for source in self.cache.get("ignored", [])
                ]
                try:
                    restored, reload_detail = self._restore_blocked_sources(
                        source_ids
                    )
                    return {
                        "code": 0,
                        "msg": "已解除全部 {} 个屏蔽站点；{}".format(
                            len(restored), reload_detail
                        ),
                    }
                except Exception as exc:
                    self._log("ERROR", "一键解除屏蔽失败: {}".format(exc))
                    return {"code": 0, "msg": "一键解除屏蔽失败：{}".format(exc)}
        if action.startswith(self.ACTION_TOGGLE_IGNORE_PREFIX):
            source_id = action[len(self.ACTION_TOGGLE_IGNORE_PREFIX) :]
            source = self.cache["source_index"].get(source_id)
            if not source:
                return {"code": 0, "msg": "站点不存在，请重新扫描"}
            if source.get("ignored"):
                with self.lock:
                    try:
                        restored, reload_detail = self._restore_blocked_sources(
                            [source_id]
                        )
                        return {
                            "code": 0,
                            "msg": "已恢复：{}；{}".format(
                                restored[0]["name"], reload_detail
                            ),
                        }
                    except Exception as exc:
                        self._log("ERROR", "解除屏蔽失败: {}".format(exc))
                        return {"code": 0, "msg": "解除屏蔽失败：{}".format(exc)}
            # 屏蔽：与文件弹窗"屏蔽"按钮（ACTION_BLOCK_PREFIX）同一套轻量逻辑，
            # 不重写注册表、不全量重载——_generate_config 在 _load_filter=None
            # 时会把所有扫描站点写入标准配置，导致屏蔽一个反而注入全部。
            with self.lock:
                identity = source["identity"]
                self._unload_file_locked(source_id)
                self.manual_ignored_sources.add(identity)
                self._sync_ignored_sources()
                self._set_cached_source_ignored(source, True)
                try:
                    self._save_settings()
                except Exception as exc:
                    self._log("ERROR", "屏蔽设置保存失败: {}".format(exc))
                    return {"code": 0, "msg": "屏蔽设置保存失败：{}".format(exc)}
                try:
                    self._save_scan_snapshot()
                except Exception as exc:
                    self._warn("屏蔽后扫描列表快照保存失败: {}".format(exc))
                self._schedule_manager_page_refresh()
                return {
                    "code": 0,
                    "msg": "已屏蔽「{}」，可在已屏蔽分类中恢复".format(source["name"]),
                }
        if action.startswith(self.ACTION_SOURCE_PREFIX):
            source_id = action[len(self.ACTION_SOURCE_PREFIX) :]
            source = self.cache["source_index"].get(source_id)
            if not source:
                return {"code": 0, "msg": "站点不存在，请重新扫描"}
            return {
                "code": 0,
                "msg": "{} · {}；已写入 {} 本地配置".format(
                    source["type"],
                    source["relative_in_root"],
                    self._app_mode_label(),
                ),
            }
        if action in (self.ACTION_TEST_SITES, self.ACTION_RETEST_SITES):
            with self._site_test_control_lock:
                worker = self._site_test_thread
                if worker is not None and worker.is_alive():
                    return {
                        "code": 0,
                        "msg": "后台检测进行中，进度将逐站通知",
                    }
            with self.lock:
                if not self.cache["sources"] and not self.cache["ignored"]:
                    return {"code": 0, "msg": "暂无扫描结果，请先点击「扫描」"}
            try:
                self._authorize_release("site_health")
            except ReleaseAuthorizationError as exc:
                self._authorization_last_error = str(exc)
                self._log("WARN", "手动测活授权失败: {}".format(exc))
                message = "当前版本未获得测活授权，已拒绝测活：{}".format(exc)
                self._notify_app(message)
                return {
                    "code": 0,
                    "msg": message,
                }
            force = action == self.ACTION_RETEST_SITES
            if not self._start_site_test_worker(force=force):
                return {
                    "code": 0,
                    "msg": "后台检测进行中，进度将逐站通知",
                }
            return {
                "code": 0,
                "msg": "已启动{}，全部站点一一检测，进度将逐站通知".format(
                    "全部重新检测" if force else "站点功能测活",
                ),
            }
        if action == self.ACTION_AUTO_CLASSIFY:
            with self.lock:
                summary, _ = self._run_auto_classify()
            self._schedule_manager_page_refresh()
            return {"code": 0, "msg": summary}
        if action == self.ACTION_FULL_CLEAR:
            with self.lock:
                transaction = []
                try:
                    previous_registry = copy.deepcopy(self._load_registry())
                    expected_cleared_registry, _ = self._remove_generated_items(
                        copy.deepcopy(previous_registry)
                    )
                except Exception as exc:
                    self._log("ERROR", "一键清除前注册表快照失败: {}".format(exc))
                    return {"code": 0, "msg": "一键清除失败：{}".format(exc)}
                previous = {
                    "manual_ignored_sources": set(self.manual_ignored_sources),
                    "auto_blocked_sources": set(self.auto_blocked_sources),
                    "adult_blocked_sources": set(self.adult_blocked_sources),
                    "adult_allowed_sources": set(self.adult_allowed_sources),
                    "ignored_sources": set(self.ignored_sources),
                    "pruned_sources": set(self.pruned_sources),
                    "site_test_results": copy.deepcopy(self.site_test_results),
                    "site_test_history": copy.deepcopy(self.site_test_history),
                    "source_metadata": copy.deepcopy(self.source_metadata),
                    "retest_pending": list(self._retest_pending),
                    "retest_auto_blocked": set(self._retest_auto_blocked),
                    "auto_scan_suspended": self.auto_scan_suspended,
                    "author_scan_surprise_shown": self._author_scan_surprise_shown,
                    "package_download_sites": copy.deepcopy(
                        self.package_download_sites
                    ),
                    "online_repositories": copy.deepcopy(
                        self.online_repositories
                    ),
                    "cache": copy.deepcopy(self.cache),
                    "status": copy.deepcopy(self.status),
                    "selected_identities": (
                        set(self.selected_identities)
                        if isinstance(self.selected_identities, set)
                        else None
                    ),
                    "temp_identities": set(self.temp_identities),
                    "selection_initialized": self.selection_initialized,
                }
                try:
                    transaction = self._stage_program_download_deletions()
                    removed_registry = self._clear_generated_registry()
                    self._reset_state_after_full_clear()
                    self._save_settings()
                except Exception as exc:
                    self.manual_ignored_sources = previous[
                        "manual_ignored_sources"
                    ]
                    self.auto_blocked_sources = previous["auto_blocked_sources"]
                    self.adult_blocked_sources = previous[
                        "adult_blocked_sources"
                    ]
                    self.adult_allowed_sources = previous[
                        "adult_allowed_sources"
                    ]
                    self.ignored_sources = previous["ignored_sources"]
                    self.pruned_sources = previous["pruned_sources"]
                    self.site_test_results = previous["site_test_results"]
                    self.site_test_history = previous["site_test_history"]
                    self.source_metadata = previous["source_metadata"]
                    self._retest_pending = previous["retest_pending"]
                    self._retest_auto_blocked = previous[
                        "retest_auto_blocked"
                    ]
                    self.auto_scan_suspended = previous[
                        "auto_scan_suspended"
                    ]
                    self._author_scan_surprise_shown = previous[
                        "author_scan_surprise_shown"
                    ]
                    self.package_download_sites = previous[
                        "package_download_sites"
                    ]
                    self.online_repositories = previous["online_repositories"]
                    self.cache = previous["cache"]
                    self.status = previous["status"]
                    self.selected_identities = previous["selected_identities"]
                    self.temp_identities = previous["temp_identities"]
                    self.selection_initialized = previous[
                        "selection_initialized"
                    ]
                    rollback_errors = []
                    try:
                        current_registry = self._load_registry()
                        if current_registry == expected_cleared_registry:
                            current_token = self._registry_token(self.output_path)
                            self._atomic_write_json(
                                previous_registry,
                                create_backup=False,
                                expected_token=current_token,
                            )
                            self._write_standard_configs(previous_registry)
                        elif current_registry != previous_registry:
                            rollback_errors.append(
                                "注册表已被其他操作修改，未覆盖"
                            )
                    except Exception as rollback_exc:
                        rollback_errors.append(
                            "注册表回滚失败：{}".format(rollback_exc)
                        )
                    try:
                        self._rollback_program_download_deletions(transaction)
                    except Exception as rollback_exc:
                        rollback_errors.append(
                            "下载目录回滚失败：{}".format(rollback_exc)
                        )
                    try:
                        self._save_settings()
                    except Exception as rollback_exc:
                        rollback_errors.append(
                            "设置回滚失败：{}".format(rollback_exc)
                        )
                    detail = "；".join(rollback_errors)
                    self._log(
                        "ERROR",
                        "一键清除失败: {}{}".format(
                            exc, "；" + detail if detail else ""
                        ),
                    )
                    return {
                        "code": 0,
                        "msg": "一键清除失败：{}{}".format(
                            exc, "；" + detail if detail else ""
                        ),
                    }

                removed_downloads, cleanup_warnings = (
                    self._finalize_program_download_deletions(transaction)
                )
                try:
                    cache_files = self._clear_scan_cache_file()
                except Exception as exc:
                    cache_files = 0
                    cleanup_warnings.append("扫描缓存清理失败：{}".format(exc))
                try:
                    backup_files = self._delete_backup_files()
                except Exception as exc:
                    backup_files = 0
                    cleanup_warnings.append("历史备份清理失败：{}".format(exc))
                artifact_files, artifact_warnings = (
                    self._clear_program_operation_artifacts()
                )
                cleanup_warnings.extend(artifact_warnings)
                for warning in cleanup_warnings:
                    self._warn(warning)
                self._set_manual_idle_status("已一键清除，请重新下载或扫描")
                try:
                    _, reload_detail = self._reload_app_vod_config(
                        expected_keys=set()
                    )
                except Exception as exc:
                    reload_detail = "App 重载请求失败：{}".format(exc)
                    self._warn(reload_detail)
                self._schedule_manager_page_refresh()
                self.inited = True
                summary = (
                    "已清除 {} 个加载项、{} 个本地包目录、{} 个在线仓库目录、"
                    "{} 个缓存/临时文件和 {} 个历史备份；用户原始文件及接口设置保留；{}"
                ).format(
                    removed_registry,
                    removed_downloads.get("package", 0),
                    removed_downloads.get("repository", 0),
                    cache_files + artifact_files,
                    backup_files,
                    reload_detail,
                )
                if cleanup_warnings:
                    summary += "；{} 项残留清理失败，详见日志".format(
                        len(cleanup_warnings)
                    )
                self._log("INFO", summary)
                return {"code": 0, "msg": summary}
        if action == self.ACTION_UNLOAD_ALL_PERM:
            # 全部移出：把所有永久加载的站点从注册表移除 + 清除选择集
            with self.lock:
                perm_sources = [
                    source
                    for source in self.cache.get("sources", [])
                    if self._source_load_state(source) == "perm"
                ]
                if not perm_sources:
                    return {"code": 0, "msg": "当前没有已永久加载的站点"}
                removed_count = 0
                for source in perm_sources:
                    identity = str(source.get("identity", ""))
                    # 从注册表移除
                    self._remove_site_from_registry(source)
                    # 从永久注入集合移除
                    self.perm_injected_identities.discard(identity)
                    # 从配置选择集移除
                    if isinstance(self.selected_identities, set):
                        self.selected_identities.discard(identity)
                    # 从运行态移除
                    site = source.get("site") if isinstance(source.get("site"), dict) else {}
                    runtime_key = str(site.get("key", "")).strip() or str(source.get("key", "")).strip()
                    if runtime_key:
                        if self._temp_home_key == runtime_key:
                            self._temp_home_key = ""
                        try:
                            self._remove_site_from_app(runtime_key)
                        except Exception:
                            pass
                    removed_count += 1
                self._save_settings()
                self._schedule_manager_page_refresh(delay=0.2)
                return {"code": 0, "msg": "已移出 {} 个永久加载站点".format(removed_count)}
        if action == self.ACTION_CONVERT_ALL_TO_TEMP:
            # 全部改为临时：把所有永久加载的站点改为临时加载
            with self.lock:
                perm_sources = [
                    source
                    for source in self.cache.get("sources", [])
                    if self._source_load_state(source) == "perm"
                ]
                if not perm_sources:
                    return {"code": 0, "msg": "当前没有已永久加载的站点"}
                converted = 0
                for source in perm_sources:
                    identity = str(source.get("identity", ""))
                    # 从注册表移除
                    self._remove_site_from_registry(source)
                    # 从永久注入集合移除
                    self.perm_injected_identities.discard(identity)
                    # 从配置选择集移除
                    if isinstance(self.selected_identities, set):
                        self.selected_identities.discard(identity)
                    # 加入临时集合
                    self.temp_identities.add(identity)
                    converted += 1
                self._save_settings()
                # 注入到运行态
                for source in perm_sources:
                    try:
                        self._inject_site_into_app(source, set_home=False)
                    except Exception:
                        pass
                self._schedule_manager_page_refresh(delay=0.2)
                return {"code": 0, "msg": "已把 {} 个站点改为临时加载".format(converted)}
        if action == self.ACTION_CLEAR_SITES:
            with self.lock:
                try:
                    previous_registry = copy.deepcopy(self._load_registry())
                    expected_cleared_registry, _ = self._remove_generated_items(
                        copy.deepcopy(previous_registry)
                    )
                except Exception as exc:
                    self._log("ERROR", "清除前注册表快照失败: {}".format(exc))
                    return {"code": 0, "msg": "清除失败：{}".format(exc)}
                previous_ignored = set(self.ignored_sources)
                previous_manual_ignored = set(self.manual_ignored_sources)
                previous_auto_blocked = set(self.auto_blocked_sources)
                previous_adult_blocked = set(self.adult_blocked_sources)
                previous_adult_allowed = set(self.adult_allowed_sources)
                previous_results = dict(self.site_test_results)
                previous_pruned = set(self.pruned_sources)
                previous_cache = self.cache
                previous_status = self.status
                previous_retest_pending = list(self._retest_pending)
                previous_retest_auto_blocked = set(
                    self._retest_auto_blocked
                )
                previous_auto_scan_suspended = self.auto_scan_suspended
                previous_selected = (
                    set(self.selected_identities)
                    if isinstance(self.selected_identities, set)
                    else None
                )
                previous_temp = set(self.temp_identities)
                previous_selection_initialized = self.selection_initialized
                try:
                    self.manual_ignored_sources.clear()
                    self.auto_blocked_sources.clear()
                    self.adult_blocked_sources.clear()
                    self.adult_allowed_sources.clear()
                    self.ignored_sources.clear()
                    # 一并复位自动清理名单：这是被移除站点唯一的恢复入口。
                    pruned_restored = len(self.pruned_sources)
                    self.pruned_sources.clear()
                    self.site_test_results.clear()
                    self._retest_pending = []
                    self._retest_auto_blocked.clear()
                    self.auto_scan_suspended = True
                    # v7.1：加载选择集一并复位，否则重新扫描会按旧选择集
                    # 显示/写回已清除站点（看似“复活”）。
                    self.selected_identities = set()
                    self.temp_identities = set()
                    self._temp_home_key = ""
                    self.perm_injected_identities = set()
                    self.selection_initialized = True
                    self._save_settings()
                    removed = self._clear_generated_registry()
                    self._set_manual_idle_status(
                        "已清除 {} 个自动注入项及扫描状态".format(removed)
                    )
                    self._clear_scan_cache_file()
                    _, detail = self._reload_app_vod_config(expected_keys=set())
                    self._schedule_manager_page_refresh()
                    self.inited = True
                    return {
                        "code": 0,
                        "msg": "已清除 {} 个自动注入站点及屏蔽状态、检测缓存{}，手工站点与类型配置保留；{}".format(
                            removed,
                            "，{} 个已清理站点恢复扫描".format(pruned_restored)
                            if pruned_restored
                            else "",
                            detail,
                        ),
                    }
                except Exception as exc:
                    self._log("ERROR", "清除自动站点失败: {}".format(exc))
                    self.ignored_sources = previous_ignored
                    self.manual_ignored_sources = previous_manual_ignored
                    self.auto_blocked_sources = previous_auto_blocked
                    self.adult_blocked_sources = previous_adult_blocked
                    self.adult_allowed_sources = previous_adult_allowed
                    self.site_test_results = previous_results
                    self.pruned_sources = previous_pruned
                    self.cache = previous_cache
                    self.status = previous_status
                    self._retest_pending = previous_retest_pending
                    self._retest_auto_blocked = previous_retest_auto_blocked
                    self.auto_scan_suspended = previous_auto_scan_suspended
                    self.selected_identities = previous_selected
                    self.temp_identities = previous_temp
                    self.selection_initialized = previous_selection_initialized
                    try:
                        self._save_settings()
                    except Exception:
                        pass
                    rollback_error = ""
                    try:
                        output_path = os.path.abspath(
                            os.path.expanduser(self.output_path)
                        )
                        if os.path.isfile(output_path):
                            current_registry = self._read_config_file(
                                output_path, "站点注入注册表"
                            )
                            if current_registry == expected_cleared_registry:
                                current_token = self._registry_token(output_path)
                                self._atomic_write_json(
                                    previous_registry,
                                    create_backup=False,
                                    expected_token=current_token,
                                )
                                if self.app_mode == self.APP_MODE_OKTV:
                                    self._ok_write_generated_configs(
                                        previous_registry
                                    )
                            elif current_registry != previous_registry:
                                rollback_error = "注册表已被其他操作修改，未覆盖"
                    except Exception as rollback_exc:
                        rollback_error = "注册表回滚失败：{}".format(
                            rollback_exc
                        )
                    if rollback_error:
                        self._log("ERROR", rollback_error)
                    return {
                        "code": 0,
                        "msg": "清除失败：{}{}".format(
                            exc,
                            "；" + rollback_error if rollback_error else "",
                        ),
                    }
        if action == self.ACTION_DELETE_BACKUPS:
            with self.lock:
                try:
                    removed = self._delete_backup_files()
                except Exception as exc:
                    self._log("ERROR", "历史备份删除失败: {}".format(exc))
                    return {"code": 0, "msg": "历史备份删除失败：{}".format(exc)}
            # 删除后立即刷新首页与分类页，避免「历史备份」分类与列表残留旧数据。
            self._schedule_manager_page_refresh()
            return {
                "code": 0,
                "msg": "已删除历史备份"
                if removed
                else "暂无历史备份",
            }
        if action.startswith(self.ACTION_RESTORE_SNAPSHOT_PREFIX):
            name = os.path.basename(
                action[len(self.ACTION_RESTORE_SNAPSHOT_PREFIX) :]
            )
            path = os.path.join(self.backup_dir, name)
            with self.lock:
                try:
                    if not name.startswith("registry-") or not name.endswith(".json"):
                        raise ValueError("历史备份名称无效")
                    count = self._restore_registry_file(path)
                    self._suspend_auto_scan()
                    self._set_manual_idle_status(
                        "已恢复历史备份，请「扫描」后重新「加载」"
                    )
                    _, detail = self._reload_app_vod_config(
                        expected_keys=self._generated_registry_keys()
                    )
                    return {
                        "code": 0,
                        "msg": "已恢复历史备份（{} 个条目）；{}".format(
                            count,
                            detail,
                        ),
                    }
                except Exception as exc:
                    self._log("ERROR", "历史备份恢复失败: {}".format(exc))
                    return {"code": 0, "msg": "历史备份恢复失败：{}".format(exc)}
        if action == self.ACTION_TOGGLE_AUTO_SCAN:
            with self.lock:
                previous_enabled = self.auto_scan_on_empty
                previous_suspended = self.auto_scan_suspended
                try:
                    self.auto_scan_on_empty = not previous_enabled
                    if self.auto_scan_on_empty:
                        self.auto_scan_suspended = False
                    self._save_settings()
                    self._schedule_manager_page_refresh()
                    return {
                        "code": 0,
                        "msg": "自动补扫已{}".format(
                            "启用，无扫描快照时进入自动扫描一次"
                            if self.auto_scan_on_empty
                            else "停用，仅手动扫描"
                        ),
                    }
                except Exception as exc:
                    self._log("ERROR", "自动补扫开关保存失败: {}".format(exc))
                    self.auto_scan_on_empty = previous_enabled
                    self.auto_scan_suspended = previous_suspended
                    return {"code": 0, "msg": "自动补扫开关保存失败：{}".format(exc)}
        if action == self.ACTION_TOGGLE_AUTO_PRUNE:
            with self.lock:
                previous_enabled = self.auto_prune_blocked
                try:
                    self.auto_prune_blocked = not previous_enabled
                    self._save_settings()
                    self._schedule_manager_page_refresh()
                    return {
                        "code": 0,
                        "msg": "自动清理屏蔽站点已{}".format(
                            "启用，测活结束后把屏蔽站点移出配置（源文件保留，"
                            "可用“清除自动站点”恢复）"
                            if self.auto_prune_blocked
                            else "停用，测活只屏蔽不移除"
                        ),
                    }
                except Exception as exc:
                    self._log("ERROR", "自动清理开关保存失败: {}".format(exc))
                    self.auto_prune_blocked = previous_enabled
                    return {"code": 0, "msg": "自动清理开关保存失败：{}".format(exc)}
        if action.startswith(self.ACTION_TOGGLE_TYPE_PREFIX):
            source_type = action[len(self.ACTION_TOGGLE_TYPE_PREFIX) :].upper()
            if source_type not in self.TYPE_ORDER:
                return {"code": 0, "msg": "未知站点类型"}
            with self.lock:
                previous = self.pending_type_enabled.get(
                    source_type, self.type_enabled.get(source_type, True)
                )
                try:
                    self._set_pending_type_settings(
                        {source_type: not previous}
                    )
                    self._schedule_manager_page_refresh()
                    return {
                        "code": 0,
                        "msg": "{} 类型扫描已{}，待应用".format(
                            source_type,
                            "启用"
                            if self.pending_type_enabled[source_type]
                            else "停用",
                        ),
                    }
                except Exception as exc:
                    self._log("ERROR", "类型开关保存失败: {}".format(exc))
                    return {"code": 0, "msg": "类型开关保存失败：{}".format(exc)}
        if action in (
            self.ACTION_APPLY_SCAN_CONFIG,
            self.ACTION_SCAN_ONLY,
        ):
            allowed, duplicate_message = self._begin_manual_scan_request()
            if not allowed:
                return {"code": 0, "msg": duplicate_message}
            try:
                with self.lock:
                    if self._site_test_is_running():
                        return {"code": 0, "msg": "后台检测进行中，请待本批完成后再扫描"}
                    if self._package_download_running():
                        return {"code": 0, "msg": "本地包下载安装中，请完成后再扫描"}
                    if self._repository_sync_running():
                        return {"code": 0, "msg": "在线仓库同步中，请完成后再扫描"}
                    if self._network_sync_running:
                        return {"code": 0, "msg": "网络目录同步中，请完成后再扫描"}
                    if (
                        action == self.ACTION_APPLY_SCAN_CONFIG
                        and self.config_dirty
                    ):
                        try:
                            self._apply_pending_type_settings()
                        except Exception as exc:
                            self._log("ERROR", "扫描配置应用失败: {}".format(exc))
                            return {
                                "code": 0,
                                "msg": "扫描配置应用失败：{}".format(exc),
                            }
                    ok = self._scan_only_locked(
                        sync_network=True,
                        progress=lambda message, **kwargs: self._update_progress_panel(
                            message, **kwargs
                        ),
                    )
                    self.inited = True
                    if ok:
                        self._schedule_manager_page_refresh()
                        message = "{}（{} 个站点 / {} 个直播可加载）".format(
                            self.status["write_state"],
                            len(self.cache["sources"]),
                            len(self.cache.get("lives", [])),
                        )
                    else:
                        message = "扫描未完成：{}".format(
                            self.status["error"] or self.status["write_state"]
                        )
                    return {"code": 0, "msg": message}
            finally:
                self._finish_manual_scan_request()
        if action == self.ACTION_LOAD_ALL:
            allowed, duplicate_message = self._begin_manual_scan_request()
            if not allowed:
                return {"code": 0, "msg": duplicate_message}
            try:
                with self.lock:
                    if self._site_test_is_running():
                        return {"code": 0, "msg": "后台检测进行中，请待本批完成后再加载"}
                    if self._package_download_running():
                        return {"code": 0, "msg": "本地包下载安装中，请完成后再加载"}
                    if self._repository_sync_running():
                        return {"code": 0, "msg": "在线仓库同步中，请完成后再加载"}
                    ok, detail = self._load_all_locked()
                    self.inited = True
                    if ok:
                        self._schedule_manager_page_refresh()
                        message = "已永久加载全部扫描结果：{} 个站点；{}".format(
                            len(self.cache["sources"]), detail or "配置已更新"
                        )
                    else:
                        message = "加载未完成：{}".format(detail)
                    return {"code": 0, "msg": message}
            finally:
                self._finish_manual_scan_request()
        if action != self.ACTION_RESCAN:
            return {"code": 0, "msg": "未知操作"}
        allowed, duplicate_message = self._begin_manual_scan_request()
        if not allowed:
            return {"code": 0, "msg": duplicate_message}
        try:
            with self.lock:
                if self.config_dirty:
                    try:
                        self._apply_pending_type_settings()
                    except Exception as exc:
                        self._log("ERROR", "扫描配置应用失败: {}".format(exc))
                        return {"code": 0, "msg": "扫描配置应用失败：{}".format(exc)}
                # v7.0：兼容入口“扫描并加载”等同「加载全部」，临时项转正。
                self.temp_identities = set()
                self._temp_home_key = ""
                ok = self._refresh_locked(
                    allow_empty=not any(self.type_enabled.values()),
                    progress=lambda message, **kwargs: self._update_progress_panel(
                        message, **kwargs
                    ),
                )
                self.inited = True
                if ok:
                    self._ensure_selection_initialized_locked()
                    self.selected_identities = {
                        str(source.get("identity", ""))
                        for source in self.cache.get("sources", [])
                        if source.get("identity")
                    }
                    try:
                        self._save_settings()
                    except Exception as exc:
                        self._warn("永久加载选择保存失败: {}".format(exc))
                    self._show_author_scan_surprise()
                    _, detail = self._reload_app_vod_config(
                        expected_keys=self._generated_registry_keys()
                    )
                    if self.status["compatibility_blocked"]:
                        message = (
                            "兼容检查完成：已拦截 {} 个不兼容站点，"
                            "当前加载 {} 个站点；{}"
                        ).format(
                            self.status["compatibility_blocked"],
                            len(self.cache["sources"]),
                            detail,
                        )
                    else:
                        message = "扫描完成：{} 个站点、{} 个直播，{}；{}".format(
                            len(self.cache["sources"]),
                            len(self.cache.get("lives", [])),
                            "{} (+{} ~{} -{})".format(
                                self.status["write_state"],
                                self.status["added_sites"],
                                self.status["updated_sites"],
                                self.status["removed_sites"],
                            ),
                            detail,
                        )
                else:
                    message = "扫描未完成：{}".format(
                        self.status["error"] or self.status["write_state"]
                    )
                return {"code": 0, "msg": message}
        finally:
            self._finish_manual_scan_request()

    def playerContent(self, flag, id, vipFlags):
        return {
            "parse": 0,
            "url": "",
            "header": {},
            "msg": "该条目为配置管理项，不可播放。",
        }

    def destroy(self):
        self._destroyed = True
        self._site_test_cancel.set()
        # 注意：不能在此移除临时站点/清空临时状态。App 每次重建站点表
        # （含本脚本自己触发的主动重载）都会销毁并重建 spider 实例，
        # 在此清理会把刚转换的临时站移除、并让看门中止（实测：改为临时
        # 加载后站点消失）。临时站仅存运行态内存，App 进程退出即自然
        # 消失，无需在此反射移除。
        return "destroy"