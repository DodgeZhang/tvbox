package com.github.catvod.spider;

import android.content.Context;
import android.os.Build;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileFilter;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 自动保活本地 Go 网盘代理（127.0.0.1:5266）。
 *
 * 接口自带的官方启动链（merge.A.s0#J0）依赖 APK 内置的 FishNative JNI so
 * 探测 ABI；部分安装包（如仅 armeabi-v7a 的包跑在 x86 模拟器上）没有该 so，
 * JNI 探测失败后官方链直接放弃，表现为“退出重进后 Go 代理未启动”，
 * 网盘播放只能回退 9978 Java 代理。
 *
 * 最小修复（不复制官方下载/路由逻辑）：
 * 1) 5266 不通时，优先反射调用官方 J0()（带 so 的真机会自行下载并启动）；
 * 2) 官方链没拉起时，用 filesDir 内已有 pvideo 二进制自行启动。
 *    文件名同时兼容长名（pvideo-arm64-v8a/pvideo-armeabi-v7a/pvideo-x86_64/
 *    pvideo-x86）与短名（pvideo-arm64/pvideo-arm），并扫描目录兜底；
 *    逐个读取 ELF 头按本机能力（ABI + 64 位内核 + 转译）排序，
 *    启动后 ping 不通即换下一个候选；
 * 3) 5266 通但官方管理器未接管（s0.d=false）时，调用官方校验方法
 *    s0#Q() 让其按官方流程 ping 校验并置 d=true，后续 fishplay 路由照常。
 * 周期看门狗保证退出重进 / 进程被杀后自动恢复。
 */
public final class PVB {

    private static final int PORT = 5266;
    private static final long PERIOD_SECONDS = 20;
    private static final long INIT_DELAY_SECONDS = 6;
    private static final int WAIT_PING_TIMES = 10;
    private static final long TRIAL_WAIT_MS = 4000;

    // ELF e_machine
    private static final int M_ARM = 0x28;
    private static final int M_X86 = 0x03;
    private static final int M_X64 = 0x3E;
    private static final int M_ARM64 = 0xB7;

    private static final AtomicBoolean sStarted = new AtomicBoolean(false);
    private static final AtomicBoolean sBusy = new AtomicBoolean(false);
    private static final AtomicBoolean sJ0Tried = new AtomicBoolean(false);
    private static final List<Process> sHeld = new ArrayList<Process>();
    private static File sLogFile;

    private PVB() {
    }

    public static void boot(final Context context) {
        if (context == null || !sStarted.compareAndSet(false, true)) return;
        final Context ctx = context.getApplicationContext() != null
                ? context.getApplicationContext() : context;
        sLogFile = new File(ctx.getFilesDir(), "pvb_boot.log");
        ScheduledExecutorService exe = Executors.newSingleThreadScheduledExecutor();
        exe.scheduleWithFixedDelay(new Runnable() {
            @Override
            public void run() {
                if (!sBusy.compareAndSet(false, true)) return;
                try {
                    ensure(ctx);
                } catch (Throwable th) {
                    log("ensure fatal: " + th);
                } finally {
                    sBusy.set(false);
                }
            }
        }, INIT_DELAY_SECONDS, PERIOD_SECONDS, TimeUnit.SECONDS);
    }

    private static void ensure(Context ctx) {
        boolean up = ping();
        boolean active = isAdopted();
        if (up && active) return;

        if (!up) {
            List<File> candidates = listCandidates(ctx);

            // 真机带 FishNative so 且本地没有二进制时，交给官方链下载启动（只试一次）
            if (candidates.isEmpty() && sJ0Tried.compareAndSet(false, true)) {
                if (invokeOfficialStart()) {
                    for (int i = 0; i < WAIT_PING_TIMES; i++) {
                        sleep(1000);
                        if (ping()) break;
                    }
                }
                up = ping();
                if (up) candidates = listCandidates(ctx);
            }

            if (!ping()) {
                File chosen = null;
                for (File bin : candidates) {
                    if (!launch(bin)) continue;
                    long deadline = System.currentTimeMillis() + TRIAL_WAIT_MS;
                    boolean ok = false;
                    while (System.currentTimeMillis() < deadline) {
                        sleep(500);
                        if (ping()) {
                            ok = true;
                            break;
                        }
                    }
                    if (ok) {
                        chosen = bin;
                        break;
                    }
                    log("candidate not serving, try next: " + bin.getName());
                }
                if (chosen == null) {
                    if (candidates.isEmpty()) log("no pvideo binary, keep java fallback");
                    else log("all candidates failed to serve");
                    return;
                }
                log("pvideo up via " + chosen.getName());
            }
        }

        if (!isAdopted()) {
            if (adopt()) {
                log("official manager adopted go proxy (d=true)");
            } else {
                log("adopt failed though ping is up");
            }
        }
    }

