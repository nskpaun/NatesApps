#include "llm_engine.h"

#include <algorithm>
#include <chrono>
#include <cmath>

#include "llama.h"

namespace fastchat {

namespace {

using Clock = std::chrono::steady_clock;

double ms_since(Clock::time_point start) {
    return std::chrono::duration<double, std::milli>(Clock::now() - start).count();
}

std::vector<llama_token> tokenize(const llama_vocab* vocab, const std::string& text) {
    if (text.empty()) return {};
    // With a null buffer llama_tokenize reports the size it needs as a negative number.
    const int needed = -llama_tokenize(vocab, text.data(), (int32_t) text.size(), nullptr, 0,
                                       /*add_special=*/false, /*parse_special=*/true);
    if (needed <= 0) return {};
    std::vector<llama_token> tokens(needed);
    const int written = llama_tokenize(vocab, text.data(), (int32_t) text.size(), tokens.data(),
                                       (int32_t) tokens.size(), false, true);
    tokens.resize(std::max(written, 0));
    return tokens;
}

// Length of the longest prefix of `bytes` that ends on a UTF-8 character boundary. A token can
// stop in the middle of a multi-byte character; those trailing bytes wait for the next token.
size_t complete_utf8_length(const std::string& bytes) {
    const size_t n = bytes.size();
    for (size_t back = 1; back <= std::min<size_t>(4, n); ++back) {
        const unsigned char c = (unsigned char) bytes[n - back];
        if ((c & 0xC0) == 0x80) continue; // continuation byte, keep looking for the lead byte
        size_t expected = 1;
        if ((c & 0xE0) == 0xC0) expected = 2;
        else if ((c & 0xF0) == 0xE0) expected = 3;
        else if ((c & 0xF8) == 0xF0) expected = 4;
        return expected > back ? n - back : n;
    }
    return n;
}

struct SamplerDeleter {
    void operator()(llama_sampler* s) const { llama_sampler_free(s); }
};

} // namespace

std::unique_ptr<Engine> Engine::load(const std::string& model_path, const LoadParams& params,
                                     std::string* error) {
    static const bool backend_ready = (llama_backend_init(), true);
    (void) backend_ready;

    std::unique_ptr<Engine> engine(new Engine());

    llama_model_params model_params = llama_model_default_params();
    model_params.n_gpu_layers = 0; // CPU only: fast enough for a small model, and it runs on any phone
    engine->model_ = llama_model_load_from_file(model_path.c_str(), model_params);
    if (!engine->model_) {
        *error = "Could not load the model file " + model_path;
        return nullptr;
    }
    engine->vocab_ = llama_model_get_vocab(engine->model_);

    llama_context_params ctx_params = llama_context_default_params();
    ctx_params.n_ctx = params.n_ctx;
    ctx_params.n_batch = 512;
    ctx_params.n_ubatch = 512;
    ctx_params.n_threads = params.n_threads;
    ctx_params.n_threads_batch = params.n_threads;
    // Lets cancel() interrupt a long prompt evaluation, not just the gap between tokens.
    ctx_params.abort_callback = [](void* flag) { return ((std::atomic<bool>*) flag)->load(); };
    ctx_params.abort_callback_data = &engine->cancel_;
    engine->ctx_ = llama_init_from_model(engine->model_, ctx_params);
    if (!engine->ctx_) {
        *error = "Could not create a model context (not enough memory?)";
        return nullptr;
    }
    engine->n_ctx_ = (int) llama_n_ctx(engine->ctx_);
    engine->n_batch_ = (int) ctx_params.n_batch;
    return engine;
}

Engine::~Engine() {
    if (ctx_) llama_free(ctx_);
    if (model_) llama_model_free(model_);
}

bool Engine::decode(const std::vector<int32_t>& tokens, bool want_logits, std::string* error) {
    if (n_past_ + (int) tokens.size() > n_ctx_) {
        *error = "The conversation is too long for the model's context";
        return false;
    }
    llama_batch batch = llama_batch_init(n_batch_, 0, 1);
    bool ok = true;
    for (size_t start = 0; start < tokens.size() && ok; start += n_batch_) {
        const int n = (int) std::min<size_t>(n_batch_, tokens.size() - start);
        batch.n_tokens = n;
        for (int i = 0; i < n; ++i) {
            batch.token[i] = tokens[start + i];
            batch.pos[i] = n_past_ + i;
            batch.n_seq_id[i] = 1;
            batch.seq_id[i][0] = 0;
            batch.logits[i] = 0;
        }
        const bool last_chunk = start + n == tokens.size();
        if (want_logits && last_chunk) batch.logits[n - 1] = 1;

        const int rc = llama_decode(ctx_, batch);
        if (rc != 0) {
            *error = rc == 2 ? "cancelled" : "llama_decode failed (" + std::to_string(rc) + ")";
            ok = false;
        } else {
            n_past_ += n;
        }
    }
    llama_batch_free(batch);
    return ok;
}

// Leaves the context holding exactly `prefix`, re-evaluating it only if it changed.
bool Engine::ensure_prefix(const std::string& prefix, bool* reused, int* evaluated,
                           std::string* error) {
    const std::vector<llama_token> tokens = tokenize(vocab_, prefix);
    *reused = false;
    *evaluated = 0;
    llama_memory_t memory = llama_get_memory(ctx_);

    if (!prefix_tokens_.empty() && tokens == prefix_tokens_) {
        if (at_prefix_) {
            *reused = true;
            return true;
        }
        // The model's hybrid (recurrent + attention) memory cannot be trimmed back to an earlier
        // position, so rewind by restoring the snapshot taken when the prefix was evaluated.
        llama_memory_clear(memory, true);
        if (!prefix_state_.empty() &&
            llama_state_seq_set_data(ctx_, prefix_state_.data(), prefix_state_.size(), 0) > 0) {
            n_past_ = (int) tokens.size();
            at_prefix_ = true;
            *reused = true;
            return true;
        }
    }

    llama_memory_clear(memory, true);
    n_past_ = 0;
    at_prefix_ = false;
    prefix_tokens_.clear();
    prefix_state_.clear();
    if (tokens.empty()) return true;

    if (!decode(tokens, /*want_logits=*/false, error)) return false;
    *evaluated = (int) tokens.size();

    prefix_state_.resize(llama_state_seq_get_size(ctx_, 0));
    const size_t written =
        llama_state_seq_get_data(ctx_, prefix_state_.data(), prefix_state_.size(), 0);
    prefix_state_.resize(written); // empty means "no snapshot": the prefix is re-evaluated instead
    prefix_tokens_ = tokens;
    at_prefix_ = true;
    return true;
}

bool Engine::prime(const std::string& prefix, std::string* error) {
    cancel_.store(false);
    bool reused = false;
    int evaluated = 0;
    return ensure_prefix(prefix, &reused, &evaluated, error);
}

bool Engine::generate(const std::string& prefix, const std::string& suffix,
                      const std::string& grammar, const GenParams& params,
                      const std::function<bool(const std::string&)>& on_text, GenStats* stats,
                      std::string* error) {
    cancel_.store(false);
    *stats = GenStats();
    const auto prompt_start = Clock::now();

    int prefix_evaluated = 0;
    if (!ensure_prefix(prefix, &stats->prefix_reused, &prefix_evaluated, error)) {
        stats->cancelled = cancel_.load();
        return false;
    }

    const std::vector<llama_token> suffix_tokens = tokenize(vocab_, suffix);
    if (suffix_tokens.empty()) {
        *error = "Empty prompt";
        return false;
    }
    at_prefix_ = false;
    if (!decode(suffix_tokens, /*want_logits=*/true, error)) {
        stats->cancelled = cancel_.load();
        return false;
    }
    stats->prompt_tokens = prefix_evaluated + (int) suffix_tokens.size();
    stats->prompt_ms = ms_since(prompt_start);

    // The grammar is kept apart from the rest of the sampler. Checking every token in the
    // vocabulary against it costs more than running a small model for a token, so the model's own
    // pick is tested first and the full check only happens when that pick breaks the format.
    std::unique_ptr<llama_sampler, SamplerDeleter> rules;
    if (!grammar.empty()) {
        rules.reset(llama_sampler_init_grammar(vocab_, grammar.c_str(), "root"));
        if (!rules) {
            *error = "The reply grammar did not parse";
            return false;
        }
    }
    std::unique_ptr<llama_sampler, SamplerDeleter> sampler(
        llama_sampler_chain_init(llama_sampler_chain_default_params()));
    llama_sampler_chain_add(sampler.get(),
                            llama_sampler_init_penalties(llama_vocab_n_tokens(vocab_), 64, 1.0f,
                                                         0.0f, params.presence_penalty));
    llama_sampler_chain_add(sampler.get(), llama_sampler_init_top_k(params.top_k));
    llama_sampler_chain_add(sampler.get(), llama_sampler_init_top_p(params.top_p, 1));
    llama_sampler_chain_add(sampler.get(), llama_sampler_init_temp(params.temperature));
    llama_sampler_chain_add(sampler.get(), llama_sampler_init_dist(params.seed));

    std::vector<llama_token_data> candidates((size_t) llama_vocab_n_tokens(vocab_));
    // Picks the next token from the latest logits, optionally restricted to what the grammar allows.
    const auto pick = [&](bool constrained) -> llama_token {
        const float* logits = llama_get_logits_ith(ctx_, -1);
        for (size_t id = 0; id < candidates.size(); ++id) {
            candidates[id] = llama_token_data{(llama_token) id, logits[id], 0.0f};
        }
        llama_token_data_array all = {candidates.data(), candidates.size(), -1, false};
        if (constrained) llama_sampler_apply(rules.get(), &all);
        llama_sampler_apply(sampler.get(), &all);
        return all.selected >= 0 ? all.data[all.selected].id : llama_vocab_eos(vocab_);
    };

    const auto output_start = Clock::now();
    std::string pending; // bytes not yet handed to on_text (an unfinished UTF-8 character)
    bool ok = true;
    while (stats->output_tokens < params.max_tokens) {
        if (cancel_.load()) {
            stats->cancelled = true;
            break;
        }
        llama_token token = pick(/*constrained=*/false);
        if (rules) {
            llama_token_data chosen = {token, 1.0f, 0.0f};
            llama_token_data_array one = {&chosen, 1, -1, false};
            llama_sampler_apply(rules.get(), &one); // the grammar marks a forbidden token -inf
            if (one.data[0].logit == -INFINITY) token = pick(/*constrained=*/true);
            llama_sampler_accept(rules.get(), token);
        }
        llama_sampler_accept(sampler.get(), token);
        if (llama_vocab_is_eog(vocab_, token)) break;
        stats->output_tokens++;

        char piece[256];
        const int n = llama_token_to_piece(vocab_, token, piece, sizeof(piece), 0, /*special=*/false);
        if (n > 0) pending.append(piece, n);
        const size_t ready = complete_utf8_length(pending);
        if (ready > 0) {
            const bool keep_going = on_text(pending.substr(0, ready));
            pending.erase(0, ready);
            if (!keep_going) break;
        }

        if (!decode({token}, /*want_logits=*/true, error)) {
            stats->cancelled = cancel_.load();
            ok = stats->cancelled; // being cancelled is not a failure
            break;
        }
    }
    stats->output_ms = ms_since(output_start);
    return ok;
}

} // namespace fastchat
