#pragma once
#include <mutex>
#include <string>
namespace ortts::detail {
extern thread_local std::string error;
extern std::mutex execution_gate;
}
