package eu.kanade.tachiyomi.extension.zh.jinmantiantang

import android.content.SharedPreferences
import android.text.InputType
import androidx.preference.EditTextPreference
import androidx.preference.PreferenceScreen
import eu.kanade.tachiyomi.network.POST
import keiyoushi.utils.parseAs
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable
import okhttp3.FormBody
import okhttp3.Headers
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.Response
import java.io.IOException

internal const val USERNAME_PREF = "jmUsername"
internal const val PASSWORD_PREF = "jmPassword"
internal const val LOGGED_IN_HOST_PREF = "jmLoggedInHost"

private const val LOGIN_PATH = "/login"

/**
 * 站点未登录访问受限作品时，会把请求 301 到该路径（伪装成"作品不存在"），
 * 而不是跳转到登录页。实测：2026-09-12。
 */
private const val LOGIN_ERROR_PATH = "/error/album_missing"

/** 站点登录响应的 status 字段：1 = 成功，2 = 凭据无效。实测：2026-09-12。 */
private const val LOGIN_STATUS_SUCCESS = 1

@Serializable
internal class LoginResult(
    val status: Int,
    val errors: List<String> = emptyList(),
)

/**
 * 禁漫账号登录与会话自愈。
 *
 * 会话凭证由站点以 `Set-Cookie` 下发，交给宿主的 CookieJar 自动持久化与携带
 * （`AndroidCookieJar` 底层是 `android.webkit.CookieManager`，跨重启有效），
 * 因此这里只需要做三件事：判断是否需要登录、发一次登录请求、记住登录过的域名。
 *
 * 实测接口契约（2026-09-12）：
 *  - `POST /login`，表单 `username` / `password` / `submit_login=1`
 *  - 必须带 `X-Requested-With: XMLHttpRequest` 与 `Origin` / `Referer`
 *  - **成功与失败都返回 HTTP 200**，判据在响应体 `status` 字段
 *  - 会话凭证绑定域名，换镜像后必须重新登录
 */