    /** 调官方 s0#Q()：内部 ping 校验成功后置 s0.d=true。 */
    private static boolean adopt() {
        ClassLoader cl = PVB.class.getClassLoader();
        try {
            Class<?> s0 = cl.loadClass("com.github.catvod.spider.merge.A.s0");
            java.lang.reflect.Method mt = s0.getDeclaredMethod("t");
            mt.setAccessible(true);
            Object inst = mt.invoke(null);
            if (inst == null) return false;
            java.lang.reflect.Method mq = s0.getDeclaredMethod("Q");
            mq.setAccessible(true);
            Object r = mq.invoke(inst);
            java.lang.reflect.Field fd = s0.getDeclaredField("d");
            fd.setAccessible(true);
            return Boolean.TRUE.equals(r) || Boolean.TRUE.equals(fd.get(inst));
        } catch (Throwable th) {
            log("adopt error: " + th.getClass().getSimpleName() + " " + th.getMessage());
            return false;
        }
    }

    /** 官方启动入口 s0#J0()：带 JNI so 的环境会下载对应 ABI 二进制并启动。 */
    private static boolean invokeOfficialStart() {
        ClassLoader cl = PVB.class.getClassLoader();
        try {
            Class<?> s0 = cl.loadClass("com.github.catvod.spider.merge.A.s0");
            java.lang.reflect.Method mj = s0.getDeclaredMethod("J0");
            mj.setAccessible(true);
            Object r = mj.invoke(null);
            log("official J0()=" + r);
            return Boolean.TRUE.equals(r);
        } catch (Throwable th) {
            log("J0 error: " + th.getClass().getSimpleName());
            return false;
        }
    }

    private static boolean isAdopted() {
        ClassLoader cl = PVB.class.getClassLoader();
        try {
            Class<?> s0 = cl.loadClass("com.github.catvod.spider.merge.A.s0");
            java.lang.reflect.Method mt = s0.getDeclaredMethod("t");
            mt.setAccessible(true);
            Object inst = mt.invoke(null);
            if (inst == null) return false;
            java.lang.reflect.Field fd = s0.getDeclaredField("d");
            fd.setAccessible(true);
            return Boolean.TRUE.equals(fd.get(inst));
        } catch (Throwable th) {
            return false;
        }
    }

    private static boolean launch(File bin) {
        try {
            //noinspection ResultOfMethodCallIgnored
            bin.setExecutable(true, false);
            File danmu = new File(bin.getParentFile(), "danmu");
            //noinspection ResultOfMethodCallIgnored
            danmu.mkdirs();
            File logf = new File(bin.getParentFile(), "pvideo.log");
            String cmd = bin.getAbsolutePath() + " -host 127.0.0.1 -port " + PORT
                    + " -danmu-dir " + danmu.getAbsolutePath()
                    + " >> " + logf.getAbsolutePath() + " 2>&1";
            Process p = Runtime.getRuntime().exec(new String[]{"sh", "-c", cmd});
            synchronized (sHeld) {
                sHeld.add(p);
            }
            return true;
        } catch (Throwable th) {
            log("launch error " + bin.getName() + ": " + th.getMessage());
            return false;
        }
    }

    // ------------------------------------------------------------------
    // ABI 候选发现与排序
    // ------------------------------------------------------------------

