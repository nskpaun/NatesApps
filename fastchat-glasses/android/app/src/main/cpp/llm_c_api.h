// Plain C interface to the engine in llm_engine.cpp, for the iPhone app (Swift imports it
// directly). The Android app uses jni.cpp instead; both wrap the same engine.
// All text is UTF-8. Errors come back as a malloc'd string the caller frees with qt_free_string.
#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct qt_engine qt_engine;

typedef struct qt_stats {
    int32_t prompt_tokens;
    int64_t prompt_ms;
    int32_t output_tokens;
    int64_t output_ms;
    bool prefix_reused;
    bool cancelled;
} qt_stats;

typedef struct qt_gen_params {
    float temperature;
    float top_p;
    int32_t top_k;
    float presence_penalty;
    int32_t max_tokens;
} qt_gen_params;

// Receives output as it is written, cut on UTF-8 character boundaries. Return false to stop.
typedef bool (*qt_text_callback)(const char* text, int32_t length, void* context);

// Returns NULL and sets *error if the model cannot be loaded.
qt_engine* qt_engine_load(const char* model_path, int32_t n_ctx, int32_t n_threads, char** error);

// Returns false and sets *error on failure. Being cancelled is not a failure.
bool qt_engine_prime(qt_engine* engine, const char* prefix, char** error);

bool qt_engine_generate(qt_engine* engine, const char* prefix, const char* suffix, const char* grammar,
                        qt_gen_params params, qt_text_callback on_text, void* context,
                        qt_stats* stats, char** error);

// Stops the prime or generate in progress, from any thread.
void qt_engine_cancel(qt_engine* engine);

void qt_engine_free(qt_engine* engine);

void qt_free_string(char* text);

#ifdef __cplusplus
}
#endif