internal class AuthManager(
    private val preferences: SharedPreferences,
    private val baseUrl: () -> String,
    private val headers: () -> Headers,
    private val client: () -> OkHttpClient,
) {
    private val username: String get() = preferences.getString(USERNAME_PREF, "")!!
    private val password: String get() = preferences.getString(PASSWORD_PREF, "")!!

    /**
     * 当前镜像的 host。主类的 `baseUrl` 是一次性求值的 `val`，运行期不会变，
     * 因此这里缓存解析结果，避免每个请求都重新解析 URL。
     */
    private val baseHost: String by lazy { baseUrl().toHttpUrl().host }

    private var loggedInHost: String
        get() = preferences.getString(LOGGED_IN_HOST_PREF, "")!!
        set(value) {
            preferences.edit().putString(LOGGED_IN_HOST_PREF, value).apply()
        }

    /** 用户是否填写了完整的凭据。 */
    val isConfigured: Boolean get() = username.isNotBlank() && password.isNotBlank()

    /**
     * 是否需要（重新）登录。
     *
     * 凭据未填写时恒为 `false` —— 登录是可选的增强能力，
     * 未配置的用户保持与旧版本完全一致的行为。
     */
    val needsLogin: Boolean get() = isConfigured && loggedInHost != baseHost

    /** 仅清除本地的"已登录域名"记录；会话 Cookie 由宿主 CookieJar 持有。 */
    fun clearSession() {
        loggedInHost = ""
    }

    /**
     * 登录去重锁。
     *
     * Mihon 在阅读/更新书架时会并发发起多个请求，而每个请求都会各自判断"是否需要登录"。
     * 没有这把锁时，N 个并发请求会各发一次登录 POST（首次进入阅读、切换镜像后尤其明显），
     * 既浪费请求、也可能触发站点风控。
     */
    private val loginLock = Any()

    /**
     * 当前会话代数。请求发出前记录代数；会话失效时只有仍持有旧代数的请求
     * 才允许执行一次重登，避免同一轮失效被多个并发请求重复 POST。
     */
    @Volatile
    private var sessionGeneration = 0

    /**
     * 执行登录。凭据无效或接口异常时抛 [IOException]，消息面向用户。
     *
     * 并发安全：先到的线程登录完成后，其余线程发现"已是登录态"就直接返回，复用同一次登录。
     */
    fun login() {
        if (!isConfigured) return

        synchronized(loginLock) {
            // 双重检查：并发场景下可能已被其它线程登完
            if (!needsLogin) return
            performLogin()
            sessionGeneration++
        }
    }

    /**
     * 应用启动时主动建立一次会话。
     *
     * Mihon 在 AppScope 中初始化 ExtensionManager 时会构造所有 Source，因此这里可以在
     * 软件启动阶段异步登录，而不必等到用户打开受限作品。登录结果不向 UI 报错：
     * 失败时后续请求仍会走 [login] / [reLogin] 兜底。
     */
    fun loginOnStartup() {
        if (!isConfigured) return

        CoroutineScope(Dispatchers.IO).launch {
            runCatching {
                synchronized(loginLock) {
                    performLogin()
                    sessionGeneration++
                }
            }
        }
    }

    /**
     * 会话失效后的重登：同一条会话失效事件只允许一个请求真正发起登录。
     *
     * 请求发出前记录旧代数；进入锁后若代数已变化，说明另一个请求已经完成了重登，
     * 当前请求直接复用新会话并重试原请求。代数在发请求前递增，因此即使重登失败，
     * 同一轮并发请求也不会反复提交账号密码。
     */
    private fun reLogin(expectedGeneration: Int) {
        if (!isConfigured) return

        synchronized(loginLock) {
            if (sessionGeneration != expectedGeneration) return
            sessionGeneration++
            clearSession()
            performLogin()
        }
    }

    /** 真正发出登录请求。调用方必须已持有 [loginLock]。 */
    private fun performLogin() {
        val base = baseUrl()

        val body = FormBody.Builder()
            .add("username", username)
            .add("password", password)
            .add("submit_login", "1")
            .build()

        val requestHeaders = headers().newBuilder()
            .set("X-Requested-With", "XMLHttpRequest")
            .set("Referer", "$base/")
            .set("Origin", base)
            .build()

        // 走宿主原始客户端，避免再次进入本扩展的拦截器链
        val result = client()
            .newCall(POST("$base$LOGIN_PATH", requestHeaders, body))
            .execute()
            .use { response ->
                if (!response.isSuccessful) {
                    throw IOException("禁漫登录失败：HTTP ${response.code}")
                }
                // 站点被 CF 挑战或维护时会返回 HTML，kotlinx 抛的是 SerializationException /
                // MissingFieldException，都不是 IOException。这里统一转成 IOException，让
                // "失败即 IOException" 的契约成立——否则用户看到的是解析器的内部报错文案。
                runCatching { response.parseAs<LoginResult>() }.getOrElse { cause ->
                    throw IOException(
                        "禁漫登录失败：站点返回了非预期内容（可能被 Cloudflare 拦截或站点维护中）",
                        cause,
                    )
                }
            }

        if (result.status != LOGIN_STATUS_SUCCESS) {
            // errors 里的文案由站点给出，原样展示
            throw IOException(result.errors.firstOrNull() ?: "禁漫登录失败（status=${result.status}）")
        }

        loggedInHost = baseHost
    }

    /**
     * 请求拦截：按需登录；若被踢回 [LOGIN_ERROR_PATH] 则重登一次并重试。
     */
    fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()

        // 登录请求自身放行。注意：login() 走的是宿主 client（不含本拦截器），所以这里不是
        // 为了防递归，而是兜住"其它调用方拿主 client 去请求 /login"这种情况。
        if (request.url.encodedPath == LOGIN_PATH) {
            return chain.proceed(request)
        }

        // 记录请求发出前的会话代数；用于判断响应返回时是否已有其他线程完成重登。
        val requestGeneration = sessionGeneration

        // 先取一次登录判定，用于判断本次请求是否已经登录过
        val needsLoginNow = needsLogin
        if (needsLoginNow) {
            login()
        }

        var response = chain.proceed(request)

        // 会话可能已在服务端失效（本地记录的域名仍然匹配）。
        // 此时重登一次再试；每个请求最多重试一次，不递归。
        if (!needsLoginNow && isConfigured && response.request.url.encodedPath == LOGIN_ERROR_PATH) {
            response.close()
            // 只允许观察到同一代数的首个请求执行重登，其余并发请求复用结果。
            reLogin(requestGeneration)
            response = chain.proceed(request)
        }

        return response
    }
}

/**
 * 账号相关的设置项，置于设置页最前面。
 */
internal fun addAuthPreferences(screen: PreferenceScreen, preferences: SharedPreferences) {
    EditTextPreference(screen.context).apply {
        key = USERNAME_PREF
        title = "禁漫账号"
        summary = "填入账号密码后自动登录，可解锁少量需要登录的题材"
        dialogTitle = "请输入禁漫账号"
        setDefaultValue("")
    }.also(screen::addPreference)

    EditTextPreference(screen.context).apply {
        key = PASSWORD_PREF
        title = "密码"
        summary = "留空则不使用登录功能"
        dialogTitle = "请输入密码"
        setDefaultValue("")
        setOnBindEditTextListener {
            it.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
    }.also(screen::addPreference)

    // 登录状态行。注意：这里刻意用 EditTextPreference 而非 androidx.preference.Preference ——
    // 后者在本扩展的编译类路径上无法以 Preference(context) 形式构造（实测 CI 编译报
    // "Too many arguments for 'constructor(): Preference'"），而其子类均可正常构造。
    // 点击监听器返回 true 以抑制默认的编辑对话框，使该项表现为只读的操作行。
    EditTextPreference(screen.context).apply {
        key = "jmLoginStatus"
        // SharedPreferences.getString() 在 Kotlin 里返回 String?，必须处理可空性
        val host = preferences.getString(LOGGED_IN_HOST_PREF, "").orEmpty()
        title = if (host.isBlank()) "登录状态：未登录" else "登录状态：已登录（$host）"
        summary = "点击可清除登录状态，下次请求会重新登录"
        setOnBindEditTextListener { it.inputType = InputType.TYPE_NULL }
        setOnPreferenceClickListener {
            preferences.edit().remove(LOGGED_IN_HOST_PREF).apply()
            title = "登录状态：未登录"
            true
        }
    }.also(screen::addPreference)
}
