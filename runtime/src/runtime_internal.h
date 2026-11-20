#pragma once
#include "ortts_engine.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <mutex>
#include <string>

struct ortts_cancel_token {
    std::atomic<bool> cancelled{false};
};

namespace ortts::detail {
extern thread_local std::string error;
extern std::mutex execution_gate;

inline std::unique_lock<std::timed_mutex> try_acquire_execution(
    std::timed_mutex & mtx,
    std::atomic<bool> & running,
    std::atomic<bool> & cancelled,
    const ortts_exec_policy * policy,
    ortts_status & fail_status) {
    error.clear();
    fail_status = ORTTS_BUSY;
    if (policy) {
        if (policy->struct_size != sizeof(*policy) ||
            policy->timeout_ms > 30000u ||
            (policy->supersede != 0 && policy->supersede != 1)) {
            error = "Invalid execution policy";
            fail_status = ORTTS_INVALID;
            return {};
        }
    }
    if (!policy || (policy->timeout_ms == 0 && policy->supersede == 0)) {
        std::unique_lock<std::timed_mutex> lock(mtx, std::try_to_lock);
        if (!lock.owns_lock()) {
            error = "Another OrTTS operation is active";
        }
        return lock;
    }
    if (policy->supersede == 0) {
        std::unique_lock<std::timed_mutex> lock(mtx, std::chrono::milliseconds(policy->timeout_ms));
        if (!lock.owns_lock()) {
            error = "Another OrTTS operation is active";
        }
        return lock;
    }
    const uint32_t wait_ms = policy->timeout_ms ? policy->timeout_ms : 500u;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(wait_ms);
    for (;;) {
        if (running.load(std::memory_order_acquire)) {
            cancelled.store(true, std::memory_order_release);
        } else if (mtx.try_lock()) {
            return std::unique_lock<std::timed_mutex>(mtx, std::adopt_lock);
        }
        const auto now = std::chrono::steady_clock::now();
        if (now >= deadline) {
            break;
        }
        const auto slice = std::min(
            std::chrono::duration_cast<std::chrono::steady_clock::duration>(std::chrono::milliseconds(5)),
            deadline - now);
        if (mtx.try_lock_for(slice)) {
            return std::unique_lock<std::timed_mutex>(mtx, std::adopt_lock);
        }
    }
    error = "Another OrTTS operation is active";
    return {};
}
}
