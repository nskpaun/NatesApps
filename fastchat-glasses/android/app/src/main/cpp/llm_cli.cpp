// Desktop test tool: runs the same engine the phone uses against a model file.
//
//   llm_cli <model.gguf> <prefix-file> <suffix-file> [grammar-file] [runs] [threads]
//
// Prints the generated text and timings for each run. With runs > 1 the prefix is evaluated once
// and then restored from its snapshot, which is the path every reply after the first one takes.
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>

#include "llm_engine.h"

static std::string read_file(const char* path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        std::fprintf(stderr, "cannot read %s\n", path);
        std::exit(2);
    }
    std::ostringstream out;
    out << in.rdbuf();
    return out.str();
}

int main(int argc, char** argv) {
    if (argc < 4) {
        std::fprintf(stderr, "usage: %s model.gguf prefix.txt suffix.txt [grammar.gbnf] [runs] [threads]\n", argv[0]);
        return 2;
    }
    const std::string prefix = read_file(argv[2]);
    const std::string suffix = read_file(argv[3]);
    const std::string grammar = argc > 4 && argv[4][0] != '-' ? read_file(argv[4]) : "";
    const int runs = argc > 5 ? std::atoi(argv[5]) : 1;

    fastchat::LoadParams load;
    if (argc > 6) load.n_threads = std::atoi(argv[6]);
    std::string error;
    auto engine = fastchat::Engine::load(argv[1], load, &error);
    if (!engine) {
        std::fprintf(stderr, "load failed: %s\n", error.c_str());
        return 1;
    }

    // With ALT_PREFIX set, odd runs use that prefix instead: both should be "reused" from run 3 on.
    const char* alt_path = std::getenv("ALT_PREFIX");
    const std::string alt_prefix = alt_path ? read_file(alt_path) : "";

    for (int run = 0; run < runs; ++run) {
        // Sampling can be overridden from the environment, to try a model's own recommended settings.
        fastchat::GenParams params;
        if (const char* seed = std::getenv("SEED")) params.seed = (uint32_t) std::atoi(seed);
        if (const char* v = std::getenv("TEMP")) params.temperature = (float) std::atof(v);
        if (const char* v = std::getenv("TOP_P")) params.top_p = (float) std::atof(v);
        if (const char* v = std::getenv("TOP_K")) params.top_k = std::atoi(v);
        if (const char* v = std::getenv("PRESENCE")) params.presence_penalty = (float) std::atof(v);
        fastchat::GenStats stats;
        std::printf("--- run %d\n", run + 1);
        const bool ok = engine->generate(
            (alt_path && run % 2 == 1) ? alt_prefix : prefix, suffix, grammar, params,
            [](const std::string& text) {
                std::fputs(text.c_str(), stdout);
                std::fflush(stdout);
                return true;
            },
            &stats, &error);
        std::printf("\n");
        if (!ok) {
            std::fprintf(stderr, "generate failed: %s\n", error.c_str());
            return 1;
        }
        std::printf("[prompt %d tok in %.0f ms%s | output %d tok in %.0f ms = %.1f tok/s]\n",
                    stats.prompt_tokens, stats.prompt_ms, stats.prefix_reused ? ", prefix reused" : "",
                    stats.output_tokens, stats.output_ms,
                    stats.output_ms > 0 ? stats.output_tokens * 1000.0 / stats.output_ms : 0.0);
    }
    return 0;
}
