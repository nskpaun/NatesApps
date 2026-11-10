// A small text-generation engine on top of llama.cpp, shared by the Android JNI bridge (jni.cpp)
// and the desktop test tool (llm_cli.cpp), so the exact code that runs on the phone can be
// exercised against the real model on a laptop.
#pragma once

#include <atomic>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <vector>

struct llama_model;
struct llama_context;
struct llama_vocab;

namespace fastchat {

struct LoadParams {
    int n_ctx = 2048;
    int n_threads = 4;
};

struct GenParams {
    // The settings the reply prompt was tuned with.
    float temperature = 0.7f;
    float top_p = 0.8f;
    int top_k = 20;
    float presence_penalty = 1.5f;
    int max_tokens = 160;
    uint32_t seed = 0xFFFFFFFF; // random
};

struct GenStats {
    int prompt_tokens = 0;   // tokens actually evaluated for the prompt (cached prefix excluded)
    double prompt_ms = 0;
    int output_tokens = 0;
    double output_ms = 0;
    bool prefix_reused = false;
    bool cancelled = false;
};

class Engine {
public:
    // Returns nullptr and fills `error` if the model cannot be loaded.
    static std::unique_ptr<Engine> load(const std::string& model_path, const LoadParams& params,
                                        std::string* error);
    ~Engine();

    // Evaluates `prefix` and keeps a snapshot of the model state after it, so later generate()
    // calls with the same prefix skip straight to the part that changed.
    bool prime(const std::string& prefix, std::string* error);

    // Completes prefix + suffix. `grammar` is a GBNF grammar constraining the output ("" for
    // none). `on_text` receives the output as it is produced, always cut on UTF-8 character
    // boundaries; returning false stops generation.
    bool generate(const std::string& prefix, const std::string& suffix, const std::string& grammar,
                  const GenParams& params, const std::function<bool(const std::string&)>& on_text,
                  GenStats* stats, std::string* error);

    // Stops the generate() or prime() in progress, from any thread.
    void cancel() { cancel_.store(true); }

private:
    Engine() = default;
    bool decode(const std::vector<int32_t>& tokens, bool want_logits, std::string* error);
    bool ensure_prefix(const std::string& prefix, bool* reused, int* evaluated, std::string* error);

    llama_model* model_ = nullptr;
    llama_context* ctx_ = nullptr;
    const llama_vocab* vocab_ = nullptr;
    int n_ctx_ = 0;
    int n_batch_ = 0;
    int n_past_ = 0;

    // Tokens of the primed prefix and the state snapshot taken right after evaluating them.
    std::vector<int32_t> prefix_tokens_;
    std::vector<uint8_t> prefix_state_;
    // True while the context holds exactly the prefix and nothing after it.
    bool at_prefix_ = false;

    std::atomic<bool> cancel_{false};
};

} // namespace fastchat
