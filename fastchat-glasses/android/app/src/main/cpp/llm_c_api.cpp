// See llm_c_api.h.
#include "llm_c_api.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <string>

#include "llama.h"
#include "llm_engine.h"

struct qt_engine {
    std::unique_ptr<fastchat::Engine> engine;
};

namespace {

void set_error(char** out, const std::string& message) {
    if (!out) return;
    *out = static_cast<char*>(std::malloc(message.size() + 1));
    if (*out) std::memcpy(*out, message.c_str(), message.size() + 1);
}

// Only warnings and errors from llama.cpp reach the console.
void quiet_log(enum ggml_log_level level, const char* text, void*) {
    if (level == GGML_LOG_LEVEL_ERROR || level == GGML_LOG_LEVEL_WARN) std::fputs(text, stderr);
}

} // namespace

extern "C" {

qt_engine* qt_engine_load(const char* model_path, int32_t n_ctx, int32_t n_threads, char** error) {
    llama_log_set(quiet_log, nullptr);
    fastchat::LoadParams params;
    params.n_ctx = n_ctx;
    params.n_threads = n_threads;
    std::string message;
    auto engine = fastchat::Engine::load(model_path ? model_path : "", params, &message);
    if (!engine) {
        set_error(error, message);
        return nullptr;
    }
    return new qt_engine{std::move(engine)};
}

bool qt_engine_prime(qt_engine* engine, const char* prefix, char** error) {
    std::string message;
    if (engine->engine->prime(prefix ? prefix : "", &message) || message == "cancelled") return true;
    set_error(error, message);
    return false;
}

bool qt_engine_generate(qt_engine* engine, const char* prefix, const char* suffix, const char* grammar,
                        qt_gen_params params, qt_text_callback on_text, void* context,
                        qt_stats* stats, char** error) {
    fastchat::GenParams gen;
    gen.temperature = params.temperature;
    gen.top_p = params.top_p;
    gen.top_k = params.top_k;
    gen.presence_penalty = params.presence_penalty;
    gen.max_tokens = params.max_tokens;

    fastchat::GenStats out;
    std::string message;
    const bool ok = engine->engine->generate(
        prefix ? prefix : "", suffix ? suffix : "", grammar ? grammar : "", gen,
        [&](const std::string& text) { return on_text(text.data(), (int32_t) text.size(), context); },
        &out, &message);
    if (stats) {
        stats->prompt_tokens = out.prompt_tokens;
        stats->prompt_ms = (int64_t) out.prompt_ms;
        stats->output_tokens = out.output_tokens;
        stats->output_ms = (int64_t) out.output_ms;
        stats->prefix_reused = out.prefix_reused;
        stats->cancelled = out.cancelled;
    }
    if (ok || out.cancelled) return true;
    set_error(error, message);
    return false;
}

void qt_engine_cancel(qt_engine* engine) { engine->engine->cancel(); }

void qt_engine_free(qt_engine* engine) { delete engine; }

void qt_free_string(char* text) { std::free(text); }

} // extern "C"
