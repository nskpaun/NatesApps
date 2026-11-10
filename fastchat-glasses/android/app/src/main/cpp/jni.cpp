// JNI bridge between com.natesapps.fastchat.llm.LlamaEngine and the engine in llm_engine.cpp.
// Text crosses the boundary as UTF-8 byte arrays, never as JNI strings: JNI's "modified UTF-8"
// mangles emoji and other characters outside the basic plane.
#include <jni.h>

#include <android/log.h>
#include <string>

#include "llama.h"
#include "llm_engine.h"

#define TAG "FastChatLLM"

namespace {

std::string to_string(JNIEnv* env, jbyteArray bytes) {
    if (!bytes) return {};
    const jsize n = env->GetArrayLength(bytes);
    std::string out((size_t) n, '\0');
    if (n > 0) env->GetByteArrayRegion(bytes, 0, n, (jbyte*) out.data());
    return out;
}

void throw_error(JNIEnv* env, const std::string& message) {
    env->ThrowNew(env->FindClass("java/lang/IllegalStateException"), message.c_str());
}

void log_to_logcat(enum ggml_log_level level, const char* text, void*) {
    if (level == GGML_LOG_LEVEL_ERROR) __android_log_print(ANDROID_LOG_ERROR, TAG, "%s", text);
    else if (level == GGML_LOG_LEVEL_WARN) __android_log_print(ANDROID_LOG_WARN, TAG, "%s", text);
}

fastchat::Engine* engine_of(jlong handle) { return reinterpret_cast<fastchat::Engine*>(handle); }

} // namespace

extern "C" {

JNIEXPORT jlong JNICALL
Java_com_natesapps_fastchat_llm_LlamaEngine_nativeLoad(JNIEnv* env, jclass, jbyteArray path,
                                                       jint n_ctx, jint n_threads) {
    llama_log_set(log_to_logcat, nullptr);
    fastchat::LoadParams params;
    params.n_ctx = n_ctx;
    params.n_threads = n_threads;
    std::string error;
    auto engine = fastchat::Engine::load(to_string(env, path), params, &error);
    if (!engine) {
        throw_error(env, error);
        return 0;
    }
    return reinterpret_cast<jlong>(engine.release());
}

JNIEXPORT void JNICALL
Java_com_natesapps_fastchat_llm_LlamaEngine_nativePrime(JNIEnv* env, jclass, jlong handle,
                                                        jbyteArray prefix) {
    std::string error;
    if (!engine_of(handle)->prime(to_string(env, prefix), &error) && error != "cancelled") {
        throw_error(env, error);
    }
}

// Returns {prompt tokens, prompt ms, output tokens, output ms, prefix reused (0/1)}.
JNIEXPORT jlongArray JNICALL
Java_com_natesapps_fastchat_llm_LlamaEngine_nativeGenerate(
    JNIEnv* env, jclass, jlong handle, jbyteArray prefix, jbyteArray suffix, jbyteArray grammar,
    jfloat temperature, jfloat top_p, jint top_k, jfloat presence_penalty, jint max_tokens,
    jobject sink) {
    jclass sink_class = env->GetObjectClass(sink);
    jmethodID on_text = env->GetMethodID(sink_class, "onText", "([B)Z");

    fastchat::GenParams params;
    params.temperature = temperature;
    params.top_p = top_p;
    params.top_k = top_k;
    params.presence_penalty = presence_penalty;
    params.max_tokens = max_tokens;

    fastchat::GenStats stats;
    std::string error;
    const bool ok = engine_of(handle)->generate(
        to_string(env, prefix), to_string(env, suffix), to_string(env, grammar), params,
        [&](const std::string& text) {
            jbyteArray bytes = env->NewByteArray((jsize) text.size());
            env->SetByteArrayRegion(bytes, 0, (jsize) text.size(), (const jbyte*) text.data());
            const jboolean keep_going = env->CallBooleanMethod(sink, on_text, bytes);
            env->DeleteLocalRef(bytes);
            return keep_going == JNI_TRUE && !env->ExceptionCheck();
        },
        &stats, &error);

    if (env->ExceptionCheck()) return nullptr; // the Kotlin callback threw; let it propagate
    if (!ok && !stats.cancelled) {
        throw_error(env, error);
        return nullptr;
    }
    const jlong values[5] = {stats.prompt_tokens, (jlong) stats.prompt_ms, stats.output_tokens,
                             (jlong) stats.output_ms, stats.prefix_reused ? 1 : 0};
    jlongArray result = env->NewLongArray(5);
    env->SetLongArrayRegion(result, 0, 5, values);
    return result;
}

JNIEXPORT void JNICALL
Java_com_natesapps_fastchat_llm_LlamaEngine_nativeCancel(JNIEnv*, jclass, jlong handle) {
    engine_of(handle)->cancel();
}

JNIEXPORT void JNICALL
Java_com_natesapps_fastchat_llm_LlamaEngine_nativeFree(JNIEnv*, jclass, jlong handle) {
    delete engine_of(handle);
}

} // extern "C"
