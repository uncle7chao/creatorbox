package com.creatorbox.m0probe

import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

/**
 * M0-V1 分享 Intent 验证探针
 *
 * 目的：确认抖音 / 小红书 / 快手 的分享面板是否真的走系统 ACTION_SEND。
 *
 * 使用方法：
 * 1. 安装到真机
 * 2. 从目标 App 分享一个视频到微信
 * 3. 在微信会话列表里应该能看到本应用（探针）；若看不到，说明该 App 未走系统分享面板
 * 4. 无论能否看到，都点"读取剪贴板"兜底检查
 * 5. 把抓到的日志贴回给开发
 */
class MainActivity : AppCompatActivity() {

    companion object {
        const val TAG = "CBProbe"
    }

    private lateinit var output: TextView
    private lateinit var input: EditText
    private val log = StringBuilder()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        output = findViewById(R.id.output)
        input = findViewById(R.id.input)

        findViewById<Button>(R.id.btn_read_clipboard).setOnClickListener {
            readClipboard()
        }
        findViewById<Button>(R.id.btn_clear).setOnClickListener {
            log.setLength(0)
            output.text = ""
            input.setText("")
        }
        findViewById<Button>(R.id.btn_copy).setOnClickListener {
            copyToClipboard(log.toString())
        }
        findViewById<Button>(R.id.btn_probe_self).setOnClickListener {
            probeSelf()
        }

        // App 启动时如果是从分享拉起的，onCreate 就能拿到 Intent
        if (intent?.action == Intent.ACTION_SEND) {
            log.append("=== 冷启动即收到 ACTION_SEND ===\n")
            dumpIntent("COLD_START", intent)
        }