    private static List<File> listCandidates(Context ctx) {
        File dir = ctx.getFilesDir();
        Set<String> names = new LinkedHashSet<String>();
        boolean kernel64 = new File("/system/bin/linker64").exists()
                || new File("/system/lib64").isDirectory();
        for (String tag : preference(kernel64)) {
            if ("arm64".equals(tag)) {
                names.add("pvideo-arm64-v8a");
                names.add("pvideo-arm64");
            } else if ("arm".equals(tag)) {
                names.add("pvideo-armeabi-v7a");
                names.add("pvideo-arm");
                names.add("pvideo-armv7");
            } else if ("x64".equals(tag)) {
                names.add("pvideo-x86_64");
            } else if ("x86".equals(tag)) {
                names.add("pvideo-x86");
            }
        }
        // 其它命名/历史命名兜底
        names.add("pvideo");

        List<File> out = new ArrayList<File>();
        Set<String> seen = new LinkedHashSet<String>();
        for (String n : names) {
            File f = new File(dir, n);
            if (usable(f) && seen.add(f.getAbsolutePath())) out.add(f);
        }
        // 目录扫描：任何 pvideo 开头的 ELF 文件都纳入（如未来改名）
        File[] glob = dir.listFiles(new FileFilter() {
            @Override
            public boolean accept(File f) {
                return f.isFile() && f.getName().startsWith("pvideo");
            }
        });
        if (glob != null) {
            for (File f : glob) {
                if (usable(f) && seen.add(f.getAbsolutePath())) out.add(f);
            }
        }

        // ELF 架构评分排序
        List<String> pref = preference(kernel64);
        List<File> scored = new ArrayList<File>();
        for (File f : out) {
            if (score(f, pref) > 0) scored.add(f);
        }
        java.util.Collections.sort(scored, new java.util.Comparator<File>() {
            @Override
            public int compare(File a, File b) {
                int sa = score(a, pref);
                int sb = score(b, pref);
                return sb - sa;
            }
        });
        return scored;
    }

    private static boolean usable(File f) {
        return f.isFile() && f.length() > 1024 * 1024;
    }

    /** 架构偏好：arm64 > arm(+arm64) > x64 > x86(+x64)，与官方 ABI 顺序一致。 */
    private static List<String> preference(boolean kernel64) {
        List<String> pref = new ArrayList<String>();
        boolean hasArm64 = false, hasArm = false, hasX64 = false, hasX86 = false;
        try {
            for (String abi : Build.SUPPORTED_ABIS) {
                if (abi == null) continue;
                if (abi.contains("arm64")) hasArm64 = true;
                else if (abi.contains("arm")) hasArm = true;
                else if (abi.contains("x86_64")) hasX64 = true;
                else if (abi.startsWith("x86")) hasX86 = true;
            }
        } catch (Throwable ignored) {
        }
        if (hasArm64) {
            pref.add("arm64");
            pref.add("arm");
        } else if (hasArm) {
            pref.add("arm");
            if (kernel64) pref.add("arm64"); // 32 位进程 + 64 位内核
        }
        if (hasX64) {
            pref.add("x64");
            pref.add("x86");
        } else if (hasX86) {
            if (kernel64) pref.add("x64"); // 本机场景：32 位 x86 进程跑 x86_64 二进制
            pref.add("x86");
        }
        if (pref.isEmpty()) {
            pref.add(kernel64 ? "arm64" : "arm");
            pref.add(kernel64 ? "x64" : "x86");
        }
        return pref;
    }

    private static int score(File f, List<String> pref) {
        int arch = readElfMachine(f);
        String tag;
        switch (arch) {
            case M_ARM64: tag = "arm64"; break;
            case M_ARM: tag = "arm"; break;
            case M_X64: tag = "x64"; break;
            case M_X86: tag = "x86"; break;
            default: return 0;
        }
        int idx = pref.indexOf(tag);
        // 偏好表外的架构（如 x86 上的 ARM 转译）给最低尝试分
        return idx >= 0 ? 10 - idx : 1;
    }

    /** 读 ELF 头 e_machine；非 ELF 返回 -1。 */
    private static int readElfMachine(File f) {
        FileInputStream in = null;
        try {
            in = new FileInputStream(f);
            byte[] h = new byte[20];
            int total = 0;
            while (total < h.length) {
                int n = in.read(h, total, h.length - total);
                if (n < 0) break;
                total += n;
            }
            if (total < 20) return -1;
            if (h[0] != 0x7f || h[1] != 'E' || h[2] != 'L' || h[3] != 'F') return -1;
            return h[19] << 8 | (h[18] & 0xff);
        } catch (Throwable t) {
            return -1;
        } finally {
            if (in != null) try {
                in.close();
            } catch (Exception ignored) {
            }
        }
    }

    // ------------------------------------------------------------------
    // FishConfig 控制台图标地址改写
    // ------------------------------------------------------------------

    private static final String OLD_ICON_BASE =
            "https://tc-new.z.wiki/autoupload/k2fxc/configicon/";
    // org.json 序列化会把 / 转义为 \/，需同时处理
    private static final String OLD_ICON_BASE_ESC =
            "https:\\/\\/tc-new.z.wiki\\/autoupload\\/k2fxc\\/configicon\\/";
    private static final String FALLBACK_ICON_BASE =
            "https://cnb.cool/dodgezhang/tvbox/-/git/raw/main/moyu/ico/";

    /**
     * FishConfig.categoryContent 返回前调用：把第三方图床的控制台图标地址
     * 替换为线路自身 ico 目录（与 my.json 同级），使线路图标自包含。
     */
    public static String rewriteIcons(String json) {
        if (json == null) return json;
        if (json.indexOf(OLD_ICON_BASE) < 0 && json.indexOf(OLD_ICON_BASE_ESC) < 0) return json;
        try {
            String base = iconBase();
            return json.replace(OLD_ICON_BASE, base)
                    .replace(OLD_ICON_BASE_ESC, base.replace("/", "\\/"));
        } catch (Throwable th) {
            return json;
        }
    }

    /** 跟随当前线路地址：<config 所在目录>/ico/；取不到时回退正式仓库地址。 */
    private static String iconBase() {
        String u = currentConfigUrl();
        if (u != null) {
            try {
                int q = u.indexOf('?');
                if (q >= 0) u = u.substring(0, q);
                int h = u.indexOf('#');
                if (h >= 0) u = u.substring(0, h);
                int slash = u.lastIndexOf('/');
                if (slash > 8) return u.substring(0, slash + 1) + "ico/";
            } catch (Throwable ignored) {
            }
        }
        return FALLBACK_ICON_BASE;
    }

    /** 反射读取宿主当前 VOD 线路地址（FongMi VodConfig.get().getUrl()）。 */
    private static String currentConfigUrl() {
        try {
            ClassLoader cl = PVB.class.getClassLoader();
            Class<?> vc = cl.loadClass("com.fongmi.android.tv.api.config.VodConfig");
            Object cfg = vc.getMethod("get").invoke(null);
            if (cfg == null) return null;
            Object url = cfg.getClass().getMethod("getUrl").invoke(cfg);
            return url == null ? null : url.toString();
        } catch (Throwable th) {
            return null;
        }
    }

    private static void sleep(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException ignored) {
        }
    }

    private static boolean ping() {
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL("http://127.0.0.1:" + PORT + "/api/ping").openConnection();
            conn.setConnectTimeout(800);
            conn.setReadTimeout(800);
            if (conn.getResponseCode() != 200) return false;
            InputStream in = conn.getInputStream();
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            byte[] buf = new byte[256];
            int n;
            while ((n = in.read(buf)) >= 0) bos.write(buf, 0, n);
            in.close();
            return "ok".equals(new String(bos.toByteArray(), "UTF-8").trim());
        } catch (Exception e) {
            return false;
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    private static synchronized void log(String msg) {
        try {
            android.util.Log.i("PVB", msg);
        } catch (Throwable ignored) {
        }
        File f = sLogFile;
        if (f != null) {
            FileOutputStream fos = null;
            try {
                fos = new FileOutputStream(f, true);
                fos.write((msg + '\n').getBytes("UTF-8"));
            } catch (Throwable ignored) {
            } finally {
                if (fos != null) try {
                    fos.close();
                } catch (Exception ignored) {
                }
            }
        }
    }
}