        logHeader()
    }

    /** 打印设备与系统信息 */
    private fun logHeader() {
        log.append("=== 环境信息 ===\n")
        log.append("设备: ${Build.MANUFACTURER} ${Build.MODEL}\n")
        log.append("Android: ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})\n")
        log.append("时间: ${java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", java.util.Locale.getDefault()).format(java.util.Date())}\n")
        log.append("本应用可见性: 已在微信分享面板中注册 text/plain + image/*\n")
        log.append("\n=== 待测记录 ===\n")
        log.append("请依次测试：抖音 → 小红书 → 快手 → 视频号\n")
        log.append("每个平台记录：能否在分享面板看到本应用 + 抓到的内容\n")
        log.append("--------------------------------------------------\n\n")
        flush()
    }

    /**
     * 分享入口：由于 intent-filter 与 ACTION_MAIN 分开，
     * 从微信分享过来时会新建一个实例并走 onNewIntent
     */
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        log.append("=== onNewIntent 收到分享 ===\n")
        dumpIntent("ON_NEW_INTENT", intent)
    }

    /** 全量打印 Intent 内容 */
    private fun dumpIntent(tag: String, i: Intent?) {
        if (i == null) {
            log.append("[$tag] Intent 为 null\n\n")
            flush()
            return
        }
        log.append("[$tag]\n")
        log.append("  action   : ${i.action}\n")
        log.append("  type     : ${i.type}\n")
        log.append("  data     : ${i.data}\n")
        log.append("  flags    : 0x${Integer.toHexString(i.flags)}\n")
        log.append("  category : ${i.categories?.joinToString(", ")}\n")
        log.append("  clipData : ${i.clipData}\n")

        // 关键：文本内容
        val text = i.getStringExtra(Intent.EXTRA_TEXT)
        val subject = i.getStringExtra(Intent.EXTRA_SUBJECT)
        log.append("  EXTRA_SUBJECT : $subject\n")
        log.append("  EXTRA_TEXT   : $text\n")

        if (!text.isNullOrBlank()) {
            analyzeText(text)
        }

        // 图片
        val stream = i.getParcelableExtra<android.net.Uri>(Intent.EXTRA_STREAM)
        if (stream != null) {
            log.append("  EXTRA_STREAM : $stream\n")
        }

        // 全量 extras
        log.append("  --- 全部 extras ---\n")
        try {
            val extras = i.extras
            if (extras != null) {
                for (key in extras.keySet()) {
                    val value = try {
                        extras.get(key)?.toString()?.take(300)
                    } catch (e: Exception) {
                        "<无法读取: ${e.message}>"
                    }
                    log.append("    $key = $value\n")
                }
            } else {
                log.append("    (无)\n")
            }
        } catch (e: Exception) {
            log.append("    读取失败: ${e.message}\n")
        }
        log.append("\n")
        flush()
    }

    /**
     * 分析文本内容：判断能否提取到可用链接
     */
    private fun analyzeText(text: String) {
        log.append("  --- 文本分析 ---\n")
        log.append("    长度: ${text.length}\n")

        val urlRegex = Regex("""https?://[^\s，。、"'）)】]+""")
        val urls = urlRegex.findAll(text).map { it.value }.toList()

        if (urls.isEmpty()) {
            log.append("    ⛔ 未提取到 http(s) 链接 —— 该平台可能未走系统分享\n")
        } else {
            log.append("    ✅ 提取到 ${urls.size} 个链接:\n")
            urls.forEachIndexed { idx, u ->
                log.append("      [$idx] $u\n")
            }
            // 试探短链能否解析出视频 id
            urls.firstOrNull()?.let { probe(u) }
        }
        log.append("\n")
    }

    /** 用 HEAD 探测链接可达性，不下载内容 */
    private fun probe(url: String) {
        Thread {
            try {
                val conn = (java.net.URL(url).openConnection() as java.net.HttpURLConnection).apply {
                    requestMethod = "GET"
                    instanceFollowRedirects = false
                    connectTimeout = 8000
                    readTimeout = 8000
                    setRequestProperty("User-Agent",
                        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15")
                }
                conn.connect()
                val code = conn.responseCode
                val location = conn.getHeaderField("Location")
                val resolved = if (code in 300..399 && !location.isNullOrBlank()) {
                    Uri.parse(url).resolve(location)?.toString() ?: location
                } else url

                // 解析后是否含视频 id
                val hasId = extractVideoId(resolved) != null
                log.append("      → HTTP $code")
                if (!location.isNullOrBlank()) {
                    log.append(" → 302 $location")
                }
                log.append("\n")
                log.append("      → 视频ID: ${extractVideoId(resolved) ?: "未提取到"} ${if (hasId) "✅" else "⚠️"}\n")
                log.append("      → 域名: ${Uri.parse(resolved).host}\n")
            } catch (e: Exception) {
                log.append("      → 探测失败: ${e.message}\n")
            }
            flush()
        }.start()
    }

    /** 从 URL 中提取视频 id（各家规则不同，此处覆盖常见命名） */
    private fun extractVideoId(url: String): String? {
        val patterns = listOf(
            Regex("""/video/(\d{6,})"""),            // 抖音 v.douyin.com/xxx/ → 后续 302
            Regex("""aweme/v1/(?:feed|aweme)/[^?]*?aweme_id=(\d{6,})"""),
            Regex("""/aweme/(\d{6,})"""),
            Regex("""modal_id=(\d{6,})"""),
            Regex("""/note/(\d{6,})"""),               // 小红书
            Regex("""explore/([0-9a-zA-Z]{16,})"""),
            Regex("""/short-video/(\d{6,})"""),
            Regex("""videoId=([0-9a-zA-Z]{6,})"""),
            Regex("""/v/([0-9a-zA-Z]{6,})""")
        )
        for (p in patterns) {
            p.find(url)?.groupValues?.getOrNull(1)?.let { return it }
        }
        return null
    }

    /** 剪贴板兜底通道 */
    private fun readClipboard() {
        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        if (!cm.hasPrimaryClip()) {
            log.append("[剪贴板] 为空\n")
            flush()
            return
        }
        val clip = cm.primaryClip ?: return
        log.append("[剪贴板] 项数: ${clip.itemCount}\n")
        for (idx in 0 until clip.itemCount) {
            val item = clip.getItemAt(idx)
            val text = item.text?.toString()
            log.append("  [$idx] text: $text\n")
            if (!text.isNullOrBlank()) {
                analyzeText(text)
            }
        }
        log.append("\n")
        flush()
    }

    /** 自检：确认 intent-filter 已正确注册 */
    private fun probeSelf() {
        val pm = packageManager
        val targets = listOf(
            Intent(Intent.ACTION_SEND, Uri.parse("dummy://x")).setType("text/plain"),
            Intent(Intent.ACTION_SEND, Uri.parse("dummy://x")).setType("image/jpeg")
        )
        log.append("=== 自检：本应用是否可被系统分享面板识别 ===\n")
        targets.forEach { probeIntent ->
            val label = probeIntent.type ?: "?"
            val resolved = pm.resolveActivity(probeIntent, 0)
            log.append("  $label → ${if (resolved != null) "✅ 已注册" else "⛔ 未注册"}\n")
        }
        log.append("\n说明：这里只验证本应用自身配置是否正确。\n")
        log.append("平台是否走系统分享，需在目标 App 内实测并观察分享面板是否出现本应用。\n\n")
        flush()
    }

    private fun copyToClipboard(s: String) {
        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        cm.setPrimaryClip(android.content.ClipData.newPlainText("CBProbe", s))
        android.widget.Toast.makeText(this, "已复制，粘贴给我即可", android.widget.Toast.LENGTH_SHORT).show()
    }

    private fun flush() {
        runOnUiThread {
            output.text = log.toString()
            output.post { output.parent?.requestFocus() }
        }
    }
}
